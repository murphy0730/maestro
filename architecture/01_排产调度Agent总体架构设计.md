# 排产调度 Agent 总体架构设计

> 文档编号：01  
> 目标：定义排产调度 Agent 的总体技术架构、模块边界、核心数据流和演进原则。  
> 本文是其余 10 篇设计文档的总纲。

---

## 1. 背景与目标

排产调度 Agent 面向制造业生产计划与调度场景，需要在长时间、多轮、多步骤任务中持续理解用户目标，访问 MES、ERP、WMS、APS/求解器等外部系统，并在约束不断补充、业务状态持续变化的情况下完成：

- 订单分析
- 物料齐套分析
- 设备与工艺能力检查
- 排程优化
- 方案解释与比较
- 用户确认
- 排程下发
- 后续状态追踪

与普通问答 Agent 相比，该 Agent 具有几个明显特征：

1. **会话长**：单个任务可能跨几十到几百个 Agent Step。
2. **工具多**：MES/WMS/ERP 中可能存在数百个细粒度接口。
3. **动态性强**：库存、设备、工单状态持续变化。
4. **约束多**：工艺、交期、资源、业务规则、用户临时指令并存。
5. **副作用强**：下发排程、创建工单等动作必须受权限和确认控制。
6. **需要可解释**：需要知道为什么选择某设备、为什么调用某工具、用了哪些证据。
7. **需要可回放**：出现错误后应能重建当时的 Agent 轨迹和上下文。

因此总体目标不是构建一个“大 Prompt”，而是构建一套可长期运行的 **Agent Runtime + Context Management + Capability Runtime + State Management**。

---

## 2. 总体设计原则

### 2.1 上下文按需装配，而不是无限追加

每轮 Context 由固定层和动态层组装：

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

完整 Tool Schema、Skill 正文、RAG Chunk、Raw Tool Result 等大块内容不长期驻留，而是按需加载。

### 2.2 Prefix 尽量稳定

Session 创建后冻结：

- System Prompt
- Agent 固定角色与行为规则
- Tool Search / Skill Loading 协议
- Capability Namespace 简介
- Skill 名称与简述
- 固定权限与安全策略
- Agent Definition Version

动态信息不修改 Prefix，而是进入尾部动态上下文。

### 2.3 Event 是事实轨迹，Checkpoint 是累计状态

```text
Event
= 发生了什么

Checkpoint
= 截止某一时刻已经形成了什么有效状态
```

Event Store 采用 append-only 思路；Checkpoint 是对历史 Event 的状态归约结果。

### 2.4 大块内容“外置”，Context 只保存当前工作集

统一原则：

```text
External Source of Truth
        ↓
     reference
        ↓
按需 Materialize
        ↓
Working Context
        ↓
使用后产生状态/结论
        ↓
Checkpoint
```

适用于：

- Tool Schema
- Skill Body
- RAG Chunk
- Memory Detail
- Raw Tool Result

### 2.5 能由程序确定的状态，不让 LLM 猜

例如：

- 当前时间
- Tool 调用次数
- 数据 freshness
- Context token 数量
- 用户是否确认
- Tool 执行成功/失败
- Plan Task 状态

这些由 Runtime 计算。

LLM 负责：

- 语义理解
- 任务分解
- 约束提取
- 决策
- Tool Search 意图生成
- 证据使用声明
- 必要的重规划

---

## 3. 总体架构

```text
                         ┌─────────────────────┐
                         │        User         │
                         └──────────┬──────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────┐
│                     Agent Runtime                        │
│                                                          │
│  ┌───────────────┐   ┌───────────────┐                  │
│  │ ContextManager│   │  PlanManager  │                  │
│  └──────┬────────┘   └──────┬────────┘                  │
│         │                   │                            │
│  ┌──────▼────────┐   ┌──────▼────────────┐              │
│  │ ContextBuilder│   │ StatusBarBuilder  │              │
│  └──────┬────────┘   └───────────────────┘              │
│         │                                                │
│         ▼                                                │
│  ┌─────────────────────────────────────────┐             │
│  │                LLM                      │             │
│  └───────┬──────────────┬──────────────┬───┘             │
│          │              │              │                 │
│          ▼              ▼              ▼                 │
│   ToolResolver     SkillResolver    RAG / Memory         │
│          │              │              │                 │
└──────────┼──────────────┼──────────────┼─────────────────┘
           │              │              │
           ▼              ▼              ▼
      Tool Registry    Skill Store   Knowledge/Memory Store
           │
           ▼
      MCP / Local Tools
           │
      MES / ERP / WMS
```

支撑组件：

```text
EventStore
CheckpointManager
ConversationCompactor
ModelRegistry
ToolResultStore
EvidenceStore
Observability / Eval
```

---

## 4. 核心模块职责

### 4.1 Agent Runtime

负责一轮 Agent Loop：

1. 接收新用户输入
2. 写入 Event
3. 构建 Context
4. 调用 LLM
5. 处理 Tool Search / Skill Load / Tool Call
6. 写入结果 Event
7. 更新 Plan / Runtime State
8. 检查是否继续执行
9. 检查是否触发 Compact
10. 生成最终回复

Agent Runtime 是编排层，不承担领域数据持久化细节。

### 4.2 ContextManager

负责：

- 计算预计 Context token
- 判断是否需要 Incremental Compact
- 判断是否需要 Force Compact
- 触发 Full Rebase
- 控制 Hot/Cold Event 边界
- 保证预留输出与工具突发空间

### 4.3 ContextBuilder

只负责装配：

