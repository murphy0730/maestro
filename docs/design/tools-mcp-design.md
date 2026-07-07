# Tools 模块和 MCP 模块设计文档

## 1. 概述

本文档描述了 manufacturing-agent 项目的工具（Tools）模块和模型上下文协议（MCP）模块的设计与实现方案。该方案基于 Claude Code 的真实架构（通过逆向工程获得），但根据项目需求进行了简化和适配。

## 2. 架构设计

### 2.1 整体架构

```
maestro/
├── tools/                    # 工具模块
│   ├── __init__.py
│   ├── base.py            # 工具基类和核心类型
│   ├── registry.py       # 工具注册器
│   ├── manager.py        # 工具管理器
│   ├── builtins/          # 内置工具
│   │   ├── __init__.py
│   │   ├── filesystem.py  # 文件系统工具
│   │   ├── shell.py       # Shell 工具
│   │   └── search.py     # 搜索工具
│   └── permissions.py      # 权限系统
└── mcp/                    # MCP 模块
    ├── __init__.py
    ├── client.py        # MCP 客户端（协议层）
    ├── manager.py       # MCP 管理器
    ├── server.py      # MCP 服务器集成
    ├── transport.py     # 传输层
    ├── discovery.py     # 工具发现
    ├── execution.py     # 工具执行
    └── types.py        # 类型定义
```

### 2.2 核心概念（基于 Claude Code）

#### 2.2.1 三层工具模型

Claude Code 采用了三层工具抽象模型，我们将其适配到 Python：

1. **CoreTool** - 纯协议接口，无宿主特定类型（参考 `packages/agent-tools/src/types.ts`）
2. **Tool** - 宿主接口，扩展了 CoreTool，包含上下文相关方法
3. **ToolDef + build_tool()** - 工具构建器模式，工具作者编写 ToolDef，build_tool 填充安全默认值

#### 2.2.2 两层 MCP 架构

MCP 实现被刻意拆分为：
- **协议层** (`mcp/client.py`, `mcp/discovery.py`, `mcp/execution.py`) - 宿主无关的 MCP 协议实现
- **宿主集成层** - 连接具体传输逻辑和宿主特定增强

#### 2.2.3 Tool（工具）

工具是可以被 AI 代理调用的功能单元，具有以下特征：

- **名称**：唯一标识符
- **描述**：工具功能描述
- **输入模式**：使用 Pydantic 定义输入参数
- **执行函数**：实际的功能实现
- **权限级别**：控制工具是否需要用户确认
- **只读标识**：标识工具是否修改系统状态
- **并发安全**：标识工具是否可以安全并发执行
- **最大结果字符数**：超过此大小的结果会持久化到磁盘

#### 2.2.4 MCP (Model Context Protocol)

MCP 是一个开放协议，允许 AI 代理与外部工具和数据源交互。本项目实现 MCP 客户端来支持：

- 连接外部 MCP 服务器
- 发现和调用外部工具
- 读取和写入资源

## 3. 工具模块设计

### 3.1 核心类型定义

```python
# tools/base.py
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable
from dataclasses import dataclass, field
from enum import Enum
from pydantic import BaseModel, Field


class ToolPermissionLevel(str, Enum):
    AUTO = "auto"              # 自动执行，无需确认
    REQUIRES_CONFIRM = "requires_confirm"  # 需要用户确认
    DENIED = "denied"          # 禁止执行


class ToolResultStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class ToolResult:
    status: ToolResultStatus
    content: Any
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # MCP 协议元数据（参考 Claude Code 的 mcpMeta）
    mcp_meta: Optional[Dict[str, Any]] = None


@runtime_checkable
class Tool(Protocol):
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
    mcp_info: Optional[Dict[str, str]]  # {server_name, tool_name}
    should_defer: bool  # 是否延迟加载
    always_load: bool  # 是否始终加载
    
    async def execute(
        self, 
        args: BaseModel, 
        context: Dict[str, Any],
        on_progress: Optional[Callable[[Any], None]] = None
    ) -> ToolResult:
        ...
    
    def get_description(self, args: Optional[BaseModel] = None) -> str:
        ...
    
    def validate_input(self, args: BaseModel, context: Dict[str, Any]) -> Optional[str]:
        ...
    
    def get_tool_use_summary(self, args: Optional[Dict[str, Any]] = None) -> Optional[str]:
        ...
    
    def get_activity_description(self, args: Optional[Dict[str, Any]] = None) -> Optional[str]:
        ...
```

### 3.2 工具基类和构建器模式

```python
# tools/base.py (continued)
from abc import ABC, abstractmethod


@dataclass
class ToolDef:
    """工具定义，用于 build_tool"""
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


def build_tool(definition: ToolDef) -> Tool:
    """
    构建完整的 Tool，填充安全默认值
    参考 Claude Code 的 buildTool() 模式
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


class BaseTool(ABC):
    name: str
    description: str
    input_schema: type[BaseModel]
    permission_level: ToolPermissionLevel = ToolPermissionLevel.AUTO
    is_readonly: bool = False
    is_enabled: bool = True
    aliases: List[str] = field(default_factory=list)
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
    ) -> ToolResult:
        ...
    
    def get_description(self, args: Optional[BaseModel] = None) -> str:
        return self.description
    
    def validate_input(self, args: BaseModel, context: Dict[str, Any]) -> Optional[str]:
        """验证输入，返回错误信息或 None"""
        return None
    
    def get_tool_use_summary(self, args: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """获取工具使用的简洁摘要"""
        return None
    
    def get_activity_description(self, args: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """获取活动描述，用于显示"""
        return None
    
    def to_anthropic_tool(self) -> Dict[str, Any]:
        """转换为 Anthropic API 工具格式"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema.model_json_schema()
        }
```

### 3.3 工具注册器

