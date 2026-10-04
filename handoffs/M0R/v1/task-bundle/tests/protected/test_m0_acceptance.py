"""Independent M0 black-box contract. Missing implementation must fail, never skip."""

import dataclasses
import importlib
import importlib.util
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
CONTEXT = {
    "task_id": "M0-process-adapter",
    "run_id": "acceptance-run",
    "attempt_id": "acceptance-attempt",
    "role": "implementer",
    "provider": "mock",
}


def module(name):
    qualified = f"supervisor.{name}"
    assert importlib.util.find_spec(qualified) is not None, f"M0 not implemented: {qualified}"
    return importlib.import_module(qualified)


def validate(name, data):
    schema = json.loads((ROOT / "schemas" / f"{name}.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(data)


def request(workspace, code, *arguments, **overrides):
    fields = {
        "argv": (sys.executable, "-c", code, *arguments),
        "cwd": workspace,
        "workspace_root": workspace,
        "env": {},
        "timeout_seconds": 2.0,
        "cancel_grace_seconds": 0.2,
        "max_output_bytes": 4096,
        "attempt_id": CONTEXT["attempt_id"],
        "require_tree_cleanup": False,
    }
    fields.update(overrides)
    return module("workers.process").ProcessRequest(**fields)


def run(req, cancel_event=None):
    return module("workers.process").ProcessRunner().run(req, cancel_event=cancel_event)


def payload():
    return {
        "schema_version": 1,
        **CONTEXT,
        "model": None,
        "session_id": "acceptance-session",
        "status": "completed",
        "exit_code": 0,
        "summary": "Fixed acceptance fixture",
        "error": None,
        "usage": None,
        "artifacts": [],
        "truncated": False,
    }


def parsed(data, **overrides):
    fields = {
        "status": "completed",
        "exit_code": 0,
        "stdout": json.dumps(data).encode(),
        "stderr": b"",
        "duration_seconds": 0.01,
        "truncated": False,
        "tree_cleanup_confirmed": None,
        "error": None,
    }
    fields.update(overrides)
    process = module("workers.process").ProcessResult(**fields)
    return module("agents.base").parse_agent_result(process, expected=CONTEXT).to_dict()


@pytest.mark.parametrize("name", ["workers.process", "agents.base", "agents.mock", "core.events"])
def test_public_modules_exist(name):
    module(name)


def test_normal_process_captures_both_streams(tmp_path):
    result = run(request(tmp_path, "import sys; print('out'); print('err', file=sys.stderr)"))
    assert result.status == "completed"
    assert result.exit_code == 0
    assert result.stdout.strip() == b"out"
    assert result.stderr.strip() == b"err"
    assert result.truncated is False
    assert 0 <= result.duration_seconds < 5


def test_nonzero_exit_is_preserved(tmp_path):
    result = run(request(tmp_path, "import sys; print('failed'); sys.exit(7)"))
    assert result.status == "failed"
    assert result.exit_code == 7
    assert result.error


def test_arguments_are_literal_and_workspace_with_spaces_is_supported(tmp_path):
    workspace = tmp_path / "space 中文"
    workspace.mkdir()
    marker = workspace / "must-not-exist"
    argument = f"x; touch {marker} $(echo injected)"
    result = run(request(workspace, "import json,sys; print(json.dumps(sys.argv[1:]))", argument))
    assert result.status == "completed"
    assert json.loads(result.stdout) == [argument]
    assert not marker.exists()


@pytest.mark.parametrize("missing", ["executable", "cwd"])
def test_missing_prerequisite_is_environment_failure(tmp_path, missing):
    req = request(tmp_path, "pass")
    field = (
        {"argv": (str(tmp_path / "absent-program"),)}
        if missing == "executable"
        else {"cwd": tmp_path / "absent-directory"}
    )
    before = Path.cwd()
    result = run(dataclasses.replace(req, **field))
    assert result.status == "environment_failure"
    assert result.error
    assert result.exit_code is None
    assert Path.cwd() == before


def test_cwd_outside_authorized_root_is_rejected(tmp_path):
    workspace = tmp_path / "allowed"
    workspace.mkdir()
    with pytest.raises(ValueError):
        run(request(workspace, "pass", cwd=tmp_path))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("argv", ()),
        ("argv", ("python", "-c", "pass")),
        ("timeout_seconds", 0),
        ("timeout_seconds", -1),
        ("timeout_seconds", float("nan")),
        ("timeout_seconds", float("inf")),
        ("cancel_grace_seconds", 0),
        ("cancel_grace_seconds", float("nan")),
        ("max_output_bytes", 0),
        ("max_output_bytes", -1),
        ("max_output_bytes", True),
    ],
)
def test_invalid_request_never_starts_a_child(tmp_path, field, value):
    marker = tmp_path / "unexpected-start"
    with pytest.raises(ValueError):
        req = request(
            tmp_path, "import pathlib,sys; pathlib.Path(sys.argv[1]).touch()", str(marker)
        )
        run(dataclasses.replace(req, **{field: value}))
    assert not marker.exists()


