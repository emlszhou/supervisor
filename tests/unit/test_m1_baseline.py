"""M1 unit tests for workspace.baseline.

These tests focus on the new behaviors introduced for M1: rejection of
.gitignore'd untracked files and explicit rejection of symlinked/hardlinked
working-tree entries. Acceptance-side coverage (clean baseline, unborn
HEAD) lives in the frozen test_m1_acceptance.py suite.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from supervisor.workspace.baseline import inspect_baseline


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
    _git(root, "config", "user.name", "M1 unit baseline")
    _git(root, "config", "user.email", "m1-unit@example.invalid")
    (root / "a.txt").write_text("baseline")
    _git(root, "add", "a.txt")
    _git(root, "commit", "-qm", "fixture")
    return root, _git(root, "rev-parse", "HEAD")


def test_clean_repo_returns_head_sha(repo: tuple[Path, str]) -> None:
    root, base = repo
    assert inspect_baseline(root) == base


def test_gitignored_untracked_file_rejected(repo: tuple[Path, str]) -> None:
    root, _base = repo
    (root / ".gitignore").write_text("secret.txt\n")
    _git(root, "add", ".gitignore")
    _git(root, "commit", "-qm", "ignore")
    (root / "secret.txt").write_text("top secret")
    with pytest.raises(ValueError, match="untracked"):
        inspect_baseline(root)


def test_excluded_cache_dir_accepted_when_only_untracked(
    repo: tuple[Path, str],
) -> None:
    root, base = repo
    cache = root / ".pytest_cache"
    cache.mkdir()
    (cache / "blob").write_text("noise")
    (root / ".ruff_cache").mkdir()
    (root / ".ruff_cache" / "noise").write_text("noise")
    assert inspect_baseline(root) == base


def test_symlink_inside_repo_rejected(repo: tuple[Path, str]) -> None:
    root, _base = repo
    os.symlink(root / "a.txt", root / "link")
    with pytest.raises(ValueError, match="link or hardlink"):
        inspect_baseline(root)


def test_hardlink_inside_repo_rejected(repo: tuple[Path, str]) -> None:
    root, _base = repo
    os.link(root / "a.txt", root / "hard")
    with pytest.raises(ValueError, match="link or hardlink"):
        inspect_baseline(root)


def test_non_git_directory_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        inspect_baseline(tmp_path)


def test_unborn_head_rejected(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    _git(root, "init", "-q")
    with pytest.raises(ValueError):
        inspect_baseline(root)


def test_symlinked_repo_root_rejected(repo: tuple[Path, str]) -> None:
    root, _base = repo
    link = root.parent / "linked_repo"
    if link.exists() or link.is_symlink():
        link.unlink()
    os.symlink(root, link)
    try:
        with pytest.raises(ValueError, match="symlink"):
            inspect_baseline(link)
    finally:
        link.unlink()
