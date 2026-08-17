from __future__ import annotations

import logging
from typing import Literal, Protocol

from pydantic import BaseModel, Field, model_validator

from maestro.foundation.llm import LLMClient, LLMContextOverflow, LLMError
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

    kind: Literal["final", "call", "error"]
    text: str = ""
    # Why the turn could not be taken; set only when kind == "error".
    reason: str = ""
    call: CapabilityCall | None = None
    assistant_message: dict = Field(default_factory=dict)
    tool_call_id: str = ""
    parse_error: str = ""
    dropped_calls: tuple[str, ...] = ()
    # Provider-reported token counts for this turn; None when unreported.
    usage: dict | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> "ModelAction":
        if self.kind == "call" and self.call is None:
            raise ValueError("call action requires capability call")
        if self.kind != "call" and self.call is not None:
            raise ValueError(f"{self.kind} action cannot contain capability call")
        if self.kind == "error" and not self.reason:
            raise ValueError("error action requires a reason")
        return self


class RuntimeModel(Protocol):
    async def next_turn(
        self,
        context: ContextBundle,
        capabilities: list[CapabilitySpec],
        messages: list[dict] | None = None,
    ) -> ModelAction: ...


def build_tool_schemas(capabilities: list[CapabilitySpec]) -> list[dict]:
    """The OpenAI tool array for these capabilities.

    Module-level so the coordinator can size the tool schemas it is billed for
    without keeping a second copy of their shape in sync.
    """
    return [
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
        tools = build_tool_schemas(capabilities)
        try:
            turn = await self._llm.chat_turn(context.system_context, list(messages or []), tools=tools)
        except LLMContextOverflow as error:
            # Distinct from an unavailable model: the Run assembled a prompt too
            # large for the window, and the budget that should have prevented it
            # is the thing to look at.
            logger.warning("上下文超出模型窗口: %s", error)
            return ModelAction(kind="error", reason="context_overflow")
        except LLMError as error:
            # Never answer on the model's behalf. Reporting a fabricated final
            # here used to complete the Run successfully, writing "模型当前不可用。"
            # into the session history as if it were a real reply.
            logger.warning("LLM Runtime 调用失败: %s", error)
            return ModelAction(kind="error", reason="model_unavailable")
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
                usage=turn.usage,
            )
        return ModelAction(kind="final", text=turn.text, usage=turn.usage)
