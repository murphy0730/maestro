---
name: weather
description: 查询指定城市的当前天气，返回实时温度、天气状况、湿度和风力。
allowed-tools: [mcp__weather__get_weather]
---
# Weather

当用户询问当前天气时，必须调用 `mcp__weather__get_weather`，并把用户提供的城市名作为
`city` 参数。根据工具返回的 `observed_at`、`condition`、`temperature`、`humidity`、
`wind_speed` 等字段回答，并注明数据来源为 Open-Meteo。

不要生成或建议执行 `curl`，不要使用模型记忆猜测实时天气，也不要声称执行了未实际调用的工具。
如果工具返回错误，直接说明错误内容并请用户确认城市名或稍后重试。
