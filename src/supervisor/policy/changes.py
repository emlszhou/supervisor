"""Change-scope and budget checking over two M1 workspace snapshots.

`check_changes` compares a before/after M1 snapshot, classifies every change
(content, mode, addition, deletion), and enforces the allowed/forbidden pattern
rules and the file/line budgets. `diff_lines` is trusted coordinator input (Git
added+deleted); this API never launches Git.
"""

from __future__ import annotations

import re

from supervisor.workspace.snapshot import (
    _ALLOWED_MODES,
    _SHA_RE,
    _snapshot_digest,
    _validate_relative_path,
)

_SNAPSHOT_FIELDS = {"schema_version", "baseline_commit", "files", "deleted", "snapshot_sha256"}


def _validate_snapshot(snapshot: dict) -> None:
    if not isinstance(snapshot, dict) or set(snapshot) != _SNAPSHOT_FIELDS:
        raise ValueError("snapshot has unexpected fields")
    # schema_version must be the integer 1 (not bool, not str).
    sv = snapshot["schema_version"]
    if isinstance(sv, bool) or not isinstance(sv, int) or sv != 1:
        raise ValueError("snapshot schema_version must be the integer 1")
    if not isinstance(snapshot["baseline_commit"], str) or not _SHA_RE.match(
        snapshot["baseline_commit"]
    ):
        raise ValueError("invalid baseline_commit")
    if not isinstance(snapshot["files"], list) or not isinstance(snapshot["deleted"], list):
        raise ValueError("files/deleted must be lists")
    # files: every entry is the exact 3-key {path,mode,sha256} dict, sorted,
    # case-distinct, mode/sha256 fingerprint match between fingerprints.
    files = snapshot["files"]
    seen_paths: set[str] = set()
    seen_cf: set[str] = set()
    prev: dict | None = None
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {"path", "mode", "sha256"}:
            raise ValueError("invalid file entry")
        if (
            not isinstance(entry["mode"], str)
            or not isinstance(entry["sha256"], str)
            or not _SHA_RE.match(entry["sha256"])
        ):
            raise ValueError("invalid file entry")
        if entry["mode"] not in _ALLOWED_MODES:
            raise ValueError(f"invalid mode: {entry['mode']}")
        _validate_relative_path(entry["path"])
        if prev is not None and entry["path"] < prev["path"]:
            raise ValueError("snapshot files must be sorted by path")
        cf = entry["path"].casefold()
        if cf in seen_cf:
            raise ValueError(f"snapshot files has case-fold collision: {entry['path']}")
        seen_cf.add(cf)
        if entry["path"] in seen_paths:
            raise ValueError(f"snapshot files has duplicate path: {entry['path']}")
        seen_paths.add(entry["path"])
        prev = entry
    # deleted: sorted, case-distinct, no overlap with files.
    deleted = snapshot["deleted"]
    deleted_seen_cf: set[str] = set()
    deleted_seen: set[str] = set()
    prev_d = None
    for rel in deleted:
        if not isinstance(rel, str):
            raise ValueError("snapshot deleted must be a list of strings")
        _validate_relative_path(rel)
        if prev_d is not None and rel < prev_d:
            raise ValueError("snapshot deleted must be sorted")
        cf = rel.casefold()
        if cf in deleted_seen_cf:
            raise ValueError(f"snapshot deleted has case-fold collision: {rel}")
        deleted_seen_cf.add(cf)
        if rel in deleted_seen:
            raise ValueError(f"snapshot deleted has duplicate: {rel}")
        deleted_seen.add(rel)
        if rel in seen_paths:
            raise ValueError(f"snapshot deleted overlaps files: {rel}")
        prev_d = rel
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


def _matches_path(path: str, segments: list[str]) -> bool:
    """Match `path` (POSIX) against a list of pattern segments.

    Each pattern segment is either a single-segment wildcard string
    (containing `*`/`?` but no `/`) or the literal segment ``**``
    (globstar). Single-segment wildcards match one whole path segment
    via ``fnmatch`` semantics; ``**`` matches zero or more whole path
    segments. This is git's ``globstar`` pathspec semantics.
    """
    parts = path.split("/")
    return _match_segments(parts, segments, 0, 0)


def _match_segments(parts: list[str], pats: list[str], pi: int, qi: int) -> bool:
    # Skip empty parts (shouldn't happen after validation, defensive).
    if pi == len(parts):
        return qi == len(pats) or all(p == "**" for p in pats[qi:])
    if qi == len(pats):
        return False
    if pats[qi] == "**":
        # Globstar: 0 or more segments. Greedy descent in position.
        # Skip globstar with empty match and try all later positions.
        if _match_segments(parts, pats, pi, qi + 1):
            return True
        for j in range(pi, len(parts)):
            if _match_segments(parts, pats, j + 1, qi + 1):
                return True
        return False
    if not _segment_match_wildcard(pats[qi], parts[pi]):
        return False
    return _match_segments(parts, pats, pi + 1, qi + 1)


def _segment_match_wildcard(pattern: str, segment: str) -> bool:
    r"""Match one path segment against a single-segment wildcard string.

    `*` matches zero or more characters in the segment; `?` matches one
    character; anything else matches itself. Backslash escapes the next
    character.
    """
    pi = 0
    si = 0
    star = -1
    ssave = 0
    while si < len(segment):
        if pi < len(pattern) and pattern[pi] == "\\" and pi + 1 < len(pattern):
            if pattern[pi + 1] == segment[si]:
                pi += 2
                si += 1
                continue
            if star == -1:
                return False
            pi = star + 1
            si = ssave + 1
            ssave = si
            continue
        if pi < len(pattern) and pattern[pi] == "*":
            star = pi
            ssave = si
            pi += 1
            continue
        if pi < len(pattern) and pattern[pi] == "?":
            pi += 1
            si += 1
            continue
        if pi < len(pattern) and pattern[pi] == segment[si]:
            pi += 1
            si += 1
            continue
        if star != -1:
            pi = star + 1
            ssave += 1
            si = ssave
            continue
        return False
    while pi < len(pattern) and pattern[pi] == "*":
        pi += 1
    return pi == len(pattern)


def _compile(pattern: str) -> re.Pattern[str]:
    """Compile an M1 change-pattern into a callable matcher.

    The returned object is duck-typed as ``re.Pattern`` so callers can
    continue to use ``.match(path)``. Path matching uses git's
    ``globstar`` pathspec semantics:

    - ``**/foo.py`` matches ``foo.py`` and ``a/foo.py`` and ``a/b/foo.py``;
    - ``src/**/foo.py`` matches ``src/foo.py`` and ``src/a/foo.py``
      and ``src/a/b/foo.py``;
    - ``src/**`` matches any non-empty path under ``src``,
      e.g. ``src/x.py`` and ``src/a/x.py`` (but not ``src`` alone).
    """
    _validate_pattern(pattern)
    return _SegmentMatcher(pattern, pattern.split("/"))


class _SegmentMatcher:
    """Duck-typed subset of ``re.Pattern[str]`` backed by ``_matches_path``."""

    __slots__ = ("pattern", "segments")

    def __init__(self, pattern: str, segments: list[str]) -> None:
        self.pattern = pattern
        self.segments = segments

    def match(self, path: str) -> re.Match[str] | bool:
        if not _matches_path(path, self.segments):
            return None
        # Return a dummy truthy match-shaped object so callers that compare
        # to ``None`` work identically to a real re.Match result.
        return _TruthyMatch(path)


class _TruthyMatch:
    __slots__ = ("string",)

    def __init__(self, string: str) -> None:
        self.string = string

    def __bool__(self) -> bool:
        return True


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
