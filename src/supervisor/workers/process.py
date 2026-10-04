"""Bounded process execution with explicit environment and cancellable pipe reads."""

from __future__ import annotations

import math
import os
import select as select
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
    max_output_bytes: int = 1048576
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


def _is_posix():
    return os.name == "posix"


def _validate_request(req):
    if not req.argv:
        raise ValueError("argv must not be empty")
    if any(not isinstance(a, str) for a in req.argv):
        raise ValueError("argv must contain strings")
    if not os.path.isabs(req.argv[0]):
        raise ValueError("executable must be an absolute path")
    for val in (req.timeout_seconds, req.cancel_grace_seconds):
        if (
            isinstance(val, bool)
            or not isinstance(val, (int, float))
            or not math.isfinite(val)
            or val <= 0
        ):
            raise ValueError("time budget must be a positive finite number")
    if (
        isinstance(req.max_output_bytes, bool)
        or not isinstance(req.max_output_bytes, int)
        or req.max_output_bytes <= 0
    ):
        raise ValueError("output budget must be a positive integer")
    try:
        req.cwd.resolve().relative_to(req.workspace_root.resolve())
    except ValueError as exc:
        raise ValueError("cwd outside workspace") from exc


def _process_table():
    """Observe ancestry with Linux start times or POSIX ps identity metadata."""
    table = {}
    try:
        for path in Path("/proc").iterdir():
            if not path.name.isdecimal():
                continue
            try:
                fields = (path / "stat").read_text().rsplit(")", 1)[1].split()
                table[int(path.name)] = (int(fields[1]), int(fields[2]), fields[0], fields[19])
            except (OSError, ValueError, IndexError):
                continue
        return table if table else None
    except OSError:
        try:
            result = subprocess.run(
                [
                    "/bin/ps" if Path("/bin/ps").exists() else "/usr/bin/ps",
                    "-axo",
                    "pid=,ppid=,pgid=,stat=,lstart=",
                ],
                env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
                capture_output=True,
                timeout=0.1,
                check=True,
            )
            for line in result.stdout.decode().splitlines():
                pid, parent, group, state, identity = line.split(None, 4)
                table[int(pid)] = (int(parent), int(group), state[0], identity)
            return table or None
        except (OSError, ValueError, subprocess.SubprocessError):
            return None


