# 设置二级菜单 / 多技能芯片 / 会话回读气泡拆分修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 前台设置增加"默认引擎"二级菜单、输入框支持多技能芯片选择（含后端多技能组合）、修复切换会话回读后一条回答被拆成多个气泡的 bug。

**Architecture:** 三块相互独立。① 设置菜单在 Sidebar 内做单面板 drill-in（root → 外观/默认引擎子视图）；默认引擎经 `defaultEngineStore`（localStorage）持久化并初始化 Composer 路由。② 技能选择由单选改多选：前端芯片行 + `skill_ids` 贯穿 API/orchestrator，`SkillEngine.handle` 接受技能列表并合并 allowed_tools/tool_preconditions/正文，单次 AgentLoop 运行。③ 会话消息新增 `kind` 字段，确认结果落盘为 `kind="system"`，回读时映射为 system 细行。

**Tech Stack:** 后端 Python 3.12 / FastAPI / pytest；前端 React 18 / TypeScript / Zustand / TanStack Query / vitest + RTL。

## Global Constraints

- 包名是 `maestro`，不是 `platform`。
- 后端测试全程 mock LLM，无网络；用 `conftest.FakeLLM`。
- 前端颜色只用语义 token（`bg-planning`、`text-text-tertiary` 等），禁止裸 hex。
- `npm run lint` 为 `--max-warnings 0`，不得留 warning。
- 向后兼容：后端保留 `skill_id` 单值字段（存在时并入 `skill_ids`）；已落盘旧消息无 `kind` → 默认 `"normal"`，不回溯。
- 每个 Task 结束提交一次，message 用中文 + `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。

---

## 文件结构

**后端**
- `maestro/src/maestro/foundation/session_store.py` — `StoredMessage.kind`、`append_message(kind=...)`
- `.../foundation/memory.py` — `append(..., kind="normal")` 透传
- `.../orchestrator/schemas.py` — `RouteDecision.skill_ids`
- `.../skills/engine.py` — `SkillEngine.handle(skill_ids: list[str], ...)` + 合并逻辑
- `.../orchestrator/orchestrator.py` — `handle(skill_ids=...)`、skill 分支、`_dispatch`、`confirm` 落盘 `kind="system"`
- `.../main.py` — `ChatRequest.skill_ids`、`ChatStreamRequest.skill_ids`、两处 handle 调用

**前端**
- `frontend/src/stores/defaultEngineStore.ts`（新）+ `stores/index.ts` 导出
- `frontend/src/features/orchestrator/history.ts`（新，抽出 `storedToThread` 纯函数）+ `history.test.ts`
- `frontend/src/api/sessions.ts` — `StoredMessage.kind`
- `frontend/src/api/useStreamingChat.ts` — `send(skillIds)` → `skill_ids`
- `frontend/src/features/orchestrator/useOrchestrator.ts` — `send(skillIds)`
- `frontend/src/features/orchestrator/skills/SkillMenu.tsx` — 多选
- `frontend/src/features/orchestrator/Composer.tsx` — 芯片行 + skills 数组
- `frontend/src/components/layout/Sidebar.tsx` — 设置 drill-in 二级菜单
- `frontend/src/pages/Workspace.tsx` — route 初值来自 store、skills 数组、用 `history.ts`

---

## Task 1: 后端消息 kind 字段（修复 Feature 3 数据层）

**Files:**
- Modify: `maestro/src/maestro/foundation/session_store.py`（`StoredMessage` ~26、`append_message` ~115）
- Modify: `maestro/src/maestro/foundation/memory.py`（`append` ~45）
- Modify: `maestro/src/maestro/orchestrator/orchestrator.py`（`confirm` 尾部 `_memory.append`）
- Test: `maestro/tests/test_sessions.py`

**Interfaces:**
- Produces: `StoredMessage(role, content, ts, kind="normal")`；`SessionStore.append_message(session_id, role, content, kind="normal")`；`ConversationMemory.append(session_id, role, content, kind="normal")`。

- [ ] **Step 1: 写失败测试**

在 `maestro/tests/test_sessions.py` 末尾追加：

```python
def test_append_message_kind_default_and_system(tmp_path):
    store = SessionStore(tmp_path)
    meta = store.create()
    store.append_message(meta.session_id, "assistant", "主回答")
    store.append_message(meta.session_id, "assistant", "已执行: 派工 — ok", kind="system")
    msgs = store.get_messages(meta.session_id)  # list[dict]
    assert msgs[0]["kind"] == "normal"
    assert msgs[1]["kind"] == "system"


def test_memory_append_passes_kind(tmp_path):
    store = SessionStore(tmp_path)
    meta = store.create()
    mem = ConversationMemory(store)
    mem.append(meta.session_id, "assistant", "确认结果", kind="system")
    assert store.get_messages(meta.session_id)[0]["kind"] == "system"
```

> `SessionStore(base_dir)` 构造为位置参数，`create()` 标题可省，`get_messages` 返回 `list[dict]`（故断言用 `msgs[i]["kind"]`），`ConversationMemory(store)` 位置参数——均对齐 `test_store_roundtrip_and_auto_title` / `test_memory_rehydrates_after_restart`。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd maestro && pytest tests/test_sessions.py::test_append_message_kind_default_and_system -v`
Expected: FAIL（`StoredMessage` 无 `kind` / `append_message` 不接受 `kind`）

- [ ] **Step 3: 实现**

`session_store.py` — `StoredMessage` 增加字段：

```python
class StoredMessage(BaseModel):
    role: str   # "user" | "assistant" | "system"
    content: str
    ts: str
    kind: str = "normal"   # "normal" | "system"（system=动作确认结果等细行）
```

`session_store.py` — `append_message` 签名与构造：

