"""知识检索器 (RAG 的 retrieve 环节)。

启动时不阻塞: 知识库 (data/mock/knowledge/*.md) 在首次检索时惰性加载并嵌入。
嵌入不可用 (未配置 embed_model) 时退化为空检索，查询引擎据此只走工具/降级回答。

切分策略 (初始版): 按 Markdown 段落 (空行分隔) 切片，元数据记来源文档名。
TODO(v0.2): 按标题层级切分、重叠窗口、rerank。
"""

import logging
from pathlib import Path

from scheduling_platform.engines.query.schemas import QuerySource
from scheduling_platform.foundation.vectorstore import VectorStore

logger = logging.getLogger(__name__)

_MIN_CHUNK_LEN = 10  # 过短片段 (标题/空段) 不入库


class KnowledgeRetriever:
    def __init__(self, store: VectorStore, knowledge_dir: Path, top_k: int = 3):
        self._store = store
        self._dir = Path(knowledge_dir)
        self._top_k = top_k
        self._loaded = False

    @property
    def available(self) -> bool:
        return self._store.available

    async def search(self, query: str, top_k: int | None = None) -> list[QuerySource]:
        """检索 top-k 相关知识片段。嵌入不可用或无知识时返回 []。"""
        passages = await self.search_passages(query, top_k)
        return [source for _, source in passages]

    async def search_passages(
        self, query: str, top_k: int | None = None
    ) -> list[tuple[str, QuerySource]]:
        """检索 top-k 相关片段，返回 (完整片段文本, 来源) —— 文本供 augment 拼接。"""
        await self._ensure_loaded()
        scored = await self._store.search(query, top_k or self._top_k)
        return [
            (
                s.document.text,
                QuerySource(
                    doc=s.document.metadata.get("doc", "未知"),
                    score=round(s.score, 4),
                    excerpt=s.document.text[:120],
                ),
            )
            for s in scored
        ]

    async def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True  # 只尝试一次，避免反复读盘
        if not self._store.available:
            logger.info("[RETRIEVER] 嵌入不可用，知识检索退化为空")
            return
        texts, metas = self._read_knowledge()
        if texts:
            await self._store.add_texts(texts, metas)
            logger.info("[RETRIEVER] 知识库加载完成: %d 片段", len(texts))

    def _read_knowledge(self) -> tuple[list[str], list[dict]]:
        if not self._dir.exists():
            logger.warning("[RETRIEVER] 知识库目录不存在: %s", self._dir)
            return [], []
        texts: list[str] = []
        metas: list[dict] = []
        for path in sorted(self._dir.glob("*.md")):
            content = path.read_text(encoding="utf-8")
            for chunk in content.split("\n\n"):
                chunk = chunk.strip()
                if len(chunk) >= _MIN_CHUNK_LEN:
                    texts.append(chunk)
                    metas.append({"doc": path.stem})
        return texts, metas
