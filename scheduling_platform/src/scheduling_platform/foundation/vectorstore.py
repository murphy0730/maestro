"""内存向量库 (查询引擎 RAG 用)。

初始版本: 文本 chunk → 嵌入 → 存内存，查询时按余弦相似度取 top-k。
接口设计成可替换为 Chroma / pgvector 等持久化向量库 (业务侧只依赖
add_texts / search 两个方法)。

TODO(v0.2): rerank、混合检索、持久化与增量更新。
"""

import logging
from dataclasses import dataclass, field

from scheduling_platform.foundation.embedding import EmbeddingClient, cosine_similarity

logger = logging.getLogger(__name__)


@dataclass
class Document:
    """知识库文档片段。"""

    text: str
    metadata: dict = field(default_factory=dict)  # 来源: doc_name / section ...


@dataclass
class ScoredDocument:
    document: Document
    score: float


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
