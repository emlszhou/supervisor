"""Unit tests for ``supervisor.workers.boundary`` (M2-C1 contract).

These tests supplement the protected test contract in
``handoffs/M2C1/v1/task-bundle/tests/protected/test_contract.py`` with
deeper coverage of:

  - ``validate_evidence`` deep-copy isolation across every nested mutable
  - identity newline handling (fullmatch)
  - argv NUL bytes, empty argv, argv non-strings
  - timestamp leap-date validation (``2026-02-30`` rejected)
  - duration reversed, exactly 120s, and 121s
  - exit_code float/bool/str rejection
  - source/reason/platform length boundaries
  - bad top-level record types and missing fields
  - ``require_live_execution`` constant-rejection across arbitrary args
  - error sentinel does not echo caller-controlled strings

Tests are pure-stdlib and have no I/O.
"""

from __future__ import annotations

import copy

import pytest

from supervisor.workers.boundary import (
    require_live_execution,
    validate_evidence,
)

# --- common fixtures --------------------------------------------------------

EXPECTED = dict(task_id="M2C1", run_id="run-1", attempt_id="attempt-1", worker_id="worker-1")
CHECK_IDS = (
    "filesystem",
    "control_readonly",
    "network",
    "mcp",
    "credentials",
    "process_tree",
    "fresh_review",
)


def base_record():
    """Return a fully-valid 7-check baseline record (all unknown, executed=False)."""
    return dict(
        schema_version=1,
        **EXPECTED,
        platform="darwin-arm64",
        checks=[
            dict(
                id=name,
                declared="unknown",
                observed="unknown",
                enforced="unknown",
                executed=False,
                argv=None,
                cwd=None,
                started_utc=None,
                ended_utc=None,
                exit_code=None,
                output_sha256=None,
                source="synthetic-fixture",
                reason="not tested",
            )
            for name in CHECK_IDS
        ],
    )


def execute_check(check):
    """Mark a check as executed=True with a real completed probe."""
    check.update(
        executed=True,
        argv=["/synthetic/probe"],
        cwd="/synthetic",
        started_utc="2026-10-06T00:00:00Z",
        ended_utc="2026-10-06T00:00:01Z",
        exit_code=0,
        output_sha256="a" * 64,
        observed="yes",
    )


# --- validate_evidence: happy paths -----------------------------------------


def test_validate_evidence_baseline_returns_deep_copy():
    data = base_record()
    before = copy.deepcopy(data)
    result = validate_evidence(data, expected=EXPECTED)
    assert data == before, "input record must not be mutated"
    assert result == before
    assert result is not data
    assert result["checks"] is not data["checks"]


def test_validate_evidence_executed_unknown_exit_preserved():
    data = base_record()
    execute_check(data["checks"][0])
    data["checks"][0]["exit_code"] = None
    before = copy.deepcopy(data)
    result = validate_evidence(data, expected=EXPECTED)
    assert data == before
    assert result["checks"][0]["exit_code"] is None
    assert result["checks"][0]["executed"] is True
    assert result["checks"][0]["enforced"] == "unknown"


def test_validate_evidence_negative_exit_preserved():
    data = base_record()
    execute_check(data["checks"][0])
    data["checks"][0]["exit_code"] = -15
    result = validate_evidence(data, expected=EXPECTED)
    assert result["checks"][0]["exit_code"] == -15


def test_validate_evidence_enforced_yes_with_zero_exit_accepted():
    data = base_record()
    execute_check(data["checks"][0])
    data["checks"][0]["enforced"] = "yes"
    data["checks"][0]["exit_code"] = 0
    assert validate_evidence(data, expected=EXPECTED)["checks"][0]["enforced"] == "yes"


# --- validate_evidence: rejection cases -------------------------------------


@pytest.mark.parametrize(
    "case",
    [
        "bool_version",
        "extra_top_level",
        "missing_check",
        "duplicate_check",
        "wrong_attempt_id",
        "null_enforced",
    ],
)
def test_validate_evidence_rejects_inconsistent_records(case):
    data = base_record()
    if case == "bool_version":
        data["schema_version"] = True
    elif case == "extra_top_level":
        data["allow_live"] = True
    elif case == "missing_check":
        data["checks"].pop()
    elif case == "duplicate_check":
        data["checks"][-1] = copy.deepcopy(data["checks"][0])
    elif case == "wrong_attempt_id":
        data["attempt_id"] = "other"
    elif case == "null_enforced":
        data["checks"][0]["enforced"] = None
    with pytest.raises(ValueError, match="boundary_evidence_invalid"):
        validate_evidence(data, expected=EXPECTED)


