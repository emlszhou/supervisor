"""Unit tests for agents.base.parse_agent_result and AgentResult."""

from __future__ import annotations

import json

import pytest

from supervisor.agents.base import parse_agent_result
from supervisor.workers.process import ProcessResult

_BASE_EXPECTED = {
    "task_id": "M0-unit",
    "run_id": "unit-run",
    "attempt_id": "unit-attempt",
    "role": "implementer",
    "provider": "mock",
}


def _ok_process(stdout: bytes = b"", exit_code: int = 0, truncated: bool = False) -> ProcessResult:
    return ProcessResult(
        status="completed",
        exit_code=exit_code,
        stdout=stdout,
        stderr=b"",
        duration_seconds=0.01,
        truncated=truncated,
        tree_cleanup_confirmed=None,
        error=None,
    )


def _failed_process(status: str = "failed", exit_code: int | None = 7) -> ProcessResult:
    return ProcessResult(
        status=status,
        exit_code=exit_code,
        stdout=b"some output",
        stderr=b"",
        duration_seconds=0.01,
        truncated=False,
        tree_cleanup_confirmed=None,
        error="process failed",
    )


def _complete_payload() -> dict:
    """Schema-valid completed payload."""
    return {
        "schema_version": 1,
        "task_id": _BASE_EXPECTED["task_id"],
        "run_id": _BASE_EXPECTED["run_id"],
        "attempt_id": _BASE_EXPECTED["attempt_id"],
        "role": _BASE_EXPECTED["role"],
        "provider": _BASE_EXPECTED["provider"],
        "model": None,
        "session_id": "session-xyz",
        "status": "completed",
        "exit_code": 0,
        "summary": "",
        "error": None,
        "usage": None,
        "artifacts": [],
        "truncated": False,
    }


class TestProcessStatusGating:
    """Parser defers to actual process status, never overrides with stdout lies."""

    def test_actual_failed_keeps_failed(self):
        result = parse_agent_result(_failed_process("failed", 7), expected=_BASE_EXPECTED)
        assert result.status == "failed"
        assert result.exit_code == 7

    def test_actual_timed_out_keeps_timed_out(self):
        result = parse_agent_result(_failed_process("timed_out", None), expected=_BASE_EXPECTED)
        assert result.status == "timed_out"

    def test_actual_cancelled_keeps_cancelled(self):
        result = parse_agent_result(_failed_process("cancelled", None), expected=_BASE_EXPECTED)
        assert result.status == "cancelled"

    def test_actual_output_limit_keeps_output_limit(self):
        result = parse_agent_result(_failed_process("output_limit", None), expected=_BASE_EXPECTED)
        assert result.status == "output_limit"

    def test_actual_truncated_overrides_completed_claim(self):
        # Child prints "completed" but process was actually truncated
        payload = _complete_payload()
        process = _ok_process(json.dumps(payload).encode(), truncated=True)
        result = parse_agent_result(process, expected=_BASE_EXPECTED)
        assert result.status == "failed"
        assert result.exit_code == 0

    def test_actual_nonzero_overrides_completed_claim(self):
        payload = _complete_payload()
        process = _ok_process(json.dumps(payload).encode(), exit_code=7)
        result = parse_agent_result(process, expected=_BASE_EXPECTED)
        assert result.status == "failed"
        assert result.exit_code == 7


