from __future__ import annotations
import json
import shutil
import threading
from pathlib import Path
from scheduling_platform.skills.schemas import SkillMeta, SkillValidationError


class SkillStore:
    def __init__(self, base_dir: Path):
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)
        self._index_path = self._base / "index.json"
        self._lock = threading.Lock()
        self._index: list[SkillMeta] = []
        self.version = 0
        self._load_index()

    def _load_index(self) -> None:
        if self._index_path.exists():
            data = json.loads(self._index_path.read_text("utf-8"))
            self._index = [SkillMeta(**m) for m in data]

    def _save_index(self) -> None:
        self._index_path.write_text(
            json.dumps([m.model_dump() for m in self._index], ensure_ascii=False, indent=2),
            "utf-8",
        )
        self.version += 1

    def list_all(self) -> list[SkillMeta]:
        with self._lock:
            return sorted(self._index, key=lambda m: m.added_at, reverse=True)

    def get(self, name: str) -> SkillMeta | None:
        with self._lock:
            return next((m for m in self._index if m.name == name), None)

    def _skill_dir(self, name: str) -> Path:
        return self._base / name

    def get_body(self, name: str) -> str:
        return (self._skill_dir(name) / "SKILL.md").read_text("utf-8")

    def save(self, meta: SkillMeta, body: str, attachments: dict[str, bytes]) -> None:
        with self._lock:
            if any(m.name == meta.name for m in self._index):
                raise KeyError(meta.name)
            d = self._skill_dir(meta.name)
            d.mkdir(parents=True, exist_ok=True)
            (d / "SKILL.md").write_text(body, "utf-8")
            for rel, content in attachments.items():
                target = d / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            self._index.append(meta)
            self._save_index()

    def delete(self, name: str) -> bool:
        with self._lock:
            before = len(self._index)
            self._index = [m for m in self._index if m.name != name]
            if len(self._index) == before:
                return False
            d = self._skill_dir(name)
            if d.exists():
                shutil.rmtree(d)
            self._save_index()
            return True

    def read_attachment(self, name: str, rel_path: str, max_bytes: int = 65536) -> dict:
        d = self._skill_dir(name)
        target = (d / rel_path).resolve()
        if not target.is_relative_to(d.resolve()):
            raise SkillValidationError(f"路径越界: {rel_path}")
        if not target.is_file():
            raise SkillValidationError(f"附属文件不存在: {rel_path}")
        content = target.read_bytes()[:max_bytes]
        return {"path": rel_path, "bytes": content}

    def routable(self) -> list[SkillMeta]:
        with self._lock:
            return [m for m in self._index if not m.disable_model_invocation]

    def routing_examples(self) -> dict[str, list[str]]:
        with self._lock:
            return {f"skill:{m.name}": list(m.when_to_use)
                    for m in self._index if not m.disable_model_invocation and m.when_to_use}
