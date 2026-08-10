---
name: scheduling-query
description: 编排并查询 llm4drd 排产工作流。用于检查五步就绪状态、校验实例、运行内置规则、多目标优化或近期窗口精确求解、比较方案 KPI、查询订单/工序、诊断瓶颈与延误、评估急单插入，以及查询或控制在线调度。普通“如果改机器/班次/交期会怎样”的假设推演改用 whatif-planning。
allowed-tools:
  - mcp__planning__get_scheduling_status
  - mcp__planning__validate_planning_instance
  - mcp__planning__list_planning_rules
  - mcp__planning__list_planning_objectives
  - mcp__planning__build_planning_context
  - mcp__planning__run_rule_planning
  - mcp__planning__start_planning_optimization
  - mcp__planning__get_planning_task
  - mcp__planning__start_exact_window_optimization
  - mcp__planning__get_planning_overview
  - mcp__planning__compare_planning_solutions
  - mcp__planning__search_planning_entities
  - mcp__planning__get_order_planning
  - mcp__planning__get_operation_planning
  - mcp__planning__diagnose_bottleneck
  - mcp__planning__explain_order_delay
  - mcp__planning__evaluate_order_insertion
  - mcp__planning__get_insertion_schedule
  - mcp__planning__get_online_dispatch_status
  - mcp__planning__control_online_dispatch
  - read_artifact
disable-model-invocation: true
---

# 排产工作流、查询与在线调度

处理正式实例上的非 What-if 排产任务。优先走最短、可审计的工具链，不重复计算，不编造 ID，
不把“已提交任务”描述成“已经完成”。

## 先判断任务类型

- 只查询已有方案、订单或工序时，直接调用最匹配的查询工具；结果缺失、过期或提示工作流未就绪时，
  再调用 `get_scheduling_status`。
- 要校验、重建上下文、运行规则、启动优化、评估插单或改变在线调度状态时，先调用
  `get_scheduling_status`，按 `state=current` 继续，遇到 `state=blocked` 先处理其 `detail`。
- 用户提出“加机器、改班次、改交期后会怎样”等假设时，停止本流程并使用 `whatif-planning`。

## 工具选择

| 目标 | 工具 |
|---|---|
| 查看五步工作流当前/阻塞步骤 | `get_scheduling_status` |
| 校验订单、工艺、资源与日历约束 | `validate_planning_instance` |
| 构建图谱与计算上下文 | `build_planning_context` |
| 查询内置规则 / 优化目标 | `list_planning_rules` / `list_planning_objectives` |
| 运行一条内置规则 | `run_rule_planning` |
| 启动多目标优化 / 近期窗口精确求解 | `start_planning_optimization` / `start_exact_window_optimization` |
| 轮询 graph、optimization、exact_window 任务 | `get_planning_task` |
| 查看或比较方案 KPI 与逐机负荷 | `get_planning_overview` / `compare_planning_solutions` |
| 搜索订单、工序和资源 | `search_planning_entities` |
| 查询订单或工序排程 | `get_order_planning` / `get_operation_planning` |
| 诊断真瓶颈 / 解释单个订单延误 | `diagnose_bottleneck` / `explain_order_delay` |
| 评估急单并按需读取合并排程 | `evaluate_order_insertion` / `get_insertion_schedule` |
| 查询或操作在线调度 | `get_online_dispatch_status` / `control_online_dispatch` |

## 推荐调用链

### 生成并比较候选方案

1. 调用 `get_scheduling_status`。
2. 仅在校验缺失、过期或用户要求强制复核时调用 `validate_planning_instance`；`errors` 非空就停止。
3. 图谱未就绪时调用 `build_planning_context`，保存 `task_id`，用
   `get_planning_task(task_type="graph")` 轮询到 `done`。
4. 调用 `list_planning_objectives` 选择合法目标，再调用 `start_planning_optimization`。
5. 用返回的 `task_id` 调用 `get_planning_task(task_type="optimization")`；`running` 时继续轮询，
   `failed/error` 时报告原始错误，不换参数偷偷重跑。
6. 完成后调用 `get_planning_overview`，按需用 `compare_planning_solutions`、
   `diagnose_bottleneck` 或 `explain_order_delay` 得出结论。

用户只要求某条内置规则时，完成状态检查并查询合法规则后调用 `run_rule_planning`。该工具会更新
最近一次仿真结果；只有用户明确要求运行时才调用，并等待 Policy Gate 审批。

### 精修近期窗口

先调用 `list_planning_objectives`，只使用精确求解支持的目标。启动
`start_exact_window_optimization` 后，用 `get_planning_task(task_type="exact_window")` 轮询。
它用于全局方案后的近期窗口精修，不要把窗口结果冒充完整全局排程。

### 评估急单

1. 用 `get_planning_overview` 选择完整基准；`base_source="solution"` 时使用真实 `task_id` 和
   `solution_id`，绝不猜测。
2. 一次性向 `evaluate_order_insertion` 提交完整 `orders` 与 `operations`。默认使用
   `policy="frozen"`；只有用户允许移动原工序且仍要保护原订单交期时使用 `due_protected`。
3. 先根据返回的订单结论回答；只有需要甘特明细时才调用 `get_insertion_schedule`，优先带
   `order_id` 并限制 `limit`。

### 处理在线故障

先调用 `get_online_dispatch_status`。仅在用户明确要求时调用 `control_online_dispatch`：

- `start` 会重置现有在线会话；
- `advance` 推进仿真时钟；
- `breakdown` 会中断在制工序，`repair_at_hours` 是相对计划起点的绝对小时；
- `repair` 提前修复；
- `reschedule` 只重排剩余工序。

这些动作会改变在线状态并需要审批。审批只表示获准执行；必须等工具成功结果后才能声称已完成。

`validate_planning_instance`、`build_planning_context`、两类优化启动和 `evaluate_order_insertion`
虽然不改正式实例业务数据，也会更新快照、创建任务或内存结果。只在当前请求需要时调用，并服从
Policy Gate；任何审批都不能替代工具成功结果。

## 结果与口径

- `solution_count` 才是方案总数；`candidate_count`、`baseline_count`、`reference_count` 是来源分项。
- `machine_utilization_ranking` 是全周期负荷榜，不是瓶颈。真瓶颈必须看
  `diagnose_bottleneck` 的 capacity/dispatch/班次/停机/资源等待归因。
- `total_order_tardiness_hours` 是订单级延误；方案 KPI 的 `total_tardiness` 是任务级累计，不能混用。
- `planned=false` 或未完整排入比“已知延误”更严重，必须先报告；`tardiness_hours=null` 不代表准时。
- `inevitable_tardiness_hours` 不能靠加机器或加班消除，只能调整交期或工艺。
- 长任务返回 `task_id` 只表示已启动。轮询使用原 `task_type` 和 `task_id`，不要创建重复任务。
- 尊重所有 `*_total`、`*_truncated` 标记。结果转为 artifact 时只调用一次 `read_artifact`，
  读取后形成结论。
- `structuredContent.ok=false` 是可修正的业务结果；依据错误码澄清输入。MCP `isError=true` 是依赖故障，
  明确报告服务不可用，不虚构排产结论。

回答时给出数字、口径、方案名称和可执行建议；不要只复述工具摘要。
