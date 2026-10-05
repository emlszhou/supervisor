"""Change-scope and budget checking over two M1 workspace snapshots.

`check_changes` compares a before/after M1 snapshot, classifies every change
(content, mode, addition, deletion), and enforces the allowed/forbidden pattern
rules and the file/line budgets. `diff_lines` is trusted coordinator input (Git
added+deleted); this API never launches Git.
"""

from __future__ import annotations

import re

from supervisor.workspace.snapshot import _SHA_RE, _snapshot_digest, _validate_relative_path

_SNAPSHOT_FIELDS = {"schema_version", "baseline_commit", "files", "deleted", "snapshot_sha256"}


def _validate_snapshot(snapshot: dict) -> None:
    if not isinstance(snapshot, dict) or set(snapshot) != _SNAPSHOT_FIELDS:
        raise ValueError("snapshot has unexpected fields")
    if snapshot["schema_version"] != 1:
        raise ValueError("unsupported snapshot schema_version")
    if not isinstance(snapshot["baseline_commit"], str) or not _SHA_RE.match(
        snapshot["baseline_commit"]
    ):
        raise ValueError("invalid baseline_commit")
    if not isinstance(snapshot["files"], list) or not isinstance(snapshot["deleted"], list):
        raise ValueError("files/deleted must be lists")
    for entry in snapshot["files"]:
        if not isinstance(entry, dict) or set(entry) != {"path", "mode", "sha256"}:
            raise ValueError("invalid file entry")
        _validate_relative_path(entry["path"])
    for rel in snapshot["deleted"]:
        _validate_relative_path(rel)
    payload = {k: v for k, v in snapshot.items() if k != "snapshot_sha256"}
    if _snapshot_digest(payload) != snapshot["snapshot_sha256"]:
        raise ValueError("snapshot self-digest mismatch")


def _validate_pattern(pattern: str) -> None:
    if not pattern or pattern.startswith("/") or "\\" in pattern:
        raise ValueError(f"invalid pattern: {pattern!r}")
    if pattern in (".", "..") or pattern.startswith("./") or pattern.startswith("../"):
        raise ValueError(f"invalid pattern: {pattern!r}")
    if ":" in pattern:
        raise ValueError(f"invalid pattern: {pattern!r}")
    for part in pattern.split("/"):
        if part in ("", ".", ".."):
            raise ValueError(f"invalid pattern: {pattern!r}")


def _compile(pattern: str) -> re.Pattern[str]:
    _validate_pattern(pattern)
    out: list[str] = []
    for part in pattern.split("/"):
        if part == "**":
            out.append(".*")
        else:
            out.append("".join(_regex_escape_char(c) for c in part))
    return re.compile("^" + "/".join(out) + "$")


def _regex_escape_char(c: str) -> str:
    if c == "*":
        return "[^/]*"
    if c == "?":
        return "[^/]"
    return re.escape(c)


def _matches(path: str, pattern: str) -> bool:
    return _compile(pattern).match(path) is not None


def _validate_budget(name: str, value: int, *, minimum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an int")
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")


def check_changes(
    before: dict,
    after: dict,
    *,
    allowed: list[str],
    forbidden: list[str],
    max_changed_files: int,
    max_diff_lines: int,
    diff_lines: int,
) -> dict:
    """Classify changes between two snapshots and enforce scope/budget rules."""
    _validate_snapshot(before)
    _validate_snapshot(after)
    if before["baseline_commit"] != after["baseline_commit"]:
        raise ValueError("before/after baseline_commit differ")

    for pattern in list(allowed) + list(forbidden):
        _validate_pattern(pattern)

    _validate_budget("max_changed_files", max_changed_files, minimum=1)
    _validate_budget("max_diff_lines", max_diff_lines, minimum=1)
    _validate_budget("diff_lines", diff_lines, minimum=0)

    before_files = {f["path"]: f for f in before["files"]}
    after_files = {f["path"]: f for f in after["files"]}
    before_deleted = set(before["deleted"])
    after_deleted = set(after["deleted"])

    changed: set[str] = set()
    for path, entry in after_files.items():
        prev = before_files.get(path)
        if prev is None or prev["sha256"] != entry["sha256"] or prev["mode"] != entry["mode"]:
            changed.add(path)
    for path in before_files:
        if path not in after_files:
            changed.add(path)
    changed |= after_deleted - before_deleted
    changed |= before_deleted - after_deleted

    changed_files = sorted(changed)
    for path in changed_files:
        if any(_matches(path, pattern) for pattern in forbidden):
            raise ValueError(f"change matches forbidden pattern: {path}")
        if not any(_matches(path, pattern) for pattern in allowed):
            raise ValueError(f"change not in allowed patterns: {path}")

    if len(changed_files) > max_changed_files:
        raise ValueError("changed file count exceeds budget")
    if diff_lines > max_diff_lines:
        raise ValueError("diff line count exceeds budget")

    return {
        "changed_files": changed_files,
        "changed_count": len(changed_files),
        "diff_lines": diff_lines,
    }
