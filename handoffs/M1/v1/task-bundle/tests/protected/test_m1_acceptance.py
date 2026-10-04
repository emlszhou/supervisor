"""Frozen independent M1 API acceptance; no missing implementation skips."""

import hashlib
import importlib
import importlib.util
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def module(name):
    qualified = "supervisor." + name
    assert importlib.util.find_spec(qualified) is not None, f"M1 not implemented: {qualified}"
    return importlib.import_module(qualified)


def git(root, *args):
    return (
        subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE)
        .decode()
        .strip()
    )


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "M1 fixture")
    git(root, "config", "user.email", "m1@example.invalid")
    (root / "a.txt").write_text("baseline")
    git(root, "add", "a.txt")
    git(root, "commit", "-qm", "fixture")
    return root, git(root, "rev-parse", "HEAD")


def source(tmp_path):
    root = tmp_path / "input"
    root.mkdir()
    task = json.loads((ROOT / "task.json").read_text())
    task.update(status="draft", baseline_commit=None)
    (root / "task.json").write_text(json.dumps(task))
    for name in [
        "requirements.md",
        "allowed_files.json",
        "forbidden_files.json",
        "verification.json",
    ]:
        (root / name).write_bytes((ROOT / name).read_bytes())
    return root, task["task_id"]


def capture(root, base):
    return module("workspace.snapshot").capture_snapshot(root, baseline_commit=base)


def canonical(snapshot):
    fields = {k: v for k, v in snapshot.items() if k != "snapshot_sha256"}
    return hashlib.sha256(
        json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def test_clean_baseline(repo):
    root, base = repo
    assert module("workspace.baseline").inspect_baseline(root) == base


@pytest.mark.parametrize("kind", ["edit", "staged", "untracked", "ignored"])
def test_baseline_rejects_nonclean(repo, kind):
    m = module("workspace.baseline")
    root, _ = repo
    if kind in ("edit", "staged"):
        (root / "a.txt").write_text("changed")
        if kind == "staged":
            git(root, "add", "a.txt")
    else:
        if kind == "ignored":
            (root / ".gitignore").write_text("secret.txt\n")
            git(root, "add", ".gitignore")
            git(root, "commit", "-qm", "ignore")
        (root / "secret.txt").write_text("fixture")
    with pytest.raises(ValueError):
        m.inspect_baseline(root)


def test_unborn_baseline_rejected(tmp_path):
    m = module("workspace.baseline")
    git(tmp_path, "init", "-q")
    with pytest.raises(ValueError):
        m.inspect_baseline(tmp_path)


def test_snapshot_deterministic_and_digest(repo):
    root, base = repo
    s = capture(root, base)
    assert set(s) == {"schema_version", "baseline_commit", "files", "deleted", "snapshot_sha256"}
    assert s == capture(root, base)
    assert s["snapshot_sha256"] == canonical(s)
    assert s["files"] == [
        dict(path="a.txt", mode="100644", sha256=hashlib.sha256(b"baseline").hexdigest())
    ]
    assert s["deleted"] == []


@pytest.mark.parametrize("change", ["edit", "delete", "untracked", "mode"])
def test_snapshot_tracks_changes_and_rejects_stale(repo, change):
    root, base = repo
    m = module("workspace.snapshot")
    before = capture(root, base)
    if change == "edit":
        (root / "a.txt").write_text("new")
    elif change == "delete":
        (root / "a.txt").unlink()
    elif change == "untracked":
        (root / "new.txt").write_text("new")
    else:
        (root / "a.txt").chmod(0o755)
    after = capture(root, base)
    assert after["snapshot_sha256"] != before["snapshot_sha256"]
    if change == "delete":
        assert after["deleted"] == ["a.txt"]
    with pytest.raises(ValueError):
        m.assert_snapshot(root, before)
    m.assert_snapshot(root, after)


def test_snapshot_rejects_forged_digest(repo):
    root, base = repo
    m = module("workspace.snapshot")
    s = capture(root, base)
    s["snapshot_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        m.assert_snapshot(root, s)


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "case"])
def test_snapshot_rejects_links_and_case_collision(repo, kind):
    m = module("workspace.snapshot")
    root, base = repo
    if kind == "symlink":
        (root / "link").symlink_to(root / "a.txt")
    elif kind == "hardlink":
        os.link(root / "a.txt", root / "link")
    else:
        (root / "A.txt").write_text("collision")
    with pytest.raises(ValueError):
        m.capture_snapshot(root, baseline_commit=base)


