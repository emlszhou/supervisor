"""Coordinator packaging checks, independent of the unimplemented M0 runner."""

import hashlib
import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VERIFY = runpy.run_path(str(ROOT / "scripts/verify_handoff.py"))["verify_task_bundle"]


def bundle(tmp_path):
    task = {"task_id": "M0", "status": "frozen", "baseline_commit": "1" * 40}
    content = json.dumps(task).encode()
    (tmp_path / "task.json").write_bytes(content)
    manifest = {
        "schema_version": 1,
        "task_id": "M0",
        "baseline_commit": "1" * 40,
        "files": {"task.json": hashlib.sha256(content).hexdigest()},
    }
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    (tmp_path / "manifest.json").write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def test_intact_frozen_bundle_is_verified(tmp_path):
    checksum = bundle(tmp_path)
    assert VERIFY(tmp_path, checksum)["task_id"] == "M0"


def test_modified_task_is_rejected(tmp_path):
    checksum = bundle(tmp_path)
    (tmp_path / "task.json").write_text("{}")
    with pytest.raises(ValueError, match="content changed"):
        VERIFY(tmp_path, checksum)


def test_missing_input_is_rejected(tmp_path):
    checksum = bundle(tmp_path)
    (tmp_path / "task.json").unlink()
    with pytest.raises(ValueError, match="inventory"):
        VERIFY(tmp_path, checksum)


def test_added_unlisted_file_is_rejected(tmp_path):
    checksum = bundle(tmp_path)
    (tmp_path / "extra.py").write_text("pass")
    with pytest.raises(ValueError, match="inventory"):
        VERIFY(tmp_path, checksum)


def test_untrusted_manifest_digest_is_rejected(tmp_path):
    bundle(tmp_path)
    with pytest.raises(ValueError, match="digest mismatch"):
        VERIFY(tmp_path, "0" * 64)


def test_symlink_is_rejected(tmp_path):
    checksum = bundle(tmp_path)
    (tmp_path / "linked-input").symlink_to(tmp_path / "task.json")
    with pytest.raises(ValueError, match="symlinks"):
        VERIFY(tmp_path, checksum)


def test_case_collision_is_rejected(tmp_path):
    checksum = bundle(tmp_path)
    (tmp_path / "TASK.json").write_text("{}")
    if len(list(tmp_path.iterdir())) == 2:
        # Case-insensitive platforms overwrite the original; verification must still fail.
        with pytest.raises(ValueError):
            VERIFY(tmp_path, checksum)
    else:
        with pytest.raises(ValueError, match="collision"):
            VERIFY(tmp_path, checksum)
