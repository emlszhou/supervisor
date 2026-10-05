"""Protected structural gate for M2-A evidence; does not prove runtime truth."""

import argparse
import datetime
import json
import re
from pathlib import Path

IDS = {
    "cli_help",
    "noninteractive",
    "model_route",
    "fresh_session",
    "output_protocol",
    "endpoint_failure",
    "timeout",
    "cancellation",
    "permissions",
}
CHECK_FIELDS = {
    "id",
    "declared",
    "observed",
    "enforced",
    "status",
    "reason",
    "argv",
    "cwd",
    "started_utc",
    "ended_utc",
    "exit_code",
    "output_sha256",
    "session_id",
    "session_id_source",
}


def validate(report: object, baseline: str) -> None:
    fields = {
        "schema_version",
        "task_id",
        "run_id",
        "attempt_id",
        "baseline_commit",
        "host",
        "agent",
        "route",
        "checks",
        "adapter_readiness",
        "limitations",
    }
    if not isinstance(report, dict) or set(report) != fields:
        raise ValueError("invalid capability report fields")
    if type(report["schema_version"]) is not int or report["schema_version"] != 1:
        raise ValueError("schema_version must be integer 1")
    if report["task_id"] != "M2A-hermes-capabilities" or report["baseline_commit"] != baseline:
        raise ValueError("task/baseline binding mismatch")
    if not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", baseline):
        raise ValueError("baseline must be a full SHA")
    for key in ("run_id", "attempt_id"):
        if not isinstance(report[key], str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", report[key]
        ):
            raise ValueError("invalid run/attempt identity")
    for key, required in (
        ("host", {"os", "architecture"}),
        ("agent", {"binary", "version"}),
        ("route", {"provider", "model", "inference_location"}),
    ):
        value = report[key]
        if not isinstance(value, dict) or set(value) != required:
            raise ValueError(f"invalid {key}")
        if not all(isinstance(v, str) and v for v in value.values()):
            raise ValueError(f"{key} values must be nonempty strings")
    if report["route"]["inference_location"] not in ("local", "cloud", "unknown"):
        raise ValueError("invalid inference location")
    checks = report["checks"]
    if not isinstance(checks, list) or len(checks) != len(IDS):
        raise ValueError("nine checks required")
    seen = set()
    for check in checks:
        if not isinstance(check, dict) or set(check) != CHECK_FIELDS:
            raise ValueError("invalid check fields")
        if not isinstance(check["id"], str) or check["id"] not in IDS or check["id"] in seen:
            raise ValueError("unknown/duplicate check ID")
        seen.add(check["id"])
        for key in ("declared", "observed", "enforced"):
            if check[key] not in ("yes", "no", "unknown"):
                raise ValueError("invalid capability tri-state")
        if check["status"] not in ("passed", "failed", "unsupported", "not_run"):
            raise ValueError("invalid check status")
        if not isinstance(check["reason"], str) or not check["reason"]:
            raise ValueError("evidence explanation required")
        if check["status"] in ("not_run", "unsupported"):
            if any(
                check[k] is not None
                for k in (
                    "argv",
                    "cwd",
                    "started_utc",
                    "ended_utc",
                    "exit_code",
                    "output_sha256",
                    "session_id",
                    "session_id_source",
                )
            ):
                raise ValueError("unexecuted checks cannot claim execution evidence")
            if check["observed"] != "unknown" or check["enforced"] != "unknown":
                raise ValueError("unexecuted capability must be unknown")
            continue
        if (
            not isinstance(check["argv"], list)
            or not check["argv"]
            or not all(isinstance(a, str) and a for a in check["argv"])
            or not isinstance(check["cwd"], str)
            or not check["cwd"]
            or type(check["exit_code"]) is not int
        ):
            raise ValueError("executed check requires actual argv/cwd/exit")
        if not isinstance(check["output_sha256"], str) or not re.fullmatch(
            r"[a-f0-9]{64}", check["output_sha256"]
        ):
            raise ValueError("executed output needs SHA256")
        times = []
        for key in ("started_utc", "ended_utc"):
            value = check[key]
            if not isinstance(value, str):
                raise ValueError("actual UTC timestamp required")
            timestamp = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
            if timestamp.utcoffset() != datetime.timedelta(0):
                raise ValueError("timestamps must be UTC")
            times.append(timestamp)
        if not 0 <= (times[1] - times[0]).total_seconds() <= 120:
            raise ValueError("invalid check duration")
        for key in ("session_id", "session_id_source"):
            if check[key] is not None and (not isinstance(check[key], str) or not check[key]):
                raise ValueError("invalid session identity/source")
        if (check["session_id"] is None) != (check["session_id_source"] is None):
            raise ValueError("session identity and source must be paired")
        if (
            check["id"] == "fresh_session"
            and check["status"] == "passed"
            and check["session_id"] is None
        ):
            raise ValueError("fresh check requires real session evidence")
    if report["adapter_readiness"] not in ("ready", "blocked"):
        raise ValueError("invalid readiness")
    if report["adapter_readiness"] == "ready" and any(
        (c["status"] != "passed" or c["observed"] != "yes")
        for c in checks
        if c["id"] != "permissions"
    ):
        raise ValueError("required smoke gates incomplete")
    if report["adapter_readiness"] == "ready" and (
        report["route"]["inference_location"] == "unknown"
        or any(v == "unknown" for v in report["route"].values())
        or report["agent"]["version"] == "unknown"
    ):
        raise ValueError("ready requires verified version/model/route")
    if not isinstance(report["limitations"], list) or not all(
        isinstance(s, str) and s for s in report["limitations"]
    ):
        raise ValueError("limitations must be strings")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--baseline", required=True)
    args = parser.parse_args()
    report = json.loads((args.repo / "deliveries/M2A/capabilities.json").read_text())
    validate(report, args.baseline)
    if not (args.repo / "deliveries/M2A/hermes-report.md").is_file():
        raise ValueError("missing delivery report")
    print("Capability evidence structure validated; actual runtime behavior requires fresh review.")


if __name__ == "__main__":
    main()
