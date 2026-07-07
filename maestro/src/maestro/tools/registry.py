"""工具注册表。

管理工具的注册、查找和列表。支持主名称和别名。
"""

from typing import Any, Dict, List, Optional

from .base import Tool, find_tool_by_name, tool_matches_name


class ToolRegistry:
    """工具注册表。"""

    _instance: Optional['ToolRegistry'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._tools: Dict[str, Tool] = {}
        self._initialized = True

    def register(self, tool: Tool) -> None:
        """注册工具，包括主名称和别名。"""
        self._tools[tool.name] = tool
        for alias in tool.aliases:
            if alias not in self._tools:
                self._tools[alias] = tool

    def unregister(self, name: str) -> None:
        """取消注册工具。"""
        if name in self._tools:
            tool = self._tools[name]
            if tool.name in self._tools:
                del self._tools[tool.name]
            for alias in tool.aliases:
                if alias in self._tools and self._tools[alias].name == tool.name:
                    del self._tools[alias]

    def get(self, name: str) -> Optional[Tool]:
        """通过名称或别名获取工具。"""
        return self._tools.get(name)

    def find_by_name(self, name: str) -> Optional[Tool]:
        """查找工具（检查主名称和别名）。"""
        return find_tool_by_name(self.list_all(), name)

    def list_all(self) -> List[Tool]:
        """列出所有工具（去重）。"""
        seen = set()
        result = []
        for tool in self._tools.values():
            if tool.name not in seen:
                seen.add(tool.name)
                result.append(tool)
        return result

    def list_enabled(self) -> List[Tool]:
        """列出所有启用的工具。"""
        return [tool for tool in self.list_all() if tool.is_enabled]

    def list_initial_load(self) -> List[Tool]:
        """列出应初始加载的工具（排除 should_defer 但包含 always_load）。"""
        return [
            tool for tool in self.list_enabled()
            if not tool.should_defer or tool.always_load
        ]

    def list_deferred(self) -> List[Tool]:
        """列出延迟加载的工具。"""
        return [
            tool for tool in self.list_enabled()
            if tool.should_defer and not tool.always_load
        ]

    def to_anthropic_tools(self) -> List[Dict[str, Any]]:
        """转换为 Anthropic 工具列表格式。"""
        return [tool.to_anthropic_tool() for tool in self.list_initial_load()]


registry = ToolRegistry()