```python
# tools/registry.py
from typing import Dict, List, Optional
from .base import Tool, tool_matches_name, find_tool_by_name


class ToolRegistry:
    _instance: Optional['ToolRegistry'] = None
    _tools: Dict[str, Tool] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def register(self, tool: Tool) -> None:
        """注册工具，包括主名称和别名"""
        self._tools[tool.name] = tool
        for alias in tool.aliases:
            if alias not in self._tools:
                self._tools[alias] = tool
    
    def unregister(self, name: str) -> None:
        """取消注册工具"""
        if name in self._tools:
            tool = self._tools[name]
            del self._tools[tool.name]
            for alias in tool.aliases:
                if alias in self._tools and self._tools[alias].name == tool.name:
                    del self._tools[alias]
    
    def get(self, name: str) -> Optional[Tool]:
        """通过名称或别名获取工具"""
        return self._tools.get(name)
    
    def find_by_name(self, name: str) -> Optional[Tool]:
        """查找工具（检查主名称和别名）"""
        return find_tool_by_name(self.list_all(), name)
    
    def list_all(self) -> List[Tool]:
        """列出所有工具（去重）"""
        seen = set()
        result = []
        for tool in self._tools.values():
            if tool.name not in seen:
                seen.add(tool.name)
                result.append(tool)
        return result
    
    def list_enabled(self) -> List[Tool]:
        """列出所有启用的工具"""
        return [tool for tool in self.list_all() if tool.is_enabled]
    
    def list_initial_load(self) -> List[Tool]:
        """列出应初始加载的工具（排除 should_defer 但包含 always_load）"""
        return [
            tool for tool in self.list_enabled()
            if not tool.should_defer or tool.always_load
        ]
    
    def list_deferred(self) -> List[Tool]:
        """列出延迟加载的工具"""
        return [
            tool for tool in self.list_enabled()
            if tool.should_defer and not tool.always_load
        ]
    
    def to_anthropic_tools(self) -> List[Dict[str, Any]]:
        """转换为 Anthropic 工具列表格式"""
        return [tool.to_anthropic_tool() for tool in self.list_initial_load()]


registry = ToolRegistry()


def tool_matches_name(tool: Tool, name: str) -> bool:
    """检查工具是否匹配给定的名称（主名称或别名）"""
    if tool.name == name:
        return True
    return name in (tool.aliases or [])


def find_tool_by_name(tools: List[Tool], name: str) -> Optional[Tool]:
    """在工具列表中按名称或别名查找工具"""
    for tool in tools:
        if tool_matches_name(tool, name):
            return tool
    return None
```

### 3.4 工具管理器

```python
# tools/manager.py
from typing import Any, Dict, List, Optional, Tuple
from .base import Tool, ToolResult, ToolResultStatus, ToolPermissionLevel
from .registry import registry, find_tool_by_name
from .permissions import PermissionChecker, PermissionResult


class ToolManager:
    def __init__(self, permission_checker: Optional[PermissionChecker] = None):
        self.registry = registry
        self.permission_checker = permission_checker or PermissionChecker()
        self._pending_confirmations: Dict[str, Tuple[Tool, Any, Dict[str, Any]]] = {}
        self._confirmation_counter = 0
    
    async def execute_tool(
        self,
        tool_name: str,
        args: Dict[str, Any],
        context: Dict[str, Any],
        on_progress: Optional[Callable[[Any], None]] = None
    ) -> ToolResult:
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
            confirmation_id = self._create_pending_confirmation(tool, parsed_args, context)
            return ToolResult(
                status=ToolResultStatus.CANCELLED,
                content={"requires_confirmation": True, "confirmation_id": confirmation_id},
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
        """处理大结果，超过 max_result_size_chars 时持久化到磁盘"""
        import json
        content_str = json.dumps(result.content, ensure_ascii=False)
        
        if len(content_str) > tool.max_result_size_chars and tool.max_result_size_chars != float('inf'):
            result = self._persist_large_result(result, content_str)
        
        return result
    
    def _persist_large_result(self, result: ToolResult, content_str: str) -> ToolResult:
        """将大结果持久化到磁盘（参考 Claude Code 的实现）"""
        import tempfile
        import json
        from pathlib import Path
        
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
        context: Dict[str, Any]
    ) -> str:
        confirmation_id = f"confirm_{self._confirmation_counter}"
        self._confirmation_counter += 1
        self._pending_confirmations[confirmation_id] = (tool, args, context)
        return confirmation_id
    
    async def confirm_execution(
        self,
        confirmation_id: str,
        approved: bool,
        on_progress: Optional[Callable[[Any], None]] = None
    ) -> Optional[ToolResult]:
        if confirmation_id not in self._pending_confirmations:
            return None
        
        tool, args, context = self._pending_confirmations.pop(confirmation_id)
        if approved:
            return await tool.execute(args, context, on_progress)
        else:
            return ToolResult(
                status=ToolResultStatus.CANCELLED,
                content=None,
                error_message="Execution cancelled by user"
            )
    
    def get_pending_confirmations(self) -> Dict[str, Dict[str, Any]]:
        return {
            cid: {
                "tool_name": tool.name,
                "args": args.model_dump() if hasattr(args, 'model_dump') else args,
                "description": tool.get_activity_description(
                    args.model_dump() if hasattr(args, 'model_dump') else args
                )
            }
            for cid, (tool, args, _) in self._pending_confirmations.items()
        }
    
    def get_tools_for_agent(self) -> List[Dict[str, Any]]:
        """获取用于 Agent 的工具列表（初始加载的工具）"""
        return self.registry.to_anthropic_tools()
    
    def get_all_tools_metadata(self) -> List[Dict[str, Any]]:
        """获取所有工具的元数据"""
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
        """
        组装工具池：合并内置工具和 MCP 工具，按名称去重
        参考 Claude Code 的 assembleToolPool()
        """
        builtin_tools = self.registry.list_initial_load()
        all_mcp_tools = mcp_tools or []
        
        builtin_dict = {tool.name: tool for tool in builtin_tools}
        
        combined_tools = []
        combined_tools.extend(builtin_tools)
        
        for tool in all_mcp_tools:
            if tool.name not in builtin_dict:
                combined_tools.append(tool)
        
        return combined_tools
```

### 3.5 权限系统

