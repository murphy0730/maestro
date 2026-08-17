# Agent Event 与 Trajectory 数据模型设计

> 文档编号：03  
> 目标：将 Agent 会话从简单 `role + content` 消息流升级为可追踪、可回放、可压缩的结构化 Event Stream。

---

## 1. 核心定义

Event 不等于消息。

```text
Event
=
Envelope
+
Payload
+
Metadata
+
References
```

一条用户消息只是 `USER_MESSAGE` 事件的一种。

Event 回答：

> 在这个 Session 中发生了什么？

---

## 2. Event 与 State 的区别

```text
Event:
“用户在 20:03 增加了约束：产品X禁止M01”

State:
“当前有效约束包括：产品X禁止M01”
```

Event 是不可变事实；State 是 Event 归约后的当前结果。

因此：

- Event Store：append-only
- Checkpoint：state snapshot
- Runtime State：当前可计算状态

---

## 3. 统一 Event Envelope

推荐：

```python
class AgentEvent:
    event_id: str
    session_id: str
    sequence: int
    event_type: str

    payload: dict
    metadata: dict
    references: dict
```

示例：

```json
{
  "event_id": "evt_1024",
  "session_id": "s_001",
  "sequence": 1024,
  "event_type": "USER_MESSAGE",
  "payload": {
    "content": "把订单A排到明天。"
  },
  "metadata": {
    "created_at": "2026-08-08T20:00:00+08:00",
    "token_count": 12
  },
  "references": {
    "turn_id": "turn_58",
    "parent_event_id": "evt_1023"
  }
}
```

---

## 4. Metadata 设计原则

数据库可以保存丰富 Metadata，但不代表全部进入 LLM Context。

推荐通用字段：

```yaml
created_at:
token_count:
source:
trace_id:
span_id:
latency_ms:
model_id:
```

可选业务侧信道：

```yaml
timezone:
location_scope:
factory_id:
workshop_id:
```

只有任务相关时才投影给模型。

---

## 5. 第一版 Event Type

建议控制数量，不追求一次定义几十种。

### 5.1 对话类

```text
USER_MESSAGE
ASSISTANT_MESSAGE
```

### 5.2 Tool 类

```text
TOOL_SEARCH
TOOL_CALL
TOOL_RESULT
```

### 5.3 检索类

```text
RAG_RECALL
MEMORY_RECALL
EVIDENCE_USED
```

### 5.4 状态变化类

```text
CONSTRAINT_ADDED
CONSTRAINT_REMOVED
DECISION_UPDATED
PLAN_CREATED
PLAN_STEP_UPDATED
USER_CONFIRMATION
```

### 5.5 系统类

```text
ERROR
```

---

## 6. Tool Event

### 6.1 TOOL_SEARCH

```json
{
  "event_type": "TOOL_SEARCH",
  "payload": {
    "query": "查询订单缺料情况",
    "namespace": "WMS",
    "candidates": [
      {
        "tool_id": "query_material_shortage",
        "score": 0.93
      },
      {
        "tool_id": "query_inventory",
        "score": 0.81
      }
    ],
    "selected_tool_id": "query_material_shortage"
  }
}
```

注意：

- Event 不保存完整 Tool Schema。
- Schema 存 Tool Registry。
- TOOL_SEARCH 是轨迹数据，用于后续评估 Tool Search 准确率。

### 6.2 TOOL_CALL

```json
{
  "event_type": "TOOL_CALL",
  "payload": {
    "tool_id": "query_material_shortage",
    "tool_version": "2.1",
    "arguments": {
      "order_id": "A1001"
    }
  },
  "references": {
    "triggered_by_event_id": "evt_120",
    "evidence_ids": ["E3"]
  }
}
```

### 6.3 TOOL_RESULT

```json
{
  "event_type": "TOOL_RESULT",
  "payload": {
    "tool_id": "query_material_shortage",
    "status": "success",
    "digest": {
      "material_ready": false,
      "shortages": ["P003"]
    },
    "result_ref": "result://R123"
  },
  "metadata": {
    "latency_ms": 428
  },
  "references": {
    "tool_call_event_id": "evt_121"
  }
}
```

Raw Result 保存在 ToolResultStore。

---

## 7. RAG / Memory Event

### 7.1 RAG_RECALL

```json
{
  "event_type": "RAG_RECALL",
  "payload": {
    "retrieval_id": "rag_1001",
    "query": "产品X设备工艺约束",
    "evidences": [
      {
        "evidence_id": "E1",
        "source_ref": "DOC-123:C18"
      },
      {
        "evidence_id": "E2",
        "source_ref": "DOC-391:C03"
      }
    ]
  }
}
```

Event Store 可只保存引用；检索正文仍在知识库。

### 7.2 EVIDENCE_USED