class TestSchemaValidation:
    """Parser rejects malformed / unsafe JSON strictly."""

    def test_invalid_json_returns_failed(self):
        process = _ok_process(b"not valid json")
        result = parse_agent_result(process, expected=_BASE_EXPECTED)
        assert result.status == "failed"
        assert result.error is not None

    def test_json_not_object_returns_failed(self):
        process = _ok_process(b"[1, 2, 3]")
        result = parse_agent_result(process, expected=_BASE_EXPECTED)
        assert result.status == "failed"

    def test_unknown_top_level_field_returns_failed(self):
        payload = _complete_payload()
        payload["permission_override"] = "full-access"
        process = _ok_process(json.dumps(payload).encode())
        result = parse_agent_result(process, expected=_BASE_EXPECTED)
        assert result.status == "failed"

    def test_missing_required_field_returns_failed(self):
        payload = _complete_payload()
        del payload["summary"]
        process = _ok_process(json.dumps(payload).encode())
        result = parse_agent_result(process, expected=_BASE_EXPECTED)
        assert result.status == "failed"

    def test_wrong_schema_version_returns_failed(self):
        payload = _complete_payload()
        payload["schema_version"] = 2
        process = _ok_process(json.dumps(payload).encode())
        result = parse_agent_result(process, expected=_BASE_EXPECTED)
        assert result.status == "failed"

    def test_session_id_none_for_completed_returns_failed(self):
        payload = _complete_payload()
        payload["session_id"] = None
        process = _ok_process(json.dumps(payload).encode())
        result = parse_agent_result(process, expected=_BASE_EXPECTED)
        assert result.status == "failed"

    def test_declared_truncated_true_returns_failed(self):
        payload = _complete_payload()
        payload["truncated"] = True
        process = _ok_process(json.dumps(payload).encode())
        result = parse_agent_result(process, expected=_BASE_EXPECTED)
        assert result.status == "failed"

    def test_declared_exit_nonzero_returns_failed(self):
        payload = _complete_payload()
        payload["exit_code"] = 7
        process = _ok_process(json.dumps(payload).encode())
        result = parse_agent_result(process, expected=_BASE_EXPECTED)
        assert result.status == "failed"

    def test_incomplete_payload_with_unknown_field_returns_failed(self):
        # Even if status=completed, unknown field trips the gate
        payload = _complete_payload()
        del payload["model"]
        del payload["summary"]
        payload["unexpected"] = True
        payload["status"] = "failed"
        process = _ok_process(json.dumps(payload).encode())
        result = parse_agent_result(process, expected=_BASE_EXPECTED)
        assert result.status == "failed"


class TestIdentityBinding:
    """Output identity must match expected; cannot override."""

    def test_task_id_mismatch_returns_failed(self):
        payload = _complete_payload()
        payload["task_id"] = "different"
        process = _ok_process(json.dumps(payload).encode())
        result = parse_agent_result(process, expected=_BASE_EXPECTED)
        assert result.status == "failed"

    def test_run_id_mismatch_returns_failed(self):
        payload = _complete_payload()
        payload["run_id"] = "different"
        process = _ok_process(json.dumps(payload).encode())
        result = parse_agent_result(process, expected=_BASE_EXPECTED)
        assert result.status == "failed"

    def test_attempt_id_mismatch_returns_failed(self):
        payload = _complete_payload()
        payload["attempt_id"] = "different"
        process = _ok_process(json.dumps(payload).encode())
        result = parse_agent_result(process, expected=_BASE_EXPECTED)
        assert result.status == "failed"

    def test_role_mismatch_returns_failed(self):
        payload = _complete_payload()
        payload["role"] = "reviewer"
        process = _ok_process(json.dumps(payload).encode())
        result = parse_agent_result(process, expected=_BASE_EXPECTED)
        assert result.status == "failed"

    def test_provider_mismatch_returns_failed(self):
        payload = _complete_payload()
        payload["provider"] = "anthropic"
        process = _ok_process(json.dumps(payload).encode())
        result = parse_agent_result(process, expected=_BASE_EXPECTED)
        assert result.status == "failed"


