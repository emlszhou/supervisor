"""Integration tests for the trusted preflight harness (offline only).

Every host-touching path (sandbox-exec, /tmp, loopback listeners, git object
reads) is stubbed or pointed at tmp directories; no real probe is executed.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

import pytest

from supervisor.workers import backend, preflight


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_authorization(path: Path, contract_sha: str) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "contract_sha256": contract_sha,
                "platform": "darwin",
                "roots": {
                    "sandbox_root": "/tmp/m2c2-sandbox",
                    "persistence_root": str(path.parent / "persist"),
                },
                "loopback": {
                    "family": "tcp",
                    "host": "127.0.0.1",
                    "control_port": 18000,
                    "refused_port": 18001,
                    "connect_timeout_s": 2,
                    "max_bytes": 8192,
                },
                "approved_by": "operator",
                "approved_at_utc": "2026-01-01T00:00:00Z",
                "approved_scopes": ["write_root", "persistence_root", "loopback"],
            }
        )
    )


def contract_sha() -> str:
    """Synthetic frozen-bundle digest used by the offline tests only.

    Project tests must not read a developer machine's exported handoff
    directory: a clean checkout has no such sibling path and would fail with
    ``FileNotFoundError``.  The real bundle digest is supplied by the protected
    run, which executes outside the project suite.
    """
    return "f" * 64


def write_contract_bundle(root: Path, sha: str) -> Path:
    """Create a self-contained stand-in for the frozen handoff bundle."""
    bundle = root / "contract-bundle"
    bundle.mkdir(parents=True, exist_ok=True)
    (bundle / "handoff.json").write_text(json.dumps({"bundle_sha256": sha}))
    return bundle


def test_cli_help_runs_offline():
    result = subprocess.run(
        [sys.executable, "-m", "supervisor.workers.preflight", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "--authorization-file" in result.stdout


def test_refuses_without_authorization_file(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "supervisor.workers.preflight",
            "--authorization-file",
            str(tmp_path / "absent.json"),
            "--attempt-id",
            "a1",
            "--output-root",
            str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "not_run" in result.stdout
    assert not (tmp_path / "out").exists()
    # the sandbox root must never have been created by the probe
    assert not Path("/tmp/m2c2-sandbox/m2c2a-test").exists()


def test_refuses_mismatched_contract_sha(tmp_path):
    """A wrong contract digest must never authorize anything.

    The CLI always runs on the real host, so on a non-darwin reviewer the
    platform gate refuses even earlier than the digest check.  Both orderings
    are correct fail-closed outcomes; what must never happen is a run that
    executes anything, so the assertion is platform independent.
    """
    auth = tmp_path / "auth.json"
    write_authorization(auth, "f" * 64)
    bundle = write_contract_bundle(tmp_path, "a" * 64)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "supervisor.workers.preflight",
            "--authorization-file",
            str(auth),
            "--attempt-id",
            "a2",
            "--output-root",
            str(tmp_path / "out"),
            "--contract-bundle",
            str(bundle),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "not_run"
    assert payload["reason"] in ("authorization_invalid", "platform_not_darwin")
    assert payload["sandbox_exec_invocations"] == 0
    assert payload["paths_created"] == []
    assert not (tmp_path / "out").exists()


def test_non_darwin_platform_refuses(tmp_path, monkeypatch):
    import platform as platform_module

    auth = tmp_path / "auth.json"
    write_authorization(auth, contract_sha())
    monkeypatch.setattr(platform_module, "system", lambda: "Linux")
    result = preflight.run(
        authorization_file=auth,
        attempt_id="a3",
        output_root=tmp_path / "out",
        bundle_dir=write_contract_bundle(tmp_path, contract_sha()),
    )
    assert result["status"] == "not_run"
    assert result["reason"] == "platform_not_darwin"
    assert not (tmp_path / "out").exists()


def test_fixture_is_plain_python_and_never_shell(tmp_path):
    fixture = Path(__file__).resolve().parents[1] / "fixtures/seatbelt_probe.py"
    source = fixture.read_text()
    assert "shell=True" not in source
    assert "os.system" not in source
    assert "subprocess" in source
    # the fixture must be runnable standalone with an argv array
    result = subprocess.run(
        [sys.executable, str(fixture), "--action", "env"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["action"] == "env"
    assert payload["completed"] is True


def test_package_persistence_roundtrip(tmp_path):
    """Persist real harness output into an exclusive output root and verify."""
    source = tmp_path / "attempt"
    (source / "harness" / "capture").mkdir(parents=True)
    (source / "harness" / "evidence").mkdir(parents=True)
    capture_bytes = b"synthetic stderr\n"
    capture = source / "harness" / "capture/T1-w.log"
    capture.write_bytes(capture_bytes)
    record = {
        "test_id": "T1-w",
        "capture_file": "capture/T1-w.log",
        "capture_sha256": sha256_file(capture),
    }
    (source / "harness" / "evidence/T1-w.json").write_text(json.dumps(record))
    pkg_root = tmp_path / "persist/m2c2a-test"

    # the package root must not exist yet: persistence is exclusive
    result = preflight.persist_package(
        source_attempt=source,
        package_root=pkg_root,
        test_ids=["T1-w"],
    )
    assert result["missing"] == []
    assert (pkg_root / "capture/T1-w.log").read_bytes() == capture_bytes
    assert result["copied"]["capture/T1-w.log"] == sha256_file(pkg_root / "capture/T1-w.log")

    # an id with no produced source is reported, never silently dropped
    missing_result = preflight.persist_package(
        source_attempt=source, package_root=tmp_path / "persist/other", test_ids=["T1-nope"]
    )
    assert missing_result["missing"] == ["T1-nope"]

    # re-using an existing package root is refused even when it looks empty-ish
    with pytest.raises(ValueError):
        preflight.persist_package(source, pkg_root, ["T1-w"])

    (pkg_root / "summary.json").write_text(
        json.dumps([{"test_id": "T1-w", "record_ref": "evidence/T1-w.json"}])
    )
    preflight._write_manifest_files(pkg_root, include_cleanup=False)
    from supervisor.workers.evidence import verify_package

    # the pre-cleanup stage is not a finished delivery
    with pytest.raises(ValueError):
        verify_package(pkg_root)

    # Finalize: real cleanup results + pre-cleanup manifest sha -> final
    # manifest + external CHECKSUMS.  In this offline test the cleanup
    # "results" describe the tmp package directory itself; a real probe run
    # would record the actual rm -rf / lstat ENOENT of the attempt.
    preflight.finalize_package(
        package_root=pkg_root,
        cleanup_results={
            "cleanup_argv": ["rm", "-rf", str(pkg_root)],
            "cleanup_exit_code": 0,
            "post_cleanup_ls_output": "",
            "cleanup_enoent_confirmed": True,
            "cleanup_timestamp_utc": _utc_now(),
        },
    )
    manifest = verify_package(pkg_root)
    paths = {entry["path"] for entry in manifest["files"]}
    assert "pre-cleanup-manifest.json" in paths
    assert "cleanup.json" in paths
    assert "manifest.json" not in paths
    assert "CHECKSUMS.sha256" not in paths
    assert "summary.json" in paths
    assert "capture/T1-w.log" in paths

    cleanup = json.loads((pkg_root / "cleanup.json").read_text())
    assert cleanup["cleanup_enoent_confirmed"] is True
    assert cleanup["pre_cleanup_manifest_sha256"] == sha256_file(
        pkg_root / "pre-cleanup-manifest.json"
    )
    # the cleanup record must not reference the final manifest
    assert "manifest_sha256" not in cleanup


def test_preflight_report_not_run_on_unapproved_host():
    report = preflight.build_report(
        attempt_id="m2c2a-test", approved=False, platform=platform.system().lower()
    )
    assert report["status"] == "not_run"
    assert report["platform_capability"] == "unknown"
    assert report["summary"] == "partial"
    assert report["live_execution"] is False
    # provenance is recorded, never guessed
    assert report["provider"] == "unrecorded"


def test_full_report_shape_includes_seven_ids():
    report = preflight.build_report(
        attempt_id="m2c2a-test",
        approved=False,
        platform=platform.system().lower(),
        case_ids=["T1", "T2", "T3", "T5", "T6", "T4", "T7"],
    )
    assert set(report["cases_by_id"]) == {"T1", "T2", "T3", "T4", "T5", "T6", "T7"}
    assert report["cases_by_id"]["T4"]["status"] == "out_of_scope"
    subitems = {
        key: [report["cases_by_id"][key]["status"]] for key in ("T1", "T2", "T3", "T5", "T6")
    }
    subitems["T4"] = "out_of_scope"
    subitems["T7"] = report["cases_by_id"]["T7"]["status"]
    assert backend.summarize_results(subitems) == "partial"


def test_c1_dependency_export_refuses_without_git_object(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    fake_repo = tmp_path / "norepo"
    (fake_repo / "src/supervisor/workers").mkdir(parents=True)
    (fake_repo / "src/supervisor/workers/boundary.py").write_text("placeholder\n")
    (fake_repo / "CACHEDIR.TAG").write_text("Tag: bogus\n")
    (fake_repo / ".git").mkdir()
    (fake_repo / ".git/objects").mkdir(parents=True)
    (fake_repo / ".git/objects/pack").mkdir()

    result = preflight.export_c1_dependency(
        repo=fake_repo,
        commit="436e3b0e026580a6b39ece891e8ffe47ac1bb698",
        dest=tmp_path / "deps/boundary.py",
    )
    assert result["status"] in ("not_run", "environment_failure")
    assert not (tmp_path / "deps/boundary.py").exists()


# === C2A-R1 REGRESSION TESTS (appended) ===


def _make_fixture(path, script):
    path.write_text(script)
    path.chmod(0o755)


def test_watchdog_kills_silent_hang_without_output(tmp_path):
    import os
    import sys

    result = preflight._run_bounded_command(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=str(tmp_path),
        env=dict(os.environ),
        timeout=1.0,
        max_output=4096,
        grace=0.5,
    )
    assert result["started"] is True
    assert result["timed_out"] is True
    assert result["completed"] is False
    assert result["exit_code"] is not None
    assert result["duration_seconds"] < 5.0


def test_leader_exit_held_pipe_does_not_stall_watchdog(tmp_path):
    import os
    import sys

    # Honest-behavior check for the held-pipe scenario: a grandchild that
    # inherits the *real* (non-DEVNULL) write ends and keeps them open for
    # 30s while the leader exits.  Two honest outcomes are acceptable:
    #   1. readers reach EOF (fixture closed its inherited copies) ->
    #      completed, or
    #   2. readers are stalled on the held ends -> the watchdog fires on
    #      timeout and terminates the whole session.
    # What must NEVER happen: the harness blocks past timeout+grace waiting
    # for an EOF that the held pipe will never deliver.
    body = (
        "import subprocess, time, os\n"
        'p = subprocess.Popen(["sh", "-c", "sleep 30"], '
        "stdout=None, stderr=None)\n"  # inherits the real write ends
        "time.sleep(0.2)\n"
    )
    start = time.monotonic()
    result = preflight._run_bounded_command(
        [sys.executable, "-c", body],
        cwd=str(tmp_path),
        env=dict(os.environ),
        timeout=1.5,
        max_output=4096,
        grace=0.5,
    )
    elapsed = time.monotonic() - start
    assert result["started"] is True
    assert elapsed < 8.0, f"harness blocked {elapsed:.1f}s on a held pipe"
    if result["completed"]:
        # readers saw EOF: fine, but the whole tree must be gone.
        assert result["exit_code"] is not None
    else:
        # watchdog path: timed out and terminated the session.
        assert result["timed_out"] is True


def test_output_overflow_terminates_immediately(tmp_path):
    import os
    import sys
    import time

    # Write 64MiB; the 64KiB budget must terminate the run at the first
    # excess byte -- long before the 120s timeout.
    script = tmp_path / "flood.py"
    body = (
        "import os, sys\n"
        'chunk = ("x" * 65536).encode()\n'
        'fd = os.write if hasattr(os, "write") else None\n'
        "for _ in range(1024):\n"
        "    os.write(1, chunk)\n"
        "sys.stdout.flush()\n"
    )
    script.write_text(body)
    start = time.monotonic()
    result = preflight._run_bounded_command(
        [sys.executable, str(script)],
        cwd=str(tmp_path),
        env=dict(os.environ),
        timeout=120.0,
        max_output=65536,
        grace=0.5,
    )
    elapsed = time.monotonic() - start
    assert result["output_limited"] is True
    assert result["capture_bytes"] <= 65536
    assert result["completed"] is False
    assert elapsed < 10.0


def test_bounded_output_never_exceeds_budget(tmp_path):
    import os

    result = preflight._run_bounded_command(
        ["true"],
        cwd=str(tmp_path),
        env=dict(os.environ),
        timeout=5.0,
        max_output=10,
        grace=0.5,
    )
    assert result["completed"] is True
    assert result["exit_code"] == 0
    assert result["capture_bytes"] <= 10


def test_bounded_command_records_real_exit_code(tmp_path):
    import os

    result = preflight._run_bounded_command(
        ["sh", "-c", "exit 3"],
        cwd=str(tmp_path),
        env=dict(os.environ),
        timeout=5.0,
        max_output=4096,
        grace=0.5,
    )
    assert result["completed"] is True
    assert result["exit_code"] == 3
    assert result["timed_out"] is False
    assert result["output_limited"] is False


def test_c1_export_bounded_reader_uses_len_not_bytes_comparison():
    import inspect

    source = inspect.getsource(preflight.export_c1_dependency)
    assert "max_bytes + 1] > max_bytes" not in source
    assert "len(buffers" in source


def test_c1_export_real_git_object_roundtrip(tmp_path):
    import os
    import subprocess as sp

    repo = tmp_path / "repo"
    (repo / "src/supervisor/workers").mkdir(parents=True)
    (repo / "src/supervisor/workers/boundary.py").write_text("B = 1\n" * 100)
    env = dict(
        os.environ,
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@t",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@t",
    )

    def git(*args):
        sp.run(["git", "-C", str(repo)] + list(args), check=True, capture_output=True, env=env)

    git("init", "-q")
    git("add", "-A")
    git("commit", "-q", "-m", "c1")
    head = (
        sp.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, env=env
        )
        .stdout.decode()
        .strip()
    )

    result = preflight.export_c1_dependency(
        repo=repo,
        commit=head,
        dest=tmp_path / "deps/boundary.py",
        max_bytes=64 * 1024,
    )
    assert result["status"] == "ok"
    assert result["bytes"] == len("B = 1\n" * 100)
    assert result["blob_sha256"] == result["file_sha256"]


def test_c1_export_oversized_real_object_fails_without_partial_write(tmp_path):
    import os
    import subprocess as sp

    repo = tmp_path / "repo2"
    (repo / "src/supervisor/workers").mkdir(parents=True)
    (repo / "src/supervisor/workers/boundary.py").write_bytes(b"x" * (64 * 1024 + 8))
    env = dict(
        os.environ,
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@t",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@t",
    )
    sp.run(["git", "-C", str(repo), "init", "-q"], check=True, capture_output=True, env=env)
    sp.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True, env=env)
    sp.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "big"],
        check=True,
        capture_output=True,
        env=env,
    )
    head = (
        sp.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, env=env
        )
        .stdout.decode()
        .strip()
    )

    result = preflight.export_c1_dependency(
        repo=repo,
        commit=head,
        dest=tmp_path / "deps/boundary.py",
        max_bytes=64 * 1024,
    )
    assert result["status"] == "environment_failure"
    assert "byte limit" in result["reason"]
    assert not (tmp_path / "deps/boundary.py").exists()


def _write_auth(path, contract_sha, **overrides):
    data = {
        "schema_version": 1,
        "contract_sha256": contract_sha,
        "platform": "darwin",
        "roots": {
            "sandbox_root": "/tmp/m2c2-sandbox",
            "persistence_root": str(path.parent / "persist"),
        },
        "loopback": {
            "host": "127.0.0.1",
            "control_port": 18000,
            "refused_port": 18001,
            "connect_timeout_s": 2,
            "max_bytes": 8192,
        },
        "approved_by": "operator",
        "approved_at_utc": "2026-01-01T00:00:00Z",
        "approved_scopes": ["write_root", "persistence_root", "loopback"],
    }
    data.update(overrides)
    path.write_text(json.dumps(data))


def test_authorization_missing_expected_sha_fails_closed(tmp_path):
    auth = tmp_path / "auth.json"
    _write_auth(auth, "f" * 64)
    with pytest.raises(ValueError) as excinfo:
        preflight.load_authorization(auth, expected_bundle_sha=None)
    assert "fail closed" in str(excinfo.value)


def test_authorization_wrong_digest_rejected(tmp_path):
    auth = tmp_path / "auth.json"
    _write_auth(auth, "z" * 64)
    with pytest.raises(ValueError):
        preflight.load_authorization(auth, expected_bundle_sha="f" * 64)
    _write_auth(auth, "f" * 63 + "F")
    with pytest.raises(ValueError):
        preflight.load_authorization(auth, expected_bundle_sha="f" * 64)


def test_authorization_wrong_platform_rejected(tmp_path):
    auth = tmp_path / "auth.json"
    _write_auth(auth, "f" * 64, platform="linux")
    with pytest.raises(ValueError) as excinfo:
        preflight.load_authorization(auth, expected_bundle_sha="f" * 64)
    assert "platform" in str(excinfo.value)


def test_authorization_non_loopback_host_rejected(tmp_path):
    auth = tmp_path / "auth.json"
    for host in ("127.0.0.2", "10.0.0.1", "0.0.0.0"):
        _write_auth(
            auth,
            "f" * 64,
            loopback={
                "host": host,
                "control_port": 18000,
                "refused_port": 18001,
                "connect_timeout_s": 2,
                "max_bytes": 8192,
            },
        )
        with pytest.raises(ValueError):
            preflight.load_authorization(auth, expected_bundle_sha="f" * 64)


def test_authorization_scope_mismatch_rejected(tmp_path):
    auth = tmp_path / "auth.json"
    scopes_cases = (
        ["write_root"],
        ["write_root", "persistence_root"],
        ["write_root", "persistence_root", "loopback", "extra"],
    )
    for scopes in scopes_cases:
        _write_auth(auth, "f" * 64, approved_scopes=scopes)
        with pytest.raises(ValueError) as excinfo:
            preflight.load_authorization(auth, expected_bundle_sha="f" * 64)
        assert "scope" in str(excinfo.value)


def test_authorization_bad_timestamp_rejected(tmp_path):
    auth = tmp_path / "auth.json"
    _write_auth(auth, "f" * 64, approved_at_utc="yesterday")
    with pytest.raises(ValueError) as excinfo:
        preflight.load_authorization(auth, expected_bundle_sha="f" * 64)
    assert "timestamp" in str(excinfo.value)


def test_authorization_symlink_file_rejected(tmp_path):
    real = tmp_path / "real.json"
    _write_auth(real, "f" * 64)
    link = tmp_path / "auth.json"
    link.symlink_to(real)
    with pytest.raises(ValueError):
        preflight.load_authorization(link, expected_bundle_sha="f" * 64)


def test_run_refuses_when_recorded_persistence_root_mismatch(tmp_path, monkeypatch):
    import platform as platform_module

    auth = tmp_path / "auth.json"
    _write_auth(
        auth,
        contract_sha(),
        roots={"sandbox_root": "/tmp/m2c2-sandbox", "persistence_root": "/somewhere/else"},
    )
    monkeypatch.setattr(platform_module, "system", lambda: "Darwin")
    result = preflight.run(
        authorization_file=auth,
        attempt_id="a9",
        output_root=tmp_path / "out",
        bundle_dir=write_contract_bundle(tmp_path, contract_sha()),
    )
    assert result["status"] == "not_run"
    assert result["reason"] == "roots_not_bound"
    assert not (tmp_path / "out").exists()


def test_run_refuses_symlinked_sandbox_root(tmp_path, monkeypatch):
    import platform as platform_module

    fake_sandbox = tmp_path / "sandbox"
    fake_sandbox.mkdir()
    link = tmp_path / "sandbox-link"
    link.symlink_to(fake_sandbox, target_is_directory=True)
    auth = tmp_path / "auth.json"
    _write_auth(
        auth,
        contract_sha(),
        roots={"sandbox_root": str(link), "persistence_root": str(tmp_path / "out")},
    )
    monkeypatch.setattr(platform_module, "system", lambda: "Darwin")
    result = preflight.run(
        authorization_file=auth,
        attempt_id="a10",
        output_root=tmp_path / "out",
        bundle_dir=write_contract_bundle(tmp_path, contract_sha()),
    )
    assert result["status"] == "not_run"
    # the symlinked root is refused while the authorization is being loaded,
    # before any root binding or path creation happens
    assert result["reason"] == "authorization_invalid"
    assert result["paths_created"] == []


def test_run_refuses_bad_attempt_id(tmp_path, monkeypatch):
    import platform as platform_module

    auth = tmp_path / "auth.json"
    (tmp_path / "sandbox").mkdir()
    _write_auth(
        auth,
        contract_sha(),
        roots={
            "sandbox_root": str(tmp_path / "sandbox"),
            "persistence_root": str(tmp_path / "out"),
        },
    )
    monkeypatch.setattr(platform_module, "system", lambda: "Darwin")
    result = preflight.run(
        authorization_file=auth,
        attempt_id="../escape",
        output_root=tmp_path / "out",
        bundle_dir=write_contract_bundle(tmp_path, contract_sha()),
    )
    assert result["status"] == "not_run"
    assert result["reason"] == "roots_not_bound"
    # nothing was created, neither inside nor outside the sandbox root
    assert not (tmp_path / "out").exists()
    assert list((tmp_path / "sandbox").iterdir()) == []


def test_run_refuses_missing_fixture(tmp_path, monkeypatch):
    import platform as platform_module

    auth = tmp_path / "auth.json"
    (tmp_path / "sandbox").mkdir()
    _write_auth(
        auth,
        contract_sha(),
        roots={
            "sandbox_root": str(tmp_path / "sandbox"),
            "persistence_root": str(tmp_path / "out"),
        },
    )
    monkeypatch.setattr(platform_module, "system", lambda: "Darwin")
    result = preflight.run(
        authorization_file=auth,
        attempt_id="a11",
        output_root=tmp_path / "out",
        fixture_path=tmp_path / "no-fixture.py",
        bundle_dir=write_contract_bundle(tmp_path, contract_sha()),
    )
    assert result["status"] == "not_run"
    assert result["reason"] == "fixture_unavailable"


def _offline_worker(
    profile_path,
    fixture,
    argv,
    cwd,
    env,
    capture_path,
    interpreter="",
    timeout=120.0,
    grace=5.0,
):
    """Stand in for the sandboxed Worker without sandbox-exec.

    The same read-only fixture copy and the same minimal environment are used,
    so orchestration, classification and the evidence lifecycle are exercised --
    but nothing here tests macOS enforcement, and the substitution must never be
    reported as boundary evidence.
    """
    result = preflight._run_bounded_command(
        [interpreter or sys.executable, fixture] + list(argv),
        cwd=cwd,
        env=dict(env),
        timeout=timeout,
        max_output=preflight.MAX_OUTPUT,
        grace=grace,
    )
    capture_path.parent.mkdir(parents=True, exist_ok=True)
    capture_path.write_bytes(result.get("stdout_bytes") or b"")
    capture_path.with_suffix(".stderr.log").write_bytes(result.get("stderr_bytes") or b"")
    return result


def test_full_orchestration_offline(tmp_path, monkeypatch):
    """End-to-end offline lifecycle: attempt -> cases -> evidence -> cleanup.

    ``run_worker`` is replaced by a direct fixture run, so this exercises the
    orchestration, the classifier and the evidence lifecycle only.  It is NOT
    evidence of macOS Seatbelt enforcement: without ``sandbox-exec`` there is no
    boundary under test at all.
    """
    import platform as platform_module

    monkeypatch.setattr(platform_module, "system", lambda: "Darwin")
    monkeypatch.setattr(preflight, "run_worker", _offline_worker)

    sandbox_root = tmp_path / "sandbox"
    sandbox_root.mkdir()
    persistence_root = tmp_path / "out"
    persistence_root.mkdir(parents=True, exist_ok=True)
    auth = tmp_path / "auth.json"
    _write_auth(
        auth,
        contract_sha(),
        roots={"sandbox_root": str(sandbox_root), "persistence_root": str(persistence_root)},
        loopback={
            "host": "127.0.0.1",
            "control_port": 19000,
            "refused_port": 19001,
            "connect_timeout_s": 2,
            "max_bytes": 8192,
        },
    )
    fixture = Path(__file__).resolve().parents[1] / "fixtures/seatbelt_probe.py"

    result = preflight.run(
        authorization_file=auth,
        attempt_id="off1",
        output_root=persistence_root,
        fixture_path=fixture,
        bundle_dir=write_contract_bundle(tmp_path, contract_sha()),
    )
    assert result["status"] == "completed", result.get("failure")
    assert result["sandbox_exec_invocations"] == len(preflight._CASES)

    # every sub-item was really classified, none silently dropped
    verdicts = {r["test_id"]: r["verdict"] for r in result["records"]}
    assert set(verdicts) == {c["test_id"] for c in preflight._CASES}
    assert set(verdicts.values()) <= {"pass", "fail", "unknown"}

    # Without sandbox-exec the "refusals" really do write/read/connect, so the
    # classifier must report them as failures.  This is the offline proof that
    # the policy is actually evaluated per case instead of being a placeholder,
    # and it is also why this run can never be boundary evidence.
    refuse_ids = [c["test_id"] for c in preflight._CASES if c["test_kind"] == "expected_refuse"]
    assert refuse_ids
    assert all(verdicts[t] == "fail" for t in refuse_ids)
    assert all(
        r["fixture"].get("effect") is True for r in result["records"] if r["test_id"] in refuse_ids
    )

    # every refusal with a same-target control really got one, and the control
    # ran *before* the refusal it justifies
    order = [r["test_id"] for r in result["records"]]
    paired = 0
    for case in preflight._CASES:
        if case["test_kind"] != "expected_refuse" or not case.get("paired_control"):
            continue
        paired += 1
        assert order.index(case["paired_control"]) < order.index(case["test_id"])
        control = next(r for r in result["records"] if r["test_id"] == case["paired_control"])
        refusal = next(r for r in result["records"] if r["test_id"] == case["test_id"])
        if case["area"] == "loopback":
            # the two loopback halves intentionally differ by exactly the port:
            # same fixture, same cwd, two harness-owned endpoints
            assert control["argv"][:4] == refusal["argv"][:4]
            assert control["argv"][5] != refusal["argv"][5]
        else:
            assert control["argv"] == refusal["argv"]
            assert control["linked_target"] == refusal["linked_target"]
        assert control["worker"]["exit_code"] == 0, control["worker"]
        # both runs started from the same restored pristine baseline, so the
        # refusal was never measured against what the control left behind.
        # A loopback pair has no file target and therefore no baseline to keep.
        if case["area"] != "loopback":
            pristine = sha256_bytes(b"synthetic-sentinel\n")
            assert refusal["restored_sha256"] == pristine
            assert control["restored_sha256"] == pristine
        # offline there is no enforcement, so a refused *write* really did
        # change its target -- which is exactly why those sub-items must fail.
        # Read refusals legitimately leave the file untouched.
        if refusal["action"] == "write":
            assert refusal["target_unchanged"] is False
    assert paired >= 6, "the required refusal sub-items must keep their controls"

    # refusals that cannot have a same-target control under the frozen profile
    # stay unknown rather than quietly claiming a pass
    unpaired = [
        c["test_id"]
        for c in preflight._CASES
        if c["test_kind"] == "expected_refuse" and not c.get("paired_control")
    ]
    assert unpaired, "symlink-escape refusals have no expressible same-target control"

    # two harness-owned loopback endpoints, each really bound and closed
    loopback_cases = [r for r in result["records"] if r["area"] == "loopback"]
    assert len(loopback_cases) == 2
    assert {r["listener"]["port"] for r in loopback_cases} == {19000, 19001}
    for record in loopback_cases:
        assert record["listener"]["bound"] is True
        assert record["listener"]["closed_confirmed"] is True
        assert record["listener"]["joined"] is True

    # the synthetic Worker saw a declared, minimal environment only
    env_record = next(r for r in result["records"] if r["test_id"] == "T5-env-names")
    assert env_record["fixture"]["undeclared_names"] == []

    package_root = persistence_root / "off1"
    manifest = preflight.verify_package_offline(package_root)
    paths = {e["path"] for e in manifest["files"]}
    # the whole required delivery tree, not just a manifest and a checksum
    for required in (
        "summary.json",
        "process_tree.json",
        "denied_manifest.json",
        "boundary-record.json",
        "pre-cleanup-manifest.json",
        "cleanup.json",
    ):
        assert required in paths, required
    # every case produced persisted evidence, a capture and a readable profile
    assert result["package"]["missing"] == []
    for case in preflight._CASES:
        assert f"evidence/{case['test_id']}.json" in paths
        assert f"capture/{case['test_id']}.log" in paths
        assert f"capture/{case['test_id']}.stderr.log" in paths
        assert f"profiles/{case['test_id']}.profile" in paths

    # the C1 seven-check validator really ran over the record we produced
    assert result["boundary_record"]["validated"] is True
    assert result["boundary_record"]["checks"] == 7
    boundary = json.loads((package_root / "boundary-record.json").read_text())
    assert [c["id"] for c in boundary["checks"]] == [
        "filesystem",
        "control_readonly",
        "network",
        "mcp",
        "credentials",
        "process_tree",
        "fresh_review",
    ]
    # MCP and the fresh-review flow are never self-signed
    for check in boundary["checks"]:
        if check["id"] in ("mcp", "fresh_review"):
            assert check["executed"] is False
            assert check["observed"] == "unknown"
            assert check["argv"] is None

    # finalized and independently re-verified after finalization
    assert result["package"]["finalized"] is True
    assert result["final_verification"]["verified"] is True
    assert result["cleanup_blockers"] == []

    assert not (sandbox_root / "off1").exists()
    cleanup = json.loads((package_root / "cleanup.json").read_text())
    assert cleanup["cleanup_enoent_confirmed"] is True


def test_run_worker_write_fixture_smoke(tmp_path):
    import os

    work = tmp_path / "work"
    denied = tmp_path / "denied"
    work.mkdir()
    denied.mkdir()
    target = denied / "synthetic.txt"
    target.write_bytes(b"synthetic\n")
    fixture = Path(__file__).resolve().parents[1] / "fixtures/seatbelt_probe.py"
    result = preflight._run_bounded_command(
        [sys.executable, str(fixture), "--action", "write", "--target", str(target)],
        cwd=str(work),
        env=dict(os.environ),
        timeout=10.0,
        max_output=preflight.MAX_OUTPUT,
        grace=1.0,
    )
    assert result["started"] is True
    assert result["exit_code"] == 0
    assert target.read_bytes() == b"synthetic\nsynthetic-append-line\n"


def test_run_loopback_control_serves_one_connection(tmp_path):
    import socket
    import threading

    port = 19123
    box = {}

    def serve():
        box["result"] = preflight.run_loopback_control(
            port=port,
            connect_timeout=2.0,
            max_bytes=8192,
            deadline=3.0,
        )

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    deadline = time.monotonic() + 3.0
    connected = False
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0) as sock:
                sock.sendall(b"synthetic-probe\n")
            connected = True
            break
        except OSError:
            time.sleep(0.05)
    thread.join(timeout=5.0)
    assert connected
    assert box["result"]["served"] is True
    assert box["result"]["received_bytes"] == len(b"synthetic-probe\n")


def test_run_loopback_control_no_connection_recorded_honestly(tmp_path):
    result = preflight.run_loopback_control(
        port=19131,
        connect_timeout=0.2,
        max_bytes=8192,
        deadline=0.3,
    )
    assert result["served"] is False
    assert result["reason"] == "no_connection"


def test_ensure_attempt_terminates_and_refuses_symlinked_parent(tmp_path):
    """Regression: the parent-chain walk must terminate and refuse symlinks.

    An inverted walk (starting at ``/`` and walking down) never terminates,
    because ``Path('/').parent`` is ``Path('/')``; this case hangs forever
    rather than failing, so it is guarded directly.
    """
    real_root = tmp_path / "real"
    real_root.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real_root, target_is_directory=True)
    params = {
        name: str(link / "a1" / name) for name in ("work", "ro", "denied", "secret", "harness")
    }
    with pytest.raises(ValueError) as excinfo:
        preflight.ensure_attempt(link / "a1", params, authorized_root=real_root)
    assert "directly under" in str(excinfo.value)
    assert not (real_root / "a1").exists()

    # the component walk itself refuses a symlinked ancestor when the whole
    # chain below the filesystem root is inspected
    with pytest.raises(ValueError) as excinfo:
        preflight._require_real_chain(link / "a1", stop=None)
    assert "symlink" in str(excinfo.value)


def test_ensure_attempt_refuses_reuse_and_missing_parent(tmp_path):
    root = tmp_path / "sandbox"
    root.mkdir()
    existing = root / "a1"
    existing.mkdir()
    params = {name: str(existing / name) for name in ("work", "ro", "denied", "secret", "harness")}
    with pytest.raises(ValueError) as excinfo:
        preflight.ensure_attempt(existing, params, authorized_root=root)
    assert "already exists" in str(excinfo.value)
    # a rejected attempt must not have been populated
    assert list(existing.iterdir()) == []


def test_ensure_attempt_requires_direct_child_of_authorized_root(tmp_path):
    root = tmp_path / "sandbox"
    (root / "nested").mkdir(parents=True)
    params = {
        name: str(root / "nested" / "a1" / name)
        for name in ("work", "ro", "denied", "secret", "harness")
    }
    with pytest.raises(ValueError) as excinfo:
        preflight.ensure_attempt(root / "nested" / "a1", params, authorized_root=root)
    assert "directly under" in str(excinfo.value)


def test_process_tree_refuses_without_identified_pid():
    """Regression: a machine-wide ps table must never be read or persisted."""
    assert preflight.process_tree(0)["status"] == "unidentified"
    assert preflight.process_tree(None)["rows"] == []
    assert preflight.process_tree(-1)["alive"] is None


def test_attempt_id_is_a_single_canonical_component():
    for bad in ("", ".", "..", "../escape", "a/b", ".hidden", "a\x00b", "a\nb", "x" * 65):
        with pytest.raises(ValueError):
            preflight._validate_attempt_id(bad)
    assert preflight._validate_attempt_id("m2c2a-2026-10-11") == "m2c2a-2026-10-11"


# ---------------------------------------------------------------------------
# C2A-R2 regressions: each case pins the contract behaviour, not the
# implementation shape.
# ---------------------------------------------------------------------------


def test_capture_budget_is_exact_not_off_by_one(tmp_path):
    """Producing exactly the budget is not overflow; one byte more is."""
    script = tmp_path / "exact.py"
    script.write_text("import sys; sys.stdout.buffer.write(b'x' * 16)\n")
    at_budget = preflight._run_bounded_command(
        [sys.executable, str(script)],
        cwd=str(tmp_path),
        env=preflight._minimal_env({}),
        timeout=20.0,
        max_output=16,
        grace=1.0,
    )
    assert at_budget["output_limited"] is False
    assert at_budget["exit_code"] == 0
    assert at_budget["capture_bytes"] == 16

    script.write_text("import sys; sys.stdout.buffer.write(b'x' * 17)\n")
    over_budget = preflight._run_bounded_command(
        [sys.executable, str(script)],
        cwd=str(tmp_path),
        env=preflight._minimal_env({}),
        timeout=20.0,
        max_output=16,
        grace=1.0,
    )
    assert over_budget["output_limited"] is True
    # never stored more than the budget, even when more was produced
    assert over_budget["capture_bytes"] == 16


def test_capture_bytes_are_persisted_verbatim(tmp_path, monkeypatch):
    """A capture is stored as the exact bytes read, not re-encoded text."""
    payload = bytes(range(256)) * 4  # invalid utf-8 on purpose
    script = tmp_path / "binary.py"
    script.write_bytes(b"import sys; sys.stdout.buffer.write(" + repr(payload).encode() + b")\n")
    # A stand-in for sandbox-exec that drops straight through to the command.
    # This exercises the real argv assembly and the byte-for-byte persistence;
    # it claims nothing about macOS enforcement.
    shim = tmp_path / "sandbox-exec-shim"
    shim.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "args = sys.argv[1:]\n"
        "assert args[0] == '-f' and args[2] == '--', args\n"
        "os.execv(args[3], args[3:])\n"
    )
    shim.chmod(0o755)
    monkeypatch.setattr(preflight, "SANDBOX_EXEC", str(shim))

    capture = tmp_path / "cap.log"
    result = preflight.run_worker(
        profile_path=str(tmp_path / "unused.profile"),
        fixture=str(script),
        argv=[],
        cwd=str(tmp_path),
        env=preflight._minimal_env({}),
        capture_path=capture,
        interpreter=sys.executable,
        timeout=20.0,
        grace=1.0,
    )
    assert result["exit_code"] == 0, result
    assert capture.read_bytes() == payload
    assert result["capture_file_sha256"] == sha256_bytes(payload)
    # stderr is persisted next to stdout instead of dying in memory
    assert (tmp_path / "cap.stderr.log").read_bytes() == b""


def test_whole_tree_cleanup_is_false_when_a_descendant_survives(tmp_path):
    """The leader exiting promptly must not be mistaken for a clean tree.

    The child spawns a grandchild that ignores SIGTERM; only the whole-group
    check can tell that something survived.
    """
    script = tmp_path / "stubborn.py"
    script.write_text(
        "import os, signal, subprocess, sys, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "kid = subprocess.Popen([sys.executable, '-c',\n"
        "    'import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);"
        "time.sleep(30)'])\n"
        "time.sleep(30)\n"
    )
    result = preflight._run_bounded_command(
        [sys.executable, str(script)],
        cwd=str(tmp_path),
        env=preflight._minimal_env({}),
        timeout=1.0,
        max_output=preflight.MAX_OUTPUT,
        grace=1.0,
    )
    assert result["timed_out"] is True
    assert isinstance(result["cancel_state"], dict)
    # either the group was escalated and confirmed gone, or residue was
    # observed and reported as not-clean; it is never silently "clean"
    assert result["cleanup_confirmed"] is not True or (
        result["cancel_state"]["group_gone"] is True
        and result["cancel_state"]["identity_confirmed"] is not False
    )
    # the outcome is recorded either way
    assert "group_gone" in result["cancel_state"]


def test_cleanup_state_is_unknown_when_identity_is_unconfirmed():
    """An unconfirmable identity can never be reported as clean."""
    assert preflight._cleanup_state_from_cancel(None) is None
    assert preflight._cleanup_state_from_cancel({"identity_confirmed": False}) is None
    assert (
        preflight._cleanup_state_from_cancel({"identity_confirmed": True, "group_gone": None})
        is None
    )
    assert (
        preflight._cleanup_state_from_cancel({"identity_confirmed": True, "group_gone": False})
        is False
    )
    assert (
        preflight._cleanup_state_from_cancel({"identity_confirmed": True, "group_gone": True})
        is True
    )


def test_minimal_environment_drops_host_secrets(monkeypatch):
    """The synthetic Worker must not inherit the host's credential-shaped vars."""
    monkeypatch.setenv("M2C2A_TEST_CREDENTIAL_SENTINEL", "do-not-leak")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "do-not-leak")
    monkeypatch.setenv("TOTALLY_UNRELATED_HOST_VAR", "do-not-leak")
    env = preflight._minimal_env({"M2C2A_ATTEMPT_ID": "a1"})
    assert env["M2C2A_ATTEMPT_ID"] == "a1"
    for name in (
        "M2C2A_TEST_CREDENTIAL_SENTINEL",
        "AWS_SECRET_ACCESS_KEY",
        "TOTALLY_UNRELATED_HOST_VAR",
    ):
        assert name not in env
    # every forwarded name is declared, nothing else sneaks through
    declared = set(preflight._MINIMAL_ENV_NAMES) | set(preflight.OS_INJECTED_ENV_NAMES)
    assert set(env) - declared <= {
        "M2C2A_ATTEMPT_ID",
        "M2C2A_SYNTHETIC",
        "M2C2A_WORK",
        "M2C2A_RO",
        "M2C2A_DENIED",
        "M2C2A_SECRET",
        "M2C2A_LOOPBACK_CONTROL_PORT",
        "M2C2A_LOOPBACK_REFUSED_PORT",
    }


