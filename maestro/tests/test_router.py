"""路由器测试: 嵌入语义路由 → LLM 分类 → 低置信澄清 → 澄清后直接路由。"""

from conftest import FakeLLM

from maestro.bootstrap import build_platform
from maestro.orchestrator.embedding_router import EmbeddingRouter
from maestro.orchestrator.router import IntentRouter
from maestro.orchestrator.schemas import RouteDecision

# 受控的小例句集 (判别词清晰，便于断言假嵌入的路由结果)
EXAMPLES = {
    "planning": ["重新排产", "帮这批单优化排程"],
    "scheduling": ["把任务令下发了", "帮我催一下缺料"],
    "query": ["查一下库存还有多少", "看看订单状态"],
}


def make_router(settings, llm, examples=EXAMPLES) -> IntentRouter:
    embed_router = EmbeddingRouter(llm, examples) if llm.embed_available else None
    return IntentRouter(llm, settings, embed_router)


# ── 第 1 层: 嵌入语义路由 ─────────────────────────────────────


async def test_embedding_routes_planning(settings):
    router = make_router(settings, FakeLLM(embed=True))
    decision = await router.route("帮我重新排产这批订单")
    assert decision.intent == "planning"
    assert decision.route_method == "embedding"
    assert decision.confidence >= settings.embed_confidence_threshold


async def test_embedding_routes_scheduling_with_entities(settings):
    router = make_router(settings, FakeLLM(embed=True))
    decision = await router.route("把任务令 WO-101 下发了")
    assert decision.intent == "scheduling"
    assert decision.route_method == "embedding"
    assert decision.entities.get("wo_ids") == ["WO-101"]


async def test_embedding_routes_query(settings):
    router = make_router(settings, FakeLLM(embed=True))
    decision = await router.route("查一下现在库存还有多少")
    assert decision.intent == "query"
    assert decision.route_method == "embedding"


# ── 第 1→2 层: 嵌入低置信/不可用 → LLM 分类 ───────────────────


async def test_low_similarity_falls_through_to_llm(settings):
    """嵌入与任何例句都不相似 → 低置信 → 交 LLM 分类。"""
    llm = FakeLLM(
        classify_map={RouteDecision: RouteDecision(intent="planning", confidence=0.9, reason="LLM")},
        embed=True,
    )
    router = make_router(settings, llm)
    decision = await router.route("把那个东西弄一下")  # 不含任何判别词 → 零向量
    assert decision.route_method == "llm"
    assert decision.intent == "planning"


async def test_embedding_disabled_uses_llm(settings):
    llm = FakeLLM(
        classify_map={RouteDecision: RouteDecision(intent="scheduling", confidence=0.95, reason="LLM")},
        embed=False,
    )
    router = make_router(settings, llm)
    decision = await router.route("重新排产")  # 即便像 planning，嵌入禁用 → 走 LLM
    assert decision.route_method == "llm"
    assert decision.intent == "scheduling"


# ── 降级: 嵌入与 LLM 均不可用 → ambiguous ─────────────────────


async def test_all_unavailable_degrades_to_ambiguous(settings):
    router = make_router(settings, FakeLLM())  # 无嵌入、无分类
    decision = await router.route("3号线那批单有问题，处理下")
    assert decision.intent == "ambiguous"
    assert decision.route_method == "fallback"
    assert decision.confidence == 0.0


# ── 第 3 层: 低置信澄清，澄清后直接路由 ───────────────────────


async def test_clarification_then_direct_route(settings):
    """嵌入/LLM 均不可用 → 澄清；用户回复序号 → 直接路由原请求 (不再走嵌入/LLM)。"""
    platform = build_platform(settings=settings, llm=FakeLLM())
    first = await platform.orchestrator.handle("s1", "3号线那批单有问题，处理下")
    assert first.needs_clarification and len(first.options) == 3

    # 回复「2」→ 调度引擎，直接路由原请求
    second = await platform.orchestrator.handle("s1", "2")
    assert not second.needs_clarification
    assert second.route.intent == "scheduling"
    assert second.route.route_method == "clarified"
    assert "齐套" in second.reply or "缺料" in second.reply


async def test_clarification_by_keyword(settings):
    platform = build_platform(settings=settings, llm=FakeLLM())
    await platform.orchestrator.handle("s2", "帮我弄一下那批单")
    second = await platform.orchestrator.handle("s2", "排产")
    assert second.route.intent == "planning"
    assert second.route.route_method == "clarified"


async def test_low_confidence_llm_triggers_clarification(settings):
    llm = FakeLLM(
        classify_map={RouteDecision: RouteDecision(intent="scheduling", confidence=0.5, reason="不确定")},
        embed=False,
    )
    platform = build_platform(settings=settings, llm=llm)
    response = await platform.orchestrator.handle("s1", "弄一下那个东西")
    assert response.needs_clarification
