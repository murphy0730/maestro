"""技能级追加断言测试: AgentLoop.extra_preconditions 只叠加不替换内置护栏。"""

from conftest import FakeLLM
from scheduling_platform.config import Settings
from scheduling_platform.engines.scheduling.agent_loop import AgentLoop
from scheduling_platform.foundation.audit import AuditLog
from scheduling_platform.foundation.authz import PendingActionStore
from scheduling_platform.foundation.tools.registry import ToolRegistry, PreconditionResult
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
