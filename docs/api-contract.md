# 生产排产调度 Agent 平台 — 前后端 API 契约 (v0.1)

> 本文档是前后端的唯一真相源（single source of truth）。前端据此生成 TypeScript 类型、API 客户端与 MSW mock；后端据此实现 FastAPI 端点与 Pydantic schema。
> 标记 **【待确认】** 的部分需根据后端实际实现补全或修正。

---

## 0. 通用约定

- **Base URL**：`【待确认，如 http://localhost:8000/api/v1】`
- **认证**：初始版本单用户，预留 `Authorization: Bearer <token>` header，暂不强校验
- **内容类型**：普通请求 `application/json`；流式接口 `text/event-stream`
- **错误响应统一结构**：

```jsonc
{
  "error": {
    "code": "string",        // 机器可读错误码，如 ROUTE_FAILED / SOLVER_TIMEOUT
    "message": "string",     // 人类可读说明
    "detail": {}             // 可选，结构化细节
  }
}
```

- **会话标识**：所有交互携带 `session_id`，用于会话粘性、记忆、SolveRun 关联

---

## 1. 核心枚举与共享类型

### 1.1 IntentType（路由四分类）
```
"planning" | "scheduling" | "query" | "uncertain"
```

### 1.2 AuthorizationLevel（动作授权级别）
```
"auto"                  // 可直接执行
"requires_confirmation" // 需人工二次确认
```

### 1.3 RouteSource（路由由哪一层产生，对应你的四层路由）
```
"command"    // Layer 0 斜杠命令/按钮，零歧义
"embedding"  // Layer 1 嵌入路由
"llm"        // Layer 2 LLM 结构化分类
"clarified"  // Layer 3 澄清后确定
```

### 1.4 RouteDecision（路由判定结果，前端 Route Badge 直接消费）
```jsonc
{
  "intent": "IntentType",
  "confidence": 0.92,                 // 0~1
  "source": "RouteSource",
  "entities": {                       // 抽取出的实体，结构随意 key-value
    "line": "3号线",
    "scope": "今日任务令"
  },
  "reason": "用户要求下发任务令，属执行层动作",
  "is_composite": false,              // 是否复合任务（跨引擎）
  "steps": [                          // 复合任务时的子任务序列，否则为空
    { "engine": "IntentType", "task": "string" }
  ]
}
```

---

## 2. Orchestrator — 统一对话入口

### 2.1 发送消息（流式）
`POST /chat/stream`  →  `text/event-stream`

**请求：**
```jsonc
{
  "session_id": "string",
  "message": "把2号线那批单重排一下",
  "current_engine": "planning | scheduling | query | null"  // 会话粘性用，当前所处引擎
}
```

**SSE 事件流**【待确认事件命名与粒度】：
```
event: route        // 路由判定完成，先于内容返回，前端立即渲染 Route Badge
data: { ...RouteDecision }

event: token        // LLM 流式输出的增量文本
data: { "delta": "正在为你重排..." }

event: clarify      // intent=uncertain 时，返回澄清卡片
data: {
  "question": "想让我做哪个？",
  "options": [
    { "id": "opt1", "label": "重新排产", "route_to": "planning" },
    { "id": "opt2", "label": "查齐套并处置", "route_to": "scheduling" }
  ]
}

event: context      // 通知前端激活/更新右侧 Context Panel
data: { "engine": "planning", "payload": { /* 见各引擎章节 */ } }

event: done         // 本轮结束
data: { "message_id": "string" }

event: error
data: { ...错误结构 }
```

### 2.2 澄清回选
`POST /chat/clarify`

**请求：**
```jsonc
{
  "session_id": "string",
  "option_id": "opt1",      // 选项答案直接路由，不再跑分类
  "route_to": "planning"
}
```
**响应：** 同 `/chat/stream` 的 SSE 流（按选定引擎继续）。

---

## 3. 排产引擎 Planning

> 有状态会话核心对象是 **SolveRun**。每次求解产生一个 SolveRun，Context Panel 据此做参数确认、甘特对比、多版本 KPI 对比、无解诊断。

### 3.1 PlanningParams（抽取出的排产参数，供前端确认/编辑）
```jsonc
{
  "order_scope": ["SO-1001", "SO-1002"],   // 【待确认】订单范围表达
  "lines": ["LINE-02"],
  "due_constraints": { /* 【待确认】交期约束结构 */ },
  "objectives": [                          // 可选的优化目标全集 + 已选
    { "id": "due_rate", "label": "交期达成率", "selected": true, "priority": 1 },
    { "id": "makespan", "label": "最小化完工时间", "selected": true, "priority": 2 }
  ]
}
```

### 3.2 提交求解
`POST /planning/solve`

**请求：**
```jsonc
{
  "session_id": "string",
  "params": { /* PlanningParams，含用户确认/修改后的目标与优先级 */ }
}
```

**响应：SolveRun**
```jsonc
{
  "solve_run_id": "string",
  "status": "feasible | infeasible | timeout",  // 【待确认】状态枚举
  "kpis": {                                       // 结果态：KPI 表，用于多版本对比
    "due_rate": 0.95,
    "makespan_hours": 72,
    "changeover_count": 8
  },
  "gantt": { /* GanttData，见 3.4 */ },
  "baseline_gantt": { /* 规则基线甘特，可选，用于对比 */ },
  "explanation": "本方案优先保交期，相比基线换型减少 3 次...",
  "infeasible_report": {                          // 仅 infeasible 时存在（IIS 诊断）
    "conflicts": [ { "constraint": "string", "human_readable": "3号线产能不足以..." } ],
    "relax_suggestions": [
      { "id": "r1", "label": "放宽交期 2 天", "action": { /* 可回传执行 */ } }
    ]
  }
}
```

