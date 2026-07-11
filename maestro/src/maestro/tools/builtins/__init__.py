"""内置工具模块。

提供文件系统、搜索、任务清单、网页抓取、延迟工具检索等内置工具。
"""

from .filesystem import (
    EditFileTool,
    ListFilesTool,
    ReadFileTool,
    WriteFileTool,
    register_filesystem_tools,
)
from .search import GlobTool, GrepTool, register_search_tools
from .sleep import SleepTool, register_sleep_tools
from .shell import BashTool, PowerShellTool, ReadOutputTool, register_shell_tools
from .todo import TodoWriteTool, register_todo_tools
from .tool_search import ToolSearchTool, register_tool_search_tools
from .web import WebFetchTool, register_web_tools
from ..registry import ToolRegistry


def register_all_builtins(tool_registry: ToolRegistry | None = None):
    """注册所有内置工具。"""
    register_filesystem_tools(tool_registry)
    register_search_tools(tool_registry)
    register_todo_tools(tool_registry)
    register_web_tools(tool_registry)
    register_tool_search_tools(tool_registry)
    register_sleep_tools(tool_registry)
    register_shell_tools(tool_registry)


def get_all_base_tools():
    """获取所有基础工具的列表。"""
    return [
        ReadFileTool,
        WriteFileTool,
        EditFileTool,
        ListFilesTool,
        GrepTool,
        GlobTool,
        TodoWriteTool,
        WebFetchTool,
        ToolSearchTool,
        SleepTool,
        BashTool,
        PowerShellTool,
        ReadOutputTool,
    ]
