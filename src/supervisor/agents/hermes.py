"""Offline Hermes CLI adapter for the M2-B contract.

This adapter implements an offline NDJSON protocol parser for the Hermes
CLI's ``--format stream-json`` output. It is OFFLINE-ONLY: the public
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
import math

from supervisor.agents.base import AgentResult

# ----- Constants from the M2-B contract --------------------------------------

# Identity pattern: starts with letter/digit, then [A-Za-z0-9._-], max 64 chars
_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"

# Session id pattern: 1..128 chars from [A-Za-z0-9._-]
_SESSION_ID_PATTERN = r"^[A-Za-z0-9._-]{1,128}$"

# Provider + model locked for M2-B
_AUTHORIZED_PROVIDER = "minimax-cn"
_AUTHORIZED_MODEL = "MiniMax-M3"

# Allowed event types in the supported NDJSON subset
_ALLOWED_EVENT_TYPES = frozenset({"system", "text", "result"})

# Allowed system subtype (we only accept ``init``)
_ALLOWED_SYSTEM_SUBTYPES = frozenset({"init"})

# Worker-statuses that we preserve verbatim with the actual exit_code
_PRESERVED_WORKER_STATUSES = frozenset(
    {"timed_out", "cancelled", "output_limit", "environment_failure"}
)

# The ONLY status the Worker must report for a "completed" outcome
_SUCCESS_WORKER_STATUS = "completed"

# Maximum summary length (terminal ``text`` field); tested at boundary 4096/4097
MAX_SUMMARY_LENGTH = 4096

# Maximum combined stdout+stderr accepted by the parser
_MAX_OUTPUT_BYTES = 65536


# ----------------------------------------------------------------------------
# Primitive helpers
# ----------------------------------------------------------------------------


def _is_int(value):
    """True iff value is a real int (not bool, not float)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_finite_number(value):
    """True iff value is a real int or finite float (not bool)."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return False


def _safe_eq_set(value):
    """True iff value is hashable.

    Used to defensively test membership in our allow-list sets without
    raising ``TypeError`` for unhashable inputs (lists, dicts, sets).
    M2B-R1-errors.
    """
    try:
        hash(value)
        return True
    except TypeError:
        return False


def _validate_expected(expected):
    """Validate the trusted identity dict passed by the caller.

    Per M2-B contract:
      - task_id, run_id, attempt_id, role, provider, model must be present
        and non-empty strings
      - provider must be ``minimax-cn`` (literal)
      - model must equal ``MiniMax-M3``

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

    import re

    for field in ("task_id", "run_id", "attempt_id"):
        if not re.match(_ID_PATTERN, expected[field]):
            raise ValueError(f"expected[{field!r}] does not match identity pattern")

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


# ----------------------------------------------------------------------------
# HermesAdapter
# ----------------------------------------------------------------------------


