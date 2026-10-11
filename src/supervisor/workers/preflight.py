"""Trusted synthetic preflight harness (harness-side; runs outside the sandbox).

Standard library only.  The harness is the only component allowed to create
attempt directories, write profiles, capture Worker output, persist evidence
packages and perform cleanup.  It never starts real Agents or models and never
performs live execution; ``backend.require_live_execution`` is the sole live
entry point and always refuses.

The actual synthetic matrix (sandbox-exec, loopback listeners, /tmp writes)
runs only after an explicit operator approval recorded in an external
authorization file that is cryptographically bound to the frozen contract.
Without that file, on a non-darwin host, or whenever the recorded approval
cannot be verified, the harness refuses before creating any path and reports
``not_run``.
"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import select
import shutil
import socket
import stat as stat_module
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from supervisor.workers import backend, evidence

__all__ = [
    "run",
    "main",
    "load_authorization",
    "validate_attempt_layout",
    "export_c1_dependency",
    "ensure_attempt",
    "build_profiles",
    "run_worker",
    "process_tree",
    "persist_package",
    "finalize_package",
    "verify_package_offline",
    "build_report",
]

MAX_OUTPUT = 64 * 1024
COMMAND_TIMEOUT = 120.0
CANCELLATION_GRACE = 5.0
CONNECT_TIMEOUT = 2
SANDBOX_EXEC = "/usr/bin/sandbox-exec"
AUTHORIZED_PLATFORM = "darwin"
AUTHORIZED_SCOPE_TYPES = ("write_root", "persistence_root", "loopback")

C1_BOUNDARY_COMMIT = "436e3b0e026580a6b39ece891e8ffe47ac1bb698"
C1_BOUNDARY_PATH = "src/supervisor/workers/boundary.py"
C1_MAX_BYTES = 64 * 1024


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fixed(message: str) -> ValueError:
    return ValueError(message)


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _lstat(path: Path) -> os.stat_result | None:
    try:
        return os.lstat(path)
    except OSError:
        return None


def _is_real_dir(path: Path) -> bool:
    st = _lstat(path)
    return (
        st is not None and stat_module.S_ISDIR(st.st_mode) and not stat_module.S_ISLNK(st.st_mode)
    )


# ---------------------------------------------------------------------------
# Authorization (external operator approval; never committed)
# ---------------------------------------------------------------------------


def load_authorization(path: Path, expected_bundle_sha: str | None = None) -> dict:
    """Load and structurally validate the external operator authorization.

    The file must be a JSON object with:
      * ``contract_sha256`` -- when ``expected_bundle_sha`` is given the two
        must match exactly (missing expected: fail closed); otherwise it must
        be a well-formed 64-character hex digest;
      * ``platform`` -- must equal the real host platform (no override);
      * ``roots`` -- absolute, canonical, non-symlinked
        ``sandbox_root`` and ``persistence_root``;
      * ``loopback`` -- ``host`` exactly ``127.0.0.1``, integer port in
        1024..65535, ``connect_timeout_s`` finite > 0, ``max_bytes`` positive;
      * ``approved_scopes`` -- must contain exactly the authorized scope
        types (order irrelevant);
      * ``approved_by`` -- non-empty string;
      * ``approved_at_utc`` -- ISO-8601 UTC timestamp.
    """
    st = _lstat(path)
    if st is None or stat_module.S_ISLNK(st.st_mode) or not stat_module.S_ISREG(st.st_mode):
        raise _fixed("authorization: path must be a real regular file")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        raise _fixed("authorization: unreadable file") from None
    if not isinstance(data, dict):
        raise _fixed("authorization: not a mapping")
    for key in (
        "contract_sha256",
        "platform",
        "roots",
        "loopback",
        "approved_scopes",
        "approved_by",
        "approved_at_utc",
    ):
        if key not in data:
            raise _fixed("authorization: missing key")
    sha = data["contract_sha256"]
    if expected_bundle_sha is None:
        raise _fixed("authorization: expected bundle sha unavailable; fail closed")
    if not isinstance(sha, str) or sha != expected_bundle_sha:
        raise _fixed("authorization: contract_sha256 mismatch")
    if data["platform"] != AUTHORIZED_PLATFORM:
        raise _fixed("authorization: platform must be darwin")
    for root_key in ("sandbox_root", "persistence_root"):
        value = data["roots"].get(root_key) if isinstance(data.get("roots"), dict) else None
        if not isinstance(value, str) or not value:
            raise _fixed("authorization: bad roots")
        canonical = posixpath.normpath(value)
        if not value.startswith("/") or value != canonical:
            raise _fixed("authorization: roots must be canonical absolute paths")
        st_root = _lstat(canonical)
        if st_root is not None and stat_module.S_ISLNK(st_root.st_mode):
            raise _fixed("authorization: root must not be a symlink")
    loopback = data["loopback"]
    if not isinstance(loopback, dict):
        raise _fixed("authorization: bad loopback")
    if loopback.get("host") != "127.0.0.1":
        raise _fixed("authorization: loopback host must be 127.0.0.1")
    port = loopback.get("port")
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise _fixed("authorization: loopback port out of range")
    timeout = loopback.get("connect_timeout_s")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not time_is_finite(timeout)
        or timeout <= 0
    ):
        raise _fixed("authorization: loopback connect_timeout_s invalid")
    max_bytes = loopback.get("max_bytes")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise _fixed("authorization: loopback max_bytes invalid")
    scopes = data["approved_scopes"]
    if (
        not isinstance(scopes, list)
        or not scopes
        or any(not isinstance(s, str) for s in scopes)
        or set(scopes) != set(AUTHORIZED_SCOPE_TYPES)
    ):
        raise _fixed("authorization: approved_scopes must cover exactly the authorized scope types")
    if not isinstance(data["approved_by"], str) or not data["approved_by"]:
        raise _fixed("authorization: approved_by must be a non-empty string")
    approved_at = data["approved_at_utc"]
    if not isinstance(approved_at, str) or not _is_utc_timestamp(approved_at):
        raise _fixed("authorization: approved_at_utc must be an ISO-8601 UTC timestamp")
    return data


def time_is_finite(value: float) -> bool:
    import math

    return math.isfinite(value)


def _is_utc_timestamp(value: str) -> bool:
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            time.strptime(value, fmt)
            return True
        except ValueError:
            continue
    return False


# ---------------------------------------------------------------------------
# Layout validation + attempt creation
# ---------------------------------------------------------------------------


def validate_attempt_layout(
    work: str, ro: str, denied: str, secret: str, harness: str
) -> dict[str, str]:
    params = {"work": work, "ro": ro, "denied": denied, "secret": secret, "harness": harness}
    backend.build_profile(**params)
    return params


_ATTEMPT_ID_MAX = 64


def _validate_attempt_id(attempt_id: str) -> str:
    """Accept exactly one canonical path component; refuse everything else.

    Anything that could escape the authorized root (``..``, ``.``-prefixed,
    separators, control characters, NUL) or that is merely long is rejected.
    """
    if not isinstance(attempt_id, str) or not attempt_id:
        raise _fixed("attempt: empty attempt id")
    if len(attempt_id) > _ATTEMPT_ID_MAX:
        raise _fixed("attempt: attempt id too long")
    if attempt_id.startswith("."):
        raise _fixed("attempt: attempt id must be a plain name")
    if not attempt_id[0].isascii() or not attempt_id[0].isalnum():
        raise _fixed("attempt: attempt id must start with an ascii alphanumeric character")
    for ch in attempt_id:
        if ch in ("/", "\\") or ord(ch) < 0x20 or ord(ch) == 0x7F:
            raise _fixed("attempt: attempt id must be a single path component")
    return attempt_id


def _require_real_chain(target: Path, stop: Path | None = None, include_leaf: bool = True) -> None:
    """Every component from ``stop`` (inclusive) down to ``target`` must be a
    real directory.

    ``abspath`` normalisation never resolves symlinks, so the ``lstat`` of each
    prefix observes the node itself instead of whatever it may point at.  When
    ``stop`` is given (the operator-approved, already canonicalised sandbox
    root) the walk starts there: that root is the single documented
    ``/tmp`` -> ``/private/tmp`` alias resolution point.  ``include_leaf`` is
    false before creation, when the leaf is expected not to exist yet.
    """
    parts = target.parts
    if stop is not None:
        if len(parts) < len(stop.parts) or parts[: len(stop.parts)] != stop.parts:
            raise _fixed("attempt: path escapes the authorized root")
        start = len(stop.parts) - 1
    else:
        if target == Path(target.anchor):
            raise _fixed("attempt: cannot target the filesystem root")
        start = 0
    end = len(parts) if include_leaf else len(parts) - 1
    for index in range(start, end):
        st = _lstat(Path(*parts[: index + 1]))
        if st is None:
            raise _fixed("attempt: missing parent directory")
        if stat_module.S_ISLNK(st.st_mode) or not stat_module.S_ISDIR(st.st_mode):
            raise _fixed("attempt: symlink or non-directory in parent chain")


def ensure_attempt(
    attempt_root: Path,
    params: dict[str, str],
    authorized_root: Path | None = None,
) -> None:
    """Exclusively create the attempt tree; never reuse or follow symlinks.

    ``authorized_root`` is the operator-approved sandbox root already bound by
    ``_bind_roots``; it is canonicalised exactly once here.  Every component
    below it must be a real directory, checked before *and* after creation, and
    the attempt directory itself must not exist at all.  ``mkdir`` without
    ``exist_ok`` is the atomic exclusive create on POSIX.
    """
    base = Path(os.path.realpath(str(authorized_root))) if authorized_root is not None else None
    target = Path(os.path.abspath(str(attempt_root)))
    if base is not None and target.parent != base:
        raise _fixed("attempt: must be created directly under the authorized root")

    _require_real_chain(target, stop=base, include_leaf=False)
    leaf = _lstat(target)
    if leaf is not None:
        if stat_module.S_ISLNK(leaf.st_mode) or not stat_module.S_ISDIR(leaf.st_mode):
            raise _fixed("attempt: path exists and is not a real directory")
        raise _fixed("attempt: directory already exists")
    try:
        target.mkdir()
    except FileExistsError:
        raise _fixed("attempt: directory already exists") from None
    except OSError:
        raise _fixed("attempt: cannot create attempt directory") from None
    _require_real_chain(target, stop=base)

    for name, value in params.items():
        sub = target / name
        _exclusive_mkdirs(sub)
        # The profile parameters must describe the directories that really
        # exist now, not merely the strings the caller intended.
        if posixpath.normpath(str(sub)) != value:
            raise _fixed("attempt: profile params are not bound to the real subdirectories")
    for sub in ("deps", "profiles", "capture", "evidence", "state"):
        _exclusive_mkdirs(target / "harness" / sub)
    _exclusive_mkdirs(target / "ro" / "fixtures")
    state = {"attempt_id": target.name, "created_utc": _utc_now()}
    (target / "harness" / "state" / "attempt.json").write_text(json.dumps(state))


def _exclusive_mkdirs(path: Path) -> None:
    # parents=False: the parent chain was verified by _require_real_chain.
    try:
        path.mkdir(parents=False)
    except FileExistsError:
        raise _fixed("attempt: subdirectory already exists") from None
    except OSError:
        raise _fixed("attempt: cannot create subdirectory") from None
    st = _lstat(path)
    if st is None or stat_module.S_ISLNK(st.st_mode) or not stat_module.S_ISDIR(st.st_mode):
        raise _fixed("attempt: expected a real directory after mkdir")


# ---------------------------------------------------------------------------
# C1 boundary dependency export (bounded, object-backed, hash-verified)
# ---------------------------------------------------------------------------


def export_c1_dependency(
    repo: Path,
    commit: str,
    dest: Path,
    timeout: float = COMMAND_TIMEOUT,
    max_bytes: int = C1_MAX_BYTES,
) -> dict[str, Any]:
    """Export the frozen C1 boundary module from a read-only Git object.

    Reads ``<commit>:<path>`` via ``git cat-file blob`` (no shell, argv
    array) with a bounded reader thread: at most ``max_bytes`` bytes are
    buffered and any further byte terminates the read and marks the object
    as oversized (never an unbounded capture-then-truncate).  The write is
    verified by re-reading the on-disk file and comparing both sha256 and
    size.  On any failure the destination file is removed.  A code baseline
    without C1 (git object missing) is ``not_run``; a real object that
    exceeds the limit or fails verification is ``environment_failure``.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    argv = ["git", "-C", str(repo), "cat-file", "blob", f"{commit}:{C1_BOUNDARY_PATH}"]
    started = time.monotonic()
    buffers: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    exceeded = threading.Event()
    errors = threading.Event()
    done = {"stdout": False, "stderr": False}

    def reader(name: str, stream: Any, fileno: int, size_cap: int) -> None:
        try:
            while True:
                room = size_cap - len(buffers[name])
                if room <= 0:
                    break
                ready, _, _ = select.select([fileno], [], [], 0.01)
                if not ready:
                    continue
                chunk = os.read(fileno, min(4096, room + 1))
                if not chunk:
                    break
                stored = min(len(chunk), room)
                buffers[name].extend(chunk[:stored])
                if len(buffers[name]) >= size_cap:
                    exceeded.set()
                    break
        except OSError:
            if not done["stdout"] and not done["stderr"]:
                errors.set()
        finally:
            done[name] = True

    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            close_fds=True,
        )
    except OSError:
        return {
            "status": "not_run",
            "source_commit": commit,
            "path": C1_BOUNDARY_PATH,
            "reason": "git executable unavailable",
        }

    threads: list[threading.Thread] = []
    try:
        for name, stream in (("stdout", proc.stdout), ("stderr", proc.stderr)):
            if stream is None:
                done[name] = True
                continue
            os.set_blocking(stream.fileno(), False)
            thread = threading.Thread(
                target=reader, args=(name, stream, stream.fileno(), max_bytes), daemon=True
            )
            thread.start()
            threads.append(thread)
        status = "completed"
        while time.monotonic() - started < timeout:
            if exceeded.is_set():
                status = "output_limit"
                break
            if errors.is_set():
                status = "environment_failure"
                break
            if proc.poll() is not None and all(done.values()):
                status = "completed" if proc.returncode == 0 else "failed"
                break
            time.sleep(0.002)
        else:
            status = "timed_out"
        if status not in ("completed", "failed"):
            proc.kill()
        proc.wait(timeout=CANCELLATION_GRACE)
        for thread in threads:
            thread.join(timeout=CANCELLATION_GRACE / 2)
    finally:
        for stream in (proc.stdout, proc.stderr):
            if stream is not None:
                stream.close()

    if status == "output_limit" or len(buffers["stdout"]) > max_bytes:
        return {
            "status": "environment_failure",
            "source_commit": commit,
            "path": C1_BOUNDARY_PATH,
            "reason": "object exceeds byte limit",
        }
    if status != "completed":
        return {
            "status": "not_run" if status == "failed" else "environment_failure",
            "source_commit": commit,
            "path": C1_BOUNDARY_PATH,
            "reason": f"git object read {status}",
        }
    data = bytes(buffers["stdout"])
    source_sha = _sha256_bytes(data)
    dest.write_bytes(data)
    ondisk = _lstat(dest)
    if ondisk is None or (
        stat_module.S_ISLNK(ondisk.st_mode) or not stat_module.S_ISREG(ondisk.st_mode)
    ):
        dest.unlink(missing_ok=True)
        return {
            "status": "environment_failure",
            "source_commit": commit,
            "path": C1_BOUNDARY_PATH,
            "reason": "destination not a real file after write",
        }
    if ondisk.st_size != len(data):
        dest.unlink(missing_ok=True)
        return {
            "status": "environment_failure",
            "source_commit": commit,
            "path": C1_BOUNDARY_PATH,
            "reason": "size mismatch after write",
        }
    ondisk_sha = _sha256_file(dest)
    if source_sha != ondisk_sha:
        dest.unlink(missing_ok=True)
        return {
            "status": "environment_failure",
            "source_commit": commit,
            "path": C1_BOUNDARY_PATH,
            "reason": "hash mismatch after write",
        }
    return {
        "status": "ok",
        "source_commit": commit,
        "path": C1_BOUNDARY_PATH,
        "blob_sha256": source_sha,
        "file_sha256": ondisk_sha,
        "bytes": len(data),
    }


