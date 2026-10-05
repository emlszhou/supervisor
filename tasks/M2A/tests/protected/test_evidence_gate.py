"""Synthetic gate tests; these do not claim Hermes was executed."""

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "m2a_gate", Path(__file__).parents[2] / "validate_delivery.py"
)
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def report():
    checks = []
    for name in sorted(GATE.IDS):
        check = dict.fromkeys(GATE.CHECK_FIELDS)
        check.update(
            id=name,
            declared="unknown",
            observed="unknown",
            enforced="unknown",
            status="not_run",
            reason="Synthetic unexecuted fixture",
        )
        checks.append(check)
    return dict(
        schema_version=1,
        task_id="M2A-hermes-capabilities",
        run_id="fixture",
        attempt_id="fixture",
        baseline_commit="a" * 40,
        host=dict(os="fixture", architecture="fixture"),
        agent=dict(binary="fixture", version="unknown"),
        route=dict(provider="unknown", model="unknown", inference_location="unknown"),
        checks=checks,
        adapter_readiness="blocked",
        limitations=["Not runtime evidence"],
    )


def test_unknown_inventory_can_be_honestly_blocked():
    GATE.validate(report(), "a" * 40)


@pytest.mark.parametrize(
    "mutation", ["boolean", "ready", "duplicate", "extra", "binding", "fake_exit"]
)
def test_invalid_or_fabricated_metadata_is_rejected(mutation):
    value = report()
    if mutation == "boolean":
        value["schema_version"] = True
    elif mutation == "ready":
        value["adapter_readiness"] = "ready"
    elif mutation == "duplicate":
        value["checks"][1]["id"] = value["checks"][0]["id"]
    elif mutation == "extra":
        value["trusted"] = True
    elif mutation == "binding":
        value["baseline_commit"] = "b" * 40
    else:
        value["checks"][0]["exit_code"] = 0
    with pytest.raises(ValueError):
        GATE.validate(value, "a" * 40)
