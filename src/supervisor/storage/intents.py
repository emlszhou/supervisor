"""M1 durable intent ledger.

`IntentStore` records the lifecycle of a single operation against a
frozen task bundle and a workspace snapshot:

    reserve  →  complete  (or mark_unknown)

The store is strictly local SQLite. It never launches processes, never
opens the network, never persists prompts/tokens/env, and never derives
external side effects from its state. Multiple `IntentStore` instances
on the same database file are safe to open concurrently; the same
operation_id will be committed by exactly one transaction even under
contention.

All identifiers and digests are validated against the contract:
- operation_id / task_id / run_id / attempt_id: ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$
- bundle_sha256 / snapshot_sha256 / evidence_sha256: 64 lowercase hex

Trust boundary: the caller's `reserve`/`complete` arguments are trusted
for *content* (this is the whole point of the ledger), but their *shape*
must match the contract. Invalid shapes raise ValueError without
mutating state.
"""

from __future__ import annotations

import re
import sqlite3
import stat
import time
from pathlib import Path
from typing import Any

# Pattern per contract: ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
# Per contract: 64 lowercase hex.
_SHA64_RE = re.compile(r"^[a-f0-9]{64}$")
_VALID_KINDS = ("agent_execute", "verification")
_VALID_STATUSES = ("pending", "completed", "unknown")


def _check_id(name: str, value: Any) -> None:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ValueError(f"{name} must match ^[A-Za-z0-9][A-Za-z0-9._-]{{0,63}}$")


def _check_sha(name: str, value: Any) -> None:
    if not isinstance(value, str) or not _SHA64_RE.fullmatch(value):
        raise ValueError(f"{name} must be 64 lowercase hex characters")


