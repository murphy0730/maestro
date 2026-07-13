"""技能能力补齐 (#1 渐进披露 / #3 嵌套 / #4 上限 + B-4 串行/预算) 的测试。"""

import pytest

from conftest import FakeLLM
from maestro.bootstrap import build_platform
from maestro.config import Settings
from maestro.engines.scheduling.agent_loop import AgentLoop
from maestro.domain.models import PendingAction
from maestro.engines.scheduling.run_state import Budget
from maestro.foundation.audit import AuditLog
from maestro.foundation.authz import PendingActionStore
from maestro.foundation.llm import LLMError
from maestro.foundation.tools.registry import ToolRegistry
from maestro.skills.context import SkillInvocationContext, reset_context, set_context
from maestro.skills.parser import parse_skill_md
from maestro.skills.schemas import SkillMeta, SkillValidationError
from maestro.skills.store import SkillStore


def _platform(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = Settings(llm_api_key="", audit_log_file=None,
                 sessions_dir=tmp_path / "sessions", skills_dir=tmp_path / "skills")
    return build_platform(settings=s)


def _meta(name="cap", **kw):
    return SkillMeta(name=name, description="x", added_at="2026-07-05T00:00:00Z", **kw)


def _ctx(allowed, depth=0, visited=None, budget=10):
    return SkillInvocationContext(
        allowed_skills=frozenset(allowed),
        depth=depth,
        visited=frozenset(visited if visited is not None else allowed),
        budget=Budget(budget),
    )


# ── #4 正文/合并上限 ────────────────────────────────────────────

def test_parser_configurable_max_bytes():
    text = "---\nname: cap\ndescription: x\n---\n" + "x" * 100
    with pytest.raises(SkillValidationError):
        parse_skill_md(text, max_bytes=50)
    fm, body = parse_skill_md(text, max_bytes=200)
    assert len(body) == 100


def test_settings_skill_caps_defaults():
    s = Settings(llm_api_key="")
    assert s.skill_body_max_bytes == 128 * 1024
    assert s.skill_prompt_max_bytes == 256 * 1024
    assert s.skill_max_depth == 2


# ── #1 附件发现与作用域 ─────────────────────────────────────────

def test_store_list_attachments(tmp_path):
    s = SkillStore(tmp_path)
    s.save(_meta("cap", file_count=2), "正文", {"reference/a.md": b"aaa", "b.txt": b"bb"})
    items = s.list_attachments("cap")
    paths = {i["path"] for i in items}
    assert paths == {"reference/a.md", "b.txt"}
    assert all("size_bytes" in i and "bytes" not in i for i in items)
    assert "SKILL.md" not in paths


async def test_read_skill_file_requires_context(tmp_path, monkeypatch):
    p = _platform(tmp_path, monkeypatch)
    p.skill_store.save(_meta("cap", file_count=1), "b", {"r.md": b"hi"})
    out = await p.tools.execute("read_skill_file", {"path": "r.md"})
    assert "blocked" in out  # 无技能上下文 → 拒绝


async def test_read_skill_file_scoped_to_allowed(tmp_path, monkeypatch):
    p = _platform(tmp_path, monkeypatch)
    p.skill_store.save(_meta("cap", file_count=1), "b", {"r.md": b"hi"})
    p.skill_store.save(_meta("other", file_count=1), "b", {"secret.md": b"nope"})
    tok = set_context(_ctx({"cap"}))
    try:
        ok = await p.tools.execute("read_skill_file", {"path": "r.md"})
        assert ok["text"] == "hi"
        denied = await p.tools.execute("read_skill_file", {"path": "secret.md"})
        assert "blocked" in denied  # 他技能附件不可达
        trav = await p.tools.execute("read_skill_file", {"path": "../other/secret.md"})
        assert "blocked" in trav  # 路径穿越被拒
    finally:
        reset_context(tok)


async def test_read_skill_file_reports_binary_and_truncation(tmp_path, monkeypatch):
    p = _platform(tmp_path, monkeypatch)
    p.skill_store.save(_meta("cap", file_count=2), "b", {
        "large.txt": b"x" * 70000,
        "image.png": b"\x89PNG\r\n\x1a\n\x00\xff",
    })
    tok = set_context(_ctx({"cap"}))
    try:
        large = await p.tools.execute("read_skill_file", {"path": "large.txt"})
        assert large["truncated"] is True
        assert len(large["text"]) == 65536
        binary = await p.tools.execute("read_skill_file", {"path": "image.png"})
        assert binary["binary"] is True
        assert "text" not in binary
        assert binary["content_type"] == "image/png"
    finally:
        reset_context(tok)


async def test_list_skill_files_scoped(tmp_path, monkeypatch):
    p = _platform(tmp_path, monkeypatch)
    p.skill_store.save(_meta("cap", file_count=1), "b", {"r.md": b"hi"})
    tok = set_context(_ctx({"cap"}))
    try:
        out = await p.tools.execute("list_skill_files", {})
        assert [f["path"] for f in out["files"]] == ["r.md"]
    finally:
        reset_context(tok)


async def test_multi_skill_files_are_namespaced(tmp_path, monkeypatch):
    p = _platform(tmp_path, monkeypatch)
    p.skill_store.save(_meta("aa", file_count=1), "b", {"reference.md": b"from aa"})
    p.skill_store.save(_meta("bb", file_count=1), "b", {"reference.md": b"from bb"})
    tok = set_context(_ctx({"aa", "bb"}))
    try:
        files = await p.tools.execute("list_skill_files", {})
        assert {f["path"] for f in files["files"]} == {"aa/reference.md", "bb/reference.md"}
        assert (await p.tools.execute("read_skill_file", {"path": "aa/reference.md"}))["text"] == "from aa"
        assert (await p.tools.execute("read_skill_file", {"path": "bb/reference.md"}))["text"] == "from bb"
        raw_path = await p.tools.execute("read_skill_file", {"path": "reference.md"})
        assert "blocked" in raw_path
    finally:
        reset_context(tok)


# ── B-4 串行 + 预算 ─────────────────────────────────────────────

def test_invoke_skill_not_parallelizable(tmp_path, monkeypatch):
    p = _platform(tmp_path, monkeypatch)
    assert p.tools.get("invoke_skill").parallelizable is False
    assert p.tools.get("read_skill_file").parallelizable is True
    assert "list_skill_files" in p.tools.names()


async def test_budget_atomic_take():
    b = Budget(2)
    assert await b.take() is True
    assert await b.take() is True
    assert await b.take() is False  # 耗尽


async def _query_ok():
    return {"ok": True}


class _CountingLLM(FakeLLM):
    def __init__(self, chat_script):
        super().__init__(chat_script=chat_script)
        self.calls = 0

    async def chat_turn(self, system, messages, tools=None):
        self.calls += 1
        return await super().chat_turn(system, messages, tools)


class _FailingLLM:
    available = True

    def __init__(self):
        self.calls = 0

    async def chat_turn(self, system, messages, tools=None):
        self.calls += 1
        raise LLMError("temporary failure")


def _loop_with_budget(llm, budget, max_steps=8):
    tools = ToolRegistry()
    tools.register("query_orders", "查询", {"type": "object", "properties": {}}, _query_ok)
    return AgentLoop(
        llm, tools, PendingActionStore(), AuditLog(file_path=None), "", ["query_orders"],
        max_steps, budget=budget,
    )


async def test_budget_counts_forced_final_request():
    llm = _CountingLLM([[("query_orders", {})], "forced final"])
    budget = Budget(2)
    result = await _loop_with_budget(llm, budget, max_steps=1).run("t")
    assert result.stop_reason == "max_steps"
    assert result.answer == "forced final"
    assert llm.calls == 2
    assert budget.remaining == 0


async def test_budget_counts_each_retry_request():
    llm = _FailingLLM()
    budget = Budget(2)
    result = await _loop_with_budget(llm, budget).run("t")
    assert result.stop_reason == "max_steps"
    assert llm.calls == 2
    assert budget.remaining == 0


# ── 首个待确认动作即停 (stop_on_pending，技能循环专用) ────────────

def _pending_loop(llm, pending, stop_on_pending):
    tools = ToolRegistry()

    async def _risky(script: str = ""):
        action = PendingAction(action_type="run_skill_script", description=f"d:{script}")
        pending.add(action)
        return {"pending_confirmation": True, "action_id": action.action_id}

    tools.register("risky", "写",
                   {"type": "object", "properties": {"script": {"type": "string"}}},
                   _risky, kind="write", parallelizable=False)
    return AgentLoop(
        llm, tools, pending, AuditLog(file_path=None), "", ["risky"], 8,
        stop_on_pending=stop_on_pending,
    )


async def test_stop_on_pending_limits_to_single_action():
    """技能循环: 单轮连发两个待确认工具调用 → 第一个挂起后立即停步。"""
    llm = FakeLLM(chat_script=[
        [("risky", {"script": "a.py"}), ("risky", {"script": "b.py"})], "final",
    ])
    pending = PendingActionStore()
    result = await _pending_loop(llm, pending, stop_on_pending=True).run("t")
    assert result.stop_reason == "pending_confirmation"
    assert len(result.pending_actions) == 1
    assert result.answer  # 有面向用户的说明文案


async def test_without_stop_on_pending_collects_multiple():
    """调度路径回归: 不开启 stop_on_pending 时仍可批量累积待确认动作。"""
    llm = FakeLLM(chat_script=[
        [("risky", {"script": "a.py"}), ("risky", {"script": "b.py"})], "final",
    ])
    pending = PendingActionStore()
    result = await _pending_loop(llm, pending, stop_on_pending=False).run("t")
    assert result.stop_reason == "final"
    assert len(result.pending_actions) == 2


# ── #3 嵌套有界护栏 (无需 LLM: 护栏在 _run 之前) ────────────────

async def test_invoke_nested_no_context(tmp_path, monkeypatch):
    p = _platform(tmp_path, monkeypatch)
    out = await p.skill_engine.invoke_nested("cap", "t")
    assert "blocked" in out


async def test_invoke_nested_cycle(tmp_path, monkeypatch):
    p = _platform(tmp_path, monkeypatch)
    p.skill_store.save(_meta("aa"), "b", {})
    p.skill_store.save(_meta("bb"), "b", {})
    tok = set_context(_ctx({"aa"}, depth=0, visited={"aa", "bb"}))
    try:
        out = await p.skill_engine.invoke_nested("bb", "t")
        assert "环" in out["blocked"]
    finally:
        reset_context(tok)


async def test_invoke_nested_depth_limit(tmp_path, monkeypatch):
    p = _platform(tmp_path, monkeypatch)
    p.skill_store.save(_meta("aa"), "b", {})
    p.skill_store.save(_meta("bb"), "b", {})
    tok = set_context(_ctx({"aa"}, depth=2, visited={"aa"}))  # +1=3 > max_depth 2
    try:
        out = await p.skill_engine.invoke_nested("bb", "t")
        assert "嵌套过深" in out["blocked"]
    finally:
        reset_context(tok)


async def test_invoke_nested_disabled_model_invocation(tmp_path, monkeypatch):
    p = _platform(tmp_path, monkeypatch)
    p.skill_store.save(_meta("aa"), "b", {})
    p.skill_store.save(_meta("secret", disable_model_invocation=True), "b", {})
    tok = set_context(_ctx({"aa"}))
    try:
        out = await p.skill_engine.invoke_nested("secret", "t")
        assert "禁用模型调用" in out["blocked"]
    finally:
        reset_context(tok)


async def test_invoke_nested_missing_skill(tmp_path, monkeypatch):
    p = _platform(tmp_path, monkeypatch)
    p.skill_store.save(_meta("aa"), "b", {})
    tok = set_context(_ctx({"aa"}))
    try:
        out = await p.skill_engine.invoke_nested("ghost", "t")
        assert "不存在" in out["blocked"]
    finally:
        reset_context(tok)


async def test_skill_whitelist_always_includes_read_observation(monkeypatch):
    """DEF-2: 大观察离线暂存的配套工具 read_observation 必须始终进技能白名单，
    否则暂存 hint 指向一个会被拒绝的工具，超限观察实际不可读。"""
    from maestro.config import Settings
    from maestro.skills.engine import SkillEngine
    from maestro.skills.schemas import SkillMeta

    captured = {}

    class FakeLoop:
        def __init__(self, llm, tools, pending, audit, prompt, allowed, max_steps, **kwargs):
            captured["allowed"] = list(allowed)

        async def run(self, message, history=None, on_progress=None):
            class R:
                answer = "ok"
                steps = []
                stop_reason = "final"
                pending_actions = []
            return R()

    monkeypatch.setattr("maestro.skills.engine.AgentLoop", FakeLoop)

    meta = SkillMeta(name="pdf", description="d", allowed_tools=[])

    class Store:
        def get(self, sid):
            return meta

        def get_body(self, sid):
            return "正文"

        def list_attachments(self, sid):
            return []

    engine = SkillEngine(
        llm=None, tools=None, pending=None, audit=None,
        store=Store(), settings=Settings(), named_preconditions={})
    resp = await engine._run(["pdf"], "hi", None, None, _ctx(["pdf"]))
    assert resp.data["skill_ids"] == ["pdf"]
    assert "read_observation" in captured["allowed"]
