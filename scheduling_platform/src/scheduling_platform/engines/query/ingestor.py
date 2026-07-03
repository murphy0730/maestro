"""知识摄取服务 —— RAG 的「写」侧，支撑文档增删改查。

编排一条管线: 字节流 → LoaderRegistry (解析为文本) → Chunker (切片) →
VectorStore.add_documents (嵌入入库)。同时维护一份文档目录 (doc_id → KnowledgeDoc)
作为前端列表的数据源。

嵌入不可用 (未配置 EMBED_MODEL) 时仍登记文档，但 status=failed、chunk_count=0，
检索为空 —— 与平台整体的离线降级哲学一致 (如实告知不臆造)。

目录是内存态: 进程重启后靠 add_directory(knowledge_dir) 从磁盘重建种子知识库。
上传的文件也落盘到 knowledge_dir，重启后一并重建。
TODO(v0.2): 目录持久化 (sqlite/json)、增量更新、并发入库。
"""

import logging
import re
import uuid
from pathlib import Path

from scheduling_platform.engines.query.schemas import KnowledgeDoc
from scheduling_platform.foundation.chunking import Chunker
from scheduling_platform.foundation.loaders import LoaderRegistry, UnsupportedFileType
from scheduling_platform.foundation.vectorstore import VectorStore

logger = logging.getLogger(__name__)

_SAFE_NAME = re.compile(r"[^\w.\-]+", re.UNICODE)


class DocumentNotFound(Exception):
    """按 doc_id 未找到文档。"""


def _safe_filename(name: str) -> str:
    """清洗文件名，防目录穿越 (仅保留基名 + 白名单字符)。"""
    base = Path(name).name
    cleaned = _SAFE_NAME.sub("_", base).strip("._")
    return cleaned or "untitled"


class KnowledgeIngestor:
    """知识库摄取 + 文档目录管理。"""

    def __init__(
        self,
        store: VectorStore,
        loaders: LoaderRegistry,
        chunker: Chunker,
        knowledge_dir: Path,
    ):
        self._store = store
        self._loaders = loaders
        self._chunker = chunker
        self._dir = Path(knowledge_dir)
        self._catalog: dict[str, KnowledgeDoc] = {}
        self._seeded = False

    @property
    def supported_extensions(self) -> list[str]:
        return self._loaders.supported_extensions

    # ── 查 ────────────────────────────────────────────────
    def list_docs(self) -> list[KnowledgeDoc]:
        """按加入时间倒序列出全部文档。"""
        return sorted(self._catalog.values(), key=lambda d: d.added_at, reverse=True)

    def get(self, doc_id: str) -> KnowledgeDoc:
        doc = self._catalog.get(doc_id)
        if doc is None:
            raise DocumentNotFound(doc_id)
        return doc

    # ── 增 ────────────────────────────────────────────────
    async def add_upload(self, filename: str, data: bytes) -> KnowledgeDoc:
        """摄取一个上传文件 (字节流)。落盘 + 入库 + 登记目录。"""
        if not self._loaders.supports(filename):
            raise UnsupportedFileType(
                Path(filename).suffix.lower(), self._loaders.supported_extensions
            )
        doc_id = f"kb_{uuid.uuid4().hex[:10]}"
        return await self._ingest(doc_id, filename, data, persist=True)

    # ── 改 ────────────────────────────────────────────────
    async def replace(self, doc_id: str, filename: str, data: bytes) -> KnowledgeDoc:
        """换内容: 删旧片段 + 重新入库到同一 doc_id。"""
        self.get(doc_id)  # 不存在则抛 DocumentNotFound
        if not self._loaders.supports(filename):
            raise UnsupportedFileType(
                Path(filename).suffix.lower(), self._loaders.supported_extensions
            )
        self._store.delete_document(doc_id)
        return await self._ingest(doc_id, filename, data, persist=True)

    def rename(self, doc_id: str, name: str) -> KnowledgeDoc:
        """仅改显示名 (不动内容/向量)。"""
        doc = self.get(doc_id)
        new_name = name.strip() or doc.name
        doc.name = new_name
        self._store.rename_document(doc_id, new_name)
        return doc

    # ── 删 ────────────────────────────────────────────────
    def remove(self, doc_id: str) -> int:
        """删除文档: 移除片段 + 目录条目 + 磁盘文件。返回删除的片段数。"""
        self.get(doc_id)
        removed = self._store.delete_document(doc_id)
        self._catalog.pop(doc_id, None)
        self._delete_file(doc_id)
        return removed

    # ── 启动种子加载 ──────────────────────────────────────
    async def seed_from_directory(self) -> None:
        """启动/首检时从 knowledge_dir 加载全部受支持文件 (仅一次)。"""
        if self._seeded:
            return
        self._seeded = True
        if not self._dir.exists():
            logger.warning("[INGESTOR] 知识库目录不存在: %s", self._dir)
            return
        for path in sorted(self._dir.iterdir()):
            if not path.is_file() or not self._loaders.supports(path.name):
                continue
            # 种子文件 doc_id 由文件名派生，保证重启重建幂等
            doc_id = f"seed_{path.stem}"
            if doc_id in self._catalog:
                continue
            try:
                await self._ingest(doc_id, path.name, path.read_bytes(), persist=False)
            except Exception:  # noqa: BLE001 — 单个种子文件失败不阻断其余
                logger.exception("[INGESTOR] 种子文件加载失败: %s", path.name)
        logger.info("[INGESTOR] 种子知识库加载完成，共 %d 篇", len(self._catalog))

    # ── 内部 ──────────────────────────────────────────────
    async def _ingest(self, doc_id: str, filename: str, data: bytes, persist: bool) -> KnowledgeDoc:
        text = self._loaders.load(data, filename)
        chunks = self._chunker.split(text)
        chunk_count = 0
        status = "ready"
        if self._store.available and chunks:
            texts = [c for c, _ in chunks]
            metas = [{**m, "doc": filename} for _, m in chunks]
            chunk_count = await self._store.add_documents(doc_id, texts, metas)
        elif not self._store.available:
            status = "failed"  # 嵌入未配置：登记但不入库
            logger.info("[INGESTOR] 嵌入不可用，文档 %s 仅登记不入库", filename)

        if persist:
            self._write_file(doc_id, filename, data)

        doc = KnowledgeDoc(
            doc_id=doc_id,
            name=filename,
            type=Path(filename).suffix.lower().lstrip("."),
            chunk_count=chunk_count,
            bytes=len(data),
            status=status,
        )
        self._catalog[doc_id] = doc
        return doc

    def _stored_path(self, doc_id: str, filename: str) -> Path:
        # 以 doc_id 作前缀落盘，避免不同文档同名覆盖
        return self._dir / f"{doc_id}__{_safe_filename(filename)}"

    def _write_file(self, doc_id: str, filename: str, data: bytes) -> None:
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            self._delete_file(doc_id)  # 换内容时清掉旧文件
            self._stored_path(doc_id, filename).write_bytes(data)
        except OSError:
            logger.exception("[INGESTOR] 落盘失败: %s", filename)

    def _delete_file(self, doc_id: str) -> None:
        for path in self._dir.glob(f"{doc_id}__*"):
            try:
                path.unlink()
            except OSError:
                logger.warning("[INGESTOR] 删除文件失败: %s", path)