```json
{
  "event_type": "EVIDENCE_USED",
  "payload": {
    "evidence_id": "E1",
    "derived_fact": "产品X支持M03加工",
    "usage_type": "DECISION"
  },
  "references": {
    "rag_event_id": "evt_130"
  }
}
```

这样 Compactor 不需要猜哪些 Recall 真正被使用。

---

## 8. 状态变化 Event

### CONSTRAINT_ADDED

```json
{
  "event_type": "CONSTRAINT_ADDED",
  "payload": {
    "constraint_id": "C17",
    "content": "产品X禁止使用M01",
    "scope": "current_session",
    "source_type": "user"
  },
  "references": {
    "source_event_id": "evt_200"
  }
}
```

### PLAN_STEP_UPDATED

```json
{
  "event_type": "PLAN_STEP_UPDATED",
  "payload": {
    "plan_id": "P001",
    "step_id": "T4",
    "from": "pending",
    "to": "in_progress"
  }
}
```

---

## 9. References：建立因果图

References 让 Event Stream 不只是线性日志，也可以形成局部因果关系。

典型关系：

```text
USER_MESSAGE
    ↓ triggered_by
TOOL_SEARCH
    ↓ selected
TOOL_CALL
    ↓ result_of
TOOL_RESULT
    ↓ supports
DECISION_UPDATED
```

建议字段：

```yaml
parent_event_id:
triggered_by_event_id:
tool_call_event_id:
source_event_id:
evidence_ids:
plan_id:
task_id:
```

不需要第一版建设通用图数据库，只需要关系字段足够可追溯。

---

## 10. Event Store 写入规则

### 10.1 append-only

已有 Event 不修改业务语义。

错误修正通过新增 Event：

```text
CONSTRAINT_ADDED C1
CONSTRAINT_REMOVED C1
CONSTRAINT_ADDED C2
```

而不是直接更新旧记录。

### 10.2 sequence 单调递增

Session 内：

```text
1, 2, 3, 4 ...
```

支持快速确定：

- Checkpoint 覆盖范围
- Cold/Hot Events
- Replay 顺序

### 10.3 Event 不承载大对象

不要直接写：

- 20K JSON Tool Result
- 5K Token Tool Schema
- 10K Token Skill Body
- 大型 RAG Chunk

保存：

```text
ref + digest + version/hash
```

---

## 11. Event 到 Context 的投影

Event Store 中的数据比 LLM 所需更多。

例如 TOOL_RESULT：

数据库：

```json
{
  "result_ref": "...",
  "latency_ms": 428,
  "trace_id": "...",
  "digest": {...}
}
```

LLM 可能只需要：

```text
[TOOL_RESULT]
query_material_shortage:
A1001缺少P003
```

因此需要 Renderer：

```python
class EventRenderer:
    def render_for_llm(self, event):
        ...
```

---

## 12. Event 到 Checkpoint 的归约

不同 Event 处理方式：

| Event | Checkpoint 处理 |
|---|---|
| USER_MESSAGE | 提取有效目标/约束/事实 |
| ASSISTANT_MESSAGE | 只保留已形成决策/承诺 |
| TOOL_SEARCH | 通常 DROP |
| TOOL_CALL | 通常不单独保存 |
| TOOL_RESULT | 提取未来相关业务事实 |
| RAG_RECALL | 未使用则 DROP |
| EVIDENCE_USED | 保存 future-relevant derived fact |
| PLAN_STEP_UPDATED | 更新计划里程碑 |
| CONSTRAINT_ADDED | 写入 active constraint |
| USER_CONFIRMATION | 写入执行状态 |
| ERROR | 仅持续影响任务时保留 |

---

## 13. Event 不是 Telemetry Dump

不建议把以下变化每轮都变 Event：

```text
CURRENT_TIME_UPDATED
TOKEN_COUNT_UPDATED
WORKING_DIRECTORY_UPDATED
TODO_PROGRESS_COMPUTED
```

判断标准：

> 是否真的“发生了一件对 Agent 轨迹有意义的事情”？

如果只是当前可计算值，应属于 Runtime State / Metadata。

---

## 14. Replay

Replay 输入：

```text
Frozen Prefix Version
+
Checkpoint before target event
+
Events after checkpoint
+
Tool/Skill/RAG references
```

用途：

- 调试错误 Tool 选择
- 分析 Constraint 丢失
- 分析 Summary Drift
- 复现某次排程决策
- 离线 Eval

---

## 15. 第一版实现建议

数据库核心表：

```text
agent_event
```

第一版字段：

```text
event_id
session_id
sequence
event_type
payload_json
metadata_json
references_json
created_at
token_count
```

先使用 JSONB，不要一开始为每种 Event 建独立表。稳定后再对高频字段做索引或拆表。
