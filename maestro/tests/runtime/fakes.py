from __future__ import annotations

from collections import deque

from maestro.runtime.capabilities import CapabilityCall, CapabilityResult
from maestro.runtime.context import ContextBundle
from maestro.runtime.model import ModelAction
from maestro.runtime.models import GoalSpec, RunIntent, TypedPlan


class FakeRuntimeModel:
    """Deterministic model double for exercising the coordinator boundary."""

    def __init__(self) -> None:
        self._actions: deque[ModelAction] = deque()
        self.contexts: list[ContextBundle] = []
        self.capability_names: list[list[str]] = []

    def queue_final(self, text: str) -> None:
        self._actions.append(ModelAction(kind="final", text=text))

    def queue_call(self, name: str, arguments: dict[str, object] | None = None) -> None:
        self._actions.append(
            ModelAction(kind="call", call=CapabilityCall(name=name, arguments=arguments or {}))
        )

    async def next_turn(self, context: ContextBundle, capabilities: list[object]) -> ModelAction:
        self.contexts.append(context)
        self.capability_names.append([capability.name for capability in capabilities])
        return self._actions.popleft()

    async def structure_goal(self, intent: RunIntent, context: ContextBundle) -> GoalSpec:
        return GoalSpec(objective=intent.objective, success_criteria=["complete"])

    async def create_plan(self, goal: GoalSpec, capabilities: list[object]) -> TypedPlan:
        raise AssertionError("structured planning is not part of the fast-loop task")


class RecordingEvents:
    def __init__(self) -> None:
        self.types: list[str] = []

    def __call__(self, event: object) -> None:
        self.types.append(event.type)


class CountingExecutor:
    def __init__(self, content: object = {"ok": True}) -> None:
        self.content = content
        self.calls = 0

    async def __call__(self, call: CapabilityCall, idempotency_key: str | None) -> CapabilityResult:
        self.calls += 1
        return CapabilityResult(status="succeeded", content=self.content)
