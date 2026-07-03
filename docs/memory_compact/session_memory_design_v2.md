# 排产调度 Agent 平台 —— 会话压缩与记忆模块设计文档（v2 重构版）

> 本文档是独立自洽的设计文档，面向两类读者：
> 1. Murphy（方案评审）；
> 2. Claude Code(据此实现代码，无需其他上下文即可开工)。
>
> 已确认的全局参数：主模型上下文窗口按 **200K tokens** 计；压缩触发后目标水位 **50%**；
> 摘要模型使用 **Haiku 级轻量模型**；**单用户**部署；会话**可跨天挂起再恢复**；
> CompactionEvent **持久化到 DB**。

---

## 1. 设计输入：业务特点 → 设计推论

本方案不是通用聊天机器人的记忆方案，每个设计决策都从平台的业务事实推出。

### 1.1 平台背景（供 Claude Code 理解）

平台是一个排产调度 Agent，Orchestrator 之下有三个引擎：

- **Planning Engine（排产）**：固定工作流范式，CP-SAT 求解器，核心对象是有状态的 `SolveRun` 会话（含甘特图对比、IIS 不可行诊断、多轮参数确认迭代）；
- **Scheduling Engine（调度）**：ReAct 范式处理派工/齐套/催料/异常，写操作前有代码级前置断言 + 强制授权确认；
- **Query Engine（问答）**：RAG + LLM 处理概念/知识类问题。

硬性架构原则：**LLM 不进入主控制循环**，只在语义节点（意图理解、结果解释、诊断说明、摘要生成）插入。本模块的设计同样遵守：记忆的写入和压缩的触发全部由确定性代码控制，LLM 只承担"把一段文本摘要成另一段文本"这一件事。

### 1.2 五个业务事实与对应推论

**事实 A：最有价值的状态本来就是结构化的，且已存在于平台数据库。**
SolveRun 的参数、求解结果、甘特图数据、IIS 集合、WorkflowRun 的步骤状态——这些都在平台 DB 里有权威副本。对话上下文不需要"背着"这些数据，只需要持有**引用（ID）+ 简短语义摘要**。
→ 推论：压缩的第一手段不是"把长文本变短"，而是**从源头不让大负载进入上下文**（结构化卸载）。

**事实 B：上下文的 token 压力主要来自工具结果，不是对话文本。**
一次求解的原始输出（排程明细、日志）可能是几万 token；用户和 Agent 的对话每轮只有几百 token。
→ 推论：对工具结果做**确定性模板摘要（不用 LLM）**+ 全量归档，能消解 80% 以上的压力；LLM 摘要只留给真正的对话流。

**事实 C：上下文条目可分为"可再生"和"不可再生"两类。**
- 可再生：RAG 检索到的知识片段、从 DB 生成的 Run 摘要——随时可以重新取回；
- 不可再生：用户的原话、用户做出的确认与决策、Agent 给出的承诺、错误现场。
→ 推论：**可再生内容过期直接丢弃（不摘要，不浪费 Haiku 调用）；不可再生内容才值得摘要，且其中一部分永不有损压缩**。

**事实 D：会话轮数不确定，且会跨天挂起再恢复。**
→ 推论：不能把上下文当作"进程内不断增长的列表"。**上下文必须每轮从持久化存储装配出来**，恢复会话 = 执行同一个装配函数，不存在特殊的"恢复逻辑"。

**事实 E：排产决策要可回溯、可审计（"当时 Agent 看到了什么"）。**
错误栈、IIS 结果、待授权的写操作是最高价值信息，压缩丢失它们的代价是真实的业务损失。
→ 推论：原文**永不删除**（append-only 日志）；每次压缩产生**审计记录（CompactionEvent）**；受保护条目有**零丢失硬断言**。

---

## 2. 核心架构决策：装配式上下文（Assembled Context）

业界常见做法是"聊天日志不断增长，超阈值时原地削减"（Claude Code 的 auto-compact 即此思路）。本方案采用另一种范式，更契合事实 A/D：

> **上下文不是一个被维护的对象，而是一个函数的返回值。**
> 每轮调用主模型前，执行 `assemble_context(session)`，从持久化存储确定性地装配出本轮上下文。

