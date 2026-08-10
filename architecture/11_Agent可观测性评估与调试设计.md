# Agent 可观测性、评估与调试设计

> 文档编号：11  
> 目标：让排产 Agent 的上下文、工具选择、RAG、规划、压缩和副作用行为可度量、可解释、可回放。

---

## 1. 为什么必须独立设计 Eval

Agent 的错误可能来自完全不同的层：

```text
Tool Search 没搜到正确工具
Tool 选对但参数错
RAG 召回错误
RAG 召回正确但没使用
Checkpoint 丢约束
Status Bar 没提醒风险
Plan 进入循环
Tool Result 过期
LLM 决策错误
```

如果只看“最终回答对不对”，无法定位问题。

---

## 2. Observability 分层

建议：

```text
Business Outcome
Agent Trajectory
Context Health
Capability Usage
Evidence Usage
Compaction Health
Runtime Safety
Latency / Cost
```

---

## 3. 业务结果指标

排产场景最终核心：

```text
Task Success Rate
Feasible Schedule Rate
Constraint Violation Rate
On-time Completion
Schedule Publish Success
User Acceptance / Override Rate
```

算法层还可加入：

- makespan
- tardiness
- setup cost
- resource utilization

但这些属于排程优化评价，不等同于 Agent Runtime Eval。

---

## 4. Tool 指标

至少：

```text
Tool Search Recall@K
Tool Selection Accuracy
Tool Argument Accuracy
Unnecessary Tool Call Rate
Tool Failure Rate
Repeated Tool Call Rate
```

### 定位逻辑

```text
正确 Tool 不在 Top-K
→ Search / Index

正确 Tool 在 Top-K 但 Agent 选错
→ Selection

Tool正确但参数错
→ Argument Generation / Schema

同参数反复调用
→ Trajectory Control
```

---

## 5. RAG / Memory 指标

```text
Retrieval Recall@K
Retrieval Precision
Evidence Used Rate
Evidence Attribution Accuracy
Unsupported Claim Rate
Stale Evidence Usage Rate
```

特别关注：

```text
Recall 5条
Used 1条
```

如果长期 Used Rate 很低，说明 RAG 可能召回过多噪声。

---

## 6. Context 指标

每轮记录：

```text
prefix_tokens
checkpoint_tokens
hot_event_tokens
status_tokens
tool_schema_tokens
skill_tokens
retrieval_tokens
input_tokens
output_tokens
```

分析：

```text
Task Success vs Context Length
Constraint Recall vs Context Length
Tool Accuracy vs Context Length
```

用于确定 operational context limit。

---

## 7. Compaction 指标

```text
Incremental Compact Count
Force Compact Count
Full Rebase Count

Checkpoint Tokens
Checkpoint Generation
Checkpoint Drift Score
State Recovery Accuracy
```

可以构造测试：

给定原始 Event Log，比较：

```text
Checkpoint state
vs
Ground Truth state
```

重点检查：

- Goal
- Active Constraints
- Current State
- Pending Actions
- Confirmation
- Volatile Fact Timestamp

---

## 8. Status Bar 指标

A/B 对比：

```text
Without Status Bar
With Status Bar
```

指标：

```text
Goal Drift Rate
Constraint Forgetting Rate
No-progress Loop Rate
Repeated Tool Call Rate
Premature Action Rate
Extra Context Tokens
```

如果 Status Bar 增加 300 token，但没有明显降低错误率，就继续砍字段。

---

## 9. Plan / Trajectory 指标

```text
Plan Completion Rate
Average Replan Count
No-progress Step Count
Loop Detection Precision
Loop Detection Recall
Average Tool Calls per Task
```

定义“进展事件”：

- Plan milestone complete
- 新有效 Fact
- Blocker resolved
- Decision made
- User confirmation
- Necessary Tool Result obtained

---

## 10. Runtime Safety

排程下发等副作用 Tool：

