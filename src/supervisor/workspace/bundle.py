"""Freeze and verify an M1 task bundle as a content-addressed directory.

`freeze_bundle` copies a draft task directory verbatim into a fresh output
directory, switches task.json to status=frozen with the supplied baseline
commit, and emits a content-addressed manifest. `verify_bundle` re-checks the
manifest and the directory inventory against a trusted checksum provided by
the caller; it never derives the trusted checksum from the bundle itself.

The manifest is the single source of truth for what files are part of the
bundle and what their raw-byte SHA256 digests are. This module never runs
Git, never opens the network, and never imports third-party libraries: all
JSON schema checks are implemented in the standard library per the contract.

Trust boundary: freeze_bundle trusts the *contents* of the source directory
(bytes are copied verbatim) but does not trust the caller-provided
task_id or baseline_commit for correctness beyond their syntactic shape
(the task.json itself is validated against the v1 schema). verify_bundle
trusts the caller's expected manifest SHA256; the manifest itself is only
trustworthy insofar as it was produced by freeze_bundle for that source.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from pathlib import Path

# Mirror the v1 contract: no third-party deps.
_TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SHA_RE = re.compile(r"^(?:[a-f0-9]{40}|[a-f0-9]{64})$")
_ROLE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

_REQUIRED_TASK_FILES = (
    "task.json",
    "requirements.md",
    "allowed_files.json",
    "forbidden_files.json",
    "verification.json",
)


# ---------- JSON v1 validators (stdlib-only per contract) ----------


def _validate_task_v1(task: object, *, expected_task_id: str, require_draft: bool) -> None:
    if not isinstance(task, dict):
        raise ValueError("task.json must be a JSON object")
    required = {
        "schema_version",
        "task_id",
        "revision",
        "status",
        "baseline_commit",
        "requirements_file",
        "allowed_files_file",
        "forbidden_files_file",
        "verification_file",
        "roles",
        "budgets",
    }
    if set(task) != required:
        raise ValueError("task.json has unexpected or missing fields")
    if task["schema_version"] != 1:
        raise ValueError("task.json schema_version must be 1")
    if not isinstance(task["task_id"], str) or not _TASK_ID_RE.match(task["task_id"]):
        raise ValueError("task.json task_id has invalid shape")
    if task["task_id"] != expected_task_id:
        raise ValueError("task.json task_id does not match freeze_bundle(task_id=)")
    if (
        not isinstance(task["revision"], int)
        or task["revision"] < 1
        or isinstance(task["revision"], bool)
    ):
        raise ValueError("task.json revision must be a positive integer")
    if task["status"] not in ("draft", "frozen"):
        raise ValueError("task.json status must be 'draft' or 'frozen'")
    if require_draft and task["status"] != "draft":
        raise ValueError("freeze_bundle requires task.json status='draft'")
    bc = task["baseline_commit"]
    if require_draft:
        if bc is not None:
            raise ValueError("freeze_bundle requires task.json baseline_commit=null")
    else:
        if not isinstance(bc, str) or not _SHA_RE.match(bc):
            raise ValueError("frozen task.json baseline_commit must be a 40/64 lowercase hex SHA")
    expected_pointers = {
        "requirements_file": "requirements.md",
        "allowed_files_file": "allowed_files.json",
        "forbidden_files_file": "forbidden_files.json",
        "verification_file": "verification.json",
    }
    for key, expected in expected_pointers.items():
        if task[key] != expected:
            raise ValueError(f"task.json {key} has unexpected value")
    # roles: 5 entries, each matching identity regex.
    if not isinstance(task["roles"], dict) or set(task["roles"]) != {
        "planner",
        "implementer",
        "reviewer",
        "fallback_repairer",
        "final_verifier",
    }:
        raise ValueError("task.json roles has unexpected shape")
    for k, v in task["roles"].items():
        if not isinstance(v, str) or not _ROLE_ID_RE.match(v):
            raise ValueError(f"task.json roles.{k} has invalid identity")
    # budgets: required keys, all non-negative ints > 0.
    budgets = task["budgets"]
    if not isinstance(budgets, dict) or set(budgets) != {
        "max_agent_calls",
        "max_repair_rounds",
        "max_takeovers",
        "max_wall_seconds",
        "max_changed_files",
        "max_diff_lines",
        "max_output_bytes",
    }:
        raise ValueError("task.json budgets has unexpected shape")
    for k, v in budgets.items():
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError(f"task.json budgets.{k} must be an integer")
        if v < 1:
            raise ValueError(f"task.json budgets.{k} must be >= 1")
        if k in ("max_repair_rounds", "max_takeovers") and v > 1:
            raise ValueError(f"task.json budgets.{k} must be <= 1")


def _validate_verification_v1(v: object) -> None:
    if not isinstance(v, dict) or set(v) != {"schema_version", "checks"}:
        raise ValueError("verification.json has unexpected shape")
    if v["schema_version"] != 1:
        raise ValueError("verification.json schema_version must be 1")
    checks = v["checks"]
    if not isinstance(checks, list) or not checks:
        raise ValueError("verification.json checks must be a non-empty list")
    for i, c in enumerate(checks):
        if not isinstance(c, dict) or set(c) != {"id", "kind", "argv", "cwd", "required"}:
            raise ValueError(f"verification.json checks[{i}] has unexpected shape")
        if not isinstance(c["id"], str) or not _TASK_ID_RE.match(c["id"]):
            raise ValueError(f"verification.json checks[{i}].id invalid")
        if c["kind"] not in ("project", "protected", "independent"):
            raise ValueError(f"verification.json checks[{i}].kind invalid")
        if (
            not isinstance(c["argv"], list)
            or not c["argv"]
            or not all(isinstance(a, str) and a for a in c["argv"])
        ):
            raise ValueError(f"verification.json checks[{i}].argv must be non-empty strings")
        if c["cwd"] != ".":
            raise ValueError(f"verification.json checks[{i}].cwd must be '.'")
        if not isinstance(c["required"], bool):
            raise ValueError(f"verification.json checks[{i}].required must be a bool")


def _validate_string_list_file(payload: object, *, name: str) -> None:
    if not isinstance(payload, list) or not all(isinstance(x, str) and x for x in payload):
        raise ValueError(f"{name} must be a list of non-empty strings")


# ---------- Path safety helpers ----------


def _validate_relative_posix(rel: str) -> None:
    if not rel or rel.startswith("/") or "\\" in rel:
        raise ValueError(f"invalid relative path: {rel!r}")
    if rel in (".", "..") or rel.startswith("./") or rel.startswith("../"):
        raise ValueError(f"invalid relative path: {rel!r}")
    if ":" in rel:
        raise ValueError(f"invalid relative path: {rel!r}")
    for part in rel.split("/"):
        if part in ("", ".", ".."):
            raise ValueError(f"invalid relative path: {rel!r}")


def _is_symlink(p: Path) -> bool:
    try:
        return p.is_symlink()
    except OSError:
        return False


def _realpath_no_symlinks(p: Path) -> Path:
    return Path(os.path.realpath(p))


def _validate_source_no_links(source: Path) -> None:
    """Reject any symlink, hardlink, case collision, or path traversal in source.

    Walks every directory entry and every file inside the source tree.
    Directories are checked for symlinks (an ancestor link would escape
    the control root) but are NOT checked for ``nlink>1``: a normal
    directory has ``nlink>=2`` because of the ``.`` self-entry and the
    parent link, and rejecting that would make any nested-directory
    input unprocessable.
    """
    real_root = _realpath_no_symlinks(source)
    if real_root != Path(os.path.realpath(source)):
        raise ValueError("source path must not be a symlink itself")
    seen: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(source, followlinks=False):
        if _is_symlink(Path(dirpath)):
            raise ValueError(f"source directory must not be a symlink: {dirpath}")
        for dname in list(dirnames):
            full = Path(dirpath) / dname
            if _is_symlink(full):
                raise ValueError(f"source must not contain symlinks: {full}")
            try:
                st = full.lstat()
            except OSError as e:
                raise ValueError(f"source entry not statable: {full}: {e}") from e
            if stat.S_ISLNK(st.st_mode):
                raise ValueError(f"source must not contain symlinks: {full}")
            # Resolve the directory's real path; reject ancestor links
            # that would escape the control root.
            try:
                if Path(os.path.realpath(full)) != real_root / full.relative_to(source):
                    raise ValueError(f"source directory escapes control root: {full}")
            except OSError as e:
                raise ValueError(f"source directory not resolvable: {full}: {e}") from e
        for name in list(filenames):
            full = Path(dirpath) / name
            if _is_symlink(full):
                raise ValueError(f"source must not contain symlinks: {full}")
            try:
                st = full.lstat()
            except OSError as e:
                raise ValueError(f"source entry not statable: {full}: {e}") from e
            if stat.S_ISLNK(st.st_mode):
                raise ValueError(f"source must not contain symlinks: {full}")
            if st.st_nlink > 1:
                raise ValueError(f"source must not contain hardlinks: {full}")
            # Refuse any link that resolves outside the source tree.
            try:
                if Path(os.path.realpath(full)) != real_root / full.relative_to(source):
                    raise ValueError(f"source file escapes control root: {full}")
            except OSError as e:
                raise ValueError(f"source file not resolvable: {full}: {e}") from e
            rel = full.relative_to(source).as_posix()
            _validate_relative_posix(rel)
            cf = rel.casefold()
            if cf in seen:
                raise ValueError(f"source case collision: {rel}")
            seen.add(cf)


def _validate_output_does_not_overlap(source: Path, output: Path, workdir: Path) -> None:
    """Reject pre-existing output, output inside source, output escaping via parent link."""
    if output.exists() or output.is_symlink():
        raise ValueError("output directory must not exist before freeze")
    if _is_symlink(output.parent):
        raise ValueError("output parent must not be a symlink")
    real_source = _realpath_no_symlinks(source)
    if not workdir.is_dir():
        raise ValueError("internal: freeze workdir is missing")
    # Ensure output (created later as workdir/..) does not live under real_source.
    # If real_output is inside real_source or equal, reject.
    real_output_target = _realpath_no_symlinks(output.parent) / output.name
    if str(real_output_target) == str(real_source) or str(real_output_target).startswith(
        str(real_source) + os.sep
    ):
        raise ValueError("output path must not be inside source")
    # Reject any ancestor of `output` that is a symlink, including the
    # full chain from `output.parent` up to filesystem root. The walk is
    # bounded by symlink detection: if a link is observed mid-chain,
    # raise before reaching it.
    chain = output.parent
    while chain != chain.parent:
        try:
            if chain.is_symlink() or os.path.islink(str(chain)):
                raise ValueError(f"output ancestor must not be a symlink: {chain}")
        except OSError as e:
            raise ValueError(f"output ancestor not statable: {chain}") from e
        if chain == Path("/"):
            break
        chain = chain.parent


# ---------- Freeze ----------


def _copy_regular_file(src: Path, dst: Path) -> None:
    """Copy raw bytes from src to dst; reject any link or special file."""
    if _is_symlink(src):
        raise ValueError(f"source must not contain symlinks: {src}")
    with src.open("rb") as fh:
        data = fh.read()
    with dst.open("wb") as fh:
        fh.write(data)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _build_manifest_bytes(
    *,
    task_id: str,
    baseline_commit: str,
    files: dict[str, str],
) -> bytes:
    """Produce manifest JSON bytes exactly as contract requires: sorted keys,
    compact separators, ensure_ascii=False, no trailing newline.
    """
    payload = {
        "schema_version": 1,
        "task_id": task_id,
        "baseline_commit": baseline_commit,
        "files": dict(sorted(files.items())),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return encoded.encode("utf-8")


def freeze_bundle(
    source: Path,
    output: Path,
    *,
    task_id: str,
    baseline_commit: str,
) -> str:
    """Freeze `source` into a new directory at `output`. Returns manifest SHA256."""
    source = Path(source)
    output = Path(output)
    if not isinstance(baseline_commit, str) or not _SHA_RE.match(baseline_commit):
        raise ValueError("baseline_commit must be a 40/64 lowercase hex SHA")
    if not isinstance(task_id, str) or not _TASK_ID_RE.match(task_id):
        raise ValueError("task_id has invalid shape")

    # Reject any link/collision/escape in the source.
    _validate_source_no_links(source)
    if (source / "manifest.json").exists():
        raise ValueError("source must not already contain manifest.json")

    # Validate and read each required input.
    task_path = source / "task.json"
    if not task_path.is_file():
        raise ValueError("source missing task.json")
    try:
        task_obj = json.loads(task_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"task.json is not valid JSON: {e}") from e
    _validate_task_v1(task_obj, expected_task_id=task_id, require_draft=True)

    req_path = source / "requirements.md"
    if not req_path.is_file():
        raise ValueError("source missing requirements.md")
    allowed_path = source / "allowed_files.json"
    if not allowed_path.is_file():
        raise ValueError("source missing allowed_files.json")
    forbidden_path = source / "forbidden_files.json"
    if not forbidden_path.is_file():
        raise ValueError("source missing forbidden_files.json")
    verification_path = source / "verification.json"
    if not verification_path.is_file():
        raise ValueError("source missing verification.json")

    try:
        allowed_obj = json.loads(allowed_path.read_text(encoding="utf-8"))
        _validate_string_list_file(allowed_obj, name="allowed_files.json")
    except json.JSONDecodeError as e:
        raise ValueError(f"allowed_files.json is not valid JSON: {e}") from e

    try:
        forbidden_obj = json.loads(forbidden_path.read_text(encoding="utf-8"))
        _validate_string_list_file(forbidden_obj, name="forbidden_files.json")
    except json.JSONDecodeError as e:
        raise ValueError(f"forbidden_files.json is not valid JSON: {e}") from e

    try:
        verification_obj = json.loads(verification_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"verification.json is not valid JSON: {e}") from e
    _validate_verification_v1(verification_obj)

    # Build the frozen task.json payload (do not mutate source).
    frozen_task = dict(task_obj)
    frozen_task["status"] = "frozen"
    frozen_task["baseline_commit"] = baseline_commit
    frozen_task_bytes = json.dumps(
        frozen_task, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")

    # Compute digests of every file that will be written (including the new task.json).
    files_for_manifest: dict[str, str] = {}
    files_for_manifest["task.json"] = _sha256_bytes(frozen_task_bytes)
    files_for_manifest["requirements.md"] = _sha256_bytes(req_path.read_bytes())
    files_for_manifest["allowed_files.json"] = _sha256_bytes(allowed_path.read_bytes())
    files_for_manifest["forbidden_files.json"] = _sha256_bytes(forbidden_path.read_bytes())
    files_for_manifest["verification.json"] = _sha256_bytes(verification_path.read_bytes())

    manifest_bytes = _build_manifest_bytes(
        task_id=task_id,
        baseline_commit=baseline_commit,
        files=files_for_manifest,
    )
    manifest_sha = _sha256_bytes(manifest_bytes)

    # Write to a temporary directory first; only after all writes succeed do we
    # rename into the final output location. Output must not pre-exist.
    if output.exists() or output.is_symlink():
        raise ValueError("output directory must not exist before freeze")

    output_parent = output.parent
    workdir = Path(tempfile.mkdtemp(prefix="m1_freeze_", dir=str(output_parent)))
    try:
        _validate_output_does_not_overlap(source, output, workdir)
        # Write all files (mode 444 applied at the end after fsync).
        (workdir / "task.json").write_bytes(frozen_task_bytes)
        (workdir / "requirements.md").write_bytes(req_path.read_bytes())
        (workdir / "allowed_files.json").write_bytes(allowed_path.read_bytes())
        (workdir / "forbidden_files.json").write_bytes(forbidden_path.read_bytes())
        (workdir / "verification.json").write_bytes(verification_path.read_bytes())
        (workdir / "manifest.json").write_bytes(manifest_bytes)
        # Make all outputs read-only (mode 0o444 == 0o100_444 == stat.S_IRUSR|...).
        for entry in workdir.iterdir():
            if _is_symlink(entry):
                raise ValueError(f"workdir leaked a symlink: {entry}")
            os.chmod(entry, 0o444)
        # Verify the on-disk manifest digest before rename.
        on_disk = (workdir / "manifest.json").read_bytes()
        if _sha256_bytes(on_disk) != manifest_sha:
            raise ValueError("internal: manifest digest mismatch before rename")
        # Atomic rename to the requested output location.
        os.replace(str(workdir), str(output))
    except BaseException:
        # Clean up only what we created.
        try:
            if workdir.exists():
                for entry in workdir.iterdir():
                    try:
                        entry.unlink()
                    except OSError:
                        pass
                workdir.rmdir()
        except OSError:
            pass
        raise

    return manifest_sha


# ---------- Verify ----------


def _read_only_inventory(root: Path) -> tuple[set[str], set[int], set[str]]:
    """Walk root (no symlink following). Return (paths, inodes, seen_paths).

    Used to detect hardlinks (nlink>1) and to confirm no symlinks exist in
    the bundle directory tree.
    """
    paths: set[str] = set()
    inodes: set[int] = set()
    seen_paths: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel_dir = os.path.relpath(dirpath, root)
        if _is_symlink(Path(dirpath)) and dirpath != str(root):
            raise ValueError(f"bundle directory must not be a symlink: {dirpath}")
        for dname in list(dirnames):
            full = Path(dirpath) / dname
            if _is_symlink(full):
                raise ValueError(f"bundle must not contain symlinks: {full}")
            try:
                full.lstat()
            except OSError as e:
                raise ValueError(f"bundle entry not statable: {full}: {e}") from e
        for name in list(filenames):
            full = Path(dirpath) / name
            if _is_symlink(full):
                raise ValueError(f"bundle must not contain symlinks: {full}")
            try:
                st = full.lstat()
            except OSError as e:
                raise ValueError(f"bundle entry not statable: {full}: {e}") from e
            if stat.S_ISLNK(st.st_mode):
                raise ValueError(f"bundle must not contain symlinks: {full}")
            # nlink>1 is meaningful for regular files (a second directory
            # entry links to the same inode); directories routinely have
            # nlink>=2 because of `.` and `..`, so we don't apply the check
            # to them.
            if stat.S_ISREG(st.st_mode) and st.st_nlink > 1:
                raise ValueError(f"bundle must not contain hardlinks: {full}")
            rel = (Path(rel_dir) / name).as_posix() if rel_dir else name
            _validate_relative_posix(rel)
            cf = rel.casefold()
            if cf in seen_paths:
                raise ValueError(f"bundle case collision: {rel}")
            seen_paths.add(cf)
            paths.add(rel)
            inodes.add(st.st_ino)
    return paths, inodes, seen_paths


def _parse_manifest_bytes(manifest_bytes: bytes) -> dict:
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"manifest.json is not valid UTF-8 JSON: {e}") from e
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema_version",
        "task_id",
        "baseline_commit",
        "files",
    }:
        raise ValueError("manifest.json has unexpected fields")
    if manifest["schema_version"] != 1:
        raise ValueError("manifest.json schema_version must be 1")
    if not isinstance(manifest["task_id"], str) or not _TASK_ID_RE.match(manifest["task_id"]):
        raise ValueError("manifest.json task_id invalid")
    if not isinstance(manifest["baseline_commit"], str) or not _SHA_RE.match(
        manifest["baseline_commit"]
    ):
        raise ValueError("manifest.json baseline_commit invalid")
    if not isinstance(manifest["files"], dict):
        raise ValueError("manifest.json files must be a dict")
    for path, digest in manifest["files"].items():
        if not isinstance(path, str) or not _TASK_ID_RE.match(path):
            raise ValueError(f"manifest.json files key invalid: {path!r}")
        if not isinstance(digest, str) or not _SHA_RE.match(digest):
            raise ValueError(f"manifest.json files[{path!r}] digest invalid")
    return manifest


def verify_bundle(root: Path, expected_sha256: str) -> dict:
    """Verify the bundle at `root` against the trusted manifest SHA256.

    Returns the manifest dict on success. Raises ValueError on any failure;
    never mutates the bundle.
    """
    root = Path(root)
    if not isinstance(expected_sha256, str) or not _SHA_RE.match(expected_sha256):
        raise ValueError("expected_sha256 must be a 40/64 lowercase hex SHA")
    if root.is_symlink():
        raise ValueError("bundle root must not be a symlink")
    if not root.is_dir():
        raise ValueError("bundle root must be a directory")

    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("bundle missing manifest.json")
    manifest_bytes = manifest_path.read_bytes()
    if _sha256_bytes(manifest_bytes) != expected_sha256:
        raise ValueError("manifest digest does not match expected_sha256")
    manifest = _parse_manifest_bytes(manifest_bytes)

    # Validate manifest.files is sorted (sorted_keys=True in encoder); JSON
    # round-trip through dict preserves insertion order in Python 3.7+ but the
    # contract requires explicit sorted-key encoding. We re-canonicalize here
    # and confirm the on-disk bytes match the canonical encoding.
    expected_canonical = _build_manifest_bytes(
        task_id=manifest["task_id"],
        baseline_commit=manifest["baseline_commit"],
        files=manifest["files"],
    )
    if expected_canonical != manifest_bytes:
        raise ValueError("manifest.json is not in canonical sorted-key compact encoding")

    paths, _inodes, _seen = _read_only_inventory(root)
    # The manifest itself is part of the bundle directory but is NOT listed
    # in manifest.files (per contract: "files...不含manifest自身").
    paths.discard("manifest.json")

    # The inventory must equal exactly the manifest.files keys.
    manifest_paths = set(manifest["files"].keys())
    if paths != manifest_paths:
        missing = manifest_paths - paths
        extra = paths - manifest_paths
        if missing:
            raise ValueError(f"bundle missing files: {sorted(missing)}")
        if extra:
            raise ValueError(f"bundle has extra files: {sorted(extra)}")

    # Identity / baseline: confirm task.json digest matches manifest, and that
    # task.json's baseline_commit equals the manifest's.
    task_path = root / "task.json"
    task_bytes = task_path.read_bytes()
    if _sha256_bytes(task_bytes) != manifest["files"]["task.json"]:
        raise ValueError("task.json digest does not match manifest entry")
    try:
        task_obj = json.loads(task_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"task.json is not valid UTF-8 JSON: {e}") from e
    _validate_task_v1(task_obj, expected_task_id=manifest["task_id"], require_draft=False)
    if task_obj["status"] != "frozen":
        raise ValueError("bundle task.json status must be 'frozen'")
    if task_obj["baseline_commit"] != manifest["baseline_commit"]:
        raise ValueError("task.json baseline_commit does not match manifest")
    if task_obj["task_id"] != manifest["task_id"]:
        raise ValueError("task.json task_id does not match manifest")

    # Confirm every digest matches the on-disk content.
    for rel, expected_digest in sorted(manifest["files"].items()):
        actual = _sha256_bytes((root / rel).read_bytes())
        if actual != expected_digest:
            raise ValueError(f"digest mismatch for {rel}")

    return manifest
