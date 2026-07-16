# Runtime 去除结构化计划层设计

日期：2026-07-16

状态：已确认，待文档复核

本文件修订并优先于《Manufacturing Agent Runtime 重构设计》中所有与 `GoalSpec`、`TypedPlan`、`PlanStep` 及其结构化路径有关的内容。

## 决策

Runtime 不再生成、保存、验证或执行预先构建的目标规范与 DAG 计划。删除 `GoalSpec`、`TypedPlan`、`PlanStep`，以及模型适配器中为它们服务的接口。

每个请求仍生成 `RunIntent`。它只负责选择初始运行强度，不是计划。简单请求进入快速循环；多能力、后台、外部等待、fork、高风险或模型不确定请求进入**受控执行模式**。

## 受控执行模式

受控执行模式沿用同一 Run、Journal、能力快照、预算和取消语义，但不构造计划图：

- 每轮只接受一个模型动作；
- 更严格的步数、时间、循环与上下文预算；
- 所有 Tool/MCP 副作用仍先经 Policy Gate 与审批；
- 未知写入结果停止后续副作用并进入对账；
- fork Skill 创建权限不超过父 Run 的 Child Run；
- 运行可从 Journal/快照恢复，但恢复的是运行状态与下一轮上下文，不是计划步骤图。

快速路径发现风险或复杂度后，可以单向升级为受控执行模式。升级冻结工作集、保留同一 `run_id`、预算、审批历史和能力快照，并记录原因；不得降级回快速路径。

## 删除范围

- `maestro.runtime.models`：删除 `GoalSpec`、`TypedPlan`、`PlanStep`，以及 `RunRecord.goal_spec`、`RunRecord.typed_plan`。
- `maestro.runtime.model`：删除 `structure_goal()`、`create_plan()` 和任何相关模型提示词。
- Runtime 测试、fakes、公开导出和文档：删除相关断言、队列和 API。
- 不创建 `runtime/planning.py`，不实现 DAG 校验、拓扑执行或计划级依赖语义。

`RunIntent`、Policy Gate、Journal、Artifact、Capability 快照、Skill 渐进加载、上下文信任边界、审批、取消、恢复及 Child Run 保持不变。

## 验收标准

1. Runtime 源码、测试和公开导出中没有 `GoalSpec`、`TypedPlan` 或 `PlanStep`。
2. `RunRecord` 不包含结构化计划字段；Journal/replay 与快照不依赖这些字段。
3. 模型协议只支持意图分类与逐轮动作，不支持目标或计划生成。
4. 高复杂度路径以受控执行模式运行，且快速路径只能单向升级。
5. 所有现有 Runtime 测试和完整后端测试通过；不引入制造业务能力。
