"""Seatbelt boundary backend: case classification, result summary, profile text.

Production module (standard library only). No I/O, no subprocess, no model calls.
``require_live_execution`` always refuses; live execution remains disabled.
"""

from __future__ import annotations

import posixpath

__all__ = [
    "classify_case",
    "build_profile",
    "require_live_execution",
    "summarize_results",
]

# Case field name -> allowed Python type(s). bool is rejected explicitly for
# integer fields because bool is a subclass of int in Python.
_INT = int
_BOOL = bool
_NONE = type(None)

_FIELDS: dict[str, tuple[type, ...]] = {
    "test_kind": (str,),
    "action_exit_code": (_INT, _NONE),
    "action_errno": (str, _NONE),
    "action_started": (_BOOL,),
    "action_completed": (_BOOL,),
    "effect_observed": (_BOOL,),
    "control_passed": (_BOOL,),
    "target_unchanged": (_BOOL, _NONE),
    "cleanup_confirmed": (_BOOL, _NONE),
    "output_limited": (_BOOL,),
    "observation_complete": (_BOOL,),
}

_KNOWN_KINDS = ("positive", "expected_refuse", "timeout_cleanup")
_REFUSE_ERRNOS = {"EPERM", "EACCES"}
_REQUIRED_GROUP_KEYS = ("T1", "T2", "T3", "T5", "T6")
_ALL_KEYS = _REQUIRED_GROUP_KEYS + ("T4", "T7")
_VERDICTS = ("pass", "fail", "unknown")


def _fixed(message: str) -> ValueError:
    return ValueError(message)


def _check_case_fields(case: dict) -> None:
    if not isinstance(case, dict):
        raise _fixed("invalid case: expected mapping")
    if set(case) != set(_FIELDS):
        raise _fixed("invalid case: fields do not match contract schema")
    for key, types in _FIELDS.items():
        value = case[key]
        if isinstance(value, bool) and bool not in types:
            raise _fixed(f"invalid case: boolean not accepted for {key}")
        if not isinstance(value, types):
            raise _fixed(f"invalid case: bad type for {key}")
    if case["test_kind"] not in _KNOWN_KINDS:
        raise _fixed("invalid case: unknown test_kind")
    if case["action_exit_code"] is not None and not isinstance(case["action_exit_code"], int):
        raise _fixed("invalid case: bad type for action_exit_code")


def _refuse_verdict(case: dict) -> str:
    if case["effect_observed"] or case["target_unchanged"] is False:
        return "fail"
    if (
        case["action_completed"]
        and case["action_exit_code"] is not None
        and case["action_exit_code"] != 0
        and case["action_errno"] in _REFUSE_ERRNOS
        and case["control_passed"]
        and case["target_unchanged"] is not False
        and case["action_started"]
        and case["observation_complete"]
        and not case["output_limited"]
    ):
        return "pass"
    return "unknown"


def classify_case(case: dict) -> str:
    """Classify one recorded sub-item as ``pass``/``fail``/``unknown``.

    ``expected_refuse``: any observed out-of-bounds effect or a changed target
    fails immediately, even with a non-zero exit.  A pass additionally needs a
    real permission errno, a successful same-action/same-target control under
    the allow profile, a started action, complete observation and no output
    truncation.  ``positive``: started + completed + exit 0 + no errno +
    observed effect passes.  ``timeout_cleanup``: actual negative-signal exit,
    watchdog-triggered control, confirmed cleanup and complete observation
    pass; unconfirmed cleanup is unknown; confirmed residue fails.
    """
    _check_case_fields(case)
    kind = case["test_kind"]
    if kind == "expected_refuse":
        return _refuse_verdict(case)
    if kind == "positive":
        if not (
            case["action_started"]
            and case["action_completed"]
            and case["action_exit_code"] == 0
            and case["action_errno"] is None
            and case["effect_observed"]
            and case["observation_complete"]
            and not case["output_limited"]
        ):
            return "fail"
        return "pass"
    # timeout_cleanup
    if case["cleanup_confirmed"] is False:
        return "fail"
    exit_code = case["action_exit_code"]
    timed_out = (
        case["control_passed"]
        and not case["action_completed"]
        and exit_code is not None
        and isinstance(exit_code, int)
        and exit_code < 0
    )
    if timed_out and case["cleanup_confirmed"] is True and case["observation_complete"]:
        return "pass"
    return "unknown"


