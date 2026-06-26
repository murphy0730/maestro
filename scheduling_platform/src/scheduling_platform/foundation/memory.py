"""会话记忆。

按 session_id 存储对话历史 + 当前会话所处引擎 (v0.2 会话粘性预留) +
上一次排产结果等上下文。初始版本内存字典实现，接口可替换为持久化存储。
"""

from typing import Any

from pydantic import BaseModel, Field


class SessionState(BaseModel):
    history: list[dict] = Field(default_factory=list)  # [{"role","content"}]
    current_engine: str | None = None  # TODO(v0.2): 会话粘性路由
    context: dict = Field(default_factory=dict)  # 如 last_planning_result


class ConversationMemory:
    def __init__(self):
        self._sessions: dict[str, SessionState] = {}

    def get(self, session_id: str) -> SessionState:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionState()
        return self._sessions[session_id]

    def append(self, session_id: str, role: str, content: str) -> None:
        self.get(session_id).history.append({"role": role, "content": content})

    def recent(self, session_id: str, n: int = 6) -> list[dict]:
        return self.get(session_id).history[-n:]

    def set_engine(self, session_id: str, engine: str | None) -> None:
        self.get(session_id).current_engine = engine

    def set_context(self, session_id: str, key: str, value: Any) -> None:
        self.get(session_id).context[key] = value

    def get_context(self, session_id: str, key: str) -> Any:
        return self.get(session_id).context.get(key)
