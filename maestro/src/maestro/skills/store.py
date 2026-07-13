from __future__ import annotations
import json
import hashlib
import mimetypes
import shutil
import threading
from pathlib import Path
from maestro.skills.schemas import SkillMeta, SkillTrustRecord, SkillValidationError

# 历史缺陷: 早期导入曾在 SKILL.md 未声明 allowed-tools 时注入默认查询工具集
# (先后两个版本)。磁盘 SKILL.md 不含 frontmatter，无法回读原始声明，故按
# "恰好等于历史注入集" 识别并重置为 [] (自定义声明的技能不受影响)。
_LEGACY_INJECTED_TOOLSETS = (
    frozenset({
        "query_orders", "query_inventory", "query_work_orders",
        "check_kitting", "read_observation",
    }),
    frozenset({
        "query_orders", "query_inventory", "query_work_orders",
        "check_kitting", "read_observation",
        "search_catalog_skills", "search_catalog_connectors",
    }),
)


def package_sha256(body: str, attachments: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    files = {"SKILL.md": body.encode("utf-8"), **attachments}
    for path in sorted(files):
        encoded = path.encode("utf-8")
        content = files[path]
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


class SkillStore:
    def __init__(self, base_dir: Path):
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)
        self._index_path = self._base / "index.json"
        self._trust_path = self._base / "trust.json"
        self._lock = threading.Lock()
        self._index: list[SkillMeta] = []
        self._trust: dict[str, SkillTrustRecord] = {}
        self.version = 0
        self._load_index()
        self._load_trust()

    def _load_index(self) -> None:
        if self._index_path.exists():
            data = json.loads(self._index_path.read_text("utf-8"))
            self._index = [SkillMeta(**m) for m in data]
            migrated = False
            for meta in self._index:
                directory = self._skill_dir(meta.name)
                body_path = directory / "SKILL.md"
                if not body_path.is_file():
                    continue
                attachments = {
                    str(path.relative_to(directory)): path.read_bytes()
                    for path in directory.rglob("*")
                    if path.is_file() and path.name != "SKILL.md"
                }
                body = body_path.read_text("utf-8")
                expected_hash = package_sha256(body, attachments)
                file_count = 1 + len(attachments)
                unpacked_bytes = len(body.encode("utf-8")) + sum(len(value) for value in attachments.values())
                if (meta.package_sha256 != expected_hash or meta.file_count != file_count
                        or meta.bytes != unpacked_bytes):
                    meta.package_sha256 = expected_hash
                    meta.file_count = file_count
                    meta.bytes = unpacked_bytes
                    migrated = True
                if meta.allowed_tools and frozenset(meta.allowed_tools) in _LEGACY_INJECTED_TOOLSETS:
                    meta.allowed_tools = []
                    migrated = True
            if migrated:
                self._save_index()

    def _save_index(self) -> None:
        tmp = self._index_path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps([m.model_dump() for m in self._index], ensure_ascii=False, indent=2),
            "utf-8",
        )
        tmp.replace(self._index_path)
        self.version += 1

    def _load_trust(self) -> None:
        if self._trust_path.exists():
            data = json.loads(self._trust_path.read_text("utf-8"))
            self._trust = {name: SkillTrustRecord(**record) for name, record in data.items()}

    def _save_trust(self) -> None:
        tmp = self._trust_path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(
                {name: record.model_dump(mode="json") for name, record in self._trust.items()},
                ensure_ascii=False,
                indent=2,
            ),
            "utf-8",
        )
        tmp.replace(self._trust_path)

    def list_all(self) -> list[SkillMeta]:
        with self._lock:
            return sorted(self._index, key=lambda m: m.added_at, reverse=True)

    def get(self, name: str) -> SkillMeta | None:
        with self._lock:
            return next((m for m in self._index if m.name == name), None)

    def update_localization(
        self,
        name: str,
        summary_zh: str | None,
        description_zh: str | None,
    ) -> bool:
        """Backfill catalog localization without changing the installed package."""
        with self._lock:
            meta = next((item for item in self._index if item.name == name), None)
            if meta is None:
                raise KeyError(name)
            if meta.summary_zh == summary_zh and meta.description_zh == description_zh:
                return False
            meta.summary_zh = summary_zh
            meta.description_zh = description_zh
            self._save_index()
            return True

    def _skill_dir(self, name: str) -> Path:
        return self._base / name

    def get_body(self, name: str) -> str:
        with self._lock:
            if not any(m.name == name for m in self._index):
                raise KeyError(name)
            return (self._skill_dir(name) / "SKILL.md").read_text("utf-8")

    def save(self, meta: SkillMeta, body: str, attachments: dict[str, bytes]) -> None:
        with self._lock:
            if any(m.name == meta.name for m in self._index):
                raise KeyError(meta.name)
            current_hash = package_sha256(body, attachments)
            if meta.package_sha256 and meta.package_sha256 != current_hash:
                raise SkillValidationError("技能包 hash 与内容不一致")
            meta.package_sha256 = current_hash
            d = self._skill_dir(meta.name)
            d.mkdir(parents=True, exist_ok=True)
            (d / "SKILL.md").write_text(body, "utf-8")
            for rel, content in attachments.items():
                target = d / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            self._index.append(meta)
            self._save_index()

    def replace(self, meta: SkillMeta, body: str, attachments: dict[str, bytes]) -> None:
        """Atomically replace an installed skill while preserving no old trust."""
        import tempfile
        with self._lock:
            index = next((i for i, item in enumerate(self._index) if item.name == meta.name), None)
            if index is None:
                raise KeyError(meta.name)
            current_hash = package_sha256(body, attachments)
            meta.package_sha256 = current_hash
            target = self._skill_dir(meta.name)
            temp = Path(tempfile.mkdtemp(prefix=f".{meta.name}-", dir=self._base))
            backup = self._base / f".{meta.name}.old"
            try:
                (temp / "SKILL.md").write_text(body, "utf-8")
                for rel, content in attachments.items():
                    path = temp / rel
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(content)
                if backup.exists():
                    shutil.rmtree(backup)
                target.replace(backup)
                temp.replace(target)
                shutil.rmtree(backup)
            except Exception:
                if temp.exists():
                    shutil.rmtree(temp)
                if backup.exists() and not target.exists():
                    backup.replace(target)
                raise
            self._index[index] = meta
            if self._trust.pop(meta.name, None) is not None:
                self._save_trust()
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
            if self._trust.pop(name, None) is not None:
                self._save_trust()
            self._save_index()
            return True

    def trust(self, name: str, package_hash: str, principal_id: str = "local-user") -> SkillTrustRecord:
        with self._lock:
            meta = next((item for item in self._index if item.name == name), None)
            if meta is None:
                raise KeyError(name)
            if not meta.package_sha256 or meta.package_sha256 != package_hash:
                raise SkillValidationError("技能包已变化，请重新检查后再信任当前版本")
            record = SkillTrustRecord(
                skill_name=name,
                package_sha256=package_hash,
                principal_id=principal_id,
            )
            self._trust[name] = record
            self._save_trust()
            return record

    def revoke_trust(self, name: str) -> bool:
        with self._lock:
            removed = self._trust.pop(name, None) is not None
            if removed:
                self._save_trust()
            return removed

    def trust_status(self, name: str) -> dict:
        with self._lock:
            meta = next((item for item in self._index if item.name == name), None)
            if meta is None:
                raise KeyError(name)
            record = self._trust.get(name)
            valid = bool(record and record.package_sha256 == meta.package_sha256)
            return {
                "level": "user_trusted" if valid else "untrusted",
                "valid": valid,
                "package_sha256": meta.package_sha256,
                "principal_id": record.principal_id if valid else None,
                "trusted_at": record.trusted_at.isoformat() if valid else None,
            }

    def is_trusted(self, name: str, package_hash: str | None = None) -> bool:
        with self._lock:
            meta = next((item for item in self._index if item.name == name), None)
            record = self._trust.get(name)
            expected = package_hash or (meta.package_sha256 if meta else "")
            return bool(meta and record and expected and record.package_sha256 == expected == meta.package_sha256)

    def snapshot_files(self, name: str) -> dict[str, bytes]:
        with self._lock:
            meta = next((item for item in self._index if item.name == name), None)
            if meta is None:
                raise KeyError(name)
            directory = self._skill_dir(name)
            files = {
                str(path.relative_to(directory)): path.read_bytes()
                for path in directory.rglob("*")
                if path.is_file()
            }
            body = files.pop("SKILL.md").decode("utf-8")
            if package_sha256(body, files) != meta.package_sha256:
                raise SkillValidationError("技能包落盘内容已变化，信任已失效")
            return {"SKILL.md": body.encode("utf-8"), **files}

    def read_attachment(self, name: str, rel_path: str, max_bytes: int = 65536) -> dict:
        with self._lock:
            d = self._skill_dir(name)
            target = (d / rel_path).resolve()
            if not target.is_relative_to(d.resolve()):
                raise SkillValidationError(f"路径越界: {rel_path}")
            if not target.is_file():
                raise SkillValidationError(f"附属文件不存在: {rel_path}")
            size = target.stat().st_size
            content = target.read_bytes()[:max_bytes]
            return {
                "path": rel_path,
                "bytes": content,
                "size_bytes": size,
                "truncated": size > max_bytes,
                "content_type": mimetypes.guess_type(target.name)[0] or "application/octet-stream",
            }

    def list_attachments(self, name: str) -> list[dict]:
        """列出技能包附件 (排除 SKILL.md)，供 list_skill_files 工具发现文件。
        返回 [{path, size_bytes}]——是**大小**不是内容;内容按需经 read_attachment 读取。"""
        with self._lock:
            d = self._skill_dir(name)
            if not d.exists():
                return []
            out = []
            for p in sorted(d.rglob("*")):
                if p.is_file() and p.name != "SKILL.md":
                    out.append(
                        {"path": str(p.relative_to(d)), "size_bytes": p.stat().st_size}
                    )
            return out

    def routable(self) -> list[SkillMeta]:
        with self._lock:
            return [m for m in self._index if not m.disable_model_invocation]

    def routing_examples(self) -> dict[str, list[str]]:
        with self._lock:
            return {f"skill:{m.name}": list(m.when_to_use)
                    for m in self._index if not m.disable_model_invocation and m.when_to_use}
