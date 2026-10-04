"""Event recording with unique sequences and metadata validation."""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime

VALID_EVENT_TYPES = {
    "RunStarted",
    "AgentStarted",
    "ToolCalled",
    "FileChanged",
    "CommandExecuted",
    "AgentCompleted",
    "ReviewStarted",
    "FindingCreated",
    "RepairStarted",
    "VerificationCompleted",
    "RunCompleted",
    "RunInterrupted",
}


class EventRecorder:
    """Record supervisor events with unique IDs and continuous sequences."""

    def __init__(
        self,
        task_id: str,
        run_id: str,
        worker_id: str,
        provider: str | None = None,
        model: str | None = None,
        session_id: str | None = None,
    ):
        self.task_id = task_id
        self.run_id = run_id
        self.worker_id = worker_id
        self.provider = provider
        self.model = model
        self.session_id = session_id
        self._sequence = 0
        self._lock = threading.Lock()

    def record(
        self,
        event_type: str,
        *,
        attempt_id: str | None = None,
        message: str = "",
        artifact_sha256: str | None = None,
    ) -> dict:
        """Record an event and return the event dict.

        Args:
            event_type: Type of event (e.g., "AgentStarted")
            attempt_id: Optional attempt identifier
            message: Optional message
            artifact_sha256: Optional artifact hash

        Returns:
            Event dict satisfying event schema v1
        """
        # Validate event type
        if event_type not in VALID_EVENT_TYPES:
            raise ValueError(f"unknown event type: {event_type}")

        with self._lock:
            self._sequence += 1
            seq = self._sequence

        event_id = str(uuid.uuid4())
        timestamp = datetime.now(UTC).isoformat()

        event = {
            "schema_version": 1,
            "event_id": event_id,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "attempt_id": attempt_id,
            "sequence": seq,
            "timestamp": timestamp,
            "type": event_type,
            "worker_id": self.worker_id,
            "provider": self.provider,
            "model": self.model,
            "session_id": self.session_id,
            "data": {
                "message": message,
                "artifact_sha256": artifact_sha256,
            },
        }

        return event
