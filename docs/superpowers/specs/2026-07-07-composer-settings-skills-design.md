# 前台设置项 / 多技能选择 / 会话回读气泡拆分修复 — 设计

日期：2026-07-07
范围：`frontend/`（三块）+ `maestro/`（仅 Feature 2 多技能组合、Feature 3 消息 kind）

三个相互独立的改动，合并为一份 spec，因为都落在 orchestrator 对话 UI 这条线上：

1. 设置菜单二级化（外观 / 默认引擎）
2. 输入框多技能选择 + 可删除芯片（含后端多技能组合）
3. 切换会话回读后一条回答被拆成多个气泡的 bug 修复

---

## Feature 1 — 设置二级菜单（外观 / 默认引擎）

**纯前端。** 现状：设置 Popover（`frontend/src/components/layout/Sidebar.tsx:264`）直接平铺 浅色/深色。

### 目标结构

```
⚙ 设置
 ├─ 外观        ▸   → 浅色 / 深色              (✓ 当前主题)
 └─ 默认引擎    ▸   → 自动 / 排产 / 调度 / 查询  (✓ 当前默认引擎)
```

- 顶层两行各是一个可展开的子菜单入口；点击（或 hover）在其一侧弹出第二级面板，点击叶子项即应用并关闭整个菜单。
- macOS 风格，沿用现有 `Popover` / `PopoverItem` / `PopoverLabel` token，不引入新配色。

### 默认引擎持久化

- 新增 `frontend/src/stores/defaultEngineStore.ts`，**镜像 `themeStore` 的写法**：
  - 类型 `DefaultEngine = 'auto' | 'planning' | 'scheduling' | 'query'`
  - `localStorage` key：`maestro-default-engine`，缺省 `'auto'`
  - `create` 时读初值，`setDefaultEngine` 写 localStorage + set。
- `Workspace` 的 `route` state 初值由 `defaultEngineStore` 提供（替换硬编码 `useState<ComposerRoute>('auto')`）。
- 语义：默认引擎是一条持久化偏好，**用于初始化 Composer 的路由选择器**。改默认引擎会持久化并作为后续会话/刷新的初始路由；不追溯改动当前已在进行中的会话选择器。

### Sidebar props 变更

- 新增 props：`defaultEngine: DefaultEngine`、`onSetDefaultEngine: (e: DefaultEngine) => void`，由 `Workspace` 从 store 注入（与现有 `theme` / `onSetTheme` 同款）。
- Sidebar 内 `settingsOpen` 单态改为可标识当前展开的子菜单（`'appearance' | 'engine' | null`），或用两个入口各自的 hover 态；实现取简单者，保持点击外部关闭逻辑不变。

### 引擎选项元信息

复用 `Composer.tsx` 的 `ROUTE_OPTS`（自动/排产/调度/查询 + dot 颜色 + label）。为避免重复，把 `ROUTE_OPTS` 抽到共享位置（如 `frontend/src/lib/routes.ts` 旁或新建 `composerOptions.ts`），Composer 与 Sidebar 子菜单共用同一份，颜色 dot 与既有 `ROUTE_META` token 一致。

---

## Feature 2 — 多技能芯片 + 后端多技能组合

用户确认：**扩展后端支持多技能组合**（不是纯前端占位）。

### 前端 UX

- `skill: SkillMeta | null` → `skills: SkillMeta[]` 贯穿 `Composer`、`Workspace`、`SkillMenu`。
- `SkillMenu` 改为多选：叶子项点击切换选中（勾选 ✓ 切换），**选中不自动关闭菜单**；"不使用技能" 变为"清空全部"。搜索/导入行为不变。
- 选中的技能以**可删除芯片**渲染在输入框 textarea 上方、composer dock 内部一行（对应用户参考图 1）：每个芯片显示 `display_name`，带 `×` 单独移除。芯片为空时该行不占位。
- 互斥规则保持：选中任一技能 → route 强制回 `auto`；选择非 auto 路由 → 清空所有技能（`handleRouteChange` / `handleSkillChange` 相应改为对数组操作）。
- 发送：`onSend` 携带 `skills.map(s => s.name)`（string[]）。

### 后端多技能组合

- 请求体：`ChatRequest` 与流式请求新增 `skill_ids: list[str] | None`。**保留** `skill_id: str | None` 向后兼容——存在时并入为单元素列表（`skill_ids = skill_ids or ([skill_id] if skill_id else None)`）。
- `Orchestrator.handle` / `stream` 分支条件由 `skill_id is not None` 改为 `skill_ids`（非空列表）时跳过路由，构造 `RouteDecision(intent="skill", skill_ids=[...])`。
- `RouteDecision`：`skill_id: str | None` → 增加 `skill_ids: list[str]`（或以 `skill_ids` 为准，`skill_id` 保留为 `skill_ids[0]` 便捷属性以少改审计/日志）。审计记录全部 skill_ids。
- `SkillEngine.handle` 接受 `skill_ids: list[str]`：
  - 逐个 `store.get(id)`，任一不存在 → 与现有"不存在"同口径收口。
  - `source == "user"` 时**每个**技能都需 `user_invocable`，否则拒绝并点名不支持手动指定的技能。
  - `allowed`：所有 `meta.allowed_tools` 的**并集**；任一 `file_count > 0` 则追加 `read_skill_file`。
  - `extra`（tool_preconditions）：按工具名**合并**各技能的命名断言列表（并集，去重）。
  - `body`：按选中顺序拼接各技能 SKILL.md 正文，加带 `display_name` 的分隔标题；`SKILL_PREAMBLE` 只加一次在最前。
  - 单次 `AgentLoop.run`。返回 `data.steps` 不变；可在 `data` 附 `skill_ids` 便于前端/调试。
