"""查询引擎 —— RAG + LLM (检索 → 增强 → 生成)。

与调度引擎 (ReAct) 的区别: 查询引擎只回答、不写数据 —— 只挂只读工具，绝不触发
任何副作用动作。流程:
  1. retrieve: 用知识库检索与问题相关的概念/规则片段;
  2. augment: 把片段作为「知识库参考」注入系统提示;
  3. generate: LLM 结合参考 + 只读工具 (查实时数据) 作答，并附来源。

LLM 不可用时降级为基础数据摘要 (不臆造)。接口 handle(message, history) 与
Orchestrator 对齐 (替换原 QueryHandler)。
"""

import logging

from scheduling_platform.engines.base import EngineResponse
from scheduling_platform.engines.query.retriever import KnowledgeRetriever
from scheduling_platform.foundation.integration.base import IntegrationAdapter
from scheduling_platform.foundation.llm import LLMClient, LLMError
from scheduling_platform.foundation.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

QUERY_SYSTEM = (
    "你是生产计划/调度平台的查询助手。回答概念性问题时优先依据下方「知识库参考」，"
    "回答实时数据问题时调用只读工具查询 (订单/库存/任务令/齐套)。"
    "不要编造: 数据以工具返回为准，概念以知识库为准；都没有依据时如实说明不掌握。"
)


class QueryEngine:
    def __init__(
        self,
        llm: LLMClient,
        tools: ToolRegistry,
        retriever: KnowledgeRetriever,
        adapter: IntegrationAdapter,
        readonly_tools: list[str],
        top_k: int = 3,
    ):
        self._llm = llm
        self._tools = tools
        self._retriever = retriever
        self._adapter = adapter
        self._readonly_tools = list(readonly_tools)
        self._top_k = top_k

    async def handle(self, message: str, history: list[dict]) -> EngineResponse:
        # 1) retrieve
        passages: list = []
        try:
            passages = await self._retriever.search_passages(message, self._top_k)
        except LLMError:
            logger.info("[QUERY] 知识检索不可用 (嵌入失败)，仅用工具回答")

        # 2) augment
        system = QUERY_SYSTEM
        if passages:
            refs = "\n\n".join(f"[来源: {src.doc}] {text}" for text, src in passages)
            system = f"{QUERY_SYSTEM}\n\n【知识库参考】\n{refs}"

        sources = [src.model_dump() for _, src in passages]

        # 3) generate (只读工具)
        try:
            reply = await self._llm.complete(
                system,
                [*history, {"role": "user", "content": message}],
                tools=self._tools.to_openai_tools(self._readonly_tools),
                tool_executor=self._tools.execute,
            )
            return EngineResponse(reply=reply, data={"sources": sources})
        except LLMError:
            return await self._degraded(sources)

    async def _degraded(self, sources: list[dict]) -> EngineResponse:
        orders = await self._adapter.get_orders({})
        wos = await self._adapter.get_work_orders({})
        draft = [w.wo_id for w in wos if w.status == "draft"]
        reply = (
            "LLM 查询助手当前不可用，以下是基础数据摘要:\n"
            f"- 订单 {len(orders)} 个: {', '.join(o.order_id for o in orders)}\n"
            f"- 任务令 {len(wos)} 个，其中待下发(draft): {', '.join(draft) or '无'}"
        )
        return EngineResponse(reply=reply, data={"sources": sources})