```python
# tools/permissions.py
from typing import Any, Dict, Optional
from dataclasses import dataclass
from .base import Tool, ToolPermissionLevel


@dataclass
class PermissionResult:
    behavior: str  # "allow", "deny", "require_confirmation"
    updated_input: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None


class PermissionChecker:
    def __init__(self):
        self._default_level = ToolPermissionLevel.AUTO
        self._tool_overrides: Dict[str, ToolPermissionLevel] = {}
        self._allow_rules: Dict[str, List[str]] = {}
        self._deny_rules: Dict[str, List[str]] = {}
    
    def set_tool_permission(self, tool_name: str, level: ToolPermissionLevel) -> None:
        self._tool_overrides[tool_name] = level
    
    def add_allow_rule(self, tool_pattern: str, input_pattern: str) -> None:
        if tool_pattern not in self._allow_rules:
            self._allow_rules[tool_pattern] = []
        self._allow_rules[tool_pattern].append(input_pattern)
    
    def add_deny_rule(self, tool_pattern: str, input_pattern: str) -> None:
        if tool_pattern not in self._deny_rules:
            self._deny_rules[tool_pattern] = []
        self._deny_rules[tool_pattern].append(input_pattern)
    
    async def check_permission(
        self,
        tool: Tool,
        args: Any,
        context: Dict[str, Any]
    ) -> PermissionResult:
        level = self._tool_overrides.get(tool.name, tool.permission_level)
        
        if level == ToolPermissionLevel.DENIED:
            return PermissionResult(behavior="deny", reason="Tool is denied by policy")
        
        if level == ToolPermissionLevel.REQUIRES_CONFIRM:
            return PermissionResult(behavior="require_confirmation", reason="Tool requires confirmation")
        
        if tool.is_mcp:
            return PermissionResult(behavior="require_confirmation", reason="MCP tools require confirmation by default")
        
        return PermissionResult(behavior="allow", updated_input=args.model_dump() if hasattr(args, 'model_dump') else None)
    
    def matches_deny_rule(self, tool_name: str) -> bool:
        """检查工具是否被拒绝规则匹配"""
        for pattern in self._deny_rules:
            if self._pattern_match(tool_name, pattern):
                return True
        return False
    
    def _pattern_match(self, text: str, pattern: str) -> bool:
        """简单的模式匹配，支持 * 通配符"""
        import re
        regex = pattern.replace('*', '.*')
        return bool(re.fullmatch(regex, text))
```

## 4. 内置工具实现

### 4.1 文件系统工具

```python
# tools/builtins/filesystem.py
from typing import List, Optional
from pathlib import Path
from pydantic import BaseModel, Field
from ..base import BaseTool, ToolResult, ToolResultStatus, ToolPermissionLevel, build_tool, ToolDef


class ReadFileArgs(BaseModel):
    file_path: str = Field(description="Path to the file to read")
    offset: Optional[int] = Field(default=None, description="Start reading from this line number")
    limit: Optional[int] = Field(default=None, description="Maximum number of lines to read")


async def read_file_execute(
    args: ReadFileArgs, 
    context: dict,
    on_progress: None = None
) -> ToolResult:
    try:
        path = Path(args.file_path)
        if not path.exists():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                content=None,
                error_message=f"File not found: {args.file_path}"
            )
        
        content = path.read_text(encoding='utf-8')
        lines = content.split('\n')
        
        if args.offset is not None and args.offset > 0:
            lines = lines[args.offset-1:]
        if args.limit is not None and args.limit > 0:
            lines = lines[:args.limit]
        
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            content='\n'.join(lines)
        )
    except Exception as e:
        return ToolResult(
            status=ToolResultStatus.ERROR,
            content=None,
            error_message=str(e)
        )


ReadFileTool = build_tool(ToolDef(
    name="read_file",
    description="Read the contents of a file",
    input_schema=ReadFileArgs,
    execute=read_file_execute,
    permission_level=ToolPermissionLevel.AUTO,
    is_readonly=True,
    is_concurrency_safe=True,
    max_result_size_chars=float('inf'),  # Read 工具不限制大小
    search_hint="file contents read"
))


class WriteFileArgs(BaseModel):
    file_path: str = Field(description="Path to the file to write")
    content: str = Field(description="Content to write to the file")


async def write_file_execute(
    args: WriteFileArgs, 
    context: dict,
    on_progress: None = None
) -> ToolResult:
    try:
        path = Path(args.file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args.content, encoding='utf-8')
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            content={"file_path": args.file_path, "bytes_written": len(args.content)}
        )
    except Exception as e:
        return ToolResult(
            status=ToolResultStatus.ERROR,
            content=None,
            error_message=str(e)
        )


WriteFileTool = build_tool(ToolDef(
    name="write_file",
    description="Write content to a file",
    input_schema=WriteFileArgs,
    execute=write_file_execute,
    permission_level=ToolPermissionLevel.REQUIRES_CONFIRM,
    is_readonly=False,
    is_destructive=True,
    search_hint="file write save"
))


class EditFileArgs(BaseModel):
    file_path: str = Field(description="Path to the file to edit")
    old_string: str = Field(description="Exact string to replace")
    new_string: str = Field(description="Replacement string")


async def edit_file_execute(
    args: EditFileArgs, 
    context: dict,
    on_progress: None = None
) -> ToolResult:
    try:
        path = Path(args.file_path)
        if not path.exists():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                content=None,
                error_message=f"File not found: {args.file_path}"
            )
        
        content = path.read_text(encoding='utf-8')
        if args.old_string not in content:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                content=None,
                error_message="Old string not found in file"
            )
        
        new_content = content.replace(args.old_string, args.new_string)
        path.write_text(new_content, encoding='utf-8')
        
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            content={"file_path": args.file_path, "replaced": True}
        )
    except Exception as e:
        return ToolResult(
            status=ToolResultStatus.ERROR,
            content=None,
            error_message=str(e)
        )


EditFileTool = build_tool(ToolDef(
    name="edit_file",
    description="Edit a file by replacing an exact string",
    input_schema=EditFileArgs,
    execute=edit_file_execute,
    permission_level=ToolPermissionLevel.REQUIRES_CONFIRM,
    is_readonly=False,
    is_destructive=True,
    search_hint="file edit modify replace"
))


class ListFilesArgs(BaseModel):
    directory: str = Field(default=".", description="Directory to list files from")


async def list_files_execute(
    args: ListFilesArgs, 
    context: dict,
    on_progress: None = None
) -> ToolResult:
    try:
        dir_path = Path(args.directory)
        if not dir_path.exists():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                content=None,
                error_message=f"Directory not found: {args.directory}"
            )
        
        files = []
        for item in sorted(dir_path.iterdir()):
            files.append({
                "name": item.name,
                "path": str(item),
                "is_dir": item.is_dir(),
                "is_file": item.is_file(),
                "size": item.stat().st_size if item.is_file() else None
            })
        
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            content={"directory": args.directory, "files": files}
        )
    except Exception as e:
        return ToolResult(
            status=ToolResultStatus.ERROR,
            content=None,
            error_message=str(e)
        )


ListFilesTool = build_tool(ToolDef(
    name="list_files",
    description="List files and directories in a given directory",
    input_schema=ListFilesArgs,
    execute=list_files_execute,
    permission_level=ToolPermissionLevel.AUTO,
    is_readonly=True,
    is_concurrency_safe=True,
    search_hint="directory list ls"
))


def register_filesystem_tools():
    from ..registry import registry
    registry.register(ReadFileTool)
    registry.register(WriteFileTool)
    registry.register(EditFileTool)
    registry.register(ListFilesTool)
```

### 4.2 Shell 工具

