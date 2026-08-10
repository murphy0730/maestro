---
name: whatif-planning
description: 在不修改正式数据库的内存沙箱中做排产 What-if 假设推演。用户询问“如果……会怎样 / 能否赶上交期 / 影响多大 / 哪个方案或规则更好”时使用：新建、列出、复述、校验或撤销场景；模拟增减机器、调整班次、工序工时或可用机器、订单交期/优先级/数量、停机窗口、工装、人员/技能、机器类型关键性或计划基准时刻；用单条或多条派工规则试排，轮询长任务，对比改动与现状、跨场景/跨规则 KPI，并分析瓶颈及瓶颈转移。只覆盖内存沙箱推演，不用于普通现状查询、正式重排或将改动写入正式库。
allowed-tools: [mcp__planning__get_planning_overview, mcp__planning__diagnose_bottleneck, mcp__planning__search_planning_entities, mcp__planning__list_planning_rules, mcp__planning__create_whatif_scenario, mcp__planning__apply_whatif_patch, mcp__planning__describe_whatif_scenario, mcp__planning__revert_whatif_patch, mcp__planning__run_whatif_planning, mcp__planning__get_whatif_run, mcp__planning__compare_whatif_runs, read_artifact]
---

# 排产 What-if 场景推演

在**不改数据库**的前提下，改一份内存里的车间数据副本，跑规则，比 KPI。
改动只活在排产后端的进程内存里，服务重启即失；正式实例数据与四步流程结论都不受影响。

## 最短路径（先看这个，务必照做）

**一次对话的工具调用次数是硬性受限的（约 5 次），超了整个推演会直接失败、一个字都答不出来。**
所以每一次调用都必须算数。目标机器明确时，标准推演正好 4 步：

1. **一次** `search_planning_entities`：`entity_type="machine"` + `query=<用户提到的工艺类型或机器名>`。
   返回里已经同时包含 `type_id` 和可直接抄用的 `shift_pattern`——**不需要**再单独查一次
   `machine_type`。只有用户完全没提是什么设备、必须先看有哪些类型时，才多花这一步。
2. **一次** `create_whatif_scenario`：只建一个场景。
3. **一次** `apply_whatif_patch`：把**所有**改动放进同一个 `patches` 数组一次提交。
   分两次调用是浪费，会直接导致推演跑不完。
4. **一次** `run_whatif_planning`：`rule_names` 里一次列全所有要跑的规则。
   现状对照会自动一起跑，**不要**为基线单独建场景或单独跑一次。

第 4 步的返回里已经同时含改动后与现状两组 KPI，**通常可以直接据此作答，不必再调
`compare_whatif_runs`**——只有需要精确的方向判定（`better` 字段）或跨多次推演比较时才调它。

`describe_whatif_scenario` / `revert_whatif_patch` 只在出问题时用，正常流程里不要调。

用户说的是“关键设备”或“瓶颈设备”而不是明确机器名时，先区分概念：

- **关键类型**是机器类型的静态标记，可从资源查询的 `is_critical` 看；
- **负荷最高**来自 `machine_utilization_ranking`，只是全周期利用率排名，不能当瓶颈；
- **真正瓶颈**必须调用 `diagnose_bottleneck`，只把确实卡住延误订单的等待作为依据。

`diagnose_bottleneck` 必须使用真实 `solution_id`。优先复用会话中已经出现的 ID；没有时只调用一次
`get_planning_overview`，绝不猜 `sol_1`。根据用户要解决的问题选择目标：扩机器看
`capacity_wait_hours`，加班次看 `off_shift_wait_hours`；`dispatch_bound` 高时应改派工而不是扩产。

本 skill 刻意**不包含落库能力**。推演只做探索；要把改动写进正式数据是一次独立的管理动作，
需要在本流程之外单独执行。用户要求落库时，如实说明这一点，不要假装做不到或声称已经做了。

## 标准流程

### 1. 先读现状，再动手

**不要凭空编造机器编号、工艺类型或班次格式。** 用户说「加一台车床」，先查清车床的 `type_id`
叫什么、现有车床的班次串长什么样：

- `mcp__planning__search_planning_entities`，`entity_type="machine_type"` → 看有哪些工艺类型
- 再 `entity_type="machine"`, `query="车"` → 拿一台现有机器当模板

