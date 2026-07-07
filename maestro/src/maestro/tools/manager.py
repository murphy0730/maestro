"""工具管理器。

管理工具的执行、权限检查、确认流程等。
"""

import json
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .base import Tool, ToolResult, ToolResultStatus, ToolPermissionLevel
from .registry import registry, find_tool_by_name
from .permissions import PermissionChecker, PermissionResult, PermissionRule


class ToolManager:
    """工具管理器。"""

    def __init__(self, permission_checker: Optional[PermissionChecker] = None):
        self.registry = registry
        self.permission_checker = permission_checker or PermissionChecker()
        self._pending_confirmations: Dict[str, Tuple[Tool, Any, Dict[str, Any], Optional[PermissionRule]]] = {}
        self._confirmation_counter = 0

    async def execute_tool(
        self,
        tool_name: str,
        args: Dict[str, Any],
        context: Dict[str, Any],
        on_progress: Optional[Callable[[Any], None]] = None
    ) -> ToolResult:
        """执行工具。"""
        tool = self.registry.find_by_name(tool_name)
        if not tool:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                content=None,
                error_message=f"Tool not found: {tool_name}"
            )

        if not tool.is_enabled:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                content=None,
                error_message=f"Tool is disabled: {tool_name}"
            )

        try:
            parsed_args = tool.input_schema(**args)
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                content=None,
                error_message=f"Invalid arguments: {str(e)}"
            )

        validation_error = tool.validate_input(parsed_args, context)
        if validation_error:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                content=None,
                error_message=validation_error
            )

        permission_result = await self.permission_checker.check_permission(
            tool, parsed_args, context
        )

        if permission_result.behavior == "deny":
            return ToolResult(
                status=ToolResultStatus.ERROR,
                content=None,
                error_message=f"Permission denied for tool: {tool_name}"
            )

        if permission_result.behavior == "require_confirmation":
            confirmation_id = self._create_pending_confirmation(
                tool, parsed_args, context, permission_result.suggested_rule
            )
            content = {
                "requires_confirmation": True,
                "confirmation_id": confirmation_id,
            }
            # 如果有 suggested_rule，提供 "don't ask again" 选项
            if permission_result.suggested_rule:
                content["can_dont_ask_again"] = True
            return ToolResult(
                status=ToolResultStatus.CANCELLED,
                content=content,
                error_message="User confirmation required"
            )

        try:
            result = await tool.execute(parsed_args, context, on_progress)

            if result.status == ToolResultStatus.SUCCESS:
                result = self._handle_large_result(result, tool)

            return result
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                content=None,
                error_message=str(e)
            )

    def _handle_large_result(self, result: ToolResult, tool: Tool) -> ToolResult:
        """处理大结果，超过 max_result_size_chars 时持久化到磁盘。"""
        content_str = json.dumps(result.content, ensure_ascii=False)

        if (tool.max_result_size_chars != float('inf') and
            len(content_str) > tool.max_result_size_chars):
            result = self._persist_large_result(result, content_str)

        return result

    def _persist_large_result(self, result: ToolResult, content_str: str) -> ToolResult:
        """将大结果持久化到磁盘。"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write(content_str)
            temp_path = f.name

        result.content = {
            "result_persisted": True,
            "path": temp_path,
            "preview": content_str[:1000] + "..." if len(content_str) > 1000 else content_str
        }
        return result

    def _create_pending_confirmation(
        self,
        tool: Tool,
        args: Any,
        context: Dict[str, Any],
        suggested_rule: Optional[PermissionRule] = None
    ) -> str:
        """创建待确认的执行。"""
        confirmation_id = f"confirm_{self._confirmation_counter}"
        self._confirmation_counter += 1
        self._pending_confirmations[confirmation_id] = (tool, args, context, suggested_rule)
        return confirmation_id

    async def confirm_execution(
        self,
        confirmation_id: str,
        approved: bool,
        and_dont_ask_again: bool = False,
        on_progress: Optional[Callable[[Any], None]] = None
    ) -> Optional[ToolResult]:
        """确认或取消待执行的操作。

        如果 and_dont_ask_again 为 True，则添加 session 级别的 allow 规则，
        今后该 session 遇到相同工具调用时不再询问（重启应用后会重置）。
        """
        if confirmation_id not in self._pending_confirmations:
            return None

        tool, args, context, suggested_rule = self._pending_confirmations.pop(confirmation_id)
        if approved:
            # 如果用户选择 "don't ask again"，并且有 suggested_rule，则添加到 session 规则
            if and_dont_ask_again and suggested_rule:
                self.permission_checker.add_rule(suggested_rule)
            return await tool.execute(args, context, on_progress)
        else:
            return ToolResult(
                status=ToolResultStatus.CANCELLED,
                content=None,
                error_message="Execution cancelled by user"
            )

    def get_pending_confirmations(self) -> Dict[str, Dict[str, Any]]:
        """获取待确认的执行列表。"""
        return {
            cid: {
                "tool_name": tool.name,
                "args": args.model_dump() if hasattr(args, 'model_dump') else args,
                "description": tool.get_activity_description(
                    args.model_dump() if hasattr(args, 'model_dump') else args
                )
            }
            for cid, (tool, args, _, _) in self._pending_confirmations.items()
        }

    def get_tools_for_agent(self) -> List[Dict[str, Any]]:
        """获取用于 Agent 的工具列表（初始加载的工具）。"""
        return self.registry.to_anthropic_tools()

    def get_all_tools_metadata(self) -> List[Dict[str, Any]]:
        """获取所有工具的元数据。"""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "is_readonly": tool.is_readonly,
                "is_destructive": tool.is_destructive,
                "permission_level": tool.permission_level,
                "is_concurrency_safe": tool.is_concurrency_safe,
                "is_mcp": tool.is_mcp,
                "should_defer": tool.should_defer,
                "always_load": tool.always_load,
                "search_hint": tool.search_hint,
                "aliases": tool.aliases
            }
            for tool in self.registry.list_all()
        ]

    def assemble_tool_pool(self, mcp_tools: Optional[List[Tool]] = None) -> List[Tool]:
        """组装工具池：合并内置工具和 MCP 工具，按名称去重。"""
        builtin_tools = self.registry.list_initial_load()
        all_mcp_tools = mcp_tools or []

        builtin_dict = {tool.name: tool for tool in builtin_tools}

        combined_tools = []
        combined_tools.extend(builtin_tools)

        for tool in all_mcp_tools:
            if tool.name not in builtin_dict:
                combined_tools.append(tool)

        return combined_tools
