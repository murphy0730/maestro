"""工具模块。

提供工具定义、注册和执行框架。
"""

from .base import (
    BaseTool,
    Tool,
    ToolDef,
    ToolPermissionLevel,
    ToolResult,
    ToolResultStatus,
    build_tool,
    find_tool_by_name,
    tool_matches_name,
)
from .builtins import get_all_base_tools, register_all_builtins
from .integrated_manager import IntegratedToolManager
from .manager import ToolManager
from .permissions import PermissionChecker, PermissionResult
from .registry import ToolRegistry, registry

__all__ = [
    "Tool",
    "BaseTool",
    "ToolDef",
    "build_tool",
    "ToolResult",
    "ToolResultStatus",
    "ToolPermissionLevel",
    "tool_matches_name",
    "find_tool_by_name",
    "ToolRegistry",
    "registry",
    "ToolManager",
    "PermissionChecker",
    "PermissionResult",
    "register_all_builtins",
    "get_all_base_tools",
    "IntegratedToolManager",
    "initialize_tools",
]


def initialize_tools(tool_registry: ToolRegistry | None = None, workspace_root=None) -> ToolRegistry:
    """初始化工具模块，注册所有内置工具。workspace_root 为文件工具的可写工作区根。"""
    target = tool_registry or registry
    register_all_builtins(target, workspace_root=workspace_root)
    return target
