---
name: time-query
description: 查询当前日期与时间，支持指定 IANA 时区。
allowed-tools: [get_current_time]
---
# 时间查询

当用户询问「现在几点」「今天几号」「某时区现在是什么时间」等问题时，使用本技能，
调用 `get_current_time` 工具获取准确时间。若用户未指定时区，默认返回 UTC；
可提示用户给定 IANA 时区名（如 Asia/Shanghai）以获得本地时间。
