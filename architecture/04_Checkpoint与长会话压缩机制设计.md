# Checkpoint 与长会话压缩机制设计

> 文档编号：04  
> 目标：定义长会话中历史信息如何被安全压缩为累计 Session State，并避免摘要漂移和上下文无限增长。

---

## 1. Checkpoint 的定位

Checkpoint 不是：

- 普通聊天摘要
- 历史消息列表
- Tool Schema 缓存
- Skill 正文缓存
- RAG 原文缓存
- Status Bar

Checkpoint 是：

> 截止某个 Event Sequence，当前 Session 已经形成的累计有效状态快照。

---

## 2. 推荐 Checkpoint Schema

```yaml
checkpoint_id: CP12
parent_checkpoint_id: CP11
covered_until_event_seq: 130

goal:
  primary: 完成A1001排产

constraints:
  - id: C1
    value: 产品X禁止使用M01
    source_ref: event://E23

decisions:
  - value: 候选设备优先M05
    source_ref: event://E81

current_state:
  order_id: A1001
  schedule_version: V3

facts:
  - value: A1001缺少物料P003
    source_type: tool
    source_ref: result://R123
    validity: volatile
    observed_at: 2026-08-08T19:50:00+08:00

completed_actions:
  - order_loaded
  - bom_checked

pending_actions:
  - material_resolution
  - schedule_optimization
  - user_confirmation
  - schedule_publish

active_skill:
  id: production_scheduling
  version: "2.3"
  phase: material_resolution
```

---

## 3. Incremental Compact

常规压缩：

```text
Previous Checkpoint
+
Cold Events
        ↓
State Reduction
        ↓
New Checkpoint
```

公式：

```text
CP2 = Reduce(CP1 + E087...E130)
```

最终 Context：

```text
Prefix
CP2
Hot Events E131...
Status Bar
```

### 3.1 为什么必须包含 Previous Checkpoint

因为 CP1 已经代表更早历史：

```text
E001...E086
```

不需要每次重读原始历史。

---

## 4. Hot / Cold Event

不要把最新活跃轨迹都压掉。

原因：

- 最新语义细节重要
- Tool Call/Result 因果关系仍在使用
- 用户可能正在修正刚刚的决定
- 当前步骤可能尚未稳定

推荐由 Token Budget 决定 Cold Boundary，而不是固定“每 10 轮”。

---

## 5. Force Compact

用途：

> Context 接近运行危险水位时快速释放空间。

例如：

```text
CP4 + E401~E500
```

Force：

```text
CP5 = Reduce(CP4 + E401~E495)
```

仅保留：

```text
E496~E500
```

特点：

- 在线
- 快
- 依赖现有 CP4
- 不解决 CP4 已存在的摘要漂移

---

## 6. Full Rebase

用途：

> 不再信任长期滚动 Checkpoint，从原始 Event Log 重建新的 Canonical Checkpoint。

```text
Raw Event Log
    ↓
Chunking
    ↓
State Extraction
    ↓
Deterministic Merge
    ↓
Canonical CP-F1
```

适用：

- Checkpoint generation 太深
- 检测到状态冲突
- Summary Drift 风险高
- 定期质量维护
- 关键业务阶段切换
- Replay 发现 CP 与原始 Event 不一致

---

## 7. 避免 Summary of Summary 漂移

错误模式：

```text
CP1 → LLM摘要 → CP2 → LLM摘要 → CP3 → ...
```

可能出现：

- 约束逐步消失
- “可选”变成“必须”
- 状态时间丢失
- 旧结论被当成当前事实

推荐：

```text
LLM负责：
语义提取 / 结构化 Delta

程序负责：
确定性 State Reduce
```

例如每个 Chunk 输出：

```json
{
  "facts_added": [],
  "facts_invalidated": [],
  "constraints_added": [],
  "constraints_removed": [],
  "decisions_added": [],
  "decisions_superseded": [],
  "state_changes": [],
  "milestones_completed": []
}
```

再由 Reducer 合并。

---

## 8. Lazy Tool / Skill / RAG 对压缩的影响

### 8.1 Tool Schema

**不参与压缩。**

因为 Tool Schema：

