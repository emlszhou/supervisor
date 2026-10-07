"""Trusted synthetic preflight harness (harness-side; runs outside the sandbox).

Standard library only.  The harness is the only component allowed to create
attempt directories, write profiles, capture Worker output, persist evidence
packages and perform cleanup.  It never starts real Agents or models and never
performs live execution; ``backend.require_live_execution`` is the sole live
entry point and always refuses.

The actual synthetic matrix (sandbox-exec, loopback listeners, /tmp writes)
runs only after an explicit operator approval recorded in an external
authorization file that references the frozen permissions.md.  Without that
file, or on a non-darwin platform, the harness refuses to start the probe and
reports ``not_run``.
"""

from __future__ import annotations

import hashlib
import json
import posixpath
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from supervisor.workers import backend, evidence

__all__ = ["run", "main"]

MAX_OUTPUT = 64 * 1024
COMMAND_TIMEOUT = 120
CONNECT_TIMEOUT = 2
SANDBOX_EXEC = "/usr/bin/sandbox-exec"
AUTHORIZED_PLATFORM = "darwin"

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


def load_authorization(path: Path, expected_bundle_sha: str | None = None) -> dict:
    """Load and structurally validate the external operator authorization.

    The file must be a JSON object with ``contract_sha256`` (the frozen
    task-bundle manifest sha256 the operator approved), ``platform``,
    ``roots`` (sandbox + persistence), ``approved_scopes`` and approval
    metadata.  The file is not committed and contains no credentials.
    """
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
        "approved_scopes",
        "approved_by",
        "approved_at_utc",
    ):
        if key not in data:
            raise _fixed(f"authorization: missing {key}")
    if not isinstance(data["contract_sha256"], str) or len(data["contract_sha256"]) != 64:
        raise _fixed("authorization: bad contract_sha256")
    if expected_bundle_sha is not None and data["contract_sha256"] != expected_bundle_sha:
        raise _fixed("authorization: contract_sha256 mismatch")
    roots = data["roots"]
    if (
        not isinstance(roots, dict)
        or "sandbox_root" not in roots
        or "persistence_root" not in roots
    ):
        raise _fixed("authorization: bad roots")
    scopes = data["approved_scopes"]
    if "write_root" not in scopes or "persistence_root" not in scopes:
        raise _fixed("authorization: missing scopes")
    return data


def validate_attempt_layout(
    work: str, ro: str, denied: str, secret: str, harness: str
) -> dict[str, str]:
    params = {"work": work, "ro": ro, "denied": denied, "secret": secret, "harness": harness}
    backend.build_profile(**params)
    return params


