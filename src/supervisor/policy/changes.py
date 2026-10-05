"""Scope checking over strict M1 snapshots; diff_lines is trusted caller input."""

import re

from supervisor.workspace.snapshot import _validate_expected, _validate_relative_path


def _validate_pattern(pattern: str) -> None:
    _validate_relative_path(pattern)
    if any("**" in part and part != "**" for part in pattern.split("/")):
        raise ValueError("globstar must occupy a whole pattern segment")


def _matches(path: str, pattern: str) -> bool:
    parts, patterns = path.split("/"), pattern.split("/")

    reachable = {0}
    for pattern in patterns:
        if pattern == "**":
            reachable = set(range(min(reachable), len(parts) + 1)) if reachable else set()
        else:
            regex = "".join(
                ".*" if c == "*" else "." if c == "?" else re.escape(c) for c in pattern
            )
            reachable = {
                i + 1
                for i in reachable
                if i < len(parts) and re.fullmatch(regex, parts[i], re.DOTALL) is not None
            }
    return len(parts) in reachable


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
    _validate_expected(before)
    _validate_expected(after)
    if before["baseline_commit"] != after["baseline_commit"]:
        raise ValueError("before/after baseline_commit differ")
    for patterns in (allowed, forbidden):
        if not isinstance(patterns, list):
            raise ValueError("patterns must be lists")
        for pattern in patterns:
            try:
                _validate_pattern(pattern)
            except ValueError as e:
                raise ValueError(f"invalid pattern: {pattern!r}") from e
    for name, value, minimum in (
        ("max_changed_files", max_changed_files, 1),
        ("max_diff_lines", max_diff_lines, 1),
        ("diff_lines", diff_lines, 0),
    ):
        if type(value) is not int or value < minimum:
            raise ValueError(f"{name} must be an integer >= {minimum}")
    old = {f["path"]: f for f in before["files"]}
    new = {f["path"]: f for f in after["files"]}
    changed = {p for p in old.keys() | new.keys() if old.get(p) != new.get(p)}
    changed |= set(before["deleted"]) ^ set(after["deleted"])
    for path in sorted(changed):
        if any(_matches(path, pattern) for pattern in forbidden):
            raise ValueError(f"change matches forbidden pattern: {path}")
        if not any(_matches(path, pattern) for pattern in allowed):
            raise ValueError(f"change not in allowed patterns: {path}")
    if len(changed) > max_changed_files:
        raise ValueError("changed file count exceeds budget")
    if diff_lines > max_diff_lines:
        raise ValueError("diff line count exceeds budget")
    return {
        "changed_files": sorted(changed),
        "changed_count": len(changed),
        "diff_lines": diff_lines,
    }
