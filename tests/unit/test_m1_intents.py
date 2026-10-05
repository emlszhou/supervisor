"""M1 unit tests for storage.intents.

The frozen acceptance suite covers the lifecycle and concurrency
contract. These unit tests focus on input validation, symlink/hardlink
rejection, and missing-record behaviour.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from supervisor.storage.intents import IntentStore

BIND = dict(
    task_id="M1",
    run_id="run",
    attempt_id="attempt",
    kind="agent_execute",
    bundle_sha256="a" * 64,
    snapshot_sha256="b" * 64,
)


def test_reserve_returns_full_record(tmp_path: Path) -> None:
    db = tmp_path / "i.sqlite"
    store = IntentStore(db)
    try:
        rec = store.reserve("op", **BIND)
        assert rec["status"] == "pending"
        assert rec["evidence_sha256"] is None
        assert rec["operation_id"] == "op"
        assert rec["task_id"] == "M1"
    finally:
        store.close()


def test_get_missing_returns_none(tmp_path: Path) -> None:
    store = IntentStore(tmp_path / "i.sqlite")
    try:
        assert store.get("absent") is None
    finally:
        store.close()


def test_complete_nonexistent_raises(tmp_path: Path) -> None:
    store = IntentStore(tmp_path / "i.sqlite")
    try:
        with pytest.raises(ValueError, match="not found"):
            store.complete(
                "missing",
                attempt_id="x",
                bundle_sha256="a" * 64,
                snapshot_sha256="b" * 64,
                evidence_sha256="c" * 64,
            )
    finally:
        store.close()


def test_mark_unknown_nonexistent_raises(tmp_path: Path) -> None:
    store = IntentStore(tmp_path / "i.sqlite")
    try:
        with pytest.raises(ValueError, match="not found"):
            store.mark_unknown("missing")
    finally:
        store.close()


def test_reserve_rejects_invalid_id_shapes(tmp_path: Path) -> None:
    store = IntentStore(tmp_path / "i.sqlite")
    try:
        for bad in ("../op", "a" * 65, "abc$", "", "-leading-dash", "abc/def"):
            with pytest.raises(ValueError):
                store.reserve(bad, **BIND)
    finally:
        store.close()


def test_reserve_rejects_bad_digest_shape(tmp_path: Path) -> None:
    store = IntentStore(tmp_path / "i.sqlite")
    try:
        bad = dict(BIND, bundle_sha256="not-a-sha")
        with pytest.raises(ValueError):
            store.reserve("op", **bad)
        bad = dict(BIND, snapshot_sha256="z" * 64)  # uppercase
        with pytest.raises(ValueError):
            store.reserve("op", **bad)
    finally:
        store.close()


def test_reserve_rejects_bad_kind(tmp_path: Path) -> None:
    store = IntentStore(tmp_path / "i.sqlite")
    try:
        with pytest.raises(ValueError):
            store.reserve("op", **{**BIND, "kind": "bogus"})
    finally:
        store.close()


def test_reserve_idempotent(tmp_path: Path) -> None:
    store = IntentStore(tmp_path / "i.sqlite")
    try:
        a = store.reserve("op", **BIND)
        b = store.reserve("op", **BIND)
        assert a == b
    finally:
        store.close()


def test_complete_from_pending(tmp_path: Path) -> None:
    store = IntentStore(tmp_path / "i.sqlite")
    try:
        store.reserve("op", **BIND)
        rec = store.complete(
            "op",
            attempt_id="attempt",
            bundle_sha256="a" * 64,
            snapshot_sha256="b" * 64,
            evidence_sha256="c" * 64,
        )
        assert rec["status"] == "completed"
        assert rec["evidence_sha256"] == "c" * 64
    finally:
        store.close()


def test_complete_idempotent_same_evidence(tmp_path: Path) -> None:
    store = IntentStore(tmp_path / "i.sqlite")
    try:
        store.reserve("op", **BIND)
        a = store.complete(
            "op",
            attempt_id="attempt",
            bundle_sha256="a" * 64,
            snapshot_sha256="b" * 64,
            evidence_sha256="c" * 64,
        )
        b = store.complete(
            "op",
            attempt_id="attempt",
            bundle_sha256="a" * 64,
            snapshot_sha256="b" * 64,
            evidence_sha256="c" * 64,
        )
        assert a == b
    finally:
        store.close()


def test_complete_conflicting_evidence_rejected(tmp_path: Path) -> None:
    store = IntentStore(tmp_path / "i.sqlite")
    try:
        store.reserve("op", **BIND)
        store.complete(
            "op",
            attempt_id="attempt",
            bundle_sha256="a" * 64,
            snapshot_sha256="b" * 64,
            evidence_sha256="c" * 64,
        )
        with pytest.raises(ValueError):
            store.complete(
                "op",
                attempt_id="attempt",
                bundle_sha256="a" * 64,
                snapshot_sha256="b" * 64,
                evidence_sha256="d" * 64,
            )
    finally:
        store.close()


def test_mark_unknown_idempotent(tmp_path: Path) -> None:
    store = IntentStore(tmp_path / "i.sqlite")
    try:
        store.reserve("op", **BIND)
        a = store.mark_unknown("op")
        b = store.mark_unknown("op")
        assert a == b
        assert a["status"] == "unknown"
    finally:
        store.close()


def test_mark_unknown_rejects_completed(tmp_path: Path) -> None:
    store = IntentStore(tmp_path / "i.sqlite")
    try:
        store.reserve("op", **BIND)
        store.complete(
            "op",
            attempt_id="attempt",
            bundle_sha256="a" * 64,
            snapshot_sha256="b" * 64,
            evidence_sha256="c" * 64,
        )
        with pytest.raises(ValueError, match="already completed"):
            store.mark_unknown("op")
    finally:
        store.close()


def test_complete_from_unknown_allowed(tmp_path: Path) -> None:
    store = IntentStore(tmp_path / "i.sqlite")
    try:
        store.reserve("op", **BIND)
        store.mark_unknown("op")
        rec = store.complete(
            "op",
            attempt_id="attempt",
            bundle_sha256="a" * 64,
            snapshot_sha256="b" * 64,
            evidence_sha256="c" * 64,
        )
        assert rec["status"] == "completed"
    finally:
        store.close()


def test_close_then_reopen_preserves_state(tmp_path: Path) -> None:
    db = tmp_path / "i.sqlite"
    store = IntentStore(db)
    try:
        store.reserve("op", **BIND)
    finally:
        store.close()
    store = IntentStore(db)
    try:
        rec = store.get("op")
        assert rec is not None
        assert rec["status"] == "pending"
    finally:
        store.close()


def test_symlinked_db_path_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real.sqlite"
    real.write_bytes(b"")
    link = tmp_path / "linked.sqlite"
    if link.exists() or link.is_symlink():
        link.unlink()
    os.symlink(real, link)
    try:
        with pytest.raises(ValueError, match="symlink"):
            IntentStore(link)
    finally:
        link.unlink()


def test_hardlinked_db_path_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real.sqlite"
    real.write_bytes(b"")
    hard = tmp_path / "hard.sqlite"
    if hard.exists():
        hard.unlink()
    os.link(real, hard)
    try:
        with pytest.raises(ValueError, match="hardlink"):
            IntentStore(hard)
    finally:
        if hard.exists():
            hard.unlink()


def test_reserve_after_complete_returns_completed(tmp_path: Path) -> None:
    store = IntentStore(tmp_path / "i.sqlite")
    try:
        store.reserve("op", **BIND)
        store.complete(
            "op",
            attempt_id="attempt",
            bundle_sha256="a" * 64,
            snapshot_sha256="b" * 64,
            evidence_sha256="c" * 64,
        )
        rec = store.reserve("op", **BIND)
        assert rec["status"] == "completed"
        assert rec["evidence_sha256"] == "c" * 64
    finally:
        store.close()
