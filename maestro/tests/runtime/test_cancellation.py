import pytest

from maestro.runtime.capabilities import CapabilityKind, CapabilitySpec, UnknownWriteOutcome
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
