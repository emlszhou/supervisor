"""Read-only clean Git baseline inspection."""

import hashlib
import subprocess
from pathlib import Path

from supervisor.workspace.snapshot import _git, _root, capture_snapshot


def inspect_baseline(repo: Path) -> str:
    root = _root(repo)
    for marker in (
        "MERGE_HEAD",
        "REBASE_HEAD",
        "CHERRY_PICK_HEAD",
        "BISECT_HEAD",
        "rebase-merge",
        "rebase-apply",
        "sequencer",
    ):
        location = _git(root, "rev-parse", "--git-path", marker).strip()
        path = Path(location)
        if not path.is_absolute():
            path = root / path
        if path.exists():
            raise ValueError("merge/rebase in progress")
    try:
        sha = _git(root, "rev-parse", "--verify", "HEAD^{commit}").strip()
    except subprocess.CalledProcessError as e:
        raise ValueError("no resolvable HEAD commit") from e
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=no")
    if status.strip():
        raise ValueError("dirty tracked files")
    snapshot = capture_snapshot(root, baseline_commit=sha)

    expected = []
    for row in filter(None, _git(root, "ls-tree", "-r", "-z", sha).split("\0")):
        header, rel = row.split("\t", 1)
        mode, kind, oid = header.split()
        if kind != "blob" or mode not in ("100644", "100755"):
            raise ValueError("unsupported baseline tree file")
        data = subprocess.check_output(
            ["git", "-C", str(root), "cat-file", "blob", oid], stderr=subprocess.PIPE
        )
        expected.append({"path": rel, "mode": mode, "sha256": hashlib.sha256(data).hexdigest()})
    if snapshot["deleted"] or snapshot["files"] != sorted(expected, key=lambda f: f["path"]):
        raise ValueError("dirty tracked files or untracked file present")
    if _git(root, "status", "--porcelain=v1", "--untracked-files=no") != status:
        raise ValueError("baseline changed during inspection")
    if _git(root, "rev-parse", "HEAD").strip() != sha:
        raise ValueError("HEAD changed during inspection")
    return sha
