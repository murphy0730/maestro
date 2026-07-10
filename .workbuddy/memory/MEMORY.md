# 项目长期记忆 · manufacturing-agent

- 出稿介质：ardot 设计画布（非代码）。用户偏好"先设计、不改代码"。

## 环境备注 · ardot 设计画布
- 写入适配器偶发 `NO_ADAPTER`（routeKey 固定），read 正常。旧文件编辑器状态可能损坏（fetch_editor_state 报 undefined children、`document`/`0:1` 无法作父节点）。
- **已验证可复用的自愈流程**：先 `open_design(fileId)` 重新挂接适配器 → 再 `create_design` 新建**全新**文档（不要复用坏文件）→ fetch_file_info 确认就绪后即可稳定连续写入。详见 2026-07-09 日记。
- 画布渲染器无 `PingFang SC`，中文会自动回退 `Sarasa Gothic SC`（字重仅 Regular 可用）。
- **后端 venv 现状**：`maestro/.venv` 已存在且依赖齐全（uvicorn 0.49 / fastapi 0.136 可导入）。它从 `scheduling_platform` 工程迁移而来，bin 下 26 个包装脚本的 shebang 曾指向旧路径 `…/scheduling_platform/.venv/bin/python3`，导致 `uvicorn` 启动报 "No such file or directory"。已用 `sed` 批量改为 `maestro/.venv/bin/python3` 修好。若后端再起不来，先查 bin 脚本 shebang 是否指向旧路径。
- **重启前后端**：`bash restart.sh all`（停/起：`restart.sh stop|backend|frontend`）。后端 :8000（uvicorn `maestro.main:app`），前端 :5173（vite）。`nohup … &` 在本机可跨工具调用存活。
- **探活**：本沙箱 `lsof -ti tcp:PORT` 偶发返回空（假阴性），以 `curl` 为准——后端 `http://localhost:8000/docs` → 200，前端 `http://127.0.0.1:5173/` → 200。macOS 无 `setsid`，勿用。

## 架构 · 工具注册与引擎白名单（关键）
- **两套工具系统**：① `maestro/tools/`（新框架，含 `builtins/`：filesystem 的 read/write/edit/list_files、search、todo、web、tool_search、sleep）；② `maestro/foundation/tools/`（调度/查询引擎实际使用的 `ToolRegistry`）。
- **桥接链路**：`bootstrap.py` 行150-151 调用 `initialize_framework_tools()` + `register_framework_tools(tools, gate)`（见 `tools/bridge.py`），把框架 builtins **桥接进 foundation 共享 registry**（重名跳过，foundation 优先）。→ 所以内置工具**确实注册生效了**。
- **引擎级白名单（根因）**：`AgentLoop` 用 `allowed_tools` 白名单过滤——`agent_loop.py` 行142 `to_openai_tools(self._allowed)` 只把白名单工具 schema 发给 LLM，行264/284 双重拦截。调度引擎传的是 `SCHEDULING_TOOLS`（`foundation/tools/builtin.py:369`，仅13个生产调度工具，**不含 write_file 等**）；查询引擎传 `QUERY_READONLY_TOOLS`（5个只读）。
- **结论**：内置文件工具没在调度 agent 生效，不是没注册，而是被 `SCHEDULING_TOOLS` 白名单挡在门外。若要让调度 agent 能写文件 → 把工具名加进 `builtin.py:369 SCHEDULING_TOOLS`；或经「技能」用（技能 `allowed_tools` 可引用桥接工具，走 SkillEngine 而非调度引擎）。