# ---------------------------------------------------------------------------
# Profile generation
# ---------------------------------------------------------------------------


def build_profiles(
    attempt: Path,
    params: dict[str, str],
    cases: list[dict[str, Any]],
    loopback_port: int | None = None,
) -> dict[str, str]:
    """Write one profile per case; same-target controls differ only by config.

    ``allow_target`` and ``allow_endpoint`` are declared on a case as an *area*
    name and a loopback marker respectively; they are resolved here into the
    single concrete file and endpoint the profile may additionally allow, so a
    control really differs from its refusal by exactly that one rule.
    """
    profiles_dir = attempt / "harness" / "profiles"
    written: dict[str, str] = {}
    for case in cases:
        area = case.get("allow_target")
        allow_target = None
        if area is not None:
            target = case.get("target")
            if target is None:
                raise _fixed("profile: allow_target requires a file target")
            allow_target = str(Path(params[area]) / target)
        allow_endpoint = None
        if case.get("allow_endpoint") is not None:
            if loopback_port is None:
                raise _fixed("profile: loopback control requires an authorized port")
            allow_endpoint = ("127.0.0.1", int(loopback_port))
        text = backend.build_profile(
            **params,
            allow_endpoint=allow_endpoint,
            allow_target=allow_target,
        )
        profile_path = profiles_dir / ("{}.profile".format(case["test_id"]))
        profile_path.write_text(text)
        written[case["test_id"]] = str(profile_path)
    return written


