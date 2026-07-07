"""Chroma 持久化向量库 (查询引擎 RAG 用)。

与 `vectorstore.VectorStore` (内存实现) 满足同一 `VectorStoreProtocol`，但用
chromadb.PersistentClient 落盘，进程重启后向量不丢失。

嵌入仍由外部 `EmbeddingClient` 自算 (bring-your-own-vectors)，Chroma 只当索引/
持久层 —— 与路由层共用同一套嵌入配置，降级语义 (available 绑定 embed_available) 不变。

幂等入库: chunk id = f"{doc_id}:{sha1(text)}"，内容寻址。重启重新播种时内容未变的
chunk 不再嵌入 (跳过重嵌是持久化的收益来源)；种子文件被编辑时，消失的旧 chunk 被剪枝。

TODO(v0.2): rerank、混合检索、并发入库。
"""

import hashlib
import logging
from pathlib import Path

from maestro.foundation.embedding import EmbeddingClient
from maestro.foundation.vectorstore import Document, ScoredDocument

logger = logging.getLogger(__name__)

_COLLECTION = "knowledge"
# 单次 add 分批上限: 既避开 Chroma 的 max batch (SQLite 变量数, 约 5461)，
# 也把单次 embedding 请求的输入条数压在常见服务端上限内。
_ADD_BATCH = 1000


def _chunk_id(doc_id: str, text: str) -> str:
    """内容寻址 id: 同 doc 内容不变则 id 不变，支撑幂等入库。"""
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    return f"{doc_id}:{digest}"


def _clean_meta(meta: dict) -> dict:
    """Chroma 元数据仅接受 str/int/float/bool，剔除 None、其余转字符串。"""
    out: dict = {}
    for k, v in meta.items():
        if v is None:
            continue
        out[k] = v if isinstance(v, (str, int, float, bool)) else str(v)
    return out


class ChromaVectorStore:
    """Chroma 持久化向量库。嵌入不可用时退化为空检索 (与内存实现一致)。"""

    def __init__(self, embedder: EmbeddingClient, persist_dir: Path):
        import chromadb  # 惰性导入: memory 后端无需 chromadb

        self._embedder = embedder
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        # cosine 空间: 相似度 = 1 - distance；BYO 向量 → 不用 Chroma 自带 embedding function
        self._col = self._client.get_or_create_collection(
            _COLLECTION, metadata={"hnsw:space": "cosine"}, embedding_function=None
        )
        try:
            self._batch = min(_ADD_BATCH, self._client.get_max_batch_size())
        except Exception:  # noqa: BLE001 — 拿不到上限时退回保守值
            self._batch = _ADD_BATCH
        logger.info("[CHROMA] 持久化向量库就绪: %s (已有 %d 片段)", persist_dir, self._col.count())

    @property
    def available(self) -> bool:
        return self._embedder.available

    def _ids_of(self, doc_id: str) -> list[str]:
        return self._col.get(where={"doc_id": doc_id})["ids"]

    async def add_documents(
        self, doc_id: str, texts: list[str], metadatas: list[dict] | None = None
    ) -> int:
        """按 doc_id 幂等入库: 只嵌入并写入库中尚不存在的 chunk，剪枝已消失的旧 chunk。

        返回该文档当前的片段数。
        """
        if not texts:
            # 无内容: 视作清空该 doc (剪枝残留)
            stale = self._ids_of(doc_id)
            if stale:
                self._col.delete(ids=stale)
            return 0
        metadatas = metadatas or [{} for _ in texts]
        # 内容寻址 id 去重 (同一 doc 内重复 chunk 只留一份)
        wanted: dict[str, tuple[str, dict]] = {}
        for text, meta in zip(texts, metadatas):
            cid = _chunk_id(doc_id, text)
            wanted[cid] = (text, _clean_meta({**meta, "doc_id": doc_id}))

        existing = set(self._ids_of(doc_id))
        to_add = [cid for cid in wanted if cid not in existing]
        # 分批: 单次 add 超过 Chroma max batch 会抛错，大文档必须切片
        for i in range(0, len(to_add), self._batch):
            slice_ids = to_add[i:i + self._batch]
            slice_texts = [wanted[cid][0] for cid in slice_ids]
            vectors = await self._embedder.embed(slice_texts)
            self._col.add(
                ids=slice_ids,
                embeddings=vectors,
                documents=slice_texts,
                metadatas=[wanted[cid][1] for cid in slice_ids],
            )
        stale = list(existing - wanted.keys())
        if stale:
            self._col.delete(ids=stale)
        logger.info(
            "[CHROMA] 入库 doc=%s: 新增 %d / 剪枝 %d / 总计 %d",
            doc_id, len(to_add), len(stale), len(wanted),
        )
        return len(wanted)

    def delete_document(self, doc_id: str) -> int:
        ids = self._ids_of(doc_id)
        if ids:
            self._col.delete(ids=ids)
            logger.info("[CHROMA] 删除文档 %s 的 %d 片段", doc_id, len(ids))
        return len(ids)

    def rename_document(self, doc_id: str, name: str) -> int:
        got = self._col.get(where={"doc_id": doc_id})
        ids, metas = got["ids"], got["metadatas"]
        if not ids:
            return 0
        updated = [{**m, "doc": name} for m in metas]
        self._col.update(ids=ids, metadatas=updated)
        return len(ids)

    def chunk_count(self, doc_id: str) -> int:
        return len(self._ids_of(doc_id))

    async def search(self, query: str, top_k: int = 3) -> list[ScoredDocument]:
        """按余弦相似度检索 top-k。库为空或嵌入不可用时返回 []。"""
        if self._col.count() == 0:
            return []
        qv = (await self._embedder.embed([query]))[0]
        res = self._col.query(
            query_embeddings=[qv],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        docs = res["documents"][0]
        metas = res["metadatas"][0]
        dists = res["distances"][0]
        return [
            ScoredDocument(Document(text=text, metadata=dict(meta or {})), 1.0 - dist)
            for text, meta, dist in zip(docs, metas, dists)
        ]
