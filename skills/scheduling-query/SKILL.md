---
name: scheduling-query
description: 查询排产方案、规则、订单、工序、设备负荷与延误成因。用于“有哪些方案”“比较 KPI”“哪台机器是真瓶颈”“某订单为什么晚”“某工序排在哪里”等只读排产问题。
allowed-tools: [mcp__planning__list_planning_rules, mcp__planning__get_planning_overview, mcp__planning__compare_planning_solutions, mcp__planning__search_planning_entities, mcp__planning__diagnose_bottleneck, mcp__planning__explain_order_delay, mcp__planning__get_order_planning, mcp__planning__get_operation_planning, read_artifact]
disable-model-invocation: true
---

# 排产查询与延误归因

只读查询排产结果。优先用一个最匹配的工具直接回答；只有缺少真实 ID、结果歧义或返回 artifact
时才增加一次查询。不要先把所有工具各调一遍。

## 工具选择

| 用户问题 | 工具 |
|---|---|
| 有哪些内置规则 | `mcp__planning__list_planning_rules` |
| 有多少方案、方案 ID 与概览 KPI | `mcp__planning__get_planning_overview` |
| 比较方案 KPI 或查看逐机负荷 | `mcp__planning__compare_planning_solutions` |
| 搜订单、工序、机器或机器类型 | `mcp__planning__search_planning_entities` |
| 哪台机器真正卡住了延误订单、该扩产还是加班 | `mcp__planning__diagnose_bottleneck` |
| 某个订单为什么晚、还能怎么救 | `mcp__planning__explain_order_delay` |
| 某订单在各方案中如何排 | `mcp__planning__get_order_planning` |
| 某工序何时、在哪台机器加工 | `mcp__planning__get_operation_planning` |

## 必须区分的口径

1. `machine_utilization_ranking` 是全体机器按 `full_horizon_utilization` 排出的**负荷榜**，
   不是瓶颈归因。全周期分母包含非工作时间，只上白班的机器数值天然偏低。
2. 真正的瓶颈必须看 `diagnose_bottleneck`：
   - `capacity_bound`：被分配机器和同期备选机器都忙，扩机器有用；
   - `dispatch_bound`：有备选机器空着，是派工/选机问题，扩机器没用；
   - `off_shift`：没排班，加班次有用；
   - `downtime`：设备停机；
   - `idle`：机器空着但被工装、人员或前置资源卡住。
3. `total_order_tardiness_hours` 是订单级延误；方案 KPI 的 `total_tardiness` 是任务级累计，
   两者口径不同，不能互相替代或强行对齐。
4. `solution_count` 才是方案总数；`candidate_count`、`baseline_count`、`reference_count`
   都只是分项计数。面向用户使用 `solution_name`，不要拿 `solution_id` 当方案名。

## 诊断规则

- `diagnose_bottleneck` 和 `explain_order_delay` 都依赖具体 `solution_id`。不知道 ID 时先查一次
  `get_planning_overview`，或使用工具错误里的 `suggestions`；绝不编造 `sol_1` 之类的 ID。
- `planned=false` 表示订单没有完整排入方案，`tardiness_hours=null` 不等于准时；先报告未排入。
- `inevitable_tardiness_hours` 是工艺链即使资源无限也无法避免的延误。这部分加机器、加班都无效，
  只能调整交期或工艺。
- `unscheduled_order_count` 或 `partially_scheduled_order_count` 非零时，先报告这些订单；它们不在
  等待归因中，比已知延误更严重。
- 返回被转成 artifact 时只调用一次 `read_artifact`，读取后直接形成结论。

回答应给出数字、口径和业务处置建议，不要把负荷最高直接写成“瓶颈”。
