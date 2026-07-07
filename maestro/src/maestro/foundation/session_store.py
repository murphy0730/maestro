"""Session persistence — 将会话元数据与消息历史写入本地文件。

目录结构:
  data/sessions/index.json          — 所有会话的元数据列表（按 updated_at 倒序）
  data/sessions/{session_id}.json   — 该会话的消息历史（append-only JSON 数组）
"""

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel


class SessionMeta(BaseModel):
    session_id: str
    title: str = "新对话"
    engine: str | None = None
    created_at: str
    updated_at: str
    message_count: int = 0


class StoredMessage(BaseModel):
    role: str   # "user" | "assistant" | "system"
    content: str
    ts: str
    kind: str = "normal"   # "normal" | "system"（system=动作确认结果等细行）


class SessionStore:
    """文件背书的会话存储（单进程可用）。

    方法为同步实现但线程安全（内部互斥锁），调用方可放心用
    asyncio.to_thread 把文件 IO 移出事件循环。
    """

    def __init__(self, base_dir: Path | str):
        self._dir = Path(base_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index_file = self._dir / "index.json"
        self._sessions: dict[str, SessionMeta] = {}
        self._lock = threading.Lock()
        self._load_index()

    def _load_index(self) -> None:
        if not self._index_file.exists():
            return
        try:
            data = json.loads(self._index_file.read_text(encoding="utf-8"))
            self._sessions = {s["session_id"]: SessionMeta(**s) for s in data}
        except Exception:
            self._sessions = {}

    def _save_index(self) -> None:
        ordered = sorted(self._sessions.values(), key=lambda s: s.updated_at, reverse=True)
        self._index_file.write_text(
            json.dumps([s.model_dump() for s in ordered], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _msg_file(self, session_id: str) -> Path:
        return self._dir / f"{session_id}.json"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def create(self, title: str = "新对话") -> SessionMeta:
        sid = uuid.uuid4().hex
        now = self._now()
        meta = SessionMeta(session_id=sid, title=title, created_at=now, updated_at=now)
        with self._lock:
            self._sessions[sid] = meta
            self._msg_file(sid).write_text("[]", encoding="utf-8")
            self._save_index()
        return meta

    def get(self, session_id: str) -> SessionMeta | None:
        with self._lock:
            return self._sessions.get(session_id)

    def list_all(self) -> list[SessionMeta]:
        with self._lock:
            return sorted(self._sessions.values(), key=lambda s: s.updated_at, reverse=True)

    def update_title(self, session_id: str, title: str) -> None:
        with self._lock:
            if session_id not in self._sessions:
                return
            self._sessions[session_id].title = title
            self._sessions[session_id].updated_at = self._now()
            self._save_index()

    def delete(self, session_id: str) -> bool:
        """删除会话元数据与其消息文件。返回是否存在并删除成功。"""
        with self._lock:
            if session_id not in self._sessions:
                return False
            self._sessions.pop(session_id, None)
            msg_file = self._msg_file(session_id)
            if msg_file.exists():
                msg_file.unlink()
            self._save_index()
            return True

    def update_engine(self, session_id: str, engine: str) -> None:
        with self._lock:
            if session_id not in self._sessions:
                return
            self._sessions[session_id].engine = engine
            self._sessions[session_id].updated_at = self._now()
            self._save_index()

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
            # 自动标题：取第一条用户消息（最多 20 字）
            if role == "user" and meta.title == "新对话":
                meta.title = content[:20] + ("…" if len(content) > 20 else "")
            self._save_index()

    def get_messages(self, session_id: str) -> list[dict]:
        with self._lock:
            msg_file = self._msg_file(session_id)
            if not msg_file.exists():
                return []
            return json.loads(msg_file.read_text(encoding="utf-8"))
