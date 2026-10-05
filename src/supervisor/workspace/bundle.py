"""Freeze and verify complete v1 task bundles, using stdlib validation."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import stat
from pathlib import Path

from supervisor.policy.changes import _validate_pattern
from supervisor.workspace.snapshot import (
    _SHA256_RE,
    _check_ancestors,
    _inventory_paths,
    _read_regular,
    _validate_relative_path,
)

# Mirror the v1 contract: no third-party deps.
_TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SHA_RE = re.compile(r"^(?:[a-f0-9]{40}|[a-f0-9]{64})$")
_ROLE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

_REQUIRED_TASK_FILES = (
    "task.json",
    "requirements.md",
    "allowed_files.json",
    "forbidden_files.json",
    "verification.json",
)


# ---------- JSON v1 validators (stdlib-only per contract) ----------


def _validate_task_v1(task: object, *, expected_task_id: str, require_draft: bool) -> None:
    if not isinstance(task, dict):
        raise ValueError("task.json must be a JSON object")
    required = {
        "schema_version",
        "task_id",
        "revision",
        "status",
        "baseline_commit",
        "requirements_file",
        "allowed_files_file",
        "forbidden_files_file",
        "verification_file",
        "roles",
        "budgets",
    }
    if set(task) != required:
        raise ValueError("task.json has unexpected or missing fields")
    if type(task["schema_version"]) is not int or task["schema_version"] != 1:
        raise ValueError("task.json schema_version must be 1")
    if not isinstance(task["task_id"], str) or not _TASK_ID_RE.fullmatch(task["task_id"]):
        raise ValueError("task.json task_id has invalid shape")
    if task["task_id"] != expected_task_id:
        raise ValueError("task.json task_id does not match freeze_bundle(task_id=)")
    if (
        not isinstance(task["revision"], int)
        or task["revision"] < 1
        or isinstance(task["revision"], bool)
    ):
        raise ValueError("task.json revision must be a positive integer")
    if task["status"] not in ("draft", "frozen"):
        raise ValueError("task.json status must be 'draft' or 'frozen'")
    if require_draft and task["status"] != "draft":
        raise ValueError("freeze_bundle requires task.json status='draft'")
    bc = task["baseline_commit"]
    if require_draft:
        if bc is not None:
            raise ValueError("freeze_bundle requires task.json baseline_commit=null")
    else:
        if not isinstance(bc, str) or not _SHA_RE.fullmatch(bc):
            raise ValueError("frozen task.json baseline_commit must be a 40/64 lowercase hex SHA")
    expected_pointers = {
        "requirements_file": "requirements.md",
        "allowed_files_file": "allowed_files.json",
        "forbidden_files_file": "forbidden_files.json",
        "verification_file": "verification.json",
    }
    for key, expected in expected_pointers.items():
        if task[key] != expected:
            raise ValueError(f"task.json {key} has unexpected value")
    # roles: 5 entries, each matching identity regex.
    if not isinstance(task["roles"], dict) or set(task["roles"]) != {
        "planner",
        "implementer",
        "reviewer",
        "fallback_repairer",
        "final_verifier",
    }:
        raise ValueError("task.json roles has unexpected shape")
    for k, v in task["roles"].items():
        if not isinstance(v, str) or not _ROLE_ID_RE.fullmatch(v):
            raise ValueError(f"task.json roles.{k} has invalid identity")
    # budgets: required keys, all non-negative ints > 0.
    budgets = task["budgets"]
    if not isinstance(budgets, dict) or set(budgets) != {
        "max_agent_calls",
        "max_repair_rounds",
        "max_takeovers",
        "max_wall_seconds",
        "max_changed_files",
        "max_diff_lines",
        "max_output_bytes",
    }:
        raise ValueError("task.json budgets has unexpected shape")
    for k, v in budgets.items():
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError(f"task.json budgets.{k} must be an integer")
        minimum = 0 if k in ("max_repair_rounds", "max_takeovers") else 1
        if v < minimum:
            raise ValueError(f"task.json budgets.{k} must be >= {minimum}")
        if k in ("max_repair_rounds", "max_takeovers") and v > 1:
            raise ValueError(f"task.json budgets.{k} must be <= 1")


def _validate_verification_v1(v: object) -> None:
    if not isinstance(v, dict) or set(v) != {"schema_version", "checks"}:
        raise ValueError("verification.json has unexpected shape")
    if type(v["schema_version"]) is not int or v["schema_version"] != 1:
        raise ValueError("verification.json schema_version must be 1")
    checks = v["checks"]
    if not isinstance(checks, list) or not checks:
        raise ValueError("verification.json checks must be a non-empty list")
    for i, c in enumerate(checks):
        if not isinstance(c, dict) or set(c) != {"id", "kind", "argv", "cwd", "required"}:
            raise ValueError(f"verification.json checks[{i}] has unexpected shape")
        if not isinstance(c["id"], str) or not _TASK_ID_RE.fullmatch(c["id"]):
            raise ValueError(f"verification.json checks[{i}].id invalid")
        if c["kind"] not in ("project", "protected", "independent"):
            raise ValueError(f"verification.json checks[{i}].kind invalid")
        if (
            not isinstance(c["argv"], list)
            or not c["argv"]
            or not all(isinstance(a, str) and a for a in c["argv"])
        ):
            raise ValueError(f"verification.json checks[{i}].argv must be non-empty strings")
        if c["cwd"] != ".":
            raise ValueError(f"verification.json checks[{i}].cwd must be '.'")
        if not isinstance(c["required"], bool):
            raise ValueError(f"verification.json checks[{i}].required must be a bool")


def _validate_string_list_file(payload: object, *, name: str) -> None:
    if not isinstance(payload, list) or not all(isinstance(x, str) and x for x in payload):
        raise ValueError(f"{name} must be a list of non-empty strings")
    for pattern in payload:
        _validate_pattern(pattern)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _build_manifest_bytes(*, task_id: str, baseline_commit: str, files: dict[str, str]) -> bytes:
    return json.dumps(
        {
            "schema_version": 1,
            "task_id": task_id,
            "baseline_commit": baseline_commit,
            "files": files,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()


def _capture(root: Path) -> tuple[dict[str, bytes], dict]:
    root = _check_ancestors(root)
    if not root.is_dir():
        raise ValueError("bundle root must be a directory")
    inventory = _inventory_paths(root)
    content = {
        rel: _read_regular(root, rel, signature)
        for rel, signature in sorted(inventory.items())
        if stat.S_ISREG(signature[2])
    }
    if inventory != _inventory_paths(root):
        raise ValueError("bundle inventory changed during reading")
    return content, inventory


def _json(data: bytes, name: str = "manifest.json") -> object:
    try:

        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError(f"{name}: duplicate JSON key")
                result[key] = value
            return result

        return json.loads(data, object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"{name}: invalid UTF-8 JSON") from e


def _validate_inputs(content: dict[str, bytes], task_id: str, *, draft: bool) -> dict:
    if not set(_REQUIRED_TASK_FILES) <= content.keys():
        raise ValueError(
            f"bundle missing required files: {sorted(set(_REQUIRED_TASK_FILES) - content.keys())}"
        )
    task = _json(content["task.json"], "task.json")
    _validate_task_v1(task, expected_task_id=task_id, require_draft=draft)
    if not draft and task["status"] != "frozen":
        raise ValueError("bundle task must be frozen")
    for name in ("allowed_files.json", "forbidden_files.json"):
        _validate_string_list_file(_json(content[name], name), name=name)
    _validate_verification_v1(_json(content["verification.json"], "verification.json"))
    return task


def freeze_bundle(source: Path, output: Path, *, task_id: str, baseline_commit: str) -> str:
    if not isinstance(task_id, str) or not _TASK_ID_RE.fullmatch(task_id):
        raise ValueError("invalid task_id")
    if not isinstance(baseline_commit, str) or not _SHA_RE.fullmatch(baseline_commit):
        raise ValueError("baseline_commit must be a full SHA")
    source, output = _check_ancestors(Path(source)), _check_ancestors(Path(output))
    if source == output or source in output.parents or output in source.parents:
        raise ValueError("output must not overlap source")
    if output.exists():
        raise ValueError("output must not exist")
    content, inventory = _capture(source)
    if "manifest.json" in inventory:
        raise ValueError("source must not contain manifest.json")
    task = _validate_inputs(content, task_id, draft=True)
    task = dict(task, status="frozen", baseline_commit=baseline_commit)
    content["task.json"] = json.dumps(
        task, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    manifest = _build_manifest_bytes(
        task_id=task_id,
        baseline_commit=baseline_commit,
        files={p: _sha256_bytes(b) for p, b in content.items()},
    )
    digest = _sha256_bytes(manifest)
    content["manifest.json"] = manifest
    _check_ancestors(output)
    # mkdir exclusively claims this output: never replace even an empty
    # directory created by another actor after the earlier existence check.
    try:
        output.mkdir()
    except FileExistsError as e:
        raise ValueError("output must not exist") from e
    identity = output.lstat()
    try:
        for rel, data in content.items():
            target = output / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            _check_ancestors(target)
            with target.open("xb") as f:
                f.write(data)
            target.chmod(0o444)
        if inventory != _inventory_paths(source):
            raise ValueError("source changed during freeze")
        verify_bundle(output, digest)
    except BaseException:
        # Only remove the directory this invocation created, never an
        # independently substituted path. rmtree does not follow file links.
        if output.exists() and not output.is_symlink():
            current = output.lstat()
            if (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino):
                shutil.rmtree(output)
        raise
    return digest


def _parse_manifest_bytes(raw: bytes) -> dict:
    manifest = _json(raw)
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema_version",
        "task_id",
        "baseline_commit",
        "files",
    }:
        raise ValueError("manifest has unexpected fields")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ValueError("manifest schema_version must be integer 1")
    if not isinstance(manifest["task_id"], str) or not _TASK_ID_RE.fullmatch(manifest["task_id"]):
        raise ValueError("invalid manifest task_id")
    if not isinstance(manifest["baseline_commit"], str) or not _SHA_RE.fullmatch(
        manifest["baseline_commit"]
    ):
        raise ValueError("invalid manifest baseline_commit")
    if not isinstance(manifest["files"], dict):
        raise ValueError("manifest files must be an object")
    for rel, digest in manifest["files"].items():
        _validate_relative_path(rel)
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            raise ValueError("invalid manifest file digest")
    if "manifest.json" in manifest["files"]:
        raise ValueError("manifest must not list itself")
    if (
        _build_manifest_bytes(
            task_id=manifest["task_id"],
            baseline_commit=manifest["baseline_commit"],
            files=manifest["files"],
        )
        != raw
    ):
        raise ValueError("manifest must use canonical encoding")
    return manifest


def verify_bundle(root: Path, expected_sha256: str) -> dict:
    if not isinstance(expected_sha256, str) or not _SHA256_RE.fullmatch(expected_sha256):
        raise ValueError("expected_sha256 must be 64 lowercase hex characters")
    content, inventory = _capture(Path(root))
    if "manifest.json" not in content:
        raise ValueError("bundle missing manifest.json")
    raw = content.pop("manifest.json")
    if _sha256_bytes(raw) != expected_sha256:
        raise ValueError("manifest digest mismatch")
    manifest = _parse_manifest_bytes(raw)
    if {p: _sha256_bytes(b) for p, b in content.items()} != manifest["files"]:
        raise ValueError("bundle file inventory or digest mismatch")
    implied_dirs = {
        parent.as_posix() for rel in content for parent in Path(rel).parents if parent != Path(".")
    }
    actual_dirs = {p for p, s in inventory.items() if stat.S_ISDIR(s[2])}
    if actual_dirs != implied_dirs:
        raise ValueError("bundle has unexpected directories")
    task = _validate_inputs(content, manifest["task_id"], draft=False)
    if task["baseline_commit"] != manifest["baseline_commit"]:
        raise ValueError("task baseline differs from manifest")
    return manifest
