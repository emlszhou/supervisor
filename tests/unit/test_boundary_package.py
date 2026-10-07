"""Unit tests for ``supervisor.workers.evidence.verify_package`` (offline)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from supervisor.workers.evidence import verify_package


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_package(root: Path) -> dict:
    (root / "capture").mkdir()
    (root / "evidence").mkdir()
    (root / "capture/x.log").write_bytes(b"synthetic errno=EPERM\n")
    record = {
        "test_id": "x",
        "capture_file": "capture/x.log",
        "capture_sha256": sha256_bytes((root / "capture/x.log").read_bytes()),
    }
    (root / "evidence/x.json").write_text(json.dumps(record))
    (root / "summary.json").write_text(
        json.dumps([{"test_id": "x", "record_ref": "evidence/x.json"}])
    )
    manifest = {
        "schema_version": 1,
        "files": [
            {
                "path": str(p.relative_to(root)),
                "sha256": sha256_bytes(p.read_bytes()),
                "bytes": p.stat().st_size,
            }
            for p in sorted(root.rglob("*"))
            if p.is_file()
        ],
    }
    raw = json.dumps(manifest).encode()
    (root / "manifest.json").write_bytes(raw)
    (root / "CHECKSUMS.sha256").write_text(sha256_bytes(raw) + "  manifest.json\n")
    return manifest


def minimal_package(root: Path) -> dict:
    """A minimal package with no summary: must still verify."""
    (root / "capture").mkdir()
    (root / "capture/only.log").write_bytes(b"synthetic\n")
    manifest = {
        "schema_version": 1,
        "files": [
            {
                "path": "capture/only.log",
                "sha256": sha256_bytes((root / "capture/only.log").read_bytes()),
                "bytes": (root / "capture/only.log").stat().st_size,
            }
        ],
    }
    raw = json.dumps(manifest).encode()
    (root / "manifest.json").write_bytes(raw)
    (root / "CHECKSUMS.sha256").write_text(sha256_bytes(raw) + "  manifest.json\n")
    return manifest


def test_full_package_verifies_and_returns_copy(tmp_path):
    manifest = build_package(tmp_path)
    result = verify_package(tmp_path)
    assert result == manifest
    result["files"][0]["sha256"] = "0" * 64
    assert manifest["files"][0]["sha256"] != "0" * 64


def test_minimal_package_without_summary_verifies(tmp_path):
    manifest = minimal_package(tmp_path)
    assert verify_package(tmp_path) == manifest


def test_manifest_must_not_include_itself(tmp_path):
    manifest = minimal_package(tmp_path)
    manifest["files"].append(
        {
            "path": "manifest.json",
            "sha256": sha256_bytes((tmp_path / "manifest.json").read_bytes()),
            "bytes": 1,
        }
    )
    raw = json.dumps(manifest).encode()
    (tmp_path / "manifest.json").write_bytes(raw)
    (tmp_path / "CHECKSUMS.sha256").write_text(sha256_bytes(raw) + "  manifest.json\n")
    with pytest.raises(ValueError):
        verify_package(tmp_path)


def test_duplicate_entry_rejected(tmp_path):
    minimal_package(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    manifest["files"].append(dict(manifest["files"][0]))
    raw = json.dumps(manifest).encode()
    (tmp_path / "manifest.json").write_bytes(raw)
    (tmp_path / "CHECKSUMS.sha256").write_text(sha256_bytes(raw) + "  manifest.json\n")
    with pytest.raises(ValueError):
        verify_package(tmp_path)


def test_wrong_bytes_field_rejected(tmp_path):
    manifest = minimal_package(tmp_path)
    manifest["files"][0]["bytes"] += 1
    raw = json.dumps(manifest).encode()
    (tmp_path / "manifest.json").write_bytes(raw)
    (tmp_path / "CHECKSUMS.sha256").write_text(sha256_bytes(raw) + "  manifest.json\n")
    with pytest.raises(ValueError):
        verify_package(tmp_path)


def test_size_mismatch_on_disk_rejected(tmp_path):
    minimal_package(tmp_path)
    (tmp_path / "capture/only.log").write_bytes(b"synthetic\n\n")
    with pytest.raises(ValueError):
        verify_package(tmp_path)


def test_unlisted_directory_entry_rejected(tmp_path):
    minimal_package(tmp_path)
    (tmp_path / "rogue").mkdir()
    (tmp_path / "rogue/stray.log").write_bytes(b"x")
    with pytest.raises(ValueError):
        verify_package(tmp_path)


def test_symlink_entry_rejected(tmp_path):
    minimal_package(tmp_path)
    victim = tmp_path / "capture/only.log"
    victim.unlink()
    (tmp_path / "capture/only.log").symlink_to(tmp_path / "manifest.json")
    with pytest.raises(ValueError):
        verify_package(tmp_path)


def test_summary_record_capture_hash_mismatch_rejected(tmp_path):
    build_package(tmp_path)
    record_path = tmp_path / "evidence/x.json"
    record = json.loads(record_path.read_text())
    record["capture_sha256"] = "0" * 64
    record_path.write_text(json.dumps(record))
    # Rewrite manifest+CHECKSUMS so structural checksums stay consistent; the
    # cross-reference check must still fail on the record-level mismatch.
    manifest = {
        "schema_version": 1,
        "files": [
            {
                "path": str(p.relative_to(tmp_path)),
                "sha256": sha256_bytes(p.read_bytes()),
                "bytes": p.stat().st_size,
            }
            for p in sorted(tmp_path.rglob("*"))
            if p.is_file()
        ],
    }
    raw = json.dumps(manifest).encode()
    (tmp_path / "manifest.json").write_bytes(raw)
    (tmp_path / "CHECKSUMS.sha256").write_text(sha256_bytes(raw) + "  manifest.json\n")
    with pytest.raises(ValueError):
        verify_package(tmp_path)


def test_dangling_record_ref_rejected(tmp_path):
    build_package(tmp_path)
    (tmp_path / "summary.json").write_text(
        json.dumps([{"test_id": "x", "record_ref": "evidence/nope.json"}])
    )
    manifest = {
        "schema_version": 1,
        "files": [
            {
                "path": str(p.relative_to(tmp_path)),
                "sha256": sha256_bytes(p.read_bytes()),
                "bytes": p.stat().st_size,
            }
            for p in sorted(tmp_path.rglob("*"))
            if p.is_file()
        ],
    }
    raw = json.dumps(manifest).encode()
    (tmp_path / "manifest.json").write_bytes(raw)
    (tmp_path / "CHECKSUMS.sha256").write_text(sha256_bytes(raw) + "  manifest.json\n")
    with pytest.raises(ValueError):
        verify_package(tmp_path)


def test_root_symlink_rejected(tmp_path):
    package_dir = tmp_path / "pkg"
    package_dir.mkdir()
    minimal_package(package_dir)
    link = tmp_path / "link"
    link.symlink_to(package_dir, target_is_directory=True)
    with pytest.raises(ValueError):
        verify_package(link)


def test_verification_does_not_write(tmp_path):
    minimal_package(tmp_path)
    before = sorted(p.name for p in tmp_path.rglob("*"))
    verify_package(tmp_path)
    assert sorted(p.name for p in tmp_path.rglob("*")) == before


def test_errors_echo_no_input(tmp_path):
    minimal_package(tmp_path)
    (tmp_path / "capture/only.log").write_bytes(b"TOTALLY-UNEXPECTED-CONTENT")
    try:
        verify_package(tmp_path)
    except ValueError as exc:
        assert "TOTALLY-UNEXPECTED-CONTENT" not in str(exc)
    else:
        pytest.fail("expected ValueError")
