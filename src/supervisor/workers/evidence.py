"""Evidence package integrity verification (offline, read-only, standard library).

``verify_package`` checks a persisted evidence package tree without executing
anything, without writing, and without following symlinks inside the package.
Hashes identify contents; they do not prove how a record was produced.
"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import stat as stat_module
from copy import deepcopy
from pathlib import Path

__all__ = ["verify_package"]

_HEX = set("0123456789abcdef")
_CHUNK = 1 << 16
# Files that may never be listed as payload in a manifest: the manifest cannot
# describe itself and the external checksum is not payload either.
_RESERVED = ("manifest.json", "CHECKSUMS.sha256")
# The pre-cleanup snapshot is meta at every stage: during the pre-cleanup stage
# it is deliberately excluded from itself (no self-reference), and in the final
# manifest it is ordinary listed payload.  It is therefore never an "unlisted"
# node, while ``_check_payload_files`` still verifies it whenever the manifest
# does list it.
_META = _RESERVED + ("pre-cleanup-manifest.json",)


def _fixed(message: str) -> ValueError:
    return ValueError(message)


def _safe_rel(text: str) -> str:
    """Validate and normalize a relative POSIX path from the manifest.

    Rejects non-strings, empty values, control characters, absolute paths,
    degenerate paths and any path containing a ``..`` component -- both
    before and after ``normpath``.  A raw ``..`` is never collapsed away
    for acceptance; the check is structural and fixed.
    """
    if not isinstance(text, str) or not text:
        raise _fixed("invalid manifest: empty path")
    if any(ord(ch) < 0x20 or ch == "\x7f" for ch in text):
        raise _fixed("invalid manifest: control character in path")
    if text.startswith("/"):
        raise _fixed("invalid manifest: absolute path")
    if ".." in text.split("/"):
        raise _fixed("invalid manifest: path traversal")
    normalized = posixpath.normpath(text)
    if normalized == ".." or normalized.startswith("../"):
        raise _fixed("invalid manifest: path traversal")
    if normalized == "/" or normalized.endswith("/.."):
        raise _fixed("invalid manifest: path traversal")
    if normalized in (".", ""):
        raise _fixed("invalid manifest: degenerate path")
    return normalized


def _is_real_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _lstat(path: Path) -> os.stat_result | None:
    try:
        return os.lstat(path)
    except OSError:
        return None


def _is_regular(st: os.stat_result) -> bool:
    return stat_module.S_ISREG(st.st_mode)


def _load_manifest(root: Path) -> dict:
    manifest_path = root / "manifest.json"
    if manifest_path.is_symlink() or not _is_real_file(manifest_path):
        raise _fixed("invalid package: manifest must be a regular file")
    try:
        raw = manifest_path.read_bytes()
        manifest = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        raise _fixed("invalid package: unreadable manifest.json") from None
    if not isinstance(manifest, dict):
        raise _fixed("invalid package: manifest not a mapping")
    if set(manifest) != {"schema_version", "files"}:
        raise _fixed("invalid package: manifest keys")
    if manifest["schema_version"] != 1:
        raise _fixed("invalid package: schema_version must be 1")
    files = manifest["files"]
    if not isinstance(files, list) or not files:
        raise _fixed("invalid package: files must be a non-empty list")
    seen: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "bytes"}:
            raise _fixed("invalid package: malformed file entry")
        rel = _safe_rel(entry["path"])
        if rel in _RESERVED:
            raise _fixed("invalid package: manifest must not include reserved file")
        if rel in seen:
            raise _fixed("invalid package: duplicate file entry")
        seen.add(rel)
        sha = entry["sha256"]
        if not isinstance(sha, str) or len(sha) != 64 or any(ch not in _HEX for ch in sha):
            raise _fixed("invalid package: malformed sha256")
        size = entry["bytes"]
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise _fixed("invalid package: malformed bytes")
    return manifest


def _check_checksums(root: Path) -> None:
    path = root / "CHECKSUMS.sha256"
    if not _is_real_file(path):
        raise _fixed("invalid package: missing CHECKSUMS.sha256")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        raise _fixed("invalid package: unreadable CHECKSUMS.sha256") from None
    # An empty placeholder marks an unfinalized package (pre-cleanup stage);
    # it is not a finished delivery.
    if not lines:
        raise _fixed("invalid package: CHECKSUMS.sha256 not finalized")
    if len(lines) != 1:
        raise _fixed("invalid package: CHECKSUMS.sha256 must contain exactly one line")
    line = lines[0]
    parts = line.split("  ")
    if len(parts) != 2 or parts[1] != "manifest.json":
        raise _fixed("invalid package: CHECKSUMS.sha256 malformed line")
    if _sha256(root / "manifest.json") != parts[0]:
        raise _fixed("invalid package: manifest checksum mismatch")


def _check_payload_files(root: Path, manifest: dict) -> None:
    for entry in manifest["files"]:
        rel = _safe_rel(entry["path"])
        path = root / rel
        st = _lstat(path)
        if st is None:
            raise _fixed("invalid package: missing file")
        if stat_module.S_ISLNK(st.st_mode):
            raise _fixed("invalid package: symlink entry")
        if not _is_regular(st):
            raise _fixed("invalid package: entry must be a regular file")
        if st.st_size != entry["bytes"]:
            raise _fixed("invalid package: size mismatch")
        if _sha256(path) != entry["sha256"]:
            raise _fixed("invalid package: checksum mismatch")


def _check_inventory(root: Path, manifest: dict) -> None:
    """Reject every node the manifest does not account for.

    The walk never follows symlink directories.  Regular files must be
    listed; symlinks (including dangling links and links to directories)
    must be listed and are separately rejected by ``_check_payload_files``;
    directory nodes are containers and may remain unlisted only when every
    node below them is listed; sockets, fifos and devices must be listed
    and are rejected as non-regular entries.
    """
    listed = {_safe_rel(entry["path"]) for entry in manifest["files"]}

    def walk(directory: Path) -> None:
        for path in directory.iterdir():
            rel = _safe_rel(str(path.relative_to(root)))
            if rel in _META:
                continue
            st = _lstat(path)
            if st is None:
                continue  # vanished between readdir and lstat: not proof either way
            mode = st.st_mode
            if stat_module.S_ISDIR(mode) and not path.is_symlink():
                walk(path)
                continue
            if stat_module.S_ISREG(mode):
                if rel not in listed:
                    raise _fixed("invalid package: unlisted file")
            elif path.is_symlink():
                if rel not in listed:
                    raise _fixed("invalid package: unlisted symlink")
            else:
                if rel not in listed:
                    raise _fixed("invalid package: unlisted file")

    walk(root)


def _resolve_reference(root: Path, ref: str, listed: set[str]) -> Path:
    """Resolve a recorded reference to a real listed regular file.

    References must be relative, traversal-free, non-symlink targets that
    are listed in the manifest.  Any violation raises a fixed ValueError.
    """
    rel = _safe_rel(ref)
    target = root / rel
    st = _lstat(target)
    if st is None:
        raise _fixed("invalid package: dangling reference")
    if stat_module.S_ISLNK(st.st_mode):
        raise _fixed("invalid package: symlink reference")
    if not _is_regular(st):
        raise _fixed("invalid package: dangling reference")
    if rel not in listed:
        raise _fixed("invalid package: reference to unlisted file")
    return target


def _check_references(root: Path, manifest: dict) -> None:
    """Validate references in summary.json and in every payload JSON record.

    A reference is any mapping value whose key ends in ``_ref`` or
    ``_file`` and whose value is a string.  The target must be a real
    listed regular file.  Records that carry ``capture_file`` plus
    ``capture_sha256`` are additionally cross-checked against the actual
    capture bytes.  All failures raise a fixed ValueError.
    """
    listed = {_safe_rel(entry["path"]) for entry in manifest["files"]}

    def check_record(record: dict) -> None:
        for key, value in record.items():
            if not isinstance(value, str):
                continue
            if key.endswith("_ref") or key.endswith("_file"):
                _resolve_reference(root, value, listed)
        if record.get("capture_file") is not None:
            recorded_sha = record.get("capture_sha256")
            if recorded_sha is not None:
                if not isinstance(recorded_sha, str) or len(recorded_sha) != 64:
                    raise _fixed("invalid package: malformed capture sha256")
                capture_path = _resolve_reference(root, record["capture_file"], listed)
                if _sha256(capture_path) != recorded_sha:
                    raise _fixed("invalid package: capture hash mismatch")

    # summary.json (optional)
    summary_path = root / "summary.json"
    st = _lstat(summary_path)
    if st is not None:
        if stat_module.S_ISLNK(st.st_mode) or not _is_regular(st):
            raise _fixed("invalid package: summary must be a regular file")
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            raise _fixed("invalid package: unreadable summary.json") from None
        if not isinstance(summary, list):
            raise _fixed("invalid package: summary.json must be a list")
        for item in summary:
            if not isinstance(item, dict):
                raise _fixed("invalid package: malformed summary item")
            check_record(item)

    # every other JSON payload record
    for entry in manifest["files"]:
        rel = _safe_rel(entry["path"])
        if not entry["path"].endswith(".json"):
            continue
        if rel == "summary.json":
            continue
        path = root / rel
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            raise _fixed("invalid package: unreadable JSON payload") from None
        if isinstance(data, dict):
            check_record(data)
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    check_record(item)


def verify_package(path: Path) -> dict:
    """Verify an evidence package and return a deep copy of its manifest.

    The package root must be a real directory containing only the files
    listed in ``manifest.json`` plus ``manifest.json``/``CHECKSUMS.sha256``.
    Symlinks, dangling references, unlisted nodes, size/hash mismatches and
    tampered cross-references are all rejected with a fixed ValueError that
    echoes no package content.  This is a generic integrity check; it does
    not verify that a record was produced honestly, and it does not reject
    minimal packages that lack ``cleanup.json`` or ``process_tree.json``.
    """
    root = Path(path)
    st = _lstat(root)
    if st is None or stat_module.S_ISLNK(st.st_mode) or not stat_module.S_ISDIR(st.st_mode):
        raise _fixed("invalid package: root must be a real directory")
    manifest = _load_manifest(root)
    _check_checksums(root)
    _check_payload_files(root, manifest)
    _check_inventory(root, manifest)
    _check_references(root, manifest)
    return deepcopy(manifest)
