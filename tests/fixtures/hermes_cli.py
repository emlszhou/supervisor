"""Synthetic Hermes CLI fixture for the M2-B offline adapter contract.

This fixture is a stdlib-only mock that emits the NDJSON protocol that the
real Hermes CLI's ``--format stream-json`` produces. It accepts a single
``--scenario <name>`` argument with a fixed allow-list, and otherwise prints
the corresponding event stream to stdout.

The fixture is deliberately small, deterministic, and self-contained:
  * No imports beyond stdlib.
  * No subprocess, network, model, dynamic code, shell call, or credential
    read paths.
  * No filesystem writes (writes go to stdout/stderr only).
  * Each scenario runs in <3 s wall time and emits <64 KiB output.

The supported scenarios (allow-listed; anything else triggers a non-zero
exit) are:
  - ``success``: clean init / text / result stream with proper session ids.
  - ``nonzero``: emits a partial stream then exits 7 (worker sees non-zero).
  - ``malformed``: emits a non-JSON first line (parser should reject).
  - ``wrong_session``: emits init with session_id=A, result with session_id=B.
  - ``fallback``: emits a stderr warning line before the success stream
    (Adapter contract requires that ANY non-empty stderr cause failure).
  - ``slow``: sleeps long enough that the worker's timeout fires.
  - ``oversized``: emits a result.text of 4097 characters (one over the cap).

This fixture is intentionally separate from any real CLI; it has no hermes
imports and does not call any external binary.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

_ALLOWED_SCENARIOS = frozenset(
    {
        "success",
        "nonzero",
        "malformed",
        "wrong_session",
        "fallback",
        "slow",
        "oversized",
    }
)


def _emit_init(model: str, session_id: str) -> str:
    """Emit the canonical init event."""
    return json.dumps(
        {
            "type": "system",
            "subtype": "init",
            "model": model,
            "session_id": session_id,
            "timestamp": 1700000000,
        }
    )


def _emit_text(body: str) -> str:
    """Emit a text event."""
    return json.dumps(
        {
            "type": "text",
            "text": body,
            "timestamp": 1700000001,
        }
    )


def _emit_result(session_id: str, text: str, *, usage=None) -> str:
    """Emit a result event with the canonical exit_code=0 and optional usage tokens."""
    obj = {
        "type": "result",
        "session_id": session_id,
        "exit_code": 0,
        "text": text,
        "duration_ms": 1234,
        "timestamp": 1700000002,
    }
    if usage is not None:
        obj["tokens"] = usage
    return json.dumps(obj)


def run_scenario(scenario: str) -> int:
    """Run the named scenario. Returns the intended process exit code.

    The fixture emits to stdout/stderr only. Tests inspect ProcessResult
    fields rather than relying on a specific exit code, but we keep
    realistic codes (0 success, 7 nonzero, 1 malformed).
    """
    if scenario not in _ALLOWED_SCENARIOS:
        print(f"unknown scenario {scenario!r}", file=sys.stderr)
        return 2

    if scenario == "success":
        sys.stdout.write(_emit_init("MiniMax-M3", "session-1") + "\n")
        sys.stdout.write(_emit_text("hello world") + "\n")
        sys.stdout.write(_emit_result("session-1", "OK") + "\n")
        sys.stdout.flush()
        return 0

    if scenario == "nonzero":
        # Emit a partial stream then exit non-zero so the worker sees exit != 0.
        sys.stdout.write(_emit_init("MiniMax-M3", "session-1") + "\n")
        sys.stdout.flush()
        return 7

    if scenario == "malformed":
        # Emit non-JSON first line so the parser must reject it.
        sys.stdout.write("not a json line\n")
        sys.stdout.write(_emit_init("MiniMax-M3", "session-1") + "\n")
        sys.stdout.flush()
        return 0

    if scenario == "wrong_session":
        # Init says session-1, result says session-other. Parser must reject.
        sys.stdout.write(_emit_init("MiniMax-M3", "session-1") + "\n")
        sys.stdout.write(_emit_text("OK") + "\n")
        sys.stdout.write(_emit_result("session-other", "OK") + "\n")
        sys.stdout.flush()
        return 0

    if scenario == "fallback":
        # Per the conservative Adapter contract, ANY stderr is rejected.
        # The fixture must therefore put the warning on stderr.
        sys.stderr.write("Primary auth failed - switching to fallback: cloud/MiniMax-M3\n")
        sys.stderr.flush()
        sys.stdout.write(_emit_init("MiniMax-M3", "session-1") + "\n")
        sys.stdout.write(_emit_text("OK") + "\n")
        sys.stdout.write(_emit_result("session-1", "OK") + "\n")
        sys.stdout.flush()
        return 0

    if scenario == "slow":
        # Sleep longer than the Adapter-level test timeout (typically < 3 s).
        # The Worker should see ``timed_out`` and the Adapter should
        # preserve that status without parsing.
        time.sleep(10)
        return 0

    if scenario == "oversized":
        # Emit a terminal text of 4097 chars to violate the 4096-char summary cap.
        sys.stdout.write(_emit_init("MiniMax-M3", "session-1") + "\n")
        sys.stdout.write(_emit_text("OK") + "\n")
        sys.stdout.write(_emit_result("session-1", "x" * 4097) + "\n")
        sys.stdout.flush()
        return 0

    # Unreachable; the allow-list gate above handles unknown scenarios.
    return 2


def main(argv: list[str] | None = None) -> int:
    """Entry point used by ``ProcessRunner.run``."""
    parser = argparse.ArgumentParser(description="synthetic hermes NDJSON fixture")
    parser.add_argument("--scenario", required=True)
    args = parser.parse_args(argv)
    return run_scenario(args.scenario)


if __name__ == "__main__":
    raise SystemExit(main())
