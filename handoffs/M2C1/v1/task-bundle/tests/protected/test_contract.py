"""Independent boundary evidence checks, not claims of real OS isolation."""

import copy

import pytest

EXPECTED = dict(task_id="M2C1", run_id="run", attempt_id="attempt", worker_id="worker")
IDS = (
    "filesystem",
    "control_readonly",
    "network",
    "mcp",
    "credentials",
    "process_tree",
    "fresh_review",
)


def api():
    from supervisor.workers.boundary import validate_evidence

    return validate_evidence


def record():
    return dict(
        schema_version=1,
        **EXPECTED,
        platform="synthetic",
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
            for name in IDS
        ],
    )


def executed(check):
    check.update(
        executed=True,
        argv=["/synthetic/probe"],
        cwd="/synthetic",
        started_utc="2026-10-06T00:00:00Z",
        ended_utc="2026-10-06T00:00:01Z",
        exit_code=None,
        output_sha256="a" * 64,
        observed="yes",
    )


def test_unknown_exit_and_no_input_mutation():
    data = record()
    executed(data["checks"][0])
    before = copy.deepcopy(data)
    result = api()(data, expected=EXPECTED)
    assert data == before
    assert result == before
    assert result is not data
    assert result["checks"] is not data["checks"]
    assert result["checks"][0]["exit_code"] is None
    assert result["checks"][0]["executed"] is True


@pytest.mark.parametrize(
    "case",
    [
        "bool_version",
        "extra",
        "duplicate",
        "missing",
        "identity",
        "null_enforced",
        "fake_execution",
    ],
)
def test_reject_inconsistent_records(case):
    data = record()
    if case == "bool_version":
        data["schema_version"] = True
    elif case == "extra":
        data["allow_live"] = True
    elif case == "duplicate":
        data["checks"][-1] = copy.deepcopy(data["checks"][0])
    elif case == "missing":
        data["checks"].pop()
    elif case == "identity":
        data["attempt_id"] = "other"
    elif case == "null_enforced":
        data["checks"][0]["enforced"] = None
    else:
        data["checks"][0]["exit_code"] = 0
    with pytest.raises(ValueError):
        api()(data, expected=EXPECTED)


@pytest.mark.parametrize(
    "case", ["bool_exit", "unknown_exit_enforced", "long", "negative", "digest", "bad_date"]
)
def test_executed_failures(case):
    data = record()
    check = data["checks"][0]
    executed(check)
    if case == "bool_exit":
        check["exit_code"] = True
    elif case == "unknown_exit_enforced":
        check["enforced"] = "yes"
    elif case == "long":
        check["ended_utc"] = "2026-10-06T00:02:01Z"
    elif case == "negative":
        check["ended_utc"] = "2026-10-05T23:59:59Z"
    elif case == "digest":
        check["output_sha256"] = "A" * 64
    else:
        check["started_utc"] = "2026-02-30T00:00:00Z"
    with pytest.raises(ValueError):
        api()(data, expected=EXPECTED)


def test_live_always_disabled():
    from supervisor.workers.boundary import require_live_execution

    with pytest.raises(RuntimeError, match="live_execution_disabled"):
        require_live_execution(record(), allow_live=True)


def test_expected_newline_rejected():
    with pytest.raises(ValueError):
        api()(record(), expected={**EXPECTED, "task_id": "M2C1\n"})


def test_consistent_enforced_declaration_is_only_evidence():
    data = record()
    check = data["checks"][0]
    executed(check)
    check.update(enforced="yes", exit_code=0)
    assert api()(data, expected=EXPECTED) == data


def test_negative_exit_preserved():
    data = record()
    executed(data["checks"][0])
    data["checks"][0]["exit_code"] = -15
    assert api()(data, expected=EXPECTED)["checks"][0]["exit_code"] == -15


@pytest.mark.parametrize(
    "expected", [None, [], {**EXPECTED, "extra": "x"}, {**EXPECTED, "worker_id": True}]
)
def test_malformed_expected_rejected(expected):
    with pytest.raises(ValueError):
        api()(record(), expected=expected)


def test_error_does_not_echo_raw_value():
    data = record()
    data["worker_id"] = "PRIVATE_SENTINEL"
    with pytest.raises(ValueError) as error:
        api()(data, expected=EXPECTED)
    assert "PRIVATE_SENTINEL" not in str(error.value)
