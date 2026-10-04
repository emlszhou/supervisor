"""Behavior regressions for the bounded-reader takeover."""

import os
import sys
import threading
import time
from pathlib import Path

import pytest

from supervisor.workers.process import ProcessRequest, ProcessRunner


def run(root, code, **overrides):
    return ProcessRunner().run(
        ProcessRequest(
            argv=(sys.executable, "-c", code),
            cwd=root,
            workspace_root=root,
            env={},
            require_tree_cleanup=False,
            **overrides,
        )
    )


def test_leader_exit_inherited_pipe_deadline(tmp_path):
    before = time.monotonic()
    result = run(
        tmp_path,
        (
            "import subprocess,sys;"
            "subprocess.Popen([sys.executable,'-c','import time;time.sleep(.5)'])"
        ),
        timeout_seconds=0.1,
    )
    assert result.status == "timed_out"
    assert time.monotonic() - before < 0.35
    time.sleep(0.55)
    assert not any(t.name.startswith("Thread-") and t.is_alive() for t in threading.enumerate())


def test_short_output_survives_timeout(tmp_path):
    result = run(
        tmp_path,
        "import os,time;os.write(1,b'out');os.write(2,b'err');time.sleep(.4)",
        timeout_seconds=0.1,
    )
    assert result.status == "timed_out"
    assert (result.stdout, result.stderr) == (b"out", b"err")


def test_large_finite_output_bounded(tmp_path):
    result = run(
        tmp_path, "import os;os.write(1,b'x'*4000000)", timeout_seconds=2, max_output_bytes=64
    )
    assert result.status == "output_limit"
    assert len(result.stdout) + len(result.stderr) == 64


@pytest.mark.skipif(not Path("/proc").exists(), reason="Linux ancestry observation")
def test_separate_session_descendant_is_stopped(tmp_path):
    pidfile = tmp_path / "child.pid"
    code = (
        "import subprocess,sys,time;"
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(2)'],"
        "start_new_session=True);"
        f"open({str(pidfile)!r},'w').write(str(p.pid));time.sleep(2)"
    )
    result = ProcessRunner().run(
        ProcessRequest(
            argv=(sys.executable, "-c", code),
            cwd=tmp_path,
            workspace_root=tmp_path,
            env={},
            timeout_seconds=0.2,
        )
    )
    pid = int(pidfile.read_text())
    try:
        stat = Path(f"/proc/{pid}/stat")
        assert not stat.exists() or stat.read_text().rsplit(")", 1)[1].split()[0] == "Z"
        assert result.tree_cleanup_confirmed is True
    finally:
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass
