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
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
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

    def update_title_if_current(
        self, session_id: str, title: str, expected_titles: set[str]
    ) -> None:
        """Update an automatically assigned title without overwriting a later rename."""
        with self._lock:
            meta = self._sessions.get(session_id)
            if meta is not None and meta.title in expected_titles:
                meta.title, meta.updated_at = title, self._now()
                self._save_index()

    def set_active_run(self, session_id: str, run_id: str | None) -> None:
        with self._lock:
            meta = self._sessions.get(session_id)
            if meta is not None:
                meta.active_run_id, meta.updated_at = run_id, self._now()
                self._save_index()

    def clear_active_run(self, session_id: str, run_id: str) -> None:
        """Clear a terminal Run without retiring a newer Run for the same session."""
        with self._lock:
            meta = self._sessions.get(session_id)
            if meta is not None and meta.active_run_id == run_id:
                meta.active_run_id, meta.updated_at = None, self._now()
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

    @staticmethod
    def _ensure_ids(messages: list[dict]) -> bool:
        """Give pre-id messages a stable identifier; report whether anything changed."""
        assigned = False
        for message in messages:
            if not message.get("id"):
                message["id"] = uuid.uuid4().hex
                assigned = True
        return assigned

    def get_messages(self, session_id: str) -> list[dict]:
        path = self._message_file(session_id)
        messages = json.loads(path.read_text("utf-8")) if path.exists() else []
        # Sessions written before messages carried ids are migrated on first read, so
        # the ids the frontend deletes by stay stable. Reads stay lock-free afterwards.
        if not self._ensure_ids(messages):
            return messages
        # Migrating means writing back, and the snapshot read above is already stale:
        # an append landing in between would be erased wholesale. Re-read under the
        # lock so what gets written is always the current file.
        with self._lock:
            messages = json.loads(path.read_text("utf-8")) if path.exists() else []
            if self._ensure_ids(messages):
                path.write_text(json.dumps(messages, ensure_ascii=False), "utf-8")
            return messages

    def delete_message(self, session_id: str, message_id: str, *, cascade: bool = False) -> list[str] | None:
        """Delete one message — plus its turn's replies when cascading — and drop the summary.

        Returns the ids actually removed, or None when the session or message is unknown.
        """
        with self._lock:
            meta = self._sessions.get(session_id)
            if meta is None:
                return None
            path = self._message_file(session_id)
            messages = json.loads(path.read_text("utf-8")) if path.exists() else []
            self._ensure_ids(messages)
            index = next((position for position, message in enumerate(messages) if message["id"] == message_id), None)
            if index is None:
                return None
            end = index + 1
            if cascade and messages[index].get("role") == "user":
                # Only assistant replies belong to the turn; a system message ends it.
                while end < len(messages) and messages[end].get("role") == "assistant":
                    end += 1
            removed = [message["id"] for message in messages[index:end]]
            del messages[index:end]
            path.write_text(json.dumps(messages, ensure_ascii=False), "utf-8")
            meta.message_count, meta.updated_at = len(messages), self._now()
            summary = self._summary_file(session_id)
            summary.unlink(missing_ok=True)
            summary.with_name(f"{summary.name}.tmp").unlink(missing_ok=True)
            self._save_index()
            return removed

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