```
assemble_context(session) =
    [系统提示词]
  + [SessionFacts 会话事实卡]        ← 始终在场，≤2K tokens
  + [活跃 Run 摘要区]                ← 从平台 DB 实时生成，≤4K tokens
  + [滚动摘要 RollingSummary]        ← 已压缩历史的语义浓缩，≤6K tokens
  + [受保护条目区]                   ← 尚未解决的错误/待授权项，原文
  + [近期原文尾部 Tail]              ← last_compacted_seq 之后的完整条目
```

这个范式带来三个直接收益：

1. **挂起/恢复零成本**：跨天恢复就是重新执行装配函数，不需要序列化"内存中的上下文对象"；
2. **压缩变成"移动一个指针 + 写一条摘要"**：压缩不修改历史（append-only），只是把 `last_compacted_seq` 前移，并把被越过的段落浓缩进 RollingSummary；
3. **DB 中的权威状态永远新鲜**：活跃 Run 摘要区每轮重新生成，不存在"上下文里的 SolveRun 状态过期了"的问题。

### 2.1 200K 窗口的预算表

| 区块 | 预算上限 | 说明 |
|---|---|---|
| 系统提示词 + 工具 schema | ~10K | 固定开销 |
| SessionFacts | 2K | 超限时触发事实卡整理（见 §3.1） |
| 活跃 Run 摘要区 | 4K | 确定性模板生成，可再生 |
| RollingSummary | 6K | 超限时触发摘要合并（见 §5.4） |
| 受保护条目区 | 8K（软） | 超限报警，见 §5.5 |
| 近期原文尾部 Tail | 其余 ~170K | 压缩的主要作用对象 |

**水位线（对装配后总 token 数计算）：**

- 软水位 `SOFT_WM = 140K`（70%）：触发常规压缩，目标压回 `TARGET_WM = 100K`（50%）；
- 硬水位 `HARD_WM = 170K`（85%）：触发激进压缩（保留尾部最近 6 轮 + 受保护条目，其余全部摘要）；
- 兜底：若激进压缩后仍超限（理论上只在受保护条目异常膨胀时发生），报错并提示用户处理，**不静默丢弃受保护条目**。

---

## 3. 记忆模型：三个持久化存储

单用户部署，存储统一用 **SQLite**（单文件、零运维、支持 FTS5 全文检索），大负载落磁盘文件。

### 3.1 SessionFacts —— 会话事实卡

一个小的结构化 JSON 对象，**每轮都完整出现在上下文**，承载"这个会话是关于什么的"：

```json
{
  "scenario": "precision_machining",
  "active_solve_run": "SR-0012",
  "active_workflow_run": null,
  "confirmed_params": {
    "objective_order": ["total_tardiness", "makespan"],
    "epsilon": {"total_tardiness": 0.05},
    "horizon": "2026-07-01 ~ 2026-07-14"
  },
  "user_preferences": ["解释时先给结论再给依据", "甘特图对比默认按产线分组"],
  "open_questions": ["产线 L3 周日班次是否可用，待用户确认"],
  "resolved_notes": ["SR-0009 因物料未齐套不可行，已放宽 M-204 到 7/3"]
}
```

**更新机制（关键：确定性钩子，不让 LLM 自由编辑记忆）：**
业界 MemGPT/Letta 的做法是让 LLM 通过工具自己编辑核心记忆，这与本平台"LLM 不进主控制循环"原则冲突，且在排产场景下有把错误参数写进事实卡的风险。本方案改为**在固定语义节点由代码调用 `facts.update()`**：

| 钩子位置 | 更新内容 |
|---|---|
| Orchestrator 路由完成 | scenario / 当前意图域 |
| Planning Engine 参数确认完成 | confirmed_params（来自结构化确认结果，非 LLM 生成） |
| SolveRun 状态变更 | active_solve_run、resolved_notes |
| 写操作授权通过/拒绝 | resolved_notes |
| 分段摘要完成（§5.3） | Haiku 摘要输出中的 `open_questions` / `user_preferences` 字段合并进来（这是 LLM 唯一间接写入事实卡的通道，且经过 schema 校验） |

事实卡超过 2K 预算时：`resolved_notes` 最旧条目移入 Transcript 归档（可通过 recall 找回），`open_questions` 永不自动删除。

### 3.2 Transcript —— append-only 事件日志

会话中发生的一切按序追加，**永不删除、永不修改**。压缩只移动视图指针。

条目类型（`type` 字段）：

