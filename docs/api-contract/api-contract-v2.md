# API 契约 v2（2026-07-03）

> 取代 `api-contract.md`（v1）。v2 以**后端实际实现**（`maestro/main.py`）为唯一事实源：
> 补齐 v1 缺失的会话/确认/事件端点，明确标注 v1 中**尚未实现**的端点。
> 通用约定（错误结构、时间格式、`/api/v1` 前缀经 Vite 代理）与核心类型
> （RouteDecision / KnowledgeDoc / SSE 基本帧）沿用 v1，不再重复，下文只写增量与差异。

## 端点总览

| 端点 | 状态 | 说明 |
|---|---|---|
| `POST /chat` | ✅ | 非流式对话（CLI/测试用） |
| `POST /chat/stream` | ✅ | 流式对话，SSE；**v2 新增 `actions` 帧** |
| `POST /chat/clarify` | ✅ | 澄清回选，续流 |
| `POST /chat/confirm` | ✅ | **v1 未收录** 确认/拒绝待执行动作 |
| `GET /pending` | ✅ | **v1 未收录** 全部待确认动作 |
| `POST /events` | ✅ | **v1 未收录** 注入系统事件（测试事件驱动） |
| `GET /audit` | ✅ | **v1 未收录** 原始审计日志 |
| `GET /audit/timeline` | ✅ | 决策时间线（v2 实装） |
| `GET/POST /sessions`, `PATCH/DELETE /sessions/{id}`, `GET /sessions/{id}/messages` | ✅ | **v1 未收录** 会话管理 |
| `GET/POST /knowledge`, `PUT/DELETE /knowledge/{doc_id}` | ✅ | 同 v1 §5.2 |
| `GET /skills` | ✅ | **v2 新增** 技能列表（见 §7） |
| `POST /skills/import` | ✅ 201 | **v2 新增** multipart 导入技能包（见 §7） |
| `POST /skills/validate` | ✅ | multipart 兼容性预检，不落盘 |
| `DELETE /skills/{name}` | ✅ | **v2 新增** 删除技能；404 不存在 |
| `GET /skills/{name}/trust` | ✅ | 当前包 hash 的本地用户信任状态 |
| `POST /skills/{name}/trust` | ✅ | 明确信任当前 hash；仅允许本机应用来源 |
| `DELETE /skills/{name}/trust` | ✅ | 撤销当前版本信任 |
| `POST /scheduling/execute` | ✅ | 调度动作执行（v2 实装，语义见下） |
| `GET /observations/{ref}` | ✅ | **v2 新增** 懒加载被离线暂存的大工具观察（方案2，见 §8）；404 不存在/已过期 |
| `GET /health` | ✅ | `{status, llm_available}` |
| `POST /planning/solve` / `GET /planning/solve-runs` | ❌ 未实现 | 面板暂由 MSW mock 演示 |
| `GET /scheduling/kitting` / `GET /scheduling/dispatch-orders` / `GET /scheduling/exception-impact` | ❌ 未实现 | 同上 |
| `POST /query/stream` | ❌ 未实现 | RAG 问答走 `/chat/stream`（route=query） |

## 1. `POST /chat/stream` — v2 增量

SSE 帧序列：`[progress…] → route → token… → [actions] → done`，或 `… → clarify → done`，异常 `error`。

**新增 `progress` 帧**（2026-07-04）：编排/引擎执行期间**实时**下发的阶段进度，
解决长任务（ReAct 多步、CP-SAT 求解）期间前端零反馈的问题。前端在流式气泡的
占位行展示最新一条即可，无需累积。

```jsonc
event: progress
data: { "text": "调用工具 check_kitting" }
// 其它示例: "识别意图…" / "思考中 (第 2/8 步)" / "求解中 (FlowShopTardiness)…" / "检索知识库…"
```

`/chat/clarify` 的续流同样携带 progress 帧。

**新增 `actions` 帧**（本轮产生了需人工确认的写动作时，在 `done` 前下发一次）：