# ---------------------------------------------------------------------------
# Worker execution (independent watchdog; full-tree cleanup)
# ---------------------------------------------------------------------------


def _run_bounded_command(
    argv: list[str],
    cwd: str,
    env: dict[str, str],
    timeout: float,
    max_output: int,
    grace: float,
) -> dict[str, Any]:
    """Run one argv command with independent watchdog and bounded capture.

    The process is started in a new session so the whole tree can be
    cancelled; reader threads never block the watchdog; output storage is
    bounded (a single excess byte terminates the command); cancellation sends
    SIGTERM to the process group, waits the grace period, then SIGKILLs the
    tree and the root process, and the result records whether cleanup was
    confirmed.  This is pure orchestration: the *policy* of what to run is
    supplied by the caller, never by the worker.
    """
    started_at = time.monotonic()
    stdout: bytearray = bytearray()
    stderr: bytearray = bytearray()
    lock = threading.Lock()
    stop = threading.Event()
    done = {"stdout": False, "stderr": False}
    exceeded = threading.Event()
    errors = threading.Event()

    def reader(index: str, stream: Any) -> None:
        """Drain one pipe with a bounded buffer.

        Non-blocking reads; EAGAIN is a normal "no data yet" state and must
        never be treated as a failure.  EOF (a zero-byte read when data is
        actually available) marks the stream done.  A single byte beyond the
        shared output budget raises the overflow flag so the watchdog
        terminates the command immediately.
        """
        fileno = stream.fileno()
        os.set_blocking(fileno, False)
        try:
            while True:
                if stop.is_set():
                    break
                with lock:
                    room = max_output - (len(stdout) + len(stderr))
                if room < 0:
                    break
                if room == 0:
                    # Budget exhausted but no read issued: let the watchdog
                    # see the process state; overflow, if any, is caught on
                    # the next select.
                    select.select([fileno], [], [], 0.005)
                    continue
                ready, _, _ = select.select([fileno], [], [], 0.005)
                if not ready:
                    continue
                chunk = os.read(fileno, min(4096, room + 1))
                if not chunk:
                    break  # true EOF
                with lock:
                    space = max_output - (len(stdout) + len(stderr))
                    target = stdout if index == "stdout" else stderr
                    stored = min(len(chunk), max(0, space))
                    target.extend(chunk[:stored])
                    # The budget is the real overflow signal.  Note that a
                    # read of room+1 from a pipe with more data available
                    # returns exactly room bytes (the kernel never hands over
                    # the extra byte), so "chunk was truncated" can never
                    # fire here; the stored amount reaching the budget is
                    # what must trigger the watchdog.
                    if len(stdout) + len(stderr) >= max_output:
                        exceeded.set()
                        break
        except OSError:
            if not stop.is_set():
                errors.set()
        finally:
            done[index] = True

    try:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
    except OSError as exc:
        return {
            "started": False,
            "completed": False,
            "exit_code": None,
            "errno": exc.errno,
            "output_limited": False,
            "timed_out": False,
            "cancelled": False,
            "cleanup_confirmed": None,
            "duration_seconds": 0.0,
            "capture_bytes": 0,
            "note": exc.__class__.__name__,
        }

    threads = [
        threading.Thread(target=reader, args=("stdout", proc.stdout), daemon=True),
        threading.Thread(target=reader, args=("stderr", proc.stderr), daemon=True),
    ]
    for thread in threads:
        thread.start()

    status = "completed"
    cancellation_reason: str | None = None
    while True:
        if exceeded.is_set():
            status = "output_limit"
            cancellation_reason = "output_limit"
            break
        if errors.is_set():
            status = "environment_failure"
            break
        if time.monotonic() - started_at >= timeout:
            status = "timed_out"
            cancellation_reason = "timeout"
            break
        if all(done.values()) and proc.poll() is not None:
            status = "completed" if proc.returncode == 0 else "failed"
            break
        stop.wait(0.002)

    cleanup_confirmed: bool | None = None
    if status not in ("completed", "failed"):
        _kill_process_tree(proc, grace)
        cleanup_confirmed = None  # caller records the ps-observed confirmation
    if status == "output_limit":
        # bounded: do not wait for a process that exceeds the output budget
        _kill_process_tree(proc, grace)
        cleanup_confirmed = None

    stop.set()
    for thread in threads:
        thread.join(timeout=grace)
    # A reader that exits because of the stop flag (after cancellation) is
    # not a failure; only a reader still alive after the grace period is.
    if any(thread.is_alive() for thread in threads):
        if status not in ("environment_failure",):
            status = "environment_failure"
    # Always reap: a finished command must not leave a zombie behind, and the
    # cancellation path already waited, so this returns immediately.
    try:
        proc.wait(timeout=CANCELLATION_GRACE)
    except subprocess.TimeoutExpired:
        status = "environment_failure"
    with lock:
        captured = len(stdout) + len(stderr)
        stdout_text = stdout.decode("utf-8", "replace")
        stderr_text = stderr.decode("utf-8", "replace")
    exit_code = proc.returncode
    completed = status in ("completed", "failed") and exit_code is not None and exit_code >= 0
    duration = time.monotonic() - started_at
    return {
        "started": True,
        "pid": proc.pid,
        "completed": completed,
        "exit_code": exit_code,
        "errno": None,
        "output_limited": exceeded.is_set(),
        "timed_out": status == "timed_out",
        "cancellation_reason": cancellation_reason,
        "cancelled": status == "cancelled",
        "cleanup_confirmed": cleanup_confirmed,
        "duration_seconds": duration,
        "capture_bytes": captured,
        "argv": argv,
        "stdout_text": stdout_text,
        "stderr_text": stderr_text,
    }


def _kill_process_tree(proc: subprocess.Popen, grace: float) -> None:
    """Terminate then kill the whole process group; never other sessions."""
    import signal

    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        pass
    try:
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass
        if proc.poll() is None:
            proc.kill()
        try:
            proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            pass


