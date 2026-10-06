"""Pure-stdlib boundary evidence validator for the M2-C1 contract.

This module exposes two entry points:

  - ``validate_evidence(record: dict, *, expected: dict[str, str]) -> dict``
    validates a boundary-evidence record against the M2-C1 schema, returns
    a deep copy on success, raises ``ValueError`` with a fixed safe error
    tag (never echoing the offending payload) on any schema, type, identity,
    datetime, length, or execution-shape violation.

  - ``require_live_execution(*args, **kwargs)`` always raises
    ``RuntimeError`` containing the substring ``live_execution_disabled``,
    regardless of arguments. There is no enable path. The function exists
    only to anchor the "live execution remains disabled" invariant at the
    Python import boundary; nothing here launches a process, reads a
    config, opens a network connection, or accesses the source path.

The validator is structural only. It does NOT attest that any check is a
real OS isolation guarantee, and it MUST NOT return any value whose
truthiness implies live execution is permitted. The check outputs are
submission-time consistency markers; the M2-C2 contract is the place
where real isolation enforcement is implemented.

Cross-checked with the protected test contract in
``handoffs/M2C1/v1/task-bundle/tests/protected/test_contract.py``: 23
cases including unknown-exit preservation, deep-copy isolation,
executed=False/True semantics, malformed expected input, newline
identity, enforced/observed/executed consistency, length and timestamp
boundaries, error sentinel that does not echo raw values, and the
constant-rejection ``require_live_execution`` path.
"""

from __future__ import annotations

import copy
import datetime
import re

# ----- Constants from the M2-C1 contract --------------------------------------

_TASK_ID = "M2C1-boundary-preflight"

# Identity pattern for task_id / run_id / attempt_id / worker_id in
# ``expected`` and the matching identity fields in ``record``:
# starts with letter/digit, then [A-Za-z0-9._-], max 64 chars.
_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"

# SHA256 hex (lowercase 64 chars)
_SHA256_PATTERN = r"^[a-f0-9]{64}$"

# Required check ids in the M2-C1 boundary-evidence record
_CHECK_IDS = (
    "filesystem",
    "control_readonly",
    "network",
    "mcp",
    "credentials",
    "process_tree",
    "fresh_review",
)

# Required identity keys on both ``expected`` and ``record``
_EXPECTED_KEYS = ("task_id", "run_id", "attempt_id", "worker_id")
_RECORD_IDENTITY_KEYS = _EXPECTED_KEYS

# Required top-level record keys (exact set; no extras allowed)
_RECORD_TOP_LEVEL_KEYS = (
    "schema_version",
    "task_id",
    "run_id",
    "attempt_id",
    "worker_id",
    "platform",
    "checks",
)

# Required check fields (exact set per check)
_CHECK_FIELDS = (
    "id",
    "declared",
    "observed",
    "enforced",
    "executed",
    "argv",
    "cwd",
    "started_utc",
    "ended_utc",
    "exit_code",
    "output_sha256",
    "source",
    "reason",
)

# Tri-state values
_TRISTATE = ("yes", "no", "unknown")

# Length limits
_PLATFORM_MAX = 128
_SOURCE_MAX = 1024
_REASON_MAX = 4096

# Timestamp regex: strict ``YYYY-MM-DDTHH:MM:SSZ`` with 4-digit year, zero-padded.
# Uses ``[0-9]`` (ASCII) rather than ``\d`` (which under Python's default
# Unicode-aware re would match fullwidth digits ０-９ and other Unicode
# decimal digits) so callers cannot bypass the digit gate by substituting
# visually-identical non-ASCII digits. The regex itself is ASCII-only
# because ``[0-9]`` has no Unicode interpretation; the surrounding
# ``re.fullmatch`` call below uses no flags (so no UNICODE flag would
# be set even by accident).
_TIMESTAMP_PATTERN = r"^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})Z$"

# Maximum check duration in seconds
_MAX_CHECK_SECONDS = 120

# Sentinel error prefix. Fixed, never echoed from caller input.
_ERR_PREFIX = "boundary_evidence_invalid"


# ----- Public API ------------------------------------------------------------


