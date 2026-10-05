"""Regression probes for independent M1 findings, without developer paths."""

import hashlib
import json
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest

from supervisor.policy.changes import check_changes
from supervisor.storage.intents import IntentStore
from supervisor.workspace import bundle, snapshot
from supervisor.workspace.baseline import inspect_baseline


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()

    def git(*args):
        return (
            subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE)
            .decode()
            .strip()
        )

    git("init", "-q")
    git("config", "user.name", "M1 regression")
    git("config", "user.email", "m1@example.invalid")
    (root / "a.txt").write_text("baseline")
    git("add", ".")
    git("commit", "-qm", "fixture")
    return root, git("rev-parse", "HEAD"), git


def draft(tmp_path):
    root = tmp_path / "draft"
    root.mkdir()
    task = dict(
        schema_version=1,
        task_id="regression",
        revision=1,
        status="draft",
        baseline_commit=None,
        requirements_file="requirements.md",
        allowed_files_file="allowed_files.json",
        forbidden_files_file="forbidden_files.json",
        verification_file="verification.json",
        roles=dict.fromkeys(
            ("planner", "implementer", "reviewer", "fallback_repairer", "final_verifier"), "A"
        ),
        budgets=dict(
            max_agent_calls=1,
            max_repair_rounds=0,
            max_takeovers=0,
            max_wall_seconds=1,
            max_changed_files=1,
            max_diff_lines=1,
            max_output_bytes=1,
        ),
    )
    for name, value in (
        ("task.json", task),
        ("allowed_files.json", ["**"]),
        ("forbidden_files.json", []),
        (
            "verification.json",
            {
                "schema_version": 1,
                "checks": [
                    {"id": "v", "kind": "project", "argv": ["python"], "cwd": ".", "required": True}
                ],
            },
        ),
    ):
        (root / name).write_text(json.dumps(value))
    (root / "requirements.md").write_text("requirements")
    return root


def test_ignored_inventory_and_fixed_directory_exclusions(repo):
    root, sha, git = repo
    (root / ".gitignore").write_text("ignored\n")
    (root / "ignored").write_text("controlled")
    (root / ".venv").mkdir()
    (root / ".venv" / "python").symlink_to("/missing/interpreter")
    assert "ignored" in {
        f["path"] for f in snapshot.capture_snapshot(root, baseline_commit=sha)["files"]
    }
    with pytest.raises(ValueError, match="untracked"):
        inspect_baseline(root)
    git("add", ".gitignore")
    git("add", "-f", "ignored")
    git("commit", "-qm", "ignored tracked")
    assert inspect_baseline(root) == git("rev-parse", "HEAD")


def test_staged_deletion_and_tracked_generated_file(repo):
    root, sha, git = repo
    git("rm", "a.txt")
    assert snapshot.capture_snapshot(root, baseline_commit=sha)["deleted"] == ["a.txt"]
    (root / ".venv").mkdir()
    (root / ".venv" / "controlled").write_text("tracked")
    git("add", "-f", ".venv/controlled")
    git("commit", "-qm", "fixture")
    sha = git("rev-parse", "HEAD")
    git("rm", "--cached", ".venv/controlled")
    result = snapshot.capture_snapshot(root, baseline_commit=sha)
    assert [f["path"] for f in result["files"]] == [".venv/controlled"]
    assert result["deleted"] == []


@pytest.mark.parametrize("mutation", ["rewrite", "addition", "delete"])
def test_capture_detects_mutation_after_read(repo, monkeypatch, mutation):
    root, sha, _ = repo
    original = snapshot._read_regular

    def read(*args):
        data = original(*args)
        if mutation == "rewrite":
            (root / "a.txt").write_text("changed")
        elif mutation == "addition":
            (root / "new").write_text("new")
        else:
            (root / "a.txt").unlink()
        return data

    monkeypatch.setattr(snapshot, "_read_regular", read)
    with pytest.raises(ValueError, match="changed"):
        snapshot.capture_snapshot(root, baseline_commit=sha)


def test_parent_link_rejected_before_content_read(repo, tmp_path, monkeypatch):
    root, sha, git = repo
    (root / "sub").mkdir()
    (root / "sub" / "x").write_text("inside")
    git("add", "sub/x")
    git("commit", "-qm", "sub")
    (root / "sub" / "x").unlink()
    (root / "sub").rmdir()
    (root / "sub").symlink_to(tmp_path)
    monkeypatch.setattr(snapshot, "_read_regular", lambda *a: pytest.fail("unsafe content read"))
    with pytest.raises(ValueError):
        snapshot.capture_snapshot(root, baseline_commit=sha)


@pytest.mark.parametrize("path", ["x.py", "src/x.py", "src/deep/x.py"])
def test_forbidden_globstar_zero_directory_match(repo, path):
    root, sha, _ = repo
    before = snapshot.capture_snapshot(root, baseline_commit=sha)
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("forbidden")
    after = snapshot.capture_snapshot(root, baseline_commit=sha)
    with pytest.raises(ValueError, match="forbidden"):
        check_changes(
            before,
            after,
            allowed=["**"],
            forbidden=["**/*.py"],
            max_changed_files=10,
            max_diff_lines=10,
            diff_lines=1,
        )


@pytest.mark.parametrize(
    "field,value", [("path", 3), ("mode", True), ("sha256", "a" * 40), ("sha256", "a" * 64 + "\n")]
)
def test_rehashed_invalid_snapshot_rejected(repo, field, value):
    root, sha, _ = repo
    result = snapshot.capture_snapshot(root, baseline_commit=sha)
    result["files"][0][field] = value
    result["snapshot_sha256"] = snapshot._snapshot_digest(
        {k: v for k, v in result.items() if k != "snapshot_sha256"}
    )
    with pytest.raises(ValueError):
        snapshot.assert_snapshot(root, result)


