# Main Loop — 主循环与编排器

## Overview

本项目的核心是**三层意图路由** + **三引擎范式**：用户输入 → 嵌入语义路由/LLM分类 → 派发至对应引擎 → 执行固定工作流/ReAct智能体/RAG问答 → 输出结果。编排器 (`Orchestrator`) 作为统一入口，协调整个流程，提供进度反馈、审计记录、会话记忆等横切关注点。

## Architecture: 三引擎三范式

| 引擎 | 范式 | 用途 |
|------|------|------|
| **Planning Engine** | 固定工作流 (策略插件框架) | 排产/重排/优化，CP-SAT求解器驱动 |
| **Scheduling Engine** | ReAct智能体循环 | 齐套检查/催料/任务令下发/异常处置 |
| **Query Engine** | RAG + LLM | 订单/库存/任务令状态查询，知识库问答 |
| **Skill Engine** | ReAct (动态系统提示词) | 自定义技能包执行 |

## Composition Root: bootstrap.py

`build_platform()` 是唯一的组装根，负责实例化并连接所有组件：

```
┌─ 共享底座 ──────────────────────────────────┐
│ IntegrationAdapter (MockAdapter)         │
│ AuditLog (审计日志)                       │
│ PendingActionStore (待确认动作)           │
│ ActionGate (写操作授权闸口)               │
│ ConversationMemory (会话记忆)             │
│ SessionStore (会话持久化)                 │
│ LLMClient (大模型客户端)                  │
│ ToolRegistry (工具注册表)                 │
└───────────────────────────────────────────┘
┌─ 三引擎 ────────────────────────────────────┐
│ PlanningEngine (固定工作流 + 策略插件)    │
│ SchedulingEngine (AgentLoop + 工具白名单) │
│ QueryEngine (RAG + 只读工具)              │
│ SkillEngine (动态AgentLoop)               │
└───────────────────────────────────────────┘
┌─ 路由层 ────────────────────────────────────┐
│ EmbeddingRouter (嵌入语义路由，第1层)     │
│ IntentRouter (LLM分类 + 澄清，第2-3层)    │
│ Orchestrator (统一入口，协调整个流程)     │
└───────────────────────────────────────────┘
┌─ 事件层 ────────────────────────────────────┐
│ EventBus (事件总线)                       │
│ PatrolScheduler (定时巡检)                │
└───────────────────────────────────────────┘
```

## Flow 1: Normal Chat (正常对话主循环)

```
用户输入
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│ Orchestrator.handle()                                      │
│  1. 检查: 前端是否选定技能 (skill_id≠None)？               │
│     ├─ 是 → 跳过路由，直接派发到 SkillEngine              │
│     └─ 否 → 继续                                           │
│  2. 检查: 前端是否指定引擎 (route≠auto)？                  │
│     ├─ 是 → 跳过路由，直接派发指定引擎                     │
│     └─ 否 → 继续                                           │
│  3. 检查: 是否有待澄清上下文 (pending_clarification)？    │
│     ├─ 是 → 解析澄清回复: 选项式→直接路由/开放式→回LLM  │
│     └─ 否 → 正常路由                                       │
│  4. 正常路由: 第1层嵌入 → 第2层LLM → 第3层澄清           │
│  5. 记录路由审计 → 派发到对应引擎                         │
│  6. 追加助手消息到记忆 → 返回 ChatResponse               │
└─────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│ 路由决策 (RouteDecision)                                    │
│  intent: planning/scheduling/query/skill/ambiguous        │
│  confidence: 0.0~1.0                                       │
│  route_method: forced/embedding/llm/clarified/fallback    │
│  skill_id: str (仅intent=skill时)                         │
└─────────────────────────────────────────────────────────────┘
   │
   ├─→ 低置信/ambiguous ────────────────────────┐
   │                                            │
   │  (显示澄清选项: ①重新排产 ②调度执行 ③查询)│
   │  用户选择后走 /chat/clarify                │
   │                                            │
   ▼                                            │
┌─────────────────────────────────────────┐    │
│ IntentRouter.route()                    │    │
│  ├─ 第1层: EmbeddingRouter.classify() │    │
│  │   (向量相似度 + margin判断)         │    │
│  │   ├─ 高置信 → 直接返回              │    │
│  │   └─ 低置信 → 走第2层              │    │
│  ├─ 第2层: LLM.classify()              │    │
│  │   (结构化分类: planning/scheduling/ │    │
│  │    query/skill/ambiguous)          │    │
│  └─ 降级: fallback → ambiguous        │    │
└─────────────────────────────────────────┘    │
   │                                            │
   └────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────┐
│ _gate_and_dispatch()                    │
│  ├─ confidence >= threshold → 执行    │
│  └─ 否则 → 澄清                         │
└─────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│ _dispatch() — 按意图派发到对应引擎                         │
│                                                           │
│ ├─ planning → PlanningEngine.handle_chat()               │
│ │   (固定工作流: 提取参数 → 选择策略 → 求解 → 验证 → 解释)│
│ │                                                         │
│ ├─ scheduling → SchedulingEngine.handle_chat()           │
│ │   (AgentLoop.run(): ReAct循环执行)                       │
│ │                                                         │
│ ├─ query → QueryEngine.handle()                           │
│ │   (RAG检索 → 增强生成 → 返回结果)                       │
│ │                                                         │
│ └─ skill → SkillEngine.handle()                           │
│     (动态AgentLoop: 加载技能 → 组装工具 → 执行ReAct)     │
└─────────────────────────────────────────────────────────────┘
   │
   ▼
 EngineResponse → ChatResponse → SSE流式输出
```

