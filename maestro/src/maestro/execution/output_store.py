"""Shell 输出的文件化存储；模型只接收不透明引用。"""

import hashlib
import json
import secrets
import shutil
from pathlib import Path


class OutputWriter:
    def __init__(self, store: "FileOutputStore", session_id: str, ref: str, directory: Path):
        self.store = store
        self.session_id = session_id
        self.ref = ref
        self.directory = directory
        self._files = {
            name: (directory / f"{name}.log").open("wb") for name in ("stdout", "stderr")
        }
        self._hashes = {name: hashlib.sha256() for name in self._files}
        self._sizes = {name: 0 for name in self._files}
        self._preview = bytearray()

    def write(self, stream: str, data: bytes) -> None:
        if stream not in self._files:
            raise ValueError("stream 必须是 stdout 或 stderr")
        self._files[stream].write(data)
        self._files[stream].flush()
        self._hashes[stream].update(data)
        self._sizes[stream] += len(data)
        remaining = self.store.inline_max_bytes - len(self._preview)
        if remaining > 0:
            self._preview.extend(data[:remaining])

    def finish(self, extra: dict | None = None) -> dict:
        for file in self._files.values():
            file.close()
        meta = {
            "output_ref": self.ref,
            "session_id": self.session_id,
            "stdout_bytes": self._sizes["stdout"],
            "stderr_bytes": self._sizes["stderr"],
            "original_bytes": sum(self._sizes.values()),
            "sha256": {name: digest.hexdigest() for name, digest in self._hashes.items()},
            "preview": self._preview.decode("utf-8", errors="replace"),
            **(extra or {}),
        }
        (self.directory / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {key: value for key, value in meta.items() if key != "session_id"}


class FileOutputStore:
    def __init__(self, root: Path, inline_max_bytes: int = 8192, max_entries: int = 200):
        self.root = Path(root)
        self.inline_max_bytes = inline_max_bytes
        self.max_entries = max_entries
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, session_id: str) -> OutputWriter:
        self._evict()
        ref = f"out-{secrets.token_urlsafe(18)}"
        directory = self.root / ref
        directory.mkdir(mode=0o700)
        return OutputWriter(self, session_id, ref, directory)

    def _evict(self) -> None:
        """FIFO 淘汰: 保证新建后目录数不超过 max_entries, 防止磁盘无限增长。"""
        entries = [d for d in self.root.iterdir() if d.is_dir() and d.name.startswith("out-")]
        surplus = len(entries) - self.max_entries + 1
        if surplus <= 0:
            return
        entries.sort(key=lambda d: d.stat().st_mtime)
        for stale in entries[:surplus]:
            shutil.rmtree(stale, ignore_errors=True)

    def read(self, ref: str, session_id: str, stream: str, offset: int = 0, limit: int = 8192) -> dict:
        if not ref.startswith("out-") or any(char in ref for char in "/\\."):
            raise ValueError("非法输出引用")
        if stream not in ("stdout", "stderr"):
            raise ValueError("stream 必须是 stdout 或 stderr")
        limit = max(1, min(limit, 65536))
        offset = max(0, offset)
        directory = self.root / ref
        meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
        if meta["session_id"] != session_id:
            raise PermissionError("输出引用不属于当前会话")
        path = directory / f"{stream}.log"
        with path.open("rb") as file:
            file.seek(offset)
            data = file.read(limit)
        total = path.stat().st_size
        return {
            "output_ref": ref,
            "stream": stream,
            "offset": offset,
            "limit": limit,
            "total": total,
            "data": data.decode("utf-8", errors="replace"),
            "has_more": offset + len(data) < total,
        }
