# API 契约文档审查 — `docs/api-contract/api-contract.md`

> 目标：审查前后端 API 契约文档的问题。
> 方法：通读契约 + 对照实际后端代码（`scheduling_platform/src/scheduling_platform/`）落地情况。
> 结论：**契约与实现存在系统性、大面积不一致**。契约描述的是一个"REST 化、流式 SSE、有 SolveRun 状态机、带 RAG"的成熟形态；当前实现是"单入口对话式 + 事件驱动 + 内存态"的 v0.1 原型。**契约声明的 10 个端点，0 个路径完全匹配**。此外契约自身还有内部矛盾与不可落地之处。

---

## 一、契约 vs 实现的硬性不一致（最严重）

### 1. 端点清单大面积不匹配
契约声明 10 个端点，实际 `main.py:53-94` 只有 6 个路由：

| 契约端点 | 实际端点 | 差异 |
|---|---|---|
| `POST /chat/stream`（SSE 流式） | `POST /chat`（同步 JSON） | 路径不同 + **非流式**，无 `text/event-stream` |
| `POST /chat/clarify`（澄清回选，回 SSE 流） | `POST /chat/confirm`（确认待执行动作） | 路径不同 + **语义完全不同**：clarify 是路由层澄清选哪个引擎；confirm 是授权层确认动作执行 |
| `POST /planning/solve` | ❌ 不存在 | 排产只经 `/chat` 对话触发 |
| `GET /planning/solve-runs` | ❌ 不存在 | 无 SolveRun 历史概念 |
| `GET /scheduling/kitting` | ❌ 不存在 | 齐套只经对话/事件触发 |
| `GET /scheduling/dispatch-orders` | ❌ 不存在 | 同上 |
| `POST /scheduling/execute` | ❌ 不存在 | 二次确认走 `/chat/confirm` |
| `GET /scheduling/exception-impact` | ❌ 不存在 | 异常影响只经对话返回 |
| `POST /query/stream`（RAG + sources） | ❌ 不存在 | 无独立 query 引擎端点 |
| `GET /audit/timeline?session_id=` | `GET /audit?action=&limit=` | 路径不同 + **过滤维度不同**：契约按 session，实际按 action |
| —（契约无） | `POST /events`（手动注入事件） | 契约漏了测试用端点 |
| —（契约无） | `GET /pending`（待确认动作列表） | 契约漏了，但这是授权闭环关键端点 |
| —（契约无） | `GET /health` | 契约漏了 |

**问题本质**：契约把"对话入口"和"各引擎的 REST 操作端点"分成两类，但实现是**纯对话式单入口**——所有引擎能力都经 `/chat` 自然语言触发，没有独立的 REST 操作端点。这是两种截然不同的前端集成范式，前端若按契约开发将全部 404。

### 2. 核心枚举命名/取值不一致
| 枚举 | 契约 | 实际（`schemas.py:18,22`） |
|---|---|---|
| IntentType | `planning\|scheduling\|query\|uncertain` | `planning\|scheduling\|query\|**ambiguous**` |
| RouteSource 字段名 | `source` | `route_method` |
| RouteSource 取值 | `command\|embedding\|llm\|clarified` | `embedding\|llm\|clarified\|**fallback**`（无 command，多 fallback） |
| AuthorizationLevel | `auto\|requires_confirmation` | 实际三档：`auto\|requires_confirmation\|**deny**` |

字段名 `source` vs `route_method` 会导致前端类型生成与后端字段对不上；`uncertain` vs `ambiguous`、缺 `command`、多 `deny`/`fallback` 会让前端枚举分支永远走不到。

### 3. RouteDecision 结构不一致
契约：`{intent, confidence, source, entities, reason, is_composite, steps}`
实际 `RouteDecision`（`schemas.py:17-23`）：`{intent, confidence, entities, reason, route_method, steps}`
- 实际**无 `is_composite` 字段**（契约用它判断是否复合任务）
- `steps` 实际是 `list[RouteStep] | None` 且 TODO(v0.2) 未实现；契约的 step 结构是 `{engine, task}`，实际 `RouteStep` 是 `{intent, instruction}`（字段名都不同）
- 字段名 `source` vs `route_method`（见上）

### 4. 无流式（SSE/WebSocket）— 契约的核心交互范式不存在
- 全仓库无 `StreamingResponse`/`text/event-stream`/`websocket`。
- 契约 2.1 定义了 5 种 SSE 事件（route/token/clarify/context/done/error），2.2 和 5.1 也都是 SSE。**这是契约的交互核心，但实现是同步 JSON 一次性返回**。
- 后果：契约的 `event: route`（先返回路由徽章再流式正文）、`event: token`（打字机效果）、`event: clarify`（澄清卡片）、`event: context`（右侧面板更新）**全部无法实现**。实际 `ChatResponse`（`schemas.py:26-34`）一次性返回 `reply + route + pending_actions + data + needs_clarification + options`。