def test_bundle_copies_nested_inputs_with_zero_repair_budget(tmp_path):
    source = draft(tmp_path)
    (source / "docs").mkdir()
    (source / "docs" / "extra.md").write_bytes(b"raw\x00bytes")
    output = tmp_path / "output"
    checksum = bundle.freeze_bundle(source, output, task_id="regression", baseline_commit="a" * 40)
    assert (output / "docs" / "extra.md").read_bytes() == b"raw\x00bytes"
    assert "docs/extra.md" in bundle.verify_bundle(output, checksum)["files"]
    (output / "extra-dir").mkdir()
    with pytest.raises(ValueError, match="directories"):
        bundle.verify_bundle(output, checksum)


def test_bundle_source_mutation_is_rejected_and_only_own_output_removed(tmp_path, monkeypatch):
    source = draft(tmp_path)
    original = bundle._sha256_bytes

    def digest(data):
        if data == b"requirements":
            (source / "requirements.md").write_text("changed")
        return original(data)

    monkeypatch.setattr(bundle, "_sha256_bytes", digest)
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="source changed"):
        bundle.freeze_bundle(source, output, task_id="regression", baseline_commit="a" * 40)
    assert not output.exists()


def test_concurrent_output_claim_not_overwritten(tmp_path, monkeypatch):
    source = draft(tmp_path)
    output = tmp_path / "output"
    original = Path.mkdir

    def mkdir(self, *args, **kwargs):
        if self == output and not self.exists():
            original(self)
            (self / "other-writer").write_text("preserve")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mkdir)
    with pytest.raises(ValueError, match="exist"):
        bundle.freeze_bundle(source, output, task_id="regression", baseline_commit="a" * 40)
    assert (output / "other-writer").read_text() == "preserve"


@pytest.mark.parametrize("suffix", ["", "-journal", "-wal", "-shm"])
@pytest.mark.parametrize("kind", ["hardlink", "dangling"])
def test_sqlite_rejects_unsafe_sidecars_before_connect(tmp_path, monkeypatch, suffix, kind):
    db = tmp_path / "db"
    sidecar = Path(str(db) + suffix)
    if kind == "hardlink":
        target = tmp_path / "outside"
        target.write_text("preserve")
        os.link(target, sidecar)
    else:
        sidecar.symlink_to(tmp_path / "missing")
    monkeypatch.setattr("sqlite3.connect", lambda *a, **k: pytest.fail("SQLite opened unsafe path"))
    with pytest.raises(ValueError):
        IntentStore(db)
    if kind == "hardlink":
        assert target.read_text() == "preserve"


def test_sqlite_ancestor_link_rejected(tmp_path):
    actual = tmp_path / "actual"
    actual.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(actual)
    with pytest.raises(ValueError):
        IntentStore(link / "db")
    assert list(actual.iterdir()) == []


def test_special_bundle_input_rejected_without_blocking(tmp_path):
    source = draft(tmp_path)
    os.mkfifo(source / "pipe")
    with pytest.raises(ValueError):
        bundle.freeze_bundle(
            source, tmp_path / "output", task_id="regression", baseline_commit="a" * 40
        )


@pytest.mark.parametrize("operation", ["reserve", "complete", "unknown"])
@pytest.mark.parametrize("error", [RuntimeError, sqlite3.OperationalError])
def test_transaction_commit_failure_rolls_back(tmp_path, operation, error):
    db = tmp_path / "rollback.db"
    store = IntentStore(db)
    bindings = dict(
        task_id="t",
        run_id="r",
        attempt_id="a",
        kind="verification",
        bundle_sha256="a" * 64,
        snapshot_sha256="b" * 64,
    )
    if operation != "reserve":
        store.reserve("op", **bindings)
    real = store._conn

    class Failure:
        def execute(self, sql, *args):
            if sql == "COMMIT":
                raise error("injected before commit")
            return real.execute(sql, *args)

        def close(self):
            real.close()

    store._conn = Failure()
    try:
        with pytest.raises(error):
            if operation == "reserve":
                store.reserve("op", **bindings)
            elif operation == "complete":
                store.complete(
                    "op",
                    attempt_id="a",
                    bundle_sha256="a" * 64,
                    snapshot_sha256="b" * 64,
                    evidence_sha256="c" * 64,
                )
            else:
                store.mark_unknown("op")
    finally:
        store.close()
    with IntentStore(db) as reopened:
        record = reopened.get("op")
        if operation == "reserve":
            assert record is None
        else:
            assert record["status"] == "pending" and record["evidence_sha256"] is None


@pytest.mark.parametrize("file,value", [("task.json", True), ("verification.json", True)])
def test_boolean_schema_version_rejected(tmp_path, file, value):
    source = draft(tmp_path)
    content = json.loads((source / file).read_text())
    content["schema_version"] = value
    (source / file).write_text(json.dumps(content))
    with pytest.raises(ValueError):
        bundle.freeze_bundle(
            source, tmp_path / "output", task_id="regression", baseline_commit="a" * 40
        )


def test_trusted_manifest_missing_task_rejected(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    raw = bundle._build_manifest_bytes(task_id="regression", baseline_commit="a" * 40, files={})
    (root / "manifest.json").write_bytes(raw)
    with pytest.raises(ValueError, match="required"):
        bundle.verify_bundle(root, hashlib.sha256(raw).hexdigest())