- Source of Truth 在 Tool Registry
- 只是 Runtime 临时可调用定义
- 不属于 Session 历史状态

### 8.2 Skill Body

**不参与压缩。**

Checkpoint 只保存：

```yaml
active_skill:
  id:
  version:
  phase:
```

### 8.3 RAG Chunk

未使用：

```text
DROP
```

已使用但未来无关：

```text
DROP
```

已使用且未来相关：

```text
derived_fact + source_ref
```

进入 Checkpoint。

### 8.4 Memory

只保存本 Session 实际采用的效果：

```yaml
active_constraint:
  紧急订单优先
```

不复制 Memory 原文。

### 8.5 Raw Tool Result

只保留：

```text
important finding + result_ref
```

---

## 9. Tool Search 新结构如何压缩

完整轨迹：

```text
TOOL_SEARCH
TOOL_CALL
TOOL_RESULT
```

Checkpoint 处理：

```text
TOOL_SEARCH
    → 通常 DROP

TOOL_CALL
    → 通常不单独保存

TOOL_RESULT
    → 提炼为业务 Fact/State
```

例如：

```text
query_material_shortage(A1001)
→ P003缺料
```

Checkpoint：

```yaml
facts:
  - value: A1001缺少P003
    source:
      tool_id: query_material_shortage
      result_ref: result://R123
```

为什么当时搜索了哪些候选 Tool，保留在 Event Store，供调试，不进入 CP。

---

## 10. Status Bar 如何处理

旧 Status Bar：

```text
直接丢弃
```

因为它是派生状态。

下一轮：

```text
Latest Checkpoint
+
Hot Events
+
PlanManager
+
Runtime State
        ↓
StatusBarBuilder
        ↓
New Status Bar
```

Status Bar 本身几乎没有“压缩”问题。

---

## 11. Plan 如何压缩

完整 TODO 存 PlanManager：

```text
T1...T30
```

Checkpoint 不保存所有任务明细，只保存关键阶段：

```yaml
plan_state:
  plan_id: P1
  current_phase: optimization
  completed_milestones:
    - data_ready
    - constraints_validated
  pending_milestones:
    - schedule_confirmation
    - schedule_publish
```

---

## 12. Compaction Pipeline

推荐：

```text
Cold Events
   ↓
Trajectory Normalizer
   ↓
Filter Non-State Events
   ↓
Extract State Delta
   ↓
Resolve Conflicts / Superseded State
   ↓
Reduce with Previous Checkpoint
   ↓
Validate Invariants
   ↓
Save New Checkpoint
```

不需要把所有原始事件一次性直接喂给一个“总结 Prompt”。

---

## 13. Checkpoint Invariants

生成后校验：

- `covered_until_event_seq` 单调递增
- 当前 active constraint 不包含已 removed constraint
- 同一状态字段不能同时存在互斥 active value
- 关键副作用操作必须能追溯确认
- volatile fact 必须带 observed_at
- source_ref 可解析
- active_skill version 存在
- plan_id 可解析

---

## 14. Checkpoint 生命周期

```text
CP1
  ↓ parent
CP2
  ↓
CP3
  ↓
CP4

Full Rebase:
CP-F1
```

数据库保留旧 Checkpoint 用于：

- Audit
- Replay
- Diff
- Drift 分析

模型只使用最新有效 Checkpoint。

---

## 15. 触发建议

### Incremental Compact

以 token 为主。

### Force Compact

Projected Context 接近 hard budget。

### Full Rebase

以“质量健康度”为主，例如：

- generation >= 8
- state conflict
- source_ref inconsistency
- checkpoint token 过大
- 周期性维护
- 关键任务结束后重新基线化

阈值需要 Eval 调优，不应写死为行业标准。

---

## 16. 第一版实现

建议先实现：

```python
ConversationCompactor.incremental()
ConversationCompactor.force()
CheckpointManager.get_latest()
CheckpointManager.save()
```

Full Rebase 第二阶段实现。

第一版 Compactor 重点保证：

- Goal 不丢
- Active Constraints 不丢
- Current State 不丢
- Pending Actions 不丢
- Tool 重要结果可追溯
- RAG Evidence 只保留已使用且未来相关结论