class HermesAdapter:
    """Offline NDJSON protocol adapter for the Hermes CLI."""

    # ------------------------------------------------------------------
    # build_request: always disabled
    # ------------------------------------------------------------------

    def build_request(self, context, workspace):
        """Always raise ``RuntimeError`` with ``live_execution_disabled``."""
        raise RuntimeError(
            "live_execution_disabled: hermes adapter does not launch real "
            "processes; use parse_result with a pre-captured ProcessResult"
        )

    # ------------------------------------------------------------------
    # parse_result: process gate -> NDJSON parse -> AgentResult
    # ------------------------------------------------------------------

    def parse_result(
        self,
        process,
        *,
        expected,
    ):
        """Parse a frozen ``ProcessResult`` into an ``AgentResult``.

        M2B-R1-process: Worker-preserved statuses carry the actual exit
        code (not coerced to None); status != completed is failed; status
        completed with exit != 0 is failed; the parser cannot promote a
        failed process to completed via stdout.

        M2B-R1-json: parse_constant rejects NaN/Infinity; ``timestamp:null``
        and ``tokens:null`` are distinguished from missing-key and
        rejected; known token keys only.

        M2B-R1-order: the state machine requires init before text/result;
        result is the terminal event.

        M2B-R1-errors: malformed event types (unhashable) and validator
        exceptions are converted to fixed safe error tags; the Adapter
        never re-raises a raw exception to the caller.
        """
        # 1) Validate trusted identity
        _validate_expected(expected)

        # 2) Worker-preserved statuses: return with the actual exit_code.
        if process.status in _PRESERVED_WORKER_STATUSES:
            return AgentResult(
                status=process.status,
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
                error="worker preserved failure",
                model=expected["model"],
            )

        # 3a) Any non-completed status is a process-level failure.
        if process.status != _SUCCESS_WORKER_STATUS:
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
                error="process status not completed",
                model=expected["model"],
            )

        # 3b) status="completed": gate on actual exit_code
        if process.exit_code is None or not _is_int(process.exit_code):
            return self._make_failed(process, expected, "exit code missing or non-int")
        if process.exit_code != 0:
            return self._make_failed(process, expected, "process failed: non-zero exit")

        # 3c) stderr gate
        if process.stderr:
            return self._make_failed(process, expected, "stderr present")

        # 3d) Truncation + tree-cleanup gate
        if process.truncated:
            return self._make_failed(process, expected, "process was truncated")
        if process.tree_cleanup_confirmed is not True:
            return self._make_failed(process, expected, "process tree cleanup unconfirmed")

        # 3e) UTF-8 decode
        try:
            text = process.stdout.decode("utf-8")
        except UnicodeDecodeError:
            return self._make_failed(process, expected, "stdout not UTF-8")

        # 3f) Output-budget gate
        if len(process.stdout) > _MAX_OUTPUT_BYTES:
            return self._make_failed(process, expected, "stdout exceeds 64KiB")

        # 4) NDJSON line split
        session_id_init = None
        session_id_terminal = None
        seen_init = False
        seen_terminal = False
        terminal_summary = ""
        usage = None

        for raw_line in text.splitlines():
            if not raw_line.strip():
                continue

            # Strict JSON: parse_constant rejects NaN/Infinity.
            # object_pairs_hook rejects duplicate keys.
            try:
                obj = json.loads(
                    raw_line,
                    object_pairs_hook=_reject_duplicate_keys,
                    parse_constant=_reject_nonfinite_constant,
                )
            except (ValueError, DuplicateKeyError, RecursionError):
                return self._make_failed(process, expected, "invalid NDJSON line")

            # M2B-R1-errors: defensive shape checks. Never raise.
            if not isinstance(obj, dict):
                return self._make_failed(process, expected, "event not object")
            event_type = obj.get("type")
            if not _safe_eq_set(event_type) or event_type not in _ALLOWED_EVENT_TYPES:
                return self._make_failed(process, expected, "unsupported event type")

            # After terminal, no further events allowed.
            if seen_terminal:
                return self._make_failed(process, expected, "event after terminal result")

            # M2B-R1-order: text/result require seen_init.
            if event_type != "system" and not seen_init:
                return self._make_failed(process, expected, "non-init event before init")

            # Per-event validation; any unexpected exception is caught and
            # converted to a fixed safe error tag. System-level exceptions
            # (KeyboardInterrupt, SystemExit, GeneratorExit) propagate.
            try:
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
                    err, terminal_summary, usage = self._validate_result(obj)
                    if err is not None:
                        return self._make_failed(process, expected, err)
                    seen_terminal = True
                    session_id_terminal = obj.get("session_id")
                    if session_id_terminal != session_id_init:
                        return self._make_failed(process, expected, "terminal session id mismatch")
            except BaseException as exc:
                if isinstance(exc, (KeyboardInterrupt, SystemExit, GeneratorExit)):
                    raise
                return self._make_failed(process, expected, "protocol validation raised")

        # Missing terminal
        if not seen_terminal:
            return self._make_failed(process, expected, "missing terminal event")

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

    @staticmethod
    def _make_failed(process, expected, error):
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
    def _validate_init(obj):
        import re

        subtype = obj.get("subtype")
        if not _safe_eq_set(subtype) or subtype not in _ALLOWED_SYSTEM_SUBTYPES:
            return "unsupported system subtype"

        if obj.get("model") != _AUTHORIZED_MODEL:
            return "init model mismatch"

        sid = obj.get("session_id")
        if not isinstance(sid, str) or not sid:
            return "init session_id missing"
        if not re.match(_SESSION_ID_PATTERN, sid):
            return "init session_id pattern invalid"

        # Optional timestamp: distinguish missing (key absent) from null.
        if "timestamp" in obj:
            ts = obj["timestamp"]
            if ts is None:
                return "init timestamp null"
            if not _is_finite_number(ts):
                return "init timestamp invalid"
            if ts < 0:
                return "init timestamp negative"

        allowed = {"type", "subtype", "model", "session_id", "timestamp"}
        unknown = set(obj.keys()) - allowed
        if unknown:
            return "init unknown field"

        return None

    @staticmethod
    def _validate_text(obj):
        body = obj.get("text")
        if not isinstance(body, str):
            return "text body missing or non-string"

        if "timestamp" in obj:
            ts = obj["timestamp"]
            if ts is None:
                return "text timestamp null"
            if not _is_finite_number(ts):
                return "text timestamp invalid"
            if ts < 0:
                return "text timestamp negative"

        allowed = {"type", "text", "timestamp"}
        unknown = set(obj.keys()) - allowed
        if unknown:
            return "text unknown field"

        return None

    @staticmethod
    def _validate_result(obj):
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

        usage = None
        if "tokens" in obj:
            tokens = obj["tokens"]
            if tokens is None:
                return "tokens null", "", None
            if not isinstance(tokens, dict):
                return "tokens not object", "", None
            for key in ("input", "output"):
                if key not in tokens:
                    return "tokens missing required field", "", None
                v = tokens[key]
                if v is None:
                    return f"tokens {key} null", "", None
                if not _is_int(v) or v < 0:
                    return f"tokens {key} invalid", "", None
            for key in ("total", "cache_read", "cache_write"):
                if key in tokens:
                    v = tokens[key]
                    if v is None:
                        return f"tokens {key} null", "", None
                    if not _is_int(v) or v < 0:
                        return f"tokens {key} invalid", "", None
            allowed_token_keys = {"input", "output", "total", "cache_read", "cache_write"}
            unknown_tokens = set(tokens.keys()) - allowed_token_keys
            if unknown_tokens:
                return "tokens unknown field", "", None
            usage = {
                "input_tokens": tokens["input"],
                "output_tokens": tokens["output"],
            }

        if "duration_ms" in obj:
            dur = obj["duration_ms"]
            if dur is None:
                return "duration_ms null", "", None
            if not _is_finite_number(dur):
                return "duration_ms invalid", "", None
            if dur < 0:
                return "duration_ms negative", "", None

        if "timestamp" in obj:
            ts = obj["timestamp"]
            if ts is None:
                return "result timestamp null", "", None
            if not _is_finite_number(ts):
                return "result timestamp invalid", "", None
            if ts < 0:
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
    """``object_pairs_hook`` for ``json.loads`` that rejects duplicate keys."""
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise DuplicateKeyError(f"duplicate key {key!r}")
        obj[key] = value
    return obj


def _reject_nonfinite_constant(value):
    """``parse_constant`` hook for ``json.loads`` that rejects NaN/Infinity."""
    raise ValueError(f"non-canonical JSON constant {value!r}")