- `user` / `assistant`：对话文本；
- `tool_call` / `tool_result`：工具调用与结果。**tool_result 超过 1K tokens 的，内容体直接落 Artifact 存储，条目里只存确定性摘要 + artifact_ref**（写入时即卸载，不等压缩触发——见 §5.1）；
- `error`：错误栈、IIS 诊断、求解失败详情。**写入即标记 protected**；
- `pending_auth`：等待用户授权的写操作。**写入即标记 protected**；
- `system_note`：resume briefing、压缩发生标记等系统事件。

每个条目记录估算 token 数（估算方法见 §12 待确认项 1）。

### 3.3 Artifact 归档 + recall 检索

**Artifact 存储**：大负载（求解器原始输出、完整排程明细、RAG 原始片段、甘特图数据导出）以文件形式存 `{session_dir}/artifacts/`，DB 中存元数据行（id、kind、path、digest_text、size）。

**recall 工具（只读，注册给 Agent）**——这是"及时检索"替代"预先塞满"的业界共识做法（Anthropic context engineering、Claude Code 的按需读取都是此思路）：

```
recall_artifact(ref_id, window=null)
    → 返回归档内容（可指定行/字段窗口，避免整个取回又撑爆上下文）

search_history(query, limit=5)
    → 对 Transcript + 历史摘要做 FTS5 全文检索，返回条目摘录 + seq 定位
```

被压缩掉的细节不是丢了，而是从"常驻上下文"降级为"可检索"。Agent 在需要时（例如用户问"第 3 次求解时迟期最长的订单是哪个"）通过 recall 取回。

### 3.4 经验记忆层（本期不做，预留接口）

跨会话的操作经验（"该用户的车间周日一般不排 L3 产线"这类模式）属于 mem0 式抽取管线的领域，本期明确不做。预留：`ExperienceStore` 接口 + Transcript 中已有的全量数据，未来可离线跑抽取管线回填，不需要改动本模块。

---

## 4. 上下文装配函数（伪代码）

```python
def assemble_context(session: Session) -> list[Block]:
    ctx = []
    ctx.append(system_prompt())                          # 固定
    ctx.append(session.facts.render())                   # §3.1，≤2K
    ctx.append(render_active_run_digests(session))       # 从平台 DB 实时生成，≤4K，可再生
    if session.rolling_summary:
        ctx.append(wrap("[历史摘要，细节可通过 search_history/recall_artifact 取回]",
                        session.rolling_summary))        # ≤6K
    ctx.extend(render_protected(session))                # 未解决的 error / pending_auth 原文
    ctx.extend(load_tail(session))                       # seq > last_compacted_seq 的原文条目
    return ctx


def on_session_resume(session: Session):
    """跨天恢复：没有特殊逻辑，装配函数即恢复逻辑。
    仅当距上次活动超过 RESUME_GAP（默认 8 小时）时，
    追加一条确定性模板生成的 resume briefing（system_note），
    帮助用户（也帮助模型）接上进度。不调用 LLM。"""
    if now() - session.updated_at > RESUME_GAP:
        note = render_resume_briefing(session.facts, active_runs(session))
        # 例："上次进展：SR-0012 已得到可行解（迟期总和 3.2 天），
        #      你确认了目标顺序 [总迟期, makespan]，
        #      待确认事项：产线 L3 周日班次是否可用。"
        append_entry(session, type="system_note", content=note)


def render_active_run_digests(session) -> Block:
    """确定性模板，每轮从平台 DB 重新生成，永远新鲜。示例输出：
    [SolveRun SR-0012] 状态: feasible | 目标: 总迟期 3.2d, makespan 11.4d
      | 迟期订单 8/142 | 对比 SR-0011: 迟期 -0.8d | 详情: recall_artifact("art-0093")
    [SolveRun SR-0011] 已被 SR-0012 取代 | 摘要归档: art-0087
    被取代的 Run 只保留一行；再往前的 Run 从本区移除（DB 中仍在，可 recall）。"""
```

**每轮主循环中本模块的接入点只有三个**（对 Orchestrator 的侵入最小化）：

```python
# ① LLM 调用前
ctx = assemble_context(session)

# ② 每个工具结果返回时（同步、无 LLM）
entry = offload_if_large(tool_result)     # §5.1
append_entry(session, entry)

# ③ 每轮结束时（检查水位，必要时压缩）
maybe_compact(session)                     # §5.2
```