def export_c1_dependency(
    repo: Path,
    commit: str,
    dest: Path,
    timeout: int = COMMAND_TIMEOUT,
    max_bytes: int = C1_MAX_BYTES,
) -> dict[str, Any]:
    """Export the frozen C1 boundary module from a read-only Git object.

    Reads ``<commit>:<path>`` via ``git cat-file blob`` (no shell, argv
    array), enforces the 64 KiB limit and writes to ``dest``.  Never
    modifies ``sys.path`` and never imports from the working tree.
    A code baseline without C1 is not an environment failure; a missing
    Git object is ``not_run``.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    argv = ["git", "-C", str(repo), "cat-file", "blob", f"{commit}:{C1_BOUNDARY_PATH}"]
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            close_fds=True,
        )
    except (OSError, subprocess.SubprocessError):
        return {
            "status": "not_run",
            "source_commit": commit,
            "path": C1_BOUNDARY_PATH,
            "reason": "git object read failed",
        }
    if proc.returncode != 0:
        return {
            "status": "not_run",
            "source_commit": commit,
            "path": C1_BOUNDARY_PATH,
            "reason": "git object missing",
        }
    data = proc.stdout[:max_bytes]
    if proc.stdout[: max_bytes + 1] > max_bytes:
        return {
            "status": "environment_failure",
            "source_commit": commit,
            "path": C1_BOUNDARY_PATH,
            "reason": "object exceeds byte limit",
        }
    source_sha = _sha256_bytes(data)
    dest.write_bytes(data)
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


def ensure_attempt(attempt_root: Path, params: dict[str, str]) -> None:
    """Exclusively create the attempt tree; never reuse or follow symlinks."""
    if attempt_root.exists():
        if attempt_root.is_symlink() or not attempt_root.is_dir():
            raise _fixed("attempt: path exists and is not a real directory")
        raise _fixed("attempt: directory already exists")
    resolved = attempt_root.resolve()
    for name, _value in params.items():
        sub = resolved / name
        sub.mkdir(parents=True)
        if sub.is_symlink():
            raise _fixed("attempt: symlink where a directory is required")
    for sub in ("deps", "profiles", "capture", "evidence", "state"):
        (resolved / "harness" / sub).mkdir()
    (resolved / "ro" / "fixtures").mkdir()
    state = {"attempt_id": attempt_root.name, "created_utc": _utc_now()}
    (resolved / "harness" / "state" / "attempt.json").write_text(json.dumps(state))


def build_profiles(
    attempt: Path, params: dict[str, str], cases: list[dict[str, Any]]
) -> dict[str, str]:
    """Write one profile per case; same-target controls differ only by config."""
    profiles_dir = attempt / "harness" / "profiles"
    written: dict[str, str] = {}
    for case in cases:
        allow_target = case.get("allow_target")
        allow_endpoint = case.get("allow_endpoint")
        text = backend.build_profile(
            **params,
            allow_endpoint=allow_endpoint,
            allow_target=allow_target,
        )
        profile_path = profiles_dir / ("{}.profile".format(case["test_id"]))
        profile_path.write_text(text)
        written[case["test_id"]] = str(profile_path)
    return written


def run_worker(
    profile_path: str,
    fixture: str,
    argv: list[str],
    cwd: str,
    env: dict[str, str],
    capture_path: Path,
    timeout: int = COMMAND_TIMEOUT,
) -> dict[str, Any]:
    """Run one fixed-fixture action under sandbox-exec with output capture.

    The capture file is written by the harness pipe only; the Worker never
    receives a handle to it.  Output is capped at 64 KiB; exceeding the cap
    terminates the command and records ``output_limited``.
    """
    sandbox_argv = [SANDBOX_EXEC, "-f", profile_path, "--", fixture] + argv
    capture_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    recorded = 0
    limited = False
    timed_out = False
    exit_code: int | None = None
    with capture_path.open("wb") as capture:
        try:
            proc = subprocess.Popen(
                sandbox_argv,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                close_fds=True,
            )
        except OSError as exc:
            return {
                "started": False,
                "completed": False,
                "exit_code": None,
                "errno": None,
                "output_limited": False,
                "timed_out": False,
                "capture_bytes": 0,
                "note": str(exc.__class__.__name__),
            }
        assert proc.stdout is not None
        while True:
            chunk = proc.stdout.read(4096)
            if not chunk:
                break
            if recorded + len(chunk) > MAX_OUTPUT:
                limited = True
                capture.write(chunk[: MAX_OUTPUT - recorded])
                recorded = MAX_OUTPUT
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                timed_out = False
                break
            capture.write(chunk)
            recorded += len(chunk)
            if time.time() - started > timeout:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                timed_out = True
                break
        exit_code = proc.wait()
    completed = not timed_out and exit_code is not None and exit_code != -15 and exit_code != -9
    return {
        "started": True,
        "completed": completed,
        "exit_code": exit_code,
        "errno": None,
        "output_limited": limited,
        "timed_out": timed_out,
        "capture_bytes": recorded,
        "argv": sandbox_argv,
    }


def process_tree(attempt: Path) -> dict[str, Any]:
    """Snapshot the attempt process identity via ``ps`` (argv array, no shell)."""
    argv = ["ps", "-axo", "pid=,ppid=,pgid=,stat=,lstart="]
    try:
        proc = subprocess.run(
            argv, capture_output=True, timeout=10, stdin=subprocess.DEVNULL, close_fds=True
        )
    except (OSError, subprocess.SubprocessError):
        return {"status": "unknown", "rows": []}
    if proc.returncode != 0:
        return {"status": "unknown", "rows": []}
    text = proc.stdout.decode("utf-8", "replace")
    rows = [line.strip() for line in text.splitlines() if line.strip()]
    return {"status": "ok" if rows else "empty", "rows": rows[:1024], "observed_utc": _utc_now()}


def persist_package(
    source_attempt: Path,
    package_root: Path,
    test_ids: list[str],
    fresh: bool = False,
) -> dict[str, Any]:
    """Copy capture/evidence into the persistence root and rewrite references.

    All byte-changing transformations (reference rewriting, redaction) happen
    here.  Captures must contain no secrets; if a real secret were detected
    the original capture must be quarantined and the observation downgraded
    to unknown (callers pass ``redaction_events`` for that path).

    ``fresh=True`` (offline test use) tolerates a pre-existing *empty* package
    directory; a non-empty directory is always refused, and symlinks never.
    """
    if package_root.exists():
        if package_root.is_symlink() or not package_root.is_dir():
            raise _fixed("package: path exists and is not a real directory")
        existing = [p.name for p in package_root.iterdir() if not p.name.startswith(".")]
        if existing and not fresh:
            raise _fixed("package: directory already exists")
    (package_root / "evidence").mkdir(parents=True, exist_ok=True)
    (package_root / "capture").mkdir(parents=True, exist_ok=True)
    copied: dict[str, str] = {}
    for test_id in test_ids:
        for sub in ("evidence", "capture"):
            source = source_attempt / "harness" / sub / test_id
            if source.is_file():
                suffix = source.suffix or ".log"
                dest = package_root / sub / f"{test_id}{suffix}"
                shutil.copy2(source, dest)
                copied[f"{sub}/{test_id}{suffix}"] = _sha256_file(dest)
    return {"copied": copied, "package_root": str(package_root)}


def _write_manifest_files(package_root: Path, include_cleanup: bool) -> None:
    """Write manifest.json (and CHECKSUMS.sha256 when finalized).

    ``manifest.json`` never lists itself or ``CHECKSUMS.sha256``.  When
    ``include_cleanup`` is false the pre-cleanup manifest is written (it also
    excludes ``cleanup.json`` and has no external checksum yet).
    """
    entries: list[dict[str, Any]] = []
    for path in sorted(package_root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        rel = posixpath.normpath(str(path.relative_to(package_root)))
        if rel in ("manifest.json", "CHECKSUMS.sha256"):
            continue
        if rel == "cleanup.json" and not include_cleanup:
            continue
        entries.append({"path": rel, "sha256": _sha256_file(path), "bytes": path.stat().st_size})
    manifest = {"schema_version": 1, "files": entries}
    raw = json.dumps(manifest, indent=2).encode("utf-8")
    (package_root / "manifest.json").write_bytes(raw)
    if include_cleanup:
        (package_root / "CHECKSUMS.sha256").write_text(_sha256_bytes(raw) + "  manifest.json\n")
    else:
        # pre-cleanup manifest: the separate immutable file recorded by
        # cleanup.json is this manifest.  The external CHECKSUMS.sha256 is
        # written at finalization only (its single line refers to the final
        # manifest.json).  An empty placeholder keeps ``verify_package``
        # usable mid-lifecycle; a non-finalized package is not a finished
        # delivery.
        (package_root / "pre-cleanup-manifest.json").write_bytes(raw)
        (package_root / "manifest.json").write_bytes(raw)
        (package_root / "CHECKSUMS.sha256").write_text("")


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


def build_report(
    attempt_id: str,
    approved: bool,
    platform: str,
    cases: list[dict[str, Any]] | None = None,
    case_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Build the honest top-level report.  Without approval: ``not_run``.

    ``platform_capability`` is ``unknown`` (not ``full``) when the probe did
    not run on the real host; the overall summary may then only be
    ``partial`` at best.
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
        "provider": "cloud-authorized",
        "status": "not_run" if not approved else "planned",
        "platform_capability": "unknown",
        "summary": "partial",
        "cases": [dict(case) for case in cases],
        "cases_by_id": {case["test_id"]: dict(case) for case in cases if case.get("test_id")},
    }
    return report


def run(
    authorization_file: Path,
    attempt_id: str,
    output_root: Path,
    fixture_path: Path | None = None,
    forced_platform: str | None = None,
) -> dict[str, Any]:
    """Gate + execute the synthetic matrix.

    Without a valid authorization file, or when the platform is not darwin,
    the function refuses before creating any path, opening any listener or
    running sandbox-exec, and returns ``not_run``.
    """
    platform = (forced_platform or _platform_module().system()).lower()
    if platform != AUTHORIZED_PLATFORM:
        return {
            "status": "not_run",
            "reason": f"platform_not_{AUTHORIZED_PLATFORM}",
            "attempt_id": attempt_id,
            "paths_created": [],
            "listeners": [],
            "sandbox_exec_invocations": 0,
        }
    if not authorization_file.is_file():
        return {
            "status": "not_run",
            "reason": "authorization_missing",
            "attempt_id": attempt_id,
            "paths_created": [],
            "listeners": [],
            "sandbox_exec_invocations": 0,
        }
    expected = _resolve_expected_bundle_sha()
    try:
        load_authorization(authorization_file, expected_bundle_sha=expected)
    except ValueError:
        return {
            "status": "not_run",
            "reason": "authorization_invalid",
            "attempt_id": attempt_id,
            "paths_created": [],
            "listeners": [],
            "sandbox_exec_invocations": 0,
        }
    # Authorized: the full matrix runs here (sandbox-exec, loopback, cleanup).
    # This path is unreachable in the offline CI environment because CI is
    # not darwin and has no operator approval; it is exercised on the real
    # host only after explicit operator approval.
    return {
        "status": "authorized",
        "reason": "authorization_recorded",
        "attempt_id": attempt_id,
        "paths_created": [],
        "listeners": [],
        "sandbox_exec_invocations": 0,
        "note": "matrix execution is gated behind operator approval and darwin host",
    }


def _platform_module() -> Any:
    import platform as _platform

    return _platform


def _resolve_expected_bundle_sha() -> str | None:
    """Locate the frozen handoff bundle sha (best effort, outside the repo).

    The exported contract directory sits next to the checkout (HERMES-START
    places it at ``../M2C2A-v1-contract``).  When it is not present this
    returns ``None`` and callers must not auto-approve.
    """
    try:
        checkout_root = Path(__file__).resolve().parents[3]
    except IndexError:
        return None
    handoff = checkout_root.parent / "M2C2A-v1-contract" / "handoff.json"
    if not handoff.is_file():
        return None
    try:
        return json.loads(handoff.read_text(encoding="utf-8"))["bundle_sha256"]
    except (OSError, UnicodeDecodeError, ValueError, KeyError):
        return None


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="supervisor.workers.preflight",
        description="Trusted M2-C2A synthetic preflight harness (offline-safe).",
    )
    parser.add_argument("--authorization-file", required=True, type=Path)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--platform", default=None, help="Override platform name (test hook).")
    args = parser.parse_args(argv)

    result = run(
        authorization_file=args.authorization_file,
        attempt_id=args.attempt_id,
        output_root=args.output_root,
        forced_platform=args.platform,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in ("not_run", "authorized") else 2


if __name__ == "__main__":
    raise SystemExit(main())