@pytest.mark.parametrize(
    "case",
    [
        "bool_exit",
        "float_exit",
        "str_exit",
        "enforced_yes_with_nonzero",
        "enforced_yes_with_unknown_exit",
        "unknown_exit_with_enforced_yes",
    ],
)
def test_validate_evidence_rejects_bad_exit_code(case):
    data = base_record()
    execute_check(data["checks"][0])
    if case == "bool_exit":
        data["checks"][0]["exit_code"] = True
    elif case == "float_exit":
        data["checks"][0]["exit_code"] = 0.0
    elif case == "str_exit":
        data["checks"][0]["exit_code"] = "0"
    elif case == "enforced_yes_with_nonzero":
        data["checks"][0]["enforced"] = "yes"
        data["checks"][0]["exit_code"] = 1
    elif case == "enforced_yes_with_unknown_exit":
        data["checks"][0]["enforced"] = "yes"
        data["checks"][0]["exit_code"] = None
    else:  # unknown_exit_with_enforced_yes
        data["checks"][0]["enforced"] = "yes"
        data["checks"][0]["exit_code"] = None
    with pytest.raises(ValueError, match="boundary_evidence_invalid"):
        validate_evidence(data, expected=EXPECTED)


@pytest.mark.parametrize(
    "case",
    [
        "duration_reversed",
        "duration_too_long",
        "duration_exactly_120s_ok",
        "bad_date_leap",
        "nonutc_suffix",
        "lowercase_z",
        "missing_z",
    ],
)
def test_validate_evidence_rejects_bad_utc_or_duration(case):
    data = base_record()
    execute_check(data["checks"][0])
    if case == "duration_reversed":
        data["checks"][0]["started_utc"] = "2026-10-06T00:00:01Z"
        data["checks"][0]["ended_utc"] = "2026-10-06T00:00:00Z"
    elif case == "duration_too_long":
        data["checks"][0]["ended_utc"] = "2026-10-06T00:02:01Z"
    elif case == "duration_exactly_120s_ok":
        data["checks"][0]["started_utc"] = "2026-10-06T00:00:00Z"
        data["checks"][0]["ended_utc"] = "2026-10-06T00:02:00Z"
        result = validate_evidence(data, expected=EXPECTED)
        assert result["checks"][0]["executed"] is True
        return
    elif case == "bad_date_leap":
        data["checks"][0]["started_utc"] = "2026-02-30T00:00:00Z"
    elif case == "nonutc_suffix":
        data["checks"][0]["started_utc"] = "2026-10-06T00:00:00+00:00"
    elif case == "lowercase_z":
        data["checks"][0]["started_utc"] = "2026-10-06T00:00:00z"
    else:  # missing_z
        data["checks"][0]["started_utc"] = "2026-10-06T00:00:00"
    with pytest.raises(ValueError, match="boundary_evidence_invalid"):
        validate_evidence(data, expected=EXPECTED)


@pytest.mark.parametrize(
    "case",
    [
        "empty_argv",
        "argv_with_nul",
        "argv_with_int",
        "argv_with_none",
        "empty_cwd",
    ],
)
def test_validate_evidence_rejects_bad_argv_or_cwd(case):
    data = base_record()
    execute_check(data["checks"][0])
    if case == "empty_argv":
        data["checks"][0]["argv"] = []
    elif case == "argv_with_nul":
        data["checks"][0]["argv"] = ["/path/with/nul\x00"]
    elif case == "argv_with_int":
        data["checks"][0]["argv"] = [123]
    elif case == "argv_with_none":
        data["checks"][0]["argv"] = [None]
    elif case == "empty_cwd":
        data["checks"][0]["cwd"] = ""
    with pytest.raises(ValueError, match="boundary_evidence_invalid"):
        validate_evidence(data, expected=EXPECTED)