def test_credential_sentinel_never_reaches_the_worker(tmp_path, monkeypatch):
    """End-to-end: a sentinel in the host environment stays in the host."""
    monkeypatch.setenv("M2C2A_TEST_CREDENTIAL_SENTINEL", "super-secret-value")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    seen = tmp_path / "seen.json"
    script = tmp_path / "spy.py"
    script.write_text(
        f"import json, os, sys\njson.dump(sorted(os.environ), open({str(seen)!r}, 'w'))\n"
    )
    result = preflight._run_bounded_command(
        [sys.executable, str(script)],
        cwd=str(tmp_path),
        env=preflight._minimal_env({}),
        timeout=20.0,
        max_output=preflight.MAX_OUTPUT,
        grace=1.0,
    )
    assert result["exit_code"] == 0
    names = json.loads(seen.read_text())
    assert "M2C2A_TEST_CREDENTIAL_SENTINEL" not in names
    assert "super-secret-value" not in result["stdout_bytes"].decode("utf-8", "replace")


def test_a_legitimate_refusal_is_classified_pass():
    """A real refusal (EPERM, untouched target, working control) must pass.

    This is the case the previous single-pass ordering could never award: the
    control was still ``unknown`` when the refusal was classified.
    """
    refusal = {
        "test_id": "T2-secret-env",
        "group": "T2",
        "test_kind": "expected_refuse",
        "action": "read",
        "area": "secret",
        "linked_target": "/tmp/secret/.env",
        "executed": True,
        "argv": ["--action", "read", "--target", "/tmp/secret/.env"],
        "cwd": "/tmp/work",
        "worker": {
            "started": True,
            "completed": True,
            "exit_code": 1,
            "output_limited": False,
            "stderr_bytes": b"",
        },
        "fixture": {"errno": "EPERM", "effect": False},
        "listener": None,
        "target_unchanged": True,
        "paired_control": "T2-secret-env-control",
    }
    control = {
        "test_id": "T2-secret-env-control",
        "group": "T2",
        "test_kind": "positive",
        "action": "read",
        "area": "secret",
        "linked_target": "/tmp/secret/.env",
        "executed": True,
        "argv": ["--action", "read", "--target", "/tmp/secret/.env"],
        "cwd": "/tmp/work",
        "worker": {
            "started": True,
            "completed": True,
            "exit_code": 0,
            "output_limited": False,
            "stderr_bytes": b"",
        },
        "fixture": {"errno": None, "effect": True},
        "listener": None,
        "target_unchanged": True,
        "paired_control": None,
    }
    verdicts = preflight._classify_records([refusal, control])
    assert verdicts["T2-secret-env-control"] == "pass"
    assert verdicts["T2-secret-env"] == "pass"

    # ...but an observed effect still fails immediately, control or not
    breached = dict(refusal, fixture={"errno": "EPERM", "effect": True})
    assert preflight._classify_records([breached, control])["T2-secret-env"] == "fail"

    # ...and with the control failing, the refusal cannot claim a pass
    broken_control = dict(
        control,
        worker=dict(control["worker"], exit_code=1),
        fixture={"errno": None, "effect": False},
    )
    assert preflight._classify_records([refusal, broken_control])["T2-secret-env"] == "unknown"