### 5. SolveRun 概念完全不存在
契约把 SolveRun 作为"有状态会话核心对象"：每次求解产生一个，可历史对比、多版本 KPI 对比、甘特对比、无解诊断。
- 实际 `PlanningResult` 无 `solve_run_id`，无 `gantt`/`baseline_gantt`/`kpis`/`infeasible_report` 结构。
- 求解结果以**单值覆盖**存内存（`engine.py` + `memory.py` 存 history），**无法多版本对比**。
- `GET /planning/solve-runs` 端点不存在。

### 6. GanttData 结构不存在
契约定义了 resources/tasks 结构，task 有 `type: production|changeover|downtime|shortage` 和 `start/end`（datetime）。
- 实际排产结果是 `Assignment` 列表，时间为 **`date` 而非 `datetime`**（无时分），无 `type` 枚举（无换型/停机/缺料块标注）。
- 前端若按契约画甘特，数据字段全对不上。

### 7. query 引擎 / RAG 不存在
契约第 5 章有独立 query 引擎 + RAG sources（doc_name/section/snippet/relevance）。
- 实际 `QueryHandler` 只是 LLM + 工具调用，**无 RAG、无知识库、无 sources 概念**（grep 零匹配）。
- 契约的 `event: sources` 事件无法产生。

### 8. infeasible_report / IIS 诊断不存在
契约说 infeasible 时返回 `conflicts + relax_suggestions`（IIS 不可行性诊断）。
- 实际 validator 只返回简单不可行原因，无 IIS 冲突提取、无松弛建议回传结构。

### 9. 调度二次确认机制描述与实现不符
契约 `POST /scheduling/execute` 用 `{action_id, confirmed}` 触发执行。
- 实际二次确认走 `/chat/confirm`，请求体是 `{session_id, action_id, approved}`（字段名 `approved` 非 `confirmed`）。
- 待确认动作列表实际走 `GET /pending`（全量，非按 session），契约无此端点。

### 10. 审计 timeline 过滤与事件分类不符
契约 `/audit/timeline?session_id=` 按 session 过滤，事件 `type: route|engine_action|tool_call|llm_call`。
- 实际 `/audit?action=&limit=` 按 action 过滤（**无 session 维度**）。
- 实际审计 entry 的 type 字段与契约的四分类是否一致需核对，但至少过滤维度不同。

### 11. 错误响应结构与错误码未实现
契约定义 `{error: {code, message, detail}}` + 错误码（ROUTE_FAILED/SOLVER_TIMEOUT 等）。
- 实际 `main.py` 无统一异常处理器，错误是 FastAPI 默认的 `{detail: "..."}`，无 `error` 包装、无机器可读 code。

### 12. 认证未实现
契约说预留 `Authorization: Bearer`。实际无任何认证中间件。

### 13. `current_engine` 会话粘性字段
契约 `/chat/stream` 请求体有 `current_engine`（客户端传当前引擎做粘性）。
- 实际 `ChatRequest`（`main.py:37-39`）只有 `session_id` 和 `message`，**不接受 current_engine**。会话粘性实际靠服务端 Memory 存（v0.2 预留），与契约"客户端传"的模型冲突。

---

## 二、契约内部矛盾与描述不完整

### 14. `/chat/clarify` 的返回类型自相矛盾
2.2 节说"响应：同 `/chat/stream` 的 SSE 流（按选定引擎继续）"。但 `/chat/stream` 是 SSE，而 clarify 是一次性路由决策后继续——澄清回选本质是一次性决策，套 SSE 流语义混乱。且实际实现根本不是这个端点。

### 15. `downtime`/`shortage` 甘特块的数据来源未定义
GanttData 的 task.type 含 `downtime|shortage`，但这俩是调度层概念（停机/缺料），而甘特是排产层产物。契约未说明排产甘特如何融合调度层数据——跨引擎数据来源未定义，前端无法渲染。

### 16. `entities` 结构"随意 key-value"不可类型化
1.4 节 entities 注释"结构随意 key-value"，但契约号称是"唯一真相源，前端据此生成 TS 类型"。随意 key-value 无法生成类型，自相矛盾。待办清单也承认"补全各引擎 entities 实际字段"未做。

