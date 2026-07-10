"""技能能力补齐 (#1 渐进披露 / #3 嵌套 / #4 上限 + B-4 串行/预算) 的测试。"""

import pytest

from maestro.bootstrap import build_platform
from maestro.config import Settings
from maestro.engines.scheduling.run_state import Budget
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


async def test_list_skill_files_scoped(tmp_path, monkeypatch):
    p = _platform(tmp_path, monkeypatch)
    p.skill_store.save(_meta("cap", file_count=1), "b", {"r.md": b"hi"})
    tok = set_context(_ctx({"cap"}))
    try:
        out = await p.tools.execute("list_skill_files", {})
        assert [f["path"] for f in out["files"]] == ["r.md"]
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
