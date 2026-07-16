"""Durable append-only events for agent runtime runs."""

import json
import os
import threading
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from maestro.runtime.models import RunPath, RunRecord, RunStatus
from maestro.runtime.store import ArtifactRef, is_reproducible_artifact_ref


class JournalCorruption(ValueError):
    """A JSONL journal line could not be decoded as a journal event."""

    def __init__(self, line_number: int) -> None:
        super().__init__(f"journal corruption at line {line_number}")
        self.line_number = line_number


class JournalEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    sequence: int = Field(default=0, ge=0)
    type: str = Field(pattern=r"^[a-z][a-z0-9_.-]+$")
    data: dict[str, object] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class JsonlJournal:
    """A per-process locked, fsynced JSONL journal."""

    _locks: dict[Path, threading.Lock] = {}
    _locks_guard = threading.Lock()

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        with self._locks_guard:
            self._lock = self._locks.setdefault(self.path.resolve(), threading.Lock())

    def append(self, event: JournalEvent) -> JournalEvent:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            sequence = self._next_sequence(event.run_id)
            appended = event.model_copy(update={"sequence": sequence})
            payload = (appended.model_dump_json() + "\n").encode("utf-8")
            fd = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
            try:
                written = os.write(fd, payload)
                if written != len(payload):
                    raise OSError("incomplete journal write")
                os.fsync(fd)
            finally:
                os.close(fd)
        return appended

    def read(self, run_id: str) -> list[JournalEvent]:
        if not self.path.exists():
            return []
        with self._lock:
            events = self._read_all()
        return [event for event in events if event.run_id == run_id]

    def _next_sequence(self, run_id: str) -> int:
        sequences = [
            event.sequence for event in self._read_all() if event.run_id == run_id
        ]
        return max(sequences, default=-1) + 1

    def _read_all(self) -> list[JournalEvent]:
        if not self.path.exists():
            return []
        events: list[JournalEvent] = []
        with self.path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                try:
                    decoded = json.loads(line)
                    events.append(JournalEvent.model_validate(decoded))
                except (json.JSONDecodeError, ValidationError, TypeError) as error:
                    raise JournalCorruption(line_number) from error
        return events


