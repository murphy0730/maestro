# MCP — Model Context Protocol 客户端模块文档

## Overview

`maestro/src/maestro/mcp/` 是平台的 MCP（Model Context Protocol）客户端实现，允许平台连接外部 MCP 服务器，发现并调用其提供的工具（tools）与资源（resources），从而在不修改平台代码的情况下扩展 Agent 能力。

- 协议：JSON-RPC 2.0，协议版本 `2024-11-05`，客户端标识 `manufacturing-agent/0.1.0`
- 传输：当前仅实现 **stdio**（子进程 + 换行分隔 JSON）；SSE / WebSocket / HTTP 已定义枚举但未实现
- 能力声明：`tools` + `resources`（不含 sampling / prompts）
- MCP 工具经 `tools/mcp_wrapper.py` 包装后进入平台统一工具池，**默认需人工确认**

> **接入状态**：MCP 已接入运行时主链。FastAPI lifespan 启动时读取 `Settings.mcp_servers`，连接服务器、发现工具并 bridge 到 SchedulingEngine；关闭时断开连接。配置可放在 `<MAESTRO_DATA_DIR>/settings.json` 或通过 `MCP_SERVERS` 环境变量提供 JSON。工具框架侧文档见 [features/tools.md](tools.md)。

最小配置示例：

```json
{
  "mcp_servers": [{
    "name": "mes",
    "transport_type": "stdio",
    "command": "python",
    "args": ["/opt/mes-mcp/server.py"]
  }]
}
```

## 目录结构

```
mcp/
├── __init__.py     # 导出 + initialize_mcp() → MCPManager
├── types.py        # 配置 / 工具 / 资源 / 连接状态等数据类型
├── transport.py    # MCPTransport 抽象 + StdioMCPTransport
├── client.py       # MCPClient：initialize → tools/list → resources/list
├── discovery.py    # 从响应中解析工具与资源定义
├── execution.py    # tools/call 与 resources/read 的请求实现
└── manager.py      # MCPManager：多服务器连接管理 + 事件
```

分层关系：

```
MCPManager（多服务器编排 + 事件）
    │  1:N
    ▼
MCPClient（协议层：握手 / 发现 / 调用）
    │        ├── discovery.py（解析 tools/list、resources/list 响应）
    │        └── execution.py（发送 tools/call、resources/read）
    ▼
MCPTransport（传输层）
    └── StdioMCPTransport（子进程 stdio，换行分隔 JSON）
```

---

## 类型定义（`types.py`）

### MCPServerConfig — 服务器配置

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | str | ✅ | 服务器名，也是工具全限定名的一部分 |
| `transport_type` | MCPTransportType | ✅ | `stdio` / `sse` / `websocket` / `http`（当前仅 stdio 可用） |
| `command` | str | stdio 必填 | 启动命令，如 `npx`、`python` |
| `args` | list[str] | ❌ | 命令参数 |
| `url` | str | ❌ | 远程传输的地址（预留） |
| `env` | dict[str,str] | ❌ | 附加环境变量（与当前进程环境合并） |
| `scope` | MCPConfigScope | ❌ | 配置作用域，默认 `project`（`dynamic`/`project`/`user`/`local`/`enterprise`/`managed`/`claudeai`） |

### 其它类型

| 类型 | 说明 |
|------|------|
| `MCPTool` | 工具定义：`name` / `description` / `input_schema`(JSON Schema) / `server_name` / `metadata`（来自 `_meta`） |
| `MCPResource` | 资源定义：`uri` / `name` / `description` / `mime_type` |
| `MCPResourceContents` | 资源内容：`uri` / `text` 或 `blob` / `mime_type` |
| `MCPServerConnectionStatus` | `connected` / `disconnected` / `error` / `needs_auth` |
| `MCPServerConnection` | 连接快照：`name` / `config` / `status` / `tools` / `resources` / `error` |

---

## 传输层（`transport.py`）

`MCPTransport` 抽象定义四个方法：`connect` / `disconnect` / `send_message` / `receive_message`。

### StdioMCPTransport

- **connect**：以 `command + args` 启动子进程，`env` 与当前进程环境合并；启动后台读循环任务。
- **send_message**：消息序列化为单行 JSON + `\n` 写入子进程 stdin。
- **读循环**：从 stdout 按 4096 字节读入，按 `\n` 切分逐行 `json.loads`，解析失败的行直接跳过，成功的消息进入内部队列。
- **receive_message**：从队列取一条消息，**30 秒超时返回 `None`**。
- **disconnect**：取消读循环 → `terminate()` 子进程 → 等待 5 秒仍未退出则 `kill()`。

其它传输类型（`sse` / `websocket` / `http`）目前只有枚举定义，`MCPClient.connect()` 遇到会抛 `ValueError: Unsupported transport`。

---

## 协议层（`client.py`）

