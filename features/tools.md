# Tools — 工具系统模块文档

## Overview

`scheduling_platform/src/scheduling_platform/tools/` 是平台的通用工具框架，借鉴 Claude Code 的三层工具模型：

- **CoreTool（协议）**：`Tool` Protocol，纯接口，定义工具必须具备的属性与方法
- **Tool（宿主）**：`BaseTool` 抽象基类，带默认实现的工具载体
- **ToolDef + build_tool（构建器）**：声明式工具定义 + 安全默认值填充

在此之上提供：注册表（`ToolRegistry`）、三级权限（`PermissionChecker`）、执行管理（`ToolManager`，含确认流程与大结果落盘）、内置工具集（`builtins/`），以及与 MCP 工具融合的 `IntegratedToolManager`。

> **接入状态**：本模块目前是自包含的框架层，尚未接入 `bootstrap.py::build_platform()`。SchedulingEngine 现有的 ReAct 工具白名单走 `engines/scheduling/` 自己的护栏体系；本模块是面向后续统一工具池的新框架。MCP 侧文档见 [features/mcp.md](mcp.md)。

## 目录结构

```
tools/
├── __init__.py            # 导出 + initialize_tools()
├── base.py                # Tool 协议 / BaseTool / ToolDef / build_tool
├── registry.py            # ToolRegistry 单例（主名称 + 别名）
├── permissions.py         # PermissionChecker（auto / requires_confirm / denied）
├── manager.py             # ToolManager（执行管道、确认流程、大结果落盘）
├── integrated_manager.py  # IntegratedToolManager（内置 + MCP 工具融合）
├── mcp_wrapper.py         # 将 MCPTool 包装为本地 Tool
├── mcp_resources.py       # list_mcp_resources / read_mcp_resource（工厂创建）
└── builtins/
    ├── filesystem.py      # read_file / write_file / edit_file / list_files
    ├── search.py          # grep / glob
    ├── todo.py            # todo_write（会话任务清单）
    ├── web.py             # web_fetch（网页抓取）
    ├── tool_search.py     # tool_search（延迟工具检索）
    └── sleep.py           # sleep
```

---

## Core Types（`base.py`）

### 枚举

| 枚举 | 取值 | 说明 |
|------|------|------|
| `ToolPermissionLevel` | `auto` / `requires_confirm` / `denied` | 工具权限级别 |
| `ToolResultStatus` | `success` / `error` / `cancelled` | 执行结果状态 |

### ToolResult — 执行结果

```python
@dataclass
class ToolResult:
    status: ToolResultStatus
    content: Any                              # 成功时的结果内容
    error_message: Optional[str] = None       # 失败原因
    metadata: Dict[str, Any] = {}
    mcp_meta: Optional[Dict[str, Any]] = None # MCP 工具透传的 _meta
```

### Tool 协议属性

每个工具（无论如何构建）都具备以下属性：

| 属性 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `name` | str | - | 工具主名称 |
| `description` | str | - | 描述，随工具列表发给 LLM |
| `input_schema` | type[BaseModel] | - | Pydantic 输入模型（自动生成 JSON Schema） |
| `aliases` | list[str] | `[]` | 别名，注册与查找时均可命中 |
| `permission_level` | ToolPermissionLevel | `auto` | 权限级别 |
| `is_readonly` | bool | `False` | 是否只读 |
| `is_enabled` | bool | `True` | 是否启用（禁用的工具拒绝执行） |
| `is_concurrency_safe` | bool | `False` | 是否可安全并发 |
| `is_destructive` | bool | `False` | 是否有破坏性 |
| `max_result_size_chars` | int | `10000` | 结果上限，超过则落盘（见下文） |
| `is_mcp` | bool | `False` | 是否为 MCP 包装工具 |
| `mcp_info` | dict \| None | `None` | `{"server_name", "tool_name"}` |
| `should_defer` | bool | `False` | 是否延迟加载（不进初始工具列表） |
| `always_load` | bool | `False` | 强制初始加载（优先于 `should_defer`） |
| `search_hint` | str \| None | `None` | 延迟工具的检索提示词 |

