"""Chroma 持久化向量库测试。

覆盖: 增/检索/删/改名与内存实现行为一致；内容寻址幂等 (同内容不重嵌)；
内容变更剪枝旧片段；跨实例重开后向量仍在且不重嵌 (持久化收益)。
嵌入用确定性假实现并计数，无网络。
"""

import hashlib

from scheduling_platform.foundation.chroma_store import ChromaVectorStore


def _vec(text: str) -> list[float]:
    """确定性向量: 同文本 → 同向量 (query==chunk 时余弦距离≈0)。"""
    h = hashlib.sha256(text.encode("utf-8")).digest()
    return [b / 255.0 for b in h[:8]]


class _FakeEmbedder:
    """确定性假嵌入，记录被嵌入的文本以断言是否重嵌。"""

    def __init__(self, available: bool = True):
        self.available = available
        self.embedded: list[str] = []

    async def embed(self, texts):
        self.embedded.extend(texts)
        return [_vec(t) for t in texts]


async def test_add_search_delete(tmp_path):
    store = ChromaVectorStore(_FakeEmbedder(), tmp_path)
    n = await store.add_documents(
        "d1", ["alpha 内容", "beta 内容"],
        [{"doc": "a.md", "section": "s1"}, {"doc": "a.md", "section": "s2"}],
    )
    assert n == 2
    hits = await store.search("alpha 内容", top_k=1)
    assert hits and hits[0].document.text == "alpha 内容"
    assert hits[0].document.metadata["doc"] == "a.md"
    assert hits[0].score > 0.99  # 相同向量 → 距离≈0
    assert store.delete_document("d1") == 2
    assert store.chunk_count("d1") == 0
    assert await store.search("alpha 内容") == []


async def test_rename_updates_source_label(tmp_path):
    store = ChromaVectorStore(_FakeEmbedder(), tmp_path)
    await store.add_documents("d1", ["x 内容"], [{"doc": "old.md"}])
    assert store.rename_document("d1", "new.md") == 1
    hits = await store.search("x 内容", top_k=1)
    assert hits[0].document.metadata["doc"] == "new.md"


async def test_idempotent_add_skips_reembedding(tmp_path):
    emb = _FakeEmbedder()
    store = ChromaVectorStore(emb, tmp_path)
    await store.add_documents("d1", ["one 内容", "two 内容"])
    assert emb.embedded == ["one 内容", "two 内容"]
    await store.add_documents("d1", ["one 内容", "two 内容"])  # 同内容再入库
    assert emb.embedded == ["one 内容", "two 内容"]  # 未重嵌
    assert store.chunk_count("d1") == 2


async def test_content_change_prunes_stale(tmp_path):
    store = ChromaVectorStore(_FakeEmbedder(), tmp_path)
    await store.add_documents("d1", ["v1 内容"], [{"doc": "a.md"}])
    await store.add_documents("d1", ["v2 内容"], [{"doc": "a.md"}])  # 内容变更
    assert store.chunk_count("d1") == 1
    hits = await store.search("v2 内容", top_k=1)
    assert hits[0].document.text == "v2 内容"


async def test_persists_across_reopen_without_reembedding(tmp_path):
    emb1 = _FakeEmbedder()
    store1 = ChromaVectorStore(emb1, tmp_path)
    await store1.add_documents("d1", ["persist 内容"], [{"doc": "p.md"}])
    del store1

    emb2 = _FakeEmbedder()
    store2 = ChromaVectorStore(emb2, tmp_path)
    # 已持久化: 同内容重新播种不再嵌入
    await store2.add_documents("d1", ["persist 内容"], [{"doc": "p.md"}])
    assert emb2.embedded == []
    hits = await store2.search("persist 内容", top_k=1)
    assert hits and hits[0].document.text == "persist 内容"


async def test_large_document_exceeds_chroma_batch(tmp_path):
    """大文档 (>Chroma 单次 add 上限 5461) 需分批入库，不得抛错。"""
    store = ChromaVectorStore(_FakeEmbedder(), tmp_path)
    texts = [f"chunk {i} 内容" for i in range(6000)]
    n = await store.add_documents("big", texts)
    assert n == 6000
    assert store.chunk_count("big") == 6000


async def test_unavailable_embedder_reports_unavailable(tmp_path):
    store = ChromaVectorStore(_FakeEmbedder(available=False), tmp_path)
    assert store.available is False
