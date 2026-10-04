"""Agent result parsing and validation."""

from __future__ import annotations

import json


def parse_agent_result(process, *, expected: dict[str, str]) -> AgentResult:
    """Parse process output into AgentResult.

    Args:
        process: ProcessResult object
        expected: dict with task_id, run_id, attempt_id, role, provider

    Returns:
        AgentResult object
    """
    # Validate expected has required fields
    for field in ["task_id", "run_id", "attempt_id", "role", "provider"]:
        if field not in expected:
            raise ValueError(f"expected must contain {field}")

    # If process didn't complete successfully, map status directly
    if process.status != "completed":
        return AgentResult(
            status=process.status,
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
            error=f"process status: {process.status}",
        )

    # Process completed successfully - try to parse JSON
    try:
        raw = process.stdout.decode("utf-8").strip()
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
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
            error=f"invalid JSON: {str(e)}",
        )

    # Validate JSON structure
    if not isinstance(data, dict):
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
            error="JSON root must be object",
        )

    # Check for required fields
    required = ["schema_version", "status", "exit_code", "session_id", "truncated"]
    for field in required:
        if field not in data:
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
                error=f"missing required field: {field}",
            )

    # Validate schema version
    if data["schema_version"] != 1:
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
            error=f"unsupported schema_version: {data['schema_version']}",
        )

    # Validate exit_code matches
    if data["exit_code"] != 0:
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
            error="exit_code in output is not 0",
        )

    # Validate truncated
    if data["truncated"]:
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
            error="output reports truncated",
        )

    # Validate identity fields
    if "task_id" in data and data["task_id"] != expected["task_id"]:
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
            error="task_id mismatch",
        )
    if "run_id" in data and data["run_id"] != expected["run_id"]:
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
            error="run_id mismatch",
        )
    if "attempt_id" in data and data["attempt_id"] != expected["attempt_id"]:
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
            error="attempt_id mismatch",
        )
    if "role" in data and data["role"] != expected["role"]:
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
            error="role mismatch",
        )
    if "provider" in data and data["provider"] != expected["provider"]:
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
            error="provider mismatch",
        )

    # Validate session_id must be non-null string for completed
    if not isinstance(data.get("session_id"), str) or not data.get("session_id"):
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
            error="session_id must be non-empty string",
        )

    # Validate no permission_override field
    if "permission_override" in data:
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
            error="permission_override not allowed",
        )

    # Validate usage if present
    if "usage" in data and data["usage"] is not None:
        usage = data["usage"]
        if not isinstance(usage, dict):
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
                error="usage must be object or null",
            )
        for key in ["input_tokens", "output_tokens"]:
            if key in usage:
                if not isinstance(usage[key], int) or usage[key] < 0:
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
                        error=f"usage.{key} must be non-negative integer",
                    )

    # Validate artifacts if present
    if "artifacts" in data and data["artifacts"] is not None:
        artifacts = data["artifacts"]
        if not isinstance(artifacts, list):
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
                error="artifacts must be array or null",
            )
        import re

        for artifact in artifacts:
            if not isinstance(artifact, dict):
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
                    error="each artifact must be object",
                )
            path = artifact.get("path", "")
            # Reject absolute paths, ../ escape, and non-alphanumeric chars
            if not re.match(r"^[A-Za-z0-9./_-]+$", path):
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
                    error=f"invalid artifact path: {path}",
                )
            if path.startswith("/") or "../" in path:
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
                    error=f"artifact path escape: {path}",
                )

    # Return successful result
    return AgentResult(
        status="completed",
        exit_code=0,
        duration_seconds=process.duration_seconds,
        task_id=expected["task_id"],
        run_id=expected["run_id"],
        attempt_id=expected["attempt_id"],
        role=expected["role"],
        provider=expected["provider"],
        session_id=data.get("session_id"),
        truncated=False,
        usage=data.get("usage"),
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
        result = {
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
        return result
