# 安全模块设计文档

## 概述

本文档描述了 manufacturing-agent 项目的安全模块设计，该模块参考了 Claude Code 的权限系统架构。

## 设计目标

1. **提供灵活的权限控制** - 支持多种权限模式
2. **工作目录限制** - 确保工具操作在指定范围内
3. **安全检查** - 对敏感文件操作进行保护
4. **可扩展性** - 支持自定义权限规则
5. **用户友好** - 提供清晰的权限提示和解释

## 架构设计

### 核心组件

```
security/
├── __init__.py          # 模块入口
├── types.py             # 类型定义
├── manager.py           # 权限管理器核心
└── rule_parser.py       # 权限规则解析
```

### 核心概念

#### 1. 权限模式（Permission Modes）

| 模式 | 说明 |
|------|------|
| `default` | 默认模式 - 破坏性操作需要确认 |
| `plan` | 计划模式 - 只做计划，不实际执行 |
| `acceptEdits` | 自动接受编辑 - 文件编辑自动允许 |
| `bypassPermissions` | 绕过权限 - 跳过所有权限检查 |
| `dontAsk` | 不询问 - 总是允许所有操作 |
| `auto` | 自动模式 - 使用 AI 智能决策 |

#### 2. 权限规则（Permission Rules）

三种规则类型：
- **allow**: 明确允许
- **deny**: 明确拒绝
- **ask**: 总是询问

规则支持的格式：
- `tool_name` - 仅匹配工具名
- `tool_name:rule_content` - 匹配工具名和内容
- `tool_name:*` - 支持通配符匹配
- `*` - 匹配所有工具

#### 3. 权限决策

决策检查顺序：
1. Bypass 模式检查
2. 安全检查（工作目录限制）
3. Deny 规则检查
4. Allow 规则检查
5. Ask 规则检查
6. 根据模式默认决策

## 核心 API

### PermissionManager

主要的权限管理器类。

```python
from maestro.security import (
    get_permission_manager,
    PermissionMode,
    PermissionRuleValue,
    PermissionRuleSource,
)

# 获取管理器实例
manager = get_permission_manager()

# 设置权限模式
manager.set_mode(PermissionMode.ACCEPT_EDITS)

# 添加权限规则
manager.add_allow_rule(PermissionRuleValue(
    tool_name="my_tool"
), source=PermissionRuleSource.PROJECT_SETTINGS)

# 检查权限
result = await manager.check_permission(tool, args, context)

if result.behavior == "allow":
    # 执行
elif result.behavior == "ask":
    # 需要用户确认
elif result.behavior == "deny":
    # 拒绝执行
```

### 权限规则 API

```python
from maestro.security import (
    parse_permission_rule_value,
    check_rule_match,
)

# 解析规则字符串
rule_value = parse_permission_rule_value("tool_name:pattern")

# 检查规则匹配
matched = check_rule_match(rule_value, "tool_name", "pattern_content")
```

## 默认安全策略

### 默认权限规则

| 工具 | 规则 | 说明 |
|------|------|------|
| `read_file` | allow | 读文件自动允许 |
| `list_files` | allow | 列目录自动允许 |
| `grep` | allow | 搜索自动允许 |
| `write_file` | ask | 写文件需要确认 |
| `edit_file` | ask | 编辑文件需要确认 |
| `execute_shell` | deny | Shell 执行被拒绝 |

### 安全检查

1. **工作目录限制** - 所有文件操作必须在项目根目录内
2. **敏感文件保护** - 对 `.env`, `.git`, `.ssh` 等敏感路径进行特殊处理
3. **默认拒绝 Shell** - Shell 执行默认被禁止

### 工作目录限制

```python
# 添加额外的允许目录
manager.add_additional_directory(
    "/path/to/allowed/dir",
    source=PermissionRuleSource.PROJECT_SETTINGS
)
```

## 与工具系统集成

### 在工具执行时使用权限检查

```python
from maestro.security import (
    get_permission_manager,
    ToolPermissionContext,
)

class MyTool:
    async def execute(self, args: Any, context: Dict[str, Any]) -> Any:
        # 1. 获取权限管理器
        manager = get_permission_manager()

        # 2. 获取权限上下文
        ctx = manager.get_permission_context()

        # 3. 检查权限
        decision = await manager.check_permission(self, args, ctx)

        if decision.behavior == "deny":
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error_message=decision.message
            )
        elif decision.behavior == "ask":
            # 这里可以集成用户确认流程
            return ToolResult(
                status=ToolResultStatus.CANCELLED,
                content={
                    "requires_confirmation": True,
                    "reason": decision.message
                }
            )

        # 4. 实际执行
        # ...
```

## 扩展点

### 1. 自定义权限检查 Hook

```python
# 在 PermissionManager 中添加自定义检查
async def custom_check(
    self,
    tool: Tool,
    args: Dict[str, Any],
) -> Optional[PermissionResult]:
    # 自定义检查逻辑
    ...
```

### 2. AI 分类器集成

在 `auto` 模式下，可以集成 AI 来智能判断权限：

```python
async def ai_classifier_check(
    tool: Tool,
    args: Dict[str, Any],
) -> bool:
    """AI 分类器判断是否允许"""
    # 调用 LLM 判断
    ...
```

### 3. 审计日志

记录所有权限决策，供安全审计使用：

```python
def log_permission_decision(
    tool_name: str,
    args: Dict[str, Any],
    decision: PermissionDecision,
) -> None:
    """记录权限决策"""
    ...
```

## 使用场景

### 场景 1: 默认开发模式

```python
manager = get_permission_manager()
manager.set_mode(PermissionMode.DEFAULT)

# 只读工具自动允许
# 写工具需要确认
```

### 场景 2: 自动化任务

```python
manager = get_permission_manager()
manager.set_mode(PermissionMode.ACCEPT_EDITS)

# 文件编辑自动允许
# 适合批量自动化任务
```

### 场景 3: 严格审查模式

```python
manager = get_permission_manager()
manager.set_mode(PermissionMode.DEFAULT)
manager.add_ask_rule(PermissionRuleValue(tool_name="*"))

# 所有操作都需要确认
```

### 场景 4: 自定义项目策略

```python
manager = get_permission_manager()

# 项目特定规则
manager.add_allow_rule(PermissionRuleValue(tool_name="project_specific_tool"))
manager.add_deny_rule(PermissionRuleValue(tool_name="dangerous_tool"))

# 项目特定目录
manager.add_additional_directory("/path/to/project/data")
```

## 安全最佳实践

1. **默认安全** - 默认使用最严格的设置
2. **最小权限** - 只赋予必要的权限
3. **审计追踪** - 记录所有权限决策
4. **定期审查** - 定期审查权限规则
5. **用户教育** - 提供清晰的权限提示

## 未来扩展计划

1. AI 驱动的权限分类器
2. 权限策略持久化到配置文件
3. 用户自定义权限规则 UI
4. 更细粒度的内容检查（Shell 命令解析）
5. 权限规则版本管理
6. 安全事件告警机制

## 参考

- Claude Code 权限系统架构
- Model Context Protocol (MCP) 安全最佳实践
- GitHub Copilot 权限设计
