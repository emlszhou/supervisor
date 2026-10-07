"""Evidence package integrity verification (offline, read-only, standard library).

``verify_package`` checks a persisted evidence package tree without executing
anything, without writing, and without following symlinks inside the package.
Hashes identify contents; they do not prove how a record was produced.
"""

from __future__ import annotations

import hashlib
import json
import posixpath
from copy import deepcopy
from pathlib import Path

__all__ = ["verify_package"]

_HEX = set("0123456789abcdef")
_CHUNK = 1 << 16


def _fixed(message: str) -> ValueError:
    return ValueError(message)


def _safe_rel(text: str) -> str:
    if not isinstance(text, str) or not text:
        raise _fixed("invalid manifest: empty path")
    if any(ord(ch) < 0x20 or ch == "\x7f" for ch in text):
        raise _fixed("invalid manifest: control character in path")
    normalized = posixpath.normpath(text)
    if normalized.startswith("/"):
        raise _fixed("invalid manifest: absolute path")
    if ".." in normalized.split("/"):
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


def _load_manifest(root: Path) -> dict:
    manifest_path = root / "manifest.json"
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
        if rel == "manifest.json":
            raise _fixed("invalid package: manifest must not include itself")
        if rel == "CHECKSUMS.sha256":
            raise _fixed("invalid package: manifest must not include CHECKSUMS.sha256")
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


def _check_checksums(root: Path, manifest: dict) -> None:
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


def _expected_bytes(entry: dict) -> int:
    return entry["bytes"]


def _check_payload_files(root: Path, manifest: dict) -> None:
    for entry in manifest["files"]:
        rel = _safe_rel(entry["path"])
        path = root / rel
        if path.is_symlink():
            raise _fixed("invalid package: symlink entry")
        if not path.is_file():
            raise _fixed("invalid package: missing file")
        if path.stat().st_size != _expected_bytes(entry):
            raise _fixed("invalid package: size mismatch")
        if _sha256(path) != entry["sha256"]:
            raise _fixed("invalid package: checksum mismatch")


def _check_inventory(root: Path, manifest: dict) -> None:
    listed = {_safe_rel(entry["path"]) for entry in manifest["files"]}
    for path in root.rglob("*"):
        rel = _safe_rel(str(path.relative_to(root)))
        if rel in ("manifest.json", "CHECKSUMS.sha256"):
            continue
        if rel not in listed and path.is_file():
            raise _fixed("invalid package: unlisted file")


def _check_references(root: Path, manifest: dict) -> None:
    payload: dict[str, dict] = {}
    for entry in manifest["files"]:
        rel = _safe_rel(entry["path"])
        if rel == "summary.json":
            continue
        path = root / rel
        if path.suffix == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, ValueError):
                raise _fixed("invalid package: unreadable JSON payload") from None
            if isinstance(data, dict):
                payload[rel] = data

    summary_path = root / "summary.json"
    if (root / "summary.json").is_file():
        if (root / "summary.json").is_symlink() or not summary_path.is_file():
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
            for ref in ("record_ref", "capture_file"):
                value = item.get(ref)
                if value is None:
                    continue
                rel = _safe_rel(value)
                target = root / rel
                if target.is_symlink() or not target.is_file():
                    raise _fixed("invalid package: dangling reference")
            record_ref = item.get("record_ref")
            if record_ref is not None:
                rec = payload.get(_safe_rel(record_ref))
                if rec is None:
                    raise _fixed("invalid package: record not a JSON object")
                capture = rec.get("capture_file")
                recorded_sha = rec.get("capture_sha256")
                if capture is not None:
                    crel = _safe_rel(capture)
                    if _sha256(root / crel) != recorded_sha:
                        raise _fixed("invalid package: capture hash mismatch")


def verify_package(path: Path) -> dict:
    """Verify an evidence package and return a deep copy of its manifest.

    The package root must be a real directory containing only the files
    listed in ``manifest.json`` plus ``manifest.json``/``CHECKSUMS.sha256``.
    Every check failure raises ValueError with a fixed message that echoes no
    package content.  This is a generic integrity check; it does not verify
    that a record was produced honestly, and it does not reject minimal
    packages that lack ``cleanup.json`` or ``process_tree.json``.
    """
    root = Path(path)
    if root.is_symlink() or not root.is_dir():
        raise _fixed("invalid package: root must be a real directory")
    manifest = _load_manifest(root)
    _check_checksums(root, manifest)
    _check_payload_files(root, manifest)
    _check_inventory(root, manifest)
    _check_references(root, manifest)
    return deepcopy(manifest)
