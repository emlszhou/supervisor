"""Independent bounded lifecycle probes; native Windows API is simulated only."""

import array
import ctypes
import fcntl
import json
import os
import select
import signal
import sys
import termios
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
# Execute revised native Windows readiness branch using simulated Win32 API.

local = threading.local()


class Function:
    def __init__(self, callback):
        self.callback = callback

    def __call__(self, *a):
        return self.callback(*a)


def peek(fd, _buf, _size, _read, available, _left):
    value = array.array("i", [0])
    fcntl.ioctl(fd, termios.FIONREAD, value, True)
    available._obj.value = value[0]
    if not value[0] and select.select([fd], [], [], 0)[0]:
        local.error = 109
        return 0
    return 1


kernel = SimpleNamespace(PeekNamedPipe=Function(peek))
proxy = SimpleNamespace(**{k: getattr(os, k) for k in dir(os) if not k.startswith("__")})
proxy.name = "nt"
original_read = os.read
read_sizes = []


def checked_read(fd, n):
    value = array.array("i", [0])
    fcntl.ioctl(fd, termios.FIONREAD, value, True)
    assert 0 < n <= value[0], (n, value[0])
    read_sizes.append(n)
    return original_read(fd, n)


proxy.read = checked_read
baseline_threads = set(threading.enumerate())
with (
    patch.object(m, "os", proxy),
    patch.dict(sys.modules, {"msvcrt": SimpleNamespace(get_osfhandle=lambda fd: fd)}),
    patch.object(ctypes, "WinDLL", return_value=kernel, create=True),
    patch.object(
        ctypes, "get_last_error", side_effect=lambda: getattr(local, "error", 0), create=True
    ),
):
    for name, script in {
        "windows_short": "import os,time;os.write(1,b'short');os.write(2,b'err');time.sleep(.6)",
        "windows_inherited": (
            "import subprocess,sys;"
            "subprocess.Popen([sys.executable,'-c','import time;time.sleep(.6)'])"
        ),
        "windows_exact": "import os;os.write(1,b'x'*64)",
        "windows_flood": "import os;os.write(1,b'x'*4000000)",
    }.items():
        OUT[name] = summary(
            m.ProcessRunner().run(req(script, require_tree_cleanup=False, max_output_bytes=64))
        )
    event = threading.Event()
    timer = threading.Timer(0.04, event.set)
    timer.start()
    OUT["windows_cancel"] = summary(
        m.ProcessRunner().run(
            req("import time;time.sleep(.6)", require_tree_cleanup=False), cancel_event=event
        )
    )
    timer.join()
OUT["windows_simulation"] = {
    "read_calls": len(read_sizes),
    "all_reads_within_available": True,
    "leaked_threads": len(
        [t for t in threading.enumerate() if t not in baseline_threads and t.is_alive()]
    ),
    "native_windows": "not_run",
}
print(json.dumps(OUT, indent=2))