def test_freeze_and_verify_source_unchanged(tmp_path):
    m = module("workspace.bundle")
    src, identity = source(tmp_path)
    out = tmp_path / "frozen"
    before = (src / "task.json").read_bytes()
    checksum = m.freeze_bundle(src, out, task_id=identity, baseline_commit="a" * 40)
    manifest = m.verify_bundle(out, checksum)
    assert (src / "task.json").read_bytes() == before
    task = json.loads((out / "task.json").read_text())
    assert task["status"] == "frozen"
    assert task["baseline_commit"] == "a" * 40
    assert manifest["task_id"] == identity
    assert hashlib.sha256((out / "manifest.json").read_bytes()).hexdigest() == checksum
    assert not ((out / "task.json").stat().st_mode & 0o222)


@pytest.mark.parametrize("mutation", ["edit", "extra", "missing", "bad_digest"])
def test_bundle_tamper_rejected(tmp_path, mutation):
    m = module("workspace.bundle")
    src, identity = source(tmp_path)
    out = tmp_path / "frozen"
    checksum = m.freeze_bundle(src, out, task_id=identity, baseline_commit="a" * 40)
    if mutation == "edit":
        (out / "requirements.md").chmod(0o644)
        (out / "requirements.md").write_text("changed")
    elif mutation == "extra":
        (out / "extra").write_text("extra")
    elif mutation == "missing":
        (out / "requirements.md").unlink()
    else:
        checksum = "0" * 64
    with pytest.raises(ValueError):
        m.verify_bundle(out, checksum)


@pytest.mark.parametrize(
    "kind",
    ["existing_output", "source_symlink", "source_hardlink", "case", "wrong_identity", "bad_json"],
)
def test_freeze_invalid_input_does_not_overwrite(tmp_path, kind):
    m = module("workspace.bundle")
    src, identity = source(tmp_path)
    out = tmp_path / "frozen"
    if kind == "existing_output":
        out.mkdir()
        (out / "keep").write_text("retain")
    elif kind == "source_symlink":
        (src / "link").symlink_to(src / "requirements.md")
    elif kind == "source_hardlink":
        os.link(src / "requirements.md", src / "link")
    elif kind == "case":
        (src / "TASK.json").write_text("{}")
    elif kind == "wrong_identity":
        identity = "wrong"
    else:
        (src / "task.json").write_text("{broken")
    with pytest.raises(ValueError):
        m.freeze_bundle(src, out, task_id=identity, baseline_commit="a" * 40)
    if kind == "existing_output":
        assert (out / "keep").read_text() == "retain"


def check(before, after, **changes):
    fields = dict(
        allowed=["a.txt", "tests/**"],
        forbidden=["tests/protected/**"],
        max_changed_files=3,
        max_diff_lines=10,
        diff_lines=1,
    )
    fields.update(changes)
    return module("policy.changes").check_changes(before, after, **fields)


def test_policy_edit_and_deletion(repo):
    root, base = repo
    before = capture(root, base)
    (root / "a.txt").unlink()
    after = capture(root, base)
    assert check(before, after) == dict(changed_files=["a.txt"], changed_count=1, diff_lines=1)


