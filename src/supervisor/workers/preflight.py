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
import sys
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
    # Two distinct endpoints are required: the control endpoint that a profile
    # may allow, and the refused endpoint that must exist and stay denied.  A
    # single port cannot produce both halves of the T3 comparison.
    ports: list[int] = []
    for key in ("control_port", "refused_port"):
        port = loopback.get(key)
        if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
            raise _fixed("authorization: loopback port out of range")
        ports.append(port)
    if ports[0] == ports[1]:
        raise _fixed("authorization: loopback endpoints must be distinct")
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
    refused_port: int | None = None,
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
        marker = case.get("allow_endpoint")
        if marker == "control" and loopback_port is not None:
            allow_endpoint = ("127.0.0.1", int(loopback_port))
        elif marker == "refused":
            # The refused endpoint exists and has a real listener, but the
            # default-deny profile must not be widened to reach it.
            if refused_port is None:
                raise _fixed("profile: refused endpoint requires an authorized port")
            allow_endpoint = None
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


def _pid_identity(pid: int, wait: float = 0.0) -> dict[str, Any] | None:
    """Start-identity snapshot used to refuse signalling a recycled pid.

    A bare pid is not an identity: once the original process is reaped the
    number can be reused.  The recorded ``lstart`` plus the pgid is what lets a
    later check tell "still our process" from "somebody else's process".
    ``wait`` retries briefly, because ``ps`` can legitimately not list a
    process that was started microseconds ago -- and "not listed yet" must not
    be mistaken for "identity could never be confirmed".
    """
    deadline = time.monotonic() + max(0.0, wait)
    while True:
        identity = _pid_identity_once(pid)
        if identity is not None or time.monotonic() >= deadline:
            return identity
        time.sleep(0.02)


def _pid_identity_once(pid: int) -> dict[str, Any] | None:
    argv = ["ps", "-o", "ppid=,pgid=,lstart=", "-p", str(pid)]
    try:
        proc = subprocess.run(
            argv, capture_output=True, timeout=5, stdin=subprocess.DEVNULL, close_fds=True
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    text = proc.stdout.decode("utf-8", "replace").strip()
    parts = text.split(None, 4)
    if len(parts) < 4:
        return None
    return {"pid": pid, "ppid": parts[0], "pgid": parts[1], "lstart": " ".join(parts[2:])}


def _group_alive(pgid: int | None) -> bool | None:
    """``True``/``False`` if any member of the group is alive, ``None`` unknown.

    Signal 0 against a process group succeeds while *any* member exists, which
    is exactly the whole-tree question; a single surviving descendant is
    enough to keep this ``True``.
    """
    if not isinstance(pgid, int) or isinstance(pgid, bool) or pgid <= 1:
        return None
    import errno as errno_module

    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as exc:
        return True if exc.errno == errno_module.EPERM else None
    return True


def _signal_group(pgid: int, sig: int) -> tuple[bool, str | None]:
    """Signal a whole process group; failures are reported, never swallowed."""
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        return False, "group_absent"
    except OSError as exc:
        return False, exc.__class__.__name__
    return True, None


def _cancel_process_tree(
    proc: subprocess.Popen, identity: dict[str, Any] | None, grace: float
) -> dict[str, Any]:
    """Cancel the whole session and report exactly what was confirmed.

    The leader exiting never short-circuits group cleanup: after SIGTERM the
    group is polled until it is gone, escalated to SIGKILL if anything is still
    there, and polled again.  Signalling is refused outright when the recorded
    start identity no longer matches, because a recycled pid must never be
    signalled on the harness' behalf.
    """
    import signal

    outcome: dict[str, Any] = {
        "identity_confirmed": None,
        "term_sent": False,
        "kill_sent": False,
        "term_error": None,
        "kill_error": None,
        "group_gone": None,
        "leader_reaped": False,
    }
    pgid = proc.pid  # start_new_session=True makes the child its own group leader
    if identity is not None:
        current = _pid_identity(proc.pid)
        outcome["identity_confirmed"] = bool(
            current is not None
            and current.get("pgid") == identity.get("pgid")
            and current.get("lstart") == identity.get("lstart")
        )
        if not outcome["identity_confirmed"]:
            outcome["term_error"] = "identity_unconfirmed"
            return outcome
    outcome["term_sent"], outcome["term_error"] = _signal_group(pgid, signal.SIGTERM)

    def wait_gone(limit: float) -> bool | None:
        deadline = time.monotonic() + limit
        while True:
            state = _group_alive(pgid)
            if state is None or state is False:
                return state
            if time.monotonic() >= deadline:
                return state
            time.sleep(0.01)

    gone = wait_gone(grace)
    if gone is not True:
        # a prompt leader exit must not skip group cleanup: escalate anyway
        outcome["kill_sent"], outcome["kill_error"] = _signal_group(pgid, signal.SIGKILL)
        gone = wait_gone(grace)
    outcome["group_gone"] = gone
    if proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.wait(timeout=grace)
        outcome["leader_reaped"] = True
    except subprocess.TimeoutExpired:
        outcome["leader_reaped"] = False
    return outcome


def _run_bounded_command(
    argv: list[str],
    cwd: str,
    env: dict[str, str],
    timeout: float,
    max_output: int,
    grace: float,
) -> dict[str, Any]:
    """Run one argv command with independent watchdog and bounded capture.

    The process is started in its own session so the whole tree can be
    cancelled; reader threads never block the watchdog.  The capture budget is
    exact: producing exactly ``max_output`` bytes and then closing the pipe is
    *not* overflow, only a byte beyond the budget is.  stdout and stderr are
    returned as the raw bytes that were actually read, with decoded text kept
    alongside as a derived convenience rather than as the stored capture.
    """
    started_at = time.monotonic()
    started_utc = _utc_now()
    stdout: bytearray = bytearray()
    stderr: bytearray = bytearray()
    lock = threading.Lock()
    stop = threading.Event()
    done = {"stdout": False, "stderr": False}
    exceeded = threading.Event()
    errors = threading.Event()

    def reader(index: str, stream: Any) -> None:
        """Drain one pipe into a shared, exactly bounded budget.

        Each read asks for ``room + 1`` bytes.  A short result means the pipe
        still holds more than the budget, which is real overflow; a result of
        exactly ``room`` bytes leaves the next read to distinguish "exactly at
        budget then EOF" from "one more byte".
        """
        fileno = stream.fileno()
        os.set_blocking(fileno, False)
        try:
            while True:
                if stop.is_set():
                    break
                ready, _, _ = select.select([fileno], [], [], 0.005)
                if not ready:
                    continue
                with lock:
                    room = max_output - (len(stdout) + len(stderr))
                    want = min(4096, room + 1)
                chunk = os.read(fileno, max(1, want))
                if not chunk:
                    break  # true EOF: the pipe closed on a budget boundary
                overflow = False
                with lock:
                    target = stdout if index == "stdout" else stderr
                    if len(chunk) > room:
                        target.extend(chunk[:room])
                        overflow = True
                    else:
                        target.extend(chunk)
                if overflow:
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
            "pid": None,
            "completed": False,
            "exit_code": None,
            "errno": exc.errno,
            "output_limited": False,
            "timed_out": False,
            "cancellation_reason": None,
            "cancelled": False,
            "cleanup_confirmed": None,
            "cancel_state": None,
            "identity": None,
            "duration_seconds": 0.0,
            "capture_bytes": 0,
            "stdout_bytes": b"",
            "stderr_bytes": b"",
            "stdout_text": "",
            "stderr_text": "",
            "note": exc.__class__.__name__,
        }

    # Record the start identity before anything can be cancelled, so a later
    # check can tell our process from a recycled pid.
    identity = _pid_identity(proc.pid, wait=1.0)
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

    cancel_state: dict[str, Any] | None = None
    if status in ("output_limit", "timed_out", "environment_failure"):
        cancel_state = _cancel_process_tree(proc, identity, grace)

    stop.set()
    for thread in threads:
        thread.join(timeout=grace)
    # A reader that exits because of the stop flag (after cancellation) is not
    # a failure; only a reader still alive after the grace period is.
    if any(thread.is_alive() for thread in threads):
        status = "environment_failure"
    if cancel_state is None:
        # Always reap: a finished command must not leave a zombie behind.
        try:
            proc.wait(timeout=CANCELLATION_GRACE)
        except subprocess.TimeoutExpired:
            status = "environment_failure"
            cancel_state = {
                "identity_confirmed": None,
                "term_sent": False,
                "kill_sent": False,
                "term_error": None,
                "kill_error": None,
                "group_gone": None,
                "leader_reaped": False,
            }

    with lock:
        stdout_bytes = bytes(stdout)
        stderr_bytes = bytes(stderr)
    exit_code = proc.returncode
    completed = status in ("completed", "failed") and exit_code is not None and exit_code >= 0
    return {
        "started": True,
        "pid": proc.pid,
        "identity": identity,
        "completed": completed,
        "exit_code": exit_code,
        "errno": None,
        "output_limited": exceeded.is_set(),
        "timed_out": status == "timed_out",
        "cancellation_reason": cancellation_reason,
        "cancelled": cancel_state is not None,
        "cancel_state": cancel_state,
        "cleanup_confirmed": _cleanup_state_from_cancel(cancel_state),
        "duration_seconds": time.monotonic() - started_at,
        "capture_bytes": len(stdout_bytes) + len(stderr_bytes),
        "started_utc": started_utc,
        "ended_utc": _utc_now(),
        "stdout_bytes": stdout_bytes,
        "stderr_bytes": stderr_bytes,
        "stdout_text": stdout_bytes.decode("utf-8", "replace"),
        "stderr_text": stderr_bytes.decode("utf-8", "replace"),
    }