`entity_type` 可取 `order` / `operation` / `machine` / `machine_type` / `tooling` / `personnel`。
查资源时 `query` 可留空表示全量列出，但**优先带上关键字或用 `limit` 收窄**——结果太大时
宿主会把它转成 artifact，还得再花一步 `read_artifact` 去取。

资源返回的 `shift_pattern` 是**一天的班次模式**（如 `"0/8.0/10.0;0/20.0/8.0"`），可直接抄进
patch 的 `shifts` 字段——后端会自动按天铺开，不需要你写满整个日历。`shift_days` 是当前日历
覆盖的天数；`calendar_uniform=false` 表示各天班次不一致，此时 `shift_pattern` 只代表第一天，
照抄会抹平差异，要先向用户确认。

如果某个工具的结果被转成了 artifact（返回里给出 artifact 引用而不是内容），用 `read_artifact`
把它取回来再继续，不要因为看不到内容就猜。

### 2. 建场景

`mcp__planning__create_whatif_scenario`，`name` 用业务语言（「车床加一台」「全员只上白班」）——
它会出现在对比表里。

**只建一个场景就够。** `run_whatif_planning` 默认会把未改动的现状一起跑掉当对照，
不需要为基线单独建场景、单独跑一次。**每一步工具调用都很宝贵，不要浪费在重复的基线上。**

### 3. 打 patch

`mcp__planning__apply_whatif_patch`。一条 patch = `{op, entity, values}`，字段名与实例导入
模板的列名一致。`update` / `remove` 必须带 `id`、`ids` 或 `where` **三选一**作为选择器。

时间类字段一律是**相对计划基准时刻的偏移小时数**（不是日期）。
`shifts` 是 `"day/start_hour/hours;..."`，例 `"0/8/10;0/20/8"` = 白班 10h + 夜班 8h。

`day` 是从计划基准日开始的**相对日序号**，不是星期编号。只有 day 0 的模式会每天重复；
提供 day 0..5 会形成六天循环，并不表示“周日休息”。表达每周固定休息日时必须给完整七天模板，
休息日也要用零工时占位来保留该日。例如计划基准日是周一、周一至周六维持白夜班、周日休息：

`"0/8/10;0/20/8;1/8/10;1/20/8;2/8/10;2/20/8;3/8/10;3/20/8;4/8/10;4/20/8;5/8/10;5/20/8;6/0/0"`

计划基准日不是周一时，先从现状中的 `plan_start_at` 计算周日对应的相对日序号，再旋转七天模板；
不能把“周一=0、周日=6”当作永远成立。

| 想干什么 | 怎么写 |
|---|---|
| 加一台机器 | `{op:"add", entity:"machine", values:{machine_id, machine_name, type_id, shifts}}` |
| 删一台机器 | `{op:"remove", entity:"machine", id:"M07"}` |
| 某台机器改班次 | `{op:"update", entity:"machine", id:"M07", values:{shifts:"0/8/10"}}` |
| 某类机器全改只上白班 | `{op:"update", entity:"machine", where:{type_id:"turning"}, values:{shifts:"0/8/10"}}` |
| 每周日休息（基准日为周一） | `{op:"update", entity:"machine", where:{type_id:"turning"}, values:{shifts:"0/8/10;1/8/10;2/8/10;3/8/10;4/8/10;5/8/10;6/0/0"}}` |
| 改工序工时 | `{op:"update", entity:"operation", id:"OP123", values:{processing_time:4.5}}` |
| 改订单交期 | `{op:"update", entity:"order", id:"ORD01", values:{due_date:120}}` |
| 整批订单延期 | `{op:"update", entity:"order", ids:["O1","O2"], values:{due_date:150}}` |
| 加停机窗口 | `{op:"add", entity:"downtime", values:{machine_id:"M07", downtime_type:"maintenance", start_time:48, end_time:56}}` |
| 改计划基准时刻 | `{op:"update", entity:"planning_context", values:{plan_start_at:"2026-08-01T08:00:00+08:00"}}` |

支持的 `entity`：`order` `task` `operation` `machine` `machine_type` `tooling` `tooling_type`
`personnel` `downtime` `planning_context`。

