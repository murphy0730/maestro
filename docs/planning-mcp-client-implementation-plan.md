# Manufacturing Agent 排产 MCP Client 实现方案

## 1. 背景与目标

Manufacturing Agent 已具备通用 stdio MCP Client、Capability Registry、Policy Gate、运行时工具循环和连接器管理接口。本方案不重写 MCP Client，而是在现有架构上补齐排产查询全流程所需的本地信任策略、错误传播、结构化结果处理、配置界面和端到端验证。

术语约定：

- `planning` 表示排产，包括候选方案、订单排产、工序排产和排产指标。
- `dispatching` 表示调度，例如现场派工、事件驱动响应和在线重调度。
- 本次新增的配置、测试、示例服务器名和领域工具名统一使用 `planning`。
- Runtime 保持领域中立；排产业务逻辑只能来自 MCP 工具或可选 Skill，不能进入 `maestro/src/maestro/runtime/`。

本期目标：

1. 连接同机部署的 `llm4drd` stdio MCP Server。
2. 自动发现并注册 Server v2 发布的 28 个排产工具，不在 Client 硬编码工具目录。
3. 由本地管理员把指定工具声明为可信只读，查询时不触发写操作审批。
4. 未受信任或未来新增的 MCP 工具继续按高风险写操作处理。
5. 正确传播 MCP `isError` 和结构化结果。
6. 完成 `/runs -> LLM -> MCP -> llm4drd -> LLM 最终回答` 的真实端到端测试。

本期不包含：

- 在 Runtime 中加入任何排产领域代码。
- 支持远程 HTTP、SSE 或 Streamable HTTP MCP 传输。
- 允许模型修改 MCP Server 配置或信任策略。
- 绕过 Policy Gate 执行排产写操作，或根据远端 annotation 自动授予低风险权限。

## 2. 现有能力与缺口

现有能力：

- `maestro/mcp/transport.py`：stdio 子进程和逐行 JSON-RPC。
- `maestro/mcp/client.py`：初始化、工具发现和工具调用。
- `maestro/mcp/manager.py`：服务器生命周期与 Capability 注册。
- `maestro/runtime/mcp.py`：MCP Capability 执行边界。
- `maestro/foundation/mcp_config_store.py`：`settings.json` 持久化。
- `maestro/api/routes/mcp.py`：连接器管理接口。
- FastAPI lifespan 启动时自动连接已配置服务器。

主要缺口：

- 所有远端 MCP 工具目前统一注册为 `writes=true, risk=high`，只读查询也需要审批。
- `tools/call` 返回 `isError=true` 时，运行时可能仍把调用包装为成功。
- 尚未优先利用 `structuredContent`。
- 配置契约没有工具级只读白名单。
- 缺少真实排产 MCP Server 的 Runtime 端到端测试。

## 3. 总体调用链

```text
POST /runs
  -> RunCoordinator
  -> LLM 看到 mcp__planning__* 工具
  -> Policy Gate 检查本地 CapabilitySpec
  -> MCPManager executor
  -> MCPClient.tools/call
  -> stdio MCP Server 子进程
  -> llm4drd Planning Query REST API
  -> MCP 结构化结果
  -> role=tool 回填模型
  -> 最终中文回答
```

用户没有显式选择工具时，当前 Runtime 会向模型提供注册表中的可用 Capability。因此连接成功后，不需要在 `/runs` 请求中硬编码排产工具名。

## 4. MCP 配置模型扩展

### 4.1 数据模型

修改：

```text
maestro/src/maestro/mcp/types.py
```

为 `MCPServerConfig` 增加本地工具策略：

```python
@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    command: str
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    read_only_tools: tuple[str, ...] = ()
```

`from_dict()` 和 `to_dict()` 必须兼容旧配置：缺少 `read_only_tools` 时使用空数组，所有工具保持当前保守策略。

### 4.2 配置示例