def test_loopback_refusal_without_a_real_listener_is_unknown():
    """ECONNREFUSED against a port nobody bound proves nothing."""
    record = {
        "test_id": "T3-connect",
        "group": "T3",
        "test_kind": "expected_refuse",
        "action": "connect",
        "area": "loopback",
        "linked_target": None,
        "executed": True,
        "argv": ["--action", "connect", "--host", "127.0.0.1", "--port", "19001"],
        "cwd": "/tmp/work",
        "worker": {
            "started": True,
            "completed": True,
            "exit_code": 1,
            "output_limited": False,
            "stderr_bytes": b"",
        },
        "fixture": {"errno": "ECONNREFUSED", "effect": False},
        "listener": {"port": 19001, "bound": False, "served": False, "received_bytes": 0},
        "target_unchanged": None,
        "paired_control": "T3-connect-control",
    }
    case = preflight._case_for_classifier(record, "pass")
    assert case["observation_complete"] is False
    assert backend.classify_case(case) == "unknown"

    # a real listener that received the connection is a boundary breach
    breached = dict(
        record,
        listener=dict(record["listener"], bound=True, closed_confirmed=True, received_bytes=16),
    )
    case = preflight._case_for_classifier(breached, "pass")
    assert case["effect_observed"] is True
    assert backend.classify_case(case) == "fail"