---

## 5. 压缩模块

三级手段，按成本从低到高依次使用：**确定性卸载（无损）→ 分段语义摘要（有损，Haiku）→ 摘要合并（有损，Haiku）**。

### 5.1 第一级：结构化卸载（写入即执行，无损，无 LLM）

```python
def offload_if_large(tool_result) -> Entry:
    if tokens(tool_result.content) <= INLINE_LIMIT:      # 默认 1K
        return Entry(type="tool_result", content=tool_result.content)
    art = save_artifact(tool_result)                      # 全量落盘
    digest = DIGEST_TEMPLATES[tool_result.tool_name](tool_result)  # 确定性模板
    return Entry(type="tool_result", content=digest, artifact_ref=art.id)
```

`DIGEST_TEMPLATES` 按工具类型编写代码模板，不用 LLM。首批需要覆盖的模板：

| 工具类型 | 摘要模板要点 |
|---|---|
| CP-SAT 求解结果 | 状态/各目标值/迟期订单数/求解耗时/与上次对比增量 |
| IIS 诊断结果 | 冲突约束条数/涉及订单与资源清单（这个条目同时标 protected） |
| 排程明细导出 | 行数/时间范围/涉及产线，明细全量归档 |
| RAG 检索结果 | 命中文档标题+分数列表；**原文片段本轮用完即弃（可再生），不进 Transcript 正文** |
| 调度引擎写操作回执 | 操作类型/对象/结果/授权人 |

**这一级预计消解绝大部分 token 压力**，且因为是无损的（全量在 Artifact），激进使用没有风险。

### 5.2 触发与主流程

```python
def maybe_compact(session):
    t = estimate_tokens(assemble_context(session))
    if t <= SOFT_WM:                                   # 140K
        return
    aggressive = (t > HARD_WM)                         # 170K
    compact(session, target=TARGET_WM, aggressive=aggressive)   # 100K

def compact(session, target, aggressive):
    segments = split_into_segments(tail(session))      # §5.3 业务边界切分
    keep_recent = 2 if not aggressive else 6           # 常规保留最近2段；激进模式只按轮数保尾部
    for seg in oldest_first(segments, excluding_recent=keep_recent):
        result = summarize_segment(seg)                # §5.3，Haiku
        merge_into_rolling_summary(session, result.summary)
        carry_forward_protected(session, seg)          # 受保护条目重新钉住，不摘要
        advance_pointer(session, seg.end_seq)          # last_compacted_seq 前移
        record_compaction_event(session, seg, result)  # §6
        if estimate_tokens(assemble_context(session)) <= target:
            break
    assert_protected_intact(session)                   # §5.5 零丢失硬断言
```

压缩在轮次边界同步执行（单用户场景可接受；Haiku 摘要一段的延迟在秒级）。若未来需要，压缩点已是独立函数，可平移为异步任务。

### 5.3 分段边界 = 业务里程碑（本方案与通用方案的关键差异）

通用方案按 token 数或消息数切段。排产会话有天然的语义单元，跨单元摘要会切断因果：

- Planning 域：**一次 SolveRun 迭代**（参数配置 → 求解 → 解释/对比 → 用户反馈）为一段；
- Scheduling 域:**一次调度事务**（异常上报 → 分析 → 授权 → 执行 → 回执）为一段；
- Query 域：连续的问答轮次合并为一段；
- WorkflowRun：每个 step 为一段。

切分实现：Transcript 条目在写入时由各引擎打上 `milestone_id`（引擎本来就知道当前处于哪个 Run/哪个事务），切分函数按 `milestone_id` 分组即可，无需推断。

**分段摘要的 Haiku prompt（完整版，Claude Code 直接使用）：**

```
你是排产调度系统的会话摘要器。请把下面这一段对话+工具记录压缩成结构化摘要。

必须无损保留（宁可多写不能漏）：
1. 用户确认过的参数及其值（目标顺序、ε 容差、时间范围、约束开关）
2. 做出的决策及理由（一句话理由即可）
3. 涉及的 Run ID 及其一句话结果（如 "SR-0011: 不可行，IIS 指向工装 T-9 独占冲突"）
4. 尚未解决的问题、用户提出但还没回答的疑问
5. 观察到的用户偏好（表达方式、关注点）

可以丢弃：寒暄、被后续轮次取代的中间讨论、工具结果的细节（已归档，只留 ref）。

严格按以下 JSON 输出，不要输出其他内容：
{
  "summary": "<200-400字的段落摘要，中文>",
  "confirmed_params": {...},
  "run_outcomes": [{"run_id": "...", "outcome": "..."}],
  "open_questions": ["..."],
  "user_preferences": ["..."],
  "decisions": [{"what": "...", "why": "..."}]
}
```