def _cleanup_state_from_cancel(cancel_state: dict[str, Any] | None) -> bool | None:
    """Three-state whole-tree cleanup verdict derived from a cancel outcome.

    ``True`` only when the entire group was confirmed gone under a confirmed
    identity; ``False`` when residue survived; ``None`` when the question could
    not be answered, which must never be read as "clean".
    """
    if not isinstance(cancel_state, dict):
        return None
    if cancel_state.get("identity_confirmed") is False:
        return None
    group_gone = cancel_state.get("group_gone")
    if group_gone is True:
        return True
    if group_gone is False:
        return False
    return None


def run_worker(
    profile_path: str,
    fixture: str,
    argv: list[str],
    cwd: str,
    env: dict[str, str],
    capture_path: Path,
    interpreter: str = "",
    timeout: float = COMMAND_TIMEOUT,
    grace: float = CANCELLATION_GRACE,
) -> dict[str, Any]:
    """Run one fixed-fixture action under sandbox-exec with raw-byte capture.

    ``capture_path`` is written by the harness only; the Worker never receives
    a handle to it.  The persisted capture is the *exact* stdout bytes that were
    read -- re-encoding a decoded string could change the bytes and break the
    "capture bytes are never altered" requirement -- and stderr is persisted
    next to it instead of dying in memory.  stdout+stderr share one
    ``MAX_OUTPUT`` budget; a single byte beyond it terminates the command and
    records ``output_limited``.  Timeout is enforced by an independent watchdog
    loop, never by a pipe read.
    """
    # The interpreter is named explicitly rather than relying on the fixture's
    # shebang: the argv array must state exactly which binary ran, and that
    # fact is what the evidence record carries.
    python = interpreter or sys.executable
    sandbox_argv = [SANDBOX_EXEC, "-f", profile_path, "--", python, fixture] + argv
    capture_path.parent.mkdir(parents=True, exist_ok=True)
    result = _run_bounded_command(
        sandbox_argv,
        cwd=cwd,
        env=env,
        timeout=timeout,
        max_output=MAX_OUTPUT,
        grace=grace,
    )
    stdout_bytes = result.get("stdout_bytes") or b""
    stderr_bytes = result.get("stderr_bytes") or b""
    # The harness writes the capture files; the Worker never receives a handle.
    capture_path.write_bytes(stdout_bytes)
    stderr_path = capture_path.with_suffix(".stderr.log")
    stderr_path.write_bytes(stderr_bytes)
    result["capture_file_sha256"] = _sha256_bytes(stdout_bytes)
    result["stderr_file"] = str(stderr_path)
    result["stderr_file_sha256"] = _sha256_bytes(stderr_bytes)
    return result


# ---------------------------------------------------------------------------
# Loopback control endpoint (harness-owned, single connection, bounded)
# ---------------------------------------------------------------------------