```python
# tools/builtins/shell.py
import asyncio
from typing import Optional
from pydantic import BaseModel, Field
from ..base import BaseTool, ToolResult, ToolResultStatus, ToolPermissionLevel, build_tool, ToolDef


class ExecuteShellArgs(BaseModel):
    command: str = Field(description="Shell command to execute")
    timeout: Optional[int] = Field(default=30, description="Timeout in seconds")


async def execute_shell_execute(
    args: ExecuteShellArgs, 
    context: dict,
    on_progress: None = None
) -> ToolResult:
    try:
        process = await asyncio.create_subprocess_shell(
            args.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=args.timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return ToolResult(
                status=ToolResultStatus.ERROR,
                content=None,
                error_message=f"Command timed out after {args.timeout} seconds"
            )
        
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            content={
                "stdout": stdout.decode('utf-8', errors='replace'),
                "stderr": stderr.decode('utf-8', errors='replace'),
                "return_code": process.returncode
            }
        )
    except Exception as e:
        return ToolResult(
            status=ToolResultStatus.ERROR,
            content=None,
            error_message=str(e)
        )


ExecuteShellTool = build_tool(ToolDef(
    name="execute_shell",
    description="Execute a shell command",
    input_schema=ExecuteShellArgs,
    execute=execute_shell_execute,
    permission_level=ToolPermissionLevel.REQUIRES_CONFIRM,
    is_readonly=False,
    is_destructive=True,
    search_hint="shell command run bash execute"
))


def register_shell_tools():
    from ..registry import registry
    registry.register(ExecuteShellTool)
```

### 4.3 搜索工具

```python
# tools/builtins/search.py
from typing import Optional
from pathlib import Path
from pydantic import BaseModel, Field
from ..base import ToolResult, ToolResultStatus, ToolPermissionLevel, build_tool, ToolDef


class GrepArgs(BaseModel):
    pattern: str = Field(description="Pattern to search for")
    directory: Optional[str] = Field(default=".", description="Directory to search in")


async def grep_execute(
    args: GrepArgs, 
    context: dict,
    on_progress: None = None
) -> ToolResult:
    try:
        import re
        dir_path = Path(args.directory)
        if not dir_path.exists():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                content=None,
                error_message=f"Directory not found: {args.directory}"
            )
        
        results = []
        for file_path in dir_path.rglob("*"):
            if file_path.is_file() and not file_path.name.startswith('.'):
                try:
                    content = file_path.read_text(encoding='utf-8')
                    for line_num, line in enumerate(content.split('\n'), 1):
                        if re.search(args.pattern, line):
                            results.append({
                                "file": str(file_path),
                                "line": line_num,
                                "content": line.strip()
                            })
                            if len(results) >= 100:
                                break
                except (UnicodeDecodeError, PermissionError):
                    continue
            if len(results) >= 100:
                break
        
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            content={"pattern": args.pattern, "matches": results, "count": len(results)}
        )
    except Exception as e:
        return ToolResult(
            status=ToolResultStatus.ERROR,
            content=None,
            error_message=str(e)
        )


GrepTool = build_tool(ToolDef(
    name="grep",
    description="Search for a pattern in files",
    input_schema=GrepArgs,
    execute=grep_execute,
    permission_level=ToolPermissionLevel.AUTO,
    is_readonly=True,
    is_concurrency_safe=True,
    search_hint="search pattern find grep"
))


def register_search_tools():
    from ..registry import registry
    registry.register(GrepTool)
```

### 4.4 内置工具注册入口

```python
# tools/builtins/__init__.py
from .filesystem import register_filesystem_tools
from .shell import register_shell_tools
from .search import register_search_tools


_ALL_TOOLS = []


def register_all_builtins():
    register_filesystem_tools()
    register_shell_tools()
    register_search_tools()


def get_all_base_tools():
    """
    获取所有基础工具的列表
    参考 Claude Code 的 getAllBaseTools()
    """
    from .filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListFilesTool
    from .shell import ExecuteShellTool
    from .search import GrepTool
    
    return [
        ReadFileTool,
        WriteFileTool,
        EditFileTool,
        ListFilesTool,
        ExecuteShellTool,
        GrepTool,
    ]
```

## 5. MCP 模块设计（基于 Claude Code 的两层架构）

### 5.1 MCP 类型定义

```python
# mcp/types.py
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field
from enum import Enum


class MCPTransportType(str, Enum):
    STDIO = "stdio"
    SSE = "sse"
    WEBSOCKET = "websocket"
    HTTP = "http"


class MCPConfigScope(str, Enum):
    """配置作用域，参考 Claude Code 的 ConfigScope"""
    DYNAMIC = "dynamic"
    PROJECT = "project"
    USER = "user"
    LOCAL = "local"
    ENTERPRISE = "enterprise"
    MANAGED = "managed"
    CLAUDEAI = "claudeai"


@dataclass
class MCPServerConfig:
    name: str
    transport_type: MCPTransportType
    command: Optional[str] = None
    args: Optional[List[str]] = None
    url: Optional[str] = None
    env: Optional[Dict[str, str]] = None
    scope: MCPConfigScope = MCPConfigScope.PROJECT


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    server_name: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPResource:
    uri: str
    name: str
    description: str
    mime_type: str = "text/plain"


@dataclass
class MCPResourceContents:
    uri: str
    text: Optional[str] = None
    blob: Optional[bytes] = None
    mime_type: str = "text/plain"


class MCPServerConnectionStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    NEEDS_AUTH = "needs_auth"


@dataclass
class MCPServerConnection:
    name: str
    config: MCPServerConfig
    status: MCPServerConnectionStatus
    tools: List[MCPTool] = field(default_factory=list)
    resources: List[MCPResource] = field(default_factory=list)
    error: Optional[str] = None
```

### 5.2 MCP 传输层

