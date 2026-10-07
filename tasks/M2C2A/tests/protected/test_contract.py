"""Coordinator-owned offline behavior tests; no host sandbox or model calls."""

import copy
import hashlib
import json
from pathlib import Path

import pytest


def api():
    from supervisor.workers import backend

    return backend


def case(**changes):
    value = dict(
        test_kind="expected_refuse",
        action_exit_code=1,
        action_errno="EPERM",
        action_started=True,
        action_completed=True,
        effect_observed=False,
        control_passed=True,
        target_unchanged=True,
        cleanup_confirmed=True,
        output_limited=False,
        observation_complete=True,
    )
    value.update(changes)
    return value


@pytest.mark.parametrize(
    "changes, expected",
    [
        ({}, "pass"),
        ({"action_errno": "EACCES"}, "pass"),
        ({"action_errno": "ENOENT"}, "unknown"),
        ({"action_errno": "ECONNREFUSED"}, "unknown"),
        ({"control_passed": False}, "unknown"),
        ({"action_started": False}, "unknown"),
        ({"observation_complete": False}, "unknown"),
        ({"output_limited": True}, "unknown"),
        ({"action_exit_code": 0, "effect_observed": True}, "fail"),
        ({"effect_observed": True}, "fail"),
        ({"effect_observed": True, "output_limited": True}, "fail"),
        ({"target_unchanged": False}, "fail"),
        (
            {
                "test_kind": "positive",
                "action_exit_code": 0,
                "action_errno": None,
                "effect_observed": True,
            },
            "pass",
        ),
        (
            {
                "test_kind": "positive",
                "action_exit_code": 0,
                "action_errno": None,
                "effect_observed": False,
            },
            "fail",
        ),
        (
            {
                "test_kind": "timeout_cleanup",
                "action_exit_code": -15,
                "action_errno": None,
                "action_completed": False,
            },
            "pass",
        ),
        (
            {
                "test_kind": "timeout_cleanup",
                "action_exit_code": -9,
                "action_completed": False,
                "cleanup_confirmed": None,
            },
            "unknown",
        ),
        ({"test_kind": "timeout_cleanup", "cleanup_confirmed": False}, "fail"),
    ],
)
def test_classification(changes, expected):
    value = case(**changes)
    before = copy.deepcopy(value)
    assert api().classify_case(value) == expected
    assert value == before


@pytest.mark.parametrize(
    "key,value",
    [
        ("action_exit_code", True),
        ("action_started", 1),
        ("cleanup_confirmed", "yes"),
        ("test_kind", "invented"),
    ],
)
def test_invalid_case(key, value):
    with pytest.raises(ValueError):
        api().classify_case(case(**{key: value}))


def results():
    return {
        **{key: ["pass"] for key in ("T1", "T2", "T3", "T5", "T6")},
        "T4": "out_of_scope",
        "T7": "pass",
    }


def test_summary():
    value = results()
    assert api().summarize_results(value) == "full_pass"
    value["T6"] = ["unknown"]
    assert api().summarize_results(value) == "partial"
    value["T1"] = ["fail"]
    assert api().summarize_results(value) == "fail"


@pytest.mark.parametrize("change", ["empty", "missing", "extra", "mcp"])
def test_invalid_summary(change):
    value = results()
    if change == "empty":
        value["T1"] = []
    elif change == "missing":
        del value["T7"]
    elif change == "extra":
        value["T8"] = "pass"
    else:
        value["T4"] = "pass"
    with pytest.raises(ValueError):
        api().summarize_results(value)


@pytest.mark.parametrize("kwargs", [{}, {"allow_live": True}])
def test_live_disabled(kwargs):
    with pytest.raises(RuntimeError, match="live_execution_disabled"):
        api().require_live_execution(**kwargs)


def profile_args():
    return {
        key: "/private/tmp/m2c2-sandbox/a/" + key
        for key in ("work", "ro", "denied", "secret", "harness")
    }


@pytest.mark.parametrize(
    "key,value",
    [
        ("work", "relative"),
        ("ro", "/a/../b"),
        ("work", "/a\x00b"),
        ("allow_endpoint", ("8.8.8.8", 80)),
        ("allow_endpoint", ("127.0.0.1", True)),
        ("allow_endpoint", ("127.0.0.1", 0)),
        ("allow_target", "/Users/operator/.hermes/.env"),
    ],
)
def test_invalid_profile(key, value):
    params = profile_args()
    params[key] = value
    with pytest.raises(ValueError):
        api().build_profile(**params)


def test_profile_overlap():
    params = profile_args()
    params["harness"] = params["work"] + "/harness"
    with pytest.raises(ValueError):
        api().build_profile(**params)


def package(root: Path):
    (root / "capture").mkdir()
    (root / "evidence").mkdir()
    (root / "capture/x.log").write_bytes(b"synthetic errno=EPERM\n")
    record = {
        "test_id": "x",
        "capture_file": "capture/x.log",
        "capture_sha256": hashlib.sha256((root / "capture/x.log").read_bytes()).hexdigest(),
    }
    (root / "evidence/x.json").write_text(json.dumps(record))
    (root / "summary.json").write_text(
        json.dumps([{"test_id": "x", "record_ref": "evidence/x.json"}])
    )
    manifest = {
        "schema_version": 1,
        "files": [
            {
                "path": str(p.relative_to(root)),
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                "bytes": len(p.read_bytes()),
            }
            for p in sorted(root.rglob("*"))
            if p.is_file()
        ],
    }
    raw = json.dumps(manifest).encode()
    (root / "manifest.json").write_bytes(raw)
    (root / "CHECKSUMS.sha256").write_text(hashlib.sha256(raw).hexdigest() + "  manifest.json\n")
    return manifest


def verifier():
    from supervisor.workers.evidence import verify_package

    return verify_package


def test_valid_package(tmp_path):
    value = package(tmp_path)
    assert verifier()(tmp_path) == value


@pytest.mark.parametrize("tamper", ["bytes", "extra", "symlink", "checksum", "missing"])
def test_package_tampering(tmp_path, tamper):
    package(tmp_path)
    if tamper == "bytes":
        (tmp_path / "capture/x.log").write_bytes(b"different")
    elif tamper == "extra":
        (tmp_path / "extra").write_bytes(b"unexpected")
    elif tamper == "symlink":
        (tmp_path / "capture/x.log").unlink()
        (tmp_path / "capture/x.log").symlink_to(tmp_path / "summary.json")
    elif tamper == "checksum":
        (tmp_path / "CHECKSUMS.sha256").write_text("0" * 64 + "  manifest.json\n")
    else:
        (tmp_path / "evidence/x.json").unlink()
    with pytest.raises(ValueError):
        verifier()(tmp_path)


@pytest.mark.parametrize("path", ["../escape", "/absolute", "capture/../x", "a\x00b"])
def test_manifest_paths(tmp_path, path):
    value = package(tmp_path)
    value["files"][0]["path"] = path
    raw = json.dumps(value).encode()
    (tmp_path / "manifest.json").write_bytes(raw)
    (tmp_path / "CHECKSUMS.sha256").write_text(
        hashlib.sha256(raw).hexdigest() + "  manifest.json\n"
    )
    with pytest.raises(ValueError):
        verifier()(tmp_path)
