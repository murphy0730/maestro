"""嵌入客户端 (共享底座)。

路由层的语义路由与查询引擎的 RAG 检索共用同一套嵌入能力。底层复用
`LLMClient.embed` (OpenAI 兼容 /embeddings)，此处提供一个聚焦的门面 +
余弦相似度工具，使向量库/检索器只依赖嵌入概念，不直接依赖 LLM 客户端。
"""

import math


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """两个向量的余弦相似度 (任一为零向量返回 0)。"""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class EmbeddingClient:
    """嵌入门面: 把文本批量向量化。底层委托 LLMClient.embed。"""

    def __init__(self, llm):  # llm: LLMClient (避免循环导入，弱类型)
        self._llm = llm

    @property
    def available(self) -> bool:
        return self._llm.embed_available

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """批量文本向量化。失败统一抛 LLMError (由调用方降级)。"""
        return await self._llm.embed(texts)
