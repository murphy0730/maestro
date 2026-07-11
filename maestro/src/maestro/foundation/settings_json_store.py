"""Concurrency-safe section updates for the shared runtime settings.json."""

import json
import os
import threading
from pathlib import Path
from typing import Any


class SettingsConflictError(Exception):
    pass


class SettingsJsonStore:
    _locks: dict[Path, threading.RLock] = {}
    _locks_guard = threading.Lock()

    def __init__(self, path: Path):
        self.path = Path(path).resolve()
        with self._locks_guard:
            self._lock = self._locks.setdefault(self.path, threading.RLock())

    def read(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                return {"revision": 0}
            try:
                data = json.loads(self.path.read_text("utf-8"))
            except (OSError, json.JSONDecodeError):
                return {"revision": 0}
            data.setdefault("revision", 0)
            return data

    def update_section(self, key: str, value: Any, expected_revision: int | None = None) -> int:
        with self._lock:
            data = self.read()
            revision = int(data.get("revision", 0))
            if expected_revision is not None and expected_revision != revision:
                raise SettingsConflictError(f"settings revision 已从 {expected_revision} 变为 {revision}")
            data[key] = value
            data["revision"] = revision + 1
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
            os.replace(tmp, self.path)
            return revision + 1