```text
Unauthorized Action Attempt
Missing Confirmation Attempt
Duplicate Side-effect Call
Idempotency Collision
Execution Gate Violation
```

目标：

```text
真正执行的副作用动作 Gate Violation = 0
```

---

## 11. Trace

一次 Agent Task 需要 trace_id。

例如：

```text
trace_id
 ├─ USER_MESSAGE
 ├─ TOOL_SEARCH
 ├─ TOOL_CALL
 ├─ TOOL_RESULT
 ├─ DECISION
 └─ ASSISTANT_MESSAGE
```

Tool 内部可使用 span_id。

---

## 12. Replay

Replay 输入：

```text
agent_definition_version
model_id
checkpoint
events
tool versions
skill versions
source refs
```

重建：

```text
当时模型看到什么
当时可用哪些 Tool
为什么选了这个 Tool
结果如何影响后续状态
```

Replay 是解决企业 Agent 问题的核心能力。

---

## 13. Debug View

推荐内部调试页面至少展示：

```text
Session Timeline
Latest Checkpoint
Current Plan
Current Status Bar
Tool Search Candidates
Tool Call/Result
Evidence Usage
Context Token Breakdown
Compaction History
```

不要只展示聊天窗口。

---

## 14. Offline Eval Dataset

从真实历史中构造：

### Tool Search Case

```text
用户问题
正确 namespace
正确 Tool
Top-K candidates
```

### Constraint Retention Case

```text
长对话 + 多次 Compact
→ 最终是否仍保留 C1/C2
```

### Evidence Attribution Case

```text
Answer
Evidence Set
Expected Used Evidence
```

### Side-effect Safety Case

```text
没有用户确认
→ Agent 不得 publish
```

---

## 15. Golden Trajectory

对关键排产任务建立标准轨迹：

```text
订单读取
→ BOM
→ 库存
→ 设备
→ 约束确认
→ 求解
→ 校验
→ 用户确认
→ 下发
```

不是要求 Agent 每次完全一致，而是用于识别：

- 缺关键步骤
- 多余循环
- 过早下发

---

## 16. 线上告警

建议：

```text
same_tool_same_args >= threshold
no_progress_steps >= threshold
tool_error_consecutive >= threshold
context_pressure = critical
checkpoint_generation too high
side_effect_gate_violation_attempt
stale_data_used_for_commit
```

告警既进入 Monitoring，也可选择性投影到 Status Bar。

---

## 17. 成本与延迟

记录：

```text
LLM Input Tokens
LLM Output Tokens
Tool Search Latency
Tool Latency
RAG Latency
Compact Latency
End-to-End Task Latency
```

Lazy Tool 应验证：

```text
Schema token 节省
vs
额外 Tool Search 调用成本
```

不能只看 token。

---

## 18. 评估层次

### L1 单组件

- Tool Search
- RAG
- Compactor

### L2 单轮 Agent

- Tool Selection
- Argument Generation

### L3 多步任务

- Plan
- Tool Loop
- Status Bar

### L4 长会话

- Compact
- State Retention
- Full Rebase

### L5 业务

- 排程是否可用
- 用户是否接受
- 是否安全下发

---

## 19. 第一版 Dashboard

建议至少：

```text
Task Success
Tool Search Recall@5
Tool Selection Accuracy
Argument Accuracy
Constraint Violation
Repeated Tool Call
Evidence Used Rate
Average Context Tokens
Compact Count
P95 Latency
Token Cost per Task
```

---

## 20. 核心目标

这套 Observability 最终应能回答：

1. Agent 为什么这么做？
2. 它用了哪些信息？
3. 为什么选择这个 Tool？
4. 哪一步开始偏离目标？
5. Compact 是否丢了状态？
6. 这个错误是 LLM、RAG、Tool Search、Tool 本身还是 Runtime 导致？
7. 修改某个模块后，整体任务成功率是否真的提升？
