# Session Persistence — 会话持久化

## 概述

本项目的会话持久化模块提供跨进程重启的对话记忆能力，将会话元数据与消息历史写入本地文件系统。采用两层架构：内存缓存层 (`ConversationMemory`) 提供低延迟读写，文件持久层 (`SessionStore`) 确保数据不丢失。

## 目录结构

```
data/sessions/
├── index.json                          # 所有会话的元数据列表（按 updated_at 倒序）
├── {session_id}.json                  # 该会话的完整消息历史（append-only JSON 数组）
└── ...
```

## 数据模型

### SessionMeta — 会话元数据

```python
class SessionMeta(BaseModel):
    session_id: str           # UUID hex，全局唯一标识
    title: str = "新对话"      # 会话标题（首条用户消息前20字或LLM生成）
    engine: str | None = None # 当前会话的引擎（会话粘性路由预留，v0.2）
    created_at: str           # ISO 8601 UTC 创建时间
    updated_at: str           # ISO 8601 UTC 最后更新时间
    message_count: int = 0    # 消息总数
```

### StoredMessage — 持久化消息

```python
class StoredMessage(BaseModel):
    role: str                 # "user" | "assistant" | "system"
    content: str              # 消息内容（纯文本）
    ts: str                   # ISO 8601 UTC 时间戳
```

### SessionState — 内存会话状态

```python
class SessionState(BaseModel):
    history: list[dict] = []           # [{"role","content"}] 消息历史
    current_engine: str | None = None # 当前引擎（会话粘性预留）
    context: dict = {}                # 瞬态上下文（进程内，不持久化）
```

**注意**：`context` 字段不持久化，包含 `pending_clarification`、`last_planning_result` 等仅在当前进程生命周期内有效的数据。

## 核心组件

### SessionStore — 文件持久层

线程安全的同步实现，可通过 `asyncio.to_thread` 安全地在异步代码中使用。

```python
class SessionStore:
    def __init__(self, base_dir: Path | str)
    
    # CRUD Operations
    def create(self, title: str = "新对话") -> SessionMeta
    def get(self, session_id: str) -> SessionMeta | None
    def list_all(self) -> list[SessionMeta]        # 按 updated_at 倒序
    def update_title(self, session_id: str, title: str) -> None
    def update_engine(self, session_id: str, engine: str) -> None
    def delete(self, session_id: str) -> bool
    
    # Message Operations
    def append_message(self, session_id: str, role: str, content: str) -> None
    def get_messages(self, session_id: str) -> list[dict]
```

**线程安全保证**：内部使用 `threading.Lock` 保护所有读写操作，多线程环境下安全。

### ConversationMemory — 内存缓存层

```python
class ConversationMemory:
    def __init__(self, session_store: SessionStore | None = None)
    
    def get(self, session_id: str) -> SessionState
    def append(self, session_id: str, role: str, content: str) -> None
    def recent(self, session_id: str, n: int = 6) -> list[dict]
    def set_engine(self, session_id: str, engine: str | None) -> None
    def set_context(self, session_id: str, key: str, value: Any) -> None
    def get_context(self, session_id: str, key: str) -> Any
```

**冷启动加载**：首次访问 `session_id` 时，自动从 `SessionStore` 回载历史消息与引擎状态，实现"重启不失忆"。

## 文件格式

### index.json — 会话索引

```json
[
  {
    "session_id": "a1b2c3d4e5f67890abcdef123456",
    "title": "重新排产注塑车间订单",
    "engine": "planning",
    "created_at": "2026-07-01T10:30:00+00:00",
    "updated_at": "2026-07-01T14:20:00+00:00",
    "message_count": 12
  }
]
```

### {session_id}.json — 消息历史

```json
[
  {
    "role": "user",
    "content": "帮我重新排一下本周的注塑订单",
    "ts": "2026-07-01T10:30:00+00:00"
  },
  {
    "role": "assistant",
    "content": "好的，我来为您重新排产...",
    "ts": "2026-07-01T10:30:05+00:00"
  }
]
```