def run_worker(
    profile_path: str,
    fixture: str,
    argv: list[str],
    cwd: str,
    env: dict[str, str],
    capture_path: Path,
    timeout: float = COMMAND_TIMEOUT,
    grace: float = CANCELLATION_GRACE,
) -> dict[str, Any]:
    """Run one fixed-fixture action under sandbox-exec with output capture.

    ``capture_path`` is written by the harness only; the Worker never receives
    a handle to it.  stdout+stderr are bounded at ``MAX_OUTPUT`` total; a
    single excess byte terminates the command and records ``output_limited``.
    Timeout is enforced by an independent watchdog loop, not by a pipe read.
    The result includes the real exit code (negative = killed by signal N on
    POSIX), whether the action completed, and the cancellation reason.
    """
    sandbox_argv = [SANDBOX_EXEC, "-f", profile_path, "--", fixture] + argv
    capture_path.parent.mkdir(parents=True, exist_ok=True)
    result = _run_bounded_command(
        sandbox_argv,
        cwd=cwd,
        env=env,
        timeout=timeout,
        max_output=MAX_OUTPUT,
        grace=grace,
    )
    # The harness writes the capture file; the Worker never receives a handle.
    if result.get("capture_bytes"):
        capture_path.write_bytes(result["stdout_text"].encode("utf-8"))
    else:
        capture_path.write_bytes(b"")
    return result


# ---------------------------------------------------------------------------
# Loopback control endpoint (harness-owned, single connection, bounded)
# ---------------------------------------------------------------------------


def run_loopback_control(
    port: int,
    connect_timeout: float,
    max_bytes: int,
    deadline: float,
) -> dict[str, Any]:
    """Serve one loopback connection inside ``deadline``; record the result.

    The listener is bound to 127.0.0.1 only, accepts a single connection,
    reads at most ``max_bytes``, and is closed and unbound at the end.  A
    background port that is already serving is *not* a valid refuse control:
    if the connect succeeds the listener was already closed, the result must
    be recorded as ``background_port`` and the observation is unknown.
    """
    socket_ = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    socket_.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        socket_.bind(("127.0.0.1", port))
        socket_.listen(1)
    except OSError:
        return {"served": False, "reason": "bind_failed"}
    try:
        socket_.settimeout(max(0.05, deadline))
        conn, _addr = socket_.accept()
    except OSError:
        return {"served": False, "reason": "no_connection"}
    received = 0
    try:
        conn.settimeout(connect_timeout)
        while received < max_bytes:
            chunk = conn.recv(min(4096, max_bytes - received))
            if not chunk:
                break
            received += len(chunk)
    except OSError:
        pass
    finally:
        conn.close()
        socket_.close()
    return {"served": True, "received_bytes": received}


# ---------------------------------------------------------------------------
# Process tree snapshot (attempt-correlated)
# ---------------------------------------------------------------------------


def process_tree(root_pid: int) -> dict[str, Any]:
    """Snapshot only the process tree that belongs to ``root_pid``.

    A pid is mandatory: without an attempt-correlated pid the function refuses
    instead of reading and persisting a machine-wide table.  Rows are kept
    only when they are the recorded pid itself or a descendant reached through
    ppid/pgid, and the returned ``alive`` flag comes from a direct signal-0
    probe rather than from ``ps`` merely succeeding.
    """
    if not isinstance(root_pid, int) or isinstance(root_pid, bool) or root_pid <= 1:
        return {"status": "unidentified", "rows": [], "alive": None, "root_pid": root_pid}
    argv = ["ps", "-axo", "pid=,ppid=,pgid=,stat=,lstart="]
    try:
        proc = subprocess.run(
            argv, capture_output=True, timeout=10, stdin=subprocess.DEVNULL, close_fds=True
        )
    except (OSError, subprocess.SubprocessError):
        return {
            "status": "unknown",
            "rows": [],
            "alive": None,
            "root_pid": root_pid,
            "observed_utc": _utc_now(),
        }
    if proc.returncode != 0:
        return {
            "status": "unknown",
            "rows": [],
            "alive": None,
            "root_pid": root_pid,
            "observed_utc": _utc_now(),
        }
    text = proc.stdout.decode("utf-8", "replace")
    rows = [line.strip() for line in text.splitlines() if line.strip()]
    parsed: list[tuple[int, int, int]] = []
    for row in rows:
        parts = row.split(None, 3)
        if len(parts) < 3:
            continue
        try:
            parsed.append((int(parts[0]), int(parts[1]), int(parts[2])))
        except ValueError:
            continue
    keep = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, ppid, pgid in parsed:
            if pid not in keep and (ppid in keep or pgid in keep):
                keep.add(pid)
                changed = True
    filtered = [
        row
        for row in rows
        if row.split(None, 1)[0].isdigit() and int(row.split(None, 1)[0]) in keep
    ]
    alive = _pid_alive(root_pid)
    return {
        "status": "ok",
        "root_pid": root_pid,
        "alive": alive,
        "rows": filtered[:256],
        "observed_utc": _utc_now(),
    }


# ---------------------------------------------------------------------------
# Evidence package lifecycle
# ---------------------------------------------------------------------------


_PACKAGE_SUFFIXES = (("evidence", ".json"), ("capture", ".log"))


def persist_package(
    source_attempt: Path,
    package_root: Path,
    test_ids: list[str],
) -> dict[str, Any]:
    """Copy produced capture/evidence into an exclusively created package root.

    The package root must not exist at all: any pre-existing directory (even
    one holding only dotfiles) is refused, so an attempt can never be reused or
    overwritten.  Sources follow the harness convention
    ``<test_id>.json`` / ``<test_id>.log``; an id with neither source is
    reported in ``missing`` instead of being silently skipped, and every copy is
    re-hashed after writing so a failed transfer keeps the package on disk
    rather than being reported as success.
    """
    st = _lstat(package_root)
    if st is not None:
        if stat_module.S_ISLNK(st.st_mode) or not stat_module.S_ISDIR(st.st_mode):
            raise _fixed("package: path exists and is not a real directory")
        raise _fixed("package: directory already exists")
    try:
        package_root.mkdir(parents=True)
    except FileExistsError:
        raise _fixed("package: directory already exists") from None
    except OSError:
        raise _fixed("package: cannot create package directory") from None
    (package_root / "evidence").mkdir()
    (package_root / "capture").mkdir()

    copied: dict[str, str] = {}
    missing: list[str] = []
    for test_id in test_ids:
        found = False
        for sub, suffix in _PACKAGE_SUFFIXES:
            source = source_attempt / "harness" / sub / f"{test_id}{suffix}"
            st_source = _lstat(source)
            if st_source is None or not stat_module.S_ISREG(st_source.st_mode):
                continue
            dest = package_root / sub / f"{test_id}{suffix}"
            shutil.copy2(source, dest)
            source_sha = _sha256_file(source)
            if _sha256_file(dest) != source_sha:
                raise _fixed("package: copy verification failed")
            copied[f"{sub}/{test_id}{suffix}"] = source_sha
            found = True
        if not found:
            missing.append(test_id)
    return {"copied": copied, "missing": missing, "package_root": str(package_root)}


def _verify_pre_cleanup(package_root: Path) -> dict[str, Any]:
    """Validate payload bytes, inventory and references *before* cleanup.

    ``evidence.verify_package`` cannot be used mid-lifecycle because the final
    ``CHECKSUMS.sha256`` only exists after finalization, so the same structural
    checks are applied directly.  Any failure propagates and leaves the attempt
    tree untouched for inspection.
    """
    manifest = evidence._load_manifest(package_root)
    evidence._check_payload_files(package_root, manifest)
    evidence._check_inventory(package_root, manifest)
    evidence._check_references(package_root, manifest)
    return manifest


