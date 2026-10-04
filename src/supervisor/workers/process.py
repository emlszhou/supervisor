"""ProcessRunner: execute subprocesses with explicit environment, timeout, and output limits."""

from __future__ import annotations

import math
import os
import select
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


def _is_posix() -> bool:
    """Check if on POSIX platform (supports process groups)."""
    return os.name == "posix"


def _can_cleanup_tree() -> bool:
    """Check if process tree cleanup is supported on this platform."""
    return _is_posix() and hasattr(signal, "SIGKILL")


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
        env_vars: dict[str, str] = {}
        for k, v in request.env.items():
            env_vars[str(k)] = str(v)

        start_time = time.monotonic()
        process: subprocess.Popen | None = None
        try:
            return self._run_process(request, env_vars, start_time, cancel_event)
        except Exception as e:
            # Reap if process was started
            if process is not None:
                try:
                    self._close_pipes(process)
                    process.kill()
                    process.wait(timeout=0.5)
                except Exception:
                    pass
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

    def _run_process(
        self,
        request: ProcessRequest,
        env_vars: dict,
        start_time: float,
        cancel_event: threading.Event | None,
    ) -> ProcessResult:
        """Start process and manage its lifecycle with timeout/cancel/output limits."""
        # Build popen kwargs - preexec_fn only on POSIX
        popen_kwargs: dict = {
            "cwd": str(request.cwd),
            "env": env_vars,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
        }
        if _is_posix() and request.require_tree_cleanup:
            popen_kwargs["preexec_fn"] = os.setpgrp

        process = subprocess.Popen(list(request.argv), **popen_kwargs)

        try:
            return self._drive_process(process, request, start_time, cancel_event)
        finally:
            self._close_pipes(process)

    def _drive_process(
        self,
        process: subprocess.Popen,
        request: ProcessRequest,
        start_time: float,
        cancel_event: threading.Event | None,
    ) -> ProcessResult:
        """Drive process: poll for cancel/timeout/output limit, then collect exit."""
        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        total_bytes = 0
        truncated = False

        # Stream output concurrently while polling for exit/timeout/cancel
        while True:
            elapsed = time.monotonic() - start_time
            remaining = request.timeout_seconds - elapsed

            # Check for cancellation
            if cancel_event is not None and cancel_event.is_set():
                cleanup_ok = self._terminate_process(process, request)
                return ProcessResult(
                    status="cancelled",
                    exit_code=process.returncode,
                    stdout=b"".join(stdout_chunks),
                    stderr=b"".join(stderr_chunks),
                    duration_seconds=time.monotonic() - start_time,
                    truncated=truncated,
                    tree_cleanup_confirmed=cleanup_ok if request.require_tree_cleanup else None,
                    error="cancelled during execution",
                )

            # Check for timeout
            if remaining <= 0:
                cleanup_ok = self._terminate_process(process, request)
                return ProcessResult(
                    status="timed_out",
                    exit_code=process.returncode,
                    stdout=b"".join(stdout_chunks),
                    stderr=b"".join(stderr_chunks),
                    duration_seconds=time.monotonic() - start_time,
                    truncated=truncated,
                    tree_cleanup_confirmed=cleanup_ok if request.require_tree_cleanup else None,
                    error="wall timeout exceeded",
                )

            # Read available output with small timeout (enforce budget in real-time)
            if process.stdout is not None or process.stderr is not None:
                # Use os.read() with O_NONBLOCK to avoid blocking on buffered reads
                # (BufferedReader.read() blocks until data available or EOF)
                rlist: list[int] = []
                if process.stdout is not None:
                    rlist.append(process.stdout.fileno())
                if process.stderr is not None:
                    rlist.append(process.stderr.fileno())

                try:
                    ready, _, _ = select.select(rlist, [], [], min(0.05, remaining))
                except (ValueError, OSError):
                    ready = []

                budget_remaining = request.max_output_bytes - total_bytes
                stdout_fileno = process.stdout.fileno() if process.stdout is not None else -1

                for fd in ready:
                    if budget_remaining <= 0:
                        # Budget used up. Check if process has exited.
                        if process.poll() is not None:
                            # Process exited. Wait for drain to detect more output.
                            break
                        # Process still running. Wait a tiny bit and re-check
                        # (poll may not have detected exit yet).
                        time.sleep(0.01)
                        if process.poll() is not None:
                            # Process exited. Wait for drain to detect more output.
                            break
                        # Process still running with more output to come.
                        # Return output_limit immediately.
                        truncated = True
                        cleanup_ok = self._terminate_process(process, request)
                        stdout_total = b"".join(stdout_chunks)
                        stderr_total = b"".join(stderr_chunks)
                        if len(stdout_total) + len(stderr_total) > request.max_output_bytes:
                            room = request.max_output_bytes - len(stdout_total)
                            if room < 0:
                                stdout_total = stdout_total[: request.max_output_bytes]
                                stderr_total = b""
                            else:
                                stderr_total = stderr_total[:room]
                        return ProcessResult(
                            status="output_limit",
                            exit_code=process.returncode,
                            stdout=stdout_total,
                            stderr=stderr_total,
                            duration_seconds=time.monotonic() - start_time,
                            truncated=True,
                            tree_cleanup_confirmed=(
                                cleanup_ok if request.require_tree_cleanup else None
                            ),
                            error=None,
                        )
                    try:
                        chunk = os.read(fd, min(4096, budget_remaining))
                    except (ValueError, OSError, BlockingIOError):
                        chunk = b""
                    if not chunk:
                        continue
                    if len(chunk) > budget_remaining:
                        chunk = chunk[:budget_remaining]
                        truncated = True
                    if fd == stdout_fileno:
                        stdout_chunks.append(chunk)
                    else:
                        stderr_chunks.append(chunk)
                    total_bytes += len(chunk)
                    budget_remaining -= len(chunk)

                if truncated:
                    # Output limit hit - kill process and return output_limit
                    cleanup_ok = self._terminate_process(process, request)
                    stdout_total = b"".join(stdout_chunks)
                    stderr_total = b"".join(stderr_chunks)
                    # Ensure combined limit
                    if len(stdout_total) + len(stderr_total) > request.max_output_bytes:
                        room = request.max_output_bytes - len(stdout_total)
                        if room < 0:
                            stdout_total = stdout_total[: request.max_output_bytes]
                            stderr_total = b""
                        else:
                            stderr_total = stderr_total[:room]
                    return ProcessResult(
                        status="output_limit",
                        exit_code=process.returncode,
                        stdout=stdout_total,
                        stderr=stderr_total,
                        duration_seconds=time.monotonic() - start_time,
                        truncated=True,
                        tree_cleanup_confirmed=cleanup_ok if request.require_tree_cleanup else None,
                        error=None,
                    )

            # Check if process has exited
            if process.poll() is not None:
                # Drain any remaining buffered output (respecting budget)
                drain_truncated = self._drain_output(
                    process, stdout_chunks, stderr_chunks, request.max_output_bytes - total_bytes
                )
                if drain_truncated:
                    truncated = True
                break

        # Process exited normally - finalize
        exit_code = process.returncode
        elapsed = time.monotonic() - start_time
        stdout_final = b"".join(stdout_chunks)
        stderr_final = b"".join(stderr_chunks)

        # Check output limit after exit (or truncation detected during drain)
        total = len(stdout_final) + len(stderr_final)
        if truncated or total > request.max_output_bytes:
            # If truncated flag is set, it means either:
            # 1. Budget was exhausted during streaming (process still running)
            # 2. Drain detected more output after budget exhaustion (process exited)
            # In both cases, output_limit is appropriate.
            truncated_stdout = stdout_final[: request.max_output_bytes]
            truncated_stderr = stderr_final[: request.max_output_bytes - len(truncated_stdout)]
            return ProcessResult(
                status="output_limit",
                exit_code=exit_code,
                stdout=truncated_stdout,
                stderr=truncated_stderr,
                duration_seconds=elapsed,
                truncated=True,
                tree_cleanup_confirmed=None,
                error=None,
            )

        if exit_code == 0:
            return ProcessResult(
                status="completed",
                exit_code=exit_code,
                stdout=stdout_final,
                stderr=stderr_final,
                duration_seconds=elapsed,
                truncated=False,
                tree_cleanup_confirmed=None,
                error=None,
            )
        else:
            return ProcessResult(
                status="failed",
                exit_code=exit_code,
                stdout=stdout_final,
                stderr=stderr_final,
                duration_seconds=elapsed,
                truncated=False,
                tree_cleanup_confirmed=None,
                error=f"nonzero exit code: {exit_code}",
            )

    def _drain_output(
        self,
        process: subprocess.Popen,
        stdout_chunks: list[bytes],
        stderr_chunks: list[bytes],
        budget: int,
    ) -> bool:
        """Drain remaining output after process exit (up to budget). Returns True if truncated."""
        if budget <= 0:
            # Check if there's more output (to detect truncation)
            if process.stdout is not None:
                try:
                    remaining = os.read(process.stdout.fileno(), 1)
                    if remaining:
                        return True
                except (ValueError, OSError, BlockingIOError):
                    pass
            if process.stderr is not None:
                try:
                    remaining = os.read(process.stderr.fileno(), 1)
                    if remaining:
                        return True
                except (ValueError, OSError, BlockingIOError):
                    pass
            return False
        if process.stdout is not None:
            try:
                remaining = process.stdout.read()
                if remaining:
                    if len(remaining) > budget:
                        stdout_chunks.append(remaining[:budget])
                        return True
                    else:
                        stdout_chunks.append(remaining)
                        budget -= len(remaining)
            except (ValueError, OSError):
                pass
        if budget > 0 and process.stderr is not None:
            try:
                remaining = process.stderr.read()
                if remaining:
                    if len(remaining) > budget:
                        stderr_chunks.append(remaining[:budget])
                        return True
                    else:
                        stderr_chunks.append(remaining)
            except (ValueError, OSError):
                pass
        return False

    def _terminate_process(
        self,
        process: subprocess.Popen,
        request: ProcessRequest,
    ) -> bool | None:
        """Terminate process and children.

        Returns:
            True if cleanup confirmed (process terminated within grace)
            False if cleanup attempted but failed
            None if tree cleanup not required
        """
        if not request.require_tree_cleanup:
            # Still need to terminate the process itself
            try:
                process.kill()
                process.wait(timeout=request.cancel_grace_seconds)
            except Exception:
                pass
            return None

        if not _can_cleanup_tree():
            return False

        # POSIX tree cleanup
        try:
            pgid = os.getpgid(process.pid)
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            try:
                process.kill()
            except (ProcessLookupError, OSError):
                pass

        try:
            process.wait(timeout=request.cancel_grace_seconds)
            return True
        except subprocess.TimeoutExpired:
            return False
        except Exception:
            return False

    def _close_pipes(self, process: subprocess.Popen) -> None:
        """Close stdout/stderr pipes."""
        try:
            if process.stdout is not None:
                process.stdout.close()
        except Exception:
            pass
        try:
            if process.stderr is not None:
                process.stderr.close()
        except Exception:
            pass