## Flow 2: Intent Routing (三层意图路由)

### Layer 1: EmbeddingRouter (嵌入语义路由)

把用户输入向量化，与各意图的种子例句 (`routing_examples.yaml`) 做余弦相似度匹配：

```python
class EmbeddingRouter:
    async def classify(message: str) -> EmbedResult:
        # 1. 向量化用户输入
        query_vector = await llm.embed([message])[0]
        # 2. 与所有种子例句计算相似度
        scores = {
            intent: max(cosine(query_vector, example)
                        for example in intent_examples)
            for intent, intent_examples in examples.items()
        }
        # 3. 取最高分 + margin判定
        top_intent, top_score = sorted(scores.items())[-1]
        margin = top_score - second_score
        # 4. margin >= MIN_MARGIN (0.05) 才认为高置信
        return EmbedResult(
            intent=top_intent,
            score=top_score,
            margin=margin,
            confident=margin >= MIN_MARGIN
        )
```

**技能向量动态失效**：技能导入/删除时 `SkillStore.version` 自增，`EmbeddingRouter` 检测到版本变化后重嵌技能例句。

### Layer 2: IntentRouter (LLM 结构化分类)

嵌入路由低置信/不可用时，调用 LLM 做结构化分类：

```python
class IntentRouter:
    async def route(message) -> RouteDecision:
        # (可选) 跳过嵌入: 用于澄清后的开放式回答
        # LLM 结构化分类: {intent, confidence, entities, skill_id}
        decision = await llm.classify(
            system_prompt,
            f"最近对话: {history}\n当前引擎: {current_engine}\n用户输入: {message}",
            RouteDecision
        )
        # 技能路由校验: skill_id 必须在可路由技能列表中
        if decision.intent == "skill" and decision.skill_id not in routable_names:
            decision.intent = "ambiguous"
            decision.confidence = 0.0
        return decision
```

### Layer 3: Clarification (澄清)

置信度低于 `route_confidence_threshold` (默认 0.7) 或 `intent=ambiguous` 时：

```
我不太确定你的意图，想让我做哪个？请直接回复序号或关键词：
① 重新排产 —— 重新求解这批订单的生产计划
② 调度执行 —— 查齐套/催料/下发任务令/处置异常
③ 只是查数据 —— 订单/库存/任务令状态查询
```

**澄清回复处理**：
- **选项式** (≤4字符)：直接按所选路由原请求 (`_route_clarified`)
- **开放式**：合并上下文，回到第2层 LLM 分类 (跳过嵌入)

## Flow 3: Scheduling AgentLoop (ReAct 智能体循环)