```json
{
  "mcp_servers": {
    "planning": {
      "command": "/Users/zhouwentao/Desktop/llm4drd/.venv/bin/python",
      "args": [
        "/Users/zhouwentao/Desktop/llm4drd/mcp_server/server.py"
      ],
      "env": {
        "PLANNING_API_BASE_URL": "http://127.0.0.1:8888"
      },
      "enabled": true,
      "read_only_tools": [
        "list_planning_rules",
        "get_planning_overview",
        "compare_planning_solutions",
        "search_planning_entities",
        "diagnose_bottleneck",
        "explain_order_delay",
        "get_order_planning",
        "get_operation_planning",
        "describe_whatif_scenario",
        "get_whatif_run",
        "compare_whatif_runs",
        "get_scheduling_status",
        "list_planning_objectives",
        "get_planning_task",
        "get_insertion_schedule",
        "get_online_dispatch_status"
      ]
    }
  }
}
```

使用绝对 Python 和脚本路径，避免 Agent 工作目录变化造成模块解析失败。

## 5. 本地只读信任策略

### 5.1 注册规则

修改：

```text
maestro/src/maestro/mcp/manager.py
```

每次发现工具后，仅根据本地 `read_only_tools` 决定 Capability 元数据：

```python
remote_requires_governance = (
    tool.annotations.get("readOnlyHint") is False
    or tool.annotations.get("destructiveHint") is True
)
is_read_only = tool.name in config.read_only_tools and not remote_requires_governance

self._connector.register(
    config.name,
    tool.name,
    description=tool.description,
    input_schema=tool.input_schema,
    writes=not is_read_only,
    risk=RiskLevel.LOW if is_read_only else RiskLevel.HIGH,
    idempotent=is_read_only,
    executor=_executor_for(client),
)
```

### 5.2 安全约束

- 远端工具描述和 annotation 不能降低风险；明确的 `readOnlyHint=false` 或
  `destructiveHint=true` 只能阻止误配的本地降级。
- 未在本地白名单中的工具继续使用 `writes=true, risk=high, idempotent=false`。
- MCP Server 新增工具后不会自动获得只读信任。
- 修改 `read_only_tools` 属于宿主管理操作，必须通过 privileged token。
- 连接器重连时重新计算 Capability 元数据并刷新内容哈希。
- 工具被移出白名单后，下一次 Run 必须看到高风险版本。

## 6. MCP 工具错误传播

### 6.1 新增错误类型

建议在：

```text
maestro/src/maestro/mcp/client.py
```

新增：

```python
class MCPToolError(MCPTransportError):
    pass
```

`call_tool()` 收到 JSON-RPC 成功响应后继续检查 MCP 结果：

```python
result = response.get("result", {})
if result.get("isError") is True:
    raise MCPToolError(extract_tool_error(result))
return result
```

错误文本提取必须有长度上限，不直接拼接任意超大远端内容。

### 6.2 Runtime 映射

- MCP Server 无法连接、进程退出、超时：`TRANSIENT_INFRASTRUCTURE`。
- MCP `isError=true`：Capability `status=failed`，错误回填模型，允许模型修正或向用户解释。
- 排产侧返回的普通业务错误 `{ok:false}` 保持一次成功的工具往返，由模型根据错误码澄清用户输入。

不能把 `isError=true` 的调用记录为 `step.succeeded`。

## 7. 结构化结果处理

MCP 工具可能同时返回：

```json
{
  "content": [
    {"type": "text", "text": "查询到 1 个候选排产方案"}
  ],
  "structuredContent": {
    "candidate_count": 1,
    "solutions": []
  }
}
```

建议在 MCP 执行边界归一化：

1. `structuredContent` 存在时，作为主要 `CapabilityResult.content`。
2. 同时保留有界文本摘要，供日志和兼容客户端使用。
3. 没有 `structuredContent` 时保持当前完整 result 行为。
4. 对返回内容继续使用 Runtime 现有 artifact 阈值，超大结果不直接注入模型上下文。

