"""Safe recovery of coordinator-owned runtime state."""

from maestro.runtime.coordinator import RunCoordinator
from maestro.runtime.journal import JsonlJournal, replay_run
from maestro.runtime.models import RunRecord, RunStatus
from maestro.runtime.store import RunStore


class UnsafeRecovery(ValueError):
    """Recovery cannot prove that a persisted run is safe to resume."""


class RunRecovery:
    def __init__(self, coordinator: RunCoordinator, journal: JsonlJournal, run_store: RunStore) -> None:
        self._coordinator = coordinator
        self._journal = journal
        self._run_store = run_store

    def restore(self, run_id: str) -> RunRecord:
        snapshot = self._run_store.load(run_id)
        events = self._journal.read(run_id)
        if not events:
            raise UnsafeRecovery("missing journal")
        if snapshot.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}:
            raise UnsafeRecovery("terminal runs cannot be restored")
        try:
            projection = replay_run(events)
        except ValueError as error:
            raise UnsafeRecovery("journal cannot be replayed") from error
        revisions = [event.data.get("snapshot_revision") for event in events]
        if not isinstance(revisions[-1], int) or revisions[-1] != snapshot.revision:
            raise UnsafeRecovery("snapshot revision does not match journal")
        if projection.model_dump(mode="json") != snapshot.model_dump(mode="json"):
            raise UnsafeRecovery("snapshot does not match journal projection")
        if self._coordinator._pinned_snapshot(snapshot, None) is None:
            raise UnsafeRecovery("capability snapshot unavailable")
        return snapshot