def replay_run(events: Iterable[JournalEvent]) -> RunRecord:
    """Rebuild the limited Task 2 run lifecycle without side effects."""
    ordered = list(events)
    if not ordered:
        raise ValueError("missing run.created")

    run_id = ordered[0].run_id
    for expected_sequence, event in enumerate(ordered):
        if event.run_id != run_id:
            raise ValueError("events must belong to one run")
        if event.sequence != expected_sequence:
            raise ValueError("event sequences must be continuous and non-decreasing")

    run: RunRecord | None = None
    pending_upgrade: dict[str, object] | None = None
    for event in ordered:
        if event.type == "run.created":
            if run is not None:
                raise ValueError("run.created must be the first event")
            objective = event.data.get("objective")
            if not isinstance(objective, str) or not objective:
                raise ValueError("run.created requires objective")
            event_run_id = event.data.get("run_id", event.run_id)
            if event_run_id != event.run_id:
                raise ValueError("run.created run_id must match the event")
            run = RunRecord(
                run_id=event.run_id,
                objective=objective,
                created_at=event.occurred_at,
                updated_at=event.occurred_at,
            )
        elif event.type == "run.path_selected":
            if run is None:
                raise ValueError("run.path_selected requires run.created")
            if (
                run.status is not RunStatus.CREATED
                or run.path is not RunPath.UNSELECTED
                or pending_upgrade is not None
            ):
                raise ValueError("run.path_selected requires an unselected run")
            path = event.data.get("path")
            try:
                selected_path = RunPath(path)
            except (TypeError, ValueError) as error:
                raise ValueError("run.path_selected requires a valid path") from error
            if selected_path not in {RunPath.FAST, RunPath.STRUCTURED}:
                raise ValueError("run.path_selected requires a selected path")
            run = run.model_copy(
                update={
                    "path": selected_path,
                    "status": (
                        RunStatus.RUNNING_FAST
                        if selected_path is RunPath.FAST
                        else RunStatus.STRUCTURING
                    ),
                    "updated_at": event.occurred_at,
                }
            )
        elif event.type == "run.controlled_started":
            if run is None or run.status is not RunStatus.STRUCTURING:
                raise ValueError("run.controlled_started requires structuring")
            run = run.model_copy(
                update={"status": RunStatus.RUNNING_STRUCTURED, "updated_at": event.occurred_at}
            )
        elif event.type == "run.path_upgraded":
            if run is None or run.path is not RunPath.FAST or run.status is not RunStatus.RUNNING_FAST:
                raise ValueError("run.path_upgraded requires a fast run")
            _upgrade_data(event)
            run = run.model_copy(
                update={
                    "path": RunPath.STRUCTURED,
                    "status": RunStatus.RUNNING_STRUCTURED,
                    "updated_at": event.occurred_at,
                }
            )
        elif event.type == "run.completed":
            if run is None:
                raise ValueError("run.completed requires run.created")
            if pending_upgrade is not None:
                raise ValueError("run.completed cannot interrupt upgrade")
            if run.status is RunStatus.COMPLETED:
                raise ValueError("run.completed cannot occur twice")
            final_text = event.data.get("final_text")
            if final_text is not None and not isinstance(final_text, str):
                raise ValueError("run.completed final_text must be a string")
            run = run.model_copy(
                update={
                    "status": RunStatus.COMPLETED,
                    "final_text": final_text,
                    "updated_at": event.occurred_at,
                }
            )
        elif event.type == "run.upgrading":
            if run is None:
                raise ValueError("run.upgrading requires run.created")
            if (
                run.path is not RunPath.FAST
                or run.status is RunStatus.COMPLETED
                or pending_upgrade is not None
            ):
                raise ValueError("run.upgrading requires a fast run")
            pending_upgrade = _upgrade_data(event)
            run = run.model_copy(
                update={
                    "path": RunPath.STRUCTURED,
                    "status": RunStatus.STRUCTURING,
                    "updated_at": event.occurred_at,
                }
            )
        elif event.type == "run.upgraded":
            if (
                run is None
                or pending_upgrade is None
                or run.status is not RunStatus.STRUCTURING
            ):
                raise ValueError("run.upgraded requires run.upgrading")
            if _upgrade_data(event) != pending_upgrade:
                raise ValueError("run.upgraded must preserve upgrade data")
            run = run.model_copy(
                update={
                    "status": RunStatus.RUNNING_STRUCTURED,
                    "updated_at": event.occurred_at,
                }
            )
            pending_upgrade = None
        elif event.type in {
            "model.turn",
            "capability.completed",
            "artifact.created",
            "child_run.created",
            "child_run.completed",
        }:
            if run is None:
                raise ValueError(f"{event.type} requires run.created")
        else:
            raise ValueError(f"unknown journal event: {event.type}")

    if run is None:
        raise ValueError("missing run.created")
    return run


def _upgrade_data(event: JournalEvent) -> dict[str, object]:
    reason = event.data.get("reason")
    artifacts = event.data.get("artifact_working_set")
    if not isinstance(reason, str) or not reason:
        raise ValueError(f"{event.type} requires a reason")
    if not isinstance(artifacts, list):
        raise ValueError(f"{event.type} requires an artifact working set")
    try:
        frozen_artifacts = [
            ArtifactRef.model_validate(artifact).model_dump() for artifact in artifacts
        ]
    except ValidationError as error:
        raise ValueError(f"{event.type} requires valid artifact references") from error
    references = [ArtifactRef.model_validate(artifact) for artifact in frozen_artifacts]
    if not all(is_reproducible_artifact_ref(ref) for ref in references):
        raise ValueError(f"{event.type} requires valid artifact references")
    return {"reason": reason, "artifact_working_set": frozen_artifacts}
