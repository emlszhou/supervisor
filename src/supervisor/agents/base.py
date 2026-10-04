"""Agent result parsing and strict protocol validation."""

from __future__ import annotations

import json
import re
from typing import Any

_ALLOWED_ROLES = {
    "planner",
    "implementer",
    "reviewer",
    "repairer",
    "fallback_repairer",
    "final_verifier",
}
_ALLOWED_STATUSES = {
    "completed",
    "failed",
    "timed_out",
    "cancelled",
    "output_limit",
    "environment_failure",
}
_ALLOWED_IDENTITY_KEYS = {
    "schema_version",
    "task_id",
    "run_id",
    "attempt_id",
    "role",
    "provider",
}
_ALLOWED_TOP_LEVEL_KEYS = {
    "schema_version",
    "task_id",
    "run_id",
    "attempt_id",
    "role",
    "provider",
    "model",
    "session_id",
    "status",
    "exit_code",
    "summary",
    "error",
    "usage",
    "artifacts",
    "truncated",
}
_ALLOWED_USAGE_KEYS = {"input_tokens", "output_tokens"}
_ALLOWED_ARTIFACT_KEYS = {"path", "sha256"}
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_ARTIFACT_PATH_PATTERN = re.compile(r"^[A-Za-z0-9_./-]+$")


def _make_failed(
    process,
    expected: dict[str, str],
    error: str,
) -> AgentResult:
    """Construct a failed AgentResult with safe metadata (no raw value echo)."""
    return AgentResult(
        status="failed",
        exit_code=process.exit_code,
        duration_seconds=process.duration_seconds,
        task_id=expected["task_id"],
        run_id=expected["run_id"],
        attempt_id=expected["attempt_id"],
        role=expected["role"],
        provider=expected["provider"],
        session_id=None,
        truncated=process.truncated,
        usage=None,
        error=error,
    )


def _check_id(value: Any, name: str) -> bool:
    """Check that value is a valid identifier string."""
    return isinstance(value, str) and bool(_ID_PATTERN.match(value))