```text
Immutable Prefix
Latest Checkpoint
Recent Events
Latest Runtime Status Bar
```

不负责 Tool Search，不负责数据库业务逻辑。

### 4.4 EventStore

保存不可变 Agent 轨迹：

- 用户消息
- Agent 消息
- Tool Search
- Tool Call
- Tool Result
- RAG Recall
- Memory Recall
- Evidence Used
- Constraint Change
- Plan Change
- Confirmation
- Error

### 4.5 CheckpointManager

负责：

- 获取最新 Checkpoint
- 保存新 Checkpoint
- 管理 parent checkpoint
- 管理 covered event 范围
- 支持版本审计与回放

### 4.6 ConversationCompactor

负责：

```text
Previous Checkpoint + Cold Events
              ↓
        New Checkpoint
```

它负责状态归约，不负责数据库 CRUD。

### 4.7 ToolRegistry / ToolResolver

ToolRegistry 保存完整 Tool Definition。

ToolResolver 决定本轮提供给模型哪些 Tool：

```text
Core Tools
+
Current Active Tools
```

其余工具通过 Tool Search 按需加载。

### 4.8 SkillStore / SkillResolver

Skill Store 保存完整 Skill Body。

Prefix 中只暴露 Skill：

- name
- description

SkillResolver 根据当前任务加载完整 Skill。

### 4.9 PlanManager

管理复杂任务结构：

- goal
- task
- dependency
- status
- current step
- milestone

完整 TODO 不应重复写入每轮 Context。

### 4.10 StatusBarBuilder

生成每轮尾部的精简控制块：

```yaml
goal:
current_step:
next_action:
blockers:
critical_constraints:
alerts:
execution_gate:
```

Status Bar 是派生状态，不是 Source of Truth。

---

## 5. 一轮完整执行流程

```text
User Message
    │
    ▼
Append USER_MESSAGE Event
    │
    ▼
ContextManager.evaluate()
    │
    ├─ Need Compact? ── Yes ──> Compact
    │
    ▼
ContextBuilder.build()
    │
    ▼
LLM
    │
    ├─ Direct Answer
    │
    ├─ Tool Search
    │
    ├─ Tool Call
    │
    ├─ Skill Load
    │
    └─ RAG / Memory Recall
    │
    ▼
Append corresponding Events
    │
    ▼
Update Plan / Runtime State
    │
    ▼
Continue or Final Answer
```

---

## 6. 上下文中的信息归属

| 信息 | Source of Truth | 是否常驻 Context | 是否进入 Checkpoint |
|---|---|---:|---:|
| System Prompt | Agent Definition | 是 | 否 |
| Capability Namespace | Agent Definition | 是 | 否 |
| Tool Schema | Tool Registry | 否，按需 | 否 |
| Skill Body | Skill Store | 否，按需 | 否 |
| RAG 原文 | Knowledge Store | 否，按需 | 否 |
| Memory 原文 | Memory Store | 否，按需 | 否 |
| Raw Tool Result | ToolResultStore | 否 | 否 |
| 业务事实 | Event/Domain State | 根据需要 | 是 |
| 当前约束 | Event/Checkpoint | 是 | 是 |
| 当前 Goal | Plan/Checkpoint | 是 | 是 |
| TODO 全量 | PlanManager | 否 | 只保留里程碑 |
| Runtime Alert | Runtime | 是，异常时 | 否 |
| 用户确认 | Event/State | 是，必要时 | 是 |

---

## 7. 关键架构边界

### 7.1 MCP 与 Tool

MCP 是能力提供与接入方式，不是业务 Tool 本身。

```text
MCP Server
   └── Tool A
   └── Tool B
```

Agent 的 Tool 选择、调用、评估应围绕 Tool 展开。

### 7.2 Tool 与 Skill

```text
Tool
= 原子或能力级可调用动作

Skill
= 如何组合知识、步骤和 Tool 完成一个任务的方法
```

Skill 可以调用多个 Tool。

### 7.3 Event 与 State

```text
PLAN_STEP_UPDATED
```

是 Event。

```text
current_step = T4
```

是 State。

### 7.4 Checkpoint 与 Status Bar

```text
Checkpoint
= 完整、累计、可恢复的 Session State

Status Bar
= 当前推理最需要关注的控制投影
```

---

## 8. 第一版推荐实现范围

第一阶段不追求一次性实现全部高级机制。

建议优先：

1. EventStore
2. ContextBuilder
3. CheckpointManager
4. Incremental Compact
5. Tool Search + Lazy Schema
6. Skill Lazy Load
7. PlanManager
8. Status Bar
9. RAG Evidence Usage
10. 基础 Eval

延后：

- 多级 Tool 生命周期状态机
- Tool Schema TTL
- 自动复杂 Full Rebase 策略
- 高级 Evidence Verifier
- 复杂多 Agent 协同
- 自动学习 Tool Search Ranking

---

## 9. 设计验收标准

总体架构满足以下条件才算成功：

- 长会话不会因为 Raw Tool Result 或 Tool Schema 迅速撑满 Context。
- Prefix 在同一 Session 内基本稳定。
- 任意关键业务结论可以追溯到 Event 或 source_ref。
- 任意关键 Tool Call 可以追溯触发它的用户目标/证据。
- Compact 后 Agent 仍知道当前 Goal、约束、进度和下一步。
- Full Rebase 可以从原始 Event Log 重建状态。
- Tool 数量扩大后，不要求所有 Schema 常驻。
- Agent 不会因为 Status Bar 自身导致新的 Context 膨胀。
- 排程下发等副作用动作受到明确执行门控制。