### 17. PlanningParams 大量【待确认】未收敛
`order_scope`、`due_constraints`、`objectives` 都标【待确认】，`SolveRun.status` 枚举、GanttData 字段也【待确认】。作为"唯一真相源"，核心结构未定稿，前端无法据此开发。

### 18. 事件层主动推送通道缺失
契约待办问"是否需要 WebSocket（调度事件层主动推送唤醒）"。但契约正文用 SSE 做单向流式，SSE 是请求-响应模型，**无法承载服务端主动推送**（缺料预警、异常报警需即时到达前端）。契约对事件层如何到达前端这一关键问题没有设计，只有一句待办。实际实现也确实没有推送通道，前端只能轮询 `/pending`。

### 19. 响应中 `data: {}` 与各引擎 payload 的映射缺失
契约 2.1 的 `event: context` 说 payload 见各引擎章节，但第 3、4 章定义的是 SolveRun / kitting / dispatch 等独立结构，并未说明这些结构如何塞进 `context.payload`。Context Panel 该消费什么字段未定义。

### 20. Base URL 与端点前缀未定
0 节 Base URL 标【待确认】，但这是契约最基础的项，影响所有端点路径。作为"唯一真相源"却连 base 都没定。

---

## 三、问题严重度归类

### P0 — 契约根本性失效（前端按此开发全部失败）
- #1 端点清单大面积不匹配（10 个 0 命中）
- #4 无流式 SSE（契约交互核心不存在）
- #5 SolveRun 概念不存在
- #7 RAG query 引擎不存在
- #2 枚举命名/取值不一致（字段名 source vs route_method 会让类型生成全错）

### P1 — 结构性不一致（前端类型/渲染错误）
- #3 RouteDecision 缺 is_composite、steps 结构不同
- #6 GanttData 不存在且字段类型不符（date vs datetime）
- #8 infeasible_report 不存在
- #9 二次确认端点/字段名不符（confirmed vs approved）
- #10 审计过滤维度不符
- #11 错误响应结构未实现
- #13 current_engine 字段不接受

### P2 — 契约内部矛盾/不完整（需在设计层面收敛）
- #14 clarify 返回类型矛盾
- #15 跨引擎甘特块来源未定义
- #16 entities 随意 key-value 不可类型化
- #17 大量【待确认】未收敛
- #18 事件层推送通道未设计
- #19 context payload 映射缺失
- #20 Base URL 未定
- #12 认证未实现（预留即可，影响小）

---

## 四、根因与方向选择

**根因**：契约显然是在实现之前（或独立于实现）按"理想成熟形态"写的，而实现走了"对话式单入口 + 事件驱动"的 v0.1 路线。两者是**不同的产品形态**，不是"实现落后于契约"的程度差异。

**两条互斥的修复方向**（需用户决策）：

- **方向 A — 收敛契约到当前实现**：把契约改成"单入口对话式 + `/chat` `/chat/confirm` `/pending` `/audit` `/events` `/health`"，删掉 SolveRun/RAG/SSE/独立引擎端点等实现里没有的东西。优点：诚实反映现状，前端能立刻开发；缺点：放弃 REST 化与流式的产品愿景，甘特对比/多版本等价值点延后。

- **方向 B — 推进实现向契约靠拢**：实现 SSE 流式、SolveRun 持久化、GanttData、RAG、各引擎 REST 端点、统一错误处理。优点：达成契约愿景；缺点：工作量极大，相当于把 v0.1 重做大半，且契约内部矛盾（#14-#20）仍需先在契约层解决。

- **方向 C — 分层契约**：把契约拆为"v0.1 实际契约"（对话式）+ "v0.2 目标契约"（REST+流式+SolveRun），明确标注演进路径。兼顾诚实与愿景。

---

## 五、需修改的关键文件（若后续修订契约）

- `/Users/zhouwentao/Desktop/manufacturing-agent/docs/api-contract/api-contract.md` — 契约文档本身（修订对象）
- `/Users/zhouwentao/Desktop/manufacturing-agent/scheduling_platform/src/scheduling_platform/main.py` — 实际端点真相源（对照）
- `/Users/zhouwentao/Desktop/manufacturing-agent/scheduling_platform/src/scheduling_platform/orchestrator/schemas.py` — RouteDecision/ChatResponse 真相源（对照）
- `/Users/zhouwentao/Desktop/manufacturing-agent/scheduling_platform/src/scheduling_platform/domain/models.py` — PlanningResult/Assignment/PendingAction 真相源（对照）

---

*本文件为 plan mode 审查产出，未修改任何项目文件。*