## API 接口

完整契约见 `docs/api-contract/api-contract-v2.md` §5。

### List Sessions — 列出所有会话

```http
GET /sessions
```

**Response**:
```json
[
  {
    "session_id": "a1b2c3d4e5f67890abcdef123456",
    "title": "重新排产注塑车间订单",
    "engine": "planning",
    "created_at": "2026-07-01T10:30:00+00:00",
    "updated_at": "2026-07-01T14:20:00+00:00",
    "message_count": 12
  }
]
```

### Create Session — 新建会话

```http
POST /sessions
Content-Type: application/json

{
  "title": "新对话"
}
```

**Response**:
```json
{
  "session_id": "a1b2c3d4e5f67890abcdef123456",
  "title": "新对话",
  "engine": null,
  "created_at": "2026-07-06T10:00:00+00:00",
  "updated_at": "2026-07-06T10:00:00+00:00",
  "message_count": 0
}
```

### Rename Session — 重命名会话

```http
PATCH /sessions/{session_id}
Content-Type: application/json

{
  "title": "我的新标题"
}
```

### Delete Session — 删除会话

```http
DELETE /sessions/{session_id}
```

**Response**:
```json
{
  "deleted": true,
  "session_id": "a1b2c3d4e5f67890abcdef123456"
}
```

### Get Session Messages — 获取消息历史

```http
GET /sessions/{session_id}/messages
```

**Response**:
```json
[
  {
    "role": "user",
    "content": "...",
    "ts": "2026-07-06T10:00:00+00:00"
  }
]
```

## 前端集成

### API Client (`frontend/src/api/sessions.ts`)

```typescript
export interface StoredMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  ts: string;
}

export const listSessions = () => apiGet<SessionInfo[]>('/sessions');
export const createSession = (title = '新对话') => apiPost<SessionInfo>('/sessions', { title });
export const getSessionMessages = (sessionId: string) => apiGet<StoredMessage[]>(`/sessions/${sessionId}/messages`);
export const renameSession = (sessionId: string, title: string) => apiPatch<SessionInfo>(`/sessions/${sessionId}`, { title });
export const deleteSession = (sessionId: string) => apiDelete<...>(`/sessions/${sessionId}`);
```

### Session Store (`frontend/src/stores/sessionStore.ts`)

Zustand 存储仅管理**前端 UI 状态**（当前活跃会话 ID），会话列表本身属于服务器状态，由 TanStack Query 缓存。

```typescript
interface SessionStoreState {
  activeSessionId: string | null;
  setActiveSessionId: (id: string | null) => void;
}
```

## 自动标题生成

首轮用户消息发送后，系统会并行调用 LLM 生成一个语义化的短标题（最多 12 汉字）：

```python
_TITLE_SYSTEM = """
你是会话标题生成助手。根据用户的第一句话，生成一个简短、有意义的中文标题，
用于会话列表展示。要求：概括核心意图；不超过 12 个汉字；
只输出标题本身，不要标点、引号、书名号或任何多余文字。
"""
```

**降级策略**：LLM 不可用或调用失败时，回退到首条消息的前 20 字符截断（超长时加"…"）。

**竞态避免**：标题生成在 `chat/stream` 端点中与编排任务并行执行，但在任何 SSE 帧流出之前完成落库，确保前端刷新不会读到旧标题。

## 流程：完整会话生命周期

### 1. 冷启动（进程重启）

```
用户访问前端 → 调用 GET /sessions
  ↓
ConversationMemory.get(session_id)
  ↓
缓存未命中 → SessionStore.get_messages(session_id)
  ↓
从 {session_id}.json 回载历史 → SessionState.history 填充
  ↓
从 SessionMeta 恢复 current_engine
  ↓
用户看到历史消息，无缝续谈
```

