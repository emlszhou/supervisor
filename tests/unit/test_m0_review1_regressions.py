"""Regression tests for M0R review-1 findings.

These cover the 8 findings raised in codex/m0r-review-1:
- M0R-R1-drain: bounded drain with wall deadline
- M0R-R1-tree: killpg denial returns tree_cleanup_confirmed=False
- M0R-R1-exception: drive exception reaps started process
- M0R-R1-session: start_new_session instead of preexec_fn
- M0R-R1-boundary: exact-budget completion when no extra byte available
- M0R-R1-windows: thread-based pipe consumption when select fails
- M0R-R1-exit-type: bool exit_code rejected
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from supervisor.agents.base import parse_agent_result
from supervisor.workers.process import (
    ProcessRequest,
    ProcessResult,
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
        "attempt_id": "M0R-attempt",
        "require_tree_cleanup": False,
    }
    fields.update(overrides)
    return ProcessRequest(**fields)


class TestDrainBounded:
    """M0R-R1-drain: drain must be bounded in time and memory."""

    def test_inherited_pipe_respects_timeout(self, tmp_path):
        """A leader spawning an inherited-pipe child that sleeps .6s should
        respect the .1s wall deadline - not be held by .6s drain wait."""
        code = (
            "import subprocess,sys;"
            "subprocess.Popen([sys.executable,'-c','import time;time.sleep(.6)']);"
            "import time;time.sleep(.5)"
        )
        result = ProcessRunner().run(_req(tmp_path, code, timeout_seconds=0.1))
        assert result.status == "timed_out"
        assert result.duration_seconds < 0.3, (
            f"drain wait extended wall deadline: {result.duration_seconds}s"
        )


class TestTreeCleanupFalse:
    """M0R-R1-tree: killpg denial must return False, not True."""

    def test_killpg_permission_error_returns_false(self, tmp_path):
        """When os.killpg raises PermissionError, tree_cleanup_confirmed
        must be False (group termination was denied)."""
        from supervisor.workers import process as m

        with patch.object(m.os, "killpg", side_effect=PermissionError("denied")):
            result = ProcessRunner().run(
                _req(
                    tmp_path,
                    "import time;time.sleep(2)",
                    require_tree_cleanup=True,
                    timeout_seconds=0.2,
                )
            )
        assert result.status == "timed_out"
        # With require_tree_cleanup=True and killpg denial, must be False
        assert result.tree_cleanup_confirmed is False, (
            f"killpg denial must return False, got {result.tree_cleanup_confirmed}"
        )


class TestExceptionReap:
    """M0R-R1-exception: drive exception must terminate/reap started process."""

    def test_drive_exception_terminates_started_process(self, tmp_path):
        """If _drive_process raises, the started subprocess must not remain
        alive after run() returns."""
        from supervisor.workers import process as m

        original_popen = m.subprocess.Popen
        captured = []

        def capture(*args, **kwargs):
            p = original_popen(*args, **kwargs)
            captured.append(p)
            return p

        with (
            patch.object(m.subprocess, "Popen", side_effect=capture),
            patch.object(
                m.ProcessRunner, "_drive_process", side_effect=RuntimeError("drive failed")
            ),
        ):
            result = ProcessRunner().run(_req(tmp_path, "import time;time.sleep(2)"))
        leader = captured[0]
        assert result.status == "environment_failure"
        assert leader.poll() is not None, "leader must be reaped after drive exception"


class TestSessionSafety:
    """M0R-R1-session: preexec_fn forbidden, use start_new_session."""

    def test_no_preexec_fn_when_tree_cleanup_required(self, tmp_path):
        """When require_tree_cleanup=True, Popen must use start_new_session
        and NOT preexec_fn=os.setpgrp."""
        from supervisor.workers import process as m

        original_popen = m.subprocess.Popen
        captured_kwargs = []

        def capture(*args, **kwargs):
            captured_kwargs.append(kwargs)
            return original_popen(*args, **kwargs)

        with patch.object(m.subprocess, "Popen", side_effect=capture):
            m.ProcessRunner().run(
                _req(
                    tmp_path,
                    "pass",
                    require_tree_cleanup=True,
                )
            )
        # Find the captured kwargs for our process
        for kwargs in captured_kwargs:
            if "start_new_session" in kwargs or "preexec_fn" in kwargs:
                assert "preexec_fn" not in kwargs, (
                    f"preexec_fn must not be used; got kwargs: {kwargs}"
                )
                break


class TestExactBudgetBoundary:
    """M0R-R1-boundary: exact-budget match with no extra byte must complete."""

    def test_exact_budget_completion(self, tmp_path):
        """64 stdout bytes at budget=64 with stderr EOF and leader sleeping
        must return 'completed' (not 'output_limit') since no extra byte."""
        code = "import os,time;os.write(1,b'x'*64);os.close(2);time.sleep(.1)"
        result = ProcessRunner().run(_req(tmp_path, code, timeout_seconds=0.5, max_output_bytes=64))
        assert result.status == "completed", (
            f"exact-budget match must complete, got {result.status}"
        )
        assert result.truncated is False
        assert len(result.stdout) == 64

    def test_exact_budget_plus_extra_byte_truncates(self, tmp_path):
        """65 stdout bytes at budget=64 must be truncated."""
        code = "import os,time;os.write(1,b'x'*65);time.sleep(.1)"
        result = ProcessRunner().run(_req(tmp_path, code, timeout_seconds=0.5, max_output_bytes=64))
        assert result.status == "output_limit"
        assert result.truncated is True
        assert len(result.stdout) == 64


class TestWindowsFallback:
    """M0R-R1-windows: thread-based pipe consumption when select fails."""

    def test_windows_select_failure_consumes_pipes(self, tmp_path):
        """When select.select raises OSError (simulating Windows non-socket
        pipes), the thread-based fallback must actually capture output."""
        from supervisor.workers import process as m

        with (
            patch.object(m, "_is_posix", return_value=False),
            patch.object(m.select, "select", side_effect=OSError("synthetic Windows")),
        ):
            result = ProcessRunner().run(
                _req(
                    tmp_path,
                    "import os,time;os.write(1,b'x'*200000);time.sleep(2)",
                    require_tree_cleanup=False,
                    timeout_seconds=0.2,
                    max_output_bytes=1_048_576,  # large budget so timeout fires first
                )
            )
        assert result.status == "timed_out", (
            f"expected timed_out (200KB < 1MB budget), got {result.status}"
        )
        assert len(result.stdout) > 0, (
            f"Windows fallback must capture output; got {len(result.stdout)} bytes"
        )


class TestStrictExitCodeType:
    """M0R-R1-exit-type: bool exit_code must be rejected."""

    def test_bool_exit_code_returns_failed(self):
        """Declared exit_code=False (or True) must return failed, not completed."""
        identity = dict(
            task_id="M0R-test",
            run_id="m0r",
            attempt_id="m0r",
            role="implementer",
            provider="mock",
        )
        protocol = dict(
            schema_version=1,
            **identity,
            model=None,
            session_id="session",
            status="completed",
            exit_code=False,
            summary="",
            error=None,
            usage=None,
            artifacts=[],
            truncated=False,
        )
        process = ProcessResult(
            "completed", 0, json.dumps(protocol).encode(), b"", 0.01, False, None, None
        )
        result = parse_agent_result(process, expected=identity)
        assert result.status == "failed", f"bool exit_code must return failed, got {result.status}"


# Sanity: ensure pytest collects these tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
