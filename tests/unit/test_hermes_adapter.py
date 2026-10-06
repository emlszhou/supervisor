"""Integration and unit tests for ``supervisor.agents.hermes.HermesAdapter``.

These tests exercise the Adapter against a real ``ProcessRunner`` running
the synthetic ``tests/fixtures/hermes_cli.py``. The fixture is a
deterministic stdlib-only mock; no network, model, or Hermes CLI is
invoked. Each individual fixture-driven test must complete in <3 s wall
and emit <64 KiB output, per the M2-B contract.

Tests are grouped by failure category:
  - Protocol-level tests operate on a synthetic ``ProcessResult`` directly.
  - Integration-level tests run the fixture via ``ProcessRunner.run`` and
    parse the captured stdout/stderr.

The protected test_contract.py (in ``handoffs/M2B/v1/task-bundle/tests``)
is the authoritative gate; this file supplements with real-process
integration so that the Adapter cannot pass by only mirroring the
protected tests' fixture data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from supervisor.agents.hermes import HermesAdapter
from supervisor.workers.process import ProcessRequest, ProcessResult, ProcessRunner

# --- common identity --------------------------------------------------------

EXPECTED = dict(
    task_id="M2B",
    run_id="run-1",
    attempt_id="attempt-1",
    role="implementer",
    provider="minimax-cn",
    model="MiniMax-M3",
)

FIXTURE_PATH = (Path(__file__).resolve().parent.parent / "fixtures" / "hermes_cli.py").resolve()


def _process(events, **changes) -> ProcessResult:
    fields = dict(
        status="completed",
        exit_code=0,
        stdout=("\n".join(json.dumps(e) for e in events)).encode(),
        stderr=b"",
        duration_seconds=0.1,
        truncated=False,
        tree_cleanup_confirmed=True,
        error=None,
    )
    fields.update(changes)
    return ProcessResult(**fields)


def _good_init() -> dict:
    return dict(type="system", subtype="init", model="MiniMax-M3", session_id="session-1")


def _good_text() -> dict:
    return dict(type="text", text="OK")


def _good_result() -> dict:
    return dict(type="result", session_id="session-1", exit_code=0, text="OK")


# --- build_request always disabled ------------------------------------------


def test_build_request_raises_live_disabled(tmp_path):
    with pytest.raises(RuntimeError, match="live_execution_disabled"):
        HermesAdapter().build_request(EXPECTED, tmp_path)


def test_build_request_does_not_inspect_env(tmp_path, monkeypatch):
    """No environment flag, env var, or CLI switch can enable real Hermes."""
    # Even if the caller pretends to enable live mode, the Adapter must reject.
    monkeypatch.setenv("HERMES_ADAPTER_LIVE", "1")
    with pytest.raises(RuntimeError, match="live_execution_disabled"):
        HermesAdapter().build_request({**EXPECTED, "enable_live": "true"}, tmp_path)


# --- process-state gate -----------------------------------------------------


def test_parse_result_rejects_nonzero_exit():
    result = HermesAdapter().parse_result(
        _process([_good_init(), _good_text(), _good_result()], exit_code=7),
        expected=EXPECTED,
    )
    assert result.status == "failed"


def test_parse_result_rejects_nonempty_stderr():
    result = HermesAdapter().parse_result(
        _process(
            [_good_init(), _good_text(), _good_result()],
            stderr=b"Primary auth failed",
        ),
        expected=EXPECTED,
    )
    assert result.status == "failed"


def test_parse_result_rejects_truncated():
    result = HermesAdapter().parse_result(
        _process(
            [_good_init(), _good_text(), _good_result()],
            truncated=True,
        ),
        expected=EXPECTED,
    )
    assert result.status == "failed"


def test_parse_result_rejects_tree_cleanup_unknown():
    result = HermesAdapter().parse_result(
        _process(
            [_good_init(), _good_text(), _good_result()],
            tree_cleanup_confirmed=None,
        ),
        expected=EXPECTED,
    )
    assert result.status == "failed"


def test_parse_result_rejects_invalid_utf8():
    result = HermesAdapter().parse_result(
        _process(
            [_good_init(), _good_text(), _good_result()],
            stdout=b"\xff\xfe",
        ),
        expected=EXPECTED,
    )
    assert result.status == "failed"


def test_parse_result_rejects_oversize_stdout():
    big = b"x" * 65537
    result = HermesAdapter().parse_result(
        _process(
            [_good_init(), _good_text(), _good_result()],
            stdout=big,
        ),
        expected=EXPECTED,
    )
    assert result.status == "failed"


@pytest.mark.parametrize("state", ["timed_out", "cancelled", "output_limit", "environment_failure"])
def test_parse_result_preserves_worker_status(state):
    result = HermesAdapter().parse_result(
        _process(
            [_good_init(), _good_text(), _good_result()],
            status=state,
            exit_code=None,
            stdout=b"bad",
        ),
        expected=EXPECTED,
    )
    assert result.status == state
    assert result.exit_code is None


# --- protocol-level gate ----------------------------------------------------


def test_parse_result_success_identity():
    result = HermesAdapter().parse_result(
        _process([_good_init(), _good_text(), _good_result()]),
        expected=EXPECTED,
    )
    assert result.status == "completed"
    assert result.session_id == "session-1"
    assert result.attempt_id == EXPECTED["attempt_id"]
    assert result.provider == EXPECTED["provider"]
    assert result.model == EXPECTED["model"]
    assert result.usage is None
    assert result.artifacts == []


def test_parse_result_ignores_terminal_text_when_no_tokens():
    """When tokens are absent, usage stays None; the text body is preserved as summary."""
    result = HermesAdapter().parse_result(
        _process([_good_init(), _good_text(), _good_result()]),
        expected=EXPECTED,
    )
    assert result.status == "completed"
    assert result.usage is None


def test_parse_result_rejects_init_model_mismatch():
    init = _good_init()
    init["model"] = "other-model"
    result = HermesAdapter().parse_result(
        _process([init, _good_text(), _good_result()]),
        expected=EXPECTED,
    )
    assert result.status == "failed"


def test_parse_result_rejects_unknown_event_type():
    events = [_good_init(), dict(type="tool_use", name="shell"), _good_text(), _good_result()]
    result = HermesAdapter().parse_result(_process(events), expected=EXPECTED)
    assert result.status == "failed"


def test_parse_result_rejects_terminal_before_init():
    # result before init: explicitly tested by the protocol gate
    events = [_good_result(), _good_init(), _good_text()]
    result = HermesAdapter().parse_result(_process(events), expected=EXPECTED)
    assert result.status == "failed"


def test_parse_result_rejects_event_after_terminal():
    events = [_good_init(), _good_text(), _good_result(), _good_text()]
    result = HermesAdapter().parse_result(_process(events), expected=EXPECTED)
    assert result.status == "failed"


def test_parse_result_rejects_result_nonzero_exit_code():
    res = _good_result()
    res["exit_code"] = 1
    result = HermesAdapter().parse_result(
        _process([_good_init(), _good_text(), res]),
        expected=EXPECTED,
    )
    assert result.status == "failed"


def test_parse_result_rejects_bool_exit_code():
    res = _good_result()
    res["exit_code"] = False
    result = HermesAdapter().parse_result(
        _process([_good_init(), _good_text(), res]),
        expected=EXPECTED,
    )
    assert result.status == "failed"


def test_parse_result_rejects_duplicate_keys():
    payload = b'{"type":"system","type":"system"}'
    result = HermesAdapter().parse_result(
        _process([], stdout=payload),
        expected=EXPECTED,
    )
    assert result.status == "failed"


def test_parse_result_rejects_nan_timestamp():
    payload = (
        b'{"type":"system","subtype":"init","model":"MiniMax-M3","session_id":"s","timestamp":NaN}'
    )
    result = HermesAdapter().parse_result(
        _process([], stdout=payload),
        expected=EXPECTED,
    )
    assert result.status == "failed"


def test_parse_result_summary_4096_passes_4097_fails():
    base = [_good_init(), _good_text()]
    at_4096 = _process(base + [dict(_good_result(), text="x" * 4096)])
    at_4097 = _process(base + [dict(_good_result(), text="x" * 4097)])
    assert HermesAdapter().parse_result(at_4096, expected=EXPECTED).status == "completed"
    assert HermesAdapter().parse_result(at_4097, expected=EXPECTED).status == "failed"


def test_parse_result_rejects_missing_terminal():
    result = HermesAdapter().parse_result(
        _process([_good_init(), _good_text()]),
        expected=EXPECTED,
    )
    assert result.status == "failed"


def test_parse_result_rejects_wrong_provider():
    with pytest.raises(ValueError):
        HermesAdapter().parse_result(
            _process([_good_init(), _good_text(), _good_result()]),
            expected={**EXPECTED, "provider": "other"},
        )


def test_parse_result_rejects_wrong_model():
    with pytest.raises(ValueError):
        HermesAdapter().parse_result(
            _process([_good_init(), _good_text(), _good_result()]),
            expected={**EXPECTED, "model": "other-model"},
        )


def test_parse_result_rejects_invalid_role():
    with pytest.raises(ValueError):
        HermesAdapter().parse_result(
            _process([_good_init(), _good_text(), _good_result()]),
            expected={**EXPECTED, "role": "hacker"},
        )


# --- usage mapping ----------------------------------------------------------


def test_usage_input_output_only():
    res = _good_result()
    res["tokens"] = dict(input=7, output=2, total=25481, cache_read=25472)
    result = HermesAdapter().parse_result(
        _process([_good_init(), _good_text(), res]), expected=EXPECTED
    )
    assert result.status == "completed"
    assert result.usage == dict(input_tokens=7, output_tokens=2)


def test_usage_rejects_bool_input():
    res = _good_result()
    res["tokens"] = dict(input=True, output=1)
    result = HermesAdapter().parse_result(
        _process([_good_init(), _good_text(), res]), expected=EXPECTED
    )
    assert result.status == "failed"


def test_usage_rejects_negative_input():
    res = _good_result()
    res["tokens"] = dict(input=-1, output=1)
    result = HermesAdapter().parse_result(
        _process([_good_init(), _good_text(), res]), expected=EXPECTED
    )
    assert result.status == "failed"


def test_usage_rejects_missing_output():
    res = _good_result()
    res["tokens"] = dict(input=1)  # no output
    result = HermesAdapter().parse_result(
        _process([_good_init(), _good_text(), res]), expected=EXPECTED
    )
    assert result.status == "failed"


# --- integration: real ProcessRunner + fixture ------------------------------


def _run_fixture(
    scenario: str, *, timeout=2.0, max_output=65536, require_cleanup=False
) -> ProcessResult:
    req = ProcessRequest(
        argv=(sys.executable, str(FIXTURE_PATH), "--scenario", scenario),
        cwd=Path.cwd(),
        workspace_root=Path.cwd(),
        env={"PATH": "/usr/bin:/bin", "HOME": str(Path.cwd())},
        timeout_seconds=timeout,
        cancel_grace_seconds=0.2,
        max_output_bytes=max_output,
        attempt_id=EXPECTED["attempt_id"],
        require_tree_cleanup=require_cleanup,
    )
    return ProcessRunner().run(req)


def test_integration_success_scenario():
    """The success fixture with cleanup-required must complete; the Adapter
    must accept it. The Worker may report cleanup-confirmed or not depending
    on the runtime; when cleanup is required and reported as True, the
    Adapter should accept the parsed result as ``completed``; when the
    Worker cannot confirm cleanup on this runtime, the Adapter must refuse.
    """
    proc = _run_fixture("success", require_cleanup=True, timeout=2.0)
    assert proc.exit_code == 0
    assert proc.stderr == b""
    # On environments without /proc or ps, the Worker may report
    # tree_cleanup_confirmed=None even with require_cleanup=True.
    result = HermesAdapter().parse_result(proc, expected=EXPECTED)
    if proc.tree_cleanup_confirmed is True:
        assert result.status == "completed"
        assert result.session_id == "session-1"
    else:
        assert result.status == "failed"
        assert "cleanup" in (result.error or "").lower()


def test_integration_nonzero_scenario():
    proc = _run_fixture("nonzero", require_cleanup=False)
    assert proc.exit_code == 7
    result = HermesAdapter().parse_result(proc, expected=EXPECTED)
    assert result.status == "failed"


def test_integration_malformed_scenario():
    proc = _run_fixture("malformed", require_cleanup=False)
    assert proc.exit_code == 0  # the fixture exits 0 even with malformed stdout
    result = HermesAdapter().parse_result(proc, expected=EXPECTED)
    assert result.status == "failed"


def test_integration_wrong_session_scenario():
    proc = _run_fixture("wrong_session", require_cleanup=False)
    assert proc.exit_code == 0
    result = HermesAdapter().parse_result(proc, expected=EXPECTED)
    assert result.status == "failed"


def test_integration_fallback_scenario_rejected_for_stderr():
    proc = _run_fixture("fallback", require_cleanup=False)
    assert proc.exit_code == 0
    assert proc.stderr  # Adapter must reject ANY stderr
    result = HermesAdapter().parse_result(proc, expected=EXPECTED)
    assert result.status == "failed"


def test_integration_slow_scenario_timeout():
    proc = _run_fixture("slow", timeout=0.5, require_cleanup=False)
    assert proc.status == "timed_out"
    result = HermesAdapter().parse_result(proc, expected=EXPECTED)
    assert result.status == "timed_out"


def test_integration_oversized_summary():
    proc = _run_fixture("oversized", require_cleanup=False)
    assert proc.exit_code == 0
    result = HermesAdapter().parse_result(proc, expected=EXPECTED)
    assert result.status == "failed"


def test_integration_with_tree_cleanup_required():
    """When cleanup is required but the Worker cannot confirm it (typical on
    macOS dev boxes without /proc + ps), the Adapter must refuse. This is
    the contract's defensive posture: process-state truth wins over stdout.
    """
    proc = _run_fixture("success", require_cleanup=True, timeout=2.0)
    # On Linux dev environments with /proc + ps available, cleanup may be
    # confirmed; the Adapter then accepts and parses.
    if proc.tree_cleanup_confirmed is True:
        result = HermesAdapter().parse_result(proc, expected=EXPECTED)
        assert result.status == "completed"
    else:
        result = HermesAdapter().parse_result(proc, expected=EXPECTED)
        assert result.status == "failed"
        assert "cleanup" in (result.error or "").lower()
