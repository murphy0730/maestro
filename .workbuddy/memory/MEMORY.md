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
- **两套工具系统**：① `maestro/tools/`（新框架，含 `builtins/`：filesystem 的 read/write/edit/list_files、search、todo、web、tool_search、sleep、bash 等）；② `maestro/foundation/tools/`（调度/查询引擎实际使用的 `ToolRegistry`）。
- **桥接链路**：`bootstrap.py` 调 `initialize_framework_tools()` + `register_framework_tools(tools, gate)`（见 `tools/bridge.py`），把框架 builtins **桥接进 foundation 共享 registry**（重名跳过，foundation 优先）。
- **引擎级白名单（已更新）**：调度引擎 `scheduling_tools(registry)` = `registry.names()` **全集**（`builtin.py:383`，非旧版 13 个硬编码）；查询引擎用 `QUERY_READONLY_TOOLS`（`builtin.py:395`，只读列表，现含 5 个调度只读 + `search_catalog_skills`/`search_catalog_connectors`）。`AgentLoop` 用 `allowed_tools` 过滤；非 deferred(should_defer=False) 工具会预加载进 `active_tools`，可直接调，无需 tool_search。
- **写工具 + ActionGate 范式**：`async def handler` 内调 `gate.request(action_type, description, params, executor)`，executor 须是 **async 返回 ActionResult**（`execute_claimed` 会 `await executor(params)`）；返回 `_gate_outcome_dict(outcome)`。未知 action_type 在 plan 模式→ask(需确认)、auto 模式→allow。`evaluate_tool` 对工具默认 allow（不阻塞），写操作的实际门控在 handler 的 gate.request。

## 扩展目录工具（SkillHub / 连接器市场）
- `extensions/catalog_tools.py` 提供 4 个工具：`search_catalog_skills`/`search_catalog_connectors`(read)、`install_catalog_skill`/`add_catalog_connector`(write，走 ActionGate)。在 bootstrap 早期（AgentLoop/QueryEngine 构造前）注册；`ExtensionCatalogService.__init__` 接受 `platform=None` 延迟绑定，Platform 构造后回填。
- **find-skills 技能是"查找技能"请求的拦截点**：编排器把"find a skill/查找技能"路由到已安装的 `find-skills` 技能（intent=skill），而非直接进调度/查询引擎。该技能的正文 + `allowed_tools` 决定行为。已把它从"建议 npx skills find"改成用 `search_catalog_skills`。改技能用 `skill_store.replace(meta, body, {})`（同时更新 allowed_tools 与正文，会清信任）。

## 后端重启（venv shebang 仍坏）
- `.venv/bin/uvicorn` shebang 可能仍指向旧路径，**用 `python -m uvicorn` 绕开**：`cd maestro && PRIVILEGED_API_TOKEN=maestro-local-dev PYTHONPATH=src .venv/bin/python -m uvicorn maestro.main:app --port 8000`（用 run_in_background 起后台）。restart.sh 的 `.venv/bin/uvicorn` 方式可能因 shebang 失败且日志为空。
- 重启后 SkillStore 在内存，改技能/工具代码后需重启后端才生效。