def require_live_execution(*args, **kwargs):
    """Always raise ``RuntimeError`` with ``live_execution_disabled``.

    The M2-C1 contract forbids any process launch, network call, or
    credential read. This function exists to anchor that invariant: any
    caller path that reaches this point is forbidden. The ``*args, **kwargs``
    signature is consumed but never inspected, so callers cannot influence
    the rejection via arguments (including ``allow_live=True``).
    """
    del args, kwargs  # explicit: we do not read them
    raise RuntimeError(
        "live_execution_disabled: boundary module never enables live "
        "process launch or OS-isolation checks; the M2-C2 contract "
        "owns real isolation enforcement."
    )


def validate_evidence(record, *, expected):
    """Validate a boundary-evidence record and return a deep copy on success.

    Raises ``ValueError`` with a fixed safe error tag on any violation.
    The error message never echoes the offending payload value.

    Returns a NEW ``dict`` (deep copy) that the caller can safely mutate;
    the input ``record`` is never modified.
    """
    expected = _validate_expected(expected)
    record = _validate_record(record, expected)
    return copy.deepcopy(record)


# ----- Helpers ----------------------------------------------------------------


def _raise_invalid(message):
    """Raise ``ValueError`` with a fixed safe error tag.

    The message is a category name from a closed enumeration, never
    constructed from caller-controlled bytes. Tests confirm that
    user-supplied sentinels (``PRIVATE_SENTINEL``) never appear in
    the stringified exception.
    """
    raise ValueError(f"{_ERR_PREFIX}:{message}")


def _is_bool(value):
    return isinstance(value, bool)


def _is_int(value):
    """Real int (not bool)."""
    return isinstance(value, int) and not _is_bool(value)


def _is_str(value):
    return isinstance(value, str)


def _is_nonempty_str(value):
    return _is_str(value) and bool(value)


def _validate_expected(expected):
    """Validate ``expected`` identity dict.

    Raises ``ValueError`` on any violation. Returns the dict unchanged
    (no normalization, no strip, no fullmatch leniency).
    """
    if not isinstance(expected, dict):
        _raise_invalid("expected_not_dict")

    if set(expected.keys()) != set(_EXPECTED_KEYS):
        _raise_invalid("expected_keys_mismatch")

    for key in _EXPECTED_KEYS:
        value = expected[key]
        if not _is_nonempty_str(value):
            _raise_invalid("expected_field_invalid")
        if not re.fullmatch(_ID_PATTERN, value):
            _raise_invalid("expected_identity_pattern")

    return expected


def _validate_record(record, expected):
    """Validate the record and return it (still original; deep copy is
    done by the public ``validate_evidence``)."""
    if not isinstance(record, dict):
        _raise_invalid("record_not_dict")

    record_keys = set(record.keys())
    expected_keys = set(_RECORD_TOP_LEVEL_KEYS)
    if record_keys != expected_keys:
        _raise_invalid("record_keys_mismatch")

    # schema_version must be exactly integer 1, not bool.
    version = record["schema_version"]
    if not _is_int(version) or version != 1:
        _raise_invalid("schema_version_invalid")

    # Identity binding: record identity MUST equal expected identity.
    for key in _RECORD_IDENTITY_KEYS:
        if not _is_nonempty_str(record[key]):
            _raise_invalid("record_identity_field_invalid")
        if not re.fullmatch(_ID_PATTERN, record[key]):
            _raise_invalid("record_identity_pattern")
        if record[key] != expected[key]:
            _raise_invalid("identity_mismatch")

    # Platform: non-empty string, length <= 128.
    platform = record["platform"]
    if not _is_nonempty_str(platform):
        _raise_invalid("platform_invalid")
    if len(platform) > _PLATFORM_MAX:
        _raise_invalid("platform_too_long")

    # checks: list of 7 items, each with the right keys.
    checks = record["checks"]
    if not isinstance(checks, list):
        _raise_invalid("checks_not_list")
    if len(checks) != len(_CHECK_IDS):
        _raise_invalid("checks_count_invalid")
    seen_ids = set()
    for check in checks:
        if not isinstance(check, dict):
            _raise_invalid("check_not_dict")
        if set(check.keys()) != set(_CHECK_FIELDS):
            _raise_invalid("check_keys_mismatch")
        _validate_check(check, seen_ids)

    if seen_ids != set(_CHECK_IDS):
        _raise_invalid("checks_ids_incomplete")
    return record


