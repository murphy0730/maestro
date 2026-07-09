# 任务：补全工具调用链中缺失 / 偏弱的能力（对齐 Claude Code）

> 可直接整段复制，粘贴进 Claude Code（在仓库根目录 `manufacturing-agent/` 启动）执行。

## 背景

我们的 Agent 工具调用链由以下文件实现：
- `maestro/src/maestro/engines/scheduling/agent_loop.py` —— 主循环 `_step()` / `_handle_call()` / `run()`
- `maestro/src/maestro/foundation/tools/registry.py` —— `ToolRegistry.execute(name, arguments)`（@92），实际 `handler(**args)`
- `maestro/src/maestro/foundation/authz.py` —— `ActionGate.request()`（@95），写操作授权（auto / pending / deny）

当前链路已完整（含白名单、去重、写后清读、8KB 截断、PendingActionStore 快照等），但相比 Claude Code 的工具调用链，有 **5 项能力缺失或偏弱**。请在**不破坏现有行为**的前提下补齐这 5 项。改动时务必保留：白名单拦截、绕圈去重 `seen`、写操作后清读 `seen`、8KB 截断、`ActionGate` 写操作授权、`PendingActionStore` 快照差集。

---

## 1. 泛型输入校验（对齐 Claude Code ④ `validateInput`）

**当前**：仅写操作在 `_handle_call` 内走 `tool.precondition(args)` 断言；读 / 中性工具没有统一的输入校验层。

**目标**：在 `_handle_call` 入口（白名单、去重之后，执行之前）增加一层**泛型输入校验**：
- 每个工具声明其 `input schema`（建议 JSON Schema 或 Pydantic model，可复用已有的工具定义）；
- 校验失败时**不执行**该工具，直接生成一个错误 `observation`（对齐 Claude 返回的错误 `tool_result`），并把该 `tool_call` 标记为失败、跳过；
- 复用现有 `seen` 去重与白名单逻辑，不要改动它们的位置与顺序。

**验收**：对一个声明了 schema 的工具传入非法参数时，链路返回错误 observation 而非崩溃或静默放行。

---

## 2. 实时进度回调（对齐 Claude Code ⑦ `onProgress`）

**当前**：`ToolRegistry.execute(name, args)` → `handler(**args)` 执行期间没有流式进度，长任务时 UI 静止。

**目标**：
- 给 `handler` / 工具执行增加 `on_progress(callback)` 钩子；
- 在 `registry.execute` 与具体 action 执行中，按阶段 emit 进度事件（如 `started` / `progress(pct, message)` / `done`）；
- 保持对现有同步调用**向后兼容**：不传 callback 时退化为同步、零开销。

**验收**：在 `registry.execute` 中打印 / 记录一次 `progress` 事件，确认长任务期间能被外部订阅。

---

## 3. 多工具并发执行（对齐 Claude Code ② `StreamingToolExecutor.runTools`）

**当前**：一轮 LLM 返回的多个 `tool_call` 在 `_step()` 内逐条 `_handle_call()` 串行处理。

**目标**：
- 对相互**无写依赖**的 `tool_call` 做并发执行（`asyncio.gather` 或线程池）；
- 写操作 / 有状态依赖的保持串行或加锁；
- 注意并发下的 `seen` 去重计数与 `ActionGate` 的竞争条件（建议加锁或先收集再并发调度）。

**验收**：一轮返回 3 个独立只读 `tool_call` 时，日志记录它们并发启动（非严格串行）。

---

## 4. 交互式权限确认（对齐 Claude Code ⑤ `canUseTool`）

**当前**：仅写操作走 `ActionGate.request(pending)` 询问用户；读 / 中性工具默认放行，没有通用的"询问用户确认"交互层。

**目标**：抽出**通用 `can_use_tool(name, args)` 拦截层**，位于白名单之后、执行之前：
- 对所有工具（含读 / 中性）提供"询问用户确认"的交互入口；
- `pending` 时**挂起**该 `tool_call` 并返回 pending 状态，而非默认通过；
- 用户拒绝时生成**拒绝 `observation`**（对齐 Claude 的拒绝 `tool_result`）。
- **不要破坏**现有写操作的 `ActionGate` 流程，应是在其之上叠加一层通用确认。

**验收**：对一个读工具配置为"需确认"时，链路进入 pending 挂起而非直接执行。

---

## 5. 独立规则权限引擎（对齐 Claude Code ⑥ `checkPermissions`）

**当前**：权限规则与写操作耦合在 `authz.py` 的 `ActionGate` 内部。

**目标**：从 `ActionGate` 中抽出**独立的权限规则引擎**，输出三态：`allow` / `deny` / `ask`：
- 对读 / 写 / 中性工具**统一评估**；
- `ActionGate` 仍作为写操作的具体执行闸门，但**决策来源**改为调用这个统一引擎；
- 提升可配置性与可审计性（规则尽量可外部配置 / 集中声明）。

**验收**：新增一条 deny 规则（例如拒绝某读工具）后，该工具被拦截，且决策来自统一引擎而非硬编码在 `ActionGate` 内。

---

## 验收总要求
1. 现有行为**不被破坏**（白名单、去重、写后清读、8KB 截断、PendingActionStore 快照均保持）；
2. 每一项都有**最小可用实现** + 至少一处日志 / 测试示例证明其生效；
3. 完成后用一段话简述每处**改动的文件与函数名**，以及是否引入了新文件。