打错了用 `mcp__planning__revert_whatif_patch` 撤销最近 N 条。

### 4. 回显并等用户确认

`mcp__planning__describe_whatif_scenario` 拿到改动清单、规模变化与校验结果，用人话复述：

> "已在副本上加了 1 台车床 M20（沿用 M07 的两班制），机器数 19 → 20。校验无问题。
> 要用哪几条规则跑？默认 ATC。"

**`validation.errors` 非空就停下来报告，不要硬跑。** 常见于删掉了某工序唯一能上的机器——
这种情况下仿真会输出一堆排不出的工序，KPI 毫无意义。`warnings` 提一句即可。

多条 patch 叠加、使用 `where` 批量更新，或目标机器是否命中存在疑问时，不能只看 changes 回放：
调用 `search_planning_entities` 并带上 `scenario_id`，查询场景物化后的最终资源状态。若这会耗尽
本轮工具预算，就在核对后向用户报告并把“运行规则”留到下一轮，不要冒险发起第 6 次工具调用。

### 5. 跑规则

`mcp__planning__run_whatif_planning`，`rule_names` 可传多条（如 `["ATC","EDD"]`）——
**多条规则一次传完，不要一条一条调**。可用规则见 `mcp__planning__list_planning_rules`。

`include_baseline` 默认为 true：`results` 里会同时含改动后（`variant="scenario"`）和现状
（`variant="baseline"`）两组，直接就能对比。

结果中的 `machine_utilization_ranking` 是逐机全周期负荷榜，不是瓶颈判定。需要解释“为什么晚”
时使用运行前的 `diagnose_bottleneck` 归因，不要把负荷排名改名成瓶颈。

- `status == "done"` → `results` 里就是结果
- `status == "running"` → 大实例还在跑，用返回的 `run_id` 调 `mcp__planning__get_whatif_run`
  轮询。生产规模实例一次仿真可能要几十秒，耐心轮询，不要改用别的办法绕过。
- `status == "failed"` → 看 `error`；校验不通过会在这里被拦住

### 6. 叙述对比

`mcp__planning__compare_whatif_runs`，传各场景的 `run_id`。第一个作为基准。

返回的每个指标带 `better` 字段——**已经按该指标是越小越好还是越大越好判定过了，直接用它，
不要自己猜方向**（利用率越高越好、延误越低越好，很容易讲反）。

给业务结论，不要只念数字：

> "加这台车床后，总延误从 12.3h 降到 8.1h（-34%），Makespan 从 96h 降到 91h。
> 代价是平均利用率从 82% 降到 76%——多出来的产能没吃满。
> 如果只是为了这批订单赶期，够用；长期扩产的话利用率偏低。"

## 常见坑

- **场景会过期**：推演期间若有人改了正式实例数据，工具返回 `WHATIF_BASE_STALE`。
  这时要重建场景并重新打 patch，不要试图绕过。
- **场景最多留 8 个**，超出后最旧的被淘汰，`WHATIF_SCENARIO_NOT_FOUND` 多半是这个原因。
- **删机器要小心**：某工序的 `eligible_machine_ids` 可能只有那一台。校验会拦住，但更好的做法
  是删之前先看看这台机器被哪些工序依赖。
- **加机器不等于加产能**：工序若显式指定了 `eligible_machine_ids`，只加同类型机器它是选不到的，
  还要同时把新机器加进该工序的可用机器列表；只有未指定的工序才按 `process_type` 自动匹配。
- **产能过剩时改动可能毫无效果**：如果实例利用率很低、排程受依赖链而非产能约束，
  砍班次/加机器可能对 KPI 一点影响都没有。这是真实结论，如实报告，不要为了「有变化」而
  编造差异或反复换参数试到有变化为止。

## 红线

1. **打 patch 前先读现状**，不要猜 id、猜工艺类型、猜班次格式。
2. **校验有 error 就停**，报告给用户，不要硬跑出一份没意义的 KPI。
3. **一次只回答一个假设**。用户同时问了「加机器」和「加班」两个方案，就建两个场景分别跑再一起
   对比——不要把两种改动混进一个场景，那样分不清是哪个改动起的作用。
4. **如实报告推演结果**，包括「没有明显改善」这种结论。
