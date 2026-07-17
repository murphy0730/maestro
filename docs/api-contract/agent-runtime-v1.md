# Agent Runtime API v1

所有接口的根路径为 `/`。失败响应为 `{ "detail": { "code", "message", "run_id"? } }`。

## Artifacts

`POST /artifacts` 接收单个 multipart 字段 `file`（最大 10 MB），返回：

```json
{"artifact_id":"<sha256>","sha256":"<sha256>","media_type":"text/plain","bytes":5}
```

`GET /artifacts/{artifact_id}` 返回对应原始字节。ID 是不透明内容寻址标识，不接受路径。

## Runs

`POST /runs` 接受：

```json
{"session_id":"s1","message":"解释 OEE","source":"chat","skill_names":[],"artifact_ids":[]}
```

`source` 可为 `chat`、`expert`、`event` 或 `resume`。服务器先持久化初始快照、立即返回 202，再在后台执行 Run；返回快照包括 `run_id`、`path`、`status` 与 `intent`。

`GET /runs/{run_id}` 返回最新 Run 快照。

`POST /runs/{run_id}/approvals/{approval_id}` 接受
`{"approved":true,"expected_revision":3,"principal_id":"local-user"}`；revision 不匹配返回 409。

`POST /runs/{run_id}/cancel` 幂等地请求取消并返回 Run 快照。

## SSE

`GET /runs/{run_id}/stream` 返回 `text/event-stream`。每条记录为：

```text
id: <event-id>
event: run.completed
data: {"final_text":"..."}

```

客户端以 `Last-Event-ID` 恢复，服务器先订阅实时事件、再稳定重放其后的 Journal 事件，因此不会有 replay/live 间隙或重复。公开事件包括：
`run.created`、`run.path_selected`、`run.path_upgraded`、`run.waiting_approval`、`run.reconciling`、`run.completed`、`run.failed`、`run.cancelled`、`step.started`、`step.succeeded`、`step.failed`、`approval.requested`、`approval.expired`、`approval.resolved`、`artifact.created`、`token.delta`。

## Extensions

宿主可在启动后通过 `Platform.capabilities.register(...)` 注册通用 Tool 能力；`Platform.mcp.register(...)` 注册 MCP transport 的本地能力描述与执行器。风险、写入与幂等元数据由本地注册者提供，不能由远端描述降低。Skill 发现会在每个 Run 意图判断时读取当前能力注册表。