def test_loopback_listener_signals_ready_before_the_worker_starts():
    """The worker must never race a port that is not accepting yet."""
    import threading as _threading

    ready = _threading.Event()
    box = {}

    def serve():
        box["result"] = preflight.run_loopback_control(
            port=19222,
            connect_timeout=2.0,
            max_bytes=8192,
            deadline=3.0,
            ready=ready,
            cancel=_threading.Event(),
        )

    thread = _threading.Thread(target=serve, daemon=True)
    thread.start()
    assert ready.wait(timeout=5.0) is True, "listener never announced readiness"
    # readiness implies the endpoint is genuinely connectable right now
    import socket as _socket

    with _socket.create_connection(("127.0.0.1", 19222), timeout=2.0) as sock:
        sock.sendall(b"probe\n")
    thread.join(timeout=5.0)
    assert box["result"]["served"] is True
    assert box["result"]["closed_confirmed"] is True


def test_authorization_requires_two_distinct_loopback_endpoints(tmp_path):
    auth = tmp_path / "auth.json"
    _write_auth(
        auth,
        "f" * 64,
        loopback={
            "host": "127.0.0.1",
            "control_port": 18000,
            "refused_port": 70000,
            "connect_timeout_s": 2,
            "max_bytes": 8192,
        },
    )
    with pytest.raises(ValueError) as excinfo:
        preflight.load_authorization(auth, expected_bundle_sha="f" * 64)
    assert "range" in str(excinfo.value)
    _write_auth(
        auth,
        "f" * 64,
        loopback={
            "host": "127.0.0.1",
            "control_port": 18000,
            "refused_port": 18000,
            "connect_timeout_s": 2,
            "max_bytes": 8192,
        },
    )
    with pytest.raises(ValueError) as excinfo:
        preflight.load_authorization(auth, expected_bundle_sha="f" * 64)
    assert "distinct" in str(excinfo.value)