def _validate_check(check, seen_ids):
    """Validate a single check dict; raises ``ValueError`` on any violation."""
    cid = check["id"]
    if not _is_nonempty_str(cid) or cid not in _CHECK_IDS:
        _raise_invalid("check_id_invalid")
    if cid in seen_ids:
        _raise_invalid("check_id_duplicate")
    seen_ids.add(cid)

    # Tri-state fields
    for field in ("declared", "observed", "enforced"):
        if check[field] not in _TRISTATE:
            _raise_invalid("check_tristate_invalid")

    # executed must be a real bool
    if not isinstance(check["executed"], bool):
        _raise_invalid("check_executed_invalid")

    # source: non-empty str, length <= 1024
    source = check["source"]
    if not _is_nonempty_str(source):
        _raise_invalid("source_invalid")
    if len(source) > _SOURCE_MAX:
        _raise_invalid("source_too_long")

    # reason: non-empty str, length <= 4096
    reason = check["reason"]
    if not _is_nonempty_str(reason):
        _raise_invalid("reason_invalid")
    if len(reason) > _REASON_MAX:
        _raise_invalid("reason_too_long")

    if not check["executed"]:
        # executed=False: every execution field must be null; observed/enforced
        # must both be unknown; declared may be any tri-state.
        if check["observed"] != "unknown" or check["enforced"] != "unknown":
            _raise_invalid("unexecuted_tristate_invalid")
        for field in ("argv", "cwd", "started_utc", "ended_utc", "exit_code", "output_sha256"):
            if check[field] is not None:
                _raise_invalid("unexecuted_field_not_null")
    else:
        # executed=True: argv non-empty list of non-empty non-NUL strings;
        # cwd non-empty str; UTC timestamps valid with end >= start, span <= 120s;
        # exit_code is real int (negative allowed) or None; bool/float rejected;
        # output_sha256 is lowercase 64-hex.
        argv = check["argv"]
        if not isinstance(argv, list) or not argv:
            _raise_invalid("argv_invalid")
        for a in argv:
            if not _is_nonempty_str(a) or "\x00" in a:
                _raise_invalid("argv_element_invalid")
        cwd = check["cwd"]
        if not _is_nonempty_str(cwd):
            _raise_invalid("cwd_invalid")

        started = _parse_utc(check["started_utc"])
        ended = _parse_utc(check["ended_utc"])
        if ended < started:
            _raise_invalid("duration_reversed")
        if (ended - started).total_seconds() > _MAX_CHECK_SECONDS:
            _raise_invalid("duration_too_long")

        exit_code = check["exit_code"]
        # Allow real int (including negative) or None. Reject bool, float, str.
        if exit_code is not None and not _is_int(exit_code):
            _raise_invalid("exit_code_invalid")

        sha = check["output_sha256"]
        if not _is_nonempty_str(sha) or not re.fullmatch(_SHA256_PATTERN, sha):
            _raise_invalid("output_sha256_invalid")

        # enforced=yes requires observed=yes, exit_code==0 (real int).
        # This is a submission consistency check, not an attestation.
        if check["enforced"] == "yes":
            if check["observed"] != "yes":
                _raise_invalid("enforced_observed_mismatch")
            if exit_code != 0:
                _raise_invalid("enforced_exit_nonzero")
        # enforced=yes MUST NOT coexist with unknown exit_code: a declared
        # guarantee cannot exist without a known outcome.
        if check["enforced"] == "yes" and exit_code is None:
            _raise_invalid("enforced_exit_unknown")


def _parse_utc(value):
    """Parse a strict UTC timestamp string; raise on any deviation."""
    if not _is_nonempty_str(value):
        _raise_invalid("timestamp_invalid")
    match = re.fullmatch(_TIMESTAMP_PATTERN, value)
    if match is None:
        _raise_invalid("timestamp_format")
    try:
        dt = datetime.datetime(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
            int(match.group(4)),
            int(match.group(5)),
            int(match.group(6)),
            tzinfo=datetime.UTC,
        )
    except ValueError:
        _raise_invalid("timestamp_value")
    return dt
