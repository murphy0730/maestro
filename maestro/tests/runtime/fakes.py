from __future__ import annotations

from collections import deque

from maestro.runtime.capabilities import CapabilityCall, CapabilityResult
from maestro.runtime.context import ContextBundle
from maestro.runtime.model import ModelAction


class FakeRuntimeModel:
    """Deterministic model double for exercising the coordinator boundary."""

    def __init__(self) -> None:
        self._actions: deque[ModelAction] = deque()
        self.contexts: list[ContextBundle] = []
        self.capability_names: list[list[str]] = []
        self.messages: list[list[dict]] = []

    def queue_final(self, text: str) -> None:
        self._actions.append(ModelAction(kind="final", text=text))

    def queue_call(
        self,
        name: str,
        arguments: dict[str, object] | None = None,
        *,
        assistant_message: dict | None = None,
        tool_call_id: str = "",
        parse_error: str = "",
        dropped_calls: tuple[str, ...] = (),
    ) -> None:
        self._actions.append(
            ModelAction(
                kind="call",
                call=CapabilityCall(name=name, arguments=arguments or {}),
                assistant_message=assistant_message or {},
                tool_call_id=tool_call_id,
                parse_error=parse_error,
                dropped_calls=dropped_calls,
            )
        )

    async def next_turn(
        self, context: ContextBundle, capabilities: list[object], messages: list[dict] | None = None
    ) -> ModelAction:
        self.contexts.append(context)
        self.capability_names.append([capability.name for capability in capabilities])
        self.messages.append(list(messages or []))
        return self._actions.popleft()

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


class FlakyExecutor:
    """Fails the first `failures` calls, then succeeds."""

    def __init__(self, failures: int = 1, message: str = "文件不存在") -> None:
        self.failures = failures
        self.message = message
        self.calls = 0

    async def __call__(self, call: CapabilityCall, idempotency_key: str | None) -> CapabilityResult:
        self.calls += 1
        if self.calls <= self.failures:
            return CapabilityResult(status="failed", error_message=self.message)
        return CapabilityResult(status="succeeded", content={"ok": True})


class RaisingExecutor:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, call: CapabilityCall, idempotency_key: str | None) -> CapabilityResult:
        self.calls += 1
        raise RuntimeError("boom")
