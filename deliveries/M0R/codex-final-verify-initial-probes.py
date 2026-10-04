"""Independent bounded lifecycle probes; native Windows API is simulated only."""

import ctypes
import json
import os
import signal
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from supervisor.workers import process as m

ROOT = Path.cwd()
OUT = {}


def req(script, **kw):
    return m.ProcessRequest(
        (sys.executable, "-c", script), ROOT, ROOT, {}, timeout_seconds=0.12, **kw
    )


def summary(r):
    return {k: len(v) if isinstance(v, bytes) else v for k, v in r.__dict__.items()}


for name, script in {
    "short": "import os,time;os.write(1,b'short');os.write(2,b'err');time.sleep(.6)",
    "inherited": (
        "import subprocess,sys;subprocess.Popen([sys.executable,'-c','import time;time.sleep(.6)'])"
    ),
    "exact": "import os;os.write(1,b'x'*64)",
    "flood": "import os;os.write(1,b'x'*4000000)",
}.items():
    OUT[name] = summary(m.ProcessRunner().run(req(script, max_output_bytes=64)))
event = threading.Event()
timer = threading.Timer(0.05, event.set)
timer.start()
OUT["cancel"] = summary(
    m.ProcessRunner().run(req("import time;time.sleep(.6)"), cancel_event=event)
)
timer.join()
with patch.object(m.os, "killpg", side_effect=PermissionError("synthetic denial")):
    OUT["killpg_denied"] = summary(m.ProcessRunner().run(req("import time;time.sleep(.6)")))
original = m.subprocess.Popen
captured = []


def capture(*a, **kw):
    p = original(*a, **kw)
    captured.append(p)
    return p


with (
    patch.object(m.subprocess, "Popen", side_effect=capture),
    patch.object(m.ProcessRunner, "_drive_process", side_effect=RuntimeError("injected")),
):
    OUT["drive_exception"] = summary(m.ProcessRunner().run(req("import time;time.sleep(.6)")))
    OUT["drive_exception"].update(
        alive=captured[0].poll() is None,
        pipes_closed=all(s.closed for s in (captured[0].stdout, captured[0].stderr)),
    )
pidfile = Path("/tmp/m0r-final-evidence/escaped.pid")
script = (
    "import subprocess,sys,time;"
    "subprocess.Popen([sys.executable,'-c',"
    f"\"import os,time;open({str(pidfile)!r},'w').write(str(os.getpid()));"
    'time.sleep(.8)"],start_new_session=True);time.sleep(.8)'
)
OUT["escaped"] = summary(m.ProcessRunner().run(req(script)))
pid = int(pidfile.read_text())
try:
    state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
except FileNotFoundError:
    state = "absent"
OUT["escaped"]["descendant_state"] = state
if state not in ("Z", "absent"):
    os.kill(pid, signal.SIGKILL)
with (
    patch.object(m, "_is_posix", return_value=False),
    patch.object(m.select, "select", side_effect=OSError("non-socket")),
):
    OUT["pipe_select_unavailable"] = summary(
        m.ProcessRunner().run(
            req("import os,time;os.write(1,b'short');time.sleep(.6)", require_tree_cleanup=False)
        )
    )
# Model legal Windows scheduling: cancellation occurs just before read starts.
entered = threading.Event()
release = threading.Event()


class Function:
    def __init__(self, callback):
        self.callback = callback

    def __call__(self, *a):
        return self.callback(*a)


kernel = SimpleNamespace(
    OpenThread=Function(lambda *a: 1),
    CancelSynchronousIo=Function(lambda *a: 0),
    CloseHandle=Function(lambda *a: 1),
)


def delayed_read(fd, n):
    entered.set()
    release.wait(2)
    return b""


proxy = SimpleNamespace(**{k: getattr(os, k) for k in dir(os) if not k.startswith("__")})
proxy.name = "nt"
proxy.read = delayed_read
baseline_threads = set(threading.enumerate())
with patch.object(m, "os", proxy), patch.object(ctypes, "WinDLL", return_value=kernel, create=True):
    r = m.ProcessRunner().run(
        req("import time;time.sleep(.6)", require_tree_cleanup=False, cancel_grace_seconds=0.04)
    )
    alive = [t for t in threading.enumerate() if t not in baseline_threads and t.is_alive()]
    OUT["windows_cancellation_race"] = dict(
        result=summary(r),
        leaked_reader_threads=len(alive),
        scheduling="read entered after loop stop check; CancelSynchronousIo reports no pending I/O",
    )
    release.set()
    for t in alive:
        t.join(1)
print(json.dumps(OUT, indent=2))