```python
# mcp/transport.py
import asyncio
import json
import sys
from typing import Any, Dict, Optional, Callable
from abc import ABC, abstractmethod
from .types import MCPServerConfig


class MCPTransport(ABC):
    @abstractmethod
    async def connect(self) -> None:
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        pass
    
    @abstractmethod
    async def send_message(self, message: Dict[str, Any]) -> None:
        pass
    
    @abstractmethod
    async def receive_message(self) -> Optional[Dict[str, Any]]:
        pass


class StdioMCPTransport(MCPTransport):
    """
    stdio 传输层实现
    参考 Claude Code 的 packages/mcp-client/src/transport/stdio.ts
    """
    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._process: Optional[asyncio.subprocess.Process] = None
        self._read_task: Optional[asyncio.Task] = None
        self._message_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._running = False
    
    async def connect(self) -> None:
        if self._process:
            return
        
        import os
        env = dict(os.environ)
        if self.config.env:
            env.update(self.config.env)
        
        self._process = await asyncio.create_subprocess_exec(
            self.config.command,
            *self.config.args or [],
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        
        self._running = True
        self._read_task = asyncio.create_task(self._read_loop())
    
    async def disconnect(self) -> None:
        self._running = False
        
        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
        
        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            self._process = None
    
    async def send_message(self, message: Dict[str, Any]) -> None:
        if not self._process or not self._process.stdin:
            raise RuntimeError("Not connected")
        
        data = json.dumps(message, ensure_ascii=False) + "\n"
        self._process.stdin.write(data.encode('utf-8'))
        await self._process.stdin.drain()
    
    async def receive_message(self) -> Optional[Dict[str, Any]]:
        try:
            return await asyncio.wait_for(self._message_queue.get(), timeout=30)
        except asyncio.TimeoutError:
            return None
    
    async def _read_loop(self) -> None:
        if not self._process or not self._process.stdout:
            return
        
        buffer = ""
        try:
            while self._running:
                chunk = await self._process.stdout.read(4096)
                if not chunk:
                    break
                
                buffer += chunk.decode('utf-8', errors='replace')
                
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()
                    if line:
                        try:
                            msg = json.loads(line)
                            await self._message_queue.put(msg)
                        except json.JSONDecodeError:
                            continue
        except asyncio.CancelledError:
            pass
```

### 5.3 MCP 发现模块

```python
# mcp/discovery.py
from typing import Any, Dict, List
from .types import MCPTool, MCPResource


def parse_input_schema(tool_def: Dict[str, Any]) -> Dict[str, Any]:
    """
    解析工具输入模式
    参考 Claude Code 的 packages/mcp-client/src/discovery.ts
    """
    if 'inputSchema' in tool_def:
        return tool_def['inputSchema']
    
    return {
        "type": "object",
        "properties": {},
        "required": []
    }


def discover_tools_from_response(
    server_name: str,
    response: Dict[str, Any]
) -> List[MCPTool]:
    """
    从 tools/list 响应中发现工具
    参考 Claude Code 的 discoverTools()
    """
    tools = []
    tool_defs = response.get('result', {}).get('tools', [])
    
    for tool_def in tool_defs:
        tool = MCPTool(
            name=tool_def['name'],
            description=tool_def.get('description', ''),
            input_schema=parse_input_schema(tool_def),
            server_name=server_name,
            metadata={}
        )
        
        if '_meta' in tool_def:
            tool.metadata = tool_def['_meta']
        
        tools.append(tool)
    
    return tools


def discover_resources_from_response(
    response: Dict[str, Any]
) -> List[MCPResource]:
    """从 resources/list 响应中发现资源"""
    resources = []
    resource_defs = response.get('result', {}).get('resources', [])
    
    for resource_def in resource_defs:
        resource = MCPResource(
            uri=resource_def['uri'],
            name=resource_def.get('name', ''),
            description=resource_def.get('description', ''),
            mime_type=resource_def.get('mimeType', 'text/plain')
        )
        resources.append(resource)
    
    return resources
```

### 5.4 MCP 执行模块

```python
# mcp/execution.py
from typing import Any, Dict, Optional
import time


async def call_mcp_tool(
    transport,
    tool_name: str,
    arguments: Dict[str, Any],
    timeout: float = 60.0
) -> Dict[str, Any]:
    """
    调用 MCP 工具
    参考 Claude Code 的 packages/mcp-client/src/execution.ts
    """
    request_id = int(time.time() * 1000)
    
    request = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        }
    }
    
    await transport.send_message(request)
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        response = await transport.receive_message()
        if response and response.get('id') == request_id:
            if 'error' in response:
                raise RuntimeError(f"MCP error: {response['error'].get('message', 'Unknown error')}")
            return response.get('result', {})
    
    raise TimeoutError("MCP tool call timed out")


async def read_mcp_resource(
    transport,
    uri: str,
    timeout: float = 30.0
) -> List[Dict[str, Any]]:
    """
    读取 MCP 资源
    参考 Claude Code 的 packages/mcp-client/src/execution.ts
    """
    request_id = int(time.time() * 1000)
    
    request = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "resources/read",
        "params": {
            "uri": uri
        }
    }
    
    await transport.send_message(request)
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        response = await transport.receive_message()
        if response and response.get('id') == request_id:
            if 'error' in response:
                raise RuntimeError(f"MCP error: {response['error'].get('message', 'Unknown error')}")
            return response.get('result', {}).get('contents', [])
    
    raise TimeoutError("MCP resource read timed out")
```

### 5.5 MCP 客户端（协议层）

```python
# mcp/client.py
import time
from typing import Any, Dict, List, Optional
from .types import MCPServerConfig, MCPTool, MCPResource, MCPServerConnection, MCPServerConnectionStatus
from .transport import MCPTransport, StdioMCPTransport
from .discovery import discover_tools_from_response, discover_resources_from_response
from .execution import call_mcp_tool, read_mcp_resource


class MCPClient:
    """
    MCP 客户端，协议层实现
    参考 Claude Code 的 packages/mcp-client/src/manager.ts
    """
    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._transport: Optional[MCPTransport] = None
        self._request_id = 0
        self._session_id: Optional[str] = None
        self._tools: List[MCPTool] = []
        self._resources: List[MCPResource] = []
    
    async def connect(self) -> MCPServerConnection:
        if self.config.transport_type == "stdio":
            self._transport = StdioMCPTransport(self.config)
        else:
            raise ValueError(f"Unsupported transport: {self.config.transport_type}")
        
        try:
            await self._transport.connect()
            
            await self._initialize()
            await self._list_tools()
            await self._list_resources()
            
            return MCPServerConnection(
                name=self.config.name,
                config=self.config,
                status=MCPServerConnectionStatus.CONNECTED,
                tools=self._tools,
                resources=self._resources
            )
        except Exception as e:
            return MCPServerConnection(
                name=self.config.name,
                config=self.config,
                status=MCPServerConnectionStatus.ERROR,
                error=str(e)
            )
    
    async def disconnect(self) -> None:
        if self._transport:
            await self._transport.disconnect()
            self._transport = None
    
    async def _initialize(self) -> None:
        if not self._transport:
            raise RuntimeError("Not connected")
        
        request_id = self._next_id()
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                    "resources": {}
                },
                "clientInfo": {
                    "name": "manufacturing-agent",
                    "version": "0.1.0"
                }
            }
        }
        
        await self._transport.send_message(request)
        
        start_time = time.time()
        while time.time() - start_time < 30:
            response = await self._transport.receive_message()
            if response and response.get('id') == request_id:
                if 'error' in response:
                    raise RuntimeError(f"MCP initialize error: {response['error'].get('message')}")
                self._session_id = response.get('result', {}).get('sessionId')
                return
        
        raise TimeoutError("MCP initialize timed out")
    
    async def _list_tools(self) -> None:
        if not self._transport:
            raise RuntimeError("Not connected")
        
        request_id = self._next_id()
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/list"
        }
        
        await self._transport.send_message(request)
        
        start_time = time.time()
        while time.time() - start_time < 30:
            response = await self._transport.receive_message()
            if response and response.get('id') == request_id:
                self._tools = discover_tools_from_response(self.config.name, response)
                return
        
        self._tools = []
    
    async def _list_resources(self) -> None:
        if not self._transport:
            raise RuntimeError("Not connected")
        
        request_id = self._next_id()
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "resources/list"
        }
        
        await self._transport.send_message(request)
        
        start_time = time.time()
        while time.time() - start_time < 30:
            response = await self._transport.receive_message()
            if response and response.get('id') == request_id:
                self._resources = discover_resources_from_response(response)
                return
        
        self._resources = []
    
    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Any:
        if not self._transport:
            raise RuntimeError("Not connected")
        
        return await call_mcp_tool(self._transport, tool_name, arguments)
    
    async def read_resource(self, uri: str) -> List[Dict[str, Any]]:
        if not self._transport:
            raise RuntimeError("Not connected")
        
        return await read_mcp_resource(self._transport, uri)
    
    def get_tools(self) -> List[MCPTool]:
        return self._tools
    
    def get_resources(self) -> List[MCPResource]:
        return self._resources
    
    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id
```