```jsonc
event: actions
data: {
  "actions": [
    {
      "action_id": "a1b2c3d4",
      "action_type": "dispatch_work_order",   // 见 ActionGate 策略表
      "description": "下发任务令 WO-101 至 注塑1号线",
      "params": {},
      "status": "pending"                      // pending | executing | executed | rejected | failed | validation_failed | expired
    }
  ]
}
```

前端渲染确认卡片，确认/拒绝走 `POST /chat/confirm`。

**技能透传（v2 新增）**：`/chat` 与 `/chat/stream` 请求体新增可选 `skill_ids: string[] | null`
（前端多技能选择时透传；对应 `Orchestrator.handle(skill_ids=…)` 的 forced 分支，跳过路由层，
后端把选中技能的 allowed_tools/前置断言/SKILL.md 正文合并为单次 AgentLoop 运行）。
兼容保留单值 `skill_id: str | null`；二者都在时并入 `skill_ids`。缺省时走原有三层路由，
行为与 v1 逐字节一致。

```jsonc
// /chat、/chat/stream 请求体增量
{ "session_id": "string", "message": "…", "current_engine": null,
  "skill_ids": ["capacity-report", "line-changeover"] }
```

**执行模式（v2 新增）**：`/chat`、`/chat/stream`、`/chat/clarify` 请求体新增可选
`mode: "plan" | "auto"`，缺省 `"plan"`。对应前端 Composer 的「默认模式 / 完全访问模式」，
经 `Orchestrator.handle(mode=…)` 下沉到 `ActionGate` 判级：

| 操作 | `plan`（默认模式） | `auto`（完全访问模式） |
|---|---|---|
| 读（查订单 / 查齐套 / `read_file` / `grep` / `list_files`） | 直接执行 | 直接执行 |
| 写文件、`web_fetch`（`tool:write_file` / `tool:edit_file` / `tool:web_fetch`） | 需确认 | 直接执行 |
| 写生产系统（`dispatch_work_order`、`update_work_order_status`、`send_expedite_message.*`、`send_notification`、`record_followup`） | 需确认 | **需确认** |

「需确认」= 该动作变成 `PendingAction`，随 `actions` 事件下发确认卡片，经 `POST /chat/confirm`
批准后才执行。完全访问模式**永不**放开写生产系统。缺省 `"plan"` 时行为与 v1 逐字节一致；
不经 HTTP 的调用（事件驱动唤醒、CLI）同样取 `"plan"`。

```jsonc
// /chat、/chat/stream、/chat/clarify 请求体增量
{ "mode": "auto" }
```

**`route` 帧扩展（v2 新增）**：
- `intent` 枚举增加 `"skill"`（v1 `IntentType` 为 `planning | scheduling | query | uncertain` 四分类，现为五分类）。
- payload 增加 `skill_id` 字段：技能路由为技能 `name`，非技能路由为 `null`。

```jsonc
event: route
data: {
  "intent": "skill",                       // 新增枚举值
  "confidence": 1.0,
  "source": "command",                     // forced 路由（前端选定）
  "skill_id": "capacity-report",           // 新增字段；非技能路由为 null
  "entities": {}, "reason": "用户显式选择技能", "is_composite": false, "steps": []
}
```

## 2. `POST /chat/confirm` — 确认/拒绝待执行动作

```jsonc
// 请求
{ "session_id": "string", "action_id": "a1b2c3d4", "approved": true }
// 响应 (非流式)
{
  "reply": "已执行: 下发任务令 WO-101 — 已下发至产线",
  "route": null,
  "pending_actions": [ { /* 该动作，status 已变为 executed|rejected|failed|validation_failed|expired */ } ],
  "data": null,
  "needs_clarification": false,
  "options": []
}
```

`action_id` 不存在或已处理 → `reply` 为 "确认失败: …"（HTTP 仍 200，与 CLI 行为一致）。

## 3. `POST /scheduling/execute` — 调度动作执行

对**已挂起**的待确认动作按 ActionGate 闸口执行（不能凭空创建动作；两道写护栏不绕过）。

```jsonc
// 请求
{ "session_id": "string", "action_id": "a1b2c3d4", "confirmed": true }
// 响应
{ "status": "executed | failed | pending", "audit_id": "a1b2c3d4", "message": "已下发至产线" }
```