调度引擎的核心是通用 ReAct 循环，骨架参考 OpenHands：

```
┌─ 外层循环终止态 ────────────────────────────────────┐
│ FINISHED   — 模型给出纯文本结论 (=等用户输入)    │
│ MAX_STEPS  —— 步数硬上限 (默认 8)，强制收尾      │
│ STUCK      —— 卡死软检测命中 (重复/连续拦截)     │
│ ERROR      —— LLM 重试仍失败                     │
└─────────────────────────────────────────────────────┘

┌─ 单步三分支 ──────────────────────────────────────────┐
│ TOOL_CALLS —— 走护栏执行工具，观察回喂            │
│ CONTENT    —— 纯文本 → FINISHED                   │
│ EMPTY      —— 既无工具也无内容 → nudge纠偏       │
└─────────────────────────────────────────────────────┘

┌─ 六道护栏 ─────────────────────────────────────────────┐
│ 1. 步数硬上限 max_steps → 必停                      │
│ 2. 卡死软检测 StuckDetector → 重复/连续拦截 → STUCK│
│ 3. 工具白名单 → 只允许白名单内工具                  │
│ 4. 写操作前置断言 precondition → 代码硬规则检查    │
│    └─ 可选: 技能级追加断言 extra_preconditions       │
│ 5. LLM 抖动重试 → 瞬时失败重试 2次 → 仍失败→ ERROR│
│ 6. 观察截断 observation_max_bytes → 单条观察限长回喂│
└─────────────────────────────────────────────────────┘
```

### AgentLoop.run() 代码流程

```python
class AgentLoop:
    async def run(task, history=None):
        # 1. 初始化状态: 消息历史 + 待确认动作快照
        before_pending_ids = {a.action_id for a in pending.list_pending()}
        st = _RunState(messages=[*history, {"role": "user", "content": task}])

        # 2. 外层循环
        iteration = 0
        while st.status == RUNNING:
            # 硬上限检测
            if iteration >= max_steps:
                st.status = MAX_STEPS; break
            # 卡死软检测
            if self._is_stuck(st):
                st.status = STUCK; break
            # 单步执行
            await self._step(st, openai_tools)
            iteration += 1

        # 3. 被强制中断的，追加一次收尾发言
        if st.status in (MAX_STEPS, STUCK):
            st.answer = await self._force_final(st)

        # 4. 收集新产生的待确认动作 (快照差集)
        new_pending = [a for a in pending.list_pending()
                       if a.action_id not in before_pending_ids]
        return AgentResult(
            answer=st.answer,
            steps=st.steps,
            pending_actions=new_pending,
            stop_reason=st.status
        )
```

### AgentLoop._step() 单步执行

```python
async def _step(st, openai_tools):
    # 1. LLM 响应 (带抖动重试)
    turn = await self._chat_turn_resilient(st.messages, openai_tools)

    # 2. 三分支处理
    if not turn.tool_calls:
        text = turn.text.strip()
        if text:  # CONTENT: 纯文本 = 结论 = 本轮结束
            st.answer = turn.text; st.status = FINISHED
        else:  # EMPTY: 纠偏 nudge (上限 2次)
            if st.nudges >= _MAX_NUDGES:
                st.status = FINISHED
            st.nudges += 1
            st.messages.append({"role": "user", "content": _NUDGE})
    else:  # TOOL_CALLS: 逐个过护栏执行
        st.messages.append(turn.assistant_message)
        for call in turn.tool_calls:
            observation, blocked = await self._handle_call(call.name, call.args, st)
            # 护栏 6: 超过 observation_max_bytes 的观察截断为
            # {truncated, original_bytes, preview, hint} 后再回喂/留痕
            content, stored = self._serialize_observation(observation)
            st.steps.append(AgentStep(thought=turn.text, observation=stored, ...))
            st.messages.append({"role": "tool", "content": content, ...})
```

### AgentLoop._handle_call() 工具执行与护栏