@pytest.mark.parametrize(
    "case",
    [
        "uppercase_sha",
        "non_hex_sha",
        "short_sha",
        "long_sha",
    ],
)
def test_validate_evidence_rejects_bad_sha256(case):
    data = base_record()
    execute_check(data["checks"][0])
    if case == "uppercase_sha":
        data["checks"][0]["output_sha256"] = "A" * 64
    elif case == "non_hex_sha":
        data["checks"][0]["output_sha256"] = "z" * 64
    elif case == "short_sha":
        data["checks"][0]["output_sha256"] = "a" * 63
    else:  # long_sha
        data["checks"][0]["output_sha256"] = "a" * 65
    with pytest.raises(ValueError, match="boundary_evidence_invalid"):
        validate_evidence(data, expected=EXPECTED)


def test_validate_evidence_executed_false_must_have_null_execution_fields():
    data = base_record()
    data["checks"][0]["executed"] = False
    data["checks"][0]["exit_code"] = 0  # should be null
    with pytest.raises(ValueError, match="boundary_evidence_invalid"):
        validate_evidence(data, expected=EXPECTED)


def test_validate_evidence_executed_false_with_observed_yes_rejected():
    data = base_record()
    data["checks"][0]["executed"] = False
    data["checks"][0]["observed"] = "yes"
    with pytest.raises(ValueError, match="boundary_evidence_invalid"):
        validate_evidence(data, expected=EXPECTED)


# --- expected input validation -----------------------------------------------


@pytest.mark.parametrize(
    "expected",
    [
        None,
        "string-not-dict",
        [],
        {"task_id": "M2C1", "run_id": "r", "attempt_id": "a"},  # missing worker_id
        {**EXPECTED, "extra": "x"},  # extra key
        {**EXPECTED, "worker_id": 123},  # non-string worker_id
        {**EXPECTED, "task_id": "M2C1\n"},  # trailing newline
        {**EXPECTED, "task_id": ""},  # empty
        {**EXPECTED, "task_id": "x" * 65},  # too long
        {**EXPECTED, "task_id": "9starts_with_digit_then_$"},  # pattern invalid
    ],
)
def test_validate_evidence_rejects_malformed_expected(expected):
    with pytest.raises(ValueError, match="boundary_evidence_invalid"):
        validate_evidence(base_record(), expected=expected)


# --- identity mismatches ----------------------------------------------------


def test_validate_evidence_record_task_id_mismatch_rejected():
    data = base_record()
    data["task_id"] = "other"
    with pytest.raises(ValueError, match="boundary_evidence_invalid"):
        validate_evidence(data, expected=EXPECTED)


def test_validate_evidence_record_worker_id_mismatch_rejected():
    data = base_record()
    data["worker_id"] = "other"
    with pytest.raises(ValueError, match="boundary_evidence_invalid"):
        validate_evidence(data, expected=EXPECTED)


def test_validate_evidence_record_identity_with_newline_rejected():
    data = base_record()
    data["worker_id"] = "worker\n"
    with pytest.raises(ValueError, match="boundary_evidence_invalid"):
        validate_evidence(data, expected=EXPECTED)


# --- platform field ---------------------------------------------------------


@pytest.mark.parametrize(
    "platform, expected_status",
    [
        ("a", True),
        ("a" * 128, True),
        ("a" * 129, "rejected"),
        ("", "rejected"),
        (None, "rejected"),
        (123, "rejected"),
        ([], "rejected"),
        ({"k": "v"}, "rejected"),
    ],
)
def test_validate_evidence_platform_length_and_type(platform, expected_status):
    data = base_record()
    data["platform"] = platform
    if expected_status is True:
        validate_evidence(data, expected=EXPECTED)
    else:
        with pytest.raises(ValueError, match="boundary_evidence_invalid"):
            validate_evidence(data, expected=EXPECTED)


# --- source / reason length ------------------------------------------------


@pytest.mark.parametrize(
    "field, max_len",
    [("source", 1024), ("reason", 4096)],
)
def test_validate_evidence_source_reason_length_boundaries(field, max_len):
    data = base_record()
    data["checks"][0][field] = "a" * max_len
    validate_evidence(data, expected=EXPECTED)
    data["checks"][0][field] = "a" * (max_len + 1)
    with pytest.raises(ValueError, match="boundary_evidence_invalid"):
        validate_evidence(data, expected=EXPECTED)


def test_validate_evidence_source_required_even_when_executed_false():
    data = base_record()
    data["checks"][0]["source"] = ""
    with pytest.raises(ValueError, match="boundary_evidence_invalid"):
        validate_evidence(data, expected=EXPECTED)