输出经 schema 校验后：`summary` 并入 RollingSummary；`open_questions` / `user_preferences` / `confirmed_params` 合并进 SessionFacts（§3.1 中提到的唯一 LLM 间接写入通道）。

### 5.4 第三级：RollingSummary 合并

RollingSummary 超过 6K 预算时，把最旧的若干段摘要再交给 Haiku 做一次"摘要的摘要"（meta-summarize），同样记 CompactionEvent。被合并的原始段摘要仍在 `summaries` 表中，可检索。

### 5.5 受保护条目与生命周期

写入即受保护的条目：`error`（错误栈、IIS、求解失败详情）、`pending_auth`（待授权写操作）。

生命周期：**active → resolved → compressible**

- active：原文常驻上下文（受保护条目区），压缩时被 carry forward，永不摘要；
- resolved：由确定性钩子标记（错误被后续成功求解覆盖、授权已完成），标记时附一行 resolution note；
- resolved 的条目在下一次压缩时按普通条目处理（可摘要），但摘要 prompt 会看到 resolution note，保证"发生过什么错、如何解决的"进入 RollingSummary。

**零丢失硬断言**：每次压缩结束后校验——所有 active 状态的 protected 条目仍完整出现在装配结果中，否则抛异常回滚本次压缩（append-only 设计使回滚 = 恢复指针位置）。这是单元测试和运行时的双重断言。

受保护条目区超过 8K 软预算：不压缩，改为向用户提示"当前有 N 个未解决错误/待授权项占用上下文，建议先处理"，把问题交还给人。

### 5.6 失败降级

Haiku 调用失败/超时（默认 15s）/输出 schema 校验不过（重试 1 次后）：

- 降级为**确定性模板摘要**：按条目类型罗列（"本段含 SolveRun SR-0011 一次不可行求解，参数确认 2 次，详情 recall art-00xx"），保证压缩总能完成、主循环永不被阻塞；
- CompactionEvent 标记 `degraded=true`，纳入监控（§9）。

---

## 6. CompactionEvent —— 压缩审计记录

**它是什么**：每当压缩改变了"模型下一轮将看到的上下文视图"，就写入一条不可变的审计记录，描述这次改变。它不参与任何运行逻辑，是纯粹的黑匣子。

**为什么需要它**（对应事实 E）：

1. **决策回溯**：排产建议出错时，回答"做这个决策的那一轮，模型看到的是原文还是摘要？摘要丢了什么？"——沿 CompactionEvent 链 + append-only 原文可以精确重放任意一轮的上下文视图；
2. **压缩质量诊断**：如果发现"压缩之后 Agent 开始忘记用户确认过的 ε 参数"，通过 event 找到对应摘要，定位是 prompt 问题还是分段问题；
3. **指标数据源**：§9 的所有压缩指标直接从这张表聚合，不需要额外埋点。

**字段定义：**

| 字段 | 说明 |
|---|---|
| id, session_id, created_at | 标识 |
| trigger | `soft` / `hard` / `summary_merge`（§5.4）/ `manual` |
| seq_from, seq_to | 本次被压缩的 Transcript 条目区间 |
| tokens_before, tokens_after | 装配上下文在本次压缩前后的估算 token 数 |
| summary_id | 产出的段摘要在 summaries 表中的 ID |
| protected_carried | 被 carry forward 的 protected 条目 ID 列表 |
| model | 实际使用的摘要模型标识 |
| degraded | 是否走了 §5.6 降级路径 |
| duration_ms | 摘要耗时 |

---

## 7. 持久化 Schema（SQLite DDL）

