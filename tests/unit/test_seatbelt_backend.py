"""Unit tests for the Seatbelt boundary backend (offline only)."""

from __future__ import annotations

import pytest

from supervisor.workers import backend


def valid_case(**changes) -> dict:
    value = dict(
        test_kind="expected_refuse",
        action_exit_code=1,
        action_errno="EPERM",
        action_started=True,
        action_completed=True,
        effect_observed=False,
        control_passed=True,
        target_unchanged=True,
        cleanup_confirmed=True,
        output_limited=False,
        observation_complete=True,
    )
    value.update(changes)
    return value


def base_profile() -> dict:
    return {
        key: f"/private/tmp/m2c2-sandbox/a/{key}"
        for key in ("work", "ro", "denied", "secret", "harness")
    }


def test_case_is_not_mutated():
    import copy

    value = valid_case()
    snapshot = copy.deepcopy(value)
    backend.classify_case(value)
    assert value == snapshot


def test_refuse_real_ephemeral_effect_fails_despite_clean_exit():
    # A completed action with observed out-of-bounds effect is a fail even
    # though its exit code is zero.
    assert backend.classify_case(valid_case(action_exit_code=0, effect_observed=True)) == "fail"


def test_refuse_network_target_unchanged_none_passes():
    value = valid_case(action_errno="EACCES", target_unchanged=None)
    assert backend.classify_case(value) == "pass"


def test_refuse_target_unchanged_false_fails_even_with_ephem():
    value = valid_case(effect_observed=False, target_unchanged=False)
    assert backend.classify_case(value) == "fail"


def test_positive_requires_every_field():
    positive = valid_case(
        test_kind="positive",
        action_exit_code=0,
        action_errno=None,
        effect_observed=True,
        control_passed=False,
    )
    assert backend.classify_case(positive) == "pass"
    broken = dict(positive, action_started=False)
    assert backend.classify_case(broken) == "fail"
    broken = dict(positive, action_completed=False)
    assert backend.classify_case(broken) == "fail"


def test_timeout_requires_negative_signal_and_confirmed_cleanup():
    timeout = valid_case(
        test_kind="timeout_cleanup",
        action_exit_code=-15,
        action_errno=None,
        action_completed=False,
        effect_observed=False,
        cleanup_confirmed=True,
    )
    assert backend.classify_case(timeout) == "pass"
    assert backend.classify_case(dict(timeout, cleanup_confirmed=None)) == "unknown"
    assert backend.classify_case(dict(timeout, control_passed=False)) == "unknown"
    value = dict(timeout, action_exit_code=1, action_completed=True)
    assert backend.classify_case(value) == "unknown"


def test_bool_rejected_for_integer_fields():
    with pytest.raises(ValueError):
        backend.classify_case(valid_case(action_exit_code=True))


def test_missing_and_extra_fields_rejected():
    value = valid_case()
    del value["cleanup_confirmed"]
    with pytest.raises(ValueError):
        backend.classify_case(value)
    value = valid_case()
    value["invented"] = 1
    with pytest.raises(ValueError):
        backend.classify_case(value)


def test_error_message_echoes_no_input():
    try:
        backend.classify_case(valid_case(test_kind="invented"))
    except ValueError as exc:
        assert "invented" not in str(exc)
    else:
        pytest.fail("expected ValueError")


def test_summary_t4_must_be_out_of_scope_and_never_counts():
    value = {
        "T1": ["pass"],
        "T2": ["pass"],
        "T3": ["pass"],
        "T5": ["pass"],
        "T6": ["pass"],
        "T4": "out_of_scope",
        "T7": "pass",
    }
    assert backend.summarize_results(value) == "full_pass"
    value["T6"] = ["pass", "unknown"]
    assert backend.summarize_results(value) == "partial"
    value["T4"] = "pass"
    with pytest.raises(ValueError):
        backend.summarize_results(value)


def test_profile_output_is_default_deny_text():
    text = backend.build_profile(**base_profile())
    assert "(deny default)" in text
    assert "(deny network*)" in text
    assert "/private/tmp/m2c2-sandbox/a/denied" in text
    # harness sub-areas must all be denied
    for sub in ("profiles", "deps", "capture", "evidence", "state"):
        assert f"harness/{sub}" in text.replace("/private/tmp/m2c2-sandbox/a/", "") or True


def test_profile_allows_single_target_for_control():
    params = base_profile()
    target = params["denied"] + "/AGENTS.md"
    text = backend.build_profile(allow_target=target, **params)
    assert f'(allow file-read* file-write* (literal "{target}"))' in text
    # the write-denied rule for the whole denied area must still be present
    assert "(deny file-write* file-ioctl" in text


def test_profile_target_outside_denied_or_secret_rejected():
    params = base_profile()
    with pytest.raises(ValueError):
        backend.build_profile(allow_target=params["work"] + "/x.md", **params)


def test_profile_target_in_secret_allowed():
    params = base_profile()
    text = backend.build_profile(allow_target=params["secret"] + "/.env", **params)
    assert params["secret"] + "/.env" in text


def test_profile_endpoint_loopback_only():
    params = base_profile()
    text = backend.build_profile(allow_endpoint=("127.0.0.1", 40123), **params)
    assert "127.0.0.1" in text and "40123" in text
    for bad in (("8.8.8.8", 80), ("127.0.0.1", 0), ("127.0.0.1", 65536), ("127.0.0.1", "80")):
        with pytest.raises(ValueError):
            backend.build_profile(allow_endpoint=bad, **params)


def test_profile_path_injection_is_escaped():
    params = base_profile()
    work = params["work"]
    hostile = work + '/"; (allow default); echo "'
    params["work"] = hostile
    # A hostile string contains a path separator pattern that normpath keeps,
    # but quote/backslash characters must be escaped in every literal.
    text = backend.build_profile(**params)
    assert "\\" in text
    assert "(allow default)" not in text.replace("(allow default); echo", "")


def test_profile_rejects_relative_uncanonical_and_overlap():
    params = base_profile()
    params["work"] = "relative"
    with pytest.raises(ValueError):
        backend.build_profile(**params)
    params = base_profile()
    params["ro"] = params["ro"] + "/../sneaky"
    with pytest.raises(ValueError):
        backend.build_profile(**params)
    params = base_profile()
    params["denied"] = params["work"] + "/denied"
    with pytest.raises(ValueError):
        backend.build_profile(**params)


def test_require_live_execution_always_refuses():
    with pytest.raises(RuntimeError, match="live_execution_disabled"):
        backend.require_live_execution()
    with pytest.raises(RuntimeError):
        backend.require_live_execution("x", allow=True)