# --- deep copy isolation ---------------------------------------------------


def test_validate_evidence_deep_copy_isolation_nested_check():
    data = base_record()
    execute_check(data["checks"][0])
    before = copy.deepcopy(data)
    result = validate_evidence(data, expected=EXPECTED)
    # Mutate the result; the original input must not change.
    result["checks"][0]["exit_code"] = -999
    result["checks"][0]["argv"].append("/injected")
    assert data == before
    assert data["checks"][0]["argv"] == ["/synthetic/probe"]


# --- error sentinel ---------------------------------------------------------


def test_error_does_not_echo_raw_value_in_stringified_exception():
    sentinel = "PRIVATE_USER_TOKEN_abc123"
    data = base_record()
    data["worker_id"] = sentinel
    with pytest.raises(ValueError) as error:
        validate_evidence(data, expected=EXPECTED)
    assert sentinel not in str(error.value)


def test_error_does_not_echo_long_reason():
    sentinel = "SECRET_LONG_TOKEN_ABCDEF" * 200  # exceeds 4096-char reason cap
    assert len(sentinel) > 4096
    data = base_record()
    data["checks"][0]["reason"] = sentinel
    with pytest.raises(ValueError) as error:
        validate_evidence(data, expected=EXPECTED)
    assert sentinel not in str(error.value)


# --- require_live_execution -------------------------------------------------


def test_require_live_execution_raises_with_substring():
    with pytest.raises(RuntimeError, match="live_execution_disabled"):
        require_live_execution()


def test_require_live_execution_rejects_allow_live_true():
    with pytest.raises(RuntimeError, match="live_execution_disabled"):
        require_live_execution(base_record(), allow_live=True)


def test_require_live_execution_rejects_kwargs():
    with pytest.raises(RuntimeError, match="live_execution_disabled"):
        require_live_execution(base_record(), enable_live="1", allow_live=True, dry_run=False)


def test_require_live_execution_rejects_positional_args():
    with pytest.raises(RuntimeError, match="live_execution_disabled"):
        require_live_execution(base_record(), True, "anything")


# --- record-level rejections ------------------------------------------------


@pytest.mark.parametrize(
    "record",
    [
        None,
        "string",
        [],
        42,
    ],
)
def test_validate_evidence_rejects_non_dict_record(record):
    with pytest.raises(ValueError, match="boundary_evidence_invalid"):
        validate_evidence(record, expected=EXPECTED)


def test_validate_evidence_rejects_extra_top_level():
    data = base_record()
    data["extra_top"] = 1
    with pytest.raises(ValueError, match="boundary_evidence_invalid"):
        validate_evidence(data, expected=EXPECTED)


def test_validate_evidence_rejects_missing_top_level():
    data = base_record()
    del data["platform"]
    with pytest.raises(ValueError, match="boundary_evidence_invalid"):
        validate_evidence(data, expected=EXPECTED)


def test_validate_evidence_rejects_checks_not_list():
    data = base_record()
    data["checks"] = {}
    with pytest.raises(ValueError, match="boundary_evidence_invalid"):
        validate_evidence(data, expected=EXPECTED)


def test_validate_evidence_rejects_check_extra_field():
    data = base_record()
    data["checks"][0]["secret"] = "value"
    with pytest.raises(ValueError, match="boundary_evidence_invalid"):
        validate_evidence(data, expected=EXPECTED)


def test_validate_evidence_rejects_check_id_unknown():
    data = base_record()
    data["checks"][0]["id"] = "unknown"
    with pytest.raises(ValueError, match="boundary_evidence_invalid"):
        validate_evidence(data, expected=EXPECTED)


def test_validate_evidence_rejects_tri_state_no():
    data = base_record()
    data["checks"][0]["declared"] = "no"
    validate_evidence(data, expected=EXPECTED)


def test_validate_evidence_rejects_executed_not_bool():
    data = base_record()
    data["checks"][0]["executed"] = 1
    with pytest.raises(ValueError, match="boundary_evidence_invalid"):
        validate_evidence(data, expected=EXPECTED)


# --- regression tests for M2C1-R1-utc (Codex round 2) ----------------------