### 5.6 MCP 管理器

```python
# mcp/manager.py
from typing import Callable, Dict, List, Optional
from .types import MCPServerConfig, MCPServerConnection, MCPTool, MCPConfigScope
from .client import MCPClient


class McpManagerEvents:
    """MCP 管理器事件"""
    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {
            "connected": [],
            "disconnected": [],
            "tools_changed": [],
            "error": [],
            "auth_required": []
        }
    
    def on(self, event: str, handler: Callable) -> None:
        if event in self._handlers:
            self._handlers[event].append(handler)
    
    def off(self, event: str, handler: Callable) -> None:
        if event in self._handlers and handler in self._handlers[event]:
            self._handlers[event].remove(handler)
    
    def emit(self, event: str, *args, **kwargs) -> None:
        if event in self._handlers:
            for handler in self._handlers[event]:
                try:
                    handler(*args, **kwargs)
                except Exception:
                    pass


class MCPManager:
    """
    MCP 管理器
    参考 Claude Code 的 McpManager
    """
    def __init__(self):
        self._clients: Dict[str, MCPClient] = {}
        self._connections: Dict[str, MCPServerConnection] = {}
        self._events = McpManagerEvents()
    
    @property
    def events(self) -> McpManagerEvents:
        return self._events
    
    async def add_server(self, config: MCPServerConfig) -> None:
        """添加 MCP 服务器配置"""
        if config.name in self._clients:
            await self.remove_server(config.name)
        
        client = MCPClient(config)
        self._clients[config.name] = client
    
    async def connect_server(self, name: str) -> Optional[MCPServerConnection]:
        """连接到 MCP 服务器"""
        if name not in self._clients:
            return None
        
        client = self._clients[name]
        try:
            connection = await client.connect()
            self._connections[name] = connection
            
            if connection.status == "connected":
                self._events.emit("connected", name)
                self._events.emit("tools_changed", name, connection.tools)
            elif connection.status == "needs_auth":
                self._events.emit("auth_required", name)
            
            return connection
        except Exception as e:
            self._events.emit("error", name, e)
            return None
    
    async def remove_server(self, name: str) -> None:
        """移除 MCP 服务器"""
        if name in self._clients:
            await self._clients[name].disconnect()
            del self._clients[name]
        
        if name in self._connections:
            del self._connections[name]
        
        self._events.emit("disconnected", name)
    
    async def connect_all(self) -> List[MCPServerConnection]:
        """连接所有 MCP 服务器"""
        connections = []
        for name in self._clients:
            conn = await self.connect_server(name)
            if conn:
                connections.append(conn)
        return connections
    
    async def disconnect_all(self) -> None:
        """断开所有 MCP 服务器"""
        for name in list(self._clients.keys()):
            await self.remove_server(name)
    
    def get_connection(self, name: str) -> Optional[MCPServerConnection]:
        """获取服务器连接状态"""
        return self._connections.get(name)
    
    def get_all_connections(self) -> List[MCPServerConnection]:
        """获取所有连接"""
        return list(self._connections.values())
    
    def get_all_tools(self) -> List[MCPTool]:
        """获取所有连接服务器的工具"""
        tools = []
        for conn in self._connections.values():
            if conn.status == "connected":
                tools.extend(conn.tools)
        return tools
    
    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict
    ) -> Any:
        """调用 MCP 工具"""
        if server_name not in self._clients:
            raise RuntimeError(f"Server not found: {server_name}")
        
        client = self._clients[server_name]
        return await client.call_tool(tool_name, arguments)
    
    async def read_resource(
        self,
        server_name: str,
        uri: str
    ) -> List[Dict[str, Any]]:
        """读取 MCP 资源"""
        if server_name not in self._clients:
            raise RuntimeError(f"Server not found: {server_name}")
        
        client = self._clients[server_name]
        return await client.read_resource(uri)
```

## 6. 工具与 MCP 集成

### 6.1 MCP 工具包装器

