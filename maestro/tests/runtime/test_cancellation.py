import pytest
import asyncio

from maestro.runtime.capabilities import CapabilityKind, CapabilityResult, CapabilitySpec, UnknownWriteOutcome
from maestro.runtime.models import RunStatus
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

    assert cancelled.status is RunStatus.CANCELLED
    assert completed.status is RunStatus.CANCELLED
