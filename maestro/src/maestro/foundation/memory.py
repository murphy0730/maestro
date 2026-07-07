"""会话记忆。

按 session_id 存储对话历史 + 当前会话所处引擎 (v0.2 会话粘性预留) +
上一次排产结果等上下文。内存字典为读写缓存，底层由 SessionStore 持久化：
- history / current_engine 重启后从 SessionStore 回载 (agent 不失忆)
- context (pending_clarification / last_planning_result 等) 为进程内瞬态
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from maestro.foundation.session_store import SessionStore


class SessionState(BaseModel):
    history: list[dict] = Field(default_factory=list)  # [{"role","content"}]
    current_engine: str | None = None  # TODO(v0.2): 会话粘性路由
    context: dict = Field(default_factory=dict)  # 如 last_planning_result


class ConversationMemory:
    def __init__(self, session_store: SessionStore | None = None):
        self._sessions: dict[str, SessionState] = {}
        self._store = session_store

    def get(self, session_id: str) -> SessionState:
        if session_id not in self._sessions:
            state = SessionState()
            # 缓存未命中 → 从持久层回载历史与所处引擎 (进程重启后继续对话)
            if self._store is not None:
                state.history = [
                    {"role": m["role"], "content": m["content"]}
                    for m in self._store.get_messages(session_id)
                ]
                meta = self._store.get(session_id)
                if meta is not None:
                    state.current_engine = meta.engine
            self._sessions[session_id] = state
        return self._sessions[session_id]

    def append(self, session_id: str, role: str, content: str) -> None:
        self.get(session_id).history.append({"role": role, "content": content})
        if self._store:
            self._store.append_message(session_id, role, content)

    def recent(self, session_id: str, n: int = 6) -> list[dict]:
        return self.get(session_id).history[-n:]

    def set_engine(self, session_id: str, engine: str | None) -> None:
        self.get(session_id).current_engine = engine
        if self._store is not None and engine is not None:
            self._store.update_engine(session_id, engine)

    def set_context(self, session_id: str, key: str, value: Any) -> None:
        self.get(session_id).context[key] = value

    def get_context(self, session_id: str, key: str) -> Any:
        return self.get(session_id).context.get(key)