### 2. 新消息

```
用户发送消息 → POST /chat/stream
  ↓
Orchestrator.handle()
  ↓
ConversationMemory.append(session_id, "user", message)
  ↓
SessionStore.append_message(session_id, "user", message)
  ↓
(同时) 编排处理 → 生成回复
  ↓
ConversationMemory.append(session_id, "assistant", reply)
SessionStore.append_message(session_id, "assistant", reply)
  ↓
(首轮时并行) LLM 生成标题 → update_title()
```

### 3. 会话切换

```
用户在侧边栏点击会话 → setActiveSessionId(session_id)
  ↓
前端调用 getSessionMessages(session_id)
  ↓
渲染历史消息
  ↓
(可选) 调用 GET /audit/timeline?session_id=... 展示决策时间线
```

## 线程安全

### SessionStore 锁

```python
class SessionStore:
    def __init__(self, ...):
        self._lock = threading.Lock()
```

所有读写操作都在 `with self._lock:` 保护下执行，包括：
- `_load_index()` / `_save_index()`
- `append_message()` 的读-改-写循环
- `delete()` 的元数据与文件删除

### 异步使用

FastAPI 端点中通过 `asyncio.to_thread` 调用同步方法：

```python
@app.get("/sessions")
async def list_sessions():
    sessions = await asyncio.to_thread(store.list_all)
    return [s.model_dump() for s in sessions]
```

## 设计决策

### 为什么使用文件而不是 SQLite？

参考 `docs/session-memory/session_memory_design_v2.md` 是 v0.2 的未来规划（装配式上下文、压缩、Artifact 存储等），当前 v0.1 采用简单文件存储的原因：
- 单用户部署，无并发写入冲突
- 可观测性：用户可直接用文本编辑器查看/备份会话
- 零依赖：无需引入 SQLAlchemy/asyncpg
- 渐进式：v0.2 可无缝迁移到 SQLite 而不改变 API 契约

### 为什么使用单独的 index.json？

- 会话列表加载快：只需读一个小文件，无需扫描所有 `{session_id}.json`
- 排序一致性：索引按 `updated_at` 倒序排列，前端无需二次排序
- 原子性：`_save_index()` 采用临时文件替换，避免崩溃导致索引损坏

### 仅追加的消息文件

消息文件只追加不修改，天然支持：
- 历史可追溯
- 崩溃恢复：追加到一半失败时，下次启动仍能读到有效前缀
- 未来对接事件溯源架构

## 未来：v0.2 路线图

当前实现是 v0.1 基础版，预留以下 v0.2 扩展点（见 `session_memory_design_v2.md`）：

| Feature | Status | Notes |
|---------|--------|-------|
| SessionSticky Routing | Reserved | `SessionMeta.engine` + `SessionState.current_engine` 已预留 |
| Context Assembly | Not Implemented | 装配式上下文（SessionFacts + ActiveRun + RollingSummary + Tail） |
| Token-Aware Compression | Not Implemented | 水位触发 + Haiku 摘要 + CompactionEvent 审计 |
| Artifact Storage | Not Implemented | 大负载卸载 + recall 工具 |
| Full-Text Search | Not Implemented | FTS5 搜索历史 |
| Experience Memory | Not Implemented | 跨会话经验抽取（预留架构） |

**API Stability Guarantee**：v0.2 的 HTTP API 将保持向后兼容，仅新增端点或字段，不删除或改变现有契约形状。

## 集成点

### Bootstrap (`bootstrap.py`)

```python
# Platform dataclass includes:
session_store: SessionStore
memory: ConversationMemory
```

### Orchestrator

- `handle()`: 调用 `memory.append()` 记录消息
- `resume_clarification()`: 从 `memory.get_context()` 恢复待澄清状态

### Main (`main.py`)

- `/chat/stream`: 附加消息 + 首轮标题生成
- `/sessions/*`: 会话 CRUD 端点封装
