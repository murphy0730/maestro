"""工具注册表。

每个工具有 name / description / parameters(JSON schema) / handler，
可导出为 OpenAI function-calling (tools) 格式。

v0.2: 工具带 `kind` (read/write/aux) 与可选 `precondition` (写操作前置断言)。
调度引擎的 ReAct 智能体据此对写操作执行「前置断言 → 授权」两道护栏。
"""

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal

logger = logging.getLogger(__name__)

ToolKind = Literal["read", "write", "aux"]


@dataclass
class PreconditionResult:
    """写操作前置断言结果。ok=False 时 reason 回喂给 ReAct (拦截执行)。"""

    ok: bool
    reason: str = ""


# 前置断言: 给定工具参数，判断写操作的硬前提是否满足 (代码硬规则，不依赖 LLM)
Precondition = Callable[[dict], Awaitable[PreconditionResult]]


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    handler: Callable[..., Awaitable[Any]]
    kind: ToolKind = "read"
    precondition: Precondition | None = None


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict,
        handler: Callable[..., Awaitable[Any]],
        kind: ToolKind = "read",
        precondition: Precondition | None = None,
    ) -> None:
        if name in self._tools:
            raise ValueError(f"工具 {name} 已注册")
        self._tools[name] = Tool(name, description, parameters, handler, kind, precondition)

    def attach_precondition(self, name: str, precondition: Precondition) -> None:
        """为已注册的写操作工具挂载前置断言 (在组装根装配，避免 foundation 依赖引擎)。"""
        tool = self.get(name)
        if tool.kind != "write":
            raise ValueError(f"工具 {name} 非写操作 (kind={tool.kind})，无需前置断言")
        tool.precondition = precondition

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"工具 {name} 未注册")
        return self._tools[name]

    def names(self, kind: ToolKind | None = None) -> list[str]:
        return [t.name for t in self._tools.values() if kind is None or t.kind == kind]

    def list_all(self) -> list[Tool]:
        return list(self._tools.values())

    def to_openai_tools(self, names: list[str] | None = None) -> list[dict]:
        """导出为 OpenAI function-calling 的 tools 格式。names 给定时只导出白名单内的工具。"""
        allow = set(names) if names is not None else None
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
            if allow is None or t.name in allow
        ]

    async def execute(self, name: str, arguments: dict) -> Any:
        tool = self.get(name)
        logger.info("[TOOL] %s args=%s", name, arguments)
        return await tool.handler(**arguments)
