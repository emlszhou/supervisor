"""ProcessRunner: execute subprocesses with explicit environment, timeout, and output limits."""

from __future__ import annotations

import math
import os
import signal
import subprocess
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProcessRequest:
    argv: tuple[str, ...]
    cwd: Path
    workspace_root: Path
    env: Mapping[str, str]
    timeout_seconds: float = 10.0
    cancel_grace_seconds: float = 0.2
    max_output_bytes: int = 1_048_576
    attempt_id: str = "M0-attempt"
    require_tree_cleanup: bool = True


@dataclass(frozen=True)
class ProcessResult:
    status: str
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    duration_seconds: float
    truncated: bool
    tree_cleanup_confirmed: bool | None
    error: str | None


def _validate_request(req: ProcessRequest) -> None:
    """Validate request before starting process. Raises ValueError on invalid input."""
    if not req.argv:
        raise ValueError("argv must not be empty")
    if not all(isinstance(a, str) for a in req.argv):
        raise ValueError("all argv elements must be strings")

    for name, val in [
        ("timeout_seconds", req.timeout_seconds),
        ("cancel_grace_seconds", req.cancel_grace_seconds),
    ]:
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise ValueError(f"{name} must be a positive finite number")
        if math.isnan(val) or math.isinf(val) or val <= 0:
            raise ValueError(f"{name} must be a positive finite number")

    if not isinstance(req.max_output_bytes, int) or isinstance(req.max_output_bytes, bool):
        raise ValueError("max_output_bytes must be a positive integer")
    if req.max_output_bytes <= 0:
        raise ValueError("max_output_bytes must be positive")

    # cwd must be inside workspace_root
    try:
        req.cwd.resolve().relative_to(req.workspace_root.resolve())
    except ValueError as e:
        raise ValueError("cwd must be within workspace_root") from e


def _can_cleanup_tree() -> bool:
    """Check if process tree cleanup is supported on this platform."""
    return hasattr(os, "killpg") and hasattr(signal, "SIGKILL")


