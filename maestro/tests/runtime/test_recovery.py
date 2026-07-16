import pytest

from maestro.runtime.capabilities import CapabilityKind, CapabilitySpec, RiskLevel
from maestro.runtime.models import RunStatus
from maestro.runtime.recovery import RunRecovery, UnsafeRecovery
from test_fast_loop import RuntimeHarness


@pytest.mark.asyncio
async def test_recovery_restores_exact_pending_approval_snapshot(tmp_path) -> None:
    harness = RuntimeHarness(tmp_path)
    harness.registry.register(CapabilitySpec(name="write", kind=CapabilityKind.TOOL, writes=True, risk=RiskLevel.HIGH, executor=harness.add_tool("placeholder")))
    harness.model.queue_call("write")
    run = await harness.coordinator.start("write")

    restored = RunRecovery(harness.coordinator, harness.publisher.journal, harness.coordinator._run_store).restore(run.run_id)

    assert restored.status is RunStatus.WAITING_APPROVAL
    assert restored.pending_approvals == run.pending_approvals


@pytest.mark.asyncio
async def test_recovery_rejects_snapshot_without_matching_journal_revision(tmp_path) -> None:
    harness = RuntimeHarness(tmp_path)
    harness.model.queue_final("done")
    run = await harness.coordinator.start("answer")
    snapshot = harness.coordinator._run_store.load(run.run_id).model_copy(update={"revision": run.revision + 1})
    harness.coordinator._run_store.save(snapshot)

    with pytest.raises(UnsafeRecovery, match="revision"):
        RunRecovery(harness.coordinator, harness.publisher.journal, harness.coordinator._run_store).restore(run.run_id)
