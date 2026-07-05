"""内存向量库 (查询引擎 RAG 用)。

初始版本: 文本 chunk → 嵌入 → 存内存，查询时按余弦相似度取 top-k。
接口设计成可替换为 Chroma / pgvector 等持久化向量库 (业务侧只依赖
add_texts / add_documents / search / delete_document 等方法)。

文档级管理 (add_documents/delete_document/list_documents) 支撑前端对知识库
文档的增删改查: 每个 chunk 记 doc_id，按 doc_id 成组增删。

TODO(v0.2): rerank、混合检索、持久化与增量更新。
"""

import logging
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from scheduling_platform.foundation.embedding import EmbeddingClient, cosine_similarity

logger = logging.getLogger(__name__)


@dataclass
class Document:
    """知识库文档片段。"""

    text: str
    metadata: dict = field(default_factory=dict)  # 来源: doc / doc_id / section ...


@dataclass
class ScoredDocument:
    document: Document
    score: float


@runtime_checkable
class VectorStoreProtocol(Protocol):
    """向量库契约。业务侧 (ingestor/retriever) 只依赖此协议，可换内存 / Chroma 等实现。"""

    @property
    def available(self) -> bool: ...

    async def add_documents(
        self, doc_id: str, texts: list[str], metadatas: list[dict] | None = None
    ) -> int: ...

    def delete_document(self, doc_id: str) -> int: ...

    def rename_document(self, doc_id: str, name: str) -> int: ...

    async def search(self, query: str, top_k: int = 3) -> list[ScoredDocument]: ...

    def chunk_count(self, doc_id: str) -> int: ...


class VectorStore:
    """内存向量库。嵌入不可用时退化为空检索 (调用方据此如实说明检索不到)。"""

    def __init__(self, embedder: EmbeddingClient):
        self._embedder = embedder
        self._docs: list[Document] = []
        self._vectors: list[list[float]] = []

    @property
    def available(self) -> bool:
        return self._embedder.available

    def __len__(self) -> int:
        return len(self._docs)

    async def add_texts(self, texts: list[str], metadatas: list[dict] | None = None) -> None:
        """把文本片段嵌入并入库。metadatas 与 texts 等长 (来源信息)。"""
        if not texts:
            return
        metadatas = metadatas or [{} for _ in texts]
        vectors = await self._embedder.embed(texts)
        for text, meta, vec in zip(texts, metadatas, vectors):
            self._docs.append(Document(text=text, metadata=meta))
            self._vectors.append(vec)
        logger.info("[VECTORSTORE] 入库 %d 片段，总计 %d", len(texts), len(self._docs))

    async def add_documents(
        self, doc_id: str, texts: list[str], metadatas: list[dict] | None = None
    ) -> int:
        """按 doc_id 成组入库。每个片段的 metadata 注入 doc_id，便于成组删除。

        返回实际入库的片段数。若 doc_id 已存在，调用方应先 delete_document 再入库
        (KnowledgeIngestor 的 update 即如此)。
        """
        if not texts:
            return 0
        metadatas = metadatas or [{} for _ in texts]
        stamped = [{**m, "doc_id": doc_id} for m in metadatas]
        await self.add_texts(texts, stamped)
        return len(texts)

    def delete_document(self, doc_id: str) -> int:
        """删除某文档的全部片段，返回删除数。"""
        keep_docs: list[Document] = []
        keep_vecs: list[list[float]] = []
        removed = 0
        for doc, vec in zip(self._docs, self._vectors):
            if doc.metadata.get("doc_id") == doc_id:
                removed += 1
            else:
                keep_docs.append(doc)
                keep_vecs.append(vec)
        self._docs = keep_docs
        self._vectors = keep_vecs
        if removed:
            logger.info("[VECTORSTORE] 删除文档 %s 的 %d 片段", doc_id, removed)
        return removed

    def chunk_count(self, doc_id: str) -> int:
        """某文档当前的片段数。"""
        return sum(1 for d in self._docs if d.metadata.get("doc_id") == doc_id)

    def rename_document(self, doc_id: str, name: str) -> int:
        """改名: 更新该文档全部片段的 doc 元数据，返回受影响片段数。"""
        affected = 0
        for doc in self._docs:
            if doc.metadata.get("doc_id") == doc_id:
                doc.metadata["doc"] = name
                affected += 1
        return affected

    async def search(self, query: str, top_k: int = 3) -> list[ScoredDocument]:
        """按余弦相似度检索 top-k 相关片段。库为空或嵌入不可用时返回 []。"""
        if not self._docs:
            return []
        qv = (await self._embedder.embed([query]))[0]
        scored = [
            ScoredDocument(doc, cosine_similarity(qv, vec))
            for doc, vec in zip(self._docs, self._vectors)
        ]
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:top_k]
