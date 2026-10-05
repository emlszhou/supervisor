"""M1 unit tests for policy.changes.

These cover pattern matching semantics and budget/identity validation
that complement the frozen acceptance suite.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from supervisor.policy.changes import check_changes
from supervisor.workspace.snapshot import capture_snapshot


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
    _git(root, "config", "user.name", "M1 unit changes")
    _git(root, "config", "user.email", "m1-unit@example.invalid")
    (root / "a.txt").write_text("baseline")
    _git(root, "add", "a.txt")
    _git(root, "commit", "-qm", "fixture")
    return root, _git(root, "rev-parse", "HEAD")


def _base_kwargs(**overrides):
    kw = dict(
        allowed=["*.txt", "src/**"],
        forbidden=["tests/protected/**"],
        max_changed_files=10,
        max_diff_lines=1000,
        diff_lines=0,
    )
    kw.update(overrides)
    return kw


def test_no_changes_returns_empty(repo: tuple[Path, str]) -> None:
    root, base = repo
    s = capture_snapshot(root, baseline_commit=base)
    result = check_changes(s, s, **_base_kwargs())
    assert result == {"changed_files": [], "changed_count": 0, "diff_lines": 0}


def test_edit_classified(repo: tuple[Path, str]) -> None:
    root, base = repo
    before = capture_snapshot(root, baseline_commit=base)
    (root / "a.txt").write_text("new")
    after = capture_snapshot(root, baseline_commit=base)
    result = check_changes(before, after, **_base_kwargs(diff_lines=1))
    assert result["changed_files"] == ["a.txt"]
    assert result["changed_count"] == 1
    assert result["diff_lines"] == 1


def test_globstar_matches_nested(repo: tuple[Path, str]) -> None:
    root, base = repo
    (root / "src").mkdir()
    (root / "src" / "x.py").write_text("x")
    before = capture_snapshot(root, baseline_commit=base)
    (root / "src" / "x.py").write_text("y")
    after = capture_snapshot(root, baseline_commit=base)
    result = check_changes(before, after, **_base_kwargs(diff_lines=2))
    assert "src/x.py" in result["changed_files"]


def test_question_mark_wildcard(repo: tuple[Path, str]) -> None:
    root, base = repo
    (root / "ab.tx").write_text("hi")
    before = capture_snapshot(root, baseline_commit=base)
    (root / "ab.tx").write_text("bye")
    after = capture_snapshot(root, baseline_commit=base)
    # "?.tx" matches exactly 1 char + ".tx". "ab.tx" has 2-char stem → no match.
    with pytest.raises(ValueError):
        check_changes(before, after, **_base_kwargs(allowed=["?.tx"], diff_lines=1))
    # "??" matches exactly two characters in a single segment. "ab.tx"
    # is two segments and contains a dot, so "??" cannot match it.
    with pytest.raises(ValueError):
        check_changes(before, after, **_base_kwargs(allowed=["??"], diff_lines=1))


def test_baseline_mismatch_rejected(repo: tuple[Path, str]) -> None:
    root, base = repo
    s = capture_snapshot(root, baseline_commit=base)
    s2 = capture_snapshot(root, baseline_commit=base)
    s2["baseline_commit"] = "f" * 40
    with pytest.raises(ValueError, match="self-digest"):
        check_changes(s, s2, **_base_kwargs())


def test_max_changed_files_zero_rejected() -> None:
    with pytest.raises(ValueError):
        check_changes(
            {"a": 1},  # bogus, will fail snapshot validation first
            {"a": 1},
            allowed=["*"],
            forbidden=[],
            max_changed_files=0,
            max_diff_lines=1,
            diff_lines=0,
        )


def test_max_diff_lines_zero_rejected() -> None:
    with pytest.raises(ValueError):
        check_changes(
            {"a": 1},
            {"a": 1},
            allowed=["*"],
            forbidden=[],
            max_changed_files=1,
            max_diff_lines=0,
            diff_lines=0,
        )


def test_negative_diff_lines_rejected() -> None:
    with pytest.raises(ValueError):
        check_changes(
            {"a": 1},
            {"a": 1},
            allowed=["*"],
            forbidden=[],
            max_changed_files=1,
            max_diff_lines=1,
            diff_lines=-1,
        )


def test_forbidden_pattern_wins_over_allowed(repo: tuple[Path, str]) -> None:
    root, base = repo
    before = capture_snapshot(root, baseline_commit=base)
    (root / "a.txt").write_text("changed")
    after = capture_snapshot(root, baseline_commit=base)
    # a.txt is both allowed and forbidden → forbidden wins → raise.
    with pytest.raises(ValueError, match="forbidden"):
        check_changes(
            before,
            after,
            allowed=["a.txt"],
            forbidden=["a.txt"],
            max_changed_files=10,
            max_diff_lines=100,
            diff_lines=1,
        )


def test_pattern_validation_rejects_absolute(repo: tuple[Path, str]) -> None:
    root, base = repo
    before = capture_snapshot(root, baseline_commit=base)
    after = capture_snapshot(root, baseline_commit=base)
    with pytest.raises(ValueError, match="pattern"):
        check_changes(
            before,
            after,
            allowed=["/abs"],
            forbidden=[],
            max_changed_files=1,
            max_diff_lines=1,
            diff_lines=0,
        )


def test_pattern_validation_rejects_backslash(repo: tuple[Path, str]) -> None:
    root, base = repo
    before = capture_snapshot(root, baseline_commit=base)
    after = capture_snapshot(root, baseline_commit=base)
    with pytest.raises(ValueError, match="pattern"):
        check_changes(
            before,
            after,
            allowed=["a\\b"],
            forbidden=[],
            max_changed_files=1,
            max_diff_lines=1,
            diff_lines=0,
        )


def test_pattern_validation_rejects_double_dot(repo: tuple[Path, str]) -> None:
    root, base = repo
    before = capture_snapshot(root, baseline_commit=base)
    after = capture_snapshot(root, baseline_commit=base)
    with pytest.raises(ValueError, match="pattern"):
        check_changes(
            before,
            after,
            allowed=["../*"],
            forbidden=[],
            max_changed_files=1,
            max_diff_lines=1,
            diff_lines=0,
        )


def test_budget_overflow_rejected(repo: tuple[Path, str]) -> None:
    root, base = repo
    before = capture_snapshot(root, baseline_commit=base)
    (root / "a.txt").write_text("new")
    after = capture_snapshot(root, baseline_commit=base)
    with pytest.raises(ValueError, match="line count"):
        check_changes(
            before,
            after,
            allowed=["*"],
            forbidden=[],
            max_changed_files=10,
            max_diff_lines=1,
            diff_lines=2,
        )
