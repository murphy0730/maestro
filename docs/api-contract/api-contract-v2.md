# API 契约 v2（2026-07-03）

> 取代 `api-contract.md`（v1）。v2 以**后端实际实现**（`scheduling_platform/main.py`）为唯一事实源：
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
| `POST /scheduling/execute` | ✅ | 调度动作执行（v2 实装，语义见下） |
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
      "status": "pending"                      // pending | executed | rejected | failed
    }
  ]
}
```

前端渲染确认卡片，确认/拒绝走 `POST /chat/confirm`。

## 2. `POST /chat/confirm` — 确认/拒绝待执行动作

```jsonc
// 请求
{ "session_id": "string", "action_id": "a1b2c3d4", "approved": true }
// 响应 (非流式)
{
  "reply": "已执行: 下发任务令 WO-101 — 已下发至产线",
  "route": null,
  "pending_actions": [ { /* 该动作，status 已变为 executed|rejected|failed */ } ],
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
{ "role": "user|assistant|system", "content": "string", "ts": "ISO" }
```

首轮对话结束前后端用 LLM 生成智能标题并落库（失败保留截断标题）。

## 6. 其余端点

`POST /chat`、`POST /events`、`GET /audit`、`GET /pending`、`/knowledge` CRUD、`GET /health`
的形状同后端实现（`main.py`），`/knowledge` 部分与 v1 §5.2 一致。

## 未实现端点的前端处理

`/planning/solve*`、`/scheduling/kitting|dispatch-orders|exception-impact`、`/query/stream`
仅存在于 MSW mock（`frontend/src/mocks/api/handlers.ts`），对应面板为演示态；
连接真实后端时这些请求会 404，属已知差距，实装时以本文件为契约基线补齐。