def _write_manifest_files(package_root: Path, include_cleanup: bool) -> None:
    """Write manifest.json (and CHECKSUMS.sha256 when finalized).

    ``manifest.json`` never lists itself or ``CHECKSUMS.sha256``.  The
    pre-cleanup snapshot additionally excludes ``cleanup.json`` and itself, so
    re-running this stage can never record a stale size/hash for the file it is
    about to overwrite.  Finalization does list both, because by then they are
    final and immutable.
    """
    entries: list[dict[str, Any]] = []
    excluded = {"manifest.json", "CHECKSUMS.sha256"}
    if not include_cleanup:
        excluded |= {"cleanup.json", "pre-cleanup-manifest.json"}
    for path in sorted(package_root.rglob("*")):
        st = _lstat(path)
        if st is None or stat_module.S_ISLNK(st.st_mode) or not stat_module.S_ISREG(st.st_mode):
            continue
        rel = posixpath.normpath(str(path.relative_to(package_root)))
        if rel in excluded:
            continue
        entries.append({"path": rel, "sha256": _sha256_file(path), "bytes": path.stat().st_size})
    manifest = {"schema_version": 1, "files": entries}
    raw = json.dumps(manifest, indent=2).encode("utf-8")
    if include_cleanup:
        # final stage: the pre-cleanup snapshot is already immutable and is
        # listed in the final manifest, so it must not be rewritten here
        (package_root / "manifest.json").write_bytes(raw)
        (package_root / "CHECKSUMS.sha256").write_text(_sha256_bytes(raw) + "  manifest.json\n")
    else:
        (package_root / "pre-cleanup-manifest.json").write_bytes(raw)
        (package_root / "manifest.json").write_bytes(raw)


def finalize_package(package_root: Path, cleanup_results: dict[str, Any]) -> None:
    """Write cleanup.json (real results only) then final manifest + CHECKSUMS.

    ``cleanup_results`` must come from the real deletion of the exact attempt
    directory (``rm -rf <exact path>`` followed by ``lstat`` ENOENT) and
    contains ``cleanup_argv``, ``cleanup_exit_code``,
    ``post_cleanup_ls_output``, ``cleanup_enoent_confirmed`` (bool from the
    real lstat) and ``cleanup_timestamp_utc``.  A missing or unconfirmed
    ENOENT is recorded as such; the pre-cleanup manifest sha is included, the
    final manifest sha is not (no self-reference).
    """
    required = (
        "cleanup_argv",
        "cleanup_exit_code",
        "post_cleanup_ls_output",
        "cleanup_enoent_confirmed",
        "cleanup_timestamp_utc",
    )
    for key in required:
        if key not in cleanup_results:
            raise _fixed(f"cleanup: missing {key}")
    if not isinstance(cleanup_results["cleanup_enoent_confirmed"], bool):
        raise _fixed("cleanup: enoent flag must be a real bool")
    cleanup = {
        "attempt_id": package_root.name,
        **{key: cleanup_results[key] for key in required},
        "pre_cleanup_manifest_sha256": _sha256_file(package_root / "pre-cleanup-manifest.json"),
    }
    (package_root / "cleanup.json").write_text(json.dumps(cleanup, indent=2))
    _write_manifest_files(package_root, include_cleanup=True)


def verify_package_offline(package_root: Path) -> dict:
    return evidence.verify_package(package_root)


# ---------------------------------------------------------------------------
# Honest reporting
# ---------------------------------------------------------------------------


def build_report(
    attempt_id: str,
    approved: bool,
    platform: str,
    cases: list[dict[str, Any]] | None = None,
    case_ids: list[str] | None = None,
    provider: str = "unrecorded",
) -> dict[str, Any]:
    """Build the honest top-level report.  Without approval: ``not_run``.

    ``provider`` records who actually executed the harness and defaults to
    ``unrecorded`` -- it is never filled in with a guess.  ``platform_capability``
    stays ``unknown`` (never ``full``) when the probe did not run on the real
    host, and the overall summary may then only be ``partial`` at best.
    """
    cases = cases or []
    if case_ids:
        cases = [
            {
                "test_id": case_id,
                "status": "out_of_scope" if case_id == "T4" else "unknown",
            }
            for case_id in case_ids
        ]
    report = {
        "attempt_id": attempt_id,
        "generated_utc": _utc_now(),
        "platform": platform,
        "approved": approved,
        "live_execution": False,
        "provider": provider,
        "status": "not_run" if not approved else "planned",
        "platform_capability": "unknown",
        "summary": "partial",
        "cases": [dict(case) for case in cases],
        "cases_by_id": {case["test_id"]: dict(case) for case in cases if case.get("test_id")},
    }
    return report


# ---------------------------------------------------------------------------
# Full orchestration
# ---------------------------------------------------------------------------

# Probe definitions for the required sub-items.  Every ``refuse`` probe runs
# twice with the *same* fixture, argv, cwd and target: once under the
# default-deny profile and once under a profile whose only difference is the
# single ``allow_target`` / ``allow_endpoint`` control.  The control verdict is
# what turns a non-zero exit into evidence of a real refusal instead of a
# crash, a missing file, or a background port that was never listening.
_PROBES: list[dict[str, Any]] = [
    {
        "id": "T1-work-write",
        "group": "T1",
        "kind": "positive",
        "action": "write",
        "area": "work",
        "target": "sentinel-work.txt",
    },
    {
        "id": "T1-sentinel-agents",
        "group": "T1",
        "kind": "refuse",
        "action": "write",
        "area": "denied",
        "target": "AGENTS.md",
    },
    {
        "id": "T1-sentinel-git",
        "group": "T1",
        "kind": "refuse",
        "action": "write",
        "area": "denied",
        "target": ".git/config",
    },
    {
        "id": "T1-sentinel-protected",
        "group": "T1",
        "kind": "refuse",
        "action": "write",
        "area": "denied",
        "target": "tests/protected/test_contract.py",
    },
    {
        "id": "T2-control-read",
        "group": "T2",
        "kind": "positive",
        "action": "read",
        "area": "ro",
        "target": "fixtures/seatbelt_probe.py",
    },
    {
        "id": "T2-secret-env",
        "group": "T2",
        "kind": "refuse",
        "action": "read",
        "area": "secret",
        "target": ".env",
    },
    {
        "id": "T2-secret-auth",
        "group": "T2",
        "kind": "refuse",
        "action": "read",
        "area": "secret",
        "target": "auth.json",
    },
    {"id": "T3-connect", "group": "T3", "kind": "refuse", "action": "connect", "area": "loopback"},
    {"id": "T5-env-names", "group": "T5", "kind": "positive", "action": "env", "area": "none"},
    {
        "id": "T6-child-normal",
        "group": "T6",
        "kind": "positive",
        "action": "child",
        "area": "work",
        "depth": 2,
    },
    {
        "id": "T6-timeout-cancel",
        "group": "T6",
        "kind": "timeout_cleanup",
        "action": "timeout",
        "area": "none",
    },
]


def _build_cases() -> list[dict[str, Any]]:
    """Expand the probe definitions into the executable case list."""
    cases: list[dict[str, Any]] = []
    for probe in _PROBES:
        base = {
            "group": probe["group"],
            "action": probe["action"],
            "area": probe["area"],
            "target": probe.get("target"),
            "depth": probe.get("depth"),
            "paired_control": None,
        }
        if probe["kind"] == "refuse":
            cases.append(
                {
                    **base,
                    "test_id": probe["id"],
                    "test_kind": "expected_refuse",
                    "allow_target": None,
                    "allow_endpoint": None,
                    "paired_control": f"{probe['id']}-control",
                }
            )
            cases.append(
                {
                    **base,
                    "test_id": f"{probe['id']}-control",
                    "test_kind": "positive",
                    # a control differs from its refusal by exactly one rule:
                    # the single synthetic file, or the loopback endpoint
                    "allow_target": (
                        probe["area"] if probe["area"] in ("denied", "secret") else None
                    ),
                    "allow_endpoint": "loopback" if probe["area"] == "loopback" else None,
                }
            )
        elif probe["kind"] == "timeout_cleanup":
            cases.append(
                {
                    **base,
                    "test_id": probe["id"],
                    "test_kind": "timeout_cleanup",
                    "allow_target": None,
                    "allow_endpoint": None,
                }
            )
        else:
            cases.append(
                {
                    **base,
                    "test_id": probe["id"],
                    "test_kind": "positive",
                    "allow_target": None,
                    "allow_endpoint": None,
                }
            )
    return cases


_CASES: list[dict[str, Any]] = _build_cases()


