"""技能级追加断言测试: AgentLoop.extra_preconditions 只叠加不替换内置护栏。"""

from conftest import FakeLLM
from scheduling_platform.engines.scheduling.agent_loop import AgentLoop
from scheduling_platform.foundation.audit import AuditLog
from scheduling_platform.foundation.authz import PendingActionStore
from scheduling_platform.foundation.tools.registry import ToolRegistry, PreconditionResult


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
