"""Unit tests for workers.process.ProcessRunner."""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

from supervisor.workers.process import (
    ProcessRequest,
    ProcessRunner,
)


def _req(workspace: Path, code: str, **overrides) -> ProcessRequest:
    """Build a valid ProcessRequest that runs python -c code."""
    fields = {
        "argv": (sys.executable, "-c", code),
        "cwd": workspace,
        "workspace_root": workspace,
        "env": {},
        "timeout_seconds": 5.0,
        "cancel_grace_seconds": 0.2,
        "max_output_bytes": 4096,
        "attempt_id": "M0-attempt",
        "require_tree_cleanup": False,
    }
    fields.update(overrides)
    return ProcessRequest(**fields)


class TestProcessRequestValidation:
    """Validation rejects bad input before any subprocess is launched."""

    def test_empty_argv_raises(self, tmp_path):
        with pytest.raises(ValueError, match="argv must not be empty"):
            ProcessRunner().run(
                ProcessRequest(argv=(), cwd=tmp_path, workspace_root=tmp_path, env={})
            )

    def test_zero_timeout_raises(self, tmp_path):
        with pytest.raises(ValueError, match="must be a positive finite number"):
            ProcessRunner().run(_req(tmp_path, "pass", timeout_seconds=0))

    def test_nan_timeout_raises(self, tmp_path):
        with pytest.raises(ValueError, match="must be a positive finite number"):
            ProcessRunner().run(_req(tmp_path, "pass", timeout_seconds=float("nan")))

    def test_bool_max_output_raises(self, tmp_path):
        with pytest.raises(ValueError, match="must be a positive integer"):
            ProcessRunner().run(_req(tmp_path, "pass", max_output_bytes=True))

    def test_relative_executable_raises(self, tmp_path):
        with pytest.raises(ValueError, match="absolute path"):
            import dataclasses

            req = _req(tmp_path, "pass")
            req = dataclasses.replace(req, argv=("python", "-c", "pass"))
            ProcessRunner().run(req)


class TestNormalExecution:
    """Standard completed and failed paths."""

    def test_completed_captures_stdout(self, tmp_path):
        result = ProcessRunner().run(_req(tmp_path, "print('hello')"))
        assert result.status == "completed"
        assert result.exit_code == 0
        assert result.stdout.strip() == b"hello"
        assert result.error is None

    def test_completed_captures_both_streams(self, tmp_path):
        code = "import sys; print('out'); print('err', file=sys.stderr); sys.exit(0)"
        result = ProcessRunner().run(_req(tmp_path, code))
        assert result.status == "completed"
        assert b"out" in result.stdout
        assert b"err" in result.stderr

    def test_failed_preserves_exit_code(self, tmp_path):
        code = "import sys; print('failed'); sys.exit(7)"
        result = ProcessRunner().run(_req(tmp_path, code))
        assert result.status == "failed"
        assert result.exit_code == 7
        assert result.error is not None

    def test_arguments_are_literal_no_shell(self, tmp_path):
        # Shell metas must pass through literally, not execute
        code = "import sys; arg = sys.argv[1]; assert arg == 'a b ; echo INJECTED'; print('ok')"
        result = ProcessRunner().run(
            _req(tmp_path, code, argv=(sys.executable, "-c", code, "a b ; echo INJECTED"))
        )
        assert result.status == "completed"
        assert b"INJECTED" not in result.stdout


class TestEnvironment:
    """Subprocess env is explicit, never inherited."""

    def test_env_not_inherited(self, tmp_path, monkeypatch):
        monkeypatch.setenv("M0_HOST_SECRET_SENTINEL", "non-production-private")
        code = "import os, json; print(json.dumps(dict(os.environ)))"
        result = ProcessRunner().run(_req(tmp_path, code, env={"M0_OK": "yes"}))
        assert result.status == "completed"
        import json as _json

        env_seen = _json.loads(result.stdout)
        assert env_seen.get("M0_OK") == "yes"
        assert "M0_HOST_SECRET_SENTINEL" not in env_seen


class TestEnvironmentFailures:
    """environment_failure for missing prerequisites, no subprocess started."""

    def test_missing_executable(self, tmp_path):
        import dataclasses

        req = _req(tmp_path, "pass")
        req = dataclasses.replace(req, argv=("/nonexistent/binary",))
        result = ProcessRunner().run(req)
        assert result.status == "environment_failure"
        assert result.exit_code is None

    def test_missing_cwd(self, tmp_path):
        bad = tmp_path / "missing"
        req = _req(tmp_path, "pass", cwd=bad)
        result = ProcessRunner().run(req)
        assert result.status == "environment_failure"


class TestTimeoutAndCancel:
    """Wall timeout and cancellation enforce bound on duration."""

    def test_wall_timeout_returns_timed_out(self, tmp_path):
        result = ProcessRunner().run(
            _req(tmp_path, "import time; time.sleep(30)", timeout_seconds=0.15)
        )
        assert result.status == "timed_out"
        assert result.exit_code != 0 or result.exit_code is None
        assert result.error is not None

    def test_cancel_running_process(self, tmp_path):
        cancel = threading.Event()
        timer = threading.Timer(0.15, cancel.set)
        timer.start()
        try:
            result = ProcessRunner().run(
                _req(tmp_path, "import time; time.sleep(30)"),
                cancel_event=cancel,
            )
        finally:
            timer.cancel()
        assert result.status == "cancelled"
        assert result.error is not None

    def test_precancelled_does_not_start(self, tmp_path):
        cancel = threading.Event()
        cancel.set()
        result = ProcessRunner().run(
            _req(tmp_path, "print('should not run')"),
            cancel_event=cancel,
        )
        assert result.status == "cancelled"
        assert result.stdout == b""


class TestOutputLimit:
    """Output budget enforced in real time, terminates on flood."""

    def test_output_limit_truncates(self, tmp_path):
        code = "import os, time; os.write(1, b'x' * 65536); time.sleep(2)"
        result = ProcessRunner().run(_req(tmp_path, code, max_output_bytes=64, timeout_seconds=1.0))
        assert result.status == "output_limit"
        assert result.truncated is True
        assert len(result.stdout) + len(result.stderr) <= 64

    def test_two_stream_flood_does_not_deadlock(self, tmp_path):
        code = (
            "import os, threading, time; "
            "t = threading.Thread(target=lambda: ["
            "    os.write(1, b'o' * 1024) for _ in range(2000)"
            "]); "
            "s = threading.Thread(target=lambda: ["
            "    os.write(2, b'e' * 1024) for _ in range(2000)"
            "]); "
            "t.start(); s.start(); t.join(); s.join()"
        )
        result = ProcessRunner().run(
            _req(tmp_path, code, max_output_bytes=4096, timeout_seconds=2.0)
        )
        # Either completed quickly, or hit output_limit (no deadlock)
        assert result.status in ("completed", "output_limit")
        assert not (result.status == "timed_out" and not result.truncated)
