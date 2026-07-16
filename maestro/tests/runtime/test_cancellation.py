import pytest
import asyncio

from maestro.runtime.capabilities import CapabilityKind, CapabilityResult, CapabilitySpec, UnknownWriteOutcome
from maestro.runtime.models import RunStatus
from maestro.runtime.state_machine import transition_run
from maestro.runtime.store import RunStore
from test_fast_loop import RuntimeHarness


class UnknownExecutor:
    async def __call__(self, _call, _key):
        raise UnknownWriteOutcome()


@pytest.mark.asyncio
async def test_unknown_write_cannot_be_cancelled_until_reconciled(tmp_path) -> None:
    harness = RuntimeHarness(tmp_path)
    harness.registry.register(CapabilitySpec(name="write", kind=CapabilityKind.TOOL, writes=True, executor=UnknownExecutor()))
    harness.model.queue_call("write")
    run = await harness.coordinator.start("write")

    cancelled = await harness.coordinator.cancel(run.run_id)

    assert cancelled.status is RunStatus.RECONCILING
    assert cancelled.requires_reconciliation is True


@pytest.mark.asyncio
async def test_cancel_during_inflight_write_cannot_be_overwritten_by_completion(tmp_path) -> None:
    harness = RuntimeHarness(tmp_path)
    started = asyncio.Event()
    release = asyncio.Event()

    class BlockingExecutor:
        async def __call__(self, _call, _key):
            started.set()
            await release.wait()
            return CapabilityResult(status="succeeded")

    harness.registry.register(CapabilitySpec(name="write", kind=CapabilityKind.TOOL, writes=True, executor=BlockingExecutor()))
    harness.model.queue_call("write")
    task = asyncio.create_task(harness.coordinator.start("write"))
    await started.wait()
    run_id = next(path.stem for path in harness.coordinator._run_store.directory.glob("*.json"))

    cancelled = await harness.coordinator.cancel(run_id)
    release.set()
    completed = await task

    assert cancelled.status is RunStatus.CANCELLING
    assert completed.status is RunStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_during_inflight_unknown_write_requires_reconciliation(tmp_path) -> None:
    harness = RuntimeHarness(tmp_path)
    started = asyncio.Event()
    release = asyncio.Event()

    class BlockingUnknownExecutor:
        async def __call__(self, _call, _key):
            started.set()
            await release.wait()
            raise UnknownWriteOutcome()

    harness.registry.register(CapabilitySpec(name="write", kind=CapabilityKind.TOOL, writes=True, executor=BlockingUnknownExecutor()))
    harness.model.queue_call("write")
    task = asyncio.create_task(harness.coordinator.start("write"))
    await started.wait()
    run_id = next(path.stem for path in harness.coordinator._run_store.directory.glob("*.json"))

    assert (await harness.coordinator.cancel(run_id)).status is RunStatus.CANCELLING
    release.set()
    completed = await task

    assert completed.status is RunStatus.RECONCILING
    assert completed.requires_reconciliation is True


@pytest.mark.asyncio
async def test_definitive_write_completion_retries_after_cancel_cas_race(tmp_path) -> None:
    class CancelRacingStore(RunStore):
        raced = False

        def compare_and_save(self, run, expected_revision):
            if not self.raced and run.steps and run.inflight_step_id is None and run.status is RunStatus.RUNNING_STRUCTURED:
                self.raced = True
                current = self.load(run.run_id)
                cancelling = transition_run(current, RunStatus.CANCELLING, "cancel requested")
                assert super().compare_and_save(cancelling, current.revision)
                return False
            return super().compare_and_save(run, expected_revision)

    harness = RuntimeHarness(tmp_path)
    store = CancelRacingStore(tmp_path / "runs")
    harness.coordinator._run_store = store
    harness.registry.register(CapabilitySpec(name="write", kind=CapabilityKind.TOOL, writes=True, executor=harness.add_tool("placeholder")))
    harness.model.queue_call("write")

    completed = await harness.coordinator.start("write")

    assert store.raced is True
    assert completed.status is RunStatus.CANCELLED
    assert completed.inflight_step_id is None