方法：`execute()`（异步执行）、`validate_input()`（业务校验，返回错误字符串或 `None`）、`get_tool_use_summary()` / `get_activity_description()`（UI 展示钩子）、`get_description()`。

### 两种定义工具的方式

**方式一：声明式（推荐）** — `ToolDef` + `build_tool()`，未填字段自动落到安全默认值：

```python
from pydantic import BaseModel, Field
from scheduling_platform.tools import ToolDef, ToolResult, ToolResultStatus, build_tool, ToolPermissionLevel

class MyArgs(BaseModel):
    order_id: str = Field(description="订单号")

async def my_execute(args: MyArgs, context: dict, on_progress=None) -> ToolResult:
    return ToolResult(status=ToolResultStatus.SUCCESS, content={"order_id": args.order_id})

MyTool = build_tool(ToolDef(
    name="my_tool",
    description="示例工具",
    input_schema=MyArgs,
    execute=my_execute,
    permission_level=ToolPermissionLevel.AUTO,
    is_readonly=True,
))
```

**方式二：继承 `BaseTool`** — 覆写类属性并实现 `execute()`，适合有复杂内部状态的工具。

工具可通过 `to_anthropic_tool()` 转换为 Anthropic API 的工具格式（`name` / `description` / `input_schema` JSON Schema）。

---

## ToolRegistry（`registry.py`）

进程级单例（模块底部导出 `registry` 实例）。注册时主名称与所有别名都会建立索引；别名不会覆盖已存在的名称。

| 方法 | 说明 |
|------|------|
| `register(tool)` / `unregister(name)` | 注册 / 注销（连同别名） |
| `get(name)` / `find_by_name(name)` | 按主名称或别名查找 |
| `list_all()` | 全部工具（按主名称去重） |
| `list_enabled()` | 仅启用的工具 |
| `list_initial_load()` | 初始加载集：`not should_defer or always_load` |
| `list_deferred()` | 延迟加载集：`should_defer and not always_load` |
| `to_anthropic_tools()` | 初始加载集转 Anthropic 工具列表 |

### 延迟加载（Deferred Loading）

参考 Claude Code 的 deferred tools 机制：`should_defer=True` 的工具不进入初始工具列表（不占上下文），需要时通过 `tool_search` 工具按名称或关键词（命中 `name`/`description`/`search_hint`）检索，取回完整定义后即可按名调用；`always_load=True` 可强制豁免。MCP 工具默认延迟加载，除非服务器在工具 `_meta` 里声明 `anthropic/alwaysLoad: true`（见 `mcp_wrapper.py`）。

`tool_search` 查询形式（与 Claude Code 的 ToolSearch 一致）：
- `select:tool_a,tool_b` — 按名称精确选取（已在初始列表的名字会归入 `already_loaded`）
- `keyword one two` — 关键词计分检索
- `+must other` — `+` 前缀的词必须命中

---

## PermissionChecker（`permissions.py`）

三级权限判定，`check_permission()` 的判定顺序：

```
工具级覆盖(set_tool_permission) 否则用工具自身 permission_level
    │
    ├─ denied            → behavior="deny"
    ├─ requires_confirm  → behavior="require_confirmation"
    ├─ (级别为 auto 但 is_mcp=True) → behavior="require_confirmation"   ← MCP 工具默认需确认
    └─ auto              → behavior="allow"
```

返回 `PermissionResult(behavior, updated_input, reason)`。

另提供规则接口：`add_allow_rule(tool_pattern, input_pattern)` / `add_deny_rule(...)` 存储允许/拒绝规则，`matches_deny_rule(tool_name)` 支持 `*` 通配符匹配。**注意**：当前 `check_permission()` 仅使用级别覆盖判定，allow/deny 规则需调用方显式检查（`matches_deny_rule`），尚未织入主判定链。

---

## ToolManager（`manager.py`）

工具执行管道，`execute_tool(tool_name, args, context, on_progress)` 依次经过：

