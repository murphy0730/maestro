# 权限体系设计文档

## 概述

本项目的权限体系融合了 **Claude Code 的三层权限架构** 和 **制造场景的动作分级授权机制**，提供了灵活且安全的工具执行控制。

### 设计目标

1. **分层保护** - 提供从工具级到策略级的多层防护
2. **审计追踪** - 完整记录所有权限决策和执行过程
3. **用户确认** - 对敏感操作提供人工确认机制
4. **可扩展性** - 支持自定义规则和策略配置
5. **向后兼容** - 同时支持旧版 ActionGate 体系和新的 PermissionChecker 体系

---

## 架构概览

```
权限决策流程：
┌─────────────────────────────────────────────────────────────────┐
│  1. 工具白名单层 (Skill allowed_tools)                          │
│  2. 静态规则层 (Permission Rules: deny > ask > allow)          │
│  3. 工具权限级别 (ToolPermissionLevel)                          │
│  4. 动作分级授权 (AuthZ + ActionGate)                          │
│  5. 运行时确认 (PendingActionStore + /chat/confirm)            │
└─────────────────────────────────────────────────────────────────┘
```

### 核心组件

| 组件 | 文件 | 职责 |
|------|------|------|
| `PermissionChecker` | `tools/permissions.py` | 新框架：三层权限规则检查器 |
| `AuthZ` | `foundation/authz.py` | 旧体系：动作分级策略 |
| `ActionGate` | `foundation/authz.py` | 旧体系：写操作统一闸口 |
| `PendingActionStore` | `foundation/authz.py` | 待确认动作存储 |
| `AuditLog` | `foundation/audit.py` | 审计日志 |
| `Tool` | `tools/base.py` | 工具基类（含权限级别） |

---

## 一、新框架：PermissionChecker 三层权限体系

### 1.1 核心概念

#### 规则行为 (RuleBehavior)

| 行为 | 说明 |
|------|------|
| `allow` | 明确允许执行 |
| `deny` | 明确拒绝执行 |
| `ask` | 需要用户确认 |

#### 规则来源 (RuleSource)

按优先级从高到低：

| 来源 | 说明 |
|------|------|
| `policy` | 企业策略（最高优先级） |
| `project` | 项目级 `.claude/settings.json` |
| `user` | 用户级 `~/.claude/settings.json` |
| `session` | 会话临时规则（最低优先级） |

#### 规则匹配格式

- `tool_name` - 仅匹配工具名
- `tool_name:*` - 通配符匹配
- `tool_name:arg_pattern` - 匹配工具名和参数内容

### 1.2 默认规则

```python
# 读类工具默认 allow
"read_file" → allow
"list_files" → allow
"grep" → allow
"glob" → allow

# 写类工具默认 ask
"write_file" → ask
"edit_file" → ask

# 网络类工具默认 ask
"web_fetch" → ask
```

### 1.3 权限检查流程

```
检查权限 (check_permission):
  │
  ├─ 1. 静态规则层
  │   └─ 查找优先级最高的匹配规则
  │       ├─ deny → 返回拒绝
  │       ├─ allow → 返回允许
  │       └─ ask → 返回需确认，提供 suggested_rule 供会话级记忆
  │
  ├─ 2. 工具级别覆盖 (tool_overrides)
  │   └─ DENIED → 拒绝
  │   └─ REQUIRES_CONFIRM → 需确认
  │
  ├─ 3. 工具默认 permission_level
  │
  └─ 4. MCP 工具默认 ask
```

### 1.4 使用示例

```python
from maestro.tools.permissions import (
    PermissionChecker,
    PermissionRule,
    RuleBehavior,
    RuleSource,
)

# 初始化检查器
checker = PermissionChecker()

# 添加会话级规则（用于 "Yes, and don't ask again"）
checker.add_rule(PermissionRule(
    tool_pattern="write_file",
    behavior=RuleBehavior.ALLOW,
    source=RuleSource.SESSION,
))

# 持久化规则到用户配置
checker.persist_rule(rule, target=RuleSource.USER)

# 检查权限
result = await checker.check_permission(tool, args, context)

if result.behavior == "allow":
    # 执行工具
elif result.behavior == "require_confirmation":
    # 需要用户确认，可使用 result.suggested_rule 记住选择
elif result.behavior == "deny":
    # 拒绝执行
```

---

## 二、旧体系：AuthZ + ActionGate 动作分级授权

### 2.1 动作分级 (ActionLevel)

| 级别 | 说明 |
|------|------|
| `auto` | 立即执行并审计 |
| `requires_confirmation` | 生成待确认动作，需人工批准 |
| `deny` | 拒绝执行 |

### 2.2 默认策略配置

