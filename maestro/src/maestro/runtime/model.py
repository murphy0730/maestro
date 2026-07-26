from __future__ import annotations

import logging
from typing import Literal, Protocol

from pydantic import BaseModel, Field, model_validator

from maestro.foundation.llm import LLMClient, LLMError
from maestro.runtime.capabilities import CapabilityCall, CapabilitySpec
from maestro.runtime.context import ContextBundle


logger = logging.getLogger(__name__)


class ModelAction(BaseModel):
    """One model turn, carrying everything needed to thread it back into the chat.

    `assistant_message` / `tool_call_id` exist so the coordinator can append the
    assistant turn and its matching `role=tool` result to the conversation, as
    `foundation/llm.py::AgentTurn` requires.  `parse_error` marks a call whose
    arguments could not be decoded: it must be fed back to the model to correct,
    never executed with the empty arguments that stand in for them.
    """

    kind: Literal["final", "call"]
    text: str = ""
    call: CapabilityCall | None = None
    assistant_message: dict = Field(default_factory=dict)
    tool_call_id: str = ""
    parse_error: str = ""
    dropped_calls: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_payload(self) -> "ModelAction":
        if self.kind == "call" and self.call is None:
            raise ValueError("call action requires capability call")
        if self.kind == "final" and self.call is not None:
            raise ValueError("final action cannot contain capability call")
        return self


class RuntimeModel(Protocol):
    async def next_turn(
        self,
        context: ContextBundle,
        capabilities: list[CapabilitySpec],
        messages: list[dict] | None = None,
    ) -> ModelAction: ...


class LLMRuntimeModel:
    """Translate the existing LLM boundary into runtime actions without executing calls."""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def next_turn(
        self,
        context: ContextBundle,
        capabilities: list[CapabilitySpec],
        messages: list[dict] | None = None,
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
            turn = await self._llm.chat_turn(context.system_context, list(messages or []), tools=tools)
        except LLMError as error:
            logger.warning("LLM Runtime 调用失败，已降级: %s", error)
            return ModelAction(kind="final", text="模型当前不可用。")
        if turn.tool_calls:
            call = turn.tool_calls[0]
            return ModelAction(
                kind="call",
                call=CapabilityCall(name=call.name, arguments=call.arguments),
                assistant_message=turn.assistant_message,
                tool_call_id=call.id,
                parse_error=call.parse_error or "",
                # The runtime executes one capability per turn; report what was
                # discarded instead of dropping it silently.
                dropped_calls=tuple(item.name for item in turn.tool_calls[1:]),
            )
        return ModelAction(kind="final", text=turn.text)