def test_child_environment_is_explicit_not_inherited(tmp_path, monkeypatch):
    monkeypatch.setenv("M0_HOST_SECRET_SENTINEL", "non-production-private-sentinel")
    code = "import json,os; print(json.dumps(dict(os.environ)))"
    result = run(request(tmp_path, code, env={"M0_ALLOWED_SENTINEL": "allowed"}))
    assert result.status == "completed"
    environment = json.loads(result.stdout)
    assert environment["M0_ALLOWED_SENTINEL"] == "allowed"
    assert "M0_HOST_SECRET_SENTINEL" not in environment
    assert b"non-production-private-sentinel" not in result.stderr


def test_pre_cancelled_request_does_not_start(tmp_path):
    marker = tmp_path / "unexpected-start"
    cancelled = threading.Event()
    cancelled.set()
    result = run(
        request(tmp_path, "import pathlib,sys; pathlib.Path(sys.argv[1]).touch()", str(marker)),
        cancelled,
    )
    assert result.status == "cancelled"
    assert not marker.exists()


def test_running_process_can_be_cancelled(tmp_path):
    cancelled = threading.Event()
    timer = threading.Timer(0.15, cancelled.set)
    timer.start()
    started = time.monotonic()
    try:
        result = run(request(tmp_path, "import time; time.sleep(30)"), cancelled)
    finally:
        timer.cancel()
    assert result.status == "cancelled"
    assert time.monotonic() - started < 5
    assert result.error


def test_wall_timeout_is_enforced(tmp_path):
    started = time.monotonic()
    result = run(request(tmp_path, "import time; time.sleep(30)", timeout_seconds=0.15))
    assert result.status == "timed_out"
    assert result.error
    assert time.monotonic() - started < 5


def test_two_stream_flood_is_bounded_and_does_not_deadlock(tmp_path):
    code = (
        "import os,threading; "
        "t=threading.Thread(target=lambda: [os.write(2,b'e'*1024) for _ in range(10000)]); "
        "t.start(); [os.write(1,b'o'*1024) for _ in range(10000)]; t.join()"
    )
    started = time.monotonic()
    result = run(request(tmp_path, code, max_output_bytes=2048))
    assert result.status == "output_limit"
    assert result.truncated is True
    assert len(result.stdout) + len(result.stderr) <= 2048
    assert time.monotonic() - started < 5


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    proc = Path(f"/proc/{pid}/stat")
    if proc.exists() and proc.read_text().rsplit(")", 1)[1].split()[0] == "Z":
        return False
    return True


@pytest.mark.parametrize("stop", ["timeout", "cancel"])
def test_descendant_cleanup_or_explicit_unsupported(tmp_path, stop):
    marker = tmp_path / "descendant.pid"
    code = (
        "import pathlib,subprocess,sys,time; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid)); time.sleep(30)"
    )
    req = request(
        tmp_path,
        code,
        str(marker),
        require_tree_cleanup=True,
        timeout_seconds=0.6 if stop == "timeout" else 3.0,
    )
    cancelled = threading.Event()
    timer = threading.Timer(0.6, cancelled.set) if stop == "cancel" else None
    if timer:
        timer.start()
    try:
        result = run(req, cancelled)
        if os.name != "posix" and result.status == "environment_failure":
            assert "unsupported" in result.error.lower()
            assert not marker.exists()
            return
        assert result.status == ("timed_out" if stop == "timeout" else "cancelled")
        assert result.tree_cleanup_confirmed is True
        assert marker.exists(), "Child fixture never started; cleanup was not exercised"
        pid = int(marker.read_text())
        deadline = time.monotonic() + 2
        while alive(pid) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not alive(pid), "Descendant survived cleanup"
    finally:
        if timer:
            timer.cancel()
        if marker.exists():
            pid = int(marker.read_text())
            if alive(pid):
                os.kill(pid, 9)