```python
async def _handle_call(name, args, st):
    # 护栏 3: 工具白名单
    if name not in self._allowed:
        return {"blocked": f"工具 {name} 不在白名单内"}, True

    # 绕圈检测: 完全相同的调用 (同名同参) 计数并跳过。
    # 计数按「状态纪元」统计: 每次写操作成功后读类计数清零 (状态已变，重读正当)
    key = (name, json.dumps(args, sort_keys=True))
    st.seen[key] = st.seen.get(key, 0) + 1
    if st.seen[key] > 1:
        return {"blocked": "重复的相同工具调用，已跳过"}, True

    tool = self._tools.get(name)

    # 护栏 4: 写操作内置前置断言
    if tool.kind == "write" and tool.precondition is not None:
        result = await tool.precondition(args)
        if not result.ok:
            return {"blocked": f"前置断言未通过: {result.reason}"}, True

    # 护栏 4b: 技能级追加断言 (只叠加，不替换)
    if self._extra is not None:
        for pre in self._extra.get(name, []):
            result = await pre(args)
            if not result.ok:
                return {"blocked": f"技能前置断言未通过: {result.reason}"}, True

    # 执行工具 (失败回喂给模型，不中断循环)
    try:
        result = await self._tools.execute(name, args)
    except Exception as e:
        return {"error": str(e)}, False

    # 写操作成功 → 清读类 seen 计数 (允许写后重读)；写类计数保留 (同参写仍防重)
    if tool.kind == "write":
        st.seen = {k: c for k, c in st.seen.items()
                   if self._tools.get(k[0]).kind == "write"}
    return result, False
```

### 卡死软检测

```python
def _is_stuck(st):
    # 模式①: 同一 (工具, 参数) 累计出现达 3 次 (重复动作打转)
    if any(c >= _STUCK_REPEAT for c in st.seen.values()):
        return True
    # 模式②: 最近连续 3 步全部被护栏拦截 (反复撞墙)
    recent = st.steps[-_STUCK_BLOCKED:]
    if len(recent) >= _STUCK_BLOCKED and all(s.blocked for s in recent):
        return True
    return False
```

## Flow 4: Progress Streaming (进度流式反馈)

编排流程中通过 `ProgressFn` 回调实时推送进度到前端 SSE：

```python
async def handle(..., on_progress=None):
    await emit_progress(on_progress, "识别意图…")
    decision = await self._router.route(...)
    ...
    await emit_progress(on_progress, "求解中 (FlowShopTardiness)…")
    resp = await self._planning_engine.handle_chat(...)
    ...
```

前端 `chat/stream` 端点中：
1. `handle()` 放到后台任务
2. `progress_q` 队列收集进度
3. `_progress_frames()` 生成器实时推送
4. `_sse_from_response()` 把响应流式拆分为 `route` → `token*` → `actions?` → `done`

## Flow 5: Event-Driven Wakeup (事件唤醒)

除了用户对话，调度引擎还可被系统事件唤醒：

```
┌─────────────────────────────────────────────────────────┐
│ PatrolScheduler (定时巡检)                              │
│  - 轮询外部系统: 订单/库存/产线状态变更                │
│  - 预测性齐套检查: 即将缺料的任务令                    │
└─────────────────────────────────────────────────────────┘
   ↓ 发布 SystemEvent
┌─────────────────────────────────────────────────────────┐
│ EventBus (事件总线)                                    │
│  - register_event_handlers() 注册调度引擎回调          │
│  - 回调内部调用 SchedulingEngine.handle_event()        │
└─────────────────────────────────────────────────────────┘
   ↓ 唤醒
┌─────────────────────────────────────────────────────────┐
│ SchedulingEngine (ReAct 智能体)                       │
│  - 自动执行工具链处置异常/催料/下发                     │
└─────────────────────────────────────────────────────────┘
```

## Audit Trail (审计追踪)

所有路由决策、工具调用、授权操作都被记录到 `AuditLog`：

| action | 说明 |
|--------|------|
| `route` | 意图路由决策 |
| `tool_call:{name}` | 工具调用 |
| `precondition_blocked:{name}` | 前置断言拦截 |
| `skill_precondition_blocked:{name}` | 技能前置断言拦截 |
| `authz:pending` / `authz:approved` / `authz:rejected` | 授权状态变更 |

