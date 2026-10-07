#!/usr/bin/env python3
"""Fixed Seatbelt probe fixture (runs inside the sandbox under the profile).

Started only through an argument array (never a shell string).  Performs one
synthetic action chosen by ``--action``, then prints a structured JSON status
line describing what the *process* actually observed (exit-relevant errno,
effect, child/depth state).  Unknown or corrupt output upstream must be treated
as ``unknown``; this fixture never self-certifies absence of side effects it
cannot observe.

Actions (all targets are synthetic paths inside the attempt):
  write --target P        append one synthetic line (O_WRONLY|O_APPEND)
  read  --target P        read the whole file
  connect --host H --port N
  child --depth N         spawn N generations of python -c "pass" children
  timeout                 sleep 30s (for the expected-timeout sub-item)
  env                     report whether probe env names are present

Exit codes: 0 = the observed action completed as the caller expected for the
*positive* control; non-zero = the action hit the boundary.  The harness
records the real exit code and errno independently of this self-report.
"""

from __future__ import annotations

import argparse
import errno as errno_module
import json
import os
import socket
import subprocess
import sys
import time


def _errno_name(number: int | None) -> str | None:
    if number is None:
        return None
    return errno_module.errorcode.get(number, f"UNKNOWN_{number}")


def _emit(status: dict) -> None:
    print(json.dumps(status))
    sys.stdout.flush()


def action_write(target: str) -> int:
    try:
        fd = os.open(target, os.O_WRONLY | os.O_APPEND)
    except OSError as exc:
        _emit(
            {
                "action": "write",
                "target": target,
                "completed": False,
                "errno": _errno_name(exc.errno),
                "effect": False,
            }
        )
        return 1
    try:
        os.write(fd, b"synthetic-append-line\n")
        _emit(
            {
                "action": "write",
                "target": target,
                "completed": True,
                "errno": None,
                "effect": True,
            }
        )
        return 0
    except OSError as exc:
        _emit(
            {
                "action": "write",
                "target": target,
                "completed": False,
                "errno": _errno_name(exc.errno),
                "effect": False,
            }
        )
        return 1
    finally:
        os.close(fd)


def action_read(target: str) -> int:
    try:
        with open(target, "rb") as handle:
            data = handle.read()
        _emit(
            {
                "action": "read",
                "target": target,
                "completed": True,
                "errno": None,
                "effect": True,
                "bytes": len(data),
            }
        )
        return 0
    except OSError as exc:
        _emit(
            {
                "action": "read",
                "target": target,
                "completed": False,
                "errno": _errno_name(exc.errno),
                "effect": False,
            }
        )
        return 1


def action_connect(host: str, port: int) -> int:
    try:
        with socket.create_connection((host, port), timeout=2) as sock:
            sock.sendall(b"synthetic-probe\n")
            _emit(
                {
                    "action": "connect",
                    "host": host,
                    "port": port,
                    "completed": True,
                    "errno": None,
                    "effect": True,
                }
            )
            return 0
    except OSError as exc:
        _emit(
            {
                "action": "connect",
                "host": host,
                "port": port,
                "completed": False,
                "errno": _errno_name(exc.errno),
                "effect": False,
            }
        )
        return 1


def action_child(depth: int) -> int:
    if depth <= 0:
        _emit({"action": "child", "depth_reached": 0, "completed": True, "errno": None})
        return 0
    if depth > 2:
        # Keep the tree tiny and deterministic; deeper trees are out of scope.
        _emit(
            {
                "action": "child",
                "depth_reached": depth,
                "completed": False,
                "errno": None,
                "note": "depth capped at 2",
            }
        )
        return 1
    cmd = [sys.executable, "-c", "import time; time.sleep(0.1)"]
    try:
        child = subprocess.run(cmd, capture_output=True, timeout=10)
    except subprocess.TimeoutExpired:
        _emit({"action": "child", "depth_reached": 1, "completed": False, "errno": None})
        return 1
    _emit(
        {
            "action": "child",
            "depth_reached": depth if child.returncode == 0 else 1,
            "child_exit_code": child.returncode,
            "completed": child.returncode == 0,
            "errno": None,
        }
    )
    return 0 if child.returncode == 0 else 1


def action_timeout() -> int:
    time.sleep(30)
    _emit({"action": "timeout", "completed": True, "errno": None})
    return 0


def action_env() -> int:
    names = sorted(n for n in os.environ if n.startswith("M2C2A_"))
    _emit({"action": "env", "names": names, "completed": True, "errno": None})
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="seatbelt_probe")
    parser.add_argument(
        "--action", required=True, choices=["write", "read", "connect", "child", "timeout", "env"]
    )
    parser.add_argument("--target", default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--depth", type=int, default=1)
    args = parser.parse_args()

    if args.action == "write":
        if not args.target:
            _emit({"action": "write", "completed": False, "errno": None, "note": "missing target"})
            return 2
        return action_write(args.target)
    if args.action == "read":
        if not args.target:
            _emit({"action": "read", "completed": False, "errno": None, "note": "missing target"})
            return 2
        return action_read(args.target)
    if args.action == "connect":
        if not args.host or args.port is None:
            _emit(
                {
                    "action": "connect",
                    "completed": False,
                    "errno": None,
                    "note": "missing endpoint",
                }
            )
            return 2
        return action_connect(args.host, args.port)
    if args.action == "child":
        return action_child(args.depth)
    if args.action == "timeout":
        return action_timeout()
    return action_env()


if __name__ == "__main__":
    raise SystemExit(main())