def test_parser_accepts_valid_result_and_unknown_usage():
    result = parsed(payload())
    validate("agent-result", result)
    assert result["status"] == "completed"
    assert result["usage"] is None


@pytest.mark.parametrize("field", ["task_id", "run_id", "attempt_id", "role", "provider"])
def test_output_identity_cannot_override_expected_identity(field):
    data = payload()
    data[field] = "other" if field != "role" else "reviewer"
    result = parsed(data)
    validate("agent-result", result)
    assert result["status"] == "failed"
    assert result[field] == CONTEXT[field]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", 2),
        ("exit_code", 7),
        ("session_id", None),
        ("truncated", True),
        ("permission_override", "full-access"),
        ("usage", {"input_tokens": -1, "output_tokens": None}),
        ("artifacts", [{"path": "../escape", "sha256": "0" * 64}]),
    ],
)
def test_parser_rejects_invalid_or_unsafe_protocol(field, value):
    data = payload()
    data[field] = value
    result = parsed(data)
    validate("agent-result", result)
    assert result["status"] == "failed"
    assert result["error"]


def test_parser_rejects_missing_field():
    data = payload()
    del data["session_id"]
    assert parsed(data)["status"] == "failed"


@pytest.mark.parametrize("raw", [b"not-json private-sentinel", b"{} {}", b"\xff"])
def test_parser_errors_do_not_echo_raw_output(raw):
    result = parsed(payload(), stdout=raw)
    validate("agent-result", result)
    assert result["status"] == "failed"
    assert "private-sentinel" not in result["error"]


@pytest.mark.parametrize("status", ["failed", "timed_out", "cancelled", "output_limit"])
def test_process_failure_overrules_stdout_completed(status):
    result = parsed(
        payload(),
        status=status,
        exit_code=7,
        truncated=status == "output_limit",
        error="Fixed process failure",
    )
    validate("agent-result", result)
    assert result["status"] == status
    assert result["exit_code"] == 7


@pytest.mark.parametrize(
    ("scenario", "expected_status"),
    [
        ("success", "completed"),
        ("nonzero", "failed"),
        ("malformed", "failed"),
        ("wrong_identity", "failed"),
        ("timeout", "timed_out"),
    ],
)
def test_mock_round_trip(tmp_path, scenario, expected_status):
    adapter = module("agents.mock").MockAdapter(scenario=scenario)
    req = adapter.build_request(CONTEXT, tmp_path)
    if scenario == "timeout":
        req = dataclasses.replace(req, timeout_seconds=0.15)
    result = adapter.parse_result(run(req), expected=CONTEXT).to_dict()
    validate("agent-result", result)
    assert result["status"] == expected_status
    assert all(result[key] == value for key, value in CONTEXT.items())


def test_mock_rejects_unknown_scenario():
    with pytest.raises(ValueError):
        module("agents.mock").MockAdapter(scenario="execute-arbitrary-shell")


def test_events_have_unique_continuous_sequences_and_valid_metadata():
    recorder = module("core.events").EventRecorder(
        task_id=CONTEXT["task_id"], run_id=CONTEXT["run_id"], worker_id="acceptance-worker"
    )
    with ThreadPoolExecutor(max_workers=4) as pool:
        events = list(pool.map(lambda _: recorder.record("AgentStarted"), range(12)))
    assert sorted(event["sequence"] for event in events) == list(range(1, 13))
    assert len({event["event_id"] for event in events}) == 12
    for event in events:
        validate("event", event)
        assert event["task_id"] == CONTEXT["task_id"]
        assert event["run_id"] == CONTEXT["run_id"]


def test_event_input_cannot_accept_unknown_types_or_raw_transcripts():
    recorder = module("core.events").EventRecorder(
        task_id=CONTEXT["task_id"], run_id=CONTEXT["run_id"], worker_id="acceptance-worker"
    )
    with pytest.raises(ValueError):
        recorder.record("UnknownEvent")
    with pytest.raises(TypeError):
        recorder.record("AgentStarted", raw_prompt="private-sentinel")
