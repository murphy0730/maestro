# Agent Context 架构与上下文装配设计

> 文档编号：02  
> 目标：定义每一轮 LLM 调用时 Context 的组成、生命周期、稳定性和装配规则。

---

## 1. 核心问题

传统聊天系统通常直接维护：

```python
messages.append(new_message)
```

随着 Tool Result、RAG、Skill 和长任务不断加入，Context 会出现：

- token 无限增长
- Prefix 频繁变化
- Prompt Cache 命中下降
- 历史噪声增加
- 重要约束被淹没
- 大块 Tool Schema、Raw Result 长期占用窗口

因此本设计采用“**状态化装配**”而不是“消息数组无限追加”。

---

## 2. 标准 Context 模型

```text
Context
=
Immutable Prefix
+
Latest Checkpoint
+
Recent Events
+
Runtime Status Bar
```

四部分回答不同问题：

| 层 | 回答的问题 |
|---|---|
| Immutable Prefix | 我是谁？我应该怎样行动？ |
| Latest Checkpoint | 到目前为止已经确定了什么？ |
| Recent Events | 最近具体发生了什么？ |
| Runtime Status Bar | 此时此刻最应该关注什么？ |

---

## 3. Immutable Prefix

### 3.1 应包含

- System Prompt
- 固定 Agent Role
- 固定行为规则
- 安全/权限基础规则
- 输出协议
- Tool Search 协议
- Skill Loading 协议
- Capability Namespace 名称与简述
- Skill 名称与简述
- Agent Version / Prefix Version

### 3.2 不应包含

- 当前时间
- 当前用户位置
- 实时设备状态
- RAG Recall 内容
- Memory Recall 内容
- 当前 TODO 全量
- 当前 Tool Result
- Tool 的大量完整 Schema
- 动态业务状态

### 3.3 Session 冻结

Session 创建时绑定：

```json
{
  "agent_definition_version": "v1.4",
  "system_prompt_hash": "...",
  "capability_index_hash": "...",
  "prefix_hash": "..."
}
```

同一 Session 不应在无记录情况下静默切换定义。

---

## 4. Latest Checkpoint

Checkpoint 是历史累计状态，不是聊天摘要。

推荐结构：

```yaml
goal:
  primary: 完成订单A1001排产

constraints:
  - 产品X禁止使用M01
  - 交期不得晚于2026-08-12

decisions:
  - 候选设备优先M05

current_state:
  order_id: A1001
  schedule_version: V3

completed_actions:
  - 订单信息获取
  - BOM检查
  - 库存检查

pending_actions:
  - 排程求解
  - 用户确认
  - MES下发

active_skill:
  id: production_scheduling
  version: "2.3"
  phase: optimization
```

Checkpoint 必须是累计状态：

```text
CP2 = Reduce(CP1 + Cold Events)
```

模型只看到最新 CP，不堆叠 CP1、CP2、CP3。

---

## 5. Recent Events

Recent Events 保留最近“热轨迹”的原始因果关系。

典型 Event：

```text
USER_MESSAGE
ASSISTANT_MESSAGE
TOOL_SEARCH
TOOL_CALL
TOOL_RESULT
RAG_RECALL
MEMORY_RECALL
EVIDENCE_USED
PLAN_UPDATED
CONSTRAINT_ADDED
USER_CONFIRMATION
ERROR
```

保留 Hot Events 的原因：

- 当前任务往往依赖最近几轮微妙语义
- Tool Call 与 Tool Result 的因果链需要保留
- 用户最近的修正指令优先级高
- 最新约束可能尚未进入 Checkpoint

---

## 6. Runtime Status Bar

Status Bar 放在 Context 最后，只做短控制提醒。

第一版建议：

```yaml
<agent_state>
goal: 完成A1001排产
current_step: 生成候选排程
next_action: 调用排程求解能力
blockers:
  - M03状态已过期
critical_constraints:
  - 产品X禁止使用M01
execution_gate:
  publish_schedule: blocked
alerts:
  - query_inventory同参数已调用3次
</agent_state>
```

目标：

- 正常 100～500 tokens
- 硬上限建议 800 tokens
- 正常信息尽量省略
- 异常信息 exception-only

---

## 7. Lazy Working Content

虽然标准逻辑结构只有四层，但真正请求 Provider 时可能还需要动态 Tool/Skill/RAG 内容。

