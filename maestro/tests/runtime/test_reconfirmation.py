"""`require_reconfirmation` — more than one human confirmation of the same call.

The Policy Gate has always been able to return this effect, but the coordinator
treated it as staleness: every approval issued a fresh approval, so a rule using
it could never execute at all. These tests pin the loop being closed, and the
guarantees the second round is supposed to buy.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from maestro.runtime.capabilities import CapabilityKind, CapabilitySpec, RiskLevel
from maestro.runtime.models import RunStatus
from maestro.runtime.policy import PolicyEffect, PolicyGate, PolicyRule

from fakes import CountingExecutor
from test_fast_loop import RuntimeHarness

pytestmark = pytest.mark.asyncio


class VersionRevalidator:
    def __init__(self) -> None:
        self.version = "resource-v1"

    async def __call__(self, _call):
        return self.version


def build(tmp_path: Path, *, revalidator=None) -> tuple[RuntimeHarness, CountingExecutor]:
    harness = RuntimeHarness(tmp_path)
    harness.coordinator._policy_gate = PolicyGate(
        [
            PolicyRule(
                pattern="write",
                effect=PolicyEffect.REQUIRE_RECONFIRMATION,
                source="organization",
            )
        ]
    )
    executor = CountingExecutor()
    harness.registry.register(
        CapabilitySpec(
            name="write", kind=CapabilityKind.TOOL, writes=True, risk=RiskLevel.HIGH,
            revalidator=revalidator, executor=executor,
        )
    )
    return harness, executor


async def test_first_confirmation_asks_again_instead_of_executing(tmp_path: Path) -> None:
    harness, executor = build(tmp_path)
    harness.model.queue_call("write")
    run = await harness.coordinator.start("write")
    first = run.pending_approvals[0]
    assert first.confirmations_required == 2

    resumed = await harness.coordinator.approve(
        run.run_id, first.approval_id, True, "u1", first.run_revision
    )

    assert resumed.status is RunStatus.WAITING_APPROVAL
    assert executor.calls == 0
    second = resumed.pending_approvals[0]
    assert second.approval_id != first.approval_id
    assert second.confirmations == ["u1"]


async def test_second_confirmation_executes_and_completes(tmp_path: Path) -> None:
    """Used to loop forever: this is the whole point of the fix."""
    harness, executor = build(tmp_path)
    harness.model.queue_call("write")
    run = await harness.coordinator.start("write")
    first = run.pending_approvals[0]

    pending = await harness.coordinator.approve(
        run.run_id, first.approval_id, True, "u1", first.run_revision
    )
    second = pending.pending_approvals[0]
    harness.model.queue_final("已写入。")

    resumed = await harness.coordinator.approve(
        pending.run_id, second.approval_id, True, "u2", second.run_revision
    )

    assert executor.calls == 1
    assert resumed.status is RunStatus.COMPLETED
    assert resumed.final_text == "已写入。"


async def test_both_confirming_principals_are_recorded(tmp_path: Path) -> None:
    """Auditable, and the hook a four-eyes rule would hang off later."""
    harness, _ = build(tmp_path)
    harness.model.queue_call("write")
    run = await harness.coordinator.start("write")
    first = run.pending_approvals[0]

    pending = await harness.coordinator.approve(
        run.run_id, first.approval_id, True, "alice", first.run_revision
    )

    assert pending.pending_approvals[0].confirmations == ["alice"]
    events = [
        event
        for event in harness.publisher.history(run.run_id)
        if event.type == "approval.reconfirmation_required"
    ]
    assert events and events[0].data["confirmations_required"] == 2


async def test_state_moving_between_confirmations_restarts_the_round(
    tmp_path: Path,
) -> None:
    """What the second confirmation actually buys: the world did not move."""
    revalidator = VersionRevalidator()
    harness, executor = build(tmp_path, revalidator=revalidator)
    harness.model.queue_call("write")
    run = await harness.coordinator.start("write")
    first = run.pending_approvals[0]
    pending = await harness.coordinator.approve(
        run.run_id, first.approval_id, True, "u1", first.run_revision
    )
    second = pending.pending_approvals[0]

    revalidator.version = "resource-v2"
    resumed = await harness.coordinator.approve(
        pending.run_id, second.approval_id, True, "u2", second.run_revision
    )

    assert executor.calls == 0
    assert resumed.status is RunStatus.WAITING_APPROVAL
    # The accumulated confirmations are dropped: they attested to state that has
    # since changed, so counting them would defeat the point.
    assert resumed.pending_approvals[0].confirmations == []


async def test_rejecting_at_the_second_round_fails_the_run(tmp_path: Path) -> None:
    harness, executor = build(tmp_path)
    harness.model.queue_call("write")
    run = await harness.coordinator.start("write")
    first = run.pending_approvals[0]
    pending = await harness.coordinator.approve(
        run.run_id, first.approval_id, True, "u1", first.run_revision
    )
    second = pending.pending_approvals[0]

    resumed = await harness.coordinator.approve(
        pending.run_id, second.approval_id, False, "u2", second.run_revision
    )

    assert resumed.status is RunStatus.FAILED
    assert executor.calls == 0


async def test_an_expired_second_round_does_not_execute(tmp_path: Path) -> None:
    harness, executor = build(tmp_path)
    harness.model.queue_call("write")
    run = await harness.coordinator.start("write")
    first = run.pending_approvals[0]
    pending = await harness.coordinator.approve(
        run.run_id, first.approval_id, True, "u1", first.run_revision
    )
    second = pending.pending_approvals[0]
    stale = pending.model_copy(
        update={
            "pending_approvals": [
                second.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
            ]
        }
    )
    harness.coordinator._run_store.save(stale)

    resumed = await harness.coordinator.approve(
        pending.run_id, second.approval_id, True, "u2", second.run_revision
    )

    assert executor.calls == 0
    assert resumed.status is RunStatus.WAITING_APPROVAL


async def test_plain_confirmation_still_executes_on_the_first_approval(
    tmp_path: Path,
) -> None:
    """Reconfirmation must not have made ordinary approvals need two rounds."""
    harness = RuntimeHarness(tmp_path)
    executor = CountingExecutor()
    harness.registry.register(
        CapabilitySpec(
            name="write", kind=CapabilityKind.TOOL, writes=True, risk=RiskLevel.HIGH,
            executor=executor,
        )
    )
    harness.model.queue_call("write")
    run = await harness.coordinator.start("write")
    approval = run.pending_approvals[0]
    assert approval.confirmations_required == 1
    harness.model.queue_final("已写入。")

    resumed = await harness.coordinator.approve(
        run.run_id, approval.approval_id, True, "u1", approval.run_revision
    )

    assert executor.calls == 1
    assert resumed.status is RunStatus.COMPLETED
