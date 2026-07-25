"""Version 3 generic session persistence; older session files are never migrated."""

import json
import os
import re
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class SessionMeta(BaseModel):
    schema_version: Literal[3] = 3
    session_id: str
    title: str = "新对话"
    created_at: str
    updated_at: str
    message_count: int = 0
    active_run_id: str | None = None


class StoredMessage(BaseModel):
    role: str
    content: str
    ts: str
    artifact_ids: list[str] = Field(default_factory=list)
    skill_names: list[str] = Field(default_factory=list)
    run_id: str | None = None


class SessionStore:
    def __init__(self, base_dir: Path | str):
        self._dir = Path(base_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index_file = self._dir / "index.json"
        self._sessions: dict[str, SessionMeta] = {}
        self._lock = threading.Lock()
        self._load_index()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def _load_index(self) -> None:
        if not self._index_file.exists():
            return
        try:
            data = json.loads(self._index_file.read_text("utf-8"))
            sessions = [SessionMeta.model_validate(item) for item in data]
        except Exception:
            return
        self._sessions = {item.session_id: item for item in sessions}

    def _save_index(self) -> None:
        data = sorted(self._sessions.values(), key=lambda item: item.updated_at, reverse=True)
        self._index_file.write_text(json.dumps([item.model_dump() for item in data], ensure_ascii=False), "utf-8")

    def _message_file(self, session_id: str) -> Path:
        if re.fullmatch(r"[A-Za-z0-9_-]+", session_id) is None:
            raise ValueError("invalid session identifier")
        return self._dir / f"{session_id}.json"

    def _summary_file(self, session_id: str) -> Path:
        """Rolling summaries live beside the messages so get_messages keeps its shape."""
        return self._message_file(session_id).with_suffix(".summary.json")

    def create(self, title: str = "新对话") -> SessionMeta:
        now = self._now()
        meta = SessionMeta(session_id=uuid.uuid4().hex, title=title, created_at=now, updated_at=now)
        with self._lock:
            self._sessions[meta.session_id] = meta
            self._message_file(meta.session_id).write_text("[]", "utf-8")
            self._save_index()
        return meta

    def ensure(self, session_id: str) -> SessionMeta:
        with self._lock:
            existing = self._sessions.get(session_id)
            if existing is not None:
                return existing
            now = self._now()
            meta = SessionMeta(session_id=session_id, created_at=now, updated_at=now)
            self._sessions[session_id] = meta
            self._message_file(session_id).write_text("[]", "utf-8")
            self._save_index()
            return meta

    def get(self, session_id: str) -> SessionMeta | None:
        return self._sessions.get(session_id)

    def list_all(self) -> list[SessionMeta]:
        return sorted(self._sessions.values(), key=lambda item: item.updated_at, reverse=True)

    def update_title(self, session_id: str, title: str) -> None:
        with self._lock:
            meta = self._sessions.get(session_id)
            if meta is not None:
                meta.title, meta.updated_at = title, self._now()
                self._save_index()

    def set_active_run(self, session_id: str, run_id: str | None) -> None:
        with self._lock:
            meta = self._sessions.get(session_id)
            if meta is not None:
                meta.active_run_id, meta.updated_at = run_id, self._now()
                self._save_index()

    def delete(self, session_id: str) -> bool:
        with self._lock:
            if self._sessions.pop(session_id, None) is None:
                return False
            self._message_file(session_id).unlink(missing_ok=True)
            summary = self._summary_file(session_id)
            summary.unlink(missing_ok=True)
            # A process killed between write and replace leaves the sidecar's tmp behind.
            summary.with_name(f"{summary.name}.tmp").unlink(missing_ok=True)
            self._save_index()
            return True

    def append_message(self, session_id: str, role: str, content: str, *, artifact_ids: list[str] | None = None, skill_names: list[str] | None = None, run_id: str | None = None) -> None:
        with self._lock:
            meta = self._sessions.get(session_id)
            if meta is None:
                return
            path = self._message_file(session_id)
            messages = json.loads(path.read_text("utf-8")) if path.exists() else []
            messages.append(StoredMessage(role=role, content=content, ts=self._now(), artifact_ids=artifact_ids or [], skill_names=skill_names or [], run_id=run_id).model_dump())
            path.write_text(json.dumps(messages, ensure_ascii=False), "utf-8")
            meta.message_count, meta.updated_at = len(messages), self._now()
            if role == "user" and meta.title == "新对话":
                meta.title = content[:20] + ("…" if len(content) > 20 else "")
            self._save_index()

    def append_run_final(self, session_id: str, run_id: str, content: str) -> None:
        """Persist a terminal assistant answer once, even if execution is resumed."""
        with self._lock:
            meta = self._sessions.get(session_id)
            if meta is None:
                return
            path = self._message_file(session_id)
            messages = json.loads(path.read_text("utf-8")) if path.exists() else []
            if any(message.get("role") == "assistant" and message.get("run_id") == run_id for message in messages):
                return
            messages.append(StoredMessage(role="assistant", content=content, ts=self._now(), run_id=run_id).model_dump())
            path.write_text(json.dumps(messages, ensure_ascii=False), "utf-8")
            meta.message_count, meta.updated_at = len(messages), self._now()
            self._save_index()

    def get_messages(self, session_id: str) -> list[dict]:
        path = self._message_file(session_id)
        return json.loads(path.read_text("utf-8")) if path.exists() else []

    def get_summary(self, session_id: str) -> tuple[str, int]:
        """Return the stored rolling summary and how many stale turns it already covers."""
        path = self._summary_file(session_id)
        if not path.exists():
            return "", 0
        try:
            data = json.loads(path.read_text("utf-8"))
            return str(data["summary"]), int(data["summarized_until"])
        except Exception:
            # A damaged sidecar only costs one re-summarization, never a Run.
            return "", 0

    def set_summary(self, session_id: str, summary: str, summarized_until: int) -> None:
        with self._lock:
            target = self._summary_file(session_id)
            temporary = target.with_name(f"{target.name}.tmp")
            payload = json.dumps(
                {"summary": summary, "summarized_until": summarized_until}, ensure_ascii=False
            ).encode("utf-8")
            fd = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
            try:
                if os.write(fd, payload) != len(payload):
                    raise OSError("incomplete session summary write")
                os.fsync(fd)
            finally:
                os.close(fd)
            temporary.replace(target)