```python
DEFAULT_POLICIES = {
    "send_expedite_message.internal": "auto",
    "send_expedite_message.supplier": "requires_confirmation",
    "dispatch_work_order": "requires_confirmation",
    "update_work_order_status": "requires_confirmation",
    "send_notification": "requires_confirmation",
}
```

未知写操作默认 `requires_confirmation`（保守策略）。

### 2.3 ActionGate 闸口流程

```
request(action_type, description, params, executor):
  │
  ├─ AuthZ.decide() → 级别
  │
  ├─ 级别 = deny
  │   └─ 审计记录 → GateOutcome(status="denied")
  │
  ├─ 级别 = auto
  │   └─ 执行 executor → 审计记录 → GateOutcome(status="executed")
  │
  └─ 级别 = requires_confirmation
      ├─ 创建 PendingAction
      ├─ 存入 PendingActionStore
      ├─ 审计记录
      └─ GateOutcome(status="pending", action=...)

confirm(action_id, approved):
  │
  ├─ 从 PendingActionStore 取出
  ├─ approved = true → 执行 executor
  ├─ approved = false → 标记为 rejected
  └─ 审计记录
```

### 2.4 使用示例

```python
from maestro.foundation.authz import (
    AuthZ,
    ActionGate,
    PendingActionStore,
    gate_outcome_summary,
)
from maestro.foundation.audit import AuditLog

# 初始化组件
authz = AuthZ()
pending = PendingActionStore()
audit = AuditLog()
gate = ActionGate(authz, pending, audit)

# 请求执行动作
outcome = await gate.request(
    action_type="dispatch_work_order",
    description="派发工单 WO-001 到车间 A",
    params={"order_id": "WO-001", "workshop": "A"},
    executor=dispatch_work_order_fn,
)

# 处理结果
print(gate_outcome_summary(outcome))
# → "待确认 [action-xxx]: 派发工单 WO-001 到车间 A"

# 用户确认后执行
action, result = await gate.confirm(action_id="action-xxx", approved=True)
```

---

## 三、两道写护栏

调度引擎 (SchedulingEngine) 对写操作有双重保护：

### 护栏 1：前置断言 (Precondition)

在工具执行前检查业务规则，例如：
- 派单前检查物料是否齐套
- 催料前检查是否已在途且未超限

```python
# 注册工具时附加前置断言
tools.register(
    name="dispatch_work_order",
    handler=dispatch_handler,
    kind="write",
    precondition=make_dispatch_precondition(kitting, adapter),
)

# 技能级追加断言（不替换，只叠加）
skill_engine = SkillEngine(
    named_preconditions={
        "dispatch_ready": make_dispatch_precondition(...),
    },
)
```

### 护栏 2：ActionGate 授权

前置断言通过后，仍需经过 ActionGate 的权限检查和可能的用户确认。

---

## 四、桥接层：新旧体系协同

`tools/bridge.py` 提供了新工具框架到 foundation 工具库的桥接：

```python
def register_framework_tools(foundation_registry, gate=None):
    """把框架工具桥接进 foundation 工具库。

    传入 gate 时：
    - requires_confirm 工具被拦截 → 生成 PendingAction
    - 随 actions 事件下发前台确认卡片
    - 经 /chat/confirm 批准后真正执行
    """
```

### 桥接流程

```
ReAct AgentLoop 调用工具
  │
  ├─ foundation 工具库 (ToolRegistry)
  │
  ├─ 桥接 handler (bridge.py)
  │
  ├─ ToolManager.execute_tool()
  │
  ├─ PermissionChecker.check_permission()
  │   └─ require_confirmation
  │       └─ ActionGate.request() → PendingAction
  │           └─ 返回 blocked_by_permission
  │
  └─ 前端显示确认卡片 → /chat/confirm → ActionGate.confirm()
```

---

## 五、审计日志 (AuditLog)

### 数据模型

```python
class AuditEntry:
    timestamp: datetime
    actor: str              # "system", "scheduling_agent", "user"
    action: str             # 动作类型
    params: dict            # 参数
    authz_decision: str     # "auto", "requires_confirmation", "deny"
    result: dict            # 执行结果
```

### 持久化

- 内存列表（快速查询）
- JSONL 文件（持久化存储，每一行一条记录）
- 写失败告警但不阻断主流程

### API

```python
# 记录
entry = audit.record(
    actor="user",
    action="dispatch_work_order",
    params={"order_id": "WO-001"},
    authz_decision="requires_confirmation",
    result={"status": "executed"},
)

# 查询
entries = audit.query(action="dispatch_work_order", limit=100)
```

---

## 六、HTTP API 接口

完整契约见 `docs/api-contract/api-contract-v2.md`。

