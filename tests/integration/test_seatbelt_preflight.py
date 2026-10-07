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
                "platform": platform.system().lower(),
                "roots": {
                    "sandbox_root": "/tmp/m2c2-sandbox",
                    "persistence_root": str(path.parent / "persist"),
                },
                "loopback": {
                    "family": "tcp",
                    "host": "127.0.0.1",
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
    contract = Path(__file__).resolve().parents[2].parent / "M2C2A-v1-contract"
    handoff = contract / "handoff.json"
    return json.loads(handoff.read_text())["bundle_sha256"]


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
    auth = tmp_path / "auth.json"
    write_authorization(auth, "f" * 64)
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
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "not_run" in result.stdout
    assert "authorization_invalid" in result.stdout


def test_non_darwin_platform_refuses(tmp_path, monkeypatch):
    auth = tmp_path / "auth.json"
    write_authorization(auth, contract_sha())
    result = preflight.run(
        authorization_file=auth,
        attempt_id="a3",
        output_root=tmp_path / "out",
        forced_platform="linux",
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
    """Copy evidence + summary + manifest into an output root and verify."""
    source = tmp_path / "attempt"
    pkg_root = tmp_path / "persist/m2c2a-test"
    (pkg_root / "capture").mkdir(parents=True)
    (pkg_root / "evidence").mkdir(parents=True)
    capture = pkg_root / "capture/T1-w.log"
    capture.write_bytes(b"synthetic stderr\n")
    record = {
        "test_id": "T1-w",
        "capture_file": "capture/T1-w.log",
        "capture_sha256": sha256_file(capture),
    }
    (pkg_root / "evidence/T1-w.json").write_text(json.dumps(record))
    (pkg_root / "summary.json").write_text(
        json.dumps([{"test_id": "T1-w", "record_ref": "evidence/T1-w.json"}])
    )

    preflight.persist_package(
        source_attempt=source,
        package_root=pkg_root,
        test_ids=["T1-w"],
        fresh=True,
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
    assert report["provider"] == "cloud-authorized"


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
