"""知识检索器 (RAG 的 retrieve 环节)。

启动时不阻塞: 种子知识库 (data/mock/knowledge/) 在首次检索时经 KnowledgeIngestor
惰性加载并嵌入。运行期由前端增删改查文档 (走同一 ingestor)，检索自动感知最新库。

嵌入不可用 (未配置 embed_model) 时退化为空检索，查询引擎据此只走工具/降级回答。
"""

import logging

from scheduling_platform.engines.query.ingestor import KnowledgeIngestor
from scheduling_platform.engines.query.schemas import QuerySource
from scheduling_platform.foundation.vectorstore import VectorStoreProtocol

logger = logging.getLogger(__name__)


class KnowledgeRetriever:
    def __init__(self, store: VectorStoreProtocol, ingestor: KnowledgeIngestor, top_k: int = 3):
        self._store = store
        self._ingestor = ingestor
        self._top_k = top_k

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
        await self._ingestor.seed_from_directory()
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
