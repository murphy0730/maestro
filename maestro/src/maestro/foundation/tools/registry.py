"""工具注册表。

每个工具有 name / description / parameters(JSON schema) / handler，
可导出为 OpenAI function-calling (tools) 格式。

v0.2: 工具带 `kind` (read/write/aux) 与可选 `precondition` (写操作前置断言)。
调度引擎的 ReAct 智能体据此对写操作执行「前置断言 → 授权」两道护栏。
"""

import inspect
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal

logger = logging.getLogger(__name__)

ToolKind = Literal["read", "write", "aux"]

# 工具执行期的进度回调 (对齐 Claude Code onProgress)。收到形如
# {"phase": "started"|"progress"|"done", "tool": name, "percent": int?, "message": str?}
# 的阶段事件。None = 调用方不关心进度 (退化为同步、零开销)。
ToolProgress = Callable[[dict], Awaitable[None]]


async def _emit(cb: "ToolProgress | None", event: dict) -> None:
    """安全上报工具进度: 回调缺席跳过, 回调抛错只记日志、不影响工具执行。"""
    if cb is None:
        return
    try:
        await cb(event)
    except Exception:  # noqa: BLE001 — 进度是旁路
        logger.debug("工具进度上报失败 (忽略): %s", event, exc_info=True)


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

    async def execute(
        self, name: str, arguments: dict, on_progress: ToolProgress | None = None
    ) -> Any:
        tool = self.get(name)
        logger.info("[TOOL] %s args=%s", name, arguments)
        await _emit(on_progress, {"phase": "started", "tool": name})
        # 长任务工具可显式声明 on_progress 形参以在执行中途上报进度; 未声明者不注入,
        # 保持既有 handler(**args) 调用签名不变 (向后兼容)。
        kwargs = dict(arguments)
        if on_progress is not None and _handler_accepts_progress(tool.handler):
            kwargs["on_progress"] = on_progress
        try:
            result = await tool.handler(**kwargs)
        finally:
            await _emit(on_progress, {"phase": "done", "tool": name})
        return result


def _handler_accepts_progress(handler: Callable[..., Any]) -> bool:
    """判断工具 handler 是否显式接收 on_progress (或 **kwargs)。"""
    try:
        params = inspect.signature(handler).parameters
    except (TypeError, ValueError):
        return False
    if "on_progress" in params:
        return True
    return any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