```python
    def append_message(self, session_id: str, role: str, content: str, kind: str = "normal") -> None:
        with self._lock:
            msg_file = self._msg_file(session_id)
            messages = (
                json.loads(msg_file.read_text(encoding="utf-8")) if msg_file.exists() else []
            )
            msg = StoredMessage(role=role, content=content, ts=self._now(), kind=kind)
            messages.append(msg.model_dump())
            msg_file.write_text(
                json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            if session_id not in self._sessions:
                return
            meta = self._sessions[session_id]
            meta.message_count = len(messages)
            meta.updated_at = self._now()
```

`memory.py` — `append` 透传：

```python
    def append(self, session_id: str, role: str, content: str, kind: str = "normal") -> None:
        self.get(session_id).history.append({"role": role, "content": content})
        if self._store:
            self._store.append_message(session_id, role, content, kind=kind)
```

`orchestrator.py` — `confirm` 尾部落盘改为 system：

```python
        self._memory.append(session_id, "assistant", reply, kind="system")
        return ChatResponse(reply=reply, pending_actions=[action])
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd maestro && pytest tests/test_sessions.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 回归**

Run: `cd maestro && pytest -q`
Expected: 全绿（`history` 字典仍只含 role/content，未受影响）

- [ ] **Step 6: 提交**

```bash
git add maestro/src/maestro/foundation/session_store.py \
        maestro/src/maestro/foundation/memory.py \
        maestro/src/maestro/orchestrator/orchestrator.py \
        maestro/tests/test_sessions.py
git commit -m "feat(session): StoredMessage.kind，确认结果落盘为 system 细行

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: 前端回读映射 kind（修复 Feature 3 展示层）

**Files:**
- Create: `frontend/src/features/orchestrator/history.ts`
- Create: `frontend/src/features/orchestrator/history.test.ts`
- Modify: `frontend/src/api/sessions.ts`（`StoredMessage`）
- Modify: `frontend/src/pages/Workspace.tsx`（删除内联 `storedToThread`，改 import）

**Interfaces:**
- Consumes: `StoredMessage` from `@/api/sessions`（现加 `kind?`）。
- Produces: `storedToThread(stored: StoredMessage[]): ChatMessageData[]`（`@/features/orchestrator/history`）。

- [ ] **Step 1: 扩展 StoredMessage 类型**

`frontend/src/api/sessions.ts`：

```ts
export interface StoredMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  ts: string;
  kind?: 'normal' | 'system';
}
```

- [ ] **Step 2: 写失败测试**

`frontend/src/features/orchestrator/history.test.ts`：

```ts
import { describe, expect, it } from 'vitest';
import { storedToThread } from './history';
import type { StoredMessage } from '@/api/sessions';

const msg = (over: Partial<StoredMessage>): StoredMessage => ({
  role: 'assistant',
  content: 'x',
  ts: '2026-07-07T12:00:00Z',
  ...over,
});

describe('storedToThread', () => {
  it('空列表只返回欢迎系统消息', () => {
    const t = storedToThread([]);
    expect(t).toHaveLength(1);
    expect(t[0].kind).toBe('system');
  });

  it('user→user，assistant(normal)→agent，assistant(system)→system', () => {
    const t = storedToThread([
      msg({ role: 'user', content: '派工 WO-1' }),
      msg({ role: 'assistant', content: '主回答', kind: 'normal' }),
      msg({ role: 'assistant', content: '已执行: 派工 — ok', kind: 'system' }),
    ]);
    // t[0] 是欢迎系统消息
    expect(t[1].kind).toBe('user');
    expect(t[2].kind).toBe('agent');
    expect(t[3].kind).toBe('system');
    expect(t[3].text).toBe('已执行: 派工 — ok');
  });

  it('缺省 kind 视为 normal→agent', () => {
    const t = storedToThread([msg({ role: 'assistant', content: '旧数据' })]);
    expect(t[1].kind).toBe('agent');
  });
});
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd frontend && npm test -- history.test.ts`
Expected: FAIL（`./history` 不存在）

- [ ] **Step 4: 实现 history.ts**

`frontend/src/features/orchestrator/history.ts`：

```ts
import type { ChatMessageData } from '@/types';
import type { StoredMessage } from '@/api/sessions';

const WELCOME: ChatMessageData = {
  id: 'sys-welcome',
  kind: 'system',
  text: '新会话 · 在下方描述排产 / 调度 / 查询需求开始',
};

/** 把后端 StoredMessage 列表转为前端 ChatMessageData。
 *  role=user→user；kind=system→system（居中细行）；其余→agent。 */
export function storedToThread(stored: StoredMessage[]): ChatMessageData[] {
  if (stored.length === 0) return [WELCOME];
  return [
    WELCOME,
    ...stored.map((m, i): ChatMessageData => {
      const time = m.ts
        ? new Date(m.ts).toLocaleTimeString('en-GB').slice(0, 5)
        : undefined;
      if (m.role === 'user') return { id: `hist-${i}`, kind: 'user', text: m.content, time };
      if (m.kind === 'system') return { id: `hist-${i}`, kind: 'system', text: m.content };
      return { id: `hist-${i}`, kind: 'agent', text: m.content, time };
    }),
  ];
}
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd frontend && npm test -- history.test.ts`
Expected: PASS

- [ ] **Step 6: Workspace 改用 history.ts**

在 `frontend/src/pages/Workspace.tsx`：删除内联的 `storedToThread` useCallback（当前 106–126 行），顶部加 `import { storedToThread } from '@/features/orchestrator/history';`，并把 `loadSession` 里的 `storedToThread(stored)` 保持不变（现在指向 import 的纯函数）。同时把 `storedToThread` 从 `loadSession` 的依赖数组移除（改为空/仅 `resetThread`）。移除因删除而不再使用的 import（若 `ChatMessageData` 仅此处用则清理）。

- [ ] **Step 7: 类型 + lint + 测试**

Run: `cd frontend && npm run build && npm run lint && npm test -- history.test.ts`
Expected: tsc 通过、lint 0 warning、测试 PASS

- [ ] **Step 8: 提交**

