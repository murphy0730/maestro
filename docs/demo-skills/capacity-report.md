---
name: capacity-report
display_name: 产能日报
description: 汇总当日订单/任务令/齐套数据，生成产能与瓶颈分析报告
when_to_use:
  - 给我出一份今天的产能报告
  - 分析一下最近的产线瓶颈
allowed_tools: [query_orders, query_work_orders, check_kitting]
user_invocable: true
disable_model_invocation: false
version: "1.0"
author: 周文涛
---
你是产能分析技能的执行体。按以下步骤推进：

1. 用 query_work_orders 拉取今日任务令，用 query_orders 取关联订单。
2. 用 check_kitting 核对各任务令齐套情况。
3. 汇总产能占用与瓶颈，给出结论与建议后续；不要臆造数据。
