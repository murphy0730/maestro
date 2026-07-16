from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from maestro.runtime.journal import JournalEvent, JsonlJournal


class RunEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    sequence: int = 0
    type: str
    data: dict[str, object] = Field(default_factory=dict)
    occurred_at: datetime


class EventPublisher:
    """Journal events before making them observable to in-process subscribers."""

    def __init__(self, journal: JsonlJournal) -> None:
        self._journal = journal
        self._subscribers: list[Callable[[RunEvent], None]] = []

    def subscribe(self, subscriber: Callable[[RunEvent], None]) -> None:
        self._subscribers.append(subscriber)

    def publish(self, event: RunEvent) -> RunEvent:
        saved = self._journal.append(
            JournalEvent(
                event_id=event.event_id,
                run_id=event.run_id,
                sequence=event.sequence,
                type=event.type,
                data=event.data,
                occurred_at=event.occurred_at,
            )
        )
        published = event.model_copy(
            update={"event_id": saved.event_id, "sequence": saved.sequence, "occurred_at": saved.occurred_at}
        )
        for subscriber in tuple(self._subscribers):
            subscriber(published)
        return published

    def history(self, run_id: str) -> list[RunEvent]:
        return [RunEvent.model_validate(event.model_dump()) for event in self._journal.read(run_id)]
