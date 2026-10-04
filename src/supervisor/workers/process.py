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
from typing import Any


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
        try:
            return self._run_process(request, env_vars, start_time, cancel_event)
        except Exception as e:
            # _run_process handles its own exception cleanup via finally blocks
            # (terminating/reaping the subprocess it started). If an exception
            # escapes, return environment_failure.
            return ProcessResult(
                status="environment_failure",
                exit_code=None,
                stdout=b"",
                stderr=b"",
                duration_seconds=time.monotonic() - start_time,
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
        # Build popen kwargs - use start_new_session for safe process group
        # creation (avoid preexec_fn which is forbidden by frozen contract).
        popen_kwargs: dict = {
            "cwd": str(request.cwd),
            "env": env_vars,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
        }
        if _is_posix() and request.require_tree_cleanup:
            popen_kwargs["start_new_session"] = True

        process = subprocess.Popen(list(request.argv), **popen_kwargs)

        try:
            return self._drive_process(process, request, start_time, cancel_event)
        except Exception:
            # On any exception during drive, terminate and reap the started process.
            # Leader must NOT remain alive after exception escapes.
            try:
                self._terminate_process(process, request)
            except Exception:
                pass
            try:
                process.wait(timeout=request.cancel_grace_seconds)
            except Exception:
                pass
            self._close_pipes(process)
            raise
        finally:
            # Always close pipes on normal return too
            try:
                self._close_pipes(process)
            except Exception:
                pass

    def _drive_process(
        self,
        process: subprocess.Popen,
        request: ProcessRequest,
        start_time: float,
        cancel_event: threading.Event | None,
    ) -> ProcessResult:
        """Drive process: poll for cancel/timeout/output limit, then collect exit."""
        # On non-POSIX platforms (Windows), select() may not work on pipe FDs.
        # Use a thread-based concurrent reader that doesn't depend on select().
        if not _is_posix():
            return self._drive_process_threads(process, request, start_time, cancel_event)

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
                        # Budget used up. We must briefly wait for process to exit
                        # to determine if there's truly more output (truncation)
                        # or if the process is just sleeping without emitting more.
                        # Use a small bounded wait (not the full remaining wall time)
                        # to avoid letting slow writers escape detection.
                        wait_deadline = time.monotonic() + 0.05
                        while time.monotonic() < wait_deadline:
                            if process.poll() is not None:
                                # Process exited - break out of wait loop
                                break
                            sleep_left = wait_deadline - time.monotonic()
                            if sleep_left <= 0:
                                break
                            time.sleep(min(0.01, sleep_left))

                        if process.poll() is not None:
                            # Process exited within deadline. Don't kill - let
                            # main loop's exit-drain detect any extra bytes.
                            break

                        # Process still running. Check if there's truly more
                        # data waiting in the pipes via nonblocking peek.
                        # If no extra byte is available, it's exact-budget completion
                        # (process is sleeping but already done emitting).
                        truly_truncated = False
                        for stream in (process.stdout, process.stderr):
                            if stream is None:
                                continue
                            try:
                                fd = stream.fileno()
                                import fcntl as _fcntl

                                flags = _fcntl.fcntl(fd, _fcntl.F_GETFL)
                                _fcntl.fcntl(fd, _fcntl.F_SETFL, flags | os.O_NONBLOCK)
                                try:
                                    extra = os.read(fd, 1)
                                    if extra:
                                        truly_truncated = True
                                        break
                                finally:
                                    _fcntl.fcntl(fd, _fcntl.F_SETFL, flags)
                            except BlockingIOError:
                                # No data available - exact budget match
                                continue
                            except (ValueError, OSError, ImportError):
                                # Other errors - assume truncated (safer)
                                truly_truncated = True
                                break

                        if not truly_truncated:
                            # No extra byte available - exact budget match.
                            # Process is just sleeping; don't kill, let main loop
                            # handle exit-drain on natural process exit.
                            break

                        # Truly truncated - kill and return output_limit
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
                # Drain any remaining buffered output (respecting budget and wall deadline)
                drain_truncated = self._drain_output(
                    process,
                    stdout_chunks,
                    stderr_chunks,
                    request.max_output_bytes - total_bytes,
                    wall_deadline=start_time + request.timeout_seconds,
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

    def _drive_process_threads(
        self,
        process: subprocess.Popen,
        request: ProcessRequest,
        start_time: float,
        cancel_event: threading.Event | None,
    ) -> ProcessResult:
        """Drive process using threads (for non-POSIX / Windows where select
        on pipes may not work).

        Spawns reader threads for stdout/stderr with bounded memory and a
        wall-clock deadline. Falls back to thread-based consumption when
        select-based polling fails.
        """
        import queue

        stdout_q: queue.Queue[bytes | None] = queue.Queue()
        stderr_q: queue.Queue[bytes | None] = queue.Queue()

        def reader(stream: Any, q: queue.Queue) -> None:
            try:
                while True:
                    chunk = stream.read(4096)
                    if not chunk:
                        q.put(None)  # EOF sentinel
                        return
                    q.put(chunk)
            except (ValueError, OSError):
                q.put(None)

        stdout_thread: threading.Thread | None = None
        stderr_thread: threading.Thread | None = None
        if process.stdout is not None:
            stdout_thread = threading.Thread(
                target=reader, args=(process.stdout, stdout_q), daemon=True
            )
            stdout_thread.start()
        if process.stderr is not None:
            stderr_thread = threading.Thread(
                target=reader, args=(process.stderr, stderr_q), daemon=True
            )
            stderr_thread.start()

        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        total_bytes = 0
        truncated = False
        stdout_done = process.stdout is None
        stderr_done = process.stderr is None

        while True:
            elapsed = time.monotonic() - start_time
            remaining = request.timeout_seconds - elapsed

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

            # Drain queues (non-blocking via get_nowait)
            for q, chunks, done_flag in [
                (stdout_q, stdout_chunks, "stdout"),
                (stderr_q, stderr_chunks, "stderr"),
            ]:
                if done_flag == "stdout" and stdout_done:
                    continue
                if done_flag == "stderr" and stderr_done:
                    continue
                while True:
                    try:
                        item = q.get_nowait()
                    except queue.Empty:
                        break
                    if item is None:
                        if done_flag == "stdout":
                            stdout_done = True
                        else:
                            stderr_done = True
                        break
                    budget_remaining = request.max_output_bytes - total_bytes
                    if budget_remaining <= 0:
                        truncated = True
                        break
                    if len(item) > budget_remaining:
                        chunks.append(item[:budget_remaining])
                        total_bytes += budget_remaining
                        truncated = True
                        break
                    else:
                        chunks.append(item)
                        total_bytes += len(item)

            if truncated:
                cleanup_ok = self._terminate_process(process, request)
                return ProcessResult(
                    status="output_limit",
                    exit_code=process.returncode,
                    stdout=b"".join(stdout_chunks)[: request.max_output_bytes],
                    stderr=b"".join(stderr_chunks)[
                        : max(0, request.max_output_bytes - len(b"".join(stdout_chunks)))
                    ],
                    duration_seconds=time.monotonic() - start_time,
                    truncated=True,
                    tree_cleanup_confirmed=cleanup_ok if request.require_tree_cleanup else None,
                    error=None,
                )

            # Check process exit
            if process.poll() is not None and stdout_done and stderr_done:
                break

            time.sleep(0.01)

        # Process exited - finalize
        exit_code = process.returncode
        elapsed = time.monotonic() - start_time
        stdout_final = b"".join(stdout_chunks)
        stderr_final = b"".join(stderr_chunks)
        total = len(stdout_final) + len(stderr_final)

        if truncated or total > request.max_output_bytes:
            return ProcessResult(
                status="output_limit",
                exit_code=exit_code,
                stdout=stdout_final[: request.max_output_bytes],
                stderr=stderr_final[: max(0, request.max_output_bytes - len(stdout_final))],
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
        wall_deadline: float | None = None,
    ) -> bool:
        """Drain remaining output after process exit (up to budget, bounded time).

        Uses bounded nonblocking reads on raw file descriptors with a wall deadline.
        Avoids unbounded allocation. Returns True if truncation was detected.

        Args:
            wall_deadline: absolute monotonic time after which drain must stop.
                           None means use a small default budget.
        """
        # Use os.read with bounded chunk size to avoid unbounded allocation.
        # Apply the same wall deadline as the rest of the pipeline.
        CHUNK = 4096
        deadline = wall_deadline if wall_deadline is not None else time.monotonic() + 0.5

        # First, drain what fits in the budget using bounded reads
        budget_left = budget
        if budget_left > 0:
            for stream_attr in ("stdout", "stderr"):
                stream = getattr(process, stream_attr)
                if stream is None:
                    continue
                try:
                    fd = stream.fileno()
                except (ValueError, OSError):
                    continue
                while budget_left > 0 and time.monotonic() < deadline:
                    try:
                        chunk = os.read(fd, min(CHUNK, budget_left))
                    except (ValueError, OSError, BlockingIOError):
                        break
                    if not chunk:
                        break
                    if len(chunk) > budget_left:
                        chunks = stdout_chunks if stream_attr == "stdout" else stderr_chunks
                        chunks.append(chunk[:budget_left])
                        budget_left = 0
                        # There's more data than budget allowed - truncation
                        # Try to peek for confirmation
                        try:
                            extra = os.read(fd, 1)
                            if extra:
                                return True
                        except (ValueError, OSError, BlockingIOError):
                            pass
                        break
                    else:
                        chunks = stdout_chunks if stream_attr == "stdout" else stderr_chunks
                        chunks.append(chunk)
                        budget_left -= len(chunk)

        # If budget exhausted, check if there's more output (to detect truncation)
        # but only until wall deadline, using nonblocking peek
        if budget_left <= 0:
            for stream_attr in ("stdout", "stderr"):
                stream = getattr(process, stream_attr)
                if stream is None:
                    continue
                try:
                    fd = stream.fileno()
                except (ValueError, OSError):
                    continue
                # Try to read 1 byte nonblocking - if any byte exists, truncated
                try:
                    # Set nonblocking temporarily for the peek
                    import fcntl

                    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
                    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                    try:
                        remaining = os.read(fd, 1)
                        if remaining:
                            return True
                    finally:
                        fcntl.fcntl(fd, fcntl.F_SETFL, flags)
                except (ValueError, OSError, BlockingIOError, ImportError):
                    # On Windows or if fcntl unavailable, skip peek
                    pass
            return False
        return False

    def _terminate_process(
        self,
        process: subprocess.Popen,
        request: ProcessRequest,
    ) -> bool | None:
        """Terminate process and children.

        Returns:
            True if cleanup confirmed (process terminated within grace)
            False if cleanup attempted but failed (group denied, exception, timeout)
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

        # POSIX tree cleanup. Leader exit is NOT sufficient proof of cleanup -
        # if group termination is denied or fails, return False even if leader died.
        group_ok = False
        try:
            pgid = os.getpgid(process.pid)
            os.killpg(pgid, signal.SIGKILL)
            group_ok = True
        except (ProcessLookupError, OSError, PermissionError):
            try:
                process.kill()
            except (ProcessLookupError, OSError):
                pass

        try:
            process.wait(timeout=request.cancel_grace_seconds)
            # If group termination was denied/failed, return False even if leader died.
            # Leader exit alone is NOT proof of cleanup.
            return group_ok
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