@pytest.mark.parametrize(
    "rule",
    [
        "forbidden",
        "not_allowed",
        "files_budget",
        "lines_budget",
        "bool_budget",
        "bad_pattern",
        "stale_digest",
    ],
)
def test_policy_rejects_invalid_or_overbudget(repo, rule):
    module("policy.changes")
    root, base = repo
    before = capture(root, base)
    (root / "a.txt").write_text("new")
    after = capture(root, base)
    args = {}
    if rule == "forbidden":
        args["forbidden"] = ["a.txt"]
    elif rule == "not_allowed":
        args["allowed"] = ["other.txt"]
    elif rule == "files_budget":
        (root / "b.txt").write_text("new")
        after = capture(root, base)
        args.update(allowed=["*.txt"], max_changed_files=1)
    elif rule == "lines_budget":
        args["diff_lines"] = 11
    elif rule == "bool_budget":
        args["max_changed_files"] = True
    elif rule == "bad_pattern":
        args["allowed"] = ["../*"]
    else:
        after["snapshot_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        check(before, after, **args)


BIND = dict(
    task_id="M1",
    run_id="run",
    attempt_id="attempt",
    kind="agent_execute",
    bundle_sha256="a" * 64,
    snapshot_sha256="b" * 64,
)
COMPLETE = dict(
    attempt_id="attempt", bundle_sha256="a" * 64, snapshot_sha256="b" * 64, evidence_sha256="c" * 64
)


def test_intent_durable_idempotent_and_unknown(tmp_path):
    m = module("storage.intents")
    db = tmp_path / "db.sqlite"
    store = m.IntentStore(db)
    try:
        first = store.reserve("op", **BIND)
        assert first["status"] == "pending"
        assert store.reserve("op", **BIND) == first
        unknown = store.mark_unknown("op")
        assert unknown["status"] == "unknown"
        assert store.reserve("op", **BIND) == unknown
    finally:
        store.close()
    store = m.IntentStore(db)
    try:
        assert store.get("op") == unknown
        completed = store.complete("op", **COMPLETE)
        assert completed["status"] == "completed"
        assert completed["evidence_sha256"] == "c" * 64
        assert store.complete("op", **COMPLETE) == completed
        assert store.reserve("op", **BIND) == completed
        with pytest.raises(ValueError):
            store.mark_unknown("op")
    finally:
        store.close()


@pytest.mark.parametrize("conflict", ["attempt", "bundle", "snapshot", "evidence", "reserve"])
def test_intent_conflicts_leave_record_unchanged(tmp_path, conflict):
    m = module("storage.intents")
    store = m.IntentStore(tmp_path / "db.sqlite")
    try:
        store.reserve("op", **BIND)
        before = store.complete("op", **COMPLETE)
        args = dict(COMPLETE)
        if conflict == "attempt":
            args["attempt_id"] = "other"
        elif conflict == "bundle":
            args["bundle_sha256"] = "d" * 64
        elif conflict == "snapshot":
            args["snapshot_sha256"] = "d" * 64
        else:
            args["evidence_sha256"] = "d" * 64
        with pytest.raises(ValueError):
            if conflict == "reserve":
                store.reserve("op", **{**BIND, "run_id": "other"})
            else:
                store.complete("op", **args)
        assert store.get("op") == before
    finally:
        store.close()


def test_concurrent_reservations_single_durable_intent(tmp_path):
    m = module("storage.intents")
    db = tmp_path / "db.sqlite"

    def reserve(_):
        store = m.IntentStore(db)
        try:
            return store.reserve("op", **BIND)
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(reserve, range(8)))
    assert all(result == results[0] for result in results)


def test_intent_missing_and_invalid_identity(tmp_path):
    m = module("storage.intents")
    store = m.IntentStore(tmp_path / "db.sqlite")
    try:
        assert store.get("absent") is None
        with pytest.raises(ValueError):
            store.complete("absent", **COMPLETE)
        with pytest.raises(ValueError):
            store.reserve("../op", **BIND)
        assert store.get("op") is None
    finally:
        store.close()
