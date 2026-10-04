"""Unit tests for core.events.EventRecorder."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from supervisor.core.events import EventRecorder

_BASE_KWARGS = {
    "task_id": "M0-unit",
    "run_id": "unit-run",
    "worker_id": "unit-worker",
}


class TestEventValidation:
    """EventRecorder rejects unknown event types and unsafe metadata."""

    def test_unknown_event_type_raises(self):
        recorder = EventRecorder(**_BASE_KWARGS)
        with pytest.raises(ValueError, match="unknown event type"):
            recorder.record("not-a-real-type")

    def test_does_not_accept_raw_prompt_or_transcript(self):
        recorder = EventRecorder(**_BASE_KWARGS)
        # Recorder has no raw_prompt or transcript parameter - signature enforces it
        import inspect

        params = inspect.signature(recorder.record).parameters
        assert "raw_prompt" not in params
        assert "transcript" not in params
        assert "env" not in params


class TestSequence:
    def test_sequences_are_continuous_from_one(self):
        recorder = EventRecorder(**_BASE_KWARGS)
        seen = [recorder.record("AgentStarted")["sequence"] for _ in range(5)]
        assert seen == [1, 2, 3, 4, 5]

    def test_concurrent_records_keep_unique_sequences(self):
        recorder = EventRecorder(**_BASE_KWARGS)
        with ThreadPoolExecutor(max_workers=8) as pool:
            events = list(pool.map(lambda _: recorder.record("AgentStarted"), range(64)))
        sequences = sorted(e["sequence"] for e in events)
        assert sequences == list(range(1, 65))
        assert len({e["event_id"] for e in events}) == 64


class TestMetadata:
    def test_event_carries_required_fields(self):
        recorder = EventRecorder(**_BASE_KWARGS, provider="mock", model="gpt-x")
        event = recorder.record("AgentStarted", attempt_id="a-1", message="hi")
        for key in (
            "schema_version",
            "event_id",
            "run_id",
            "task_id",
            "attempt_id",
            "sequence",
            "timestamp",
            "type",
            "worker_id",
            "provider",
            "model",
            "session_id",
            "data",
        ):
            assert key in event
        assert event["task_id"] == _BASE_KWARGS["task_id"]
        assert event["run_id"] == _BASE_KWARGS["run_id"]
        assert event["worker_id"] == _BASE_KWARGS["worker_id"]
        assert event["attempt_id"] == "a-1"
        assert event["data"]["message"] == "hi"
        assert event["data"]["artifact_sha256"] is None
        assert event["provider"] == "mock"
        assert event["model"] == "gpt-x"

    def test_artifact_sha256_in_data(self):
        recorder = EventRecorder(**_BASE_KWARGS)
        event = recorder.record("FileChanged", artifact_sha256="a" * 64)
        assert event["data"]["artifact_sha256"] == "a" * 64


class TestEventTypeEnum:
    """Only documented event types accepted."""

    @pytest.mark.parametrize(
        "name",
        [
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
        ],
    )
    def test_valid_event_type_accepted(self, name):
        recorder = EventRecorder(**_BASE_KWARGS)
        event = recorder.record(name)
        assert event["type"] == name