推荐归一化结果：

```json
{
  "data": {},
  "summary": "查询到 1 个候选排产方案",
  "mcp": {
    "server": "planning",
    "tool": "get_planning_overview"
  }
}
```

## 8. 管理 API 扩展

修改：

```text
maestro/src/maestro/api/routes/mcp.py
```

`MCPServerPayload` 增加：

```python
read_only_tools: list[str] = Field(default_factory=list)
```

校验要求：

- 去重并保持稳定顺序。
- 工具名必须非空且满足 MCP/OpenAI 工具命名约束。
- 可先保存尚未发现的工具名，便于服务器暂时离线时配置。
- 路径名与 payload 名继续保持一致。

`GET /mcp/servers` 的工具视图增加：

```json
{
  "name": "get_order_planning",
  "capability": "mcp__planning__get_order_planning",
  "description": "...",
  "read_only": true,
  "writes": false,
  "risk": "low"
}
```

服务器级响应增加 `read_only_tools`，但继续只返回环境变量键名，不返回环境变量值。

## 9. 前端连接器管理

修改：

```text
frontend/src/types/api/mcp.ts
frontend/src/api/mcp.ts
frontend/src/features/extensions/connectors/ConnectorEditorDrawer.tsx
frontend/src/features/extensions/connectors/ConnectorDetailDrawer.tsx
```

### 9.1 类型

为 `McpServerInput` 和 `McpServer` 增加：

```typescript
read_only_tools: string[];
```

工具摘要增加：

```typescript
read_only: boolean;
writes: boolean;
risk: 'low' | 'medium' | 'high';
```

### 9.2 交互

连接器详情展示：

- 已发现工具名称。
- Capability 完整名称。
- 本地风险等级。
- 是否无需审批即可只读调用。

编辑连接器时允许管理员切换“可信只读”。提示必须明确：

```text
该判断由本机管理员授予，不来自远端服务器声明。
新增工具默认按高风险处理。
```

第一阶段可以只支持 API 和配置文件，第二阶段再增加图形化策略编辑，不阻塞核心调用链。

## 10. 工具描述与模型选择

排产 MCP Server 发布的 28 个工具都按同一规则动态注册，例如：

```text
mcp__planning__list_planning_rules
mcp__planning__run_rule_planning
mcp__planning__get_planning_overview
mcp__planning__compare_planning_solutions
mcp__planning__search_planning_entities
mcp__planning__get_order_planning
mcp__planning__get_operation_planning
mcp__planning__get_scheduling_status
mcp__planning__start_planning_optimization
mcp__planning__control_online_dispatch
```

工具描述应包含中文触发示例和指标口径。例如：

```text
查询指定订单在一个或多个候选排产方案中的工序安排、完工时间和订单延误。
适用于：“ORD-0004 怎么排”“这个订单什么时候完工”“比较该订单在各方案中的差异”。
```

Runtime 不需要根据关键词硬编码工具路由，继续由模型使用标准 function calling 选择工具。

可选增强：安装一个领域 Skill，用于说明总延误、订单延误、候选方案和 Archive 的业务口径；该 Skill 只能收窄允许工具，不能提升风险权限。

## 11. 启动与生命周期

### 11.1 启动顺序

1. 启动 `llm4drd`，监听 `127.0.0.1:8888`。
2. 启动 Manufacturing Agent。
3. Agent lifespan 读取 `settings.json`。
4. `MCPManager` 启动 `planning` 子进程。
5. 完成 initialize、initialized notification、ping 和 tools/list。
6. 把工具注册到 Capability Registry。

### 11.2 故障行为

- MCP 子进程启动失败不阻止 Agent 主服务启动。
- 排产 HTTP 服务未启动时，MCP Server 可以完成协议握手，但工具调用返回 `PLANNING_API_UNAVAILABLE`。
- 配置更新或手动 reconnect 时，先注销旧 Capability，再连接新进程。
- Agent 关闭时终止 MCP 子进程并清理 pending request。

