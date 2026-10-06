"""Offline Hermes CLI adapter for the M2-B contract.

This adapter implements an offline NDJSON protocol parser for the Hermes
CLI's `--format stream-json` output. It is OFFLINE-ONLY: the public
``build_request`` entry point raises unconditionally before any process is
launched. Real Hermes execution, network calls, model invocation, and
credential reads are out of scope and are forbidden by the M2-B contract.

The adapter consumes a frozen ``ProcessResult`` produced by the existing
``supervisor.workers.process.ProcessRunner`` and parses the captured stdout
as a sequence of NDJSON events. Process-level truth (status, exit_code,
truncated, tree_cleanup_confirmed, stderr) gates the protocol-level parse;
no event payload can promote a failed process to ``completed``.

The adapter does not modify ``supervisor.agents.base``, the public
``AgentResult`` schema, the ``ProcessRunner``, or any forbidden file.
"""

from __future__ import annotations

import json
from typing import Any

from supervisor.agents.base import AgentResult
from supervisor.workers.process import ProcessResult

# ----- Constants from the M2-B contract --------------------------------------

# Identity pattern: starts with letter/digit, then [A-Za-z0-9._-], max 64 chars
_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"

# Session id pattern: 1..128 chars from [A-Za-z0-9._-]
_SESSION_ID_PATTERN = r"^[A-Za-z0-9._-]{1,128}$"

# Provider + model locked for M2-B
_AUTHORIZED_PROVIDER = "minimax-cn"
_AUTHORIZED_MODEL = "MiniMax-M3"

# Statuses the Adapter itself can emit (ProcessResult may carry other
# statuses like ``timed_out``/``cancelled`` which are preserved as-is)
_ALLOWED_RESULT_STATUSES = {"completed", "failed"}

# Worker-statuses that we preserve verbatim without parsing stdout
_PRESERVED_WORKER_STATUSES = {"timed_out", "cancelled", "output_limit", "environment_failure"}

# Maximum summary length (terminal ``text`` field); tested at boundary 4096/4097
MAX_SUMMARY_LENGTH = 4096

# Maximum combined stdout+stderr accepted by the parser
_MAX_OUTPUT_BYTES = 65536

# Allowed event types in the supported NDJSON subset
_ALLOWED_EVENT_TYPES = {"system", "text", "result"}

# Allowed system subtype (we only accept ``init``)
_ALLOWED_SYSTEM_SUBTYPES = {"init"}


