"""Run with the exact M2-B candidate's environment; these are rejection probes."""

import json

from supervisor.agents.hermes import HermesAdapter
from supervisor.workers.process import ProcessResult

EXPECTED = dict(
    task_id="M2B",
    run_id="run",
    attempt_id="attempt",
    role="implementer",
    provider="minimax-cn",
    model="MiniMax-M3",
)
BASE = [
    dict(type="system", subtype="init", model="MiniMax-M3", session_id="s"),
    dict(type="result", session_id="s", exit_code=0, text="OK"),
]
CASES = [
    ("failed_worker", BASE, dict(status="failed"), "failed", 0),
    ("text_before_init", [dict(type="text", text="early")] + BASE, {}, "failed", 0),
    ("infinite_timestamp", [{**BASE[0], "timestamp": float("inf")}, BASE[1]], {}, "failed", 0),
    (
        "unknown_token",
        [BASE[0], {**BASE[1], "tokens": dict(input=1, output=2, unknown=3)}],
        {},
        "failed",
        0,
    ),
    ("null_timestamp", [{**BASE[0], "timestamp": None}, BASE[1]], {}, "failed", 0),
    ("unhashable_type", [dict(type=[])], {}, "failed", 0),
    ("timedout_exit", BASE, dict(status="timed_out", exit_code=-15), "timed_out", -15),
]


def main():
    failures = 0
    for name, events, changes, status, exit_code in CASES:
        fields = dict(
            status="completed",
            exit_code=0,
            stdout="\n".join(json.dumps(x) for x in events).encode(),
            stderr=b"",
            duration_seconds=0.1,
            truncated=False,
            tree_cleanup_confirmed=True,
            error=None,
        )
        fields.update(changes)
        try:
            result = HermesAdapter().parse_result(ProcessResult(**fields), expected=EXPECTED)
            passed = result.status == status and result.exit_code == exit_code
            print(name, "PASS" if passed else "FAIL", result.status, result.exit_code)
        except Exception as error:
            passed = False
            print(name, "FAIL", type(error).__name__)
        failures += not passed
    return int(failures != 0)


if __name__ == "__main__":
    raise SystemExit(main())