```
① 查找工具（主名称/别名） ──未找到──→ ERROR "Tool not found"
② is_enabled 检查         ──禁用────→ ERROR "Tool is disabled"
③ input_schema(**args) 解析 ──失败──→ ERROR "Invalid arguments"
④ tool.validate_input()    ──有错──→ ERROR（业务校验信息）
⑤ 权限检查
    ├─ deny                 → ERROR "Permission denied"
    ├─ require_confirmation → CANCELLED + {requires_confirmation: true, confirmation_id}
    └─ allow ↓
⑥ tool.execute()           ──异常──→ ERROR（异常信息）
⑦ 大结果处理（超限落盘）
```

### 确认流程

权限判定为需确认时，执行被挂起并返回 `confirmation_id`（形如 `confirm_0`），随后：

```python
manager.get_pending_confirmations()
# {"confirm_0": {"tool_name": "...", "args": {...}, "description": "..."}}

await manager.confirm_execution("confirm_0", approved=True)   # 批准 → 真正执行
await manager.confirm_execution("confirm_0", approved=False)  # 拒绝 → CANCELLED
```

待确认项存在内存字典中，进程重启即失效。语义上与平台 ActionGate 的 `requires_confirmation` 一致（工具层确认 vs 业务动作层确认）。

### 大结果落盘

执行成功后，若 `json.dumps(content)` 长度超过工具的 `max_result_size_chars`（默认 10000，可设 `float('inf')` 关闭），完整结果写入临时 `.json` 文件，`content` 被替换为：

```json
{"result_persisted": true, "path": "/tmp/xxx.json", "preview": "前 1000 字符..."}
```

避免超大结果撑爆 LLM 上下文，同时保留完整数据可供后续读取。

### 其它方法

| 方法 | 说明 |
|------|------|
| `get_tools_for_agent()` | 初始加载工具的 Anthropic 格式列表 |
| `get_all_tools_metadata()` | 全部工具元数据（权限、只读、延迟等标记） |
| `assemble_tool_pool(mcp_tools)` | 内置工具 + MCP 工具合并，按名称去重（内置优先） |

---

## Builtins（`builtins/`）

`initialize_tools()`（即 `register_all_builtins()`）一次性注册以下内置工具。文件类工具的路径一律经 `_resolve_and_validate_path` 限制在项目根目录内（越界报错）；平台**不提供 shell 执行工具**（安全取舍，曾有 `execute_shell` 后移除）。

| 工具 | 权限 | 只读 | 延迟 | 说明 |
|------|------|------|------|------|
| `read_file` | auto | ✅ | - | 读文件，支持 `offset`/`limit` 按行截取；结果不落盘（`max_result_size_chars=inf`） |
| `list_files` | auto | ✅ | - | 列目录（名称/路径/类型/大小） |
| `grep` | auto | ✅ | - | 目录递归正则搜索，跳过隐藏文件，最多 100 条匹配 |
| `glob` | auto | ✅ | - | 通配符匹配文件（如 `**/*.py`），按修改时间倒序，最多 100 条并标记截断 |
| `todo_write` | auto | ✅ | - | 会话任务清单（按 `agent_id`/`session_id` 分键存进程内；全部 completed 自动清空） |
| `tool_search` | auto | ✅ | always_load | 检索延迟加载工具，返回完整定义（见上文「延迟加载」） |
| `sleep` | auto | ✅ | ✅ | 等待 N 秒（上限 300），用于轮询外部状态 |
| `web_fetch` | requires_confirm | ✅ | ✅ | 抓取 URL 转纯文本；http 升级 https，跨主机重定向返回提示不自动跟随；依赖 httpx |
| `write_file` | requires_confirm | - | - | 写文件（自动创建父目录），破坏性 |
| `edit_file` | requires_confirm | - | - | 精确字符串替换（old_string 不存在则报错），破坏性 |

另有两个绑定 `MCPManager` 实例的工具，由 `IntegratedToolManager` 构造时经 `mcp_resources.py` 工厂注册（均只读/auto/延迟加载）：