- `_dispatch` 中 `intent == "skill"` 分支改为传 `decision.skill_ids`。

### 兼容与降级

- LLM 未配置：与现有单技能一致，返回"技能暂不可用"。
- 只选一个技能：走同一多技能路径（列表长度 1），行为等价于旧单技能。

---

## Feature 3 — 会话回读气泡拆分修复

### 根因（已确认）

一轮对话在后端持久化为：
1. `_finish` → `memory.append(session_id, "assistant", resp.reply)`（主回答，一条）
2. `orchestrator.confirm()` → `memory.append(session_id, "assistant", "已执行: …")`（每个动作确认结果，各一条）

实时：主回答是 agent 气泡，确认结果由前端 `confirmPending` 以 `kind:'system'`（居中细行）渲染。
回读：`storedToThread`（`frontend/src/pages/Workspace.tsx:107`）把所有非 user 消息一律映射为整块 `agent` 气泡 → 一条逻辑回答在回读后变成 2~3 个堆叠的 Maestro 气泡。

### 修复方案（后端 kind 字段，已选定）

- `StoredMessage`（`maestro/.../foundation/session_store.py:26`）新增 `kind: str = "normal"`。
- `SessionStore.append_message` 与 `ConversationMemory.append` 增加可选 `kind: str = "normal"` 参数，透传落盘。
- `orchestrator.confirm()` 的结果 append 传 `kind="system"`。其余 `append` 不传（默认 `"normal"`）。
- `GET /sessions/{id}/messages` 返回体每条带上 `kind`（`StoredMessage` 序列化即含）。
- 前端 `StoredMessage` 类型（`frontend/src/api/sessions.ts`）加 `kind?: 'normal' | 'system'`。
- `storedToThread`：`role === 'user'` → `user`；`kind === 'system'` → `system`；否则 → `agent`。

### 已知局限（本次不处理，除非另行要求）

回读的主回答是纯文本气泡——route badge、thinking log、pending-action 卡片均未持久化，故不重现。此为既有限制，与本 bug（拆分）正交。

### 旧数据兼容

历史已落盘消息无 `kind` 字段 → pydantic 默认 `"normal"` → 旧的确认结果仍显示为 agent 气泡（不回溯修复），新产生的会话正确。可接受。

---

## 影响文件清单

**前端**
- `stores/defaultEngineStore.ts`（新）、`stores/index.ts`（导出）
- `components/layout/Sidebar.tsx`（二级菜单 + 新 props）
- `pages/Workspace.tsx`（route 初值来自 store、skills 数组、storedToThread kind）
- `features/orchestrator/Composer.tsx`（多技能芯片行、skills 数组）
- `features/orchestrator/skills/SkillMenu.tsx`（多选）
- `lib/routes.ts` 或新 `composerOptions.ts`（共享引擎选项）
- `api/sessions.ts`（StoredMessage.kind）
- `api/useStreamingChat.ts`（skill_ids）
- 相关 `types`

**后端**
- `foundation/session_store.py`（StoredMessage.kind、append_message kind）
- `foundation/memory.py`（append kind 透传）
- `orchestrator/orchestrator.py`（skill_ids 分支、RouteDecision、confirm kind）
- `orchestrator/…`（RouteDecision schema）
- `skills/engine.py`（handle 接受 skill_ids、组合逻辑）
- `main.py`（ChatRequest.skill_ids、stream 请求、dispatch 传递）
- `docs/api-contract/api-contract-v2.md`（skill_ids、messages.kind）

**测试**
- 后端：多技能组合（allowed 并集/body 拼接/user_invocable 全员校验）、confirm 落盘 kind、messages 返回 kind。
- 前端：SkillMenu 多选、芯片删除、storedToThread kind 映射、默认引擎 store。

---

## 验收标准

1. 设置菜单出现"外观"与"默认引擎"两个二级入口；选默认引擎后刷新页面，输入框路由选择器复现该引擎。
2. 可在输入框选中多个技能，各以带 × 的芯片显示并可单独删除；发送后端以合并的 allowed_tools + 拼接 body 单次 AgentLoop 运行（单技能行为不回归）。
3. 执行含动作确认的会话后切走再切回，主回答为单一气泡，确认结果为居中 system 细行，不再拆成多个 Maestro 气泡。
4. `pytest` 与 `npm test` / `npm run lint` 全绿。
