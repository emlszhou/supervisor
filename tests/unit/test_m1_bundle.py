"""M1 unit tests for workspace.bundle.

The frozen acceptance suite covers the major happy paths and tamper
detection. These unit tests focus on input validation, manifest shape,
output atomics, and the read-only 0o444 mode guarantee.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from supervisor.workspace.bundle import freeze_bundle, verify_bundle


def _resolve_contract_root() -> Path:
    """Find the frozen contract root, honouring ``M1_CONTRACT_ROOT`` if set.

    The default looks for a sibling ``supervisor-M1-contract/task-bundle``
    relative to the supervisor-M1 worktree. Test runners on a clean checkout
    may override the location with the ``M1_CONTRACT_ROOT`` env var so the
    bundle unit tests do not depend on a developer-specific absolute path.
    """
    override = os.environ.get("M1_CONTRACT_ROOT")
    if override:
        return Path(override)
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "supervisor-M1-contract" / "task-bundle"
        if candidate.is_dir():
            return candidate
    # Final fallback: relative to cwd.
    cwd_candidate = Path.cwd() / "supervisor-M1-contract" / "task-bundle"
    if cwd_candidate.is_dir():
        return cwd_candidate
    raise FileNotFoundError(
        "M1 contract root not found; set M1_CONTRACT_ROOT or clone the "
        "supervisor-M1-contract repo next to supervisor-M1"
    )


CONTRACT_ROOT = _resolve_contract_root()
TASK_PATH = CONTRACT_ROOT / "task.json"
REQUIREMENTS_PATH = CONTRACT_ROOT / "requirements.md"
ALLOWED_PATH = CONTRACT_ROOT / "allowed_files.json"
FORBIDDEN_PATH = CONTRACT_ROOT / "forbidden_files.json"
VERIFICATION_PATH = CONTRACT_ROOT / "verification.json"


def _make_draft_source(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "input"
    root.mkdir()
    task = json.loads(TASK_PATH.read_text())
    task["status"] = "draft"
    task["baseline_commit"] = None
    (root / "task.json").write_text(json.dumps(task))
    for name, src in (
        ("requirements.md", REQUIREMENTS_PATH),
        ("allowed_files.json", ALLOWED_PATH),
        ("forbidden_files.json", FORBIDDEN_PATH),
        ("verification.json", VERIFICATION_PATH),
    ):
        (root / name).write_bytes(src.read_bytes())
    return root, task["task_id"]


def test_freeze_then_verify_round_trip(tmp_path: Path) -> None:
    src, task_id = _make_draft_source(tmp_path)
    out = tmp_path / "frozen"
    checksum = freeze_bundle(src, out, task_id=task_id, baseline_commit="a" * 40)
    assert checksum == hash_of_manifest(out / "manifest.json")
    manifest = verify_bundle(out, checksum)
    assert manifest["task_id"] == task_id
    assert manifest["baseline_commit"] == "a" * 40
    # task.json must be frozen and bound to the baseline.
    frozen = json.loads((out / "task.json").read_text())
    assert frozen["status"] == "frozen"
    assert frozen["baseline_commit"] == "a" * 40


def test_outputs_are_read_only_0444(tmp_path: Path) -> None:
    src, task_id = _make_draft_source(tmp_path)
    out = tmp_path / "frozen"
    freeze_bundle(src, out, task_id=task_id, baseline_commit="a" * 40)
    for entry in out.iterdir():
        mode = entry.stat().st_mode
        # The writable bits must all be cleared.
        assert mode & 0o222 == 0, f"{entry.name} still has writable bits: {oct(mode)}"


def test_source_unchanged_after_freeze(tmp_path: Path) -> None:
    src, task_id = _make_draft_source(tmp_path)
    before = (src / "task.json").read_bytes()
    out = tmp_path / "frozen"
    freeze_bundle(src, out, task_id=task_id, baseline_commit="a" * 40)
    assert (src / "task.json").read_bytes() == before


def test_existing_output_rejected(tmp_path: Path) -> None:
    src, task_id = _make_draft_source(tmp_path)
    out = tmp_path / "frozen"
    out.mkdir()
    (out / "keep").write_text("retain")
    with pytest.raises(ValueError):
        freeze_bundle(src, out, task_id=task_id, baseline_commit="a" * 40)
    assert (out / "keep").read_text() == "retain"


def test_source_with_manifest_rejected(tmp_path: Path) -> None:
    src, task_id = _make_draft_source(tmp_path)
    (src / "manifest.json").write_text("{}")
    out = tmp_path / "frozen"
    with pytest.raises(ValueError):
        freeze_bundle(src, out, task_id=task_id, baseline_commit="a" * 40)


def test_wrong_identity_rejected(tmp_path: Path) -> None:
    src, _ = _make_draft_source(tmp_path)
    out = tmp_path / "frozen"
    with pytest.raises(ValueError, match="task_id"):
        freeze_bundle(src, out, task_id="wrong", baseline_commit="a" * 40)


def test_invalid_baseline_commit_shape_rejected(tmp_path: Path) -> None:
    src, task_id = _make_draft_source(tmp_path)
    out = tmp_path / "frozen"
    with pytest.raises(ValueError, match="baseline_commit"):
        freeze_bundle(src, out, task_id=task_id, baseline_commit="not-a-sha")
    assert not out.exists()


def test_missing_required_input_rejected(tmp_path: Path) -> None:
    src, task_id = _make_draft_source(tmp_path)
    (src / "requirements.md").unlink()
    out = tmp_path / "frozen"
    with pytest.raises(ValueError, match="requirements.md"):
        freeze_bundle(src, out, task_id=task_id, baseline_commit="a" * 40)


def test_broken_json_rejected(tmp_path: Path) -> None:
    src, task_id = _make_draft_source(tmp_path)
    (src / "task.json").write_text("{broken")
    out = tmp_path / "frozen"
    with pytest.raises(ValueError, match="task.json"):
        freeze_bundle(src, out, task_id=task_id, baseline_commit="a" * 40)


def test_verify_rejects_bad_digest(tmp_path: Path) -> None:
    src, task_id = _make_draft_source(tmp_path)
    out = tmp_path / "frozen"
    freeze_bundle(src, out, task_id=task_id, baseline_commit="a" * 40)
    with pytest.raises(ValueError):
        verify_bundle(out, "0" * 64)


def test_verify_rejects_malformed_manifest_encoding(tmp_path: Path) -> None:
    src, task_id = _make_draft_source(tmp_path)
    out = tmp_path / "frozen"
    freeze_bundle(src, out, task_id=task_id, baseline_commit="a" * 40)
    # Tamper with manifest encoding: rewrite manifest.json with sorted=False
    # and explicit non-canonical JSON. The test relies on the fact that
    # verify_bundle recomputes the canonical encoding.
    manifest_path = out / "manifest.json"
    parsed = json.loads(manifest_path.read_text())
    # Re-emit with default separators (extra spaces) and unsorted keys.
    non_canonical = json.dumps(parsed, ensure_ascii=False).encode("utf-8")
    # Manifest is read-only mode 0o444; reset perms briefly to rewrite.
    os.chmod(manifest_path, 0o644)
    manifest_path.write_bytes(non_canonical)
    os.chmod(manifest_path, 0o444)
    checksum = hash_of_manifest(manifest_path)
    with pytest.raises(ValueError):
        verify_bundle(out, checksum)


def test_verify_rejects_modified_file(tmp_path: Path) -> None:
    src, task_id = _make_draft_source(tmp_path)
    out = tmp_path / "frozen"
    freeze_bundle(src, out, task_id=task_id, baseline_commit="a" * 40)
    # Need original checksum for the verify call.
    original_checksum = hash_of_manifest(out / "manifest.json")
    # Tamper with a tracked file (mode is 0o444; reset, write, restore).
    target = out / "requirements.md"
    os.chmod(target, 0o644)
    target.write_text("changed")
    os.chmod(target, 0o444)
    with pytest.raises(ValueError, match="digest mismatch"):
        verify_bundle(out, original_checksum)


def test_freeze_writes_sorted_canonical_manifest(tmp_path: Path) -> None:
    src, task_id = _make_draft_source(tmp_path)
    out = tmp_path / "frozen"
    checksum = freeze_bundle(src, out, task_id=task_id, baseline_commit="a" * 40)
    raw = (out / "manifest.json").read_bytes()
    assert raw == json.dumps(
        {
            "schema_version": 1,
            "task_id": task_id,
            "baseline_commit": "a" * 40,
            "files": dict(
                sorted(
                    {
                        "task.json": hash_for((out / "task.json").read_bytes()),
                        "requirements.md": hash_for((out / "requirements.md").read_bytes()),
                        "allowed_files.json": hash_for((out / "allowed_files.json").read_bytes()),
                        "forbidden_files.json": hash_for(
                            (out / "forbidden_files.json").read_bytes()
                        ),
                        "verification.json": hash_for((out / "verification.json").read_bytes()),
                    }.items()
                )
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    # Manifest sha256 == checksum returned.
    import hashlib

    assert hashlib.sha256(raw).hexdigest() == checksum


def hash_for(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def hash_of_manifest(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()
