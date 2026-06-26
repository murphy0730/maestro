"""工具注册表。

每个工具有 name / description / parameters(JSON schema) / handler，
可导出为 OpenAI function-calling (tools) 格式。
"""

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    handler: Callable[..., Awaitable[Any]]


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict,
        handler: Callable[..., Awaitable[Any]],
    ) -> None:
        if name in self._tools:
            raise ValueError(f"工具 {name} 已注册")
        self._tools[name] = Tool(name, description, parameters, handler)

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"工具 {name} 未注册")
        return self._tools[name]

    def list_all(self) -> list[Tool]:
        return list(self._tools.values())

    def to_openai_tools(self) -> list[dict]:
        """导出为 OpenAI function-calling 的 tools 格式。"""
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
        ]

    async def execute(self, name: str, arguments: dict) -> Any:
        tool = self.get(name)
        logger.info("[TOOL] %s args=%s", name, arguments)
        return await tool.handler(**arguments)
