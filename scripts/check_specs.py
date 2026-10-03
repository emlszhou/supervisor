"""Validate preparation artifacts; this does not execute tasks or prove runtime safety."""

import fnmatch
import json
import subprocess
import tomllib
from pathlib import Path, PurePosixPath

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def check_path(value: str, *, allow_root: bool = False) -> None:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ValueError(f"Invalid relative path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or (value == "." and not allow_root):
        raise ValueError(f"Path escapes or names the workspace root: {value!r}")


def check_project(data: dict) -> None:
    check_path(data["project"]["root"], allow_root=True)
    if set(data["roles"].values()) - set(data["agents"]):
        raise ValueError("Role refers to an undeclared agent")
    if any(agent["adapter"] != "mock" for agent in data["agents"].values()):
        raise ValueError("Scaffold examples must use only mock adapters")
    policy = data["policy"]
    if policy["network"] == "disabled" and policy["allowed_domains"]:
        raise ValueError("Disabled networking must have no allowed domains")
    for group in ("allowed_files", "forbidden_files"):
        for path in policy[group]:
            check_path(path)
    check_checks(data["verification"]["checks"])


def check_checks(checks: list[dict]) -> None:
    names = [check["id"] for check in checks]
    if len(names) != len(set(names)):
        raise ValueError("Verification IDs must be unique")
    if not any(check["required"] for check in checks):
        raise ValueError("At least one required verification is needed")


def main() -> int:
    schemas = {}
    for path in sorted((ROOT / "schemas").glob("*.schema.json")):
        schema = load_json(path)
        Draft202012Validator.check_schema(schema)
        schemas[path.name.removesuffix(".schema.json")] = schema

    def validate(name: str, data) -> None:
        Draft202012Validator(schemas[name], format_checker=FormatChecker()).validate(data)

    for name in ("task", "agent-result", "review", "event"):
        validate(name, load_json(ROOT / "examples" / "artifacts" / f"{name}.json"))
    validate("review", load_json(ROOT / "templates" / "review.json"))

    for path in (ROOT / "examples/synthetic/project.toml", ROOT / "templates/project.toml"):
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        validate("project", data)
        check_project(data)

    task_dir = ROOT / "tasks/M0"
    task = load_json(task_dir / "task.json")
    validate("task", task)
    for key in (
        "requirements_file",
        "allowed_files_file",
        "forbidden_files_file",
        "verification_file",
    ):
        check_path(task[key])
        if not (task_dir / task[key]).is_file():
            raise ValueError(f"Task input is missing: {task[key]}")
    groups = []
    for name in ("allowed_files_file", "forbidden_files_file"):
        paths = load_json(task_dir / task[name])
        if not isinstance(paths, list) or not paths or len(paths) != len(set(paths)):
            raise ValueError(f"Invalid task file list: {name}")
        for path in paths:
            check_path(path)
        groups.append(paths)
    if any(fnmatch.fnmatchcase(path, deny) for path in groups[0] for deny in groups[1]):
        raise ValueError("M0 allow/deny scope overlaps")

    verification = load_json(task_dir / task["verification_file"])
    validate("verification", verification)
    check_checks(verification["checks"])
    if not any(c["kind"] == "independent" and c["required"] for c in verification["checks"]):
        raise ValueError("M0 requires independent behavioral verification")
    if task["status"] == "frozen":
        subprocess.run(
            ["git", "cat-file", "-e", f"{task['baseline_commit']}^{{commit}}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )

    print(f"Validated {len(schemas)} schemas, sample artifacts/configs and M0 {task['status']}.")
    print("Runtime behavior, task freezing, agent execution and isolation remain unverified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
