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

审批决定本身是同步的（404 / 409 照常立即抛出），被它解开的写入与随后的模型回合则在后台继续，因此返回 **202** 与一份**非终态**快照：批准为 `running_structured`，重开一轮或进入下一次确认为 `waiting_approval` 且 `approval_id` 已变，拒绝为 `failed`。客户端拿到 202 后应重新订阅 `GET /runs/{run_id}/stream`（可带 `Last-Event-ID`），在那条流上实时收到 `approval.resolved`、`step.started` 与后续 `token.delta`。

`POST /runs/{run_id}/cancel` 幂等地请求取消并返回 Run 快照。

## SSE

`GET /runs/{run_id}/stream` 返回 `text/event-stream`。每条记录为：

```text
id: <event-id>
event: run.completed
data: {"final_text":"..."}

```

客户端以 `Last-Event-ID` 恢复，服务器先订阅实时事件、再稳定重放其后的 Journal 事件，因此不会有 replay/live 间隙或重复。公开事件包括：
`run.created`、`run.path_selected`、`run.path_upgraded`、`run.waiting_approval`、`run.reconciling`、`run.completed`、`run.failed`、`run.cancelled`、`step.started`、`step.succeeded`、`step.failed`、`approval.requested`、`approval.expired`、`approval.resolved`、`artifact.created`、`context.shed`、`token.delta`。

`step.*` 的 `data` 结构：`step.started` 为 `{step_id, idempotency_key}`；`step.succeeded` 为 `{name, status}`；`step.failed` 为 `{name, status, error}`（写路径为 `{step_id, status}`）。`artifact.created` 为 `ArtifactRef`，即 `{artifact_id, sha256, media_type, bytes}`。只读能力只在完成时发事件，因此不会出现 `step.started`。

`model.turn` 的 `data` 为 `{kind, estimated_prompt_tokens}`，供应商回报 usage 时并入 `prompt_tokens` / `completion_tokens` / `total_tokens`。估算值与实际值同时给出是刻意的：预算按估算值决策，两者的偏差必须可见而不是被假定为零。

`context.shed` 为 `{limit, total_tokens, items}`，在统一 token 预算把过旧的工具结果降级为 artifact 引用时发出。上下文从不静默截断——只看总量会把被裁剪过的 prompt 误读成本来就小的 prompt。被降级的内容仍可用 `read_artifact` 读回。

`run.failed` 的 `reason` 新增两个取值：`context_overflow`（组装出的 prompt 超出模型窗口）与 `model_unavailable`（模型调用失败）。这两种情况以前会被当作一次成功的回答返回「模型当前不可用。」并写进会话历史。

## Extensions

宿主可在启动后通过 `Platform.capabilities.register(...)` 注册通用 Tool 能力；`Platform.mcp.register(...)` 注册 MCP transport 的本地能力描述与执行器。风险、写入与幂等元数据由本地注册者提供，不能由远端描述降低。Skill 发现会在每个 Run 意图判断时读取当前能力注册表。

## Host primitives

默认平台注册以下通用原语，Skill 的 `allowed-tools` 可以直接命名它们（Claude 名称别名见 `skills/parser.py::DEFAULT_TOOL_ALIASES`）。全部路径参数经 `runtime/paths.py::safe_join` 限制在 `workspace_root` 内：

| capability | 别名 | 参数 | writes / risk |
| --- | --- | --- | --- |
| `read_file` | `Read` | `path`，可选 `offset`/`limit` | 否 / low |
| `glob` | `Glob` | `pattern` | 否 / low |
| `grep` | `Grep` | `pattern`，可选 `path` | 否 / low |
| `write_file` | `Write` | `path`, `content` | 是 / high |
| `edit_file` | `Edit` | `path`, `old`, `new`（`old` 必须唯一） | 是 / high |
| `read_artifact` | — | `artifact_id` | 否 / low |
| `bash` | `Bash` | `command` | 是 / high |

`write_file` 与 `edit_file` 是 `writes=true, risk=high`，因此**必然**经 Policy Gate 产生审批记录。`read_artifact` 用于取回超过内联阈值而被存为产物的能力结果，且只能读取当前 Run 见过或作为输入传入的产物，否则 Run 以 `artifact_not_visible` 失败。

`bash` 是**任意命令执行**，因此声明为 `writes=true, risk=high`，每次调用都必经 Policy Gate 产生审批记录——审批是真正的闸门。它以工作区为 cwd，`tools/sandbox.py` 提供纵深防御（不继承 API Key、macOS seatbelt 下禁网并把写入限定在工作区、超时与输出上限），但与文件系统能力不同，shell 无法被证明不越出工作区；`isolation` 字段如实回报实际生效的隔离级别。

`PowerShell`、`WebFetch`、`TodoWrite` **没有**对应实现：宿主若需要，须自行注册能力并登记别名。声明了未注册能力的 Skill 会作为坏包出现在 `GET /skills` 的 `errors` 中。

## 审批与多次确认

`ApprovalRecord` 带 `confirmations_required` 与 `confirmations`。Policy Gate 返回 `require_reconfirmation` 时要求 **2 次**人工确认，其余情况为 1 次。

