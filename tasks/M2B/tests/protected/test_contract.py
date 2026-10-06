"""External behavioral checks for the offline Hermes adapter contract."""

import json
from pathlib import Path

import pytest

from supervisor.workers.process import ProcessResult

EXPECTED = dict(
    task_id="M2B",
    run_id="run-1",
    attempt_id="attempt-1",
    role="implementer",
    provider="minimax-cn",
    model="MiniMax-M3",
)


def adapter():
    from supervisor.agents.hermes import HermesAdapter

    return HermesAdapter()


def output():
    return [
        dict(type="system", subtype="init", model="MiniMax-M3", session_id="session-1"),
        dict(type="text", text="OK"),
        dict(type="result", session_id="session-1", exit_code=0, text="OK"),
    ]


def process(events=None, **changes):
    fields = dict(
        status="completed",
        exit_code=0,
        stdout=(
            "\n".join(json.dumps(e) for e in (output() if events is None else events))
        ).encode(),
        stderr=b"",
        duration_seconds=0.1,
        truncated=False,
        tree_cleanup_confirmed=True,
        error=None,
    )
    fields.update(changes)
    return ProcessResult(**fields)


def test_live_disabled(tmp_path):
    with pytest.raises(RuntimeError, match="live_execution_disabled"):
        adapter().build_request(EXPECTED, Path(tmp_path))


def test_success_identity_and_unknown_usage():
    result = adapter().parse_result(process(), expected=EXPECTED)
    assert result.status == "completed"
    assert result.session_id == "session-1"
    assert result.attempt_id == EXPECTED["attempt_id"]
    assert result.provider == EXPECTED["provider"]
    assert result.model == EXPECTED["model"]
    assert result.usage is None
    assert result.artifacts == []


@pytest.mark.parametrize(
    "changes",
    [
        dict(exit_code=7),
        dict(exit_code=None),
        dict(exit_code=True),
        dict(stderr=b"Primary auth failed - switching to fallback"),
        dict(truncated=True),
        dict(tree_cleanup_confirmed=None),
        dict(tree_cleanup_confirmed=False),
        dict(stdout=b"\xff"),
        dict(stdout=b"x" * 65537),
    ],
)
def test_process_cannot_claim_success(changes):
    assert adapter().parse_result(process(**changes), expected=EXPECTED).status == "failed"


@pytest.mark.parametrize("state", ["timed_out", "cancelled", "output_limit", "environment_failure"])
def test_preserve_worker_failure(state):
    result = adapter().parse_result(
        process(status=state, exit_code=None, stdout=b"bad"), expected=EXPECTED
    )
    assert result.status == state
    assert result.exit_code is None


@pytest.mark.parametrize(
    "mutation", ["model", "session", "duplicate", "bool", "tool", "usage", "extra"]
)
def test_protocol_failures(mutation):
    events = output()
    if mutation == "model":
        events[0]["model"] = "other"
    elif mutation == "session":
        events[-1]["session_id"] = "other"
    elif mutation == "duplicate":
        events.append(events[-1].copy())
    elif mutation == "bool":
        events[-1]["exit_code"] = False
    elif mutation == "tool":
        events.insert(1, dict(type="tool_use", name="shell"))
    elif mutation == "usage":
        events[-1]["tokens"] = dict(input=True, output=1)
    else:
        events[-1]["unknown"] = "secret"
    result = adapter().parse_result(process(events), expected=EXPECTED)
    assert result.status == "failed"
    assert "secret" not in (result.error or "")


def test_usage_mapping():
    events = output()
    events[-1]["tokens"] = dict(input=7, output=2, total=25481, cache_read=25472)
    result = adapter().parse_result(process(events), expected=EXPECTED)
    assert result.status == "completed"
    assert result.usage == dict(input_tokens=7, output_tokens=2)
