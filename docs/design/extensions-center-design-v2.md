# Maestro 扩展中心设计 v2 — 与实现对齐的修订

> 本文修订 `extensions-center-design-v1.md`。按仓库约定新建 vN+1 而不覆盖 v1；
> 两者冲突时**以本文与代码为准**。v1 保留为背景与产品意图的说明。

日期：2026-07-26

---

## 0. 为什么需要这次修订

v1 的 §10 / §11.3 以「已实现」的口吻描述了一整套 MCP 后端架构与 API。截至本次修订前，
**这些在代码中一行都不存在**：Agent Runtime 重写（提交 `7f2d838`）删除了整个
`maestro/mcp/` 包与 `api/routes/mcp.py`，此后 `runtime/mcp.py` 长期只是一个 45 行的
注册钩子——没有传输、没有握手、没有 `tools/list`、没有超时、没有配置来源，
`bootstrap.py` 构造了 `MCPConnector` 但从不调用它。

同期 `docs/superpowers/plans/2026-07-11-skillhub-mcp-market-sync.md` 也声称
`MCPConfigStore` 与 `/mcp/servers`「已在 v1 落地」，同属事实错误（已在该文就地更正）。

本次已重建 MCP（stdio + tools），本文把设计文档拉回与实现一致的状态。

## 1. 已落地的范围

| 组件 | 位置 | 状态 |
| --- | --- | --- |
| stdio 传输 | `mcp/transport.py` | ✅ |
| 协议客户端（`2024-11-05`） | `mcp/client.py` | ✅ `initialize` / `notifications/initialized` / `tools/list` / `tools/call` |
| 生命周期与能力发布 | `mcp/manager.py` | ✅ 连接、断开、重连、注销 |
| 受治理的注册边界 | `runtime/mcp.py` | ✅ 含冲突保护与失败映射 |
| 配置持久化 | `foundation/mcp_config_store.py` | ✅ `settings.json` 的 `mcp_servers` 键 |
| HTTP API | `api/routes/mcp.py` | ✅ `GET` / `PUT` / `DELETE` / `reconnect` |
| 前端「系统集成」 | `features/settings/McpSettings.tsx` | ✅ |

## 2. 明确**未**实现的范围

v1 描述过、本次**刻意不做**的部分。不要在文档里把它们写成已有能力：

- **MCP resources**（`resources/list` / `resources/read`）。当前只做 tools。
- **SSE / WebSocket / HTTP 传输**。类型枚举里也不保留这些值——一个没有实现支撑的
  枚举值就是代码兑现不了的承诺。
- **`GET /mcp/catalog` 连接器市场**、`/test` 预检、多作用域配置（v1 的 7 值
  `MCPConfigScope`）。当前只有一个本地作用域。
- **独立路由的扩展中心页面**（v1 §2.2）。当前仍在设置弹窗内，未新增路由。

## 3. 与 v1 不同的关键设计决策

### 3.1 远端工具一律按高风险写处理

v1 设想按工具语义分级风险。实现改为：**所有** MCP 工具注册为
`writes=True, risk=HIGH`，每次调用都经 Policy Gate 产生人工审批。

理由：Runtime 无从知道任意远端工具会触及什么，而远端自述不可信。宁可让操作者
每次确认，也不能让一个自称只读的工具静默产生副作用。若将来要分级，必须由**本地
操作者**在配置里声明，不能由服务器描述决定。

### 3.2 配置不走环境变量

v1 提到「从 settings.json / 环境变量读取」。实现只走 `settings.json` 的
`mcp_servers` 键。环境变量会让配置来源分裂成两处、且无法按服务器隔离 env。

### 3.3 子进程环境白名单

v1 未涉及。被删的旧实现用 `env = dict(os.environ)`，把宿主的 `LLM_API_KEY`
交给每一个 MCP 服务器。现改为只继承
`PATH`/`LANG`/`LC_ALL`/`TZ`/`HOME`/`TMPDIR`，加上该服务器配置里显式声明的 `env`。

### 3.4 名称冲突保护对称

`bootstrap.py` 早已禁止 Skill 顶替同名 TOOL/MCP，但 MCP 侧原先是无条件
`replace=True`，一个叫 `read` 的服务器可以遮蔽宿主自己的工具。现补上对称保护
（`MCPCapabilityConflict`）；重连刷新自己的条目仍然允许。

### 3.5 失败是数据，不是异常

连接失败、远端错误、超时都作为状态与 `CapabilityResult(status="failed")` 上报：
启动时一个坏服务器不会阻断整个 API，运行时一次远端错误不会终结 Run。

（相关：同期修复了 `runtime/mcp.py` 中 `execute` 包装器**无条件返回 succeeded**
的缺陷——远端业务失败此前会被当成成功回填给模型。）

## 4. 后续可做（未承诺）

按需要再评估，不要预先实现：

1. MCP resources 接入 `skill_read_resource` 之外的第三层上下文。
2. 按操作者声明为特定工具降级风险（需要配置面与审计设计）。
3. 连接器市场目录（v1 §10 的 `/mcp/catalog`）。
4. 独立路由的扩展中心页面（v1 §2.2）。