### 3.3 获取 SolveRun 历史（多版本对比）
`GET /planning/solve-runs?session_id=string`
→ 返回 `SolveRun[]`，前端横向对比 KPI + 缩略甘特。

### 3.4 GanttData【待确认数据结构】
```jsonc
{
  "resources": [ { "id": "LINE-02", "name": "2号线" } ],
  "tasks": [
    {
      "id": "T1", "resource_id": "LINE-02",
      "order_id": "SO-1001",
      "start": "2026-06-26T08:00:00", "end": "2026-06-26T12:00:00",
      "type": "production | changeover | downtime | shortage",  // 标注停机/换型/缺料
      "label": "string"
    }
  ]
}
```

---

## 4. 调度引擎 Scheduling

### 4.1 齐套检查
`GET /scheduling/kitting?session_id=string&scope=...`
```jsonc
{
  "items": [
    {
      "work_order": "WO-2001",
      "material_rate": 0.8,        // 物料齐套率
      "tooling_rate": 1.0,         // 工装齐套率
      "status": "ready | partial | blocked",   // 红黄绿
      "missing": [ { "material": "M-330", "qty_short": 50 } ]
    }
  ]
}
```

### 4.2 待下发任务令列表
`GET /scheduling/dispatch-orders?session_id=string`
```jsonc
{
  "orders": [
    {
      "id": "DO-3001",
      "line": "LINE-03",
      "summary": "下发 WO-2001 至 3 号线",
      "authorization": "auto | requires_confirmation",  // 前端两级视觉区分
      "action": { /* 执行该动作时回传的 payload */ }
    }
  ]
}
```

### 4.3 执行调度动作（含二次确认）
`POST /scheduling/execute`
```jsonc
{
  "session_id": "string",
  "action_id": "DO-3001",
  "confirmed": true     // requires_confirmation 的动作必须为 true 才执行
}
```
**响应：**
```jsonc
{
  "status": "executed | rejected | pending",
  "audit_id": "string",          // 进审计日志
  "message": "已下发至 3 号线"
}
```

### 4.4 异常影响范围
`GET /scheduling/exception-impact?session_id=string&event_id=...`
```jsonc
{
  "trigger": "3号线设备报警",
  "affected_orders": ["SO-1001", "SO-1005"],
  "suggested_actions": [ { "label": "改派至2号线", "authorization": "requires_confirmation", "action": {} } ]
}
```

---

## 5. 查询引擎 Query (RAG + LLM)

### 5.1 RAG 查询（流式）
`POST /query/stream`  →  `text/event-stream`
```jsonc
// 请求
{ "session_id": "string", "question": "什么是齐套？我们的齐套规则是什么？" }
```
**SSE：** `token` 事件流式返回正文；结束前返回 `sources`：
```jsonc
event: sources
data: {
  "sources": [
    {
      "id": "src1",
      "doc_name": "排产规则手册 v3",
      "section": "4.2 齐套定义",
      "snippet": "齐套指...",        // 检索片段
      "relevance": 0.88
    }
  ]
}
```

### 5.2 知识库文档增删改查（RAG 知识库管理）

查询引擎选中时，前端右侧面板对知识库文档做增删改查；embedding 与 llm 均复用后端
配置文件模型 (`EMBED_MODEL` / `LLM_MODEL`)。`KnowledgeDoc` 形状：
```jsonc
{
  "doc_id": "kb_a1b2c3d4e5",
  "name": "排产规则手册 v3.pdf",
  "type": "pdf",              // 文件后缀 (不含点)
  "chunk_count": 42,          // 已入库的向量片段数
  "bytes": 183422,
  "status": "ready",          // ready | failed(嵌入未配置，未参与检索)
  "added_at": "2026-07-03T10:00:00Z"
}
```

**列出（查）** `GET /knowledge`
```jsonc
{
  "docs": [ /* KnowledgeDoc[] , 按 added_at 倒序 */ ],
  "supported_extensions": [".md", ".txt", ".csv", ".html", ".pdf", ".docx"]
}
```

**上传（增）** `POST /knowledge` — `multipart/form-data`，字段 `file`
→ `200` 返回新建的 `KnowledgeDoc`。
类型不支持 → `415`；单文件超 10MB → `413`。

**修改（改）** `PUT /knowledge/{doc_id}` — `multipart/form-data`
- 传 `file` → 换内容（删旧片段 + 重新入库到同一 `doc_id`）
- 传 `name`（表单字段）→ 仅改显示名
→ `200` 返回更新后的 `KnowledgeDoc`；`doc_id` 不存在 → `404`。

**删除（删）** `DELETE /knowledge/{doc_id}`
```jsonc
{ "doc_id": "kb_a1b2c3d4e5", "removed_chunks": 42 }
```
`doc_id` 不存在 → `404`。

---

## 6. 可观测 — 决策日志

`GET /audit/timeline?session_id=string`
→ 时间线：路由判定、引擎动作、工具调用、LLM 调用，前端可观测抽屉消费。
```jsonc
{
  "events": [
    {
      "ts": "2026-06-25T10:00:00Z",
      "type": "route | engine_action | tool_call | llm_call",
      "summary": "string",
      "detail": {}
    }
  ]
}
```

---

## 待办清单（交给前端前先补全）

- [ ] 确认 Base URL 与端点前缀
- [ ] 确认 SSE 事件命名与粒度（第 2.1 节）
- [ ] 确认 PlanningParams 中交期约束、订单范围的具体结构
- [ ] 确认 SolveRun.status 枚举与 GanttData 字段
- [ ] 确认是否需要 WebSocket 通道（调度事件层主动推送唤醒）
- [ ] 补全各引擎 entities 的实际字段