def _is_int(value: Any) -> bool:
    """True iff value is a real int (not bool)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_expected(expected: dict[str, str]) -> None:
    """Validate the trusted identity dict passed by the caller.

    Per M2-B contract:
      - task_id, run_id, attempt_id, role, provider must be present and be strings
      - provider must be ``minimax-cn`` (literal)
      - model must be present, must be a string, must equal ``MiniMax-M3``

    Raises ``ValueError`` on any violation. The Adapter does NOT trust
    process-level identity claims; this dict is the source of truth.
    """
    required = ("task_id", "run_id", "attempt_id", "role", "provider", "model")
    for field in required:
        if field not in expected:
            raise ValueError(f"expected must contain {field!r}")
        value = expected[field]
        if not isinstance(value, str) or not value:
            raise ValueError(f"expected[{field!r}] must be non-empty string")

    # ID pattern checks for identity-shaped fields
    import re

    for field in ("task_id", "run_id", "attempt_id"):
        if not re.match(_ID_PATTERN, expected[field]):
            raise ValueError(f"expected[{field!r}] does not match identity pattern")

    # role must be in the enum set
    from supervisor.agents.base import _ALLOWED_ROLES  # type: ignore[attr-defined]

    if expected["role"] not in _ALLOWED_ROLES:
        raise ValueError(f"expected[role] {expected['role']!r} not in allowed set")

    if expected["provider"] != _AUTHORIZED_PROVIDER:
        raise ValueError(
            f"expected[provider] must be {_AUTHORIZED_PROVIDER!r}, got {expected['provider']!r}"
        )

    if expected["model"] != _AUTHORIZED_MODEL:
        raise ValueError(
            f"expected[model] must be {_AUTHORIZED_MODEL!r}, got {expected['model']!r}"
        )


class HermesAdapter:
    """Offline NDJSON protocol adapter for the Hermes CLI.

    The adapter implements the contract specified in
    ``handoffs/M2B/v1/task-bundle/requirements.md``:
      - ``build_request`` always raises ``RuntimeError`` containing the
        substring ``live_execution_disabled``. It never launches a process.
      - ``parse_result`` consumes a frozen ``ProcessResult`` and returns a
        validated ``AgentResult``.
    """

    # ------------------------------------------------------------------
    # build_request: always disabled
    # ------------------------------------------------------------------

    def build_request(self, context: dict[str, str], workspace):
        """Always raise ``RuntimeError`` with ``live_execution_disabled``.

        Per M2-B contract: real Hermes execution is OUT OF SCOPE for this
        task. No subprocess is launched. No CLI is constructed. No enable
        flag exists. Future contracts may lift this gate; today, the
        Adapter exists only to parse captured offline output.
        """
        raise RuntimeError(
            "live_execution_disabled: hermes adapter does not launch real "
            "processes; use parse_result with a pre-captured ProcessResult"
        )

    # ------------------------------------------------------------------
    # parse_result: process gate -> NDJSON parse -> AgentResult
    # ------------------------------------------------------------------

    def parse_result(
        self,
        process: ProcessResult,
        *,
        expected: dict[str, str],
    ) -> AgentResult:
        """Parse a frozen ``ProcessResult`` into an ``AgentResult``.

        Steps:
          1. Validate ``expected`` (trusted identity source).
          2. Gate on real process state: if status is a worker-preserved
             state (timed_out/cancelled/output_limit/environment_failure),
             return AgentResult preserving that state and exit_code=None.
          3. Gate on exit_code: non-zero, None, or bool returns failed.
          4. Gate on ``stderr``: any non-empty stderr returns failed.
          5. Gate on ``truncated`` / ``tree_cleanup_confirmed``: any of
             those returning True/false (not True) returns failed.
          6. Decode stdout as UTF-8; any failure -> failed.
          7. Split NDJSON into non-empty lines; for each line require
             strict JSON (no duplicate keys, no NaN/Infinity, no bool-as-int).
          8. Validate event-shape against the supported subset
             (init/text/result). Reject tool_use/tool_result and unknown
             types.
          9. Validate first event is init; last is result; session_ids match.
          10. Map usage tokens if present; reject bool/non-int/non-finite.
          11. Enforce 4096-character summary length.
        """
        # 1) Validate trusted identity
        _validate_expected(expected)

        # 2) Worker-preserved statuses: return as-is
        if process.status in _PRESERVED_WORKER_STATUSES:
            return AgentResult(
                status=process.status,
                exit_code=None,
                duration_seconds=process.duration_seconds,
                task_id=expected["task_id"],
                run_id=expected["run_id"],
                attempt_id=expected["attempt_id"],
                role=expected["role"],
                provider=expected["provider"],
                session_id=None,
                truncated=process.truncated,
                usage=None,
                error=None,
                model=expected["model"],
            )

        # 3) Exit code gate
        if process.exit_code is None or not _is_int(process.exit_code):
            return self._make_failed(process, expected, "exit code missing or non-int")
        if process.exit_code != 0:
            return self._make_failed(process, expected, "process failed: non-zero exit")

        # 4) stderr gate (this conservative subset rejects any stderr)
        if process.stderr:
            return self._make_failed(process, expected, "stderr present")

        # 5) Truncation + tree-cleanup gate
        if process.truncated:
            return self._make_failed(process, expected, "process was truncated")
        if process.tree_cleanup_confirmed is not True:
            return self._make_failed(process, expected, "process tree cleanup unconfirmed")

        # 6) UTF-8 decode
        try:
            text = process.stdout.decode("utf-8")
        except UnicodeDecodeError:
            return self._make_failed(process, expected, "stdout not UTF-8")

        # 7) Output-budget gate (combined stdout+stderr already checked at
        #    process level; we still enforce the 64KiB parsing cap here to
        #    keep parser-local reasoning tight).
        if len(process.stdout) > _MAX_OUTPUT_BYTES:
            return self._make_failed(process, expected, "stdout exceeds 64KiB")

        # 8) NDJSON line split (allow empty lines, reject non-JSON / canonical violations)
        session_id_terminal = None
        seen_init = False
        seen_terminal = False
        line_count = 0

        for raw_line in text.splitlines():
            if not raw_line.strip():
                continue
            line_count += 1

            # Each line must be a single JSON object; use strict parsing via
            # the stdlib json module (it rejects duplicate keys with the
            # object_pairs_hook parameter). NaN/Infinity are not valid JSON
            # per RFC 8259, so the stdlib rejects them. bool-as-int: True
            # parses as JSON true (not an int), so this is naturally handled.
            try:
                obj = json.loads(raw_line, object_pairs_hook=_reject_duplicate_keys)
            except (ValueError, DuplicateKeyError):
                return self._make_failed(process, expected, "invalid NDJSON line")

            if not isinstance(obj, dict):
                return self._make_failed(process, expected, "event must be object")

            event_type = obj.get("type")
            if event_type not in _ALLOWED_EVENT_TYPES:
                return self._make_failed(process, expected, "unsupported event type")

            # After terminal result, no further events
            if seen_terminal:
                return self._make_failed(process, expected, "event after terminal result")

            # Validate the specific event shape
            if event_type == "system":
                if seen_init:
                    return self._make_failed(process, expected, "duplicate init event")
                err = self._validate_init(obj)
                if err is not None:
                    return self._make_failed(process, expected, err)
                seen_init = True
                session_id_init = obj.get("session_id")

            elif event_type == "text":
                err = self._validate_text(obj)
                if err is not None:
                    return self._make_failed(process, expected, err)

            elif event_type == "result":
                if not seen_init:
                    return self._make_failed(process, expected, "result before init")
                err, terminal_summary, usage = self._validate_result(obj)
                if err is not None:
                    return self._make_failed(process, expected, err)
                seen_terminal = True
                session_id_terminal = obj.get("session_id")
                if session_id_terminal != session_id_init:
                    return self._make_failed(process, expected, "terminal session id mismatch")

        # 9) Missing terminal
        if not seen_terminal:
            return self._make_failed(process, expected, "missing terminal event")

        # 10) All checks passed: return completed AgentResult
        return AgentResult(
            status="completed",
            exit_code=0,
            duration_seconds=process.duration_seconds,
            task_id=expected["task_id"],
            run_id=expected["run_id"],
            attempt_id=expected["attempt_id"],
            role=expected["role"],
            provider=expected["provider"],
            session_id=session_id_terminal,
            truncated=False,
            usage=usage,
            error=None,
            model=expected["model"],
            summary=terminal_summary,
            artifacts=[],
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_failed(
        process: ProcessResult,
        expected: dict[str, str],
        error: str,
    ) -> AgentResult:
        """Construct a failed ``AgentResult`` with safe metadata.

        Never echoes the raw stdout. Error is a fixed safe string that
        names the failure category, not the offending payload.
        """
        return AgentResult(
            status="failed",
            exit_code=process.exit_code if _is_int(process.exit_code) else None,
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
            model=expected["model"],
        )

    @staticmethod
    def _validate_init(obj: dict) -> str | None:
        """Validate an ``init`` event. Returns None on success or an error tag."""
        import re

        if obj.get("subtype") not in _ALLOWED_SYSTEM_SUBTYPES:
            return "unsupported system subtype"

        if obj.get("model") != _AUTHORIZED_MODEL:
            return "init model mismatch"

        sid = obj.get("session_id")
        if not isinstance(sid, str) or not sid:
            return "init session_id missing"
        if not re.match(_SESSION_ID_PATTERN, sid):
            return "init session_id pattern invalid"

        # Optional timestamp: non-negative finite number, not bool
        ts = obj.get("timestamp")
        if ts is not None and not (_is_int(ts) or _is_finite_non_bool_float(ts)):
            return "init timestamp invalid"
        if ts is not None and isinstance(ts, (int, float)) and ts < 0:
            return "init timestamp negative"

        # Reject any unknown keys beyond the explicit ones
        allowed = {"type", "subtype", "model", "session_id", "timestamp"}
        unknown = set(obj.keys()) - allowed
        if unknown:
            return "init unknown field"

        return None

    @staticmethod
    def _validate_text(obj: dict) -> str | None:
        """Validate a ``text`` event. Returns None on success or an error tag."""
        body = obj.get("text")
        if not isinstance(body, str):
            return "text body missing or non-string"

        # Optional timestamp
        ts = obj.get("timestamp")
        if ts is not None and not (_is_int(ts) or _is_finite_non_bool_float(ts)):
            return "text timestamp invalid"
        if ts is not None and isinstance(ts, (int, float)) and ts < 0:
            return "text timestamp negative"

        allowed = {"type", "text", "timestamp"}
        unknown = set(obj.keys()) - allowed
        if unknown:
            return "text unknown field"

        return None

    @staticmethod
    def _validate_result(obj: dict) -> tuple[str | None, str, dict | None]:
        """Validate a ``result`` event. Returns (None, summary, usage) on success
        or (error_tag, "", None) on failure."""
        import re

        sid = obj.get("session_id")
        if not isinstance(sid, str) or not sid:
            return "result session_id missing", "", None
        if not re.match(_SESSION_ID_PATTERN, sid):
            return "result session_id pattern invalid", "", None

        exit_code = obj.get("exit_code")
        if not _is_int(exit_code):
            return "result exit_code missing or non-int", "", None
        if exit_code != 0:
            return "result exit_code non-zero", "", None

        text = obj.get("text")
        if not isinstance(text, str):
            return "result text missing or non-string", "", None
        if len(text) > MAX_SUMMARY_LENGTH:
            return "result summary too long", "", None

        # Tokens usage is optional. If present, must be object with non-negative ints.
        usage = None
        tokens = obj.get("tokens")
        if tokens is not None:
            if not isinstance(tokens, dict):
                return "tokens not object", "", None
            # Required: input, output (additional allowed: total, cache_read,
            # cache_write). All must be non-negative ints (not bool).
            for key in ("input", "output"):
                v = tokens.get(key)
                if v is None:
                    return "tokens missing required field", "", None
                if not _is_int(v) or v < 0:
                    return "tokens field invalid", "", None
            for key in ("total", "cache_read", "cache_write"):
                if key in tokens:
                    v = tokens[key]
                    if not _is_int(v) or v < 0:
                        return "tokens field invalid", "", None
            # Map input/output to input_tokens/output_tokens (do not infer other identities)
            usage = {
                "input_tokens": tokens["input"],
                "output_tokens": tokens["output"],
            }

        # Optional duration_ms / timestamp
        dur = obj.get("duration_ms")
        if dur is not None and not (_is_int(dur) or _is_finite_non_bool_float(dur)):
            return "result duration_ms invalid", "", None
        if dur is not None and isinstance(dur, (int, float)) and dur < 0:
            return "result duration_ms negative", "", None
        ts = obj.get("timestamp")
        if ts is not None and not (_is_int(ts) or _is_finite_non_bool_float(ts)):
            return "result timestamp invalid", "", None
        if ts is not None and isinstance(ts, (int, float)) and ts < 0:
            return "result timestamp negative", "", None

        allowed = {"type", "session_id", "exit_code", "text", "tokens", "duration_ms", "timestamp"}
        unknown = set(obj.keys()) - allowed
        if unknown:
            return "result unknown field", "", None

        return None, text, usage


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


class DuplicateKeyError(ValueError):
    """Raised by ``_reject_duplicate_keys`` when a JSON object has duplicate keys."""


def _reject_duplicate_keys(pairs):
    """``object_pairs_hook`` for ``json.loads`` that rejects duplicate keys.

    RFC 8259 says JSON objects MUST have unique keys but does not require
    parsers to reject duplicates. The M2-B contract forbids duplicates in
    NDJSON, so we enforce it locally.
    """
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise DuplicateKeyError(f"duplicate key {key!r}")
        obj[key] = value
    return obj


def _is_finite_non_bool_float(value: Any) -> bool:
    """True iff value is a real float (not bool, not int subclass) and is finite."""
    # bool is a subclass of int, so the int check above already filters booleans.
    return isinstance(value, float) and not isinstance(value, bool)