每一轮确认都会重新计算 `external_state_token` 并重新评估策略，因此后一次确认真正证明的是「两次之间外部状态没有变化」。中途状态漂移或审批过期会作废已累计的确认并重开一轮——它们担保的是已经改变了的状态。

SSE 上一轮确认完成投影为 `approval.resolved`，紧随其后的 `approval.requested` 携带下一轮；公开事件词汇表不变。

## MCP

MCP 工具经 stdio 传输接入（协议版本 `2024-11-05`，实现 `initialize` / `notifications/initialized` / `ping` / `tools/list` / `tools/call`；未实现 resources、SSE 与 HTTP）。发现到的工具以 `mcp__{server}__{tool}` 注册为 `CapabilityKind.MCP`。

风险姿态在本地决定：Runtime 无法知道任意远端工具会触及什么，因此默认注册为 `writes=true, risk=high, idempotent=false`，每次调用都要人工审批。本地管理员可在服务器配置的 `read_only_tools` 中逐项授予只读信任；只有列出的工具注册为 `writes=false, risk=low, idempotent=true`。远端描述和 annotations 不能降低这一判定，也不能顶替同名的 TOOL/SKILL 能力；远端明确给出 `readOnlyHint=false` 或 `destructiveHint=true` 时，只能阻止误配的本地降级。新发现但未列入白名单的工具始终保持高风险。

服务器配置存放在 `<数据根>/settings.json` 的 `mcp_servers` 键下，**不经环境变量**。`read_only_tools` 为可选工具名数组，缺失时按空数组兼容旧配置。子进程只继承 `PATH`/`LANG`/`LC_ALL`/`TZ`/`HOME`/`TMPDIR` 与该服务器配置中显式声明的 `env`，宿主的 `LLM_API_KEY` 不会泄漏给 MCP 服务器。

- `GET /mcp/servers`：只读，列出配置、连接状态与已发布的能力名；
- `PUT /mcp/servers/{name}`：新增或更新并立即重连；
- `DELETE /mcp/servers/{name}`：删除配置并注销其能力；
- `POST /mcp/servers/{name}/reconnect`：按现有配置重连。

后三者与 Skill 包管理同属宿主管理接口，要求 `Authorization: Bearer <PRIVILEGED_API_TOKEN>`，无效或缺失凭证返回 403。服务器响应包含 `read_only_tools`；每个已发现工具包含 `read_only`、`writes` 与 `risk`。响应中的 `env_keys` 只回显键名，不回显值。连接失败通过 `status: "error"` 与 `error` 字段上报，不会让启动或请求失败。

`tools/call` 返回 `isError=true` 时，该调用记录为失败并把有界错误文本回填模型，不产生成功事件。存在 `structuredContent` 的成功结果归一化为 `{data, summary, mcp}`；没有时保留原始 MCP result。超过 Runtime artifact 阈值的结果只向模型传递 artifact 引用，完整内容由 `read_artifact` 按需读取。

## 模型与引擎

推理来源以「供应商列表 + 一个启用项」的形式配置，存放在 `<数据根>/settings.json` 的 `model_providers` 键下，与 `mcp_servers` 同为分节原子写。结构为 `{"llm": {"providers": [...], "active_id": ...}, "embedding": {...}}`，每个 provider 为 `{id, name, base_url, api_key, model}`。

**优先级**：某 section 存在 `active_id` 指向的启用项时，它的连接信息覆盖扁平的 `llm_*` / `embed_*`（环境变量与 `.env`）；没有启用项时回退到扁平值。这样设置界面里的选择不会被一份过期的 `.env` 静默击败。`embedding` 段目前可以配置并持久化，但 Runtime 尚无嵌入消费方，配置暂不产生行为。

- `GET /models`：只读，返回已持久化的配置；
- `PUT /models`：保存整份配置并热更新运行中的客户端；
- `POST /models/test`：用候选参数试连一次，不改动任何持久化状态。

`api_key` 从不回传：`GET` 与 `PUT` 的响应里该字段恒为空串，另给派生的 `api_key_set` 表示磁盘上是否存有密钥。相应地，`PUT` 载荷中某个已存 `id` 的 `api_key` 为空时保留原值——否则前端「回读—保存」会把密钥清空；显式给出非空值才覆盖。`PUT` 的响应额外带 `available`，表示热更新后客户端是否真的可用。

`POST /models/test` 接受 `{section, id?, base_url, model, api_key}`，走一次性客户端，不触碰正在服务的连接；`api_key` 为空且 `id` 命中已存条目时使用磁盘上的密钥。连接失败不是服务端错误，一律以 `{ok: false, error, latency_ms}` 返回 200。

`PUT` 与 `POST /models/test` 与 MCP、Skill 包管理同属宿主管理接口，要求 `Authorization: Bearer <PRIVILEGED_API_TOKEN>`，无效或缺失凭证返回 403。热更新在原有客户端实例上原地发生，因此已持有该实例的协调器与摘要器立即用上新连接。

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