### 列出待确认动作

```http
GET /pending
```

### 确认动作

```http
POST /chat/confirm
Content-Type: application/json

{
  "action_id": "action-xxx",
  "approved": true
}
```

### 查询审计日志

```http
GET /audit
GET /audit/timeline
```

---

## 七、前端集成

### API 客户端

```typescript
// 列出待确认动作
const pending = await listPendingActions();

// 确认动作
const result = await confirmAction(actionId, approved);

// 查询审计日志
const audit = await fetchAuditTrail();
```

### 确认卡片流程

1. 聊天流 SSE 包含 `actions` 事件 → 显示待确认卡片
2. 用户点击批准/拒绝 → 调用 `/chat/confirm`
3. 刷新聊天流显示执行结果

---

## 八、引导层：工具权限级别

### ToolPermissionLevel

```python
class ToolPermissionLevel(str, Enum):
    AUTO = "auto"                    # 自动执行
    REQUIRES_CONFIRM = "requires_confirm"  # 需要确认
    DENIED = "denied"                # 拒绝
```

### 工具定义示例

```python
from maestro.tools.base import (
    ToolDef,
    ToolPermissionLevel,
    build_tool,
)

tool = build_tool(ToolDef(
    name="write_file",
    description="写入文件",
    input_schema=WriteFileArgs,
    execute=write_file_handler,
    permission_level=ToolPermissionLevel.REQUIRES_CONFIRM,
    is_readonly=False,
    is_destructive=False,
))
```

---

## 九、配置文件

### settings.json 格式

```json
{
  "permissions": {
    "rules": [
      {
        "tool": "write_file",
        "args": "*.md",
        "behavior": "allow"
      },
      {
        "tool": "execute_shell",
        "behavior": "deny"
      }
    ]
  }
}
```

加载顺序：
1. 用户级：`~/.claude/settings.json`
2. 项目级：`.claude/settings.json`

---

## 十、集成点

### Bootstrap (bootstrap.py)

```python
# 组装根
def build_platform():
    audit = AuditLog(settings.audit_log_file)
    authz = AuthZ()
    pending = PendingActionStore()
    gate = ActionGate(authz, pending, audit)

    # 注册工具 + 桥接新框架工具
    tools = ToolRegistry()
    register_builtin_tools(tools, adapter, gate, ...)
    register_framework_tools(tools, gate=gate)  # ← 桥接

    # ...
```

### 调度引擎 (agent_loop.py)

```python
# 工具调用时的护栏
async def _handle_call(name, args, st):
    # 1. 白名单检查
    if name not in self._allowed:
        return blocked

    # 2. 重复调用检测
    if seen[key] > 1:
        return blocked

    # 3. 前置断言检查
    if tool.kind == "write" and tool.precondition:
        result = await tool.precondition(args)
        if not result.ok:
            return blocked

    # 4. 执行（内部仍有 ActionGate 权限检查）
    result = await self._tools.execute(name, args)
```

---

## 十一、设计决策

### 为什么同时保留两套体系？

- **向后兼容** - 现有业务代码基于 ActionGate
- **逐步迁移** - 新工具用 PermissionChecker，旧工具逐步迁移
- **双重保险** - 桥接层协同两者

### 为什么 PendingAction 存在内存中？

- 会话重启后待确认动作失效是可接受的（用户重新发起即可）
- 简化实现，避免状态持久化的复杂性
- 未来 v0.2 可考虑持久化

### 为什么未知写操作默认 requires_confirmation？

- 安全优先原则
- 宁可多问一次，不可误操作一次
- 可通过策略覆盖默认行为

---

## 十二、未来：v0.2 路线图

| 功能 | 状态 | 说明 |
|------|------|------|
| 策略持久化 | 预留 | 权限规则保存到配置文件 |
| 会话级规则记忆 | 已预留 | "Yes, and don't ask again" |
| 更细粒度参数检查 | 规划中 | 工具参数内容的规则匹配 |
| AI 驱动分类器 | 规划中 | 智能判断操作风险 |
| 安全事件告警 | 规划中 | 异常权限决策实时通知 |

---

## 十三、安全最佳实践

1. **默认安全** - 新工具默认 `requires_confirmation`
2. **最小权限** - 只给必要的工具白名单
3. **审计追踪** - 定期审查审计日志
4. **分层防护** - 前置断言 + ActionGate 双重保护
5. **用户教育** - 清晰描述待确认动作的后果

---

## 参考

- [Claude Code 权限系统](https://anthropic.com)
- [OpenHands 护栏设计](https://github.com/All-Hands-AI/OpenHands)
- [Model Context Protocol (MCP)](https://modelcontextprotocol.io)