def run_loopback_control(
    port: int,
    connect_timeout: float,
    max_bytes: int,
    deadline: float,
    ready: threading.Event | None = None,
    cancel: threading.Event | None = None,
) -> dict[str, Any]:
    """Serve at most one loopback connection and report verifiable evidence.

    ``ready`` is set only once bind *and* listen have both succeeded, so a
    caller never starts a worker against a port that is not yet accepting.  The
    socket is closed on every path and the result states whether that close was
    confirmed.  A refused case is only meaningful when this endpoint really was
    listening: ``bound=False`` leaves the observation unknown, it never means
    "isolation confirmed", and ECONNREFUSED against a dead port is never read
    as a refusal.
    """
    result: dict[str, Any] = {
        "port": port,
        "bound": False,
        "served": False,
        "received_bytes": 0,
        "closed_confirmed": False,
        "reason": "not_started",
    }
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    conn = None
    try:
        try:
            sock.bind(("127.0.0.1", port))
            sock.listen(1)
            result["bound"] = True
        except OSError:
            result["reason"] = "bind_failed"
            return result
        if ready is not None:
            ready.set()
        sock.settimeout(0.05)
        end = time.monotonic() + max(0.05, deadline)
        while True:
            if cancel is not None and cancel.is_set():
                result["reason"] = "cancelled"
                return result
            if time.monotonic() >= end:
                result["reason"] = "no_connection"
                return result
            try:
                conn, _addr = sock.accept()
                break
            except TimeoutError:
                continue
            except OSError:
                result["reason"] = "accept_failed"
                return result
        result["served"] = True
        conn.settimeout(connect_timeout)
        while result["received_bytes"] < max_bytes:
            try:
                chunk = conn.recv(min(4096, max_bytes - result["received_bytes"]))
            except OSError:
                break
            if not chunk:
                break
            result["received_bytes"] += len(chunk)
        return result
    finally:
        if conn is not None:
            try:
                conn.close()
            except OSError:
                pass
        try:
            sock.close()
        except OSError:
            pass
        # fileno() becomes -1 exactly when this harness' own socket is closed;
        # this confirms our descriptor is gone and deliberately says nothing
        # about whether some other process owns the port now.
        result["closed_confirmed"] = sock.fileno() == -1
        if cancel is not None:
            cancel.set()


# ---------------------------------------------------------------------------
# Process tree snapshot (attempt-correlated)
# ---------------------------------------------------------------------------


def process_tree(root_pid: int, expected_identity: dict[str, Any] | None = None) -> dict[str, Any]:
    """Snapshot only the process tree that belongs to ``root_pid``.

    A pid is mandatory: without an attempt-correlated pid the function refuses
    instead of reading and persisting a machine-wide table.  Rows are kept only
    when they are the recorded pid itself or a descendant reached through
    ppid/pgid.  When ``expected_identity`` is supplied (the snapshot taken at
    process start) the result also states whether the pid still carries that
    same identity, because a recycled pid is not evidence about our process.
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
    identity = _pid_identity(root_pid)
    identity_match: bool | None = None
    if isinstance(expected_identity, dict):
        identity_match = bool(
            identity is not None
            and identity.get("lstart") == expected_identity.get("lstart")
            and identity.get("pgid") == expected_identity.get("pgid")
        )
    return {
        "status": "ok",
        "root_pid": root_pid,
        "alive": alive,
        "identity": identity,
        "identity_match": identity_match,
        "rows": filtered[:256],
        "observed_utc": _utc_now(),
    }


# ---------------------------------------------------------------------------
# Evidence package lifecycle
# ---------------------------------------------------------------------------


# Per-case artefacts persisted for every executed case.  stderr is captured
# alongside stdout instead of dying in memory, and the profile that was actually
# applied travels with the record so a reviewer can read it.
_PACKAGE_SUFFIXES = (
    ("evidence", ".json"),
    ("capture", ".log"),
    ("capture", ".stderr.log"),
)


def persist_package(
    source_attempt: Path,
    package_root: Path,
    test_ids: list[str],
) -> dict[str, Any]:
    """Copy produced capture/evidence into an exclusively created package root.

    The package root must not exist at all: any pre-existing directory (even
    one holding only dotfiles) is refused, so an attempt can never be reused or
    overwritten.  Sources follow the harness convention
    ``<test_id>.json`` / ``<test_id>.log`` / ``<test_id>.stderr.log``; an id
    with no record source is reported in ``missing`` instead of being silently
    skipped, and every copy is re-hashed after writing so a failed transfer
    keeps the package on disk rather than being reported as success.  Bytes are
    copied verbatim: a capture is never rewritten in transit.
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


def _target_unchanged(before: str | None, after: str | None, has_file_target: bool) -> bool | None:
    """Three-state target observation: network cases have no file to compare."""
    if not has_file_target:
        return None
    if before is None or after is None:
        return None
    return before == after


