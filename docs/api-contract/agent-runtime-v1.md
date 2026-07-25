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

## Skills

`GET /skills` 列出当前发现的 Claude 兼容 Skill metadata；`POST /skills/validate` 接收 multipart 字段 `file`，仅校验包兼容性且不写入文件系统。两者为只读接口。

`GET /skills` 响应为 `{"skills": [...], "errors": [...]}`。`errors` 里每项为 `{path, source, reason}`，表示磁盘上存在但解析失败的包——单个坏包不会影响其余技能的发现。每个 skill 的 `package_sha256`、`file_count`、`bytes`、`scripts` 与 `added_at` 均按磁盘实况计算；`trust` 为 `{level, valid, package_sha256, principal_id, trusted_at}`，其中 `level` 表示用户是否授予过信任，`valid=false` 专门表示「授予过但包已变更、信任已失效」。

Skill 的三层加载对应两个 Runtime capability：`skill_read_resource(skill, resource)` 读取已加载技能自带的 `references/`/`scripts/` 文件（只读、低风险）；`skill_run_script(skill, script, arguments)` 执行技能脚本，声明为 `writes=true, risk=high`，因此**必然**经 Policy Gate 产生审批记录，且要求该技能已按当前 `package_sha256` 被信任。两者都只能作用于当前 Run 已加载的技能，否则 Run 以 `skill_resource_not_loaded` 失败。

以下是宿主的 Skill 包管理接口，不是 Runtime Tool/MCP capability，也不经过模型调用或 Policy Gate：

- `POST /skills/import`：接收 multipart 字段 `file`，导入 `.md` 或 `.zip` Skill 包；
- `POST /skills/{name}/trust`：接收 `{"trusted":true}`，把信任绑定到该包**当前**的 `package_sha256` 并持久化到 `skills_dir/trust.json`；
- `DELETE /skills/{name}/trust`：删除信任记录；
- `DELETE /skills/{name}`：删除已导入 Skill 包。

这些管理接口都要求 `Authorization: Bearer <PRIVILEGED_API_TOKEN>`；无效或缺失凭证返回 403。导入或删除后会刷新注册表：已删除的 `CapabilityKind.SKILL` 不再出现在新 Run 的能力快照中。`disable-model-invocation: true` 的 Skill 可被列出和由用户显式选择，但不会被提供给模型作为可调用 capability。