def parse_agent_result(process, *, expected: dict[str, str]) -> AgentResult:
    """Parse process output into AgentResult.

    Args:
        process: ProcessResult object
        expected: dict with task_id, run_id, attempt_id, role, provider

    Returns:
        AgentResult object satisfying agent-result schema v1.
    """
    # Validate expected has required fields and types
    for field in ("task_id", "run_id", "attempt_id", "role", "provider"):
        if field not in expected:
            raise ValueError(f"expected must contain {field}")
        if not isinstance(expected[field], str):
            raise ValueError(f"expected.{field} must be string")

    # Gate on actual process status. Real exit_code != 0 -> failed (preserve).
        # Even with exit_code 0, if status is not "completed" (e.g. output_limit,
        # truncated, timeout, failed), return failed to override bogus output.
        # Non-completed status with exit_code=0 is a "process failed" state per protocol:
        #   timeout, cancelled, output_limit, environment_failure all require exit_code != 0.
        # Only "completed" status with exit_code=0 is the legitimate success.
        if process.exit_code != 0:
            return AgentResult(
                status=process.status if process.status != "completed" else "failed",
                exit_code=process.exit_code,
                duration_seconds=process.duration_seconds,
                task_id=expected["task_id"],
                run_id=expected["run_id"],
                attempt_id=expected["attempt_id"],
                role=expected["role"],
                provider=expected["provider"],
                session_id=None,
                truncated=process.truncated,
                usage=None,
                error=f"process failed: status={process.status} exit_code={process.exit_code}",
            )

            # exit_code=0 but non-completed status: process is a "failed" state (timeout/cancelled/output_limit).
            # Do not interpret as completed.
            if process.status not in ("completed",):
                return AgentResult(
                    status="failed",
                    exit_code=process.exit_code,
                    duration_seconds=process.duration_seconds,
                    task_id=expected["task_id"],
                    run_id=expected["run_id"],
                    attempt_id=expected["attempt_id"],
                    role=expected["role"],
                    provider=expected["provider"],
                    session_id=None,
                    truncated=process.truncated,
                    usage=None,
                    error=f"non-completed process status: status={process.status} exit_code={process.exit_code}",
                )

    # Process completed - now parse protocol
    try:
        raw = process.stdout.decode("utf-8").strip()
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _make_failed(process, expected, "invalid JSON")

    if not isinstance(data, dict):
        return _make_failed(process, expected, "JSON root must be object")

    # Reject unknown top-level fields
    unknown = set(data.keys()) - _ALLOWED_TOP_LEVEL_KEYS
    if unknown:
        return _make_failed(process, expected, "unknown top-level field")

    # Check required fields present
    for field in (
        "schema_version",
        "task_id",
        "run_id",
        "attempt_id",
        "role",
        "provider",
        "model",
        "session_id",
        "status",
        "exit_code",
        "summary",
        "error",
        "usage",
        "artifacts",
        "truncated",
    ):
        if field not in data:
            return _make_failed(process, expected, "missing required field")

    # Validate schema_version
    if data["schema_version"] != 1:
        return _make_failed(process, expected, "unsupported schema_version")

    # Validate types of every required field
    if not isinstance(data["task_id"], str):
        return _make_failed(process, expected, "task_id type invalid")
    if not isinstance(data["run_id"], str):
        return _make_failed(process, expected, "run_id type invalid")
    if not isinstance(data["attempt_id"], str):
        return _make_failed(process, expected, "attempt_id type invalid")
    if not isinstance(data["role"], str):
        return _make_failed(process, expected, "role type invalid")
    if data["role"] not in _ALLOWED_ROLES:
        return _make_failed(process, expected, "role enum invalid")
    if not isinstance(data["provider"], str) or not data["provider"]:
        return _make_failed(process, expected, "provider type invalid")
    if not (data["model"] is None or isinstance(data["model"], str)):
        return _make_failed(process, expected, "model type invalid")
    if data["model"] is not None and not data["model"]:
        return _make_failed(process, expected, "model type invalid")
    if not (data["session_id"] is None or isinstance(data["session_id"], str)):
        return _make_failed(process, expected, "session_id type invalid")
    if not isinstance(data["status"], str):
        return _make_failed(process, expected, "status type invalid")
    if data["status"] not in _ALLOWED_STATUSES:
        return _make_failed(process, expected, "status enum invalid")
    if not (data["exit_code"] is None or isinstance(data["exit_code"], int)):
        return _make_failed(process, expected, "exit_code type invalid")
    if not isinstance(data["summary"], str):
        return _make_failed(process, expected, "summary type invalid")
    if len(data["summary"]) > 4096:
        return _make_failed(process, expected, "summary too long")
    if not (data["error"] is None or isinstance(data["error"], str)):
        return _make_failed(process, expected, "error type invalid")
    if data["error"] is not None and not data["error"]:
        return _make_failed(process, expected, "error empty")
    if not isinstance(data["truncated"], bool):
        return _make_failed(process, expected, "truncated type invalid")

    # Validate identity pattern
    if not _check_id(data["task_id"], "task_id"):
        return _make_failed(process, expected, "task_id pattern invalid")
    if not _check_id(data["run_id"], "run_id"):
        return _make_failed(process, expected, "run_id pattern invalid")
    if not _check_id(data["attempt_id"], "attempt_id"):
        return _make_failed(process, expected, "attempt_id pattern invalid")

    # Bind identity to expected (strict equality; output cannot override)
    if data["task_id"] != expected["task_id"]:
        return _make_failed(process, expected, "task_id mismatch")
    if data["run_id"] != expected["run_id"]:
        return _make_failed(process, expected, "run_id mismatch")
    if data["attempt_id"] != expected["attempt_id"]:
        return _make_failed(process, expected, "attempt_id mismatch")
    if data["role"] != expected["role"]:
        return _make_failed(process, expected, "role mismatch")
    if data["provider"] != expected["provider"]:
        return _make_failed(process, expected, "provider mismatch")

    # Gate on declared status - if declared != completed, that is a fail.
    # And if declared completed but actual exit_code != 0 OR truncated is true,
    # we already gated above; double-check exit_code/exit declared consistency.
    if data["exit_code"] != 0:
        return _make_failed(process, expected, "declared exit_code != 0")

    # If declared completed but process actually truncated, fail.
    if data["status"] == "completed" and process.truncated:
        return _make_failed(process, expected, "process was truncated")

    # Declared truncated=True cannot claim completed (per protocol).
    if data["status"] == "completed" and data["truncated"]:
        return _make_failed(process, expected, "truncated cannot be true when completed")

    # session_id required for completed
    if data["status"] == "completed":
        if not isinstance(data["session_id"], str) or not data["session_id"]:
            return _make_failed(process, expected, "session_id required")
        # error must be null when status is completed
        if data["error"] is not None:
            return _make_failed(process, expected, "error must be null when completed")

    # Non-completed status must have non-empty error
    if data["status"] != "completed":
        if not (isinstance(data["error"], str) and data["error"]):
            return _make_failed(process, expected, "error required when not completed")

    # Validate usage
    if data["usage"] is not None:
        if not isinstance(data["usage"], dict):
            return _make_failed(process, expected, "usage type invalid")
        unknown_usage = set(data["usage"].keys()) - _ALLOWED_USAGE_KEYS
        if unknown_usage:
            return _make_failed(process, expected, "usage unknown field")
        if not _ALLOWED_USAGE_KEYS.issubset(data["usage"].keys()):
            return _make_failed(process, expected, "usage missing field")
        for key in _ALLOWED_USAGE_KEYS:
            v = data["usage"][key]
            if not (v is None or isinstance(v, int)):
                return _make_failed(process, expected, "usage field type invalid")
            if isinstance(v, int) and v < 0:
                return _make_failed(process, expected, "usage field negative")

    # Validate artifacts - strictly enforce canonical paths and hash format
    if data["artifacts"] is not None:
        if not isinstance(data["artifacts"], list):
            return _make_failed(process, expected, "artifacts type invalid")
        for artifact in data["artifacts"]:
            if not isinstance(artifact, dict):
                return _make_failed(process, expected, "artifact type invalid")
            unknown_art = set(artifact.keys()) - _ALLOWED_ARTIFACT_KEYS
            if unknown_art:
                return _make_failed(process, expected, "artifact unknown field")
            if not _ALLOWED_ARTIFACT_KEYS.issubset(artifact.keys()):
                return _make_failed(process, expected, "artifact missing field")
            path = artifact["path"]
            sha = artifact["sha256"]
            if not isinstance(path, str):
                return _make_failed(process, expected, "artifact path type invalid")
            if not isinstance(sha, str):
                return _make_failed(process, expected, "artifact sha type invalid")
            # Path must be non-empty, canonical, no absolute, no parent refs,
            # no dot components, no double slashes, no backslashes.
            if not path or path != path.strip():
                return _make_failed(process, expected, "artifact path invalid")
            if path.startswith("/") or "\\" in path:
                return _make_failed(process, expected, "artifact path invalid")
            if path == "..":
                return _make_failed(process, expected, "artifact path invalid")
            # Split into components and check each
            if "//" in path:
                return _make_failed(process, expected, "artifact path invalid")
            parts = path.split("/")
            for part in parts:
                if not part or part in (".", ".."):
                    return _make_failed(process, expected, "artifact path invalid")
                if not _ARTIFACT_PATH_PATTERN.match(part):
                    return _make_failed(process, expected, "artifact path invalid")
            # Hash format check
            if not _SHA256_PATTERN.match(sha):
                return _make_failed(process, expected, "artifact sha format invalid")

    # Now: if status is failed/timed_out/cancelled/output_limit/environment_failure,
    # the output itself is asserting a failure but the process succeeded; this is
    # actually an unusual case (process exit 0 but declared non-completed).
    # Per spec: stdout cannot override process failure. So declared non-completed
    # status with exit 0 is acceptable; we keep the declared status and set exit_code.
    if data["status"] != "completed":
        return AgentResult(
            status=data["status"],
            exit_code=0,
            duration_seconds=process.duration_seconds,
            task_id=expected["task_id"],
            run_id=expected["run_id"],
            attempt_id=expected["attempt_id"],
            role=expected["role"],
            provider=expected["provider"],
            session_id=None,
            truncated=process.truncated,
            usage=data["usage"],
            error=data["error"],
        )

    # Return successful result - preserve declared fields, do not invent new ones
    return AgentResult(
        status="completed",
        exit_code=0,
        duration_seconds=process.duration_seconds,
        task_id=expected["task_id"],
        run_id=expected["run_id"],
        attempt_id=expected["attempt_id"],
        role=expected["role"],
        provider=expected["provider"],
        session_id=data["session_id"],
        truncated=False,
        usage=data["usage"],
        error=None,
    )


class AgentResult:
    """Unified agent result structure."""

    def __init__(
        self,
        status: str,
        exit_code: int | None,
        duration_seconds: float,
        task_id: str,
        run_id: str,
        attempt_id: str,
        role: str,
        provider: str,
        session_id: str | None,
        truncated: bool,
        usage: dict | None,
        error: str | None,
    ):
        self.status = status
        self.exit_code = exit_code
        self.duration_seconds = duration_seconds
        self.task_id = task_id
        self.run_id = run_id
        self.attempt_id = attempt_id
        self.role = role
        self.provider = provider
        self.session_id = session_id
        self.truncated = truncated
        self.usage = usage
        self.error = error

    def to_dict(self) -> dict:
        """Convert to dict for serialization."""
        return {
            "schema_version": 1,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "attempt_id": self.attempt_id,
            "role": self.role,
            "provider": self.provider,
            "model": None,
            "session_id": self.session_id,
            "status": self.status,
            "exit_code": self.exit_code,
            "summary": "",
            "error": self.error,
            "usage": self.usage,
            "artifacts": [],
            "truncated": self.truncated,
        }