def test_regression_fullwidth_digits_timestamp_rejected():
    """M2C1-R1-utc: the timestamp regex must use [0-9] (ASCII), not \\d
    (which under Python's default Unicode-aware re matches fullwidth
    digits 0-9). A fullwidth timestamp that looks visually identical
    to ASCII must be rejected.
    """
    data = base_record()
    execute_check(data["checks"][0])
    data["checks"][0]["started_utc"] = (
        "\uff12\uff10\uff12\uff16-\uff11\uff10-\uff10\uff16T\uff10\uff10:\uff10\uff10:\uff10\uff10Z"
    )
    data["checks"][0]["ended_utc"] = (
        "\uff12\uff10\uff12\uff16-\uff11\uff10-\uff10\uff16T\uff10\uff10:\uff10\uff10:\uff10\uff11Z"
    )
    with pytest.raises(ValueError, match="boundary_evidence_invalid"):
        validate_evidence(data, expected=EXPECTED)


def test_regression_arabic_indic_digits_timestamp_rejected():
    """Other Unicode decimal digit blocks (e.g. Arabic-Indic ٠-٩) must
    also be rejected by the strict ASCII timestamp regex.
    """
    data = base_record()
    execute_check(data["checks"][0])
    data["checks"][0]["started_utc"] = (
        "\u0660\u0660\u0660\u0660-\u0660\u0660-\u0660\u0660T\u0660\u0660:\u0660\u0660:\u0660\u0660Z"
    )
    with pytest.raises(ValueError, match="boundary_evidence_invalid"):
        validate_evidence(data, expected=EXPECTED)


def test_regression_mixed_ascii_and_unicode_digits_timestamp_rejected():
    """A timestamp that mixes ASCII and Unicode digits must be rejected;
    fullmatch rejects any deviation, so even one fullwidth digit fails."""
    data = base_record()
    execute_check(data["checks"][0])
    data["checks"][0]["started_utc"] = "2026-10-06T00:00:\uff10\uff10Z"  # last 2 digits fullwidth
    with pytest.raises(ValueError, match="boundary_evidence_invalid"):
        validate_evidence(data, expected=EXPECTED)


def test_regression_ascii_120_second_boundary_accepted():
    """A 120-second boundary span (allowed by the contract) with strict
    ASCII digits is accepted."""
    data = base_record()
    execute_check(data["checks"][0])
    data["checks"][0]["started_utc"] = "2026-10-06T00:00:00Z"
    data["checks"][0]["ended_utc"] = "2026-10-06T00:02:00Z"  # exactly 120s
    result = validate_evidence(data, expected=EXPECTED)
    assert result["checks"][0]["executed"] is True


def test_regression_ascii_leap_date_rejected():
    """Strict UTC datetime validation rejects 2026-02-30 even when
    digits are pure ASCII."""
    data = base_record()
    execute_check(data["checks"][0])
    data["checks"][0]["started_utc"] = "2026-02-30T00:00:00Z"
    data["checks"][0]["ended_utc"] = "2026-03-01T00:00:00Z"
    with pytest.raises(ValueError, match="boundary_evidence_invalid"):
        validate_evidence(data, expected=EXPECTED)


def test_regression_enforced_yes_with_unknown_exit_rejected():
    """M2C1-R1-evidence: enforced=yes requires exit_code=0, not None.
    The report §9.3 wording previously said '校验器不强制' which
    contradicted the module; this regression test pins the contract."""
    data = base_record()
    execute_check(data["checks"][0])
    data["checks"][0]["enforced"] = "yes"
    data["checks"][0]["exit_code"] = None  # exit unknown
    with pytest.raises(ValueError, match="boundary_evidence_invalid"):
        validate_evidence(data, expected=EXPECTED)


def test_regression_executed_true_with_unknown_exit_preserved_when_enforced_unknown():
    """When exit_code is None, executed must remain True (the
    'executed but exit unknown' contract guarantee). enforced must NOT
    be 'yes' (because the contract forbids that)."""
    data = base_record()
    execute_check(data["checks"][0])
    data["checks"][0]["exit_code"] = None
    data["checks"][0]["enforced"] = "unknown"
    result = validate_evidence(data, expected=EXPECTED)
    assert result["checks"][0]["executed"] is True
    assert result["checks"][0]["exit_code"] is None
    assert result["checks"][0]["enforced"] == "unknown"