```sql
CREATE TABLE sessions (
  id TEXT PRIMARY KEY,
  scenario TEXT,
  status TEXT DEFAULT 'active',          -- active | suspended | closed
  last_compacted_seq INTEGER DEFAULT 0,
  created_at TEXT, updated_at TEXT
);

CREATE TABLE entries (                    -- Transcript, append-only
  id TEXT PRIMARY KEY,
  session_id TEXT REFERENCES sessions(id),
  seq INTEGER,                            -- 会话内单调递增
  type TEXT,                              -- user|assistant|tool_call|tool_result|error|pending_auth|system_note
  content TEXT,                           -- 正文或确定性摘要
  artifact_ref TEXT,                      -- 大负载卸载后的引用，可空
  milestone_id TEXT,                      -- 业务里程碑分组键（§5.3）
  tokens INTEGER,
  protected_state TEXT,                   -- NULL | active | resolved
  resolution_note TEXT,
  created_at TEXT,
  UNIQUE(session_id, seq)
);

CREATE TABLE artifacts (
  id TEXT PRIMARY KEY,
  session_id TEXT,
  kind TEXT,                              -- solver_output|iis|schedule_export|rag_chunks|dispatch_receipt|...
  path TEXT,                              -- {session_dir}/artifacts/ 下的文件
  digest_text TEXT,
  size_bytes INTEGER,
  created_at TEXT
);

CREATE TABLE session_facts (
  session_id TEXT PRIMARY KEY,
  facts_json TEXT,
  version INTEGER,                        -- 每次 update 递增，便于排查
  updated_at TEXT
);

CREATE TABLE summaries (
  id TEXT PRIMARY KEY,
  session_id TEXT,
  covers_seq_from INTEGER, covers_seq_to INTEGER,
  text TEXT, structured_json TEXT,        -- §5.3 的 JSON 原样保存
  merged_into TEXT,                       -- 被 §5.4 合并后指向新摘要，可空
  tokens INTEGER, created_at TEXT
);

CREATE TABLE compaction_events (
  id TEXT PRIMARY KEY,
  session_id TEXT,
  trigger TEXT, seq_from INTEGER, seq_to INTEGER,
  tokens_before INTEGER, tokens_after INTEGER,
  summary_id TEXT, protected_carried TEXT,   -- JSON array
  model TEXT, degraded INTEGER DEFAULT 0, duration_ms INTEGER,
  created_at TEXT
);

CREATE VIRTUAL TABLE entries_fts USING fts5(content, content=entries);  -- search_history 用
```

---

## 8. 与三引擎 / Orchestrator 的集成点清单

| 位置 | 调用 | 说明 |
|---|---|---|
| Orchestrator 每轮 LLM 调用前 | `assemble_context()` | 唯一的上下文来源 |
| Orchestrator 每轮结束 | `maybe_compact()` | 水位检查 |
| Orchestrator 会话恢复 | `on_session_resume()` | resume briefing |
| Orchestrator 路由完成 | `facts.update(scenario=...)` | |
| 所有引擎的工具结果返回处 | `offload_if_large()` + `append_entry()` | 统一入口 |
| Planning：参数确认完成 | `facts.update(confirmed_params=...)` | 来源是结构化确认结果 |
| Planning：SolveRun 状态变更 | `facts.update(...)`；旧 Run 摘要降级 | §4 digest 区 |
| Planning：求解失败/IIS | `append_entry(type="error", protected)` | |
| Planning：新可行解覆盖旧错误 | `mark_resolved(error_entry, note)` | |
| Scheduling：写操作待授权 | `append_entry(type="pending_auth", protected)` | |
| Scheduling：授权完成/拒绝 | `mark_resolved(...)` | |
| Query：RAG 检索结果 | 本轮内联使用，只把命中清单写入 entry（可再生原则） | |
| Agent 工具注册表 | `recall_artifact` / `search_history` | 只读工具 |

---

## 9. 可观测性指标

全部可从 §7 的表直接聚合，实现为一个 `metrics` 查询模块：

- `compaction_trigger_rate`：每会话压缩次数 / 轮数（持续偏高 → 卸载模板覆盖不足或预算表失衡）；
- `hard_trigger_rate`：硬水位触发占比（健康值应接近 0，>5% 说明软水位压不下去）;
- `avg_compression_ratio`：tokens_after / tokens_before，健康区间 0.30–0.50；
- `protected_loss`：硬断言违例计数，**必须恒为 0**；
- `degraded_rate`：降级摘要占比;
- `recall_hit_rate`：recall/search 调用中成功取回被压缩内容的比例（衡量"压掉的东西是不是真的还找得回来"）；
- `resume_briefing_count` 与恢复后首轮是否触发澄清（间接衡量恢复体验）。

