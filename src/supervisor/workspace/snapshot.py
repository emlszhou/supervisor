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


def _resolve_commit(root: Path, ref: str) -> str | None:
    try:
        out = _git(root, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}")
    except (subprocess.CalledProcessError, OSError):
        return None
    sha = out.strip()
    return sha if _SHA_RE.match(sha) else None


def _tracked_paths(root: Path) -> list[str]:
    out = _git(root, "ls-files", "-z")
    return [p for p in out.split("\0") if p]


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
    seen: set[str] = set()
    for rel in paths:
        _validate_relative_path(rel)
        cf = rel.casefold()
        if cf in seen:
            raise ValueError(f"case collision under control root: {rel}")
        seen.add(cf)
        target = root / rel
        if target.is_symlink():
            raise ValueError(f"symlink not supported: {rel}")
        try:
            st = target.lstat()
        except OSError:
            continue
        if os.path.islink(str(target)):
            raise ValueError(f"symlink not supported: {rel}")
        if st.st_nlink > 1:
            raise ValueError(f"hardlink not supported: {rel}")


def _inventory(root: Path, baseline_commit: str) -> dict:
    tracked = _tracked_paths(root)
    untracked = _untracked_paths(root)
    all_paths = tracked + untracked
    _check_links_and_case(root, all_paths)

    tracked_set = set(tracked)
    files: list[dict] = []
    for rel in all_paths:
        target = root / rel
        if not target.is_file():
            continue
        files.append({"path": rel, "mode": _mode_of(target), "sha256": _sha256_file(target)})

    deleted = sorted(p for p in tracked_set if not (root / p).exists())
    files.sort(key=lambda f: f["path"])
    return {
        "schema_version": _SCHEMA_VERSION,
        "baseline_commit": baseline_commit,
        "files": files,
        "deleted": deleted,
    }


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
    if expected["schema_version"] != _SCHEMA_VERSION:
        raise ValueError("unsupported snapshot schema_version")
    if not isinstance(expected["baseline_commit"], str) or not _SHA_RE.match(
        expected["baseline_commit"]
    ):
        raise ValueError("invalid baseline_commit")
    if not isinstance(expected["files"], list) or not isinstance(expected["deleted"], list):
        raise ValueError("files/deleted must be lists")
    for entry in expected["files"]:
        if not isinstance(entry, dict) or set(entry) != {"path", "mode", "sha256"}:
            raise ValueError("invalid file entry")
        if entry["mode"] not in _ALLOWED_MODES:
            raise ValueError(f"invalid mode: {entry['mode']}")
        _validate_relative_path(entry["path"])
    for rel in expected["deleted"]:
        _validate_relative_path(rel)
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