```bash
git add frontend/src/features/orchestrator/history.ts \
        frontend/src/features/orchestrator/history.test.ts \
        frontend/src/api/sessions.ts frontend/src/pages/Workspace.tsx
git commit -m "fix(orchestrator): 回读按 kind 映射，确认结果不再拆成独立 Maestro 气泡

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: 默认引擎 store（Feature 1 数据层）

**Files:**
- Create: `frontend/src/stores/defaultEngineStore.ts`
- Create: `frontend/src/stores/defaultEngineStore.test.ts`
- Modify: `frontend/src/stores/index.ts`

**Interfaces:**
- Produces: `useDefaultEngineStore` → `{ defaultEngine: DefaultEngine; setDefaultEngine(e: DefaultEngine): void }`；`type DefaultEngine = 'auto' | 'planning' | 'scheduling' | 'query'`。localStorage key `maestro-default-engine`。

- [ ] **Step 1: 写失败测试**

`frontend/src/stores/defaultEngineStore.test.ts`：

```ts
import { afterEach, describe, expect, it } from 'vitest';
import { useDefaultEngineStore } from './defaultEngineStore';

afterEach(() => localStorage.clear());

describe('defaultEngineStore', () => {
  it('缺省为 auto', () => {
    expect(useDefaultEngineStore.getState().defaultEngine).toBe('auto');
  });

  it('setDefaultEngine 写入 localStorage 并更新 state', () => {
    useDefaultEngineStore.getState().setDefaultEngine('scheduling');
    expect(useDefaultEngineStore.getState().defaultEngine).toBe('scheduling');
    expect(localStorage.getItem('maestro-default-engine')).toBe('scheduling');
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npm test -- defaultEngineStore.test.ts`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现（镜像 themeStore）**

`frontend/src/stores/defaultEngineStore.ts`：

```ts
import { create } from 'zustand';

export type DefaultEngine = 'auto' | 'planning' | 'scheduling' | 'query';

const STORAGE_KEY = 'maestro-default-engine';
const VALID: DefaultEngine[] = ['auto', 'planning', 'scheduling', 'query'];

/** 读取初始默认引擎：localStorage 优先，缺省 auto。 */
function readInitial(): DefaultEngine {
  const saved = localStorage.getItem(STORAGE_KEY) as DefaultEngine | null;
  return saved && VALID.includes(saved) ? saved : 'auto';
}

interface DefaultEngineState {
  defaultEngine: DefaultEngine;
  setDefaultEngine: (engine: DefaultEngine) => void;
}

export const useDefaultEngineStore = create<DefaultEngineState>((set) => ({
  defaultEngine: readInitial(),
  setDefaultEngine: (engine) => {
    localStorage.setItem(STORAGE_KEY, engine);
    set({ defaultEngine: engine });
  },
}));
```

- [ ] **Step 4: 导出**

`frontend/src/stores/index.ts` 追加：

```ts
export { useDefaultEngineStore } from './defaultEngineStore';
export type { DefaultEngine } from './defaultEngineStore';
```

- [ ] **Step 5: 跑测试 + lint**

Run: `cd frontend && npm test -- defaultEngineStore.test.ts && npm run lint`
Expected: PASS、lint 0 warning

- [ ] **Step 6: 提交**

```bash
git add frontend/src/stores/defaultEngineStore.ts \
        frontend/src/stores/defaultEngineStore.test.ts frontend/src/stores/index.ts
git commit -m "feat(settings): defaultEngineStore 持久化默认引擎

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: 设置二级菜单 + Workspace 接入（Feature 1 UI）

**Files:**
- Modify: `frontend/src/components/layout/Sidebar.tsx`
- Modify: `frontend/src/pages/Workspace.tsx`

**Interfaces:**
- Consumes: `useDefaultEngineStore`（Task 3）；`ComposerRoute`（`@/types`，与 `DefaultEngine` 同集合）。
- Produces: Sidebar 新增 props `defaultEngine: DefaultEngine`、`onSetDefaultEngine: (e: DefaultEngine) => void`。

- [ ] **Step 1: Sidebar 增加引擎选项常量与 props**

`Sidebar.tsx` 顶部 import 加 `Sparkles`（自动）、`CalendarCog`、`GitBranch`、`Search`、`ChevronRight`、`ChevronLeft`（lucide-react），并从 `@/stores` 引 `DefaultEngine` 类型。props interface 增加：

```ts
  defaultEngine: DefaultEngine;
  onSetDefaultEngine: (engine: DefaultEngine) => void;
```

在组件文件内（`Sidebar` 函数外）定义本地选项常量（避免跨 layer 依赖 Composer）：

```tsx
const ENGINE_OPTS: { value: DefaultEngine; label: string; dot: string }[] = [
  { value: 'auto', label: '自动', dot: 'bg-accent' },
  { value: 'planning', label: '排产', dot: 'bg-planning' },
  { value: 'scheduling', label: '调度', dot: 'bg-scheduling' },
  { value: 'query', label: '查询', dot: 'bg-query' },
];
```

- [ ] **Step 2: 设置面板改为 drill-in 单面板**

把 `Sidebar` 里 `const [settingsOpen, setSettingsOpen] = useState(false);` 下面加：

```tsx
  const [settingsView, setSettingsView] = useState<'root' | 'appearance' | 'engine'>('root');
```

在关闭设置菜单的 `useEffect`（`if (!settingsOpen) return;` 那段）里，把 `setSettingsOpen(false)` 处同时重置视图：外部点击时 `setSettingsOpen(false); setSettingsView('root');`。并在打开按钮 `onClick={() => setSettingsOpen(v => !v)}` 改为：

```tsx
onClick={() => { setSettingsOpen((v) => !v); setSettingsView('root'); }}
```

替换现有 `{settingsOpen && (<Popover ...>…外观…</Popover>)}` 整块为：

```tsx
{settingsOpen && (
  <Popover className="absolute bottom-[38px] right-0 w-[200px]">
    {settingsView === 'root' && (
      <>
        <PopoverLabel>设置</PopoverLabel>
        <PopoverItem
          icon={<Sun size={15} />}
          trailing={<ChevronRight size={14} className="flex-none text-text-tertiary" />}
          onClick={() => setSettingsView('appearance')}
        >
          外观
        </PopoverItem>
        <PopoverItem
          icon={<Sparkles size={15} />}
          trailing={<ChevronRight size={14} className="flex-none text-text-tertiary" />}
          onClick={() => setSettingsView('engine')}
        >
          默认引擎
        </PopoverItem>
      </>
    )}

    {settingsView === 'appearance' && (
      <>
        <PopoverItem
          icon={<ChevronLeft size={14} />}
          onClick={() => setSettingsView('root')}
        >
          外观
        </PopoverItem>
        {[
          { value: 'light' as const, label: '浅色', Icon: Sun },
          { value: 'dark' as const, label: '深色', Icon: Moon },
        ].map(({ value, label, Icon }) => (
          <PopoverItem
            key={value}
            icon={<Icon size={15} />}
            trailing={theme === value ? <Check size={14} className="flex-none text-accent-fg" /> : undefined}
            onClick={() => { onSetTheme(value); setSettingsOpen(false); setSettingsView('root'); }}
          >
            {label}
          </PopoverItem>
        ))}
      </>
    )}

    {settingsView === 'engine' && (
      <>
        <PopoverItem
          icon={<ChevronLeft size={14} />}
          onClick={() => setSettingsView('root')}
        >
          默认引擎
        </PopoverItem>
        {ENGINE_OPTS.map(({ value, label, dot }) => (
          <PopoverItem
            key={value}
            icon={<span className={`h-[7px] w-[7px] rounded-full ${dot}`} />}
            trailing={defaultEngine === value ? <Check size={14} className="flex-none text-accent-fg" /> : undefined}
            onClick={() => { onSetDefaultEngine(value); setSettingsOpen(false); setSettingsView('root'); }}
          >
            {label}
          </PopoverItem>
        ))}
      </>
    )}
  </Popover>
)}
```

> `PopoverItem` 的 `icon`/`trailing` 见现有用法；若 `icon` 需要 ReactNode 而非仅图标组件，上面 `<span dot>` 直接作为 node 传入即可。如 `PopoverItem` 不支持任意 node icon，则改用现有 dot 呈现方式（参考会话行 `h-[6px] w-[6px] rounded-full`）。

- [ ] **Step 3: Workspace 注入 defaultEngine + 初始化 route**

`Workspace.tsx`：
- import 增加 `useDefaultEngineStore`（从 `@/stores`）。
- 读取：`const defaultEngine = useDefaultEngineStore((s) => s.defaultEngine);` 和 `const setDefaultEngine = useDefaultEngineStore((s) => s.setDefaultEngine);`。
- 把 `const [route, setRoute] = useState<ComposerRoute>('auto');` 改为 `const [route, setRoute] = useState<ComposerRoute>(defaultEngine);`（`DefaultEngine` 与 `ComposerRoute` 同集合，类型兼容）。
- `<Sidebar ... />` 传入 `defaultEngine={defaultEngine}` 和 `onSetDefaultEngine={setDefaultEngine}`。

- [ ] **Step 4: 类型 + lint + 现有前端测试**

Run: `cd frontend && npm run build && npm run lint && npm test`
Expected: tsc 通过、lint 0 warning、既有测试全绿

- [ ] **Step 5: 手动核对（可选，subagent 跳过）**

`npm run dev` → 点左下设置：出现"外观 ›""默认引擎 ›"两项；进"默认引擎"选"调度"，刷新页面后输入框路由芯片显示"调度"。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/components/layout/Sidebar.tsx frontend/src/pages/Workspace.tsx
git commit -m "feat(settings): 设置二级菜单（外观/默认引擎），默认引擎初始化输入框路由

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: SkillEngine 多技能组合（Feature 2 后端核心）

**Files:**
- Modify: `maestro/src/maestro/skills/engine.py`（`handle` 签名 + 合并）
- Modify: `maestro/tests/test_skill_routing.py`（更新既有 `handle` 调用 + 新增多技能用例）

**Interfaces:**
- Produces: `SkillEngine.handle(skill_ids: list[str], message: str, session_id: str, history=None, on_progress=None, source="user") -> EngineResponse`。`EngineResponse.data` 含 `skill_ids: list[str]`。

- [ ] **Step 1: 更新既有 handle 调用为列表**

在 `tests/test_skill_routing.py` 里，把所有 `e.handle("cap", ...)` / `e.handle("nope", ...)` / `p.skill_engine.handle("nope", ...)` 的首参包成列表：`e.handle(["cap"], ...)`、`e.handle(["nope"], ...)`、`p.skill_engine.handle(["nope"], ...)`。共 6 处（`test_skill_engine_not_found`、`_llm_unavailable`、`_executes`、`_precondition_blocks`、`_dir_removed_friendly`、`_user_invocable_enforced`、`test_bootstrap_wires_skill_engine`）。

- [ ] **Step 2: 写多技能失败测试**

在 `test_skill_routing.py` 的 SkillEngine 段末尾追加：

```python
async def test_skill_engine_multi_not_found(tmp_path):
    e = _engine(tmp_path, FakeLLM(chat_script=["x"]))
    _seed(e._store, "a", allowed_tools=[])
    r = await e.handle(["a", "missing"], "msg", "s1")
    assert "不存在" in r.reply


async def test_skill_engine_multi_user_invocable_blocks_offender(tmp_path):
    e = _engine(tmp_path, FakeLLM(chat_script=["结论"]))
    _seed(e._store, "a", allowed_tools=[])
    _seed(e._store, "b", allowed_tools=[], user_invocable=False, display_name="仅路由技能")
    r = await e.handle(["a", "b"], "msg", "s1")  # source=user
    assert "仅路由技能" in r.reply and "不支持手动指定" in r.reply


async def test_skill_engine_multi_unions_allowed_tools(tmp_path):
    # a 无工具、b 有 query_orders；合并后 query_orders 可用（不被白名单拒绝）
    e = _engine(tmp_path, FakeLLM(chat_script=[[("query_orders", {})], "结论"]))
    _seed(e._store, "a", allowed_tools=[])
    _seed(e._store, "b", allowed_tools=["query_orders"])
    r = await e.handle(["a", "b"], "msg", "s1")
    assert r.reply == "结论"
    assert r.data["steps"][0]["blocked"] is False
    assert r.data["skill_ids"] == ["a", "b"]
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd maestro && pytest tests/test_skill_routing.py -k multi -v`
Expected: FAIL（`handle` 仍按单 `skill_id`，首参为 list 时 `store.get(list)` 报错/找不到）

- [ ] **Step 4: 实现合并逻辑**

`skills/engine.py` 整体替换 `handle` 方法为：

```python
    async def handle(
        self,
        skill_ids: list[str],
        message: str,
        session_id: str,
        history: list[dict] | None = None,
        on_progress: ProgressFn | None = None,
        source: Literal["user", "route"] = "user",
    ) -> EngineResponse:
        """source: 触发来源。"user"=前端强制指定（每个技能都受 user_invocable 约束）；
        "route"=路由命中。多技能：合并 allowed_tools/tool_preconditions/正文，单次 AgentLoop。"""
        if not skill_ids:
            return EngineResponse(reply="未指定技能")
        metas = []
        for sid in skill_ids:
            meta = self._store.get(sid)
            if meta is None:
                return EngineResponse(reply=f"技能 {sid} 不存在或已被删除")
            metas.append(meta)
        if source == "user":
            blocked = [m.effective_display_name for m in metas if not m.user_invocable]
            if blocked:
                return EngineResponse(
                    reply=f"技能 {'、'.join(blocked)} 不支持手动指定，仅由系统自动路由调用"
                )
        if not self._llm.available:
            return EngineResponse(reply="LLM 未配置，技能暂不可用")

        allowed: list[str] = []
        for m in metas:
            for t in (m.allowed_tools or []):
                if t not in allowed:
                    allowed.append(t)
        if any(m.file_count > 0 for m in metas) and "read_skill_file" not in allowed:
            allowed.append("read_skill_file")

        extra: dict[str, list[Precondition]] = {}
        for m in metas:
            for tool, names in m.tool_preconditions.items():
                bucket = extra.setdefault(tool, [])
                for n in names:
                    p = self._named[n]
                    if p not in bucket:
                        bucket.append(p)

        bodies: list[str] = []
        for sid, m in zip(skill_ids, metas):
            try:  # 与删除并发的竞态: 与"不存在"同口径收口
                body = self._store.get_body(sid)
            except (KeyError, FileNotFoundError):
                return EngineResponse(reply=f"技能 {sid} 不存在或已被删除")
            bodies.append(f"## 技能: {m.effective_display_name}\n\n{body}")
        combined = SKILL_PREAMBLE + "\n\n---\n\n".join(bodies)

        try:
            result = await AgentLoop(
                self._llm, self._tools, self._pending, self._audit,
                combined, allowed, self._settings.react_max_steps,
                observation_max_bytes=self._settings.react_observation_max_bytes,
                extra_preconditions=extra or None,
            ).run(message, history=history, on_progress=on_progress)
        except LLMError:
            return EngineResponse(reply="LLM 调用失败，技能暂不可用")
        return EngineResponse(
            reply=result.answer,
            data={
                "steps": [s.model_dump(mode="json") for s in result.steps],
                "stop_reason": result.stop_reason,
                "skill_ids": list(skill_ids),
            },
            pending_actions=result.pending_actions,
        )
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd maestro && pytest tests/test_skill_routing.py -v`
Expected: 全部 PASS（既有单技能用例以 `["cap"]` 形式通过，多技能新用例通过）

- [ ] **Step 6: 提交**

```bash
git add maestro/src/maestro/skills/engine.py \
        maestro/tests/test_skill_routing.py
git commit -m "feat(skills): SkillEngine.handle 接受技能列表，合并工具/断言/正文单次运行

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: orchestrator + main 的 skill_ids 贯通（Feature 2 后端接线）

**Files:**
- Modify: `maestro/src/maestro/orchestrator/schemas.py`（`RouteDecision.skill_ids`）
- Modify: `maestro/src/maestro/orchestrator/orchestrator.py`（`handle`、skill 分支、`_dispatch`）
- Modify: `maestro/src/maestro/main.py`（两个请求模型 + 两处 handle 调用）
- Modify: `maestro/tests/test_skill_routing.py`（RouteDecision 字段用例）
- Docs: `docs/api-contract/api-contract-v2.md`

**Interfaces:**
- Consumes: `SkillEngine.handle(skill_ids, ...)`（Task 5）。
- Produces: `Orchestrator.handle(session_id, message, route="auto", on_progress=None, skill_ids: list[str] | None = None)`；`RouteDecision.skill_ids: list[str]`；请求体 `skill_ids: list[str] | None`。

- [ ] **Step 1: RouteDecision 加 skill_ids（含失败测试）**

在 `test_skill_routing.py` 的 `test_routedecision_skill_fields` 后追加：

```python
def test_routedecision_skill_ids_default_and_set():
    d = RouteDecision(intent="skill", skill_ids=["a", "b"], confidence=1.0)
    assert d.skill_ids == ["a", "b"]
    assert RouteDecision(intent="query", confidence=0.5).skill_ids == []
```

Run: `cd maestro && pytest tests/test_skill_routing.py::test_routedecision_skill_ids_default_and_set -v` → FAIL。

`orchestrator/schemas.py` — `RouteDecision` 在 `skill_id` 下加：

```python
    skill_id: str | None = None  # 兼容：单技能路由/首个技能
    skill_ids: list[str] = Field(default_factory=list)  # 前端多技能选择
```

- [ ] **Step 2: orchestrator.handle 接受 skill_ids**

`orchestrator.py` `handle` 签名把 `skill_id: str | None = None` 改为：

```python
        skill_ids: list[str] | None = None,
```

skill 分支（原 `if skill_id is not None:`）整块替换：

```python
        # ── 前端选定技能 (skill_ids 非空)：跳过路由，直接派发到 SkillEngine ──
        if skill_ids:
            decision = RouteDecision(
                intent="skill",
                skill_id=skill_ids[0],
                skill_ids=list(skill_ids),
                confidence=1.0,
                entities=extract_entities(message),
                reason="前端选定技能",
                route_method="forced",
            )
            self._memory.append(session_id, "user", message)
            self._record_route(session_id, message, decision)
            resp = await self._dispatch(decision, message, session_id, state, on_progress)
            return self._finish(session_id, decision, resp)
```

- [ ] **Step 3: _dispatch skill 分支传列表**

`_dispatch` 里 `if decision.intent == "skill":` 的调用改为：

```python
            return await self._skills.handle(
                decision.skill_ids or ([decision.skill_id] if decision.skill_id else []),
                message, session_id,
                history=state.history[:-1], on_progress=on_progress,
                source="user" if decision.route_method == "forced" else "route",
            )
```

- [ ] **Step 4: main.py 请求模型 + 调用**

`ChatRequest` 与 `ChatStreamRequest` 各加：

```python
    skill_ids: list[str] | None = None  # 多技能选择；与 skill_id 二选一，二者都在时合并
```

`/chat`（~103）调用改为：

```python
        req.session_id, req.message, route=req.route,
        skill_ids=req.skill_ids or ([req.skill_id] if req.skill_id else None),
```

`/chat/stream`（~230）`platform.orchestrator.handle(...)` 的 `skill_id=req.skill_id` 改为：

```python
                skill_ids=req.skill_ids or ([req.skill_id] if req.skill_id else None),
```

`main.py:149` 的路由数据 `"skill_id": rd.skill_id if rd.intent == "skill" else None` 保持不变（`skill_id` 仍填首个）。

- [ ] **Step 5: 跑后端全量测试**

Run: `cd maestro && pytest -q`
Expected: 全绿。若有测试直接调用 `orchestrator.handle(..., skill_id=...)`，改为 `skill_ids=[...]`（grep 确认：`grep -rn "handle(.*skill_id" maestro/tests`）。

- [ ] **Step 6: 更新 API 契约**

`docs/api-contract/api-contract-v2.md` 中 `/chat` 与 `/chat/stream` 请求体补充 `skill_ids: string[]`（说明与 `skill_id` 合并、跳过路由直达 SkillEngine 合并运行）；`/sessions/{id}/messages` 响应的消息对象补充 `kind: "normal" | "system"`（Task 1/2 的字段，一并补文档）。

- [ ] **Step 7: 提交**

```bash
git add maestro/src/maestro/orchestrator/schemas.py \
        maestro/src/maestro/orchestrator/orchestrator.py \
        maestro/src/maestro/main.py \
        maestro/tests/test_skill_routing.py \
        docs/api-contract/api-contract-v2.md
git commit -m "feat(orchestrator): skill_ids 贯通 handle/main，多技能直达 SkillEngine

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: 前端 API/hook 传 skill_ids（Feature 2 前端接线）

**Files:**
- Modify: `frontend/src/api/useStreamingChat.ts`（`send` 签名 + 请求体）
- Modify: `frontend/src/features/orchestrator/useOrchestrator.ts`（`send` 透传）

**Interfaces:**
- Produces: `useStreamingChat().send(message, currentEngine, skillIds: string[])`；`useOrchestrator().send(text, currentEngine, skillIds: string[])`。请求体字段 `skill_ids: string[]`。

- [ ] **Step 1: useStreamingChat.send 改多技能**

`useStreamingChat.ts` 的 `send`：

```ts
  const send = useCallback(
    (message: string, currentEngine: EngineType | null = null, skillIds: string[] = []) => {
      start(
        (signal) =>
          streamChat(
            { session_id: sessionId, message, current_engine: currentEngine, skill_ids: skillIds },
            signal,
          ),
        true,
      );
    },
    [sessionId, start],
  );
```

若 `streamChat` 的请求体类型（`@/api/...` 或本文件内 interface）不含 `skill_ids`，把该 body 类型的 `skill_id?: string | null` 改/加为 `skill_ids?: string[]`。

- [ ] **Step 2: useOrchestrator.send 透传数组**

`useOrchestrator.ts` `send`：

```ts
  const send = useCallback(
    (text: string, currentEngine: EngineType | null, skillIds: string[] = []) => {
      turnIdRef.current = `a-${Date.now()}`;
      turnTimeRef.current = nowHM();
      pendingRef.current = true;
      addMessage({ id: `u-${Date.now()}`, kind: 'user', time: nowHM(), text });
      chatRef.current.send(text, currentEngine, skillIds);
    },
    [addMessage],
  );
```

- [ ] **Step 3: 类型 + lint + 测试**

Run: `cd frontend && npm run build && npm run lint && npm test`
Expected: tsc 通过、lint 0 warning。此时 `Workspace` 仍传旧的 `skill?.name ?? null` 会类型报错 → 允许，将在 Task 8 修正；若要保持 Task 间可编译，本 Task 暂把 Workspace 调用改为 `send(text, ..., skill ? [skill.name] : [])`（Task 8 会覆盖）。

> 为保证每个 Task 都可编译通过，本步骤同时在 `Workspace.tsx` 把 `onSend={(text) => send(text, route === 'auto' ? null : route, skill?.name ?? null)}` 临时改为 `onSend={(text) => send(text, route === 'auto' ? null : route, skill ? [skill.name] : [])}`。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/api/useStreamingChat.ts \
        frontend/src/features/orchestrator/useOrchestrator.ts frontend/src/pages/Workspace.tsx
git commit -m "feat(api): 前端对话发送改用 skill_ids 数组

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: 多技能多选菜单 + 芯片行（Feature 2 前端 UI）

**Files:**
- Modify: `frontend/src/features/orchestrator/skills/SkillMenu.tsx`
- Modify: `frontend/src/features/orchestrator/skills/SkillMenu.test.tsx`
- Modify: `frontend/src/features/orchestrator/Composer.tsx`
- Modify: `frontend/src/pages/Workspace.tsx`

**Interfaces:**
- Consumes: `useOrchestrator().send(text, engine, skillIds)`（Task 7）。
- Produces: `SkillMenu` props `{ skills, selected: SkillMeta[], onToggleSkill(s), onClear(), onImportSkill, open, onToggle }`；`Composer` props `{ skills, selectedSkills: SkillMeta[], onToggleSkill(s), onClearSkills(), ... }`。

- [ ] **Step 1: 改 SkillMenu 测试为多选**

替换 `SkillMenu.test.tsx` 的 props 工厂与三个用例：

```tsx
const props = (overrides: Record<string, unknown> = {}) => ({
  skills: SKILLS,
  selected: [] as unknown[],
  onToggleSkill: vi.fn(),
  onClear: vi.fn(),
  onImportSkill: vi.fn(),
  open: true,
  onToggle: vi.fn(),
  ...overrides,
});

describe('SkillMenu', () => {
  it('lists skills and filters by search', () => {
    render(<SkillMenu {...props()} />);
    expect(screen.getByText('产能日报')).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText(/搜索/), { target: { value: '换线' } });
    expect(screen.queryByText('产能日报')).toBeNull();
    expect(screen.getByText('换线检查清单')).toBeTruthy();
  });

  it('点击技能触发 onToggleSkill（不关闭菜单）', () => {
    const onToggleSkill = vi.fn();
    render(<SkillMenu {...props({ onToggleSkill })} />);
    fireEvent.click(screen.getByText('产能日报'));
    expect(onToggleSkill).toHaveBeenCalledWith(expect.objectContaining({ name: 'capacity-report' }));
  });

  it('清空与导入入口', () => {
    const onClear = vi.fn();
    const onImportSkill = vi.fn();
    render(<SkillMenu {...props({ onClear, onImportSkill })} />);
    fireEvent.click(screen.getByText(/清空/));
    expect(onClear).toHaveBeenCalled();
    fireEvent.click(screen.getByText(/导入技能/));
    expect(onImportSkill).toHaveBeenCalled();
  });
});
```

Run: `cd frontend && npm test -- SkillMenu.test.tsx` → FAIL。

- [ ] **Step 2: 实现 SkillMenu 多选**

`SkillMenu.tsx` props 与逻辑改为多选（chip 触发按钮显示计数）：

```tsx
interface SkillMenuProps {
  skills: SkillMeta[];
  selected: SkillMeta[];
  onToggleSkill: (s: SkillMeta) => void;
  onClear: () => void;
  onImportSkill: () => void;
  open: boolean;
  onToggle: () => void;
}

export function SkillMenu({
  skills, selected, onToggleSkill, onClear, onImportSkill, open, onToggle,
}: SkillMenuProps) {
  const [q, setQ] = useState('');
  const visible = skills.filter((s) => s.user_invocable !== false);
  const filtered = visible.filter((s) =>
    [s.name, s.display_name, s.description].join(' ').toLowerCase().includes(q.toLowerCase()),
  );
  const isSel = (s: SkillMeta) => selected.some((x) => x.name === s.name);

  const active = open || selected.length > 0;
  const chip = `inline-flex h-8 cursor-pointer items-center gap-[6px] rounded-md border px-[9px] font-sans text-caption font-semibold text-text-secondary transition-colors duration-fast ease-out ${
    active ? 'border-accent-border bg-accent-bg' : 'border-border-default hover:bg-border-subtle'
  }`;
  const row =
    'flex w-full items-center gap-[10px] rounded-sm px-2 py-[7px] text-left transition-colors duration-fast ease-out';

  return (
    <div className="relative">
      <button type="button" onClick={onToggle} aria-haspopup="menu" aria-expanded={open} className={chip}>
        <Sparkles size={13} className="text-accent" />
        <span className="text-text-primary">
          {selected.length > 0 ? `技能 · ${selected.length}` : '技能'}
        </span>
        <ChevronDown size={13} className="text-text-tertiary" />
      </button>

      {open && (
        <div className="material-popover absolute bottom-full left-0 mb-2 w-[264px] rounded-md border border-border-default shadow-popover">
          <div className="flex items-center gap-[6px] border-b border-border-default px-[10px] py-[7px]">
            <Search size={13} className="flex-none text-text-tertiary" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="搜索技能"
              className="w-full bg-transparent text-body-sm text-text-primary placeholder:text-text-tertiary focus:outline-none"
            />
          </div>

          <div className="max-h-[280px] overflow-auto px-1 py-1">
            <button
              onClick={onClear}
              disabled={selected.length === 0}
              className={`${row} ${selected.length === 0 ? 'opacity-50' : 'hover:bg-border-subtle'}`}
            >
              <Ban size={14} className="flex-none text-text-tertiary" />
              <span className="min-w-0 flex-1 text-body-sm text-text-secondary">清空已选</span>
            </button>

            {filtered.map((s) => {
              const selectedNow = isSel(s);
              return (
                <button
                  key={s.name}
                  role="menuitemcheckbox"
                  aria-checked={selectedNow}
                  onClick={() => onToggleSkill(s)}
                  className={`${row} ${selectedNow ? 'bg-accent-bg' : 'hover:bg-border-subtle'}`}
                >
                  <Sparkles size={14} className="flex-none text-text-secondary" />
                  <span className="flex min-w-0 flex-1 flex-col leading-tight">
                    <span className="truncate text-body-sm font-semibold text-text-primary">
                      {s.display_name ?? s.name}
                    </span>
                    <span className="truncate text-[11px] text-text-tertiary">{s.description}</span>
                  </span>
                  {selectedNow && <Check size={14} className="flex-none text-accent" />}
                </button>
              );
            })}

            {filtered.length === 0 && (
              <div className="px-2 py-2 text-[11px] text-text-tertiary">暂无技能，点击下方导入</div>
            )}
          </div>

          <div className="border-t border-border-default px-1 py-1">
            <button onClick={onImportSkill} className={`${row} text-text-secondary hover:bg-border-subtle`}>
              <Import size={14} className="flex-none text-text-tertiary" />
              <span className="text-body-sm font-medium">导入技能</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
```

Run: `cd frontend && npm test -- SkillMenu.test.tsx` → PASS。

- [ ] **Step 3: Composer 加芯片行 + 改 props**

`Composer.tsx`：
- import `lucide-react` 增加 `X`。
- `ComposerProps` 把 `skill: SkillMeta | null; onSkillChange` 换成：

```ts
  selectedSkills: SkillMeta[];
  onToggleSkill: (s: SkillMeta) => void;
  onClearSkills: () => void;
```

- 函数签名解构相应更新；`<SkillMenu>` 调用改为：

```tsx
            <SkillMenu
              skills={skills}
              selected={selectedSkills}
              onToggleSkill={onToggleSkill}
              onClear={onClearSkills}
              onImportSkill={onImportSkill}
              open={openMenu === 'skill'}
              onToggle={() => setOpenMenu(openMenu === 'skill' ? null : 'skill')}
            />
```

- 在 `<textarea>` 之前、dock `<div className="material-dock ...">` 内部顶部插入芯片行（仅有选中时渲染）：

```tsx
          {selectedSkills.length > 0 && (
            <div className="flex flex-wrap items-center gap-[6px] px-[12px] pt-[10px]">
              {selectedSkills.map((s) => (
                <span
                  key={s.name}
                  className="inline-flex h-[26px] items-center gap-[6px] rounded-md border border-accent-border bg-accent-bg px-[8px] text-caption font-medium text-text-primary"
                >
                  <Sparkles size={12} className="text-accent" />
                  {s.display_name ?? s.name}
                  <button
                    type="button"
                    title="移除技能"
                    onClick={() => onToggleSkill(s)}
                    className="grid h-[16px] w-[16px] place-items-center rounded-sm text-text-tertiary hover:bg-border-subtle hover:text-text-secondary"
                  >
                    <X size={12} />
                  </button>
                </span>
              ))}
            </div>
          )}
```

（`Sparkles` 已在 SkillMenu 用；Composer 需从 `lucide-react` import `Sparkles`、`X`。）

- [ ] **Step 4: Workspace 改 skills 数组**

`Workspace.tsx`：
- `const [skill, setSkill] = useState<SkillMeta | null>(null);` → `const [skills, setSkills] = useState<SkillMeta[]>([]);`
- `handleRouteChange`：`if (next !== 'auto') setSkill(null);` → `setSkills([]);`
- 删除 `handleSkillChange`，新增：

```tsx
  const handleToggleSkill = (s: SkillMeta) => {
    setSkills((cur) =>
      cur.some((x) => x.name === s.name) ? cur.filter((x) => x.name !== s.name) : [...cur, s],
    );
    setRoute('auto');
  };
  const handleClearSkills = () => setSkills([]);
```

- `SkillImportModal` 的 `onImported={(s) => { setSkill(s); setImportOpen(false); }}` → `onImported={(s) => { setSkills((cur) => cur.some((x) => x.name === s.name) ? cur : [...cur, s]); setImportOpen(false); }}`
- `<Composer>` 的 `onSend`/`skill`/`onSkillChange` 更新：

```tsx
      onSend={(text) => send(text, route === 'auto' ? null : route, skills.map((s) => s.name))}
      ...
      selectedSkills={skills}
      onToggleSkill={handleToggleSkill}
      onClearSkills={handleClearSkills}
```

（移除已废弃的 `skill`/`onSkillChange` 传参与 Task 7 的临时 `skill ? [skill.name] : []`。）

- [ ] **Step 5: 全量前端校验**

Run: `cd frontend && npm run build && npm run lint && npm test`
Expected: tsc 通过、lint 0 warning、所有测试（含 SkillMenu、history、defaultEngineStore）PASS

- [ ] **Step 6: 手动核对（可选，subagent 跳过）**

`npm run dev` → 打开技能菜单，勾选两个技能（菜单不关闭）→ 输入框上方出现两个可 × 删除的芯片 → 触发按钮显示"技能 · 2" → 删除一个芯片后计数变 1 → 输入需求发送。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/features/orchestrator/skills/SkillMenu.tsx \
        frontend/src/features/orchestrator/skills/SkillMenu.test.tsx \
        frontend/src/features/orchestrator/Composer.tsx frontend/src/pages/Workspace.tsx
git commit -m "feat(composer): 多技能多选 + 可删除芯片行

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## 收尾验证（全部 Task 后）

- [ ] 后端：`cd maestro && pytest -q` 全绿
- [ ] 前端：`cd frontend && npm run build && npm run lint && npm test` 全绿
- [ ] 手动走查三条验收：设置二级菜单 + 默认引擎持久化生效；多技能芯片选择/删除/发送；执行含确认动作的会话后切走再回，回答不再拆成多个 Maestro 气泡、确认结果为 system 细行。

---

## Self-Review 记录

- **Spec 覆盖**：Feature 1 → Task 3+4；Feature 2 前端 → Task 7+8、后端 → Task 5+6；Feature 3 → Task 1+2；API 契约 → Task 6 Step 6。全覆盖。
- **偏离 spec 的简化**：spec 建议把 `ROUTE_OPTS` 抽为共享；实现改为在 Sidebar 内定义 4 行 `ENGINE_OPTS` 局部常量，避免 layer→feature 反向依赖，更符合"surgical"。设置二级菜单采用单面板 drill-in（root→子视图）而非 macOS 侧向 flyout，规避定位复杂度，仍是两级导航。
- **类型一致性**：`skill_ids: list[str]` 在 handle/RouteDecision/请求体/SkillEngine 一致；前端 `skillIds: string[]` 在 useStreamingChat/useOrchestrator 一致；`storedToThread` 签名前后一致；`DefaultEngine` 与 `ComposerRoute` 同集合可赋值。
- **Placeholder 扫描**：无 TBD/TODO/占位；每个代码步骤含完整代码。