- `confirmed=false` → `status: "pending"`，动作**不消费**（提示需确认；显式拒绝走 `/chat/confirm`）
- `action_id` 不存在 → `404`；已处理过 → `409`
- 与 v1 差异：`status` 增加 `failed`（执行了但失败）；`rejected` 不由本端点产生
- `audit_id` 即 `action_id`，可用 `GET /audit` 按此关联

## 4. `GET /audit/timeline?session_id=&limit=100` — 决策时间线

```jsonc
{
  "events": [
    {
      "ts": "2026-07-03T10:00:00",
      "type": "route | engine_action | tool_call",   // llm_call 预留未产生
      "summary": "路由 → planning (embedding, 置信 0.92)",
      "detail": { "actor": "s1", "params": {}, "authz": null, "result": {} }
    }
  ]
}
```

单用户版：传 `session_id` 时返回该会话条目 **+** 全局系统条目（巡检/事件层，actor 为
`system|scheduling_agent|event_layer`）。

## 5. 会话管理

```
GET    /sessions                     → SessionMeta[]（按 updated_at 倒序）
POST   /sessions      {title?}       → SessionMeta（生成 session_id）
PATCH  /sessions/{id} {title}        → SessionMeta；404 不存在
DELETE /sessions/{id}                → {deleted, session_id}；404 不存在
GET    /sessions/{id}/messages       → StoredMessage[]
```

```jsonc
// SessionMeta
{ "session_id": "hex32", "title": "重排注塑订单", "engine": "planning|scheduling|query|null",
  "created_at": "ISO", "updated_at": "ISO", "message_count": 4 }
// StoredMessage
{ "role": "user|assistant|system", "content": "string", "ts": "ISO",
  "kind": "normal|system" }   // v2 新增；kind=system 为动作确认结果，回读时渲染为居中细行；缺省 normal
```

首轮对话结束前后端用 LLM 生成智能标题并落库（失败保留截断标题）。

## 6. 其余端点

`POST /chat`、`POST /events`、`GET /audit`、`GET /pending`、`/knowledge` CRUD、`GET /health`
的形状同后端实现（`main.py`），`/knowledge` 部分与 v1 §5.2 一致。

## 7. 技能模块 (Skills)

照 `/knowledge` 模式（见 design-v1 §3.5）。frontmatter 规范见 `docs/skills-design-v1.md` §2。

### 端点

```
GET    /skills                       → { "skills": [SkillMeta…] }
POST   /skills/validate              → SkillValidationReport  # multipart，不落盘
POST   /skills/import                → 201, SkillMeta   # multipart，见下
DELETE /skills/{name}                → { "deleted": true, "name": "…" }；404 不存在
GET    /skills/{name}/trust          → SkillTrustStatus
POST   /skills/{name}/trust          → SkillTrustStatus
DELETE /skills/{name}/trust          → SkillTrustStatus
```

### SkillMeta

frontmatter 全字段（见 design-v1 §2.2，共 10 个）**外加落盘元数据** 3 个：

```jsonc
{
  "name": "capacity-report",
  "display_name": "产能日报",
  "description": "汇总当日订单/任务令/齐套数据，生成产能与瓶颈分析报告",
  "when_to_use": ["给我出一份今天的产能报告", "分析一下最近的产线瓶颈"],
  "allowed_tools": ["query_orders", "query_work_orders", "check_kitting"],
  "user_invocable": true,
  "disable_model_invocation": false,
  "tool_preconditions": {},                  // 缺省 {}；写操作技能示例见 design-v1 §2.2
  "version": "1.0",
  "author": "周文涛",
  "license": "MIT",
  "extensions": {},                 // 未识别的外部生态字段，不静默丢弃
  "scripts": [],                    // 需信任当前 hash；每次执行仍需确认
  // —— 以下为落盘元数据（导入时生成）——
  "file_count": 1,                            // .md=1；.zip=成员数（含 SKILL.md）
  "bytes": 4096,                              // 解压后总字节数
  "added_at": "2026-07-03T10:00:00",          // 导入时间
  "compatibility_status": "ready",            // ready/degraded/not_ready/disabled
  "warnings": [],
  "package_sha256": "...",
  "trust": {                         // GET /skills 列表中的派生状态
    "level": "untrusted",
    "valid": false,
    "package_sha256": "..."
  }
}
```