class ProcessRunner:
    def run(self, request, *, cancel_event=None):
        _validate_request(request)
        start = time.monotonic()

        def failure(error):
            return ProcessResult(
                "environment_failure", None, b"", b"", time.monotonic() - start, False, None, error
            )

        if request.require_tree_cleanup and (not _is_posix() or _process_table() is None):
            return failure("unsupported: process tree cleanup")
        if cancel_event is not None and cancel_event.is_set():
            return ProcessResult(
                "cancelled", None, b"", b"", 0.0, False, None, "cancelled before start"
            )
        process = None

        try:
            process = subprocess.Popen(
                request.argv,
                cwd=request.cwd,
                env=dict(request.env),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                start_new_session=request.require_tree_cleanup,
            )
            process._m0_known = {}
            return self._drive_process(process, request, start, cancel_event)
        except Exception:
            if process is not None:
                self._terminate_process(process, request)
            return failure("process execution failed")
        finally:
            if process is not None:
                if process.poll() is None:
                    self._terminate_process(process, request)
                for stream in (process.stdout, process.stderr):
                    stream.close()

    def _observe(self, process):
        table = _process_table()
        if table is None:
            return None
        parents = {process.pid, *process._m0_known}
        changed = True
        while changed:
            changed = False
            for pid, (ppid, group, _state, _identity) in table.items():
                if pid not in parents and (ppid in parents or group == process.pid):
                    parents.add(pid)
                    changed = True
        for pid in parents:
            if pid in table:
                process._m0_known[pid] = table[pid][3]
        return table

    def _terminate_process(self, process, request):
        table = self._observe(process) if request.require_tree_cleanup else None
        denied = False
        if request.require_tree_cleanup:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except OSError:
                denied = True
            for pid, identity in process._m0_known.items():
                if table and pid in table and table[pid][3] == identity:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    except OSError:
                        denied = True
        if process.poll() is None:
            process.kill()
        deadline = time.monotonic() + request.cancel_grace_seconds
        try:
            process.wait(timeout=request.cancel_grace_seconds)
        except subprocess.TimeoutExpired:
            return False if request.require_tree_cleanup else None
        if not request.require_tree_cleanup:
            return None
        if denied:
            return False
        if table is None:
            return None
        while time.monotonic() < deadline:
            current = _process_table()
            if current is None:
                return None
            if all(
                pid not in current or current[pid][3] != identity or current[pid][2] == "Z"
                for pid, identity in process._m0_known.items()
            ):
                return True
            time.sleep(0.005)
        return False

    def _drive_process(self, process, request, start, cancel_event):
        buffers = [bytearray(), bytearray()]
        lock = threading.Lock()
        stop = threading.Event()
        done = [False, False]
        exceeded = threading.Event()
        errors = threading.Event()
        streams = (process.stdout, process.stderr)
        # POSIX raw reads are nonblocking, including the simulated Windows path.
        if os.name == "posix":
            for stream in streams:
                os.set_blocking(stream.fileno(), False)

        def reader(index):
            stream = streams[index]
            try:
                while not stop.is_set():
                    try:
                        # Read at most one excess byte; output storage is shared and bounded.
                        with lock:
                            room = request.max_output_bytes - sum(map(len, buffers))
                            chunk = (
                                os.read(stream.fileno(), min(4096, room + 1))
                                if os.name == "posix"
                                else None
                            )
                        if os.name != "posix":
                            chunk = os.read(stream.fileno(), min(4096, room + 1))
                    except BlockingIOError:
                        stop.wait(0.002)
                        continue
                    if not chunk:
                        break
                    with lock:
                        room = request.max_output_bytes - sum(map(len, buffers))
                        buffers[index].extend(chunk[:room])
                        if len(chunk) > room:
                            exceeded.set()
                            break
            except OSError:
                if not stop.is_set():
                    errors.set()
            finally:
                done[index] = True

        threads = [threading.Thread(target=reader, args=(i,), daemon=True) for i in range(2)]
        for thread in threads:
            thread.start()
        status = "completed"
        cleanup = None
        try:
            while True:
                if request.require_tree_cleanup:
                    self._observe(process)
                if exceeded.is_set():
                    status = "output_limit"
                    break
                if cancel_event is not None and cancel_event.is_set():
                    status = "cancelled"
                    break
                if time.monotonic() - start >= request.timeout_seconds:
                    status = "timed_out"
                    break
                if errors.is_set():
                    status = "environment_failure"
                    break
                if all(done) and process.poll() is not None:
                    status = "completed" if process.returncode == 0 else "failed"
                    break
                stop.wait(0.002)
            if status not in ("completed", "failed"):
                cleanup = self._terminate_process(process, request)
        finally:
            stop.set()
            # Cancel Windows synchronous ReadFile before closing raw (unbuffered) pipes.
            if os.name == "nt":
                import ctypes

                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.OpenThread.restype = ctypes.c_void_p
                kernel.OpenThread.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
                kernel.CancelSynchronousIo.argtypes = [ctypes.c_void_p]
                kernel.CloseHandle.argtypes = [ctypes.c_void_p]
                for thread in threads:
                    handle = kernel.OpenThread(1, False, thread.native_id)
                    if handle:
                        kernel.CancelSynchronousIo(handle)
                        kernel.CloseHandle(handle)
            for thread in threads:
                thread.join(timeout=request.cancel_grace_seconds / 2)
            if any(thread.is_alive() for thread in threads):
                status = "environment_failure"
        with lock:
            stdout, stderr = map(bytes, buffers)
        return ProcessResult(
            status,
            process.returncode,
            stdout,
            stderr,
            time.monotonic() - start,
            exceeded.is_set(),
            cleanup,
            None if status in ("completed", "output_limit") else status,
        )