`MCPClient` 持有一个服务器配置，`connect()` 执行完整握手序列：

```
MCPClient.connect()
    │
    ① initialize          ← protocolVersion=2024-11-05, capabilities={tools,resources}
    │      （30s 超时；error 响应 → 抛异常；记录 sessionId）
    ② tools/list          → discovery.discover_tools_from_response()
    │      （30s 超时；超时则工具列表为空，不报错）
    ③ resources/list      → discovery.discover_resources_from_response()
    │      （30s 超时；超时则资源列表为空，不报错）
    ▼
MCPServerConnection(status=connected, tools=[...], resources=[...])
```

任一步抛异常时不向上传播，而是返回 `MCPServerConnection(status=error, error="...")`——连接失败被降级为状态，由上层决定重试或提示。

请求 id 由客户端自增维护；接收端以 `response['id'] == request_id` 匹配响应，忽略其它消息（如服务器通知）。

其它方法：`call_tool(name, arguments)`、`read_resource(uri)`（委托给 `execution.py`）、`get_tools()`、`get_resources()`、`disconnect()`。

---

## 发现（`discovery.py`）

从 `tools/list` / `resources/list` 响应解析定义：

- 工具：`name` 必取，`description` 缺省为空串；`inputSchema` 缺失时回退为空 object schema（`{"type":"object","properties":{},"required":[]}`）；工具定义中的 `_meta` 存入 `MCPTool.metadata`（用于 `anthropic/alwaysLoad` 等声明）。
- 资源：`uri` 必取，`mimeType` 缺省 `text/plain`。

## 执行（`execution.py`）

| 函数 | JSON-RPC 方法 | 超时 | 返回 |
|------|---------------|------|------|
| `call_mcp_tool(transport, tool_name, arguments)` | `tools/call` | 60s | `response.result`（含 `content` 与可选 `_meta`） |
| `read_mcp_resource(transport, uri)` | `resources/read` | 30s | `result.contents` 列表 |

两者的错误语义一致：响应含 `error` → 抛 `RuntimeError("MCP error: ...")`；超时未匹配到响应 → 抛 `TimeoutError`。请求 id 用毫秒时间戳。

---

## MCPManager（`manager.py`）

多服务器编排层，`initialize_mcp()` 返回其实例。

### 生命周期方法

| 方法 | 说明 |
|------|------|
| `add_server(config)` | 登记服务器（同名已存在则先移除旧的） |
| `connect_server(name)` | 建立连接并缓存 `MCPServerConnection`；按结果触发事件 |
| `connect_all()` / `disconnect_all()` | 批量连接 / 断开 |
| `remove_server(name)` | 断开并移除，触发 `disconnected` |
| `get_connection(name)` / `get_all_connections()` | 查询连接快照 |
| `get_all_tools()` | 汇总所有 **connected** 服务器的 `MCPTool` |
| `call_tool(server_name, tool_name, arguments)` | 路由到对应客户端调用工具 |
| `read_resource(server_name, uri)` | 路由读取资源 |

### 事件

`manager.events.on(event, handler)` 注册回调，handler 异常被吞掉不影响其它 handler：

| 事件 | 触发时机 | 参数 |
|------|----------|------|
| `connected` | 服务器连接成功 | `name` |
| `tools_changed` | 连接成功后工具列表就绪 | `name, tools` |
| `auth_required` | 连接状态为 `needs_auth` | `name` |
| `error` | 连接过程抛异常 | `name, exception` |
| `disconnected` | 服务器被移除 | `name` |

典型用法：监听 `tools_changed` 后调用 `IntegratedToolManager.refresh_mcp_tools()` 重建工具池。

---

## 工具命名规则

MCP 工具进入平台工具池时（`tools/mcp_wrapper.py`），名称统一为：

```
mcp__{server_name}__{tool_name}
```

| 服务器名 | 工具名 | 平台内全限定名 |
|----------|--------|----------------|
| `github` | `create_issue` | `mcp__github__create_issue` |
| `erp` | `query_stock` | `mcp__erp__query_stock` |

双下划线分隔避免与内置工具重名；`mcp_info` 字段保留原始 `server_name` / `tool_name` 供回调路由。

## 包装与集成（`tools/mcp_wrapper.py`）

`create_mcp_tool_wrapper(mcp_tool, mcp_manager)` 把 `MCPTool` 变成平台 `Tool`：

1. **动态输入模型**：根据 JSON Schema 的 `properties`/`required` 用 `pydantic.create_model` 生成输入类（类型映射：string→str、integer→int、number→float、boolean→bool、array→list、object→dict；非必填字段为 Optional 默认 None）。
2. **执行代理**：`execute()` 转发到 `mcp_manager.call_tool(server, tool, args)`，结果的 `content` 进 `ToolResult.content`，`_meta` 进 `ToolResult.mcp_meta`；异常转为 `ERROR` 结果。
3. **默认标记**：`permission_level=REQUIRES_CONFIRM`、`is_mcp=True`、`is_readonly=True`（协议无法验证副作用，标记只读仅表示平台不将其视为破坏性写入，确认仍必须）。
4. **延迟加载**：默认 `should_defer=True`；服务器在工具 `_meta` 中声明 `anthropic/alwaysLoad: true` 时改为初始加载。