`POST /skills/{name}/trust` 请求：

```json
{
  "package_sha256": "当前导入版本返回的 hash",
  "acknowledged_script_execution": true
}
```

信任严格绑定当前包 hash。可信 Skill 的 `run_skill_script` 调用仍经 ActionGate；确认后
优先使用 SRT，SRT 不可用时可在宿主机受控执行，结果明确返回 `srt` 或
`guarded_host`。当前信任主体固定为单用户 `local-user`。

### 兼容性预检

`POST /skills/validate` 接收与导入相同的文件，返回规范化名称、能力、工具映射、
规范化 frontmatter、警告与错误。兼容导入支持常见 kebab-case 字段和 `Read`、`Bash`、
`Glob`、`Grep`、`WebFetch` 等工具别名；映射后仍执行 Maestro 原有权限策略。

### multipart 约定

`POST /skills/import` 表单字段 `file`，支持两种格式（后端统一落盘为目录）：

- **单 `.md` 文件**：整个文件即 `SKILL.md`，无附属文件。
- **`.zip` 包**：根级（或唯一顶层目录内，自动归一化）必须有 `SKILL.md`；其余为附属文件，
  由 agent 经 `read_skill_file` 工具按需读取。

导入流程：大小 → 后缀 → 解包归一化 → frontmatter 解析 → 字段校验 → 落盘。
完整校验规则见 design-v1 §2.3。

### 错误语义

| HTTP | 触发条件 |
|---|---|
| 413 | 上传体超过 10MB（`_MAX_UPLOAD_BYTES`） |
| 415 | 后缀非 `.zip`/`.md` |
| 422 | `SkillValidationError`：frontmatter 非法、必填缺失、正文空/超配置上限、`allowed_tools` 含未注册工具、`tool_preconditions` key 越界 `allowed_tools` 或断言名非法、zip 穿越/缺 `SKILL.md`/超成员上限等（消息列出具体原因） |
| 409 | `name` 与已存在技能重复 |

## 8. 大工具观察离线暂存 (方案2)

调度 ReAct 的某次工具结果过大 (超 `react_observation_max_bytes`) 时，后端不再有损截断，而是把
整对象离线暂存，轨迹 (`data.steps[].observation`) 与 SSE `context` 帧里只放一个**紧凑句柄**：

```json
{ "observation_ref": "obs-7", "kind": "list", "total": 847,
  "item_keys": ["order_id", "status", "due_date"],
  "preview": [ /* 前若干条 */ ], "original_bytes": 123456, "hint": "…用 read_observation 分页…" }
```

`GET /observations/{ref}?offset=&limit=&keys=` 懒加载完整内容，返回分页：

```json
{ "observation_ref": "obs-7", "kind": "list", "total": 847,
  "offset": 0, "limit": 20, "items": [ /* 本页 */ ], "has_more": true }
```

- `kind: "dict"` 时可传 `keys`（逗号分隔）取子集，返回 `{ keys: {…} }`；不传则返回 `item_keys` + `preview`。
- `kind: "scalar"` 时 `offset/limit` 为字符切片，返回 `{ slice, has_more }`。
- 观察为**进程内临时** (FIFO 淘汰)，重启后旧 ref 失效 → 404（前端降级提示"观察已过期"）。

**SSE `context` 帧**：调度回合结束前，若有工具轨迹，`POST /chat/stream` 先发一帧
`{ event: "context", data: { engine: "scheduling", payload: { steps, stop_reason } } }`，
前端 Context Panel 据此渲染轨迹并按 `observation_ref` 懒加载。

## 未实现端点的前端处理

`/planning/solve*`、`/scheduling/kitting|dispatch-orders|exception-impact`、`/query/stream`
仅存在于 MSW mock（`frontend/src/mocks/api/handlers.ts`），对应面板为演示态；
连接真实后端时这些请求会 404，属已知差距，实装时以本文件为契约基线补齐。
