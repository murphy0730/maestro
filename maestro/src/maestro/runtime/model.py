from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, model_validator

from maestro.foundation.llm import LLMClient, LLMError
from maestro.runtime.capabilities import CapabilityCall, CapabilitySpec
from maestro.runtime.context import ContextBundle


class ModelAction(BaseModel):
    kind: Literal["final", "call"]
    text: str = ""
    call: CapabilityCall | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> "ModelAction":
        if self.kind == "call" and self.call is None:
            raise ValueError("call action requires capability call")
        if self.kind == "final" and self.call is not None:
            raise ValueError("final action cannot contain capability call")
        return self


class RuntimeModel(Protocol):
    async def next_turn(
        self, context: ContextBundle, capabilities: list[CapabilitySpec]
    ) -> ModelAction: ...


class LLMRuntimeModel:
    """Translate the existing LLM boundary into runtime actions without executing calls."""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def next_turn(
        self, context: ContextBundle, capabilities: list[CapabilitySpec]
    ) -> ModelAction:
        tools = [
            {
                "type": "function",
                "function": {
                    "name": capability.name,
                    "description": capability.description,
                    "parameters": capability.input_schema or {"type": "object"},
                },
            }
            for capability in capabilities
        ]
        try:
            turn = await self._llm.chat_turn(context.system_context, [], tools=tools)
        except LLMError:
            return ModelAction(kind="final", text="模型当前不可用。")
        if turn.tool_calls:
            call = turn.tool_calls[0]
            return ModelAction(
                kind="call", call=CapabilityCall(name=call.name, arguments=call.arguments)
            )
        return ModelAction(kind="final", text=turn.text)