原则：

> 动态大块内容通过 Runtime 绑定到本轮调用，不作为永久 Context 层管理。

例如：

```python
base_context = context_builder.build(session_id)
active_tools = tool_resolver.resolve(session_id, base_context)
active_skill = skill_resolver.resolve(session_id)
rag_chunks = retrieval_manager.resolve_current(session_id)

llm.invoke(
    messages=base_context,
    tools=active_tools,
    extra_context=[active_skill, rag_chunks]
)
```

其中：

- Tool Schema：Provider callable tool definition
- Skill Body：当前工作上下文
- RAG Chunk：当前工作上下文

它们都不是 Checkpoint。

---

## 8. ContextBuilder 设计

```python
class ContextBuilder:

    def build(self, session_id: str):
        prefix = self.prefix_manager.get_frozen_prefix(session_id)
        checkpoint = self.checkpoint_manager.get_latest(session_id)
        events = self.event_store.get_hot_events(session_id)
        status = self.status_bar_builder.build(session_id)

        return [
            *prefix,
            self.render_checkpoint(checkpoint),
            *self.render_events(events),
            self.render_status(status),
        ]
```

### 8.1 ContextBuilder 不负责

- 搜索 Tool
- 加载 Tool Schema
- 执行 Skill
- RAG 检索
- Compact 决策
- Event 持久化

保持其职责单一。

---

## 9. ContextManager 设计

```python
class ContextManager:

    def prepare(self, session_id, incoming_user_tokens):
        estimate = self.estimate_projected_tokens(
            session_id,
            incoming_user_tokens
        )

        if estimate >= self.policy.force_compact_trigger:
            self.force_compact(session_id)

        elif estimate >= self.policy.compact_trigger:
            self.incremental_compact(session_id)
```

预测值应考虑：

```text
projected_context_tokens
=
prefix
+ checkpoint
+ hot_events
+ incoming_user
+ planned_retrieval_budget
+ planned_tool_budget
+ output_reserve
```

---

## 10. Prefix Stability 与动态尾部原则

设计要求：

```text
固定内容尽量在前
动态内容尽量在后
```

同一 Session：

```text
Round 1:
PREFIX | CP1 | Events | Status

Round 2:
PREFIX | CP1 | Events+ | Status'

Compact:
PREFIX | CP2 | Hot Events | Status''
```

Prefix 不因 RAG、Tool Schema、Skill 内容改变。

---

## 11. Context Epoch

每次 Checkpoint 替换可以视为一个新的 Context Epoch：

```text
Epoch 1:
PREFIX + M001~M086

Compact

Epoch 2:
PREFIX + CP1 + M087~M130

Compact

Epoch 3:
PREFIX + CP2 + M131...
```

静态 Prefix 不变，动态 baseline 变化。

---

## 12. 信息重复控制

四层之间应避免无意义复制。

### Prefix

不重复到 Checkpoint。

### Checkpoint

保存完整有效状态，但不复制 Tool Schema / Skill Body / RAG 原文。

### Recent Events

保留近期原始因果，不需要重复写成摘要。

### Status Bar

只投影当前关键控制信号。

原则：

```text
Prefix    = rules
Checkpoint= state
Events    = recent causality
Status    = current attention
```

---

## 13. 冲突优先级

建议默认：

```text
Current explicit user instruction
    >
Current verified runtime/tool state
    >
Latest Checkpoint
    >
Recalled Memory
    >
RAG background knowledge
```

同类信息中：

- 更新时间更近者优先
- 权威业务系统高于历史摘要
- 明确用户修改应产生 Constraint/Decision Event

---

## 14. 失败保护

ContextBuilder 在以下情况应拒绝静默继续：

- Prefix 版本找不到
- Checkpoint lineage 损坏
- Hot Event sequence 不连续
- 当前 Session 使用未知 ModelProfile
- 核心执行权限状态缺失且即将执行副作用操作

不应让 LLM 自己猜这些基础状态。

---

## 15. 第一版验收指标

- Prefix token 占比稳定
- 平均 Context token 可控
- Compact 后任务成功率不显著下降
- 用户最近指令不丢失
- Critical Constraint 命中率高
- Status Bar 平均 token < 500
- Raw Tool Result 不进入长期 Context
