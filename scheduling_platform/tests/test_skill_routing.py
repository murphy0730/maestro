"""技能级追加断言测试: AgentLoop.extra_preconditions 只叠加不替换内置护栏。"""

from conftest import FakeLLM
from scheduling_platform.config import Settings
from scheduling_platform.engines.scheduling.agent_loop import AgentLoop
from scheduling_platform.foundation.audit import AuditLog
from scheduling_platform.foundation.authz import PendingActionStore
from scheduling_platform.foundation.tools.registry import ToolRegistry, PreconditionResult
from scheduling_platform.orchestrator.schemas import RouteDecision
from scheduling_platform.skills.engine import SkillEngine
from scheduling_platform.skills.schemas import SkillMeta
from scheduling_platform.skills.store import SkillStore


async def _blocking(args):
    return PreconditionResult(False, "技能禁止")


async def _ok(args):
    return {"ok": True}


def _loop(extra):
    tools = ToolRegistry()
    tools.register("query_orders", "查询订单", {"type": "object", "properties": {}}, _ok, kind="read")
    llm = FakeLLM(chat_script=[[("query_orders", {})], "最终结论"])
    return AgentLoop(
        llm, tools, PendingActionStore(), AuditLog(file_path=None),
        "", ["query_orders"], 5, extra_preconditions=extra,
    )


async def test_extra_preconditions_block():
    r = await _loop({"query_orders": [_blocking]}).run("t")
    assert r.steps[0].blocked is True
    assert "技能前置断言未通过" in r.steps[0].observation["blocked"]


async def test_extra_preconditions_none_unchanged():
    r = await _loop(None).run("t")
    assert r.steps[0].blocked is False
    assert r.answer == "最终结论"


# ── SkillEngine (Task 3.2) ──────────────────────────────────────────────


def _tools_with_query_orders():
    tools = ToolRegistry()
    tools.register("query_orders", "查询订单", {"type": "object", "properties": {}}, _ok, kind="read")
    return tools


def _engine(tmp_path, llm, named=None):
    store = SkillStore(tmp_path / "skills")
    s = Settings(llm_api_key="", mock_data_dir=tmp_path / "mock", audit_log_file=None)
    return SkillEngine(llm, _tools_with_query_orders(), PendingActionStore(),
                       AuditLog(file_path=None), store, s, named or {})


def _seed(store, name="cap", body="你是产能技能。", **kw):
    store.save(SkillMeta(name=name, description="x", added_at="t",
                         file_count=0, bytes=0, **kw), body, {})


async def test_skill_engine_not_found(tmp_path):
    e = _engine(tmp_path, FakeLLM(chat_script=["x"]))
    r = await e.handle("nope", "msg", "s1")
    assert "不存在" in r.reply


async def test_skill_engine_llm_unavailable(tmp_path):
    e = _engine(tmp_path, FakeLLM())  # available=False
    _seed(e._store, "cap")
    r = await e.handle("cap", "msg", "s1")
    assert "LLM 未配置" in r.reply


async def test_skill_engine_executes(tmp_path):
    e = _engine(tmp_path, FakeLLM(chat_script=["产能结论"]))
    _seed(e._store, "cap")
    r = await e.handle("cap", "msg", "s1")
    assert r.reply == "产能结论"


async def test_skill_engine_precondition_blocks(tmp_path):
    e = _engine(tmp_path, FakeLLM(chat_script=[[("query_orders", {})], "结论"]),
                named={"my_assert": _blocking})
    _seed(e._store, "cap", allowed_tools=["query_orders"],
          tool_preconditions={"query_orders": ["my_assert"]})
    r = await e.handle("cap", "msg", "s1")
    assert r.data["steps"][0]["blocked"] is True
    assert "技能前置断言未通过" in r.data["steps"][0]["observation"]["blocked"]


# ── RouteDecision skill intent (Task 3.4) ──────────────────────────────


def test_routedecision_skill_fields():
    d = RouteDecision(intent="skill", skill_id="cap", confidence=0.9)
    assert d.intent == "skill" and d.skill_id == "cap"
    schema = RouteDecision.model_json_schema()
    assert "skill" in schema["properties"]["intent"]["enum"]
    assert "skill_id" in schema["properties"]


# ── bootstrap 装配 SkillEngine (Task 3.3) ──────────────────────────────

from scheduling_platform.bootstrap import build_platform  # noqa: E402


async def test_bootstrap_wires_skill_engine(tmp_path, settings):
    p = build_platform(settings=Settings(llm_api_key="", mock_data_dir=settings.mock_data_dir,
                                         audit_log_file=None, skills_dir=tmp_path / "skills"))
    assert p.skill_engine is not None
    # 技能不存在 → 友好回复(不抛)
    r = await p.skill_engine.handle("nope", "msg", "s1")
    assert "不存在" in r.reply


# ── EmbeddingRouter 技能向量 + version 拉式失效 (Task 3.5, 分叉 A1) ──────

from scheduling_platform.orchestrator.embedding_router import EmbeddingRouter  # noqa: E402
from scheduling_platform.orchestrator.router import IntentRouter  # noqa: E402