def test_persistence_failure_preserves_the_attempt_tree(tmp_path, monkeypatch):
    """Regression: cleanup used to run unconditionally and destroy the capture.

    When persistence or its verification fails, the only remaining copy of the
    evidence is the attempt tree itself, so it must survive and the failure must
    be reported rather than silently sealed into a delivery.
    """
    import platform as platform_module

    monkeypatch.setattr(platform_module, "system", lambda: "Darwin")
    monkeypatch.setattr(preflight, "run_worker", _offline_worker)

    sandbox_root = tmp_path / "sandbox"
    sandbox_root.mkdir()
    persistence_root = tmp_path / "out"
    persistence_root.mkdir()
    auth = tmp_path / "auth.json"
    _write_auth(
        auth,
        contract_sha(),
        roots={
            "sandbox_root": str(sandbox_root),
            "persistence_root": str(persistence_root),
        },
        loopback={
            "host": "127.0.0.1",
            "control_port": 19300,
            "refused_port": 19301,
            "connect_timeout_s": 2,
            "max_bytes": 8192,
        },
    )
    fixture = Path(__file__).resolve().parents[1] / "fixtures/seatbelt_probe.py"

    def refuse(*_args, **_kwargs):
        raise ValueError("package: simulated persistence failure")

    monkeypatch.setattr(preflight, "persist_package", refuse)

    result = preflight.run(
        authorization_file=auth,
        attempt_id="keep1",
        output_root=persistence_root,
        fixture_path=fixture,
        bundle_dir=write_contract_bundle(tmp_path, contract_sha()),
    )
    assert result["status"] == "partial"
    assert "persistence" in (result["failure"] or "")
    assert "skipped" in result["cleanup"]
    # the scene is still there, with its captures, for inspection
    attempt = sandbox_root / "keep1"
    assert attempt.is_dir()
    assert list((attempt / "harness" / "capture").glob("*.log"))
    assert result["package"]["finalized"] is False
    assert result["final_verification"]["verified"] is False