## 12. 测试方案

建议新增或扩展：

```text
maestro/tests/mcp/test_mcp_read_only_policy.py
maestro/tests/mcp/test_mcp_tool_errors.py
maestro/tests/mcp/test_planning_mcp_runtime.py
maestro/tests/mcp/test_planning_mcp_end_to_end.py
frontend/src/features/extensions/connectors/ConnectorEditorDrawer.test.tsx
```

### 12.1 配置兼容测试

- 旧配置缺少 `read_only_tools` 时仍可加载。
- 保存和读取白名单不丢失。
- API 响应不泄漏 env 值。
- MCP 管理写接口仍要求 privileged token。

### 12.2 风险策略测试

- 白名单中的工具注册为只读低风险。
- 未在白名单中的工具注册为高风险写操作。
- 新发现工具不会自动被信任。
- 重连后风险元数据正确刷新。
- 远端描述无法降低本地风险。

### 12.3 错误传播测试

- `isError=true` 产生 Capability failed。
- MCP 请求超时产生基础设施失败。
- 子进程退出唤醒所有 pending request。
- 普通 `{ok:false}` 业务结果能回填模型用于澄清。

### 12.4 Runtime 测试

使用 Fake LLM 固定发起：

```text
mcp__planning__get_planning_overview
```

验证：

- 只读工具走快速路径。
- 不产生 ApprovalRecord。
- 结果以 `role=tool` 回填。
- 模型可以基于结果生成最终文本。
- 工具失败后模型可以改参数或解释失败。

### 12.5 真实端到端测试

启动真实 `llm4drd` MCP Server 子进程，完成：

```text
POST /runs
  -> model tool call
  -> Policy Gate
  -> stdio MCP
  -> Planning REST API
  -> tool result
  -> run.completed
```

## 13. 实施步骤

1. 扩展 `MCPServerConfig` 和配置存储，保持旧配置兼容。
2. 为 Manager 添加工具级本地只读策略。
3. 修复 `isError` 传播并增加错误类型。
4. 增加 `structuredContent` 归一化。
5. 扩展 MCP 管理 API。
6. 配置同机 `planning` MCP Server。
7. 编写风险、错误和 Runtime 测试。
8. 与 `llm4drd` 做真实全链路测试。
9. 最后增加连接器前端的只读策略展示和编辑。

## 14. 验收标准

- `/mcp/servers` 显示 `planning` 已连接及当前 Server v2 的 28 个工具。
- 排产查询工具以 `mcp__planning__*` 注册。
- 白名单中的查询工具不触发审批。
- `run_rule_planning` 保持高风险写操作，审批后才执行并将结果回填模型。
- 未受信任的 MCP 工具仍触发高风险策略。
- MCP `isError=true` 不再被记录为成功。
- 用户询问候选数量、方案延误、订单排产和工序时间时，Agent 能自动选择正确工具。
- 无匹配或匹配歧义时，Agent 基于结构化错误澄清，不虚构 ID。
- 排产服务不可用时，Agent 明确说明依赖不可用，不虚构排产结论。
- Runtime 目录不包含任何排产业务逻辑。

## 15. 端到端验收问题

| 用户问题 | 期望工具 |
| --- | --- |
| 有哪些内置排产规则？ | `list_planning_rules` |
| 使用 ATC 跑一遍排产 | `run_rule_planning`（需要审批） |
| 现在有多少候选排产方案？ | `get_planning_overview` |
| 各候选方案总延误时长分别是多少？ | `compare_planning_solutions` |
| ORD-0004 的排产结果是什么？ | `get_order_planning` |
| OP-0004-02-01 排在什么时候？ | `get_operation_planning` |
| 名称包含 Turning 的工序有哪些？ | `search_planning_entities` |

所有调用最终都应形成可审计的 Capability 事件，并由模型基于真实工具结果完成回答。
