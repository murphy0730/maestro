import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from maestro.runtime.capabilities import CapabilityCall, CapabilityKind, CapabilitySpec, RiskLevel
from maestro.runtime.models import ApprovalRecord, RunIntent, RunPath, RunRecord, RunStatus, StepRecord
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
async def test_rejected_approval_is_persisted_as_rejected(tmp_path) -> None:
    harness = RuntimeHarness(tmp_path)
    harness.registry.register(
        CapabilitySpec(name="write", kind=CapabilityKind.TOOL, writes=True, risk=RiskLevel.HIGH, executor=harness.add_tool("placeholder"))
    )
    harness.model.queue_call("write")
    run = await harness.coordinator.start("write")
    approval = run.pending_approvals[0]

    rejected = await harness.coordinator.approve(
        run.run_id, approval.approval_id, False, "u1", approval.run_revision
    )
    stored = harness.coordinator._run_store.load(run.run_id)

    assert rejected.status is RunStatus.FAILED
    assert [item.status for item in rejected.pending_approvals] == ["rejected"]
    assert [item.status for item in stored.pending_approvals] == ["rejected"]


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


@pytest.mark.asyncio
async def test_approval_reassessment_keeps_empty_initial_skill_allowlist_and_denies(tmp_path) -> None:
    harness = RuntimeHarness(tmp_path)
    executor = harness.add_tool("write")
    snapshot = harness.registry.snapshot()
    call = CapabilityCall(name="write")
    approval = ApprovalRecord(
        run_id="skill-denied", step_id="s1", call_sha256=harness.coordinator._call_sha256(call),
        impact_summary="write", policy_reason="approval", run_revision=1,
        skill_allowed_tools=[], expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    run = RunRecord(
        run_id="skill-denied", objective="x", path=RunPath.STRUCTURED,
        status=RunStatus.WAITING_APPROVAL,
        intent=RunIntent(objective="x", path=RunPath.STRUCTURED),
        capability_versions=snapshot.versions(), revision=1,
        steps={"s1": StepRecord(run_id="skill-denied", step_id="s1", kind="write", call=call.model_dump())},
        pending_approvals=[approval],
    )
    harness.coordinator._run_store.save(run)

    resumed = await harness.coordinator.approve(run.run_id, approval.approval_id, True, "u1", 1)

    assert resumed.status is RunStatus.FAILED
    assert [item.status for item in resumed.pending_approvals] == ["expired"]
    assert executor.calls == 0
