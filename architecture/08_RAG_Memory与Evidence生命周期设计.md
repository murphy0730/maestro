# RAG、Memory 与 Evidence 生命周期设计

> 文档编号：08  
> 目标：解决“召回了什么、真正用了什么、哪些内容应该进入 Checkpoint、以后如何再取回详细内容”。

---

## 1. 核心原则

```text
Recall
= 候选信息

Evidence Used
= 实际影响本轮推理的信息

Checkpoint
= 已经对当前 Session 产生实际且持续影响的信息
```

不是所有 Recall 都进入 Checkpoint。

---

## 2. RAG Recall

一次 RAG：

```text
E1
E2
E3
E4
E5
```

每条必须具有唯一标识：

```yaml
evidence_id:
source_ref:
content:
retrieval_score:
```

Context 中可展示：

```text
[E1] ...
[E2] ...
```

---

## 3. Agent 如何知道自己用了哪些 Evidence

要求模型通过 Structured Output 显式声明：

```json
{
  "answer": "...",
  "evidence_usage": [
    {
      "evidence_id": "E1",
      "derived_fact": "产品X支持M03加工",
      "usage_type": "DECISION"
    }
  ]
}
```

推荐 Usage Type：

```text
ANSWER
DECISION
CONSTRAINT
TOOL_CALL
STATE_UPDATE
```

---

## 4. 为什么不能只靠事后猜

如果仅使用语义相似度判断：

```text
回答和E1很像
→ 推断E1被使用
```

会出现：

- 多证据表达相似
- 模型综合多个来源
- Evidence 只用于触发 Tool Call
- 模型读到了但没有实际使用

因此第一版使用：

```text
Agent Self Attribution
```

高风险场景可增加：

```text
Evidence Verifier
```

进行离线/二次校验。

---

## 5. Evidence Used Event

```json
{
  "event_type": "EVIDENCE_USED",
  "payload": {
    "evidence_id": "E1",
    "derived_fact": "产品X支持M03加工",
    "usage_type": "DECISION"
  },
  "references": {
    "rag_event_id": "evt_100"
  }
}
```

这样 Compactor 不需要重新判断 Evidence 是否被使用。

---

## 6. RAG 生命周期

```text
RAG Store
   ↓
Retrieve
   ↓
Recall Working Set
   ↓
Agent
   ↓
Used?
 ┌─┴─────────────┐
 No              Yes
 │                │
DROP          Future Relevant?
              ┌──┴─────┐
              No       Yes
              │         │
            DROP    Checkpoint
                    derived fact
                    + source_ref
```

“DROP”是退出 LLM Context，不是删除知识库。

---

## 7. Checkpoint 保存方式

错误：

```yaml
rag_content:
  3000 token 原文...
```

正确：

```yaml
facts:
  - value: 产品X支持M03和M05加工
    source_type: rag
    source_ref: DOC-123:C18
    evidence_id: E1
    validity: stable
```

以后需要完整工艺条件：

```text
source_ref
  ↓
重新检索
```

---

## 8. Memory

Memory 是跨 Session 的可复用个人/业务信息。

Recall：

```json
{
  "event_type": "MEMORY_RECALL",
  "payload": {
    "memory_id": "MEM-18",
    "content_ref": "memory://MEM-18"
  }
}
```

如果实际应用：

```json
{
  "event_type": "EVIDENCE_USED",
  "payload": {
    "evidence_id": "MEM-18",
    "derived_fact": "本次采用紧急订单优先",
    "usage_type": "CONSTRAINT"
  }
}
```

Checkpoint 保存的是当前 Session 的应用效果：

```yaml
constraints:
  - 本次排程采用紧急订单优先
```

不是整份长期 Memory。

---

## 9. 优先级

推荐：

```text
当前用户明确指令
    >
最新实时 Tool 状态
    >
当前 Checkpoint
    >
Memory Recall
    >
RAG 背景知识
```

例如长期 Memory：

```text
用户通常偏好紧急订单优先
```

当前用户说：

```text
这次不要按紧急程度排
```

必须服从当前指令。

---

## 10. Stable 与 Volatile Evidence

### Stable

```text
产品X工艺上支持M03
```

可较长期使用。

### Volatile

```text
M03当前空闲
```

必须保存：

```yaml
observed_at:
validity: volatile
refresh_policy:
```

在 Status Bar 可产生：

```text
M03状态已过期，需要重新查询。
```

---

## 11. Tool Result 也可视为 Evidence

统一 Evidence 模型：

```python
class EvidenceRef:
    evidence_id: str
    source_type: str
    source_ref: str
```

source_type：

```text
rag
memory
tool
user
```

这使决策来源统一可追踪。

---

## 12. Tool Call 的 Evidence Attribution

Evidence 不只支持最终回答，也可能触发 Tool：

```json
{
  "event_type": "TOOL_CALL",
  "payload": {
    "tool_id": "query_fixture_availability"
  },
  "references": {
    "evidence_ids": ["E3"]
  }
}
```

说明：

```text
E3
→ 发现M03需要T08
→ 触发查询T08
```

这对解释轨迹非常重要。

---

## 13. 压缩规则

### RAG_RECALL

未使用：

```text
DROP
```

### EVIDENCE_USED

如果 future relevant：

```text
derived_fact + source_ref
→ Checkpoint
```

否则 Drop。

### MEMORY_RECALL

未应用：

```text
DROP
```

已应用：

```text
保存对当前 Session 的状态影响
```

---

## 14. Evidence 评估指标

```text
Recall Precision
Recall Recall@K
Evidence Used Rate
Evidence Attribution Accuracy
Unsupported Claim Rate
Stale Evidence Usage Rate
```

还可分析：

```text
召回很多但使用率低
→ Retrieval 噪声过大

Evidence在Recall里但未被模型使用
→ Prompt/Attention问题

模型使用但无法支撑Claim
→ Attribution/Reasoning问题
```

---

## 15. 第一版实现

最低实现：

```text
evidence_id
source_ref
EVIDENCE_USED
derived_fact
usage_type
```

不要第一版就引入复杂 Claim Graph。

高风险排产动作后续可增加：

```text
claim → evidence mapping verifier
```

---

## 16. 验收标准

- 能明确回答“这次决策用了哪几条 RAG”。
- 未使用 Recall 不进入 Checkpoint。
- RAG 原文不长期驻留 Context。
- future-relevant 结论可通过 source_ref 再取详情。
- Memory 与当前 Session 状态不混为一体。
- Volatile Evidence 有时间与刷新语义。
