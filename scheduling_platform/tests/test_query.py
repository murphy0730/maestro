"""查询引擎 (RAG + LLM) 测试。

覆盖: 检索命中知识库并把来源附在回答上 / 嵌入不可用时退化为无来源 /
LLM 不可用时降级为基础数据摘要 (仍附已检索到的来源)。
"""

from conftest import FakeLLM

from scheduling_platform.engines.query.query_engine import QueryEngine
from scheduling_platform.engines.query.retriever import KnowledgeRetriever
from scheduling_platform.foundation.embedding import EmbeddingClient
from scheduling_platform.foundation.kitting import KittingService
from scheduling_platform.foundation.tools.builtin import (
    QUERY_READONLY_TOOLS,
    FollowupStore,
    register_builtin_tools,
)
from scheduling_platform.foundation.tools.registry import ToolRegistry
from scheduling_platform.foundation.vectorstore import VectorStore


def _build_query_engine(adapter, audit, gate, settings, llm):
    tools = ToolRegistry()
    register_builtin_tools(
        tools, adapter, gate, KittingService(adapter, audit), llm, FollowupStore()
    )
    retriever = KnowledgeRetriever(
        VectorStore(EmbeddingClient(llm)), settings.knowledge_dir, settings.rag_top_k
    )
    return QueryEngine(llm, tools, retriever, adapter, QUERY_READONLY_TOOLS, settings.rag_top_k)


async def test_rag_attaches_knowledge_sources(adapter, audit, gate, settings):
    llm = FakeLLM(complete_reply="齐套指开工所需物料均已备齐。", embed=True)
    qe = _build_query_engine(adapter, audit, gate, settings, llm)
    resp = await qe.handle("什么是齐套？", [])

    assert resp.reply == "齐套指开工所需物料均已备齐。"
    assert resp.data["sources"]
    assert any(s["doc"] == "kitting-definition" for s in resp.data["sources"])


async def test_no_embedding_means_no_sources(adapter, audit, gate, settings):
    llm = FakeLLM(complete_reply="好的。", embed=False)
    qe = _build_query_engine(adapter, audit, gate, settings, llm)
    resp = await qe.handle("什么是齐套？", [])
    assert resp.reply == "好的。"
    assert resp.data["sources"] == []


async def test_llm_down_degrades_to_data_summary(adapter, audit, gate, settings):
    llm = FakeLLM(embed=True)  # 无 complete_reply → complete 抛错 → 降级
    qe = _build_query_engine(adapter, audit, gate, settings, llm)
    resp = await qe.handle("有多少订单？", [])
    assert "基础数据摘要" in resp.reply
