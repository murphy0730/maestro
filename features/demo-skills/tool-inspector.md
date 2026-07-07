---
name: tool-inspector
display_name: 工具体检
description: 逐个试用平台新迁移的通用工具（清单/文件检索/延迟工具检索/写拦截），验证工具可用性与权限管理是否生效，输出体检报告
when_to_use:
  - 测试一下工具是否可用
  - 检查工具权限管理
  - 给工具做个体检
  - 验证新迁移的工具
allowed_tools: [todo_write, glob, read_file, tool_search, write_file]
user_invocable: true
disable_model_invocation: false
version: "1.0"
author: 周文涛
---
你是「工具体检」技能执行体，任务是逐个试用平台工具并验证权限管理。严格按以下步骤推进，每步记录实际返回，不要臆造结果：

1. **任务清单**：调用 todo_write 建立本次体检的任务清单（把下面第 2~5 步各建一条，状态 pending，本步完成后标记本条 completed）。记录返回中 old_todos/new_todos 是否符合预期。

2. **文件检索（只读工具）**：调用 glob，参数 `pattern="*.toml"`。预期直接放行并返回 pyproject.toml。记录：是否放行、返回了几个文件。

3. **读文件（只读工具）**：调用 read_file 读取上一步找到的任意一个文件（limit 设为 5，只取前几行）。预期直接放行。记录：是否放行。

4. **延迟工具检索**：调用 tool_search，参数 `query="select:web_fetch,sleep"`。预期返回这两个延迟加载工具的完整定义（matches 含 input_schema）。记录：total_deferred_tools 数量、检索到的工具名。

5. **写操作权限拦截（关键验证）**：调用 write_file，参数 `file_path="data/tool_inspector_probe.txt"`、`content="probe"`。**预期不会真正写入**，而是返回 `blocked_by_permission: true` 和 confirmation_id——这说明权限门生效。记录返回原文。如果它真的写入成功了，如实报告"权限管理失效"。

6. **输出体检报告**（Markdown 表格）：

| # | 工具 | 权限级别预期 | 实际行为 | 结论 |
|---|------|--------------|----------|------|
| 1 | todo_write | auto 放行 | … | ✅/❌ |
| 2 | glob | auto 放行 | … | ✅/❌ |
| 3 | read_file | auto 放行 | … | ✅/❌ |
| 4 | tool_search | auto 放行 | … | ✅/❌ |
| 5 | write_file | requires_confirm 拦截 | … | ✅/❌ |

表格后用两三句话总结：工具是否全部可用、权限门是否生效（只读放行 / 写拦截）。任何一步报错都如实写入表格，不要跳过或粉饰。