---

## 10. 业界方案对照与取舍

| 业界方案 | 借鉴 | 不采用的部分及原因 |
|---|---|---|
| **Claude Code auto-compact** | 水位触发思路；摘要 prompt 的"必须保留清单"写法；CLAUDE.md 常驻文件 ≈ SessionFacts 的角色 | 其"日志原地削减"范式——本平台有权威 DB 状态，装配式更优；其面向代码场景的摘要内容清单不适用 |
| **MemGPT / Letta** | 主上下文/外部存储分层；核心记忆块（core memory）≈ SessionFacts | LLM 通过工具自编辑记忆——违反"LLM 不进主控制循环"，改为确定性钩子 + schema 校验的单一间接通道 |
| **Anthropic context engineering 实践** | 及时检索（just-in-time retrieval）优于预加载 → recall 工具；结构化笔记 → SessionFacts | — |
| **LangGraph checkpointer / store** | 线程状态持久化的接口形态可作为 SessionStore 的接口参照 | 不引入 LangGraph 依赖，SQLite 直连即可（单用户，无分布式需求） |
| **LangChain ConversationSummaryBufferMemory** | "摘要 + 近期缓冲"的二段结构与 RollingSummary+Tail 同构 | 其按消息数/token 数切段——本方案按业务里程碑切段（§5.3） |
| **mem0** | 经验抽取管线，仅对 §3.4 预留层有参考价值 | 本期不做 |

---

## 11. 分期实施计划（交给 Claude Code 的四个批次）

每批次独立可验收，顺序有依赖。

**Batch 1 —— 持久化层与装配函数（地基）**
实现：§7 全部 DDL、SessionStore（entries/facts/summaries/events 的读写）、`assemble_context()`、`on_session_resume()`、token 估算器。
验收：① 写入 50 条模拟条目后关闭进程，重开进程恢复会话，装配结果与关闭前一致；② resume briefing 在超过 8 小时间隔时正确生成；③ 所有表的 CRUD 有单元测试。

**Batch 2 —— 结构化卸载与 recall**
实现：`offload_if_large()`、§5.1 五个 DIGEST_TEMPLATES、Artifact 文件存储、`recall_artifact` / `search_history` 工具（含 FTS5）。
验收：① 注入一个 30K token 的模拟求解输出，上下文中只出现 ≤200 token 的 digest；② recall 能按窗口取回归档内容；③ search_history 能命中已卸载条目。

**Batch 3 —— 压缩器与 CompactionEvent**
实现：`maybe_compact()` / `compact()`、milestone 分段、Haiku 摘要调用（§5.3 prompt + schema 校验）、protected 生命周期与 carry forward、零丢失硬断言、§5.6 降级、RollingSummary 合并、CompactionEvent 写入。
验收：① 构造 160K 模拟会话，触发软压缩后装配结果 ≤100K 且所有 active protected 条目原文在场；② 摘要 JSON 中的 open_questions 正确合并进 SessionFacts；③ 模拟 Haiku 超时，降级路径生效且 event.degraded=1；④ 断言违例时压缩回滚。

**Batch 4 —— 指标与端到端测试**
实现：§9 metrics 查询模块；端到端场景测试（一个跨"两天"的模拟排产会话：3 次 SolveRun 迭代 + 1 次 IIS + 1 次挂起恢复 + 2 次压缩），输出指标报告。
验收：指标数值落在 §9 健康区间；重放任意一轮的历史上下文视图（利用 CompactionEvent + append-only entries）结果正确。

---

## 12. 待确认事项

1. **Token 估算方法**：默认方案——中日韩字符按 1 token、其他字符按 3.5 字符/token 的启发式估算，定期用 Anthropic `count_tokens` API 校准系数。【待确认：是否可接受 ±10% 估算误差；水位线已留了余量】
2. **Artifact 存储形式**：默认落磁盘文件 + DB 元数据。【待确认：是否有备份/单文件分发诉求，若有可改为 SQLite BLOB】
3. **resume briefing 是否展示给用户**：默认既进上下文也在 UI 显示（作为一条系统消息）。【待确认】
4. **Haiku 摘要的具体模型串**：默认 `claude-haiku-4-5-20251001`。【待确认：以接入时最新 Haiku 为准】