def _group_results(verdicts: dict[str, str]) -> dict[str, Any]:
    """Map per-case verdicts onto the T1..T7 summary schema.

    ``T4`` is the fixed out-of-scope MCP sub-item and ``T7`` is filled by an
    independent fresh reviewer, so it stays ``unknown`` here and keeps the
    overall result at ``partial`` no matter what the probe observed.
    """
    grouped: dict[str, Any] = {"T1": [], "T2": [], "T3": [], "T5": [], "T6": []}
    for case in _CASES:
        if case["test_id"] not in verdicts:
            continue
        grouped[case["group"]].append(verdicts[case["test_id"]])
    for key in ("T1", "T2", "T3", "T5", "T6"):
        if not grouped[key]:
            grouped[key] = ["unknown"]
    grouped["T4"] = "out_of_scope"
    grouped["T7"] = "unknown"
    return grouped


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
# immediately after its own positive control, with the *same* fixture, argv,
# cwd and target; the only difference between the two runs is the single
# isolation rule in the generated profile.  The harness restores the target to
# its pristine baseline and re-verifies the digest before the refusal runs, so
# the refusal is always judged against the recovered initial state.
#
# ``control: False`` marks a refusal whose same-target control cannot be
# expressed under the frozen profile rule (``allow_target`` may only name a
# single synthetic file under denied/secret).  Those cases still run and are
# still recorded, but they cannot reach ``pass`` because
# ``control_passed`` stays False -- that limitation is data, not a silent gap.
_PROBES: list[dict[str, Any]] = [
    # --- T1: writable workspace, denied sentinels, symlink escape ---------
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
        "id": "T1-sentinel-other",
        "group": "T1",
        "kind": "refuse",
        "action": "write",
        "area": "denied",
        "target": "sentinel/other.conf",
    },
    {
        "id": "T1-link-escape-read",
        "group": "T1",
        "kind": "refuse",
        "action": "read",
        "area": "work",
        "target": "escape-read",
        "control": False,
        "link": "secret/.env",
    },
    # --- T2: read-only control, secret reads, direct and linked writes ----
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
    {
        "id": "T2-write-direct",
        "group": "T2",
        "kind": "refuse",
        "action": "write",
        "area": "denied",
        "target": "direct-target.txt",
    },
    {
        "id": "T2-write-link",
        "group": "T2",
        "kind": "refuse",
        "action": "write",
        "area": "work",
        "target": "escape-write",
        "control": False,
        "link": "denied/direct-target.txt",
    },
    # --- T3: two harness-owned loopback endpoints -------------------------
    # Two distinct endpoints: the control endpoint is allowed by its profile,
    # the refused endpoint has a real listener but is not allowed by the
    # default-deny profile.  A dead port is never allowed to stand in for a
    # refusal, so the refused case is still paired with the control's verdict.
    {
        "id": "T3-connect-control",
        "group": "T3",
        "kind": "positive",
        "action": "connect",
        "area": "loopback",
        "endpoint": "control",
    },
    {
        "id": "T3-connect",
        "group": "T3",
        "kind": "refuse",
        "action": "connect",
        "area": "loopback",
        "endpoint": "refused",
        "control": False,
        "paired_control_id": "T3-connect-control",
    },
    # --- T5: credential-shaped sentinels and the minimal environment -------
    {"id": "T5-env-names", "group": "T5", "kind": "positive", "action": "env", "area": "none"},
    {
        "id": "T5-secret-credential",
        "group": "T5",
        "kind": "refuse",
        "action": "read",
        "area": "secret",
        "target": "credentials.json",
    },
    # --- T6: controlled descendants and expected timeout cancellation ------
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
    """Expand the probes into the executable order: control first, then refusal.

    The ordering is the contract's ordering.  A refusal is only meaningful
    after its control has demonstrated that the same argv/target works under
    the allow profile and that the harness restored the baseline in between.
    """
    cases: list[dict[str, Any]] = []
    for probe in _PROBES:
        base = {
            "group": probe["group"],
            "action": probe["action"],
            "area": probe["area"],
            "target": probe.get("target"),
            "depth": probe.get("depth"),
            "link": probe.get("link"),
            "endpoint": probe.get("endpoint"),
            "paired_control": None,
            "paired_refusal": None,
        }
        if probe["kind"] == "refuse":
            if probe.get("control", True):
                cases.append(
                    {
                        **base,
                        "test_id": f"{probe['id']}-control",
                        "test_kind": "positive",
                        "allow_target": probe["area"],
                        "allow_endpoint": (
                            "control" if probe.get("endpoint") == "control" else None
                        ),
                        "paired_refusal": probe["id"],
                    }
                )
            cases.append(
                {
                    **base,
                    "test_id": probe["id"],
                    "test_kind": "expected_refuse",
                    "allow_target": None,
                    "allow_endpoint": ("refused" if probe.get("endpoint") == "refused" else None),
                    "paired_control": (
                        probe.get("paired_control_id")
                        or (f"{probe['id']}-control" if probe.get("control", True) else None)
                    ),
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
                    "allow_endpoint": ("control" if probe.get("endpoint") == "control" else None),
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


# The synthetic Worker runs with a declared, minimal environment only.  The
# harness host's full environment (which may hold real credentials) is never
# inherited; the interpreter needs a small, fixed set of names to start, and
# the real Mac run must verify this list before any probe.  Values are never
# recorded, only names.
_MINIMAL_ENV_NAMES = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TERM")
# macOS injects this name into every spawned child regardless of the parent's
# environment.  It is declared rather than hidden so that the fixture's
# "undeclared names" check still means something: any *other* inherited name,
# credential-shaped or not, is still reported.
OS_INJECTED_ENV_NAMES = ("__CF_USER_TEXT_ENCODING",)
TOTAL_CAPTURE_BUDGET = 1 << 20
# Every synthetic file target starts from, and is restored to, these bytes.
PRISTINE_TARGET_BYTES = b"synthetic-sentinel\n"


def _minimal_env(extra: dict[str, str]) -> dict[str, str]:
    """Build the declared minimal environment plus the synthetic values."""
    env = {name: os.environ[name] for name in _MINIMAL_ENV_NAMES if name in os.environ}
    env.update(extra)
    return env


def _prepare_targets(attempt_root: Path, params: dict[str, str], fixture: Path) -> None:
    """Create the synthetic sentinels every probe acts on, and their baselines.

    All targets live inside the attempt tree.  Each file target gets a pristine
    byte pattern recorded under ``harness/state`` so the harness can restore it
    and re-verify the digest between a control and its refusal, and after any
    refused action, without ever relying on what the Worker reported.
    """
    layout = {
        "work": ["sentinel-work.txt"],
        "denied": [
            "AGENTS.md",
            ".git/config",
            "tests/protected/test_contract.py",
            "sentinel/other.conf",
            "direct-target.txt",
        ],
        "secret": [".env", "auth.json", "credentials.json"],
    }
    pristine = PRISTINE_TARGET_BYTES
    baselines: dict[str, str] = {}
    for area, names in layout.items():
        for name in names:
            path = Path(params[area]) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(pristine)
            baselines[f"{area}/{name}"] = _sha256_bytes(pristine)
    fixture_dest = Path(params["ro"]) / "fixtures" / fixture.name
    fixture_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(fixture, fixture_dest)
    baselines[f"ro/fixtures/{fixture.name}"] = _sha256_file(fixture_dest)
    # Escape links deliberately point out of the writable area.
    work = Path(params["work"])
    for link_name, target_rel in (
        ("escape-read", Path(params["secret"]) / ".env"),
        ("escape-write", Path(params["denied"]) / "direct-target.txt"),
    ):
        link = work / link_name
        if not link.is_symlink():
            link.symlink_to(target_rel)
    state = attempt_root / "harness" / "state" / "baselines.json"
    state.write_text(json.dumps(baselines, indent=2, sort_keys=True))


def _restore_target(path: Path | None, apply_restore: bool = True) -> str | None:
    """Restore a synthetic target to its pristine bytes and re-verify it.

    Returns the digest actually observed afterwards, or ``None`` when there is
    no file target.  A control that modified its target is therefore undone
    before the refusal is measured, so the refusal's baseline is the restored
    state rather than whatever the control left behind.

    ``apply_restore`` is false for the read-only area: that holds the frozen
    fixture copy, which the harness must never rewrite.  It is only digested,
    so a refused or successful read is still observable without the harness
    turning a read-only file into a synthetic sentinel.
    """
    if path is None:
        return None
    if apply_restore:
        try:
            path.write_bytes(PRISTINE_TARGET_BYTES)
        except OSError:
            pass
    return _digest_or_none(path)


def _target_path(case: dict[str, Any], params: dict[str, str]) -> Path | None:
    """The path a case passes on its argv (may be an escape symlink)."""
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


def _linked_real_path(case: dict[str, Any], params: dict[str, str]) -> Path | None:
    """The real file an escape symlink points at, for before/after digests."""
    link = case.get("link")
    if link is None:
        return None
    area, _, name = str(link).partition("/")
    if area not in params:
        return None
    return Path(params[area]) / name


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


def _write_summary(package_root: Path, records: list[dict[str, Any]]) -> None:
    """Write the package index; every reference is relative to the package root."""
    index = []
    for record in records:
        entry: dict[str, Any] = {"test_id": record["test_id"]}
        if record.get("capture_file"):
            entry["record_ref"] = f"evidence/{record['test_id']}.json"
            entry["capture_file"] = record["capture_file"]
            entry["capture_sha256"] = record["capture_sha256"]
            entry["stderr_file"] = record["stderr_file"]
            entry["profile_file"] = record["profile_file"]
        index.append(entry)
    (package_root / "summary.json").write_text(json.dumps(index, indent=2))


def _write_process_tree(package_root: Path, records: list[dict[str, Any]]) -> None:
    """Persist only the attempt-correlated trees the harness actually recorded."""
    trees = {
        record["test_id"]: record.get("process_tree")
        for record in records
        if record.get("process_tree")
    }
    (package_root / "process_tree.json").write_text(
        json.dumps({"recorded_utc": _utc_now(), "trees": trees}, indent=2)
    )


def _write_denied_manifest(package_root: Path, records: list[dict[str, Any]]) -> None:
    """Inventory the denied targets with the digests observed around each action."""
    entries = []
    for record in records:
        if record["area"] not in ("denied", "secret"):
            continue
        entries.append(
            {
                "test_id": record["test_id"],
                "area": record["area"],
                "argv_target": record.get("target"),
                "allow_target": record.get("allow_target"),
                "sha256_before": record.get("target_sha256_before"),
                "sha256_after": record.get("target_sha256_after"),
                "target_unchanged": record.get("target_unchanged"),
            }
        )
    (package_root / "denied_manifest.json").write_text(
        json.dumps({"schema_version": 1, "entries": entries}, indent=2)
    )


def _persist_profiles(package_root: Path, attempt_root: Path, test_ids: list[str]) -> None:
    """Copy the generated profiles into the package so a reviewer can read them."""
    destination = package_root / "profiles"
    destination.mkdir()
    for test_id in test_ids:
        source = attempt_root / "harness" / "profiles" / f"{test_id}.profile"
        shutil.copy2(source, destination / f"{test_id}.profile")


_CHECK_GROUP = {
    "T1": "filesystem",
    "T2": "control_readonly",
    "T3": "network",
    "T5": "credentials",
    "T6": "process_tree",
}
_CHECK_ORDER = (
    "filesystem",
    "control_readonly",
    "network",
    "mcp",
    "credentials",
    "process_tree",
    "fresh_review",
)


def _build_boundary_record(
    records: list[dict[str, Any]],
    attempt_id: str,
    verdict_by_id: dict[str, str],
    max_check_seconds: float,
) -> dict[str, Any]:
    """Assemble the C1 boundary-evidence record from what actually executed.

    Nothing is asserted here that the harness did not observe: ``enforced`` is
    only ever ``yes`` when a check really ran, really passed and really exited
    zero on the host that ran it.  MCP and the fresh-review flow are reported as
    not executed, which the C1 schema requires to be fully null.
    """
    by_check: dict[str, dict[str, Any]] = {}
    for record in records:
        group = record.get("group")
        check_id = _CHECK_GROUP.get(group or "")
        if check_id is None or check_id in by_check:
            continue
        worker = record.get("worker") or {}
        capture = record.get("capture_sha256")
        started = worker.get("started_utc")
        ended = worker.get("ended_utc")
        span_ok = (
            isinstance(started, str)
            and isinstance(ended, str)
            and _duration_seconds(started, ended) is not None
            and _duration_seconds(started, ended) <= max_check_seconds
        )
        executed = bool(worker.get("started")) and capture is not None and span_ok
        verdict = verdict_by_id.get(record["test_id"], "unknown")
        observed = "yes" if verdict == "pass" else ("no" if verdict == "fail" else "unknown")
        enforced = "unknown"
        if executed and observed == "yes" and worker.get("exit_code") == 0:
            enforced = "yes"
        check: dict[str, Any] = {
            "id": check_id,
            "declared": "yes",
            "observed": observed if executed else "unknown",
            "enforced": enforced if executed else "unknown",
            "executed": executed,
            "argv": None,
            "cwd": None,
            "started_utc": None,
            "ended_utc": None,
            "exit_code": None,
            "output_sha256": None,
            "source": "",
            "reason": "",
        }
        if executed:
            check.update(
                {
                    "argv": list(record.get("argv") or []),
                    "cwd": str(record.get("cwd") or ""),
                    "started_utc": started,
                    "ended_utc": ended,
                    "exit_code": worker.get("exit_code"),
                    "output_sha256": capture,
                    "source": f"capture/{record['test_id']}.log",
                    "reason": (
                        "observed on the host that executed it"
                        if not span_ok
                        else "harness observation for the representative case"
                    ),
                }
            )
            if not span_ok:
                check["reason"] = "duration outside the C1 per-check bound"
        else:
            check["source"] = "attempt/" + attempt_id
            check["reason"] = "no executed representative case for this sub-item"
        by_check[check_id] = check

    checks = []
    for check_id in _CHECK_ORDER:
        if check_id in by_check:
            checks.append(by_check[check_id])
            continue
        checks.append(
            {
                "id": check_id,
                "declared": "no" if check_id == "mcp" else "unknown",
                "observed": "unknown",
                "enforced": "unknown",
                "executed": False,
                "argv": None,
                "cwd": None,
                "started_utc": None,
                "ended_utc": None,
                "exit_code": None,
                "output_sha256": None,
                "source": "attempt/" + attempt_id,
                "reason": (
                    "MCP is out of scope for this contract"
                    if check_id == "mcp"
                    else "filled by an independent fresh reviewer, never self-signed"
                ),
            }
        )
    return {
        "schema_version": 1,
        "task_id": "M2C2A",
        "run_id": "run-" + attempt_id,
        "attempt_id": attempt_id,
        "worker_id": "harness-fixture",
        "platform": "darwin",
        "checks": checks,
    }


def _duration_seconds(started: str, ended: str) -> float | None:
    import datetime

    fmt = "%Y-%m-%dT%H:%M:%SZ"
    try:
        start = datetime.datetime.strptime(started, fmt)
        end = datetime.datetime.strptime(ended, fmt)
    except (TypeError, ValueError):
        return None
    return (end - start).total_seconds()


def _cleanup_blockers(records: list[dict[str, Any]]) -> list[str]:
    """Reasons the attempt tree must NOT be deleted.

    Cleanup is allowed only when nothing about the process state is unknown or
    known-bad.  Any residue, any unconfirmable identity, or any expected
    cancellation whose whole-tree state could not be established keeps the
    attempt on disk, because deleting it would destroy the only capture.
    """
    blockers: list[str] = []
    for record in records:
        worker = record.get("worker") or {}
        state = worker.get("cleanup_confirmed")
        if state is False:
            blockers.append(f"{record['test_id']}: confirmed process residue")
        cancel = worker.get("cancel_state")
        if isinstance(cancel, dict) and cancel.get("identity_confirmed") is False:
            blockers.append(f"{record['test_id']}: process identity unconfirmed")
        if record["test_kind"] == "timeout_cleanup" and state is None:
            blockers.append(f"{record['test_id']}: whole-tree cleanup not confirmable")
    return blockers


def run(
    authorization_file: Path,
    attempt_id: str,
    output_root: Path,
    fixture_path: Path | None = None,
    bundle_dir: Path | None = None,
    provider: str = "unrecorded",
) -> dict[str, Any]:
    """Gate, execute the full synthetic matrix, and seal the evidence package.

    Fail-closed order (each stage refuses before the next side effect):
      1. the host platform must really be darwin (there is no override hook);
      2. the frozen bundle sha must be resolvable from a real handoff file;
      3. the authorization must match that sha, the two approved roots and the
         two approved loopback endpoints;
      4. only then are paths created, and only then does anything execute.

    The attempt tree is deleted only when persistence was fully verified and no
    residue or unknown process state remains.  Every other outcome keeps the
    scene on disk and says so, rather than destroying the only capture.
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
    loopback = auth["loopback"]
    control_port = int(loopback["control_port"])
    refused_port = int(loopback["refused_port"])
    connect_timeout = float(loopback["connect_timeout_s"])
    max_bytes = int(loopback["max_bytes"])

    fixture = Path(fixture_path) if fixture_path else _default_fixture()
    if not fixture.is_file() or fixture.is_symlink():
        return _not_run_result(attempt_id, "fixture_unavailable", real_platform, provider)

    attempt_root = sandbox_root / attempt_id
    params = {
        "work": str(attempt_root / "work"),
        "ro": str(attempt_root / "ro"),
        "denied": str(attempt_root / "denied"),
        "secret": str(attempt_root / "secret"),
        "harness": str(attempt_root / "harness"),
    }
    try:
        ensure_attempt(attempt_root, params, authorized_root=sandbox_root)
    except ValueError:
        return _not_run_result(attempt_id, "attempt_creation_refused", real_platform, provider)
    paths_created = [str(attempt_root)]

    # Declared minimal environment: the host's own variables (and anything
    # credential-shaped in them) are never handed to the synthetic Worker.
    env = _minimal_env(
        {
            "M2C2A_ATTEMPT_ID": attempt_id,
            "M2C2A_SYNTHETIC": "1",
            "M2C2A_WORK": params["work"],
            "M2C2A_RO": params["ro"],
            "M2C2A_DENIED": params["denied"],
            "M2C2A_SECRET": params["secret"],
            "M2C2A_LOOPBACK_CONTROL_PORT": str(control_port),
            "M2C2A_LOOPBACK_REFUSED_PORT": str(refused_port),
        }
    )

    package_root = persistence_root / attempt_id
    records: list[dict[str, Any]] = []
    listeners: list[dict[str, Any]] = []
    invocations = 0
    capture_used = 0
    package_record: dict[str, Any] = {"copied": {}, "missing": []}
    c1: dict[str, Any] = {"status": "not_run"}
    summary_value = "partial"
    verdicts: dict[str, str] = {}
    failure: str | None = None
    persistence_verified = False
    boundary_validation: dict[str, Any] = {"validated": False, "reason": "not_attempted"}

    try:
        c1 = export_c1_dependency(
            Path(__file__).resolve().parents[3],
            C1_BOUNDARY_COMMIT,
            attempt_root / "harness" / "deps" / "boundary.py",
        )
        c1_module = None
        if c1.get("status") == "ok":
            c1["loaded"] = _load_c1_dependency(
                c1, attempt_root / "harness" / "deps" / "boundary.py"
            )
            c1_module = _load_c1_module(attempt_root / "harness" / "deps" / "boundary.py")
        _prepare_targets(attempt_root, params, fixture)
        # The Worker runs the read-only copy inside the attempt, which is the
        # only fixture path the generated profile makes readable.
        ro_fixture = Path(params["ro"]) / "fixtures" / fixture.name
        written = build_profiles(
            attempt_root,
            params,
            _CASES,
            loopback_port=control_port,
            refused_port=refused_port,
        )

        for case in _CASES:
            if capture_used + MAX_OUTPUT > TOTAL_CAPTURE_BUDGET:
                records.append(_budget_skipped_record(case, "capture_budget_exhausted"))
                continue
            record = _run_case(
                case=case,
                attempt_root=attempt_root,
                params=params,
                profile=written[case["test_id"]],
                fixture=str(ro_fixture),
                interpreter=sys.executable,
                env=env,
                control_port=control_port,
                refused_port=refused_port,
                connect_timeout=connect_timeout,
                max_bytes=max_bytes,
            )
            records.append(record)
            invocations += 1
            capture_used += int((record.get("worker") or {}).get("capture_bytes") or 0)
            if record.get("listener") is not None:
                listeners.append(record["listener"])

        verdicts = _classify_records(records)
        for record in records:
            record["verdict"] = verdicts[record["test_id"]]
        summary_value = backend.summarize_results(_group_results(verdicts))

        package_record = persist_package(attempt_root, package_root, [c["test_id"] for c in _CASES])
        paths_created.append(str(package_root))
        _persist_profiles(package_root, attempt_root, [c["test_id"] for c in _CASES])
        _write_summary(package_root, records)
        _write_process_tree(package_root, records)
        _write_denied_manifest(package_root, records)
        boundary_record = _build_boundary_record(
            records,
            attempt_id,
            verdicts,
            float(getattr(c1_module, "_MAX_CHECK_SECONDS", 120)),
        )
        (package_root / "boundary-record.json").write_text(json.dumps(boundary_record, indent=2))
        boundary_validation = _validate_boundary_record(c1_module, boundary_record)
        _write_manifest_files(package_root, include_cleanup=False)
        evidence.verify_pre_cleanup_package(package_root)
        persistence_verified = True
    except ValueError as exc:
        failure = f"execution_refused: {exc}"
    except OSError as exc:
        failure = f"environment_failure: {exc.__class__.__name__}"

    blockers = _cleanup_blockers(records)
    cleanup: dict[str, Any]
    finalized = False
    final_verification: dict[str, Any] = {"verified": False, "reason": "not_attempted"}
    if not persistence_verified:
        cleanup = {"skipped": "persistence was not verified; the scene is preserved"}
        failure = failure or "persistence_unverified"
    elif blockers:
        cleanup = {"skipped": "process state is not clean", "blockers": blockers}
        failure = failure or "cleanup_blocked"
    else:
        cleanup = _clean_attempt(attempt_root)
        try:
            finalize_package(package_root, cleanup)
            finalized = True
            final_verification = {
                "verified": True,
                "files": len(evidence.verify_package(package_root)["files"]),
            }
        except (ValueError, OSError) as exc:
            final_verification = {
                "verified": False,
                "reason": exc.__class__.__name__ if isinstance(exc, OSError) else "invalid_package",
            }
            failure = failure or "final_verification_failed"

    report = build_report(
        attempt_id=attempt_id,
        approved=True,
        platform=real_platform,
        provider=provider,
        cases=[{"test_id": r["test_id"], "status": r["verdict"]} for r in records],
        case_ids=["T1", "T2", "T3", "T5", "T6", "T4", "T7"],
    )
    report["platform_capability"] = "full" if summary_value == "full_pass" else "partial"
    report["summary"] = summary_value
    report["status"] = "completed" if failure is None else "partial"
    report["failure"] = failure
    report["c1_dependency"] = c1
    report["boundary_record"] = boundary_validation
    report["paths_created"] = paths_created
    report["listeners"] = listeners
    report["sandbox_exec_invocations"] = invocations
    report["capture_budget"] = {"used_bytes": capture_used, "limit_bytes": TOTAL_CAPTURE_BUDGET}
    report["process_tree"] = {
        "status": "recorded_per_case",
        "note": "each case carries only the tree of the pid this harness started",
        "cases_with_tree": [r["test_id"] for r in records if r.get("process_tree")],
    }
    report["records"] = records
    report["package"] = {**package_record, "finalized": finalized}
    report["final_verification"] = final_verification
    report["cleanup"] = cleanup
    report["cleanup_blockers"] = blockers
    return report


def _budget_skipped_record(case: dict[str, Any], reason: str) -> dict[str, Any]:
    """A case that was never run because the attempt capture budget was spent."""
    return {
        "test_id": case["test_id"],
        "group": case["group"],
        "test_kind": case["test_kind"],
        "action": case["action"],
        "area": case["area"],
        "target": None,
        "allow_target": case.get("allow_target"),
        "allow_endpoint": case.get("allow_endpoint"),
        "paired_control": case.get("paired_control"),
        "executed": False,
        "skipped_reason": reason,
        "verdict": "unknown",
        "worker": {},
        "fixture": {},
        "listener": None,
        "recorded_utc": _utc_now(),
    }


def _load_c1_module(dest: Path) -> Any:
    """Load the exported C1 boundary module again for its validator.

    ``importlib`` is used with an explicit file location; ``sys.path`` is never
    modified.
    """
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("m2c2a_c1_boundary_validate", dest)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except (OSError, ImportError, SyntaxError, ValueError, TypeError, AttributeError):
        return None
    return module


def _validate_boundary_record(module: Any, record: dict[str, Any]) -> dict[str, Any]:
    """Actually run the C1 seven-check validator over the record we produced."""
    if module is None or not callable(getattr(module, "validate_evidence", None)):
        return {"validated": False, "reason": "c1_validator_unavailable"}
    expected = {
        "task_id": record["task_id"],
        "run_id": record["run_id"],
        "attempt_id": record["attempt_id"],
        "worker_id": record["worker_id"],
    }
    try:
        module.validate_evidence(record, expected=expected)
    except (ValueError, TypeError, KeyError) as exc:
        return {"validated": False, "reason": exc.__class__.__name__}
    return {"validated": True, "checks": len(record["checks"])}


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
    """Check that the exported C1 module is intact and actually loadable.

    ``sys.path`` is never touched.  The digest recorded at export time is
    re-checked against the bytes on disk immediately before loading, and the
    module object itself is handed to ``_load_c1_module`` for the real
    seven-check validation rather than merely proving it imports.
    """
    if export.get("status") != "ok":
        return {"loaded": False, "reason": "dependency was not exported"}
    if _sha256_file(dest) != export.get("file_sha256"):
        return {"loaded": False, "reason": "dependency hash changed after export"}
    module = _load_c1_module(dest)
    if module is None:
        return {"loaded": False, "reason": "module could not be loaded"}
    return {
        "loaded": True,
        "has_validator": callable(getattr(module, "validate_evidence", None)),
    }


def _run_case(
    *,
    case: dict[str, Any],
    attempt_root: Path,
    params: dict[str, str],
    profile: str,
    fixture: str,
    interpreter: str,
    env: dict[str, str],
    control_port: int,
    refused_port: int,
    connect_timeout: float,
    max_bytes: int,
) -> dict[str, Any]:
    """Run one case and record everything the classifier needs.

    Every run starts from the restored baseline: the target is rewritten to its
    pristine bytes and the digest is re-verified, so a refusal is judged against
    the recovered initial state rather than against whatever the previous
    control left behind.  For loopback cases a harness-owned listener is bound,
    announced ready and only then does the worker start, so a refusal can never
    be explained by a port that was not listening.
    """
    test_id = case["test_id"]
    area = case["area"]
    target = _target_path(case, params)
    digest_target = _linked_real_path(case, params) or target
    restored = _restore_target(digest_target, apply_restore=area != "ro")

    argv = ["--action", case["action"]]
    if target is not None:
        argv += ["--target", str(target)]
    if area == "loopback":
        port = control_port if case.get("allow_endpoint") == "control" else refused_port
        argv += ["--host", "127.0.0.1", "--port", str(port)]
    if case.get("depth") is not None:
        argv += ["--depth", str(case["depth"])]

    listener: dict[str, Any] | None = None
    listener_thread: threading.Thread | None = None
    listener_ready = threading.Event()
    listener_cancel = threading.Event()
    if area == "loopback":
        port = control_port if case.get("allow_endpoint") == "control" else refused_port

        def _serve() -> None:
            listener_box["result"] = run_loopback_control(
                port=port,
                connect_timeout=connect_timeout,
                max_bytes=max_bytes,
                deadline=connect_timeout + COMMAND_TIMEOUT,
                ready=listener_ready,
                cancel=listener_cancel,
            )

        listener_box: dict[str, Any] = {}
        listener_thread = threading.Thread(target=_serve, daemon=True)
        listener_thread.start()
        if not listener_ready.wait(timeout=5.0):
            listener_cancel.set()

    capture_path = attempt_root / "harness" / "capture" / f"{test_id}.log"
    evidence_path = attempt_root / "harness" / "evidence" / f"{test_id}.json"

    result = run_worker(
        profile_path=profile,
        fixture=fixture,
        argv=argv,
        cwd=params["work"],
        env=env,
        capture_path=capture_path,
        interpreter=interpreter,
        # The fixture's timeout case sleeps 30s; the watchdog must terminate it
        # well inside that, because those sub-items expect cancellation.
        timeout=min(COMMAND_TIMEOUT, 5.0),
    )

    if listener_thread is not None:
        listener_cancel.set()
        listener_thread.join(timeout=CANCELLATION_GRACE)
        listener = listener_box.get("result")
        if not isinstance(listener, dict):
            listener = {"bound": False, "served": False, "reason": "listener_not_reported"}
        listener["joined"] = not listener_thread.is_alive()

    after = _digest_or_none(digest_target)
    tree = process_tree(result.get("pid"), result.get("identity")) if result.get("pid") else None
    if isinstance(tree, dict) and tree.get("status") == "unidentified":
        tree = None

    fixture_report: dict[str, Any] = {}
    capture_bytes = result.get("stdout_bytes") or b""
    capture_text = capture_bytes.decode("utf-8", "replace")
    for line in capture_text.splitlines():
        try:
            parsed = json.loads(line)
        except ValueError:
            continue
        if isinstance(parsed, dict) and "action" in parsed:
            fixture_report = parsed
            break

    unchanged = _target_unchanged(restored, after, digest_target is not None)
    record: dict[str, Any] = {
        "test_id": test_id,
        "group": case["group"],
        "test_kind": case["test_kind"],
        "action": case["action"],
        "area": area,
        "target": str(target) if target is not None else None,
        "linked_target": str(digest_target) if digest_target is not None else None,
        "allow_target": case.get("allow_target"),
        "allow_endpoint": case.get("allow_endpoint"),
        "paired_control": case.get("paired_control"),
        "executed": True,
        "argv": argv,
        "cwd": params["work"],
        "interpreter": interpreter,
        "worker": _jsonable_worker(result),
        "fixture": fixture_report,
        "listener": listener,
        "process_tree": tree,
        "restored_sha256": restored,
        "target_sha256_after": after,
        "target_unchanged": unchanged,
        "profile_sha256": _sha256_file(Path(profile)) if Path(profile).is_file() else None,
        "recorded_utc": _utc_now(),
    }
    if fixture_report:
        record["capture_file"] = f"capture/{test_id}.log"
        record["capture_sha256"] = _sha256_file(capture_path)
        record["stderr_file"] = f"capture/{test_id}.stderr.log"
        record["profile_file"] = f"profiles/{test_id}.profile"
    evidence_path.write_text(json.dumps(record, indent=2))
    return record


def _classify_records(records: list[dict[str, Any]]) -> dict[str, str]:
    """Classify every case through the frozen backend policy.

    Two passes, in the contract's order: every control and standalone positive
    is classified first, and only then the refusals, which consume their
    control's verdict.  A single pass would see the control as ``unknown`` and
    could never award a legitimate refusal.
    """
    verdicts = {record["test_id"]: "unknown" for record in records}
    for record in records:
        if not record.get("paired_control"):
            verdicts[record["test_id"]] = backend.classify_case(
                _case_for_classifier(record, "pass")
            )
    for record in records:
        control_id = record.get("paired_control")
        if control_id:
            verdicts[record["test_id"]] = backend.classify_case(
                _case_for_classifier(record, verdicts.get(control_id, "unknown"))
            )
    return verdicts


def _jsonable_worker(result: dict[str, Any]) -> dict[str, Any]:
    """The worker result with raw capture bytes replaced by their digests.

    The bytes themselves are persisted verbatim in the capture files; keeping
    them in the JSON record as well would duplicate megabytes of binary and
    make the record unserialisable for no gain.
    """
    record = {
        key: value for key, value in result.items() if key not in ("stdout_bytes", "stderr_bytes")
    }
    record["stdout_bytes_len"] = len(result.get("stdout_bytes") or b"")
    record["stderr_bytes_len"] = len(result.get("stderr_bytes") or b"")
    return record


def _listener_evidence_ok(record: dict[str, Any]) -> bool:
    """A loopback observation is only complete with real listener evidence.

    The endpoint must have been bound, and the harness' own socket must have
    been confirmed closed after the run.  Without this a failed connect proves
    nothing about isolation.
    """
    listener = record.get("listener")
    if not isinstance(listener, dict):
        return False
    return bool(listener.get("bound")) and bool(listener.get("closed_confirmed"))


def _case_for_classifier(record: dict[str, Any], control_verdict: str) -> dict[str, Any]:
    """Map a harness record onto the exact ``classify_case`` input schema."""
    worker = record.get("worker") or {}
    fixture_report = record.get("fixture") or {}
    unchanged = record.get("target_unchanged")
    output_limited = bool(worker.get("output_limited"))
    stderr_seen = bool(worker.get("stderr_bytes"))

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
            "output_limited": output_limited,
            "observation_complete": not output_limited,
        }

    if record["test_kind"] == "positive":
        observation_complete = not output_limited and not stderr_seen
        if record["area"] == "loopback":
            observation_complete = observation_complete and _listener_evidence_ok(record)
        return {
            "test_kind": "positive",
            "action_exit_code": worker.get("exit_code"),
            "action_errno": fixture_report.get("errno"),
            "action_started": bool(worker.get("started")),
            "action_completed": bool(worker.get("completed")),
            "effect_observed": bool(fixture_report.get("effect")),
            "control_passed": True,
            "target_unchanged": unchanged,
            "cleanup_confirmed": None,
            "output_limited": output_limited,
            "observation_complete": observation_complete,
        }

    # expected_refuse
    listener = record.get("listener") if record["area"] == "loopback" else None
    listener_effect = bool(isinstance(listener, dict) and listener.get("received_bytes"))
    observation_complete = not output_limited and not stderr_seen
    if record["area"] == "loopback":
        observation_complete = observation_complete and _listener_evidence_ok(record)
    return {
        "test_kind": "expected_refuse",
        "action_exit_code": worker.get("exit_code"),
        "action_errno": fixture_report.get("errno"),
        "action_started": bool(worker.get("started")),
        "action_completed": bool(worker.get("completed")),
        "effect_observed": bool(fixture_report.get("effect"))
        or listener_effect
        or unchanged is False,
        "control_passed": control_verdict == "pass",
        "target_unchanged": unchanged,
        "cleanup_confirmed": None,
        "output_limited": output_limited,
        "observation_complete": observation_complete,
    }


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