```python
# tools/mcp_wrapper.py
from typing import Any, Dict, Optional, Callable
from pydantic import BaseModel, create_model
from ..mcp.types import MCPTool
from ..mcp.manager import MCPManager
from .base import BaseTool, ToolResult, ToolResultStatus, ToolPermissionLevel, build_tool, ToolDef


def create_mcp_tool_wrapper(
    mcp_tool: MCPTool, 
    mcp_manager: MCPManager
) -> BaseTool:
    """
    创建 MCP 工具的包装器
    参考 Claude Code 的 MCPTool 存根展开模式
    """
    fields = {}
    properties = mcp_tool.input_schema.get("properties", {})
    required = mcp_tool.input_schema.get("required", [])
    
    for prop_name, prop_schema in properties.items():
        field_type = str
        if prop_schema.get("type") == "integer":
            field_type = int
        elif prop_schema.get("type") == "number":
            field_type = float
        elif prop_schema.get("type") == "boolean":
            field_type = bool
        elif prop_schema.get("type") == "array":
            field_type = list
        elif prop_schema.get("type") == "object":
            field_type = dict
        
        field_info = {"description": prop_schema.get("description", "")}
        if prop_name in required:
            fields[prop_name] = (field_type, ...)
        else:
            fields[prop_name] = (Optional[field_type], None)
    
    DynamicInputSchema = create_model(
        f"{mcp_tool.name.replace('-', '_').replace(' ', '_')}_Input",
        **fields
    )
    
    fully_qualified_name = f"mcp__{mcp_tool.server_name}__{mcp_tool.name}"
    
    should_defer = not mcp_tool.metadata.get("anthropic/alwaysLoad", False)
    always_load = mcp_tool.metadata.get("anthropic/alwaysLoad", False)
    
    async def mcp_tool_execute(
        args: BaseModel, 
        context: dict,
        on_progress: Optional[Callable[[Any], None]] = None
    ) -> ToolResult:
        try:
            result = await mcp_manager.call_tool(
                mcp_tool.server_name,
                mcp_tool.name,
                args.model_dump()
            )
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                content=result.get("content"),
                mcp_meta=result.get("_meta")
            )
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                content=None,
                error_message=str(e)
            )
    
    return build_tool(ToolDef(
        name=fully_qualified_name,
        description=mcp_tool.description,
        input_schema=DynamicInputSchema,
        execute=mcp_tool_execute,
        permission_level=ToolPermissionLevel.REQUIRES_CONFIRM,
        is_readonly=True,
        is_mcp=True,
        mcp_info={"server_name": mcp_tool.server_name, "tool_name": mcp_tool.name},
        should_defer=should_defer,
        always_load=always_load
    ))
```

### 6.2 集成的工具管理器

```python
# tools/integrated_manager.py
from typing import List, Dict, Any, Optional, Callable
from .manager import ToolManager
from .mcp_wrapper import create_mcp_tool_wrapper
from .registry import registry
from .base import Tool
from ..mcp.manager import MCPManager


class IntegratedToolManager:
    """
    集成工具管理器，结合内置工具和 MCP 工具
    参考 Claude Code 的 assembleToolPool
    """
    def __init__(self, mcp_manager: Optional[MCPManager] = None):
        self.tool_manager = ToolManager()
        self.mcp_manager = mcp_manager or MCPManager()
        self._mcp_tools_registered: List[str] = []
    
    async def refresh_mcp_tools(self) -> None:
        """刷新 MCP 工具"""
        for tool_name in self._mcp_tools_registered:
            try:
                registry.unregister(tool_name)
            except Exception:
                pass
        
        self._mcp_tools_registered = []
        
        mcp_tools = self.mcp_manager.get_all_tools()
        for mcp_tool in mcp_tools:
            wrapper = create_mcp_tool_wrapper(mcp_tool, self.mcp_manager)
            registry.register(wrapper)
            self._mcp_tools_registered.append(wrapper.name)
    
    def get_tools_for_agent(self) -> List[Dict[str, Any]]:
        """获取 Agent 使用的工具列表"""
        return self.tool_manager.get_tools_for_agent()
    
    def get_all_tools_metadata(self) -> List[Dict[str, Any]]:
        """获取所有工具的元数据"""
        return self.tool_manager.get_all_tools_metadata()
    
    async def execute_tool(
        self,
        tool_name: str,
        args: Dict[str, Any],
        context: Dict[str, Any],
        on_progress: Optional[Callable[[Any], None]] = None
    ):
        """执行工具"""
        return await self.tool_manager.execute_tool(tool_name, args, context, on_progress)
    
    async def confirm_execution(
        self,
        confirmation_id: str,
        approved: bool,
        on_progress: Optional[Callable[[Any], None]] = None
    ):
        """确认执行"""
        return await self.tool_manager.confirm_execution(confirmation_id, approved, on_progress)
    
    def get_pending_confirmations(self) -> Dict[str, Dict[str, Any]]:
        """获取待确认的执行"""
        return self.tool_manager.get_pending_confirmations()
    
    def assemble_tool_pool(self) -> List[Tool]:
        """
        组装完整的工具池
        参考 Claude Code 的 assembleToolPool()
        """
        mcp_tools = []
        for conn in self.mcp_manager.get_all_connections():
            if conn.status == "connected":
                for mcp_tool in conn.tools:
                    try:
                        wrapper = create_mcp_tool_wrapper(mcp_tool, self.mcp_manager)
                        mcp_tools.append(wrapper)
                    except Exception:
                        pass
        
        return self.tool_manager.assemble_tool_pool(mcp_tools)
```

## 7. 模块初始化

### 7.1 工具模块入口

```python
# tools/__init__.py
from .base import (
    Tool,
    BaseTool,
    ToolDef,
    build_tool,
    ToolResult,
    ToolResultStatus,
    ToolPermissionLevel,
    tool_matches_name,
    find_tool_by_name
)
from .registry import ToolRegistry, registry
from .manager import ToolManager
from .permissions import PermissionChecker, PermissionResult
from .builtins import register_all_builtins, get_all_base_tools
from .integrated_manager import IntegratedToolManager


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


def initialize_tools():
    """初始化工具模块，注册所有内置工具"""
    register_all_builtins()
```

### 7.2 MCP 模块入口

```python
# mcp/__init__.py
from .types import (
    MCPServerConfig,
    MCPTool,
    MCPResource,
    MCPServerConnection,
    MCPTransportType,
    MCPConfigScope,
    MCPServerConnectionStatus
)
from .manager import MCPManager
from .client import MCPClient


__all__ = [
    "MCPServerConfig",
    "MCPTool",
    "MCPResource",
    "MCPServerConnection",
    "MCPTransportType",
    "MCPConfigScope",
    "MCPServerConnectionStatus",
    "MCPManager",
    "MCPClient",
    "initialize_mcp",
]


def initialize_mcp():
    """初始化 MCP 模块"""
    return MCPManager()
```

## 8. 在 Bootstrap 中集成

```python
# 在 bootstrap.py 中添加
from .tools import initialize_tools, get_all_base_tools, registry, IntegratedToolManager
from .mcp import initialize_mcp, MCPServerConfig, MCPTransportType


async def setup_tools_and_mcp(config: dict):
    """
    设置工具和 MCP 模块
    参考 Claude Code 的架构
    """
    initialize_tools()
    
    for tool in get_all_base_tools():
        registry.register(tool)
    
    mcp_manager = initialize_mcp()
    
    mcp_servers = config.get("mcp_servers", [])
    for server_config in mcp_servers:
        mcp_config = MCPServerConfig(
            name=server_config["name"],
            transport_type=MCPTransportType(server_config["transport_type"]),
            command=server_config.get("command"),
            args=server_config.get("args"),
            env=server_config.get("env")
        )
        await mcp_manager.add_server(mcp_config)
    
    await mcp_manager.connect_all()
    
    integrated_manager = IntegratedToolManager(mcp_manager)
    await integrated_manager.refresh_mcp_tools()
    
    return integrated_manager
```

