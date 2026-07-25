# 任务：为 manufacturing-agent 的 Runtime 实现「多轮会话滚动摘要压缩」 

> 把本文件作为提示词直接粘贴给 Claude Code 执行即可。所有文件/函数/行号均已核实，无需重新探索。

## 一、目标

当前多轮会话只有两道**硬截断**，没有任何语义压缩：

- `Coordinator` 的滑动窗口 `max_history_messages = 20`（`maestro/src/maestro/runtime/coordinator.py:47`）——窗口外轮次被静默丢弃。
- `ContextProvider` 的字符预算 `max_chars = 16000`（`maestro/src/maestro/bootstrap.py:86`）——超出后走 `_TruncatingSummarizer` 纯尾部裁剪，非语义摘要。

要实现的方案是**增量滚动摘要**：窗口外轮次不是丢弃，而是经大模型摘要后落盘，再回填进系统上下文。要点是「轮次掉出窗口才摘要一次并缓存」，之后复用已存摘要，不每次调用都花钱。

## 二、现有架构（已核实的定位）

- `maestro/src/maestro/runtime/coordinator.py`
  - `Coordinator.__init__` 有 `history_provider: Callable[[str], list[dict]] | None = None`（默认 None）与 `max_history_messages: int = 20`（默认 20），分别在 46-47 行、59-60 行。
  - `_conversation_messages(run)`（431 行）返回 `[*self._session_history(run), {"role": "user", "content": run.objective}]`。
  - `_session_history(run)`（435-451 行）：调用 `history_provider(run.session_id)` 拿全部消息 → 过滤 `role ∈ {user, assistant}` 且 `content` 非空且 `run_id != 当前 run` → 返回 `usable[-self._max_history_messages:]`（只留最后 20 条，更早的静默丢弃）。
  - `_initial_context(run)`（453 行起）用 `ContextItem.from_run(run)` 等拼出系统上下文 items。
- `maestro/src/maestro/runtime/context.py`
  - `ContextProvider(max_chars=...)`（120 行）按 `Priority` 组装 `system_context`：P0 永不被截，P1-P3 超预算走 `_TruncatingSummarizer`（纯尾部裁剪）。
  - `ContextItem`（27 行）、`Priority`（15 行，P0 最高）、`Trust`（22 行）。
- `maestro/src/maestro/foundation/session_store.py`
  - `get_messages(session_id)`（143 行）原样返回磁盘 JSON 消息列表；消息是含 `role/content/run_id` 等字段的 dict。需新增摘要持久化，用**侧车文件**，不要污染 `get_messages` 的返回结构（前端 `/sessions/{id}/messages` 依赖它）。
- `maestro/src/maestro/foundation/llm.py`
  - `LLMClient.complete(system, messages, tools=None, ...)`（137 行）返回纯文本 `str`，**不进 ReAct 循环**，适合做摘要；`self.available` 属性指示是否有 API key（降级判断用）。
- `maestro/src/maestro/bootstrap.py`
  - 86 行 `ContextProvider(max_chars=16_000)`；91 行 `history_provider=session_store.get_messages`。从 Settings 注入窗口大小/摘要开关。
- `maestro/src/maestro/config.py`：Settings 定义处，新增配置项。

## 三、实现方案

### 1. SessionStore 侧车持久化

新增侧车文件 `{sessions_dir}/{session_id}.summary.json`，结构：

```json
{ "summary": "<str>", "summarized_until": <int> }
```

- 新增方法 `get_summary(session_id) -> tuple[str, int]`：文件不存在返回 `("", 0)`。
- 新增方法 `set_summary(session_id, summary: str, summarized_until: int)`：**原子写**（参考现有 `RunStore.save` 的 tmp 文件 + `fsync` + `replace` 写法，见 `maestro/src/maestro/runtime/store.py:60`）。
- **不要改动** `get_messages` 的返回结构/契约。

### 2. Coordinator 改造

- `__init__` 新增：
  - `summary_enabled: bool = True`
  - `session_store: SessionStore | None = None`（或单独的 `summary_store` 引用）
  - `max_history_messages` 改为从外部传入（默认值保持 20，不再硬编码）。
