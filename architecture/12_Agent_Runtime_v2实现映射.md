# Agent Runtime v2 实现映射

本文记录 `01`—`11` 设计文档在代码中的落点，避免后续维护重新引入两套事实源。

| 设计关注点 | 实现位置 | 持久化事实 |
|---|---|---|
| Agent 定义与冻结前缀 | `runtime/definition.py`、`agent_definitions/maestro.yaml` | `agent_session.prefix_text/prefix_hash` |
| Run 循环与状态所有权 | `runtime/agent.py` | `agent_run` + `RUN_STATUS_CHANGED` |
| Event / Trajectory | `runtime/trajectory.py` | `agent_event`，Session 内 sequence 单调递增 |
| Checkpoint / 压缩 | `runtime/checkpointing.py` | `session_checkpoint` lineage |
| Context Budget | `runtime/session_context.py` | `model_turn` / `ContextManifest` |
| Tool / MCP 懒加载 | `runtime/resolver.py`、`runtime/meta_tools.py` | `tool_definition` + FTS5、Run 版本 pin |
| Skill 三层加载 | `runtime/skills.py`、`runtime/agent.py` | `skill_definition`、Run 仅保留版本/参数/权限 |
| RAG / Memory / Evidence | `extensions/retrieval.py` | knowledge/memory FTS5、evidence/evidence_usage |
| StatusBar / 轨迹控制 | `runtime/status.py` | 从 Checkpoint、Plan 与 hot events 投影 |
| SQLite 数据层 | `foundation/sqlite_store.py` | `$MAESTRO_DATA_DIR/runtime-v2/maestro.db` |
| 调试 / Replay | `api/routes/v2.py`、`frontend/src/pages/RuntimeDebug.tsx` | Debug API 只读投影与一致性报告 |

关键边界：

1. `runtime/` 不包含排产、齐套、派工或检索业务逻辑；领域身份在 Agent Definition，能力由宿主注册。
2. 所有 Capability 调用都经过 `PolicyGate`；高风险写入审批绑定 Tool/schema/arguments/version/Run revision/外部状态 token。
3. 模型只能看到核心能力和已由 `tool_search` 固定版本的候选；Skill 只能收窄权限。
4. 原始 ToolResult 只存一份；Event、Context 与最终 Evidence 使用引用和有界摘要。
5. v2 不迁移 v1 JSON 数据。兼容代码不得承载新行为。