def summarize_results(results: dict) -> str:
    """Map T1/T2/T3/T5/T6 lists + T4 + T7 onto fail/partial/full_pass.

    Any fail -> ``fail``; otherwise any unknown -> ``partial``; otherwise
    ``full_pass``.  T4 must be the fixed string ``out_of_scope`` and is never
    counted.  Missing, empty or extra keys and unexpected values raise
    ValueError with a fixed message that echoes no input.
    """
    if not isinstance(results, dict):
        raise _fixed("invalid results: expected mapping")
    if set(results) != set(_ALL_KEYS):
        raise _fixed("invalid results: keys do not match contract schema")
    verdicts: list[str] = []
    for key in _REQUIRED_GROUP_KEYS:
        group = results[key]
        if not isinstance(group, list) or not group:
            raise _fixed("invalid results: empty or non-list group")
        for item in group:
            if not isinstance(item, str) or item not in _VERDICTS:
                raise _fixed("invalid results: unexpected verdict value")
            verdicts.append(item)
    if results["T4"] != "out_of_scope":
        raise _fixed("invalid results: T4 must be out_of_scope")
    if results["T7"] not in _VERDICTS:
        raise _fixed("invalid results: unexpected verdict value")
    verdicts.append(results["T7"])
    if "fail" in verdicts:
        return "fail"
    if "unknown" in verdicts:
        return "partial"
    return "full_pass"


def require_live_execution(*args: object, **kwargs: object) -> None:  # pragma: no cover
    """Refuse every live execution request unconditionally."""
    raise RuntimeError("live_execution_disabled")


def _sbpl_escape(value: str) -> str:
    out = []
    for ch in value:
        if ch in '\\"':
            out.append("\\" + ch)
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        else:
            out.append(ch)
    return "".join(out)


def _sbpl_lit(absolute: str) -> str:
    return _sbpl_escape(absolute)


def _validated_dir(name: str, value: str) -> str:
    if not isinstance(value, str) or not value:
        raise _fixed(f"invalid profile: empty path for {name}")
    if any(ord(ch) < 0x20 or ch == "\x7f" for ch in value):
        raise _fixed(f"invalid profile: control character in path for {name}")
    if not value.startswith("/"):
        raise _fixed(f"invalid profile: non-absolute path for {name}")
    resolved = posixpath.normpath(value)
    if ".." in resolved.split("/"):
        raise _fixed(f"invalid profile: uncanonical path for {name}")
    if value != resolved:
        raise _fixed(f"invalid profile: uncanonical path for {name}")
    return resolved


def _validate_paths(
    work: str,
    ro: str,
    denied: str,
    secret: str,
    harness: str,
    allow_target: str | None,
) -> tuple[str, str, str, str, str, str | None]:
    dirs = {
        "work": _validated_dir("work", work),
        "ro": _validated_dir("ro", ro),
        "denied": _validated_dir("denied", denied),
        "secret": _validated_dir("secret", secret),
        "harness": _validated_dir("harness", harness),
    }
    values = list(dirs.values())
    for i, a in enumerate(values):
        for b in values[i + 1 :]:
            if a == b:
                raise _fixed("invalid profile: overlapping directories")
            if b.startswith(a.rstrip("/") + "/") or a.startswith(b.rstrip("/") + "/"):
                raise _fixed("invalid profile: overlapping directories")
    target = None
    if allow_target is not None:
        target = _validated_dir("allow_target", allow_target)
        for base_name in ("denied", "secret"):
            base = dirs[base_name].rstrip("/")
            if target.startswith(base + "/") and base + "/" < target:
                break
        else:
            raise _fixed("invalid profile: allow_target outside denied/secret")
    return dirs["work"], dirs["ro"], dirs["denied"], dirs["secret"], dirs["harness"], target


def _validate_endpoint(
    allow_endpoint: tuple[str, int] | None,
) -> tuple[str, int] | None:
    if allow_endpoint is None:
        return None
    if len(allow_endpoint) != 2:
        raise _fixed("invalid profile: allow_endpoint must be (host, port)")
    host, port = allow_endpoint
    if not isinstance(host, str) or host != "127.0.0.1":
        raise _fixed("invalid profile: allow_endpoint host must be 127.0.0.1")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise _fixed("invalid profile: allow_endpoint port out of range")
    return host, port


def _sub_rules(root: str) -> list[tuple[str, str]]:
    r = root.rstrip("/")
    return [
        (r, r),
        (r + "/profiles", r + "/profiles"),
        (r + "/deps", r + "/deps"),
        (r + "/capture", r + "/capture"),
        (r + "/evidence", r + "/evidence"),
        (r + "/state", r + "/state"),
    ]


