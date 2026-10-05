"""M1 full-workspace snapshot: capture and assert a content-addressed inventory.

`capture_snapshot` inventories every controlled tracked/untracked regular file
plus the deletion list and executable mode, and `assert_snapshot` re-derives the
current candidate and compares it to a previously captured snapshot. This is a
different algorithm from the M0R tracked-commit snapshot; the two digests must
not be mixed.

The snapshot hashes file *content* (sha256 of raw bytes); it does not persist
raw file contents and does not prove provenance. It is not an OS sandbox.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path

_SCHEMA_VERSION = 1
_ALLOWED_MODES = {"100644", "100755"}
_SHA_RE = re.compile(r"^(?:[a-f0-9]{40}|[a-f0-9]{64})$")


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE).decode()


def _is_git_root(root: Path) -> bool:
    try:
        out = _git(root, "rev-parse", "--is-inside-work-tree")
    except (subprocess.CalledProcessError, OSError):
        return False
    return out.strip() == "true"


def _git_toplevel(root: Path) -> str | None:
    """Resolve the actual Git working-tree root. The root passed to
    inspect_baseline may be a subdirectory; the contract requires the
    control root to be the real top level so that an attacker cannot
    narrow scope by handing us a subdir."""
    try:
        out = _git(root, "rev-parse", "--show-toplevel")
    except (subprocess.CalledProcessError, OSError):
        return None
    s = out.strip()
    return s or None


def _git_active_submodules(root: Path) -> list[str]:
    try:
        out = _git(root, "submodule", "status", "--recursive")
    except (subprocess.CalledProcessError, OSError):
        return []
    return [ln.strip().split(" ", 1)[-1] for ln in out.splitlines() if ln.strip()]


def _git_lfs_pointer_files(root: Path, paths: list[str]) -> list[str]:
    """Return the subset of `paths` whose blob content starts with the
    LFS pointer header. LFS support is not implemented; the contract
    requires honest refusal rather than silent acceptance.
    """
    found: list[str] = []
    for rel in paths:
        try:
            content = (root / rel).read_bytes()
        except OSError:
            continue
        if content.startswith(b"version https://git-lfs.github.com"):
            found.append(rel)
    return found


def _head_sha(root: Path) -> str | None:
    try:
        out = _git(root, "rev-parse", "--verify", "--end-of-options", "HEAD^{commit}")
    except (subprocess.CalledProcessError, OSError):
        return None
    sha = out.strip()
    return sha if len(sha) in (40, 64) else None


def _resolve_commit(root: Path, ref: str) -> str | None:
    try:
        out = _git(root, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}")
    except (subprocess.CalledProcessError, OSError):
        return None
    sha = out.strip()
    return sha if _SHA_RE.match(sha) else None


def _tracked_paths(root: Path) -> list[str]:
    """Return paths that exist in the working tree AND are tracked by
    the current HEAD. Includes staged additions; staged deletions are
    also returned (because git ls-files --deleted still reports them) so
    that the caller can decide what "tracked at HEAD" really means.

    Note: a plain `unlink` of a tracked file does NOT remove the entry
    from the index; the file stays "tracked" from git's view but is
    absent on disk. Callers that care about "exists on disk" should
    check the FS themselves.
    """
    out = _git(root, "ls-files", "-z")
    return [p for p in out.split("\0") if p]


def _missing_paths(root: Path) -> set[str]:
    """Return the subset of HEAD-tracked paths whose file is absent on
    disk. Captures both `git rm`-staged deletions and plain unlinks.
    """
    try:
        out = _git(root, "ls-files", "--deleted", "-z")
    except (subprocess.CalledProcessError, OSError):
        return set()
    return {p for p in out.split("\0") if p}


def _untracked_paths(root: Path) -> list[str]:
    out = _git(root, "ls-files", "--others", "--exclude-standard", "-z")
    return [p for p in out.split("\0") if p]


def _mode_of(path: Path) -> str:
    return "100755" if path.stat().st_mode & 0o111 else "100644"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _snapshot_digest(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()


def _validate_relative_path(rel: str) -> None:
    if not rel or rel.startswith("/") or "\\" in rel:
        raise ValueError(f"invalid relative path: {rel!r}")
    if rel in (".", "..") or rel.startswith("./") or rel.startswith("../"):
        raise ValueError(f"invalid relative path: {rel!r}")
    if ":" in rel:
        raise ValueError(f"invalid relative path: {rel!r}")
    for part in rel.split("/"):
        if part in ("", ".", ".."):
            raise ValueError(f"invalid relative path: {rel!r}")


def _check_links_and_case(root: Path, paths: list[str]) -> None:
    """Validate that every controlled path is a real regular file
    reachable through the supplied root. Rejects symlinks at any depth,
    hardlinks (nlink>1) on regular files, duplicate case-folds, and any
    ancestor link that escapes the control root. Refuses to walk
    directories whose entry itself is a link.
    """
    seen: set[str] = set()
    real_root = Path(os.path.realpath(root))
    for rel in paths:
        _validate_relative_path(rel)
        cf = rel.casefold()
        if cf in seen:
            raise ValueError(f"case collision under control root: {rel}")
        seen.add(cf)
        target = root / rel
        # Every path segment between root and target must be a real dir
        # (not a symlink) so the controlled root cannot be escaped via
        # an intermediate link.
        anchor = root
        for segment in rel.split("/")[:-1]:
            anchor = anchor / segment
            try:
                if anchor.is_symlink() or os.path.islink(str(anchor)):
                    raise ValueError(f"ancestor link not supported: {rel}")
            except OSError as e:
                raise ValueError(f"ancestor not statable: {anchor}") from e
        if target.is_symlink():
            raise ValueError(f"symlink not supported: {rel}")
        try:
            st = target.lstat()
        except OSError:
            continue
        if os.path.islink(str(target)):
            raise ValueError(f"symlink not supported: {rel}")
        if stat.S_ISLNK(st.st_mode):
            raise ValueError(f"symlink not supported: {rel}")
        if st.st_nlink > 1:
            raise ValueError(f"hardlink not supported: {rel}")
        # Resolve target's real path and confirm it stays under real_root.
        try:
            real_target = Path(os.path.realpath(target))
        except OSError as e:
            raise ValueError(f"target not resolvable: {rel}") from e
        if real_target != real_root / rel:
            raise ValueError(f"target escapes control root: {rel}")


def _inventory(root: Path, baseline_commit: str) -> dict:
    # Tracked paths at HEAD (current index) — the same set the contract
    # expects to see in baseline. Untracked paths under fixed artifact dirs
    # (.venv etc.) are not added: those are governed by inspect_baseline.
    tracked = _tracked_paths(root)
    untracked = _untracked_paths(root)
    all_paths = tracked + untracked

    # Submodules are not supported by the contract — refuse explicitly.
    submods = _git_active_submodules(root)
    if submods:
        raise ValueError(f"submodules not supported: {submods}")

    # LFS pointers are not supported — refuse explicitly.
    lfs = _git_lfs_pointer_files(root, all_paths)
    if lfs:
        raise ValueError(f"git-lfs pointers not supported: {lfs}")

    _check_links_and_case(root, all_paths)

    tracked_set = set(tracked)
    # Files missing on disk: combine ls-files --deleted (captures staged
    # removals) with a plain existence check (captures plain unlinks).
    missing = _missing_paths(root)
    for rel in tracked_set:
        if not (root / rel).exists():
            missing.add(rel)

    files: list[dict] = []
    for rel in all_paths:
        target = root / rel
        if not target.is_file():
            continue
        files.append({"path": rel, "mode": _mode_of(target), "sha256": _sha256_file(target)})

    # deleted = paths that the baseline_commit tree had but the working
    # tree has removed (staged `git rm` or plain `unlink`). Derivation is
    # from baseline_commit tree ∩ (HEAD index missing) — the contract
    # explicitly requires comparing against the baseline_commit, not the
    # current index alone.
    baseline_paths = _tracked_paths_at(root, baseline_commit)
    deleted = sorted(p for p in baseline_paths if p in missing)
    files.sort(key=lambda f: f["path"])
    return {
        "schema_version": _SCHEMA_VERSION,
        "baseline_commit": baseline_commit,
        "files": files,
        "deleted": deleted,
    }


def _tracked_paths_at(root: Path, ref: str) -> list[str]:
    try:
        out = _git(root, "ls-tree", "--name-only", "-r", "-z", ref)
    except (subprocess.CalledProcessError, OSError):
        return []
    return [p for p in out.split("\0") if p]


def _validate_expected(expected: dict) -> None:
    if not isinstance(expected, dict):
        raise ValueError("snapshot must be a dict")
    if set(expected) != {
        "schema_version",
        "baseline_commit",
        "files",
        "deleted",
        "snapshot_sha256",
    }:
        raise ValueError("snapshot has unexpected fields")
    # schema_version must be the integer 1.
    sv = expected["schema_version"]
    if isinstance(sv, bool) or not isinstance(sv, int) or sv != 1:
        raise ValueError("snapshot schema_version must be the integer 1")
    if not isinstance(expected["baseline_commit"], str) or not _SHA_RE.match(
        expected["baseline_commit"]
    ):
        raise ValueError("invalid baseline_commit")
    if not isinstance(expected["files"], list) or not isinstance(expected["deleted"], list):
        raise ValueError("files/deleted must be lists")
    files = expected["files"]
    seen_paths: set[str] = set()
    seen_cf: set[str] = set()
    prev = None
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {"path", "mode", "sha256"}:
            raise ValueError("invalid file entry")
        if (
            not isinstance(entry["mode"], str)
            or not isinstance(entry["sha256"], str)
            or not _SHA_RE.match(entry["sha256"])
        ):
            raise ValueError("invalid file entry")
        if entry["mode"] not in _ALLOWED_MODES:
            raise ValueError(f"invalid mode: {entry['mode']}")
        _validate_relative_path(entry["path"])
        if prev is not None and entry["path"] < prev["path"]:
            raise ValueError("snapshot files must be sorted")
        cf = entry["path"].casefold()
        if cf in seen_cf:
            raise ValueError(f"snapshot files has case-fold collision: {entry['path']}")
        seen_cf.add(cf)
        if entry["path"] in seen_paths:
            raise ValueError(f"snapshot files has duplicate path: {entry['path']}")
        seen_paths.add(entry["path"])
        prev = entry
    deleted = expected["deleted"]
    deleted_seen_cf: set[str] = set()
    deleted_seen: set[str] = set()
    prev_d = None
    for rel in deleted:
        if not isinstance(rel, str):
            raise ValueError("snapshot deleted must be a list of strings")
        _validate_relative_path(rel)
        if prev_d is not None and rel < prev_d:
            raise ValueError("snapshot deleted must be sorted")
        cf = rel.casefold()
        if cf in deleted_seen_cf:
            raise ValueError(f"snapshot deleted has case-fold collision: {rel}")
        deleted_seen_cf.add(cf)
        if rel in deleted_seen:
            raise ValueError(f"snapshot deleted has duplicate: {rel}")
        deleted_seen.add(rel)
        if rel in seen_paths:
            raise ValueError(f"snapshot deleted overlaps files: {rel}")
        prev_d = rel
    # Self-digest must be internally consistent.
    payload = {k: v for k, v in expected.items() if k != "snapshot_sha256"}
    if _snapshot_digest(payload) != expected["snapshot_sha256"]:
        raise ValueError("snapshot self-digest mismatch")


def capture_snapshot(repo: Path, *, baseline_commit: str) -> dict:
    """Capture a full-workspace snapshot and return the strict snapshot dict."""
    root = Path(repo)
    if root.is_symlink():
        raise ValueError("snapshot root must not be a symlink")
    if not root.is_dir():
        raise ValueError("snapshot root must be a directory")
    if not _is_git_root(root):
        raise ValueError("not a Git working tree")
    # The control root must be the actual Git top-level, not a subdir
    # that would let an attacker narrow scope.
    toplevel = _git_toplevel(root)
    if toplevel is None:
        raise ValueError("could not resolve Git top-level")
    if Path(toplevel).resolve(strict=False) != root.resolve(strict=False):
        raise ValueError(
            f"snapshot root must be Git top-level; got {root}, top-level is {toplevel}"
        )
    if not isinstance(baseline_commit, str) or not _SHA_RE.match(baseline_commit):
        raise ValueError("baseline_commit must be a full 40/64 lowercase hex SHA")
    if _resolve_commit(root, baseline_commit) is None:
        raise ValueError("baseline_commit does not resolve to a commit")

    payload = _inventory(root, baseline_commit)
    payload["snapshot_sha256"] = _snapshot_digest(payload)
    return payload


def assert_snapshot(repo: Path, expected: dict) -> None:
    """Re-derive the current candidate and require it to equal `expected`."""
    _validate_expected(expected)
    root = Path(repo)
    if root.is_symlink():
        raise ValueError("snapshot root must not be a symlink")
    if not root.is_dir():
        raise ValueError("snapshot root must be a directory")
    if not _is_git_root(root):
        raise ValueError("not a Git working tree")
    current = capture_snapshot(root, baseline_commit=expected["baseline_commit"])
    if current != expected:
        raise ValueError("snapshot does not match current workspace")