class ProcessRunner:
    """Execute subprocesses with timeout, cancellation, and output limits."""

    def run(
        self,
        request: ProcessRequest,
        *,
        cancel_event: threading.Event | None = None,
    ) -> ProcessResult:
        """Run a process and return ProcessResult."""
        _validate_request(request)

        # Check if tree cleanup is required but not supported
        if request.require_tree_cleanup and not _can_cleanup_tree():
            return ProcessResult(
                status="environment_failure",
                exit_code=None,
                stdout=b"",
                stderr=b"",
                duration_seconds=0.0,
                truncated=False,
                tree_cleanup_confirmed=None,
                error="unsupported: process tree cleanup not available on this platform",
            )

        # Pre-cancelled: do not start
        if cancel_event is not None and cancel_event.is_set():
            return ProcessResult(
                status="cancelled",
                exit_code=None,
                stdout=b"",
                stderr=b"",
                duration_seconds=0.0,
                truncated=False,
                tree_cleanup_confirmed=None,
                error="cancelled before start",
            )

        # Check executable exists (these should raise, not return environment_failure)
        executable = request.argv[0]
        if not os.path.isabs(executable):
            raise ValueError(f"first argv element must be an absolute path: {executable}")

        # Check for file existence and permissions - these are environment failures
        try:
            if not os.path.isfile(executable):
                return ProcessResult(
                    status="environment_failure",
                    exit_code=None,
                    stdout=b"",
                    stderr=b"",
                    duration_seconds=0.0,
                    truncated=False,
                    tree_cleanup_confirmed=None,
                    error=f"executable not found: {executable}",
                )
            if not os.access(executable, os.X_OK):
                return ProcessResult(
                    status="environment_failure",
                    exit_code=None,
                    stdout=b"",
                    stderr=b"",
                    duration_seconds=0.0,
                    truncated=False,
                    tree_cleanup_confirmed=None,
                    error=f"not executable: {executable}",
                )
        except Exception as e:
            return ProcessResult(
                status="environment_failure",
                exit_code=None,
                stdout=b"",
                stderr=b"",
                duration_seconds=0.0,
                truncated=False,
                tree_cleanup_confirmed=None,
                error=str(e),
            )

        # Check cwd exists
        if not request.cwd.is_dir():
            return ProcessResult(
                status="environment_failure",
                exit_code=None,
                stdout=b"",
                stderr=b"",
                duration_seconds=0.0,
                truncated=False,
                tree_cleanup_confirmed=None,
                error=f"cwd not a directory: {request.cwd}",
            )

        # Build explicit environment
        env_vars = {}
        for k, v in request.env.items():
            env_vars[str(k)] = str(v)

        start_time = time.monotonic()

        try:
            # Start process
            process = subprocess.Popen(
                list(request.argv),
                cwd=str(request.cwd),
                env=env_vars,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setpgrp,
            )

            # Poll for exit with timeout and cancellation support
            stdout = b""
            stderr = b""
            exit_code = None
            while True:
                elapsed = time.monotonic() - start_time
                remaining = request.timeout_seconds - elapsed

                # Check for cancellation
                if cancel_event is not None and cancel_event.is_set():
                    self._kill_process_group(process.pid)
                    try:
                        process.wait(timeout=request.cancel_grace_seconds)
                    except subprocess.TimeoutExpired:
                        pass
                    return ProcessResult(
                        status="cancelled",
                        exit_code=process.returncode,
                        stdout=b"",
                        stderr=b"",
                        duration_seconds=elapsed,
                        truncated=False,
                        tree_cleanup_confirmed=True,
                        error="cancelled during execution",
                    )

                # Check for timeout
                if remaining <= 0:
                    self._kill_process_group(process.pid)
                    try:
                        process.wait(timeout=request.cancel_grace_seconds)
                    except subprocess.TimeoutExpired:
                        pass
                    return ProcessResult(
                        status="timed_out",
                        exit_code=process.returncode,
                        stdout=b"",
                        stderr=b"",
                        duration_seconds=elapsed,
                        truncated=False,
                        tree_cleanup_confirmed=True,
                        error="wall timeout exceeded",
                    )

                # Try to wait with short timeout to check for exit
                try:
                    stdout, stderr = process.communicate(timeout=min(0.05, remaining))
                    exit_code = process.returncode
                    break
                except subprocess.TimeoutExpired:
                    continue

            # Check output limit
            total_bytes = len(stdout) + len(stderr)
            truncated = total_bytes > request.max_output_bytes
            if truncated:
                # Truncate to limit
                remaining = request.max_output_bytes
                truncated_stdout = stdout[:remaining]
                remaining -= len(truncated_stdout)
                truncated_stderr = stderr[:remaining]
                return ProcessResult(
                    status="output_limit",
                    exit_code=exit_code,
                    stdout=truncated_stdout,
                    stderr=truncated_stderr,
                    duration_seconds=time.monotonic() - start_time,
                    truncated=True,
                    tree_cleanup_confirmed=None,
                    error=None,
                )

            if exit_code == 0:
                return ProcessResult(
                    status="completed",
                    exit_code=exit_code,
                    stdout=stdout,
                    stderr=stderr,
                    duration_seconds=time.monotonic() - start_time,
                    truncated=False,
                    tree_cleanup_confirmed=None,
                    error=None,
                )
            else:
                return ProcessResult(
                    status="failed",
                    exit_code=exit_code,
                    stdout=stdout,
                    stderr=stderr,
                    duration_seconds=time.monotonic() - start_time,
                    truncated=False,
                    tree_cleanup_confirmed=None,
                    error=f"nonzero exit code: {exit_code}",
                )

        except Exception as e:
            return ProcessResult(
                status="environment_failure",
                exit_code=None,
                stdout=b"",
                stderr=b"",
                duration_seconds=0.0,
                truncated=False,
                tree_cleanup_confirmed=None,
                error=str(e),
            )

    def _kill_process_group(self, pid: int) -> None:
        """Kill process and its children by process group."""
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