### MCP 资源工具（`tools/mcp_resources.py`）

除工具包装外，`IntegratedToolManager` 构造时会注册两个绑定其 `MCPManager` 的平台工具，把 MCP 资源开放给 Agent（迁移自 Claude Code 的 ListMcpResources/ReadMcpResourceTool，均只读 / auto / 延迟加载）：

- `list_mcp_resources(server?)` — 列出已连接服务器的资源；指定的 `server` 不存在时报错并附可用服务器列表
- `read_mcp_resource(server, uri)` — 读取指定资源的 `contents`

## 安全

| 机制 | 说明 |
|------|------|
| 默认需确认 | 包装器设 `REQUIRES_CONFIRM`；且 `PermissionChecker` 对 `is_mcp=True` 的工具兜底强制确认（即使级别被改回 auto） |
| 统一执行管道 | MCP 工具与内置工具走同一 `ToolManager` 管道（schema 校验 → 权限 → 确认 → 执行） |
| 超时保护 | 握手/发现 30s、工具调用 60s、资源读取 30s，防止挂死 Agent 循环 |
| 失败降级 | 连接失败不抛异常，转为 `status=error` 的连接快照 |

---

## 使用示例

```python
from maestro.mcp import MCPServerConfig, MCPTransportType, initialize_mcp
from maestro.tools import IntegratedToolManager

# 1. 配置并连接 MCP 服务器（stdio）
mcp = initialize_mcp()
await mcp.add_server(MCPServerConfig(
    name="filesystem",
    transport_type=MCPTransportType.STDIO,
    command="npx",
    args=["-y", "@modelcontextprotocol/server-filesystem", "/data"],
    env={"LOG_LEVEL": "info"},
))
conn = await mcp.connect_server("filesystem")
print(conn.status, [t.name for t in conn.tools])

# 2. 融合进平台工具池
itm = IntegratedToolManager(mcp_manager=mcp)
await itm.refresh_mcp_tools()

# 3. 通过统一管道调用（首次返回待确认）
result = await itm.execute_tool(
    "mcp__filesystem__read_file", {"path": "/data/a.txt"}, context={})
cid = result.content["confirmation_id"]
final = await itm.confirm_execution(cid, approved=True)

# 4. 直接读取 MCP 资源
contents = await mcp.read_resource("filesystem", "file:///data/a.txt")
```

---

## 故障排查

### 连接后 status=error

- 查看 `connection.error` 字段（连接异常信息会记录在此）。
- `Unsupported transport`：配置了 stdio 以外的传输类型，当前未实现。
- `MCP initialize timed out`：子进程启动了但 30 秒内没有回应 initialize——确认命令确实是 MCP 服务器、输出为换行分隔 JSON（stderr 的日志不影响，但 stdout 混入非 JSON 行会被跳过）。

### 连接成功但没有工具

- `tools/list` 超时会静默置空工具列表（不算连接失败）——检查服务器是否实现了 `tools/list`。
- 工具在但 Agent 看不到：MCP 工具默认延迟加载（`should_defer=True`），不进初始工具列表；让服务器声明 `_meta: {"anthropic/alwaysLoad": true}` 或在平台侧改用 `registry.list_deferred()` 检索加载。

### 调用报错

- `RuntimeError: MCP error: ...`：服务器返回了 JSON-RPC error，信息来自服务器本身。
- `TimeoutError: MCP tool call timed out`：单次调用超过 60 秒。
- `RuntimeError: Server not found`：`call_tool` 的 `server_name` 未经 `add_server` 登记。
- 执行返回「需要确认」不是错误：见 [features/tools.md](tools.md) 的确认流程。

---

## 当前限制（TODO）

- 仅支持 stdio 传输；SSE / WebSocket / HTTP 待实现
- 不支持 MCP 的 prompts / sampling 能力，也无 OAuth 认证流（`needs_auth` 状态已预留）
- 当前仅支持 settings 中声明的服务器；尚未实现 Claude `.mcp.json` 的兼容加载
- CLI 需要显式调用 `Platform.connect_mcp()`；HTTP 主流程会在 lifespan 自动连接
- 无自动重连；`tools_changed` 仅在连接成功时触发一次（不监听服务器端的 listChanged 通知）

## 相关文档

- 工具框架与包装细节：[features/tools.md](tools.md)
- 平台主循环：[features/main-loop.md](main-loop.md)
- MCP 官方协议：https://modelcontextprotocol.io
