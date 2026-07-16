import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from maestro.runtime.capabilities import CapabilityKind, CapabilitySpec, RiskLevel
from maestro.runtime.models import RunStatus
from test_fast_loop import RuntimeHarness


class VersionRevalidator:
    def __init__(self) -> None:
        self.version = "resource-v1"

    def change_version(self, version: str) -> None:
        self.version = version

    async def __call__(self, _call):
        return self.version


@pytest.mark.asyncio
async def test_changed_external_state_expires_approval(tmp_path) -> None:
    harness = RuntimeHarness(tmp_path)
    revalidator = VersionRevalidator()
    harness.registry.register(
        CapabilitySpec(
            name="write", kind=CapabilityKind.TOOL, writes=True, risk=RiskLevel.HIGH,
            revalidator=revalidator, executor=harness.add_tool("placeholder"),
        )
    )
    harness.model.queue_call("write")
    run = await harness.coordinator.start("write")
    approval = run.pending_approvals[0]

    revalidator.change_version("resource-v2")
    resumed = await harness.coordinator.approve(
        run.run_id, approval.approval_id, True, "u1", approval.run_revision
    )

    assert resumed.status is RunStatus.WAITING_APPROVAL
    assert resumed.pending_approvals[0].approval_id != approval.approval_id
    assert harness.executors["placeholder"].calls == 0


@pytest.mark.asyncio
async def test_stale_approval_revision_is_rejected(tmp_path) -> None:
    harness = RuntimeHarness(tmp_path)
    harness.registry.register(
        CapabilitySpec(name="write", kind=CapabilityKind.TOOL, writes=True, risk=RiskLevel.HIGH, executor=harness.add_tool("placeholder"))
    )
    harness.model.queue_call("write")
    run = await harness.coordinator.start("write")
    approval = run.pending_approvals[0]

    with pytest.raises(ValueError, match="stale approval revision"):
        await harness.coordinator.approve(run.run_id, approval.approval_id, True, "u1", approval.run_revision - 1)


@pytest.mark.asyncio
async def test_expired_approval_is_replaced_without_execution(tmp_path) -> None:
    harness = RuntimeHarness(tmp_path)
    executor = harness.add_tool("placeholder")
    harness.registry.register(CapabilitySpec(name="write", kind=CapabilityKind.TOOL, writes=True, risk=RiskLevel.HIGH, executor=executor))
    harness.model.queue_call("write")
    run = await harness.coordinator.start("write")
    approval = run.pending_approvals[0]
    expired = run.model_copy(update={"pending_approvals": [approval.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})]})
    harness.coordinator._run_store.save(expired)

    resumed = await harness.coordinator.approve(run.run_id, approval.approval_id, True, "u1", approval.run_revision)

    assert resumed.status is RunStatus.WAITING_APPROVAL
    assert resumed.pending_approvals[0].approval_id != approval.approval_id
    assert executor.calls == 0


@pytest.mark.asyncio
async def test_concurrent_approval_is_claimed_once(tmp_path) -> None:
    harness = RuntimeHarness(tmp_path)
    harness.registry.register(CapabilitySpec(name="write", kind=CapabilityKind.TOOL, writes=True, risk=RiskLevel.HIGH, executor=harness.add_tool("placeholder")))
    harness.model.queue_call("write")
    run = await harness.coordinator.start("write")
    approval = run.pending_approvals[0]

    results = await asyncio.gather(
        harness.coordinator.approve(run.run_id, approval.approval_id, True, "u1", approval.run_revision),
        harness.coordinator.approve(run.run_id, approval.approval_id, True, "u2", approval.run_revision),
        return_exceptions=True,
    )

    assert sum(isinstance(item, ValueError) for item in results) == 1
