"""工具基类与核心类型。

基于 Claude Code 的三层工具模型：
- CoreTool (协议): 纯接口
- Tool (宿主): 带上下文的工具
- ToolDef + build_tool (构建器): 工具定义 + 安全默认值填充
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class ToolPermissionLevel(str, Enum):
    """工具权限级别。"""
    AUTO = "auto"
    REQUIRES_CONFIRM = "requires_confirm"
    DENIED = "denied"


class ToolResultStatus(str, Enum):
    """工具执行结果状态。"""
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class ToolResult:
    """工具执行结果。"""
    status: ToolResultStatus
    content: Any
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    mcp_meta: Optional[Dict[str, Any]] = None


@runtime_checkable
class Tool(Protocol):
    """工具协议接口。"""
    name: str
    description: str
    input_schema: type[BaseModel]
    permission_level: ToolPermissionLevel
    is_readonly: bool
    is_enabled: bool
    aliases: List[str]
    is_concurrency_safe: bool
    is_destructive: bool
    max_result_size_chars: int
    is_mcp: bool
    mcp_info: Optional[Dict[str, str]]
    should_defer: bool
    always_load: bool
    search_hint: Optional[str]

    async def execute(
        self,
        args: BaseModel,
        context: Dict[str, Any],
        on_progress: Optional[Callable[[Any], None]] = None
    ) -> ToolResult: ...

    def get_description(self, args: Optional[BaseModel] = None) -> str: ...

    def validate_input(self, args: BaseModel, context: Dict[str, Any]) -> Optional[str]: ...

    def get_tool_use_summary(self, args: Optional[Dict[str, Any]] = None) -> Optional[str]: ...

    def get_activity_description(self, args: Optional[Dict[str, Any]] = None) -> Optional[str]: ...


@dataclass
class ToolDef:
    """工具定义，用于 build_tool。"""
    name: str
    description: str
    input_schema: type[BaseModel]
    execute: Callable[[Any, Dict[str, Any], Optional[Callable]], Any]
    aliases: List[str] = field(default_factory=list)
    permission_level: ToolPermissionLevel = ToolPermissionLevel.AUTO
    is_readonly: bool = False
    is_enabled: bool = True
    is_concurrency_safe: bool = False
    is_destructive: bool = False
    max_result_size_chars: int = 10000
    is_mcp: bool = False
    mcp_info: Optional[Dict[str, str]] = None
    should_defer: bool = False
    always_load: bool = False
    search_hint: Optional[str] = None
    validate_input: Optional[Callable[[Any, Dict[str, Any]], Optional[str]]] = None
    get_tool_use_summary: Optional[Callable[[Optional[Dict[str, Any]]], Optional[str]]] = None
    get_activity_description: Optional[Callable[[Optional[Dict[str, Any]]], Optional[str]]] = None


class BaseTool(ABC):
    """工具基类。"""
    name: str
    description: str
    input_schema: type[BaseModel]
    permission_level: ToolPermissionLevel = ToolPermissionLevel.AUTO
    is_readonly: bool = False
    is_enabled: bool = True
    aliases: List[str] = []
    is_concurrency_safe: bool = False
    is_destructive: bool = False
    max_result_size_chars: int = 10000
    is_mcp: bool = False
    mcp_info: Optional[Dict[str, str]] = None
    should_defer: bool = False
    always_load: bool = False
    search_hint: Optional[str] = None

    @abstractmethod
    async def execute(
        self,
        args: BaseModel,
        context: Dict[str, Any],
        on_progress: Optional[Callable[[Any], None]] = None
    ) -> ToolResult: ...

    def get_description(self, args: Optional[BaseModel] = None) -> str:
        return self.description

    def validate_input(self, args: BaseModel, context: Dict[str, Any]) -> Optional[str]:
        return None

    def get_tool_use_summary(self, args: Optional[Dict[str, Any]] = None) -> Optional[str]:
        return None

    def get_activity_description(self, args: Optional[Dict[str, Any]] = None) -> Optional[str]:
        return None

    def to_anthropic_tool(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema.model_json_schema(),
        }


def build_tool(definition: ToolDef) -> Tool:
    """构建完整的 Tool，填充安全默认值。

    参考 Claude Code 的 buildTool() 模式。
    """

    class BuiltTool(BaseTool):
        name = definition.name
        description = definition.description
        input_schema = definition.input_schema
        aliases = definition.aliases
        permission_level = definition.permission_level
        is_readonly = definition.is_readonly
        is_enabled = definition.is_enabled
        is_concurrency_safe = definition.is_concurrency_safe
        is_destructive = definition.is_destructive
        max_result_size_chars = definition.max_result_size_chars
        is_mcp = definition.is_mcp
        mcp_info = definition.mcp_info
        should_defer = definition.should_defer
        always_load = definition.always_load
        search_hint = definition.search_hint

        async def execute(
            self,
            args: BaseModel,
            context: Dict[str, Any],
            on_progress: Optional[Callable[[Any], None]] = None
        ) -> ToolResult:
            return await definition.execute(args, context, on_progress)

        def validate_input(self, args: BaseModel, context: Dict[str, Any]) -> Optional[str]:
            if definition.validate_input:
                return definition.validate_input(args, context)
            return None

        def get_tool_use_summary(self, args: Optional[Dict[str, Any]] = None) -> Optional[str]:
            if definition.get_tool_use_summary:
                return definition.get_tool_use_summary(args)
            return None

        def get_activity_description(self, args: Optional[Dict[str, Any]] = None) -> Optional[str]:
            if definition.get_activity_description:
                return definition.get_activity_description(args)
            return None

    return BuiltTool()


def tool_matches_name(tool: Tool, name: str) -> bool:
    """检查工具是否匹配给定的名称（主名称或别名）。"""
    if tool.name == name:
        return True
    return name in (tool.aliases or [])


def find_tool_by_name(tools: List[Tool], name: str) -> Optional[Tool]:
    """在工具列表中按名称或别名查找工具。"""
    for tool in tools:
        if tool_matches_name(tool, name):
            return tool
    return None
