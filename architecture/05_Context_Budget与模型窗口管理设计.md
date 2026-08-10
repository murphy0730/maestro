# Context Budget 与模型窗口管理设计

> 文档编号：05  
> 目标：定义不同模型窗口下 Agent 的可运行上下文预算、压缩触发规则和安全余量。

---

## 1. 为什么不能把模型最大窗口直接当运行上限

假设模型物理支持：

```text
200K tokens
```

不代表 Agent 应在 199K 时才处理。

需要预留：

- 模型输出
- Tool Schema 动态加载
- RAG 突发召回
- Skill Body
- 用户突然输入大段内容
- Provider 包装开销
- 估算误差
- 长 Context 质量下降余量

因此区分：

```text
MODEL_CONTEXT_LIMIT
OPERATIONAL_CONTEXT_LIMIT
HARD_CONTEXT_LIMIT
COMPACT_TRIGGER
FORCE_COMPACT_TRIGGER
```

---

## 2. ModelRegistry

模型能力来自 Runtime 配置，而不是询问 LLM。

```python
@dataclass(frozen=True)
class ModelCapabilities:
    model_id: str
    context_window: int
    max_output_tokens: int
    tokenizer_id: str
```

```python
@dataclass(frozen=True)
class ContextPolicy:
    operational_limit: int
    compact_trigger: int
    force_compact_trigger: int

    reserved_output: int
    reserved_tool_burst: int
    reserved_retrieval_burst: int
    safety_margin: int
```

---

## 3. 预算公式

推荐：

```text
projected_context_tokens
=
prefix_tokens
+
checkpoint_tokens
+
hot_event_tokens
+
incoming_user_tokens
+
active_skill_tokens
+
planned_tool_schema_budget
+
planned_retrieval_budget
+
status_bar_tokens
```

再加：

```text
reserved_output
+
safety_margin
```

评估下一轮是否安全。

---

## 4. 示例策略

假设：

```text
MODEL_CONTEXT_LIMIT = 200_000
```

示例而非固定标准：

```text
reserved_output         = 16_000
reserved_tool_burst     = 8_000
reserved_retrieval_burst= 8_000
safety_margin           = 8_000

hard_context_limit      = 160_000
operational_limit       = 130_000
compact_trigger         = 105_000
force_compact_trigger   = 140_000
```

真实参数需根据模型和 Agent Eval 调优。

---

## 5. Compact 决策

```python
if projected >= force_compact_trigger:
    force_compact()

elif projected >= compact_trigger:
    incremental_compact()
```

不要使用：

```text
每20轮压缩一次
```

因为 1 个 Tool Result 可能比 20 轮普通对话还大。

---

## 6. Lazy Tool 对 Context Budget 的影响

Tool Schema 不常驻后，需引入：

```text
planned_tool_schema_budget
```

例如模型已通过 Tool Search 找到 3 个候选，但只需要加载 1～3 个 Schema。

Runtime 应估算：

```text
当前上下文
+
待加载 Tool Schema
+
预计 Tool Result Digest
```

后再调用模型。

如果超预算：

- 缩小 Tool Search 候选
- 只加载最相关 Tool
- Compact
- 限制 Skill/RAG 同时物化

---

## 7. Skill Budget

Skill Body 也可能很长。

Skill Registry 应记录：

```yaml
estimated_tokens: 2400
```

SkillResolver 在加载前检查 Context Budget。

超限可：

- 使用 Skill 摘要版
- Compact
- 将 Skill 拆成阶段性模块
- 使用 SubAgent 隔离长 Skill 处理

---

## 8. RAG Budget

RAG 不应单纯按 `top_k` 控制。

建议同时控制：

```text
max_retrieval_tokens
max_chunk_count
per_chunk_max_tokens
```

例如：

```python
retrieval_budget = min(
    policy.max_retrieval_tokens,
    remaining_working_budget
)
```

---

## 9. Tool Result Budget

原则：

> Raw Tool Result 不进入主上下文。

Tool 层先输出：

```text
Raw Result
  ↓
Result Processor
  ↓
Digest
```

Agent Context 只吃 Digest。

若后续需要细节，通过：

```text
result_ref
```

局部读取。

---

## 10. Status Bar Budget

建议：

```text
TARGET: 100~500 tokens
MAX: 800 tokens
```

超预算时按优先级删除：

1. Goal
2. Current Step
3. Next Action
4. Blocker
5. Execution Gate
6. Critical Constraint
7. Critical Alert
8. 其他辅助信息

不要把 Status Bar 压成长自然语言摘要。

---

## 11. Context Health

内部可维护：

```python
class ContextHealth(Enum):
    NORMAL = "normal"
    PRESSURE = "pressure"
    CRITICAL = "critical"
```

一般不必把精确 token 告诉模型。

仅在需要模型改变行为时，向 Status Bar 投影：

```text
上下文空间紧张，避免无必要的大规模数据读取。
```

真正 Compact 决策仍由 Runtime 做。

---

## 12. Context 质量而非仅容量

模型在长上下文下可能出现：

- 远端信息关注下降
- 干扰增多
- 约束遗漏
- Tool 选择混乱

因此 operational_limit 不只由物理窗口确定，也由 Eval 中的：

```text
Task Success vs Context Length
Constraint Recall vs Context Length
Tool Accuracy vs Context Length
```

共同决定。

---

## 13. Model 切换

若一个 Session 必须切模型：

- 检查目标模型窗口
- 重新计算 Context Policy
- 必要时先 Compact
- 保存 model_switch Event 或审计记录
- 不假设不同模型 tokenizer 相同

---

## 14. Prompt Cache 与 Context Window

Prompt Cache 能降低重复前缀计算成本，但缓存内容依然占逻辑 Context。

所以：

```text
Cache Hit ≠ 不占上下文窗口
```

Prefix Stability 解决成本/延迟问题；Checkpoint/Compaction 解决容量与质量问题。

二者不能混为一谈。

---

## 15. 第一版指标

建议记录：

```text
prefix_tokens
checkpoint_tokens
hot_event_tokens
status_tokens
active_skill_tokens
tool_schema_tokens
retrieval_tokens

projected_context_tokens
actual_input_tokens

compact_trigger_count
force_compact_count
```

以便后续基于真实运行数据调参。