## 9. API 端点

### 9.1 工具执行端点

```python
# api/tools.py
from fastapi import APIRouter, HTTPException, Body, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, Any, Optional, List


class ToolExecuteRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]
    session_id: Optional[str] = None


class ToolConfirmRequest(BaseModel):
    confirmation_id: str
    approved: bool


tools_router = APIRouter(prefix="/tools", tags=["tools"])


def get_integrated_manager():
    """获取集成工具管理器（依赖注入占位）"""
    from ..bootstrap import platform
    return platform.integrated_tool_manager


@tools_router.post("/execute")
async def execute_tool(
    request: ToolExecuteRequest,
    background_tasks: BackgroundTasks
):
    manager = get_integrated_manager()
    
    result = await manager.execute_tool(
        request.tool_name,
        request.arguments,
        {"session_id": request.session_id}
    )
    
    if result.status == "error":
        raise HTTPException(status_code=500, detail=result.error_message)
    
    return {
        "status": result.status,
        "content": result.content,
        "error": result.error_message,
        "mcp_meta": result.mcp_meta
    }


@tools_router.post("/confirm")
async def confirm_tool(request: ToolConfirmRequest):
    manager = get_integrated_manager()
    
    result = await manager.confirm_execution(
        request.confirmation_id,
        request.approved
    )
    
    if result is None:
        raise HTTPException(status_code=404, detail="Confirmation not found")
    
    return {
        "status": result.status,
        "content": result.content,
        "error": result.error_message
    }


@tools_router.get("/pending")
async def get_pending_confirmations():
    manager = get_integrated_manager()
    return manager.get_pending_confirmations()


@tools_router.get("/list")
async def list_tools():
    manager = get_integrated_manager()
    return {
        "tools": manager.get_all_tools_metadata()
    }


@tools_router.get("/for-agent")
async def get_tools_for_agent():
    manager = get_integrated_manager()
    return {
        "tools": manager.get_tools_for_agent()
    }


# MCP 相关端点
mcp_router = APIRouter(prefix="/mcp", tags=["mcp"])


def get_mcp_manager():
    """获取 MCP 管理器（依赖注入占位）"""
    from ..bootstrap import platform
    return platform.mcp_manager


@mcp_router.get("/servers")
async def list_mcp_servers():
    manager = get_mcp_manager()
    connections = manager.get_all_connections()
    return {
        "servers": [
            {
                "name": conn.name,
                "status": conn.status,
                "error": conn.error,
                "tools": [
                    {"name": t.name, "description": t.description}
                    for t in conn.tools
                ],
                "resources": [
                    {"uri": r.uri, "name": r.name}
                    for r in conn.resources
                ]
            }
            for conn in connections
        ]
    }


@mcp_router.post("/servers/{name}/connect")
async def connect_mcp_server(name: str):
    manager = get_mcp_manager()
    connection = await manager.connect_server(name)
    if not connection:
        raise HTTPException(status_code=404, detail="Server not found")
    return {"name": connection.name, "status": connection.status}


@mcp_router.post("/servers/{name}/disconnect")
async def disconnect_mcp_server(name: str):
    manager = get_mcp_manager()
    await manager.remove_server(name)
    return {"success": True}


@mcp_router.post("/servers/{name}/tools/{tool_name}/call")
async def call_mcp_tool(
    name: str, 
    tool_name: str, 
    arguments: Dict[str, Any] = Body(...)
):
    manager = get_mcp_manager()
    try:
        result = await manager.call_tool(name, tool_name, arguments)
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@mcp_router.get("/servers/{name}/resources")
async def read_mcp_resource(name: str, uri: str):
    manager = get_mcp_manager()
    try:
        result = await manager.read_resource(name, uri)
        return {"contents": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

## 10. 使用示例

### 10.1 注册自定义工具

```python
from maestro.tools import (
    build_tool, 
    ToolDef, 
    ToolResult, 
    ToolResultStatus,
    ToolPermissionLevel,
    registry
)
from pydantic import BaseModel, Field


class MyCustomArgs(BaseModel):
    param1: str = Field(description="First parameter")
    param2: int = Field(description="Second parameter")


async def my_custom_execute(
    args: MyCustomArgs, 
    context: dict,
    on_progress: None = None
) -> ToolResult:
    return ToolResult(
        status=ToolResultStatus.SUCCESS,
        content={"param1": args.param1, "param2": args.param2}
    )


MyCustomTool = build_tool(ToolDef(
    name="my_custom_tool",
    description="This is my custom tool",
    input_schema=MyCustomArgs,
    execute=my_custom_execute,
    permission_level=ToolPermissionLevel.AUTO,
    is_readonly=True,
    search_hint="custom example"
))

registry.register(MyCustomTool)
```

### 10.2 配置 MCP 服务器

```python
from maestro.mcp import (
    MCPServerConfig, 
    MCPTransportType,
    MCPManager
)


config = MCPServerConfig(
    name="my-mcp-server",
    transport_type=MCPTransportType.STDIO,
    command="npx",
    args=["-y", "@modelcontextprotocol/server-filesystem", "/path/to/directory"]
)


mcp_manager = MCPManager()
await mcp_manager.add_server(config)
connection = await mcp_manager.connect_server("my-mcp-server")
```

## 11. 总结

本文档描述了一个完整的工具模块和 MCP 模块的设计与实现方案。该方案基于 Claude Code 的真实架构，但进行了适当的简化，更适合 manufacturing-agent 项目的需求。

关键设计点（参考 Claude Code）：

1. **三层工具模型**：CoreTool (协议) -> Tool (宿主) -> ToolDef (定义) + build_tool (构建器)
2. **两层 MCP 架构**：协议层 (mcp/client) + 宿主集成层 (mcp/manager)
3. **工具注册模式**：支持主名称和别名，统一的查找机制
4. **MCP 工具包装**：动态创建包装器，支持延迟加载 (should_defer) 和始终加载 (always_load)
5. **大结果处理**：超过 max_result_size_chars 时持久化到磁盘
6. **权限系统**：支持 auto/require_confirmation/denied 三级权限
7. **工具池组装**：合并内置工具和 MCP 工具，按名称去重
8. **事件系统**：MCP 管理器支持 connected/disconnected/tools_changed 等事件