EMBED_EXAMPLES = {
    "planning": ["重新排产", "优化排程"],
    "scheduling": ["把任务令下发了", "催一下缺料"],
    "query": ["查库存还有多少"],
}


def _seed_skill(store, name="capacity-report", when=("给我出一份今天的产能报告",)):
    store.save(SkillMeta(name=name, description="产能日报", when_to_use=list(when),
                        added_at="t", file_count=0, bytes=0), "正文", {})


async def test_embedding_classifies_skill(tmp_path):
    store = SkillStore(tmp_path / "skills")
    _seed_skill(store)
    er = EmbeddingRouter(FakeLLM(embed=True), EMBED_EXAMPLES, skills=store)
    result = await er.classify("出一份产能报告")
    assert result.intent == "skill:capacity-report"
    assert result.score >= 0.5


async def test_embedding_skill_version_invalidation(tmp_path):
    store = SkillStore(tmp_path / "skills")
    er = EmbeddingRouter(FakeLLM(embed=True), EMBED_EXAMPLES, skills=store)
    r1 = await er.classify("重新排产")  # 无技能 → planning
    assert r1.intent == "planning"
    _seed_skill(store, when=("出产能报告",))
    r2 = await er.classify("出产能报告")  # 导入后 version 变 → 重嵌 → 命中 skill
    assert r2.intent == "skill:capacity-report"


# ── IntentRouter 技能路由 + 校验 (Task 3.6, 分叉 B1) ─────────────────────


def _router(llm, store, settings):
    embed = EmbeddingRouter(llm, EMBED_EXAMPLES, skills=store) if llm.embed_available else None
    return IntentRouter(llm, settings, embed, skills=store)


async def test_llm_routes_to_existing_skill(tmp_path, settings):
    store = SkillStore(tmp_path / "skills")
    _seed_skill(store)
    llm = FakeLLM(
        classify_map={
            RouteDecision: RouteDecision(
                intent="skill", skill_id="capacity-report", confidence=0.9, reason="LLM",
            ),
        },
        embed=False,
    )
    d = await _router(llm, store, settings).route("弄一下产能")
    assert d.intent == "skill" and d.skill_id == "capacity-report"
    assert d.route_method == "llm"


async def test_llm_skill_nonexistent_degrades_ambiguous(tmp_path, settings):
    store = SkillStore(tmp_path / "skills")  # 空
    llm = FakeLLM(
        classify_map={
            RouteDecision: RouteDecision(intent="skill", skill_id="ghost", confidence=0.9),
        },
        embed=False,
    )
    d = await _router(llm, store, settings).route("弄一下")
    assert d.intent == "ambiguous"
    assert "不存在的技能" in d.reason


async def test_embedding_routes_to_skill(tmp_path, settings):
    store = SkillStore(tmp_path / "skills")
    _seed_skill(store)
    d = await _router(FakeLLM(embed=True), store, settings).route("出一份产能报告")
    assert d.intent == "skill" and d.skill_id == "capacity-report"
    assert d.route_method == "embedding"


# ── Orchestrator forced skill + _contract_route + chat 透传 (Task 3.7) ────

from pathlib import Path  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from scheduling_platform.main import _contract_route, app  # noqa: E402

_MOCK_DATA = Path(__file__).resolve().parents[1] / "data" / "mock"


async def test_orchestrator_forced_skill(tmp_path):
    s = Settings(
        llm_api_key="",
        mock_data_dir=_MOCK_DATA,
        audit_log_file=None,
        sessions_dir=tmp_path / "sessions",
        skills_dir=tmp_path / "skills",
    )
    p = build_platform(settings=s, llm=FakeLLM(chat_script=["产能结论"]))
    _seed_skill(p.skill_store)
    resp = await p.orchestrator.handle("s1", "出产能报告", skill_id="capacity-report")
    assert resp.reply == "产能结论"
    assert resp.route.intent == "skill"
    assert resp.route.skill_id == "capacity-report"
    assert resp.route.route_method == "forced"


def test_contract_route_emits_skill_id():
    rd = RouteDecision(
        intent="skill", skill_id="cap", confidence=1.0, route_method="forced"
    )
    out = _contract_route(rd)
    assert out["intent"] == "skill"
    assert out["skill_id"] == "cap"
    assert _contract_route(RouteDecision(intent="planning", confidence=0.9))["skill_id"] is None


async def test_chat_endpoint_threads_skill_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = Settings(
        llm_api_key="",
        mock_data_dir=_MOCK_DATA,
        audit_log_file=None,
        sessions_dir=tmp_path / "sessions",
        skills_dir=tmp_path / "skills",
    )
    p = build_platform(settings=s, llm=FakeLLM(chat_script=["产能结论"]))
    _seed_skill(p.skill_store)
    app.state.platform = p
    c = TestClient(app)
    r = c.post(
        "/chat",
        json={
            "session_id": "s1",
            "message": "出产能报告",
            "skill_id": "capacity-report",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["route"]["intent"] == "skill"
    assert body["route"]["skill_id"] == "capacity-report"