def build_profile(
    *,
    work: str,
    ro: str,
    denied: str,
    secret: str,
    harness: str,
    allow_endpoint: tuple[str, int] | None = None,
    allow_target: str | None = None,
) -> str:
    """Generate Seatbelt SBPL text (default deny). No I/O; never executable.

    Worker: write only ``work``; read only ``ro``; ``denied`` write-deny,
    ``secret`` read-deny, ``harness`` (incl. profiles/deps/capture/evidence/
    state) full deny; network fully denied except an optional single
    ``127.0.0.1`` loopback endpoint and an optional single-file allow under
    ``denied``/``secret`` for the same-target positive control.  Every runtime
    dependency of the interpreter itself must be disclosed per platform and
    verified on a real Mac before any probe; until then this text alone does
    not constitute proof of OS enforcement.
    """
    work, ro, denied, secret, harness, target = _validate_paths(
        work, ro, denied, secret, harness, allow_target
    )
    endpoint = _validate_endpoint(allow_endpoint)

    lines: list[str] = []
    lines.append("(version 1)")
    lines.append("")
    lines.append("; M2-C2A synthetic boundary profile (harness-generated, default deny)")
    lines.append("(deny default)")
    lines.append("")
    lines.append("; --- harness private areas: full deny for Worker (defense in depth)")
    for _a, p in _sub_rules(harness):
        lines.append(f'(deny file-read* file-write* file-ioctl (literal "{_sbpl_lit(p)}"))')
    lines.append("")
    lines.append("; --- denied area: write denied; read allowed for same-target control")
    _deny_literal = f'(deny file-write* file-ioctl (literal "{_sbpl_lit(denied)}")'
    lines.append(_deny_literal + f' (subpath "{_sbpl_lit(denied)}"))')
    lines.append(
        f'(allow file-read* (literal "{_sbpl_lit(denied)}") (subpath "{_sbpl_lit(denied)}"))'
    )
    if target is not None:
        lines.append("; same-target positive control: single synthetic file allow")
        lines.append(f'(allow file-read* file-write* (literal "{_sbpl_lit(target)}"))')
    lines.append("")
    lines.append("; --- secret area: read denied; write denied")
    _sec_literal = f'(deny file-read* file-write* file-ioctl (literal "{_sbpl_lit(secret)}")'
    lines.append(_sec_literal + f' (subpath "{_sbpl_lit(secret)}"))')
    lines.append("")
    lines.append("; --- work area: the only writable area (synthetic git repo)")
    _work_literal = f'(allow file-read* file-write* file-ioctl (literal "{_sbpl_lit(work)}")'
    lines.append(_work_literal + f' (subpath "{_sbpl_lit(work)}"))')
    lines.append("")
    lines.append("; --- ro area: read only (frozen fixture scripts live here)")
    _ro_literal = f'(allow file-read* (literal "{_sbpl_lit(ro)}")'
    lines.append(_ro_literal + f' (subpath "{_sbpl_lit(ro)}"))')
    lines.append("")
    lines.append("; --- network: fully denied")
    lines.append("(deny network*)")
    if endpoint is not None:
        host, port = endpoint
        lines.append("; loopback control endpoint (harness-owned 127.0.0.1 service)")
        rule = f'(allow network-outbound (local ip "{host}") (remote ip "{host}")'
        lines.append(rule + f' (local port "{port}") (remote port "{port}"))')
    lines.append("")
    lines.append("; --- minimal runtime read allow list")
    lines.append("; Basis: the Python interpreter and its standard library map read")
    lines.append("; dependencies (python binary, dylibs, encodings/locale data) must be")
    lines.append("; readable for the fixture to start.  This list is generated from")
    lines.append("; platform observation and MUST be re-verified on the real Mac before")
    lines.append("; any authorized probe; until then no enforcement claim is made.")
    lines.append('(allow file-read* (literal "/usr/bin/python3") (subpath "/usr/local"))')
    lines.append('(allow file-read* (subpath "/System/Library/Frameworks"))')
    lines.append('(allow file-read* (subpath "/System/Library/Caches"))')
    lines.append('(allow file-read* (subpath "/System/Library/Extensions"))')
    lines.append('(allow file-read* (subpath "/usr/lib"))')
    lines.append('(allow file-read* (subpath "/usr/local/lib"))')
    lines.append('(allow file-read* (subpath "/private/var/select"))')
    lines.append('(allow file-read* (subpath "/etc"))')
    lines.append("")
    return "\n".join(lines) + "\n"
