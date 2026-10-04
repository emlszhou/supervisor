"""Unit tests for agents.mock.MockAdapter."""

from __future__ import annotations

import dataclasses

import pytest

from supervisor.agents.mock import MockAdapter

_CONTEXT = {
    "task_id": "M0-unit",
    "run_id": "unit-run",
    "attempt_id": "unit-attempt",
    "role": "implementer",
    "provider": "mock",
}


class TestScenarioNames:
    """MockAdapter only accepts documented scenarios."""

    def test_unknown_scenario_raises(self):
        with pytest.raises(ValueError, match="unknown mock scenario"):
            MockAdapter(scenario="bogus")

    @pytest.mark.parametrize(
        "name",
        [
            "success",
            "nonzero",
            "timeout",
            "malformed",
            "wrong_identity",
        ],
    )
    def test_known_scenario_accepted(self, name):
        adapter = MockAdapter(scenario=name)
        assert adapter.scenario == name


class TestBuildRequest:
    """Mock request uses absolute python and explicit minimal env."""

    def test_first_argv_is_absolute_python(self, tmp_path):
        req = MockAdapter("success").build_request(_CONTEXT, tmp_path)
        import os

        assert os.path.isabs(req.argv[0])

    def test_workspace_matches(self, tmp_path):
        req = MockAdapter("success").build_request(_CONTEXT, tmp_path)
        assert req.cwd == tmp_path
        assert req.workspace_root == tmp_path

    def test_env_is_explicit_minimal(self, tmp_path):
        req = MockAdapter("success").build_request(_CONTEXT, tmp_path)
        # Only allowlisted keys
        assert set(req.env.keys()) <= {"PATH", "HOME"}
        # No host secrets can leak through

    def test_attempt_id_from_context(self, tmp_path):
        req = MockAdapter("success").build_request(_CONTEXT, tmp_path)
        assert req.attempt_id == _CONTEXT["attempt_id"]


class TestEndToEnd:
    """Mock round-trip through ProcessRunner + parse_agent_result."""

    def test_success_returns_completed(self, tmp_path):
        from supervisor.workers.process import ProcessRunner

        adapter = MockAdapter("success")
        req = adapter.build_request(_CONTEXT, tmp_path)
        result = ProcessRunner().run(req)
        parsed = adapter.parse_result(result, expected=_CONTEXT)
        assert parsed.status == "completed"
        assert parsed.error is None

    def test_nonzero_returns_failed(self, tmp_path):
        from supervisor.workers.process import ProcessRunner

        adapter = MockAdapter("nonzero")
        req = adapter.build_request(_CONTEXT, tmp_path)
        result = ProcessRunner().run(req)
        assert result.status == "failed"
        assert result.exit_code == 7

    def test_malformed_returns_failed(self, tmp_path):
        from supervisor.workers.process import ProcessRunner

        adapter = MockAdapter("malformed")
        req = adapter.build_request(_CONTEXT, tmp_path)
        result = ProcessRunner().run(req)
        parsed = adapter.parse_result(result, expected=_CONTEXT)
        assert parsed.status == "failed"

    def test_wrong_identity_returns_failed(self, tmp_path):
        from supervisor.workers.process import ProcessRunner

        adapter = MockAdapter("wrong_identity")
        req = adapter.build_request(_CONTEXT, tmp_path)
        result = ProcessRunner().run(req)
        parsed = adapter.parse_result(result, expected=_CONTEXT)
        assert parsed.status == "failed"
        assert "attempt_id" in (parsed.error or "") or "mismatch" in (parsed.error or "")

    def test_timeout_returns_timed_out(self, tmp_path):
        from supervisor.workers.process import ProcessRunner

        adapter = MockAdapter("timeout")
        req = adapter.build_request(_CONTEXT, tmp_path)
        req = dataclasses.replace(req, timeout_seconds=0.15)
        result = ProcessRunner().run(req)
        assert result.status == "timed_out"