def _not_run_result(attempt_id: str, reason: str, platform: str, provider: str) -> dict[str, Any]:
    return {
        "status": "not_run",
        "reason": reason,
        "attempt_id": attempt_id,
        "platform": platform,
        "paths_created": [],
        "listeners": [],
        "sandbox_exec_invocations": 0,
        "report": build_report(
            attempt_id=attempt_id,
            approved=False,
            platform=platform,
            provider=provider,
            case_ids=["T1", "T2", "T3", "T5", "T6", "T4", "T7"],
        ),
    }


def _prepare_targets(attempt_root: Path, params: dict[str, str], fixture: Path) -> None:
    """Create the synthetic sentinels every probe acts on.

    All targets live inside the attempt tree; nothing outside the approved
    write root is ever created or probed.  The read-only area receives a copy
    of the frozen fixture so the ``ro`` positive control reads real bytes.
    """
    layout = {
        "work": ["sentinel-work.txt"],
        "denied": ["AGENTS.md", ".git/config", "tests/protected/test_contract.py"],
        "secret": [".env", "auth.json"],
    }
    for area, names in layout.items():
        base = Path(params[area])
        for name in names:
            path = base / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"synthetic-sentinel\n")
    fixture_dest = Path(params["ro"]) / "fixtures" / fixture.name
    fixture_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(fixture, fixture_dest)


def _target_path(case: dict[str, Any], params: dict[str, str]) -> Path | None:
    """Resolve the on-disk target of a case, or ``None`` when it has none."""
    area = case["area"]
    target = case.get("target")
    if target is None or area == "none":
        return None
    return Path(params[area]) / target


def _digest_or_none(path: Path | None) -> str | None:
    st = _lstat(path) if path is not None else None
    if st is None or stat_module.S_ISLNK(st.st_mode) or not stat_module.S_ISREG(st.st_mode):
        return None
    return _sha256_file(path)


def _pid_alive(pid: int | None) -> bool | None:
    """Identity-bound liveness probe: ``None`` when the pid is unusable."""
    if pid is None or pid <= 1:
        return None
    import errno as errno_module

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as exc:
        return True if exc.errno == errno_module.EPERM else None
    return True


def _cleanup_state(result: dict[str, Any]) -> bool | None:
    """Three-state cleanup verdict bound to the recorded worker identity.

    ``True`` only when the pid that the harness actually started is confirmed
    gone by a direct signal-0 probe; a successful ``ps`` run with an empty table
    alone is never treated as proof.
    """
    return _pid_alive(result.get("pid"))


def run(
    authorization_file: Path,
    attempt_id: str,
    output_root: Path,
    fixture_path: Path | None = None,
    bundle_dir: Path | None = None,
    provider: str = "unrecorded",
) -> dict[str, Any]:
    """Gate + execute the full synthetic matrix.

    Fail-closed order (each stage refuses before the next side effect):
      1. the host platform must really be darwin (there is no override hook);
      2. the frozen bundle sha must be resolvable from a real handoff file;
      3. the authorization file must be a real regular file whose recorded
         contract digest matches that sha exactly;
      4. the recorded roots and the attempt id must bind to the real locations;
      5. only then are paths created, and only then does anything execute.

    After authorization the harness creates the attempt tree, exports and
    actually loads the frozen C1 dependency, writes one profile per case, runs
    every case (same-target control and a harness-owned loopback listener where
    applicable) with bounded capture and an independent watchdog, classifies
    each sub-item through ``backend.classify_case`` paired with its control,
    summarizes through ``backend.summarize_results``, persists the evidence
    package, verifies every produced reference, performs the real cleanup of
    the exact attempt directory, finalizes the package and reports honestly.
    """
    import platform as platform_module

    real_platform = platform_module.system().lower()
    if real_platform != AUTHORIZED_PLATFORM:
        return _not_run_result(attempt_id, "platform_not_darwin", real_platform, provider)

    expected = _resolve_expected_bundle_sha(bundle_dir)
    if expected is None:
        return _not_run_result(attempt_id, "contract_bundle_unavailable", real_platform, provider)

    if (
        not _lstat(authorization_file)
        or authorization_file.is_symlink()
        or not authorization_file.is_file()
    ):
        return _not_run_result(attempt_id, "authorization_missing", real_platform, provider)
    try:
        auth = load_authorization(authorization_file, expected_bundle_sha=expected)
    except ValueError:
        return _not_run_result(attempt_id, "authorization_invalid", real_platform, provider)

    try:
        sandbox_root = _bind_roots(auth, output_root, attempt_id)
    except ValueError:
        return _not_run_result(attempt_id, "roots_not_bound", real_platform, provider)

    persistence_root = Path(os.path.abspath(str(output_root)))
    loopback_port = int(auth["loopback"]["port"])
    connect_timeout = float(auth["loopback"]["connect_timeout_s"])
    max_bytes = int(auth["loopback"]["max_bytes"])

    fixture = Path(fixture_path) if fixture_path else _default_fixture()
    if not fixture.is_file() or fixture.is_symlink():
        return _not_run_result(attempt_id, "fixture_unavailable", real_platform, provider)

    # --- attempt tree (exclusive, real directories only) ---
    attempt_root = sandbox_root / attempt_id
    params = {
        "work": str(attempt_root / "work"),
        "ro": str(attempt_root / "ro"),
        "denied": str(attempt_root / "denied"),
        "secret": str(attempt_root / "secret"),
        "harness": str(attempt_root / "harness"),
    }
    paths_created: list[str] = []
    try:
        ensure_attempt(attempt_root, params, authorized_root=sandbox_root)
    except ValueError:
        return _not_run_result(attempt_id, "attempt_creation_refused", real_platform, provider)
    paths_created.append(str(attempt_root))

    env = dict(os.environ)
    env.update(
        {
            "M2C2A_ATTEMPT_ID": attempt_id,
            "M2C2A_SYNTHETIC": "1",
            "M2C2A_WORK": params["work"],
            "M2C2A_RO": params["ro"],
            "M2C2A_DENIED": params["denied"],
            "M2C2A_SECRET": params["secret"],
            "M2C2A_LOOPBACK_PORT": str(loopback_port),
        }
    )

    package_root = persistence_root / attempt_id
    records: list[dict[str, Any]] = []
    listeners: list[dict[str, Any]] = []
    invocations = 0
    package_record: dict[str, Any] = {"copied": {}, "missing": []}
    c1: dict[str, Any] = {"status": "not_run"}
    summary_value = "partial"
    verdicts: dict[str, str] = {}
    failure: str | None = None

    try:
        c1 = export_c1_dependency(
            Path(__file__).resolve().parents[3],
            C1_BOUNDARY_COMMIT,
            attempt_root / "harness" / "deps" / "boundary.py",
        )
        if c1.get("status") == "ok":
            c1["loaded"] = _load_c1_dependency(
                c1, attempt_root / "harness" / "deps" / "boundary.py"
            )
        _prepare_targets(attempt_root, params, fixture)
        written = build_profiles(attempt_root, params, _CASES, loopback_port=loopback_port)

        for case in _CASES:
            record = _run_case(
                case=case,
                attempt_root=attempt_root,
                params=params,
                profile=written[case["test_id"]],
                fixture=str(fixture),
                env=env,
                loopback_port=loopback_port,
                connect_timeout=connect_timeout,
                max_bytes=max_bytes,
            )
            records.append(record)
            invocations += 1
            if record.get("listener") is not None:
                listeners.append(record["listener"])

        verdicts = _classify_records(records)
        for record in records:
            record["verdict"] = verdicts[record["test_id"]]
        summary_value = backend.summarize_results(_group_results(verdicts))

        # Persist before cleanup: the package must exist and every produced
        # reference must verify before the attempt tree may be deleted.
        package_record = persist_package(attempt_root, package_root, [c["test_id"] for c in _CASES])
        paths_created.append(str(package_root))
        _write_summary(package_root, records)
        _write_manifest_files(package_root, include_cleanup=False)
        _verify_pre_cleanup(package_root)
    except ValueError as exc:
        failure = f"persistence_refused: {exc}"
    except OSError as exc:
        failure = f"environment_failure: {exc.__class__.__name__}"
    finally:
        cleanup = _clean_attempt(attempt_root)
        cancel_record = next((r for r in records if r["test_kind"] == "timeout_cleanup"), None)
        cleanup_state = _cleanup_state(cancel_record["worker"]) if cancel_record else None
        # Finalization only happens over a package that really exists and was
        # verified before cleanup; otherwise the half-written package is left
        # on disk for inspection instead of being sealed into a delivery.
        finalized = False
        if (package_root / "pre-cleanup-manifest.json").is_file():
            try:
                finalize_package(package_root, cleanup)
                finalized = True
            except (ValueError, OSError) as exc:
                failure = failure or f"finalization_refused: {exc}"
        report = build_report(
            attempt_id=attempt_id,
            approved=True,
            platform=real_platform,
            provider=provider,
            cases=[{"test_id": r["test_id"], "status": r["verdict"]} for r in records],
            case_ids=["T1", "T2", "T3", "T5", "T6", "T4", "T7"],
        )
        # A full pass is only possible when the whole matrix ran on the real
        # host and no sub-item is unknown; offline or partial evidence stays
        # partial and is never upgraded into an enforcement claim.
        report["platform_capability"] = "full" if summary_value == "full_pass" else "partial"
        report["summary"] = summary_value
        report["status"] = "completed" if failure is None else "partial"
        report["failure"] = failure
        report["c1_dependency"] = c1
        report["paths_created"] = paths_created
        report["listeners"] = listeners
        report["sandbox_exec_invocations"] = invocations
        report["process_tree"] = {
            "status": "recorded_per_case",
            "note": "each case carries only the tree of the pid this harness started",
            "cases_with_tree": [r["test_id"] for r in records if r.get("process_tree")],
        }
        report["records"] = records
        report["package"] = {**package_record, "finalized": finalized}
        report["cleanup"] = cleanup
        report["cleanup_state"] = cleanup_state
    return report


