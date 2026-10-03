"""Preparation-format regression tests, not M0 runtime acceptance."""

import copy
import json
import runpy
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

ROOT = Path(__file__).resolve().parents[2]


def read_json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def validator(name):
    schema = read_json(f"schemas/{name}.schema.json")
    return Draft202012Validator(schema, format_checker=FormatChecker())


def accepted_review():
    review = read_json("examples/artifacts/review.json")
    review["decision"] = "accept"
    review["verification_status"] = "passed"
    return review


def test_preparation_checker_runs_from_another_working_directory(tmp_path):
    subprocess.run([sys.executable, str(ROOT / "scripts/check_specs.py")], cwd=tmp_path, check=True)


def test_frozen_task_requires_a_baseline():
    task = read_json("tasks/M0/task.json")
    task["status"] = "frozen"
    with pytest.raises(ValidationError):
        validator("task").validate(task)


@pytest.mark.parametrize("budget", ["max_repair_rounds", "max_takeovers"])
def test_unbounded_repair_is_rejected(budget):
    task = read_json("tasks/M0/task.json")
    task["budgets"][budget] = 2
    with pytest.raises(ValidationError):
        validator("task").validate(task)


@pytest.mark.parametrize("status", ["failed", "not_run"])
def test_review_cannot_accept_unverified_candidate(status):
    review = accepted_review()
    review["verification_status"] = status
    with pytest.raises(ValidationError):
        validator("review").validate(review)


def test_review_cannot_accept_a_reused_session():
    review = accepted_review()
    review["reviewer"]["fresh_session"] = False
    with pytest.raises(ValidationError):
        validator("review").validate(review)


@pytest.mark.parametrize("severity", ["blocking", "major"])
def test_review_cannot_accept_unresolved_critical_findings(severity):
    review = accepted_review()
    review["findings"] = [
        {"id": "F1", "severity": severity, "description": "Unresolved defect", "path": None}
    ]
    with pytest.raises(ValidationError):
        validator("review").validate(review)


@pytest.mark.parametrize(
    ("stage", "decision"),
    [("review_1", "takeover"), ("review_2", "return_once"), ("final_verify", "return_once")],
)
def test_review_decision_must_match_the_stage(stage, decision):
    review = read_json("examples/artifacts/review.json")
    review.update(stage=stage, decision=decision)
    with pytest.raises(ValidationError):
        validator("review").validate(review)


def test_context_independence_does_not_require_provider_independence():
    review = accepted_review()
    review["reviewer"]["independent_provider"] = False
    validator("review").validate(review)


@pytest.mark.parametrize(
    ("field", "value"), [("exit_code", 7), ("session_id", None), ("truncated", True)]
)
def test_completed_result_cannot_hide_execution_failure(field, value):
    result = read_json("examples/artifacts/agent-result.json")
    result[field] = value
    with pytest.raises(ValidationError):
        validator("agent-result").validate(result)


def test_unknown_usage_remains_unknown():
    result = read_json("examples/artifacts/agent-result.json")
    assert result["usage"] is None
    validator("agent-result").validate(result)
    result["usage"] = {"input_tokens": -1, "output_tokens": None}
    with pytest.raises(ValidationError):
        validator("agent-result").validate(result)


def test_unknown_fields_cannot_smuggle_policy_into_a_result():
    result = read_json("examples/artifacts/agent-result.json")
    result["permission_override"] = "full-access"
    with pytest.raises(ValidationError):
        validator("agent-result").validate(result)


def test_event_timestamp_must_have_a_timezone():
    event = read_json("examples/artifacts/event.json")
    event["timestamp"] = "2026-10-03T05:00:00"
    with pytest.raises(ValidationError):
        validator("event").validate(event)


@pytest.mark.parametrize("path", ["../secret", "/tmp/secret", "C:/secret", "a\\b", "."])
def test_preparation_paths_must_stay_relative(path):
    check = runpy.run_path(str(ROOT / "scripts/check_specs.py"))["check_path"]
    with pytest.raises(ValueError):
        check(path)


@pytest.mark.parametrize("field", ["require_sandbox", "auto_push", "raw_transcripts"])
def test_example_policy_cannot_relax_safety_defaults(field):
    project = tomllib.loads((ROOT / "examples/synthetic/project.toml").read_text())
    project["policy"][field] = not project["policy"][field]
    with pytest.raises(ValidationError):
        validator("project").validate(project)


def test_project_role_must_reference_a_declared_agent():
    project = tomllib.loads((ROOT / "examples/synthetic/project.toml").read_text())
    project = copy.deepcopy(project)
    project["roles"]["implementer"] = "missing"
    check = runpy.run_path(str(ROOT / "scripts/check_specs.py"))["check_project"]
    with pytest.raises(ValueError, match="undeclared"):
        check(project)