- 在 `_session_history` 中（或抽取一个 `_compact_history` 辅助方法）：
  1. 算出 `usable` 后分 `recent = usable[-N:]`、`stale = usable[:-N]`。
  2. 若 `summary_enabled` 且 `stale` 非空且 `session_store` 可用：
     - 读 `(prior_summary, summarized_until) = session_store.get_summary(session_id)`。
     - 若 `summarized_until < len(stale)`：取新掉出批次 `new_turns = stale[summarized_until:]`，调用  
       `self._llm.complete(SUMMARY_SYSTEM_PROMPT, [{"role": "user", "content": _render_summary_input(prior_summary, new_turns)}])`  
       得到 `new_summary`，写回 `set_summary(session_id, new_summary, len(stale))`；  
       否则（游标已覆盖）**不调 LLM**，直接复用 `prior_summary`。
     - 边界：若 `len(stale) < summarized_until`（如窗口被调大），重置游标从 0 重新摘要。
  3. 把最终 `summary` 作为 `ContextItem(key="conversation-summary", text=summary, priority=Priority.P1, trust=Trust.TRUSTED, source="history")` 收集，供 `_initial_context` 注入 `system_context`。**不要往 `messages` 里塞 `role: system`**（会与 `system_context` 重复 system 角色，交给 `ContextProvider` 走现有 16k 预算更干净，超大自动截断）。
- **容错**：任何 LLM 调用 / IO 异常都要 `catch`，降级为「不摘要、纯窗口」并打 `warning` 日志，**绝不能让 run 失败**；当 `self._llm.available` 为 `False` 时直接跳过摘要。

### 3. config.py 配置项

新增（建议放在 runtime 相关小节）：

```python
history_max_messages: int = 20
summary_enabled: bool = True
```

默认值保证与现状一致。

### 4. bootstrap.py 接线

读取 Settings，把 `max_history_messages=settings.history_max_messages`、`summary_enabled=settings.summary_enabled`、`session_store=session_store` 传给 `Coordinator(...)` 构造；`ContextProvider(max_chars=16_000)` 保持不变。

### 5. 摘要提示词（写进代码常量，中文）

系统 prompt 常量 `SUMMARY_SYSTEM_PROMPT`：

```
你是一个对话压缩器。给定一段【已有摘要】和【本次新增对话】，输出更新后的、简洁且信息密集的完整摘要。
必须保留：用户的目标与意图；已做出的决策及其理由；关键实体与编号（如订单号、工序号、机台名、日期）；未完成的待办与开放问题；用户明确提出的约束或偏好；对后续连续性重要的工具结果。
必须丢弃：寒暄与重复表述、过长的原文逐字引用（改用自己的简述）、工具调用的过程性细节。
只输出更新后的摘要正文，不要任何前缀、不要 markdown 代码块、使用中文。
```

用户消息渲染函数 `_render_summary_input(prior_summary, new_turns)` 输出：

```
[已有摘要]
{prior_summary}

[本次新增对话]
{将 new_turns 按 "角色: 内容" 逐条格式化}

请把【本次新增对话】合并进【已有摘要】，输出更新后的完整摘要。
```

## 四、约束

- **向后兼容**：`summary_enabled=False` 或首次无摘要时，行为必须完全等于现状（最后 20 条、无摘要项），现有会话与测试不受影响。
- **不改 `get_messages` 契约**：前端依赖它的返回结构，摘要必须走侧车文件。
- **复用原子写风格**：侧车文件写入参考 `RunStore.save` 的 tmp + fsync + replace。
- **摘要调用走 `LLMClient.complete`**，不要走 `chat_turn` / ReAct。

## 五、验证

1. 在 `maestro/tests/` 新增 pytest：mock `LLMClient.complete`（回声或拼接），构造一个 session 写入 > 20 条消息，调用 Coordinator 的会话历史拼装，断言：
   - (a) 窗口外更早轮次**不在**最终 messages 中；
   - (b) 这些轮次的关键信息**出现**在注入的 `conversation-summary` ContextItem 里；
   - (c) 第二次调用复用已存摘要、**不再触发 LLM**；
   - (d) `llm.available=False` 时退回纯窗口、不报错。
2. 跑 `cd maestro && pytest` 确保全绿（现有测试全部 mock LLM）。
3. 确认导入链路正常：例如 `python -c "from maestro.bootstrap import build_platform"` 不报错。
4. **不动前端**。

## 六、附录：提交给 Claude Code 的一句话

「请按 `docs/rolling-summary-claudecode-prompt.md` 实现多轮会话滚动摘要压缩：在 SessionStore 加侧车摘要持久化，改造 Coordinator 做增量滚动摘要并注入 system_context，config 加开关，补 pytest，保证向后兼容与降级不阻断 run。」