def _write_summary(package_root: Path, records: list[dict[str, Any]]) -> None:
    """Write the package index; every reference is relative to the package root."""
    index = []
    for record in records:
        entry: dict[str, Any] = {"test_id": record["test_id"]}
        if record.get("capture_file"):
            entry["record_ref"] = f"evidence/{record['test_id']}.json"
            entry["capture_file"] = record["capture_file"]
            entry["capture_sha256"] = record["capture_sha256"]
        index.append(entry)
    (package_root / "summary.json").write_text(json.dumps(index, indent=2))


def _group_results(verdicts: dict[str, str]) -> dict[str, Any]:
    """Map per-case verdicts onto the T1..T7 summary schema.

    ``T4`` is the fixed out-of-scope MCP sub-item and ``T7`` is filled by an
    independent fresh reviewer, so it stays ``unknown`` here and keeps the
    overall result at ``partial`` no matter what the probe observed.
    """
    grouped: dict[str, list[str]] = {"T1": [], "T2": [], "T3": [], "T5": [], "T6": []}
    for case in _CASES:
        grouped[case["group"]].append(verdicts[case["test_id"]])
    grouped["T4"] = "out_of_scope"
    grouped["T7"] = "unknown"
    return grouped


def _default_fixture() -> Path:
    return Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "seatbelt_probe.py"


def _bind_roots(auth: dict, output_root: Path, attempt_id: str) -> Path:
    """Bind the recorded roots and the attempt id to the real locations.

    The persistence root recorded by the operator must be the very directory
    the caller passed as ``--output-root`` (both sides canonicalised), the
    attempt id must be a single canonical component, and the sandbox root must
    exist as a real, non-symlinked directory.  Returns the canonical sandbox
    root used as the exclusive-creation anchor.
    """
    _validate_attempt_id(attempt_id)
    canonical_output = Path(os.path.abspath(str(output_root))).resolve()
    recorded_persistence = posixpath.normpath(auth["roots"]["persistence_root"])
    if Path(recorded_persistence).resolve() != canonical_output:
        raise _fixed("roots: recorded persistence_root does not match the real output root")
    sandbox = Path(os.path.abspath(auth["roots"]["sandbox_root"]))
    st = _lstat(sandbox)
    if st is None or not stat_module.S_ISDIR(st.st_mode):
        raise _fixed("roots: sandbox_root must be an existing real directory")
    if stat_module.S_ISLNK(st.st_mode):
        raise _fixed("roots: sandbox_root must not be a symlink")
    # The recorded root itself is canonicalised exactly once.  This is the
    # documented macOS alias point (``/tmp`` -> ``/private/tmp``); every path
    # below it must then be free of symlinked components.
    return Path(os.path.realpath(str(sandbox)))


def _clean_attempt(attempt_root: Path) -> dict[str, Any]:
    """Delete the exact attempt directory and confirm ENOENT with lstat."""
    try:
        proc = subprocess.run(
            ["rm", "-rf", str(attempt_root)],
            capture_output=True,
            timeout=COMMAND_TIMEOUT,
            stdin=subprocess.DEVNULL,
            close_fds=True,
        )
    except (OSError, subprocess.SubprocessError):
        proc = None
    exit_code = proc.returncode if proc is not None else None
    st = _lstat(attempt_root)
    enoent = st is None
    ls_output = ""
    try:
        ls_proc = subprocess.run(
            ["ls", str(attempt_root.parent)],
            capture_output=True,
            timeout=10,
            stdin=subprocess.DEVNULL,
            close_fds=True,
        )
        ls_output = ls_proc.stdout.decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError):
        ls_output = ""
    return {
        "cleanup_argv": ["rm", "-rf", str(attempt_root)],
        "cleanup_exit_code": exit_code,
        "post_cleanup_ls_output": ls_output,
        "cleanup_enoent_confirmed": enoent,
        "cleanup_timestamp_utc": _utc_now(),
    }


def _load_c1_dependency(export: dict[str, Any], dest: Path) -> dict[str, Any]:
    """Load the exported C1 module by explicit file location via importlib.

    ``sys.path`` is never touched.  The digest recorded at export time is
    re-checked against the bytes on disk immediately before loading, and any
    failure is reported rather than swallowed.
    """
    if export.get("status") != "ok":
        return {"loaded": False, "reason": "dependency was not exported"}
    try:
        import importlib.util

        if _sha256_file(dest) != export.get("file_sha256"):
            return {"loaded": False, "reason": "dependency hash changed after export"}
        spec = importlib.util.spec_from_file_location("m2c2a_c1_boundary", dest)
        if spec is None or spec.loader is None:
            return {"loaded": False, "reason": "no loader for the exported dependency"}
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except (OSError, ImportError, SyntaxError, ValueError, TypeError, AttributeError) as exc:
        return {"loaded": False, "reason": exc.__class__.__name__}
    return {
        "loaded": True,
        "module": getattr(module, "__name__", "unknown"),
        "has_verify_package": callable(getattr(module, "verify_package", None)),
    }


