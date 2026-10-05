"""M1 unit tests for workspace.snapshot.

These cover scenarios the frozen acceptance suite already validates plus
focused negative paths that benefit from per-feature isolation: invalid
inputs to capture/assert, mode classification, and digest canonicalization.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from supervisor.workspace.snapshot import (
    _snapshot_digest,
    assert_snapshot,
    capture_snapshot,
)


def _git(root: Path, *args: str) -> str:
    return (
        subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE)
        .decode()
        .strip()
    )


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "M1 unit snapshot")
    _git(root, "config", "user.email", "m1-unit@example.invalid")
    (root / "a.txt").write_text("baseline")
    _git(root, "add", "a.txt")
    _git(root, "commit", "-qm", "fixture")
    return root, _git(root, "rev-parse", "HEAD")


def _canonical(snapshot: dict) -> str:
    fields = {k: v for k, v in snapshot.items() if k != "snapshot_sha256"}
    return hashlib.sha256(
        json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def test_capture_clean_repo(repo: tuple[Path, str]) -> None:
    root, base = repo
    s = capture_snapshot(root, baseline_commit=base)
    assert s["snapshot_sha256"] == _canonical(s)
    assert s["baseline_commit"] == base
    assert s["files"] == [
        {
            "path": "a.txt",
            "mode": "100644",
            "sha256": hashlib.sha256(b"baseline").hexdigest(),
        }
    ]
    assert s["deleted"] == []


def test_capture_deterministic(repo: tuple[Path, str]) -> None:
    root, base = repo
    a = capture_snapshot(root, baseline_commit=base)
    b = capture_snapshot(root, baseline_commit=base)
    assert a == b


def test_capture_untracked_included(repo: tuple[Path, str]) -> None:
    root, base = repo
    (root / "u.txt").write_text("u")
    s = capture_snapshot(root, baseline_commit=base)
    paths = [f["path"] for f in s["files"]]
    assert "u.txt" in paths


def test_capture_executable_mode_classified(repo: tuple[Path, str]) -> None:
    root, base = repo
    (root / "a.txt").chmod(0o755)
    s = capture_snapshot(root, baseline_commit=base)
    assert s["files"][0]["mode"] == "100755"


def test_capture_deleted_tracked(repo: tuple[Path, str]) -> None:
    root, base = repo
    (root / "a.txt").unlink()
    s = capture_snapshot(root, baseline_commit=base)
    assert s["deleted"] == ["a.txt"]
    assert s["files"] == []


def test_capture_rejects_invalid_baseline_commit(repo: tuple[Path, str]) -> None:
    root, _base = repo
    with pytest.raises(ValueError, match="baseline_commit"):
        capture_snapshot(root, baseline_commit="not-a-sha")


def test_capture_rejects_non_git_dir(tmp_path: Path) -> None:
    root = tmp_path / "x"
    root.mkdir()
    with pytest.raises(ValueError):
        capture_snapshot(root, baseline_commit="a" * 40)


def test_capture_rejects_unborn_baseline(tmp_path: Path) -> None:
    root = tmp_path / "x"
    root.mkdir()
    _git(root, "init", "-q")
    # Rev-parse of HEAD fails on unborn HEAD; pass a syntactically valid
    # SHA so the rejection comes from the resolve step.
    with pytest.raises(ValueError):
        capture_snapshot(root, baseline_commit="a" * 40)


def test_assert_snapshot_matches(repo: tuple[Path, str]) -> None:
    root, base = repo
    s = capture_snapshot(root, baseline_commit=base)
    assert_snapshot(root, s)  # should not raise


def test_assert_snapshot_detects_edit(repo: tuple[Path, str]) -> None:
    root, base = repo
    s = capture_snapshot(root, baseline_commit=base)
    (root / "a.txt").write_text("new")
    with pytest.raises(ValueError):
        assert_snapshot(root, s)


def test_assert_snapshot_rejects_forged_digest(repo: tuple[Path, str]) -> None:
    root, base = repo
    s = capture_snapshot(root, baseline_commit=base)
    s["snapshot_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="self-digest"):
        assert_snapshot(root, s)


def test_assert_snapshot_rejects_unknown_field(repo: tuple[Path, str]) -> None:
    root, base = repo
    s = capture_snapshot(root, baseline_commit=base)
    s["rogue"] = "x"
    # extra field breaks self-digest → mismatch
    with pytest.raises(ValueError):
        assert_snapshot(root, s)


def test_assert_snapshot_rejects_symlinked_root(tmp_path: Path) -> None:
    root = tmp_path / "real"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "x")
    _git(root, "config", "user.email", "x@x")
    (root / "a.txt").write_text("x")
    _git(root, "add", "a.txt")
    _git(root, "commit", "-qm", "init")
    base = _git(root, "rev-parse", "HEAD")
    s = capture_snapshot(root, baseline_commit=base)
    link = tmp_path / "link"
    if link.exists() or link.is_symlink():
        link.unlink()
    os.symlink(root, link)
    try:
        with pytest.raises(ValueError):
            assert_snapshot(link, s)
    finally:
        link.unlink()


def test_digest_helper_matches_canonical() -> None:
    payload = {"a": 1, "b": [1, 2]}
    expected = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    assert _snapshot_digest(payload) == expected
