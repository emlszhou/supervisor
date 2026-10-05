"""Read-only clean Git baseline inspection.

`inspect_baseline` verifies that a path is a real, clean Git working tree and
returns its full HEAD SHA. It never mutates the working tree, Git config, or
process cwd, and never fetches, checks out, resets, pushes, or runs hooks or
Agent commands. All invalid inputs raise ValueError; external Git failures
surface as OSError.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

# Fixed build/venv/cache artifacts. Exclusion applies only to *untracked*
# entries; tracked files are always controlled. The project .gitignore cannot
# widen this set.
_EXCLUDED_DIRS = {".venv", ".supervisor", ".pytest_cache", ".ruff_cache", "__pycache__"}


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE).decode()


def _is_git_root(root: Path) -> bool:
    try:
        out = _git(root, "rev-parse", "--is-inside-work-tree")
    except (subprocess.CalledProcessError, OSError):
        return False
    return out.strip() == "true"


def _git_toplevel(root: Path) -> str | None:
    try:
        out = _git(root, "rev-parse", "--show-toplevel")
    except (subprocess.CalledProcessError, OSError):
        return None
    s = out.strip()
    return s or None


def _in_progress(root: Path) -> bool:
    for marker in (
        "MERGE_HEAD",
        "REBASE_HEAD",
        "CHERRY_PICK_HEAD",
        "BISECT_HEAD",
        "rebase-merge",
        "rebase-apply",
    ):
        if (root / ".git" / marker).exists():
            return True
    return False


def _head_sha(root: Path) -> str | None:
    try:
        out = _git(root, "rev-parse", "--verify", "--end-of-options", "HEAD^{commit}")
    except (subprocess.CalledProcessError, OSError):
        return None
    sha = out.strip()
    return sha if len(sha) in (40, 64) else None


def _tracked_paths(root: Path) -> list[str]:
    out = _git(root, "ls-files", "-z")
    return [p for p in out.split("\0") if p]


def _ignored_untracked_paths(root: Path) -> list[str]:
    out = _git(root, "ls-files", "--others", "--ignored", "--exclude-standard", "-z")
    return [p for p in out.split("\0") if p]


def _untracked_paths(root: Path) -> list[str]:
    out = _git(root, "ls-files", "--others", "--exclude-standard", "-z")
    return [p for p in out.split("\0") if p]


def _is_excluded_dir(rel: str) -> bool:
    parts = rel.split("/")
    return any(part in _EXCLUDED_DIRS for part in parts)


def _has_case_collision(paths: list[str]) -> bool:
    seen: set[str] = set()
    for p in paths:
        cf = p.casefold()
        if cf in seen:
            return True
        seen.add(cf)
    return False


def _has_link_or_hardlink(root: Path, rel: str) -> bool:
    target = root / rel
    if target.is_symlink():
        return True
    try:
        st = target.lstat()
    except OSError:
        return False
    if os.path.islink(str(target)):
        return True
    if st.st_nlink > 1:
        return True
    return False


def inspect_baseline(repo: Path) -> str:
    """Return the full HEAD SHA of a clean Git working tree, or raise ValueError."""
    root = Path(repo)
    if root.is_symlink():
        raise ValueError("baseline root must not be a symlink")
    if not root.is_dir():
        raise ValueError("baseline root must be a directory")
    if not _is_git_root(root):
        raise ValueError("not a Git working tree")
    toplevel = _git_toplevel(root)
    if toplevel is None:
        raise ValueError("could not resolve Git top-level")
    # Refuse to inspect any subdirectory of the work tree — the control
    # root must equal the actual Git top-level so an attacker cannot
    # narrow scope by handing us a subdir.
    if Path(toplevel).resolve(strict=False) != root.resolve(strict=False):
        raise ValueError(
            f"baseline root must be Git top-level; got {root}, top-level is {toplevel}"
        )
    if _in_progress(root):
        raise ValueError("merge/rebase in progress")

    sha = _head_sha(root)
    if sha is None:
        raise ValueError("no resolvable HEAD commit")

    # Dirty tracked files: any non-empty porcelain entry is a tracked change.
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=no")
    if status.strip():
        raise ValueError("dirty tracked files")

    tracked = _tracked_paths(root)
    untracked = _untracked_paths(root)
    # `.gitignore` cannot widen the controlled root: ignored untracked files
    # are not allowed unless they fall under a fixed artifact dir (see
    # _EXCLUDED_DIRS). Note: tracked *ignored* paths (git add -f) ARE
    # included in `tracked` and ARE controlled by the contract.
    ignored = _ignored_untracked_paths(root)

    # Reject symlinks / hardlinks / case collisions under the control root.
    for rel in tracked + untracked + ignored:
        if _has_link_or_hardlink(root, rel):
            raise ValueError(f"link or hardlink not supported: {rel}")
    if _has_case_collision(tracked + untracked + ignored):
        raise ValueError("case collision under control root")

    # Untracked files are rejected unless they fall under a fixed artifact dir.
    for rel in untracked + ignored:
        if not _is_excluded_dir(rel):
            raise ValueError(f"untracked file present: {rel}")

    return sha