def _run_case(
    *,
    case: dict[str, Any],
    attempt_root: Path,
    params: dict[str, str],
    profile: str,
    fixture: str,
    env: dict[str, str],
    loopback_port: int,
    connect_timeout: float,
    max_bytes: float,
) -> dict[str, Any]:
    """Run one case and record everything the classifier needs.

    A harness-owned loopback listener is started *before* the worker and joined
    after it for both the refused and the controlled case, so a successful
    connect can only mean the endpoint really existed.  The target digest is
    sampled before and after the action so a refusal is judged on observable
    effect rather than on the exit code alone.
    """
    test_id = case["test_id"]
    area = case["area"]
    target = _target_path(case, params)

    argv = ["--action", case["action"]]
    if target is not None:
        argv += ["--target", str(target)]
    if area == "loopback":
        argv += ["--host", "127.0.0.1", "--port", str(loopback_port)]
    if case.get("depth") is not None:
        argv += ["--depth", str(case["depth"])]

    worker_env = dict(env)
    if case.get("allow_target") is not None and target is not None:
        worker_env["M2C2A_ALLOW_TARGET"] = str(target)

    before = _digest_or_none(target)

    listener: dict[str, Any] | None = None
    listener_thread: threading.Thread | None = None
    listener_box: dict[str, Any] = {}
    if area == "loopback":

        def _serve() -> None:
            listener_box["result"] = run_loopback_control(
                port=loopback_port,
                connect_timeout=connect_timeout,
                max_bytes=max_bytes,
                deadline=connect_timeout + COMMAND_TIMEOUT,
            )

        listener_thread = threading.Thread(target=_serve, daemon=True)
        listener_thread.start()

    capture_path = attempt_root / "harness" / "capture" / f"{test_id}.log"
    evidence_path = attempt_root / "harness" / "evidence" / f"{test_id}.json"

    result = run_worker(
        profile_path=profile,
        fixture=fixture,
        argv=argv,
        cwd=params["work"],
        env=worker_env,
        capture_path=capture_path,
        # The fixture's timeout case sleeps 30s; the watchdog must terminate it
        # well inside that, because those sub-items expect cancellation.
        timeout=min(COMMAND_TIMEOUT, 5.0),
    )

    if listener_thread is not None:
        listener_thread.join(timeout=CANCELLATION_GRACE)
        listener = listener_box.get("result")
        if not isinstance(listener, dict):
            # The listener never reported: the endpoint cannot be treated as
            # having existed, so any connect claim for this case is unknown.
            listener = {"served": False, "reason": "listener_not_reported"}

    # Capture only this attempt's own tree, correlated to the pid the harness
    # actually started, so cancellation evidence never depends on a
    # machine-wide ps table.
    tree = process_tree(result.get("pid")) if result.get("pid") else None
    if isinstance(tree, dict) and tree.get("status") == "unidentified":
        tree = None

    after = _digest_or_none(target)

    fixture_report: dict[str, Any] = {}
    capture_text = (
        capture_path.read_bytes().decode("utf-8", "replace") if capture_path.is_file() else ""
    )
    for line in capture_text.splitlines():
        try:
            parsed = json.loads(line)
        except ValueError:
            continue
        if isinstance(parsed, dict) and "action" in parsed:
            fixture_report = parsed
            break

    record: dict[str, Any] = {
        "test_id": test_id,
        "group": case["group"],
        "test_kind": case["test_kind"],
        "action": case["action"],
        "area": area,
        "target": str(target) if target is not None else None,
        "allow_target": case.get("allow_target"),
        "allow_endpoint": case.get("allow_endpoint"),
        "paired_control": case.get("paired_control"),
        "argv": argv,
        "cwd": params["work"],
        "worker": result,
        "fixture": fixture_report,
        "listener": listener,
        "process_tree": tree,
        "target_sha256_before": before,
        "target_sha256_after": after,
        "profile_sha256": _sha256_file(Path(profile)) if Path(profile).is_file() else None,
        "recorded_utc": _utc_now(),
    }
    if fixture_report:
        record["capture_file"] = f"capture/{test_id}.log"
        record["capture_sha256"] = _sha256_file(capture_path)
    evidence_path.write_text(json.dumps(record, indent=2))
    return record


def _classify_records(records: list[dict[str, Any]]) -> dict[str, str]:
    """Classify every case through the frozen backend policy.

    A refusal is only a pass when its same-action/same-target control really
    passed; otherwise the exit code proves nothing and the sub-item stays
    ``unknown``.
    """
    verdicts: dict[str, str] = {}
    for record in records:
        verdicts[record["test_id"]] = "unknown"
    for record in records:
        control_id = record.get("paired_control")
        control_verdict = verdicts.get(control_id, "unknown") if control_id else "unknown"
        verdicts[record["test_id"]] = backend.classify_case(
            _case_for_classifier(record, control_verdict)
        )
    return verdicts


def _case_for_classifier(record: dict[str, Any], control_verdict: str) -> dict[str, Any]:
    """Map a harness record onto the exact ``classify_case`` input schema."""
    worker = record["worker"]
    fixture_report = record["fixture"] or {}
    before = record.get("target_sha256_before")
    after = record.get("target_sha256_after")
    has_file_target = record.get("target") is not None

    if record["test_kind"] == "timeout_cleanup":
        return {
            "test_kind": "timeout_cleanup",
            "action_exit_code": worker.get("exit_code"),
            "action_errno": None,
            "action_started": bool(worker.get("started")),
            "action_completed": bool(worker.get("completed")),
            "effect_observed": False,
            # The watchdog itself is the control: it fired and terminated the
            # command instead of waiting for it to finish.
            "control_passed": bool(worker.get("timed_out")),
            "target_unchanged": None,
            "cleanup_confirmed": worker.get("cleanup_confirmed"),
            "output_limited": bool(worker.get("output_limited")),
            "observation_complete": not worker.get("output_limited", False),
        }

    if record["test_kind"] == "positive":
        return {
            "test_kind": "positive",
            "action_exit_code": worker.get("exit_code"),
            "action_errno": fixture_report.get("errno"),
            "action_started": bool(worker.get("started")),
            "action_completed": bool(worker.get("completed")),
            "effect_observed": bool(fixture_report.get("effect")),
            "control_passed": True,
            "target_unchanged": _target_unchanged(before, after, has_file_target),
            "cleanup_confirmed": None,
            "output_limited": bool(worker.get("output_limited")),
            "observation_complete": not worker.get("output_limited", False)
            and not worker.get("stderr_text", ""),
        }

    # expected_refuse
    effect = bool(fixture_report.get("effect"))
    changed = has_file_target and before is not None and after is not None and before != after
    return {
        "test_kind": "expected_refuse",
        "action_exit_code": worker.get("exit_code"),
        "action_errno": fixture_report.get("errno"),
        "action_started": bool(worker.get("started")),
        "action_completed": bool(worker.get("completed")),
        "effect_observed": effect or changed,
        "control_passed": control_verdict == "pass",
        "target_unchanged": _target_unchanged(before, after, has_file_target),
        "cleanup_confirmed": None,
        "output_limited": bool(worker.get("output_limited")),
        "observation_complete": not worker.get("output_limited", False)
        and not worker.get("stderr_text", ""),
    }


def _target_unchanged(before: str | None, after: str | None, has_file_target: bool) -> bool | None:
    """Three-state target observation: network cases have no file to compare."""
    if not has_file_target:
        return None
    if before is None or after is None:
        return None
    return before == after


def _resolve_expected_bundle_sha(bundle_dir: Path | None = None) -> str | None:
    """Resolve the frozen handoff ``bundle_sha256`` (fail closed when absent).

    ``bundle_dir`` is the operator-exported contract bundle directory; when it is
    not supplied the documented sibling export next to the checkout is used.
    This only ever *reads* a digest that is then compared against the operator
    authorization -- it never approves anything by itself, and a missing or
    unreadable bundle resolves to ``None`` so every caller refuses.
    """
    if bundle_dir is not None:
        handoff = Path(bundle_dir) / "handoff.json"
    else:
        try:
            checkout_root = Path(__file__).resolve().parents[3]
        except IndexError:
            return None
        handoff = checkout_root.parent / "M2C2A-v1-contract" / "handoff.json"
    st = _lstat(handoff)
    if st is None or stat_module.S_ISLNK(st.st_mode) or not stat_module.S_ISREG(st.st_mode):
        return None
    try:
        sha = json.loads(handoff.read_text(encoding="utf-8"))["bundle_sha256"]
    except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(sha, str) or len(sha) != 64:
        return None
    return sha


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="supervisor.workers.preflight",
        description="Trusted M2-C2A synthetic preflight harness (offline-safe).",
    )
    parser.add_argument("--authorization-file", required=True, type=Path)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--fixture", default=None, type=Path, help="Fixed probe fixture path.")
    parser.add_argument(
        "--contract-bundle",
        default=None,
        type=Path,
        help="Directory of the exported frozen handoff bundle (read-only, never committed).",
    )
    parser.add_argument(
        "--provider",
        default="unrecorded",
        help="Provenance label recorded verbatim in the report; approves nothing.",
    )
    args = parser.parse_args(argv)

    result = run(
        authorization_file=args.authorization_file,
        attempt_id=args.attempt_id,
        output_root=args.output_root,
        fixture_path=args.fixture,
        bundle_dir=args.contract_bundle,
        provider=args.provider,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in ("not_run", "completed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