| 工具 | 说明 |
|------|------|
| `list_mcp_resources` | 列出已连接 MCP 服务器的资源，可按 `server` 过滤（未知服务器报错并列出可用项） |
| `read_mcp_resource` | 按 `server` + `uri` 读取 MCP 资源内容 |

规律：**只读且无外联的工具 auto 放行；写文件与外网访问一律需确认**。

上述工具迁移对照（源：Claude Code）：`glob`←GlobTool、`todo_write`←TodoWriteTool、`web_fetch`←WebFetchTool、`tool_search`←SearchExtraTools/ToolSearch、`sleep`←SleepTool、`list_mcp_resources`/`read_mcp_resource`←ListMcpResources/ReadMcpResourceTool。未迁移：Bash/PowerShell（平台不开 shell）、AskUserQuestion（平台已有澄清流程）、Skill 系（平台有自己的技能引擎）、Task/Agent/Team/PlanMode/Artifact/LSP/REPL 等（依赖 Claude Code 宿主设施）、WebSearch（需外部搜索 API）。

---

## IntegratedToolManager（`integrated_manager.py`）

内置工具与 MCP 工具的融合层，内部组合 `ToolManager` + `MCPManager`：

```
IntegratedToolManager
├── tool_manager: ToolManager        # 执行管道 / 确认流程
├── mcp_manager: MCPManager          # MCP 连接管理（见 features/mcp.md）
├── __init__                         # 注册 list_mcp_resources / read_mcp_resource（绑定本实例）
└── refresh_mcp_tools()              # 注销旧 MCP 包装 → 重新包装注册
```

- `refresh_mcp_tools()`：把 `MCPManager.get_all_tools()` 逐个经 `create_mcp_tool_wrapper()` 包装为本地 `Tool` 注册进 registry；重复调用会先注销上一批，适合在 MCP `tools_changed` 事件后调用。
- `assemble_tool_pool()`：遍历所有 **connected** 状态的 MCP 连接，即时包装其工具并与内置工具池合并（同名时内置工具优先）。
- `execute_tool` / `confirm_execution` / `get_pending_confirmations` 等直接代理给 `ToolManager`，MCP 工具与内置工具走完全相同的执行管道与确认流程。

MCP 包装工具的命名规则、权限默认值见 [features/mcp.md](mcp.md) 的「工具命名规则」与「安全」章节。

---

## 使用示例

```python
from scheduling_platform.tools import initialize_tools, ToolManager

initialize_tools()                       # 注册全部内置工具
manager = ToolManager()

# 只读工具：auto 直接执行
result = await manager.execute_tool("read_file", {"file_path": "README.md"}, context={})
assert result.status == "success"

# 写工具：挂起待确认
result = await manager.execute_tool(
    "write_file", {"file_path": "/tmp/a.txt", "content": "hi"}, context={})
cid = result.content["confirmation_id"]
final = await manager.confirm_execution(cid, approved=True)
```

---

## Design Decisions

### 为什么用 ToolDef + build_tool 而不是纯继承？

声明式定义把「工具是什么」（名称/schema/权限标记）与「工具做什么」（execute 函数）分离，安全属性有统一默认值、不可遗漏；这也是 Claude Code `buildTool()` 的模式。继承 `BaseTool` 仍保留给有状态的复杂工具。

### 为什么权限判定在 Manager 而不是工具内部？

工具只声明自己的 `permission_level`，判定与覆盖（`set_tool_permission`）集中在 `PermissionChecker`，策略可在不改工具代码的前提下调整；MCP 工具默认需确认这条兜底规则也只需写一处。

### 为什么大结果落盘而不是截断？

截断会丢数据；落盘 + preview 让 LLM 拿到摘要的同时，后续步骤仍可用 `read_file` 精确读取完整结果。

## 相关文档

- MCP 客户端与包装：[features/mcp.md](mcp.md)
- 平台主循环与现有 ReAct 工具白名单：[features/main-loop.md](main-loop.md)
- 技能系统的 allowed_tools：[features/agent-skills.md](agent-skills.md)
