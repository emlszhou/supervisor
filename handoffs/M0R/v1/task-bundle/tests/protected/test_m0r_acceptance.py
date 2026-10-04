"""Independent regressions for Review-2; process probes have an outer watchdog."""

import dataclasses
import importlib
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = dict(
    task_id="M0-process-adapter",
    run_id="m0r-test",
    attempt_id="m0r-test",
    role="implementer",
    provider="mock",
)


def protocol():
    return dict(
        schema_version=1,
        **EXPECTED,
        model="retained-model",
        session_id="session",
        status="completed",
        exit_code=0,
        summary="retained summary",
        error=None,
        usage=None,
        artifacts=[dict(path="result.txt", sha256="a" * 64)],
        truncated=False,
    )


def parse(data, **changes):
    process_module = importlib.import_module("supervisor.workers.process")
    process = process_module.ProcessResult(
        "completed", 0, json.dumps(data).encode(), b"", 0.01, False, None, None
    )
    process = dataclasses.replace(process, **changes)
    result = (
        importlib.import_module("supervisor.agents.base")
        .parse_agent_result(process, expected=EXPECTED)
        .to_dict()
    )
    schema = json.loads((ROOT / "schemas/agent-result.schema.json").read_text())
    Draft202012Validator(schema).validate(result)
    return result


def probe(tmp_path, child, timeout=0.1, budget=4096, cancel=False):
    code = f"""
import json,sys,time,threading
from pathlib import Path
from supervisor.workers.process import ProcessRequest,ProcessRunner
root=Path({str(tmp_path)!r})
event=threading.Event()
if {cancel!r}:
    threading.Timer(.1,event.set).start()
r=ProcessRunner().run(ProcessRequest(argv=(sys.executable,'-c',{child!r}),cwd=root,workspace_root=root,env={{}},timeout_seconds={timeout!r},max_output_bytes={budget!r},require_tree_cleanup=False),cancel_event=event)
print(json.dumps(dict(status=r.status,duration=r.duration_seconds,size=len(r.stdout)+len(r.stderr),truncated=r.truncated)))
"""
    # Whitelist test environment; no host credentials passed into probe process.
    env = {
        k: os.environ[k]
        for k in ("PATH", "SYSTEMROOT", "PYTHONPATH", "VIRTUAL_ENV")
        if k in os.environ
    }
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=os.name == "posix",
    )
    try:
        out, err = proc.communicate(timeout=3)
        assert proc.returncode == 0, err.decode(errors="replace")
        return json.loads(out)
    finally:
        if os.name == "posix":
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif proc.poll() is None:
            proc.kill()
        proc.communicate()


@pytest.mark.parametrize(
    "child",
    [
        "import os,time;os.write(1,b'x');time.sleep(.8)",
        "import os,time;os.write(1,b'x');os.write(2,b'y');time.sleep(.8)",
    ],
)
def test_short_output_obeys_timeout(tmp_path, child):
    result = probe(tmp_path, child)
    assert result["status"] == "timed_out"
    assert result["duration"] < 0.6


def test_short_output_obeys_cancellation(tmp_path):
    result = probe(
        tmp_path, "import os,time;os.write(1,b'x');time.sleep(.8)", timeout=2, cancel=True
    )
    assert result["status"] == "cancelled"
    assert result["duration"] < 0.6


@pytest.mark.parametrize("size", [63, 64, 65])
def test_exact_output_boundary(tmp_path, size):
    result = probe(tmp_path, f"import os;os.write(1,b'x'*{size})", timeout=2, budget=64)
    assert result["status"] == ("completed" if size <= 64 else "output_limit")
    assert result["truncated"] == (size > 64)
    assert result["size"] == min(size, 64)


@pytest.mark.parametrize(
    "status", ["failed", "timed_out", "cancelled", "output_limit", "environment_failure"]
)
def test_actual_process_status_wins(status):
    result = parse(protocol(), status=status, exit_code=0)
    assert result["status"] == status


def test_valid_protocol_fields_survive():
    data = protocol()
    data["usage"] = dict(input_tokens=2, output_tokens=3)
    result = parse(data)
    assert result["status"] == "completed"
    for field in ("model", "session_id", "summary", "usage", "artifacts"):
        assert result[field] == data[field]


@pytest.mark.parametrize(
    "field,value",
    [
        ("artifacts", None),
        ("usage", dict(input_tokens=True, output_tokens=0)),
        ("schema_version", True),
    ],
)
def test_strict_protocol_types(field, value):
    data = protocol()
    data[field] = value
    assert parse(data)["status"] == "failed"
