"""Controlled working-tree inventory; hashes detect changes, not an OS sandbox."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path

_SHA_RE = re.compile(r"(?:[a-f0-9]{40}|[a-f0-9]{64})")
_SHA256_RE = re.compile(r"[a-f0-9]{64}")
_ALLOWED_MODES = {"100644", "100755"}
_EXCLUDED_DIRS = {".venv", ".supervisor", ".pytest_cache", ".ruff_cache", "__pycache__"}


def _git(root: Path, *args: str) -> str:
    raw = subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE)
    try:
        return raw.decode()
    except UnicodeDecodeError as e:
        raise ValueError("Git paths must be valid UTF-8") from e


def _validate_relative_path(rel: str) -> None:
    if (
        not isinstance(rel, str)
        or not rel
        or any(c in rel for c in "\\:\0")
        or any(p in ("", ".", "..") for p in rel.split("/"))
    ):
        raise ValueError(f"invalid relative path: {rel!r}")


def _check_ancestors(path: Path) -> Path:
    path = path.absolute()
    for ancestor in reversed((path, *path.parents)):
        try:
            st = ancestor.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(st.st_mode):
            raise ValueError(f"symlink not supported: {ancestor}")
        if ancestor != path and not stat.S_ISDIR(st.st_mode):
            raise ValueError(f"ancestor is not a directory: {ancestor}")
    return path


def _root(repo: Path) -> Path:
    root = _check_ancestors(Path(repo))
    if not root.is_dir():
        raise ValueError("control root must be a directory")
    try:
        top = _git(root, "rev-parse", "--show-toplevel").strip()
    except subprocess.CalledProcessError as e:
        raise ValueError("not a Git working tree") from e
    if Path(top).absolute() != root:
        raise ValueError("control root must be the actual Git top-level")
    return root


def _tree_paths(root: Path, ref: str) -> list[str]:
    rows = _git(root, "ls-tree", "-r", "-z", ref).split("\0")
    paths = []
    for row in filter(None, rows):
        header, rel = row.split("\t", 1)
        if header.split()[0] == "160000":
            raise ValueError("submodules not supported")
        paths.append(rel)
    return paths


def _tracked_paths(root: Path) -> list[str]:
    paths = []
    for row in filter(None, _git(root, "ls-files", "--stage", "-z").split("\0")):
        header, rel = row.split("\t", 1)
        mode, _, stage = header.split()
        if mode == "160000" or stage != "0":
            raise ValueError("submodules or unresolved index not supported")
        paths.append(rel)
    return paths


def _signature(st: os.stat_result) -> tuple:
    return (
        st.st_dev,
        st.st_ino,
        st.st_mode,
        st.st_nlink,
        st.st_size,
        st.st_mtime_ns,
        st.st_ctime_ns,
    )


def _open_directory(path: Path) -> int:
    if (
        not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_DIRECTORY")
        or os.open not in os.supports_dir_fd
    ):
        raise ValueError("OS lacks required no-follow directory opening capability")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(path.anchor, flags)
    try:
        for part in path.parts[1:]:
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _inventory_paths(root: Path, tracked: list[str] | None = None) -> dict[str, tuple]:
    """No-follow traversal; fixed exclusions apply only to untracked artifacts."""
    inventory, folded = {}, set()
    tracked = None if tracked is None else set(tracked)

    def walk(fd: int, prefix: str) -> None:
        with os.scandir(fd) as entries:
            names = [entry.name for entry in entries]
        for name in names:
            rel = prefix + name
            _validate_relative_path(rel)
            st = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if tracked is not None:
                if rel == ".git":
                    continue
                excluded = any(p in _EXCLUDED_DIRS for p in rel.split("/")[:-1])
                excluded |= name in _EXCLUDED_DIRS and stat.S_ISDIR(st.st_mode)
                controlled = rel in tracked or any(p.startswith(rel + "/") for p in tracked)
                if excluded and not controlled:
                    continue
            alternate = name.swapcase()
            if alternate != name:
                try:
                    other = os.stat(alternate, dir_fd=fd, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    if (st.st_dev, st.st_ino) == (other.st_dev, other.st_ino):
                        raise ValueError("case-insensitive filesystem is not supported")
            if rel.casefold() in folded:
                raise ValueError(f"case collision: {rel}")
            folded.add(rel.casefold())
            if stat.S_ISDIR(st.st_mode):
                inventory[rel] = _signature(st)
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    if _signature(os.fstat(child)) != inventory[rel]:
                        raise ValueError("directory changed during inventory")
                    walk(child, rel + "/")
                    if _signature(os.fstat(child)) != inventory[rel]:
                        raise ValueError("directory changed during inventory")
                finally:
                    os.close(child)
            elif stat.S_ISREG(st.st_mode) and st.st_nlink == 1:
                inventory[rel] = _signature(st)
            else:
                raise ValueError(f"link or hardlink/special file not supported: {rel}")

    try:
        fd = _open_directory(root)
        try:
            walk(fd, "")
        finally:
            os.close(fd)
    except OSError as e:
        raise ValueError("inventory changed or unsafe") from e
    return inventory


def _read_regular(root: Path, rel: str, expected: tuple) -> bytes:
    """Open each component without following links; check identity around reading."""
    _validate_relative_path(rel)
    if (
        not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_DIRECTORY")
        or os.open not in os.supports_dir_fd
    ):
        raise ValueError("OS lacks required no-follow directory opening capability")
    descriptors = []
    try:
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        fd = _open_directory(root)
        descriptors.append(fd)
        parts = rel.split("/")
        for part in parts[:-1]:
            fd = os.open(part, directory_flags, dir_fd=fd)
            descriptors.append(fd)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        descriptors.append(fd)
        if _signature(os.fstat(fd)) != expected or not stat.S_ISREG(expected[2]):
            raise ValueError(f"file changed before read: {rel}")
        chunks = []
        while chunk := os.read(fd, 1 << 20):
            chunks.append(chunk)
        if _signature(os.fstat(fd)) != expected:
            raise ValueError(f"file changed during read: {rel}")
        return b"".join(chunks)
    except OSError as e:
        raise ValueError(f"file changed or unsafe: {rel}") from e
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def _snapshot_digest(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _validate_expected(expected: dict) -> None:
    keys = {"schema_version", "baseline_commit", "files", "deleted", "snapshot_sha256"}
    if not isinstance(expected, dict) or set(expected) != keys:
        raise ValueError("snapshot has unexpected fields")
    if type(expected["schema_version"]) is not int or expected["schema_version"] != 1:
        raise ValueError("snapshot schema_version must be integer 1")
    if not isinstance(expected["baseline_commit"], str) or not _SHA_RE.fullmatch(
        expected["baseline_commit"]
    ):
        raise ValueError("invalid baseline_commit")
    if not isinstance(expected["files"], list) or not isinstance(expected["deleted"], list):
        raise ValueError("files/deleted must be lists")
    paths = []
    for entry in expected["files"]:
        if not isinstance(entry, dict) or set(entry) != {"path", "mode", "sha256"}:
            raise ValueError("invalid file entry")
        _validate_relative_path(entry["path"])
        if (
            not isinstance(entry["mode"], str)
            or entry["mode"] not in _ALLOWED_MODES
            or not isinstance(entry["sha256"], str)
            or not _SHA256_RE.fullmatch(entry["sha256"])
        ):
            raise ValueError("invalid mode or file digest")
        paths.append(entry["path"])
    for rel in expected["deleted"]:
        _validate_relative_path(rel)
    prefixes = {}
    for path in paths:
        parts = path.split("/")
        for i in range(1, len(parts) + 1):
            prefix = "/".join(parts[:i])
            previous = prefixes.setdefault(prefix.casefold(), prefix)
            if previous != prefix or (i < len(parts) and prefix in paths):
                raise ValueError("snapshot has colliding or file-as-directory paths")
    deleted = expected["deleted"]
    if paths != sorted(paths) or deleted != sorted(deleted):
        raise ValueError("snapshot paths must be sorted")
    all_paths = paths + deleted
    if len({p.casefold() for p in all_paths}) != len(all_paths):
        raise ValueError("duplicate, overlap or case collision")
    digest = expected["snapshot_sha256"]
    payload = {k: v for k, v in expected.items() if k != "snapshot_sha256"}
    if (
        not isinstance(digest, str)
        or not _SHA256_RE.fullmatch(digest)
        or _snapshot_digest(payload) != digest
    ):
        raise ValueError("snapshot self-digest mismatch")


def capture_snapshot(repo: Path, *, baseline_commit: str) -> dict:
    root = _root(repo)
    if not isinstance(baseline_commit, str) or not _SHA_RE.fullmatch(baseline_commit):
        raise ValueError("baseline_commit must be a full lowercase hex SHA")
    try:
        resolved = _git(
            root, "rev-parse", "--verify", "--end-of-options", f"{baseline_commit}^{{commit}}"
        ).strip()
    except subprocess.CalledProcessError as e:
        raise ValueError("baseline_commit does not resolve") from e
    if resolved != baseline_commit:
        raise ValueError("baseline_commit must identify a commit")
    baseline = _tree_paths(root, baseline_commit)
    tracked = _tracked_paths(root)
    controlled = sorted(set(tracked) | set(baseline))
    inventory = _inventory_paths(root, controlled)
    files = []
    for rel, signature in sorted(inventory.items()):
        if not stat.S_ISREG(signature[2]):
            continue
        data = _read_regular(root, rel, signature)
        if data.startswith(b"version https://git-lfs.github.com/spec/v1"):
            raise ValueError("git-lfs pointers not supported")
        files.append(
            {
                "path": rel,
                "mode": "100755" if signature[2] & 0o111 else "100644",
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    if tracked != _tracked_paths(root) or inventory != _inventory_paths(root, controlled):
        raise ValueError("inventory changed during capture")
    existing = {f["path"] for f in files}
    payload = {
        "schema_version": 1,
        "baseline_commit": baseline_commit,
        "files": files,
        "deleted": sorted(set(baseline) - existing),
    }
    payload["snapshot_sha256"] = _snapshot_digest(payload)
    _validate_expected(payload)
    return payload


def assert_snapshot(repo: Path, expected: dict) -> None:
    _validate_expected(expected)
    if capture_snapshot(repo, baseline_commit=expected["baseline_commit"]) != expected:
        raise ValueError("snapshot does not match current workspace")