## Resuming Clarification (澄清回选)

前端 `/chat/clarify` 端点调用 `Orchestrator.resume_clarification()`：

1. 从 `ConversationMemory.context` 取出 `pending_clarification`
2. 按用户选择的引擎 (`route_to`) 直接路由原请求
3. 不再经过嵌入/LLM 层

## Confirming Actions (动作确认)

前端 `/chat/confirm` 端点调用 `Orchestrator.confirm()`：

1. `ActionGate.confirm()` 执行授权/拒绝
2. 写操作只有通过授权才真正执行
3. 结果追加到会话记忆

## Key Integration Points (集成要点)

### bootstrap.py 组装要点

```python
def build_platform():
    # 1. 工具库: 注册内置工具 + 挂前置断言
    tools = ToolRegistry()
    register_builtin_tools(tools, ...)
    tools.attach_precondition("dispatch_work_order", make_dispatch_precondition(...))

    # 2. 命名前置断言表 (供技能包按名引用)
    named_preconditions = {
        "dispatch_ready": make_dispatch_precondition(...),
        "expedite_valid": make_expedite_precondition(...),
    }

    # 3. 调度引擎 = AgentLoop (注入工具白名单 + 系统提示词)
    agent = AgentLoop(llm, tools, pending, audit,
                      SCHEDULING_SYSTEM, SCHEDULING_TOOLS, settings.react_max_steps)
    scheduling_engine = SchedulingEngine(agent, kitting, audit)

    # 4. 路由层: EmbeddingRouter + IntentRouter (均注入 skill_store)
    embed_router = EmbeddingRouter(llm, load_examples(), skills=skill_store)
    router = IntentRouter(llm, settings, embed_router, skills=skill_store)

    # 5. 编排器: 注入所有引擎 + 记忆 + 审计 + 闸口
    orchestrator = Orchestrator(router, planning_engine, scheduling_engine,
                                 query_engine, memory, audit, gate, settings,
                                 skill_engine=skill_engine)
```

### main.py 端点要点

```python
@app.post("/chat/stream")
async def chat_stream(req):
    platform = app.state.platform
    store = platform.session_store
    meta = store.get(req.session_id)
    is_first_turn = meta is not None and meta.message_count == 0

    # 首轮: 与编排并发生成标题，避免前端刷新竞态
    title_task = asyncio.create_task(_summarize_title(platform, req.message)) if is_first_turn else None

    # 真流式: 编排放后台任务，执行中经队列实时推 progress 帧
    progress_q = asyncio.Queue()
    handle_task = asyncio.create_task(
        platform.orchestrator.handle(..., on_progress=progress_q.put)
    )
    async for frame in _progress_frames(handle_task, progress_q):
        yield frame

    # 标题落地 (如果有)
    if title_task is not None:
        title = await title_task
        if title:
            store.update_title(req.session_id, title)

    # 响应流式输出
    async for frame in _sse_from_response(resp):
        yield frame
```

## Configuration (配置项)

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `route_confidence_threshold` | 0.7 | 路由置信度门控 |
| `embed_confidence_threshold` | 0.85 | 嵌入路由置信度门控 |
| `react_max_steps` | 8 | ReAct 最大步数 |
| `strategy_confidence_threshold` | 0.7 | 策略选择置信度门控 |
| `rag_top_k` | 5 | RAG 检索 top-k |
| `vector_backend` | "memory" | 向量库后端 ("memory"/"chroma") |

## Design Principles (设计原则)

1. **LLM 不进主循环**：只在语义节点 (意图理解、结果解释、摘要生成) 插入
2. **确定性优先**：路由、护栏、工具执行优先走代码逻辑，LLM 仅做补充
3. **安全不变量**：写操作必经前置断言 + ActionGate 两道护栏，技能只能追加不能移除
4. **可审计**：所有决策和动作都留痕，通过 `AuditLog` / `audit/timeline` 可追溯
5. **渐进式扩展**：v0.1 简单文件存储 → v0.2 SQLite/装配式上下文/压缩，API 契约保持兼容