class IntentStore:
    """Durable single-row-per-operation ledger backed by SQLite.

    The constructor does not create or migrate any extra database files.
    Closing the store does not delete the database; reopening the same
    path recovers all records.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._check_path(self._path)
        # isolation_level=None puts sqlite3 in autocommit mode for the
        # multi-statement BEGIN IMMEDIATE transactions below; this keeps
        # each reserve/complete atomic without depending on python-level
        # context managers that might be left half-committed on exception.
        # Pre-open safety: refuse any DB / sidecar / sidecar-ancestor
        # that is a symlink, has nlink>1 on a regular file, or escapes
        # via an ancestor link. Doing this BEFORE sqlite3.connect means
        # the database engine never touches a path we have not first
        # classified as safe.
        for suffix in ("", "-wal", "-shm", "-journal"):
            sidecar = Path(str(self._path) + suffix)
            self._check_name_chain(sidecar, suffix=suffix)
        self._conn = sqlite3.connect(
            str(self._path),
            timeout=30.0,
            isolation_level=None,
            check_same_thread=False,
        )
        # Pragmas: WAL gives concurrent readers + single writer; foreign
        # keys / busy_timeout provide the contract's "no silent loss"
        # guarantee without leaking partial state on conflict.
        # The PRAGMA journal_mode = WAL write is itself a write that
        # acquires the writer lock; multiple connections initialising in
        # parallel can race here on macOS/Linux even with busy_timeout
        # set. Retry with exponential backoff until the pragma lands.
        deadline = time.monotonic() + 5.0
        delay = 0.005
        while True:
            try:
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA synchronous=FULL")
                self._conn.execute("PRAGMA foreign_keys=ON")
                self._conn.execute("PRAGMA busy_timeout=30000")
                break
            except sqlite3.OperationalError as e:
                if "locked" not in str(e).lower() or time.monotonic() >= deadline:
                    self._safe_close()
                    raise
                time.sleep(delay)
                delay = min(delay * 2, 0.1)
        try:
            self._create_schema()
        except BaseException:
            self._safe_close()
            raise

    @staticmethod
    def _check_path(path: Path) -> None:
        from supervisor.workspace.snapshot import _check_ancestors

        _check_ancestors(path)

    def _check_name_chain(self, sidecar: Path, *, suffix: str = "") -> None:
        from supervisor.workspace.snapshot import _check_ancestors

        _check_ancestors(sidecar)
        try:
            st = sidecar.lstat()
        except FileNotFoundError:
            return
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            raise ValueError(f"DB or sidecar must be an unlinked regular file: {sidecar}")

    def _safe_close(self) -> None:
        conn = getattr(self, "_conn", None)
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass

    def _create_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS intents (
                operation_id TEXT PRIMARY KEY,
                task_id      TEXT NOT NULL,
                run_id       TEXT NOT NULL,
                attempt_id   TEXT NOT NULL,
                kind         TEXT NOT NULL,
                bundle_sha256    TEXT NOT NULL,
                snapshot_sha256  TEXT NOT NULL,
                status       TEXT NOT NULL,
                evidence_sha256  TEXT
            );
            CREATE TABLE IF NOT EXISTS intent_history (
                operation_id TEXT NOT NULL,
                status       TEXT NOT NULL,
                evidence_sha256 TEXT,
                ts           REAL NOT NULL DEFAULT (julianday('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_history_op
                ON intent_history(operation_id, ts);
            """
        )

    # ---------- Public API ----------

    def reserve(
        self,
        operation_id: str,
        *,
        task_id: str,
        run_id: str,
        attempt_id: str,
        kind: str,
        bundle_sha256: str,
        snapshot_sha256: str,
    ) -> dict:
        """Idempotently insert a pending intent. Re-binding an existing
        intent with *different* parameters raises ValueError without
        mutating the row."""
        _check_id("operation_id", operation_id)
        _check_id("task_id", task_id)
        _check_id("run_id", run_id)
        _check_id("attempt_id", attempt_id)
        if kind not in _VALID_KINDS:
            raise ValueError(f"kind must be one of {_VALID_KINDS}")
        _check_sha("bundle_sha256", bundle_sha256)
        _check_sha("snapshot_sha256", snapshot_sha256)

        # Serialise critical section: BEGIN IMMEDIATE acquires the writer
        # lock. Any concurrent transaction trying to insert the same
        # operation_id will see UNIQUE constraint or our prior row.
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            existing = self._conn.execute(
                "SELECT task_id, run_id, attempt_id, kind, bundle_sha256, "
                "snapshot_sha256, status, evidence_sha256 "
                "FROM intents WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            if existing is not None:
                existing_bindings = existing[:6]
                new_bindings = (
                    task_id,
                    run_id,
                    attempt_id,
                    kind,
                    bundle_sha256,
                    snapshot_sha256,
                )
                if existing_bindings != new_bindings:
                    self._conn.execute("ROLLBACK")
                    raise ValueError(
                        f"operation {operation_id!r} already bound with different params"
                    )
                # Idempotent: return the existing record. Completed/unknown
                # intents remain in their final state.
                record = self._row_to_record(operation_id, existing)
                self._conn.execute("COMMIT")
                return record
            self._conn.execute(
                "INSERT INTO intents(operation_id, task_id, run_id, attempt_id, "
                "kind, bundle_sha256, snapshot_sha256, status, evidence_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', NULL)",
                (
                    operation_id,
                    task_id,
                    run_id,
                    attempt_id,
                    kind,
                    bundle_sha256,
                    snapshot_sha256,
                ),
            )
            self._conn.execute(
                "INSERT INTO intent_history(operation_id, status, evidence_sha256) "
                "VALUES (?, 'pending', NULL)",
                (operation_id,),
            )
            self._conn.execute("COMMIT")
        except BaseException:
            try:
                self._conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        return self._row_to_record(
            operation_id,
            (
                task_id,
                run_id,
                attempt_id,
                kind,
                bundle_sha256,
                snapshot_sha256,
                "pending",
                None,
            ),
        )

    def complete(
        self,
        operation_id: str,
        *,
        attempt_id: str,
        bundle_sha256: str,
        snapshot_sha256: str,
        evidence_sha256: str,
    ) -> dict:
        """Mark an existing intent completed. The (attempt_id, bundle_sha256,
        snapshot_sha256) binding must match the reservation exactly. Once
        completed, the evidence is durable."""
        _check_id("operation_id", operation_id)
        _check_id("attempt_id", attempt_id)
        _check_sha("bundle_sha256", bundle_sha256)
        _check_sha("snapshot_sha256", snapshot_sha256)
        _check_sha("evidence_sha256", evidence_sha256)

        try:
            self._conn.execute("BEGIN IMMEDIATE")
            row = self._conn.execute(
                "SELECT task_id, run_id, attempt_id, kind, bundle_sha256, "
                "snapshot_sha256, status, evidence_sha256 "
                "FROM intents WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            if row is None:
                self._conn.execute("ROLLBACK")
                raise ValueError(f"operation not found: {operation_id!r}")
            existing_bindings = row[:6]
            # task_id is fixed at reserve time; only attempt_id, bundle, snapshot are verified here.
            new_bindings_full = (
                row[0],
                row[1],
                attempt_id,
                row[3],
                bundle_sha256,
                snapshot_sha256,
            )
            if existing_bindings != new_bindings_full:
                self._conn.execute("ROLLBACK")
                raise ValueError(f"complete({operation_id!r}) bindings do not match reservation")
            status = row[6]
            evidence = row[7]
            if status == "completed":
                if evidence == evidence_sha256:
                    record = self._row_to_record(operation_id, row)
                    self._conn.execute("COMMIT")
                    return record
                self._conn.execute("ROLLBACK")
                raise ValueError(
                    f"complete({operation_id!r}) evidence conflict: already completed "
                    f"with a different digest"
                )
            # status == "pending" or "unknown": both can transition to completed.
            self._conn.execute(
                "UPDATE intents SET status='completed', evidence_sha256=? WHERE operation_id=?",
                (evidence_sha256, operation_id),
            )
            self._conn.execute(
                "INSERT INTO intent_history(operation_id, status, evidence_sha256) "
                "VALUES (?, 'completed', ?)",
                (operation_id, evidence_sha256),
            )
            self._conn.execute("COMMIT")
        except BaseException:
            try:
                self._conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        return self.get(operation_id)

    def mark_unknown(self, operation_id: str) -> dict:
        """Transition a pending intent to 'unknown'. Already-unknown intents
        are idempotent. Completed intents cannot be downgraded."""
        _check_id("operation_id", operation_id)
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            row = self._conn.execute(
                "SELECT task_id, run_id, attempt_id, kind, bundle_sha256, "
                "snapshot_sha256, status, evidence_sha256 "
                "FROM intents WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            if row is None:
                self._conn.execute("ROLLBACK")
                raise ValueError(f"operation not found: {operation_id!r}")
            status = row[6]
            if status == "completed":
                self._conn.execute("ROLLBACK")
                raise ValueError(
                    f"mark_unknown({operation_id!r}) refused: intent already completed"
                )
            if status == "unknown":
                record = self._row_to_record(operation_id, row)
                self._conn.execute("COMMIT")
                return record
            self._conn.execute(
                "UPDATE intents SET status='unknown' WHERE operation_id=?",
                (operation_id,),
            )
            self._conn.execute(
                "INSERT INTO intent_history(operation_id, status, evidence_sha256) "
                "VALUES (?, 'unknown', NULL)",
                (operation_id,),
            )
            self._conn.execute("COMMIT")
        except BaseException:
            try:
                self._conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        return self.get(operation_id)

    def get(self, operation_id: str) -> dict | None:
        _check_id("operation_id", operation_id)
        row = self._conn.execute(
            "SELECT task_id, run_id, attempt_id, kind, bundle_sha256, "
            "snapshot_sha256, status, evidence_sha256 "
            "FROM intents WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_record(operation_id, row)

    def close(self) -> None:
        self._safe_close()

    # ---------- Internal helpers ----------

    def _row_to_record(self, operation_id: str, row: tuple) -> dict:
        return {
            "operation_id": operation_id,
            "task_id": row[0],
            "run_id": row[1],
            "attempt_id": row[2],
            "kind": row[3],
            "bundle_sha256": row[4],
            "snapshot_sha256": row[5],
            "status": row[6],
            "evidence_sha256": row[7],
        }

    # Context-manager sugar (not required by the contract).
    def __enter__(self) -> IntentStore:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()
