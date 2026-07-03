"""知识库摄取 + 文档 CRUD 测试。

覆盖: 多格式加载 (md/csv/html) 与不支持类型拒绝、切分、以及文档的增删改查
(含换内容/改名) 对向量库的成组影响；嵌入不可用时登记但不入库 (降级)。
所有嵌入用确定性假实现，无网络。
"""

from pathlib import Path

import pytest

from scheduling_platform.engines.query.ingestor import (
    DocumentNotFound,
    KnowledgeIngestor,
)
from scheduling_platform.foundation.chunking import Chunker
from scheduling_platform.foundation.loaders import (
    UnsupportedFileType,
    build_loader_registry,
)
from scheduling_platform.foundation.vectorstore import VectorStore


class _FakeEmbedder:
    """确定性假嵌入 (按文本长度散列)，available 可控。"""

    def __init__(self, available: bool = True):
        self.available = available

    async def embed(self, texts):
        return [[float(len(t) % 5), 1.0, float(i)] for i, t in enumerate(texts)]


def _ingestor(tmp_path: Path, available: bool = True) -> tuple[KnowledgeIngestor, VectorStore]:
    store = VectorStore(_FakeEmbedder(available))
    ing = KnowledgeIngestor(
        store, build_loader_registry(), Chunker(chunk_size=60, overlap=10), tmp_path
    )
    return ing, store


# ── 加载器 ────────────────────────────────────────────────
def test_loaders_supported_formats():
    reg = build_loader_registry()
    assert ".md" in reg.supported_extensions
    assert reg.load(b"name,qty\nA,5", "t.csv") == "name: A | qty: 5"
    assert reg.load(b"<p>Hi</p><script>bad</script>", "t.html") == "Hi"
    assert reg.load(b"# T\nbody", "t.md") == "# T\nbody"


def test_unsupported_type_rejected():
    reg = build_loader_registry()
    with pytest.raises(UnsupportedFileType):
        reg.load(b"x", "malware.exe")


# ── 切分 ──────────────────────────────────────────────────
def test_chunker_splits_by_heading():
    chunks = Chunker(chunk_size=100).split(
        "# 章节甲\n这是章节甲的正文内容一段。\n## 章节乙\n这是章节乙的正文内容另一段。"
    )
    sections = [m["section"] for _, m in chunks]
    assert sections == ["章节甲", "章节乙"]


# ── 增 / 查 ───────────────────────────────────────────────
async def test_add_and_list(tmp_path):
    ing, store = _ingestor(tmp_path)
    doc = await ing.add_upload("rules.md", b"# rules\n content here for chunking")
    assert doc.type == "md" and doc.status == "ready" and doc.chunk_count >= 1
    assert [d.doc_id for d in ing.list_docs()] == [doc.doc_id]
    assert len(store) == doc.chunk_count
    # 落盘
    assert any(tmp_path.iterdir())


async def test_add_unsupported_raises(tmp_path):
    ing, _ = _ingestor(tmp_path)
    with pytest.raises(UnsupportedFileType):
        await ing.add_upload("x.exe", b"data")


# ── 改: 换内容 / 改名 ─────────────────────────────────────
async def test_replace_swaps_chunks(tmp_path):
    ing, store = _ingestor(tmp_path)
    doc = await ing.add_upload("a.md", b"# one\n short")
    doc2 = await ing.replace(doc.doc_id, "a.md", b"# two\n" + b"long body " * 30)
    assert doc2.doc_id == doc.doc_id
    assert doc2.chunk_count > 1
    # 旧片段被清掉，只剩新文档的片段
    assert len(store) == doc2.chunk_count


async def test_rename_updates_source_label(tmp_path):
    ing, store = _ingestor(tmp_path)
    doc = await ing.add_upload("old.md", b"# t\n body text for a chunk")
    ing.rename(doc.doc_id, "new.md")
    assert ing.get(doc.doc_id).name == "new.md"
    assert all(d.metadata["doc"] == "new.md" for d in store._docs)


# ── 删 ────────────────────────────────────────────────────
async def test_remove_deletes_chunks_and_file(tmp_path):
    ing, store = _ingestor(tmp_path)
    doc = await ing.add_upload("a.md", b"# t\n body text here")
    removed = ing.remove(doc.doc_id)
    assert removed == doc.chunk_count
    assert len(store) == 0
    assert ing.list_docs() == []
    assert list(tmp_path.iterdir()) == []


async def test_missing_doc_raises(tmp_path):
    ing, _ = _ingestor(tmp_path)
    with pytest.raises(DocumentNotFound):
        ing.remove("nope")


# ── 降级: 嵌入不可用 ──────────────────────────────────────
async def test_no_embedding_registers_but_skips_vectors(tmp_path):
    ing, store = _ingestor(tmp_path, available=False)
    doc = await ing.add_upload("a.md", b"# t\n body text here")
    assert doc.status == "failed" and doc.chunk_count == 0
    assert len(store) == 0
    assert len(ing.list_docs()) == 1  # 仍登记，前端可见并可删


# ── 种子加载幂等 ──────────────────────────────────────────
async def test_seed_is_idempotent(tmp_path):
    (tmp_path / "seed.md").write_bytes(b"# s\n seed body content")
    ing, _ = _ingestor(tmp_path)
    await ing.seed_from_directory()
    n = len(ing.list_docs())
    await ing.seed_from_directory()  # 二次不重复
    assert len(ing.list_docs()) == n == 1
