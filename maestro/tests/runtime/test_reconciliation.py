import pytest

from maestro.runtime.capabilities import CapabilityKind, CapabilityResult, CapabilitySpec, UnknownWriteOutcome
from maestro.runtime.models import RunStatus, RuntimeErrorKind
from test_fast_loop import RuntimeHarness


class UnknownExecutor:
    def __init__(self) -> None:
        self.calls = 0
        self.keys: list[str | None] = []

    async def __call__(self, _call, key):
        self.calls += 1
        self.keys.append(key)
        raise UnknownWriteOutcome()


@pytest.mark.asyncio
async def test_unknown_write_is_reconciled_without_repeat_execution(tmp_path) -> None:
    harness = RuntimeHarness(tmp_path)
    executor = UnknownExecutor()
    reconciled: list[str] = []

    async def reconcile(_call, key):
        reconciled.append(key)
        return CapabilityResult(status="succeeded", content={"external": "done"})

    harness.registry.register(
        CapabilitySpec(name="write", kind=CapabilityKind.TOOL, writes=True, executor=executor, reconciler=reconcile)
    )
    harness.model.queue_call("write")
    run = await harness.coordinator.start("write")

    assert run.status is RunStatus.RECONCILING
    assert run.requires_reconciliation is True
    assert executor.calls == 1
    completed = await harness.coordinator.reconcile(run.run_id)
    assert completed.status is RunStatus.RUNNING_STRUCTURED
    assert executor.calls == 1
    assert reconciled == executor.keys


@pytest.mark.asyncio
async def test_only_idempotent_configured_transient_write_retries(tmp_path) -> None:
    harness = RuntimeHarness(tmp_path)

    class Flaky:
        def __init__(self) -> None:
            self.calls = 0

        async def __call__(self, _call, _key):
            self.calls += 1
            if self.calls == 1:
                return CapabilityResult(status="failed", error_kind=RuntimeErrorKind.TRANSIENT_INFRASTRUCTURE)
            return CapabilityResult(status="succeeded")

    executor = Flaky()
    harness.registry.register(CapabilitySpec(name="write", kind=CapabilityKind.TOOL, writes=True, idempotent=True, retryable_errors=frozenset({RuntimeErrorKind.TRANSIENT_INFRASTRUCTURE}), executor=executor))
    harness.model.queue_call("write")

    run = await harness.coordinator.start("write")

    assert run.status is RunStatus.RUNNING_STRUCTURED
    assert executor.calls == 2


@pytest.mark.asyncio
async def test_failed_write_never_invokes_compensation_implicitly(tmp_path) -> None:
    harness = RuntimeHarness(tmp_path)

    class Failing:
        async def __call__(self, _call, _key):
            return CapabilityResult(status="failed", error_message="blocked")

    compensation = harness.add_tool("compensate")
    harness.registry.register(CapabilitySpec(name="write", kind=CapabilityKind.TOOL, writes=True, executor=Failing()))
    harness.model.queue_call("write")

    run = await harness.coordinator.start("write")

    assert run.status is RunStatus.FAILED
    assert compensation.calls == 0