class TestArtifactPathValidation:
    """Artifact paths must be canonical relative paths."""

    @pytest.mark.parametrize(
        "bad_path",
        ["..", "../escape", "./foo", "foo//bar", "foo/", "/abs", "a\\b"],
    )
    def test_malformed_path_returns_failed(self, bad_path):
        payload = _complete_payload()
        payload["artifacts"] = [{"path": bad_path, "sha256": "0" * 64}]
        process = _ok_process(json.dumps(payload).encode())
        result = parse_agent_result(process, expected=_BASE_EXPECTED)
        assert result.status == "failed"

    def test_bad_hash_format_returns_failed(self):
        payload = _complete_payload()
        payload["artifacts"] = [{"path": "ok.txt", "sha256": "not-a-hash"}]
        process = _ok_process(json.dumps(payload).encode())
        result = parse_agent_result(process, expected=_BASE_EXPECTED)
        assert result.status == "failed"

    def test_artifact_nonstring_path_returns_failed(self):
        payload = _complete_payload()
        payload["artifacts"] = [{"path": 12345, "sha256": "0" * 64}]
        process = _ok_process(json.dumps(payload).encode())
        result = parse_agent_result(process, expected=_BASE_EXPECTED)
        assert result.status == "failed"

    def test_canonical_path_accepted(self):
        payload = _complete_payload()
        payload["artifacts"] = [{"path": "out/result.txt", "sha256": "a" * 64}]
        process = _ok_process(json.dumps(payload).encode())
        result = parse_agent_result(process, expected=_BASE_EXPECTED)
        assert result.status == "completed"


class TestUsageValidation:
    """Usage fields enforce types and non-negative integers."""

    def test_usage_negative_tokens_returns_failed(self):
        payload = _complete_payload()
        payload["usage"] = {"input_tokens": -1, "output_tokens": 5}
        process = _ok_process(json.dumps(payload).encode())
        result = parse_agent_result(process, expected=_BASE_EXPECTED)
        assert result.status == "failed"

    def test_usage_wrong_type_returns_failed(self):
        payload = _complete_payload()
        payload["usage"] = {"input_tokens": "5", "output_tokens": 5}
        process = _ok_process(json.dumps(payload).encode())
        result = parse_agent_result(process, expected=_BASE_EXPECTED)
        assert result.status == "failed"

    def test_usage_unknown_field_returns_failed(self):
        payload = _complete_payload()
        payload["usage"] = {
            "input_tokens": 5,
            "output_tokens": 5,
            "model_internal": "x",
        }
        process = _ok_process(json.dumps(payload).encode())
        result = parse_agent_result(process, expected=_BASE_EXPECTED)
        assert result.status == "failed"


class TestErrorEchoSafety:
    """Errors must not echo raw stdout verbatim."""

    def test_error_does_not_echo_stdout(self):
        process = _ok_process(b'super-secret-prompt "hello world"')
        result = parse_agent_result(process, expected=_BASE_EXPECTED)
        assert result.status == "failed"
        assert result.error is not None
        assert b"super-secret" not in result.error.encode()
        assert b"hello world" not in result.error.encode()


class TestCompletedPath:
    """Valid payload returns completed with all expected fields."""

    def test_valid_payload_returns_completed(self):
        payload = _complete_payload()
        process = _ok_process(json.dumps(payload).encode())
        result = parse_agent_result(process, expected=_BASE_EXPECTED)
        assert result.status == "completed"
        assert result.exit_code == 0
        assert result.session_id == "session-xyz"
        assert result.task_id == _BASE_EXPECTED["task_id"]
        assert result.error is None

    def test_to_dict_satisfies_schema(self):
        payload = _complete_payload()
        process = _ok_process(json.dumps(payload).encode())
        result = parse_agent_result(process, expected=_BASE_EXPECTED)
        data = result.to_dict()
        # Required schema fields all present
        for key in (
            "schema_version",
            "task_id",
            "run_id",
            "attempt_id",
            "role",
            "provider",
            "model",
            "session_id",
            "status",
            "exit_code",
            "summary",
            "error",
            "usage",
            "artifacts",
            "truncated",
        ):
            assert key in data
        # No raw stdout reflected
        assert "stdout" not in data