def test_unconfirmed_process_state_blocks_cleanup(tmp_path, monkeypatch):
    """A cleanup question that could not be answered keeps the attempt."""
    import platform as platform_module

    monkeypatch.setattr(platform_module, "system", lambda: "Darwin")
    monkeypatch.setattr(preflight, "run_worker", _offline_worker)
    # the whole-tree state of the expected-cancellation case stays unknown
    monkeypatch.setattr(preflight, "_cleanup_state_from_cancel", lambda _state: None)

    sandbox_root = tmp_path / "sandbox"
    sandbox_root.mkdir()
    persistence_root = tmp_path / "out"
    persistence_root.mkdir()
    auth = tmp_path / "auth.json"
    _write_auth(
        auth,
        contract_sha(),
        roots={
            "sandbox_root": str(sandbox_root),
            "persistence_root": str(persistence_root),
        },
        loopback={
            "host": "127.0.0.1",
            "control_port": 19310,
            "refused_port": 19311,
            "connect_timeout_s": 2,
            "max_bytes": 8192,
        },
    )
    fixture = Path(__file__).resolve().parents[1] / "fixtures/seatbelt_probe.py"
    result = preflight.run(
        authorization_file=auth,
        attempt_id="keep2",
        output_root=persistence_root,
        fixture_path=fixture,
        bundle_dir=write_contract_bundle(tmp_path, contract_sha()),
    )
    assert result["cleanup_blockers"], "an unknown tree state must block cleanup"
    assert (sandbox_root / "keep2").is_dir()
    assert result["package"]["finalized"] is False
