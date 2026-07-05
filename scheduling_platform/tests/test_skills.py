import io
import zipfile

import pytest
from datetime import datetime, timezone
from scheduling_platform.skills.parser import (
    parse_skill_md,
    extract_package,
    validate_allowed_tools,
)
from scheduling_platform.skills.schemas import SkillFrontmatter, SkillMeta, SkillValidationError


def _base(**kw):
    return {"name": "capacity-report", "description": "产能日报", **kw}


def test_frontmatter_ok_minimal():
    fm = SkillFrontmatter(**_base())
    assert fm.name == "capacity-report"
    assert fm.user_invocable is True
    assert fm.disable_model_invocation is False
    assert fm.tool_preconditions == {}
    assert fm.allowed_tools is None  # None 哨兵 = 校验时填默认
    assert fm.effective_display_name == "capacity-report"


def test_frontmatter_name_regex():
    for bad in ["X", "1a", "has_underscore", "a" * 33, "CAP"]:
        with pytest.raises(Exception):
            SkillFrontmatter(**_base(name=bad))


def test_frontmatter_description_length():
    with pytest.raises(Exception):
        SkillFrontmatter(**_base(description=""))
    with pytest.raises(Exception):
        SkillFrontmatter(**_base(description="x" * 201))


def test_frontmatter_when_to_use_limits():
    with pytest.raises(Exception):
        SkillFrontmatter(**_base(when_to_use=["x" * 101]))
    with pytest.raises(Exception):
        SkillFrontmatter(**_base(when_to_use=[str(i) for i in range(11)]))


def test_frontmatter_preconditions_types():
    fm = SkillFrontmatter(**_base(
        allowed_tools=["dispatch_work_order"],
        tool_preconditions={"dispatch_work_order": ["dispatch_ready"]},
    ))
    assert fm.tool_preconditions == {"dispatch_work_order": ["dispatch_ready"]}


def test_skillmeta_extra_fields():
    fm = SkillMeta(**_base(), file_count=2, bytes=1024, added_at="2026-07-05T00:00:00Z")
    assert fm.file_count == 2 and fm.bytes == 1024


# --- Task 1.2: parser.py ---


def _md(fm: str, body: str = "正文") -> str:
    return f"---\n{fm}\n---\n{body}"


def test_parse_skill_md_ok():
    text = _md("name: cap\ndescription: 产能\nwhen_to_use:\n  - 出报告\n")
    fm, body = parse_skill_md(text)
    assert fm.name == "cap" and fm.description == "产能"
    assert body == "正文"


def test_parse_skill_md_no_frontmatter():
    with pytest.raises(SkillValidationError):
        parse_skill_md("no frontmatter here")


def test_parse_skill_md_empty_body():
    with pytest.raises(SkillValidationError):
        parse_skill_md("---\nname: cap\ndescription: x\n---\n   \n")


def test_parse_skill_md_body_too_large():
    text = _md("name: cap\ndescription: x\n", "x" * (32 * 1024 + 1))
    with pytest.raises(SkillValidationError):
        parse_skill_md(text)


def _zip(files: dict[str, bytes]) -> bytes:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w") as zf:
        for n, c in files.items():
            zf.writestr(n, c)
    return bio.getvalue()


def test_extract_package_md():
    data = _md("name: cap\ndescription: x\n", "正文").encode()
    fm, body, att = extract_package(data, "cap.md")
    assert fm.name == "cap" and body == "正文" and att == {}


def test_extract_package_zip_ok():
    z = _zip({"SKILL.md": _md("name: cap\ndescription: x\n", "正文"),
              "docs/ref.md": b"# ref"})
    fm, body, att = extract_package(z, "cap.zip")
    assert fm.name == "cap" and att == {"docs/ref.md": b"# ref"}


def test_extract_package_zip_top_dir_normalized():
    z = _zip({"pkg/SKILL.md": _md("name: cap\ndescription: x\n", "正文"),
              "pkg/docs/ref.md": b"# ref"})
    fm, body, att = extract_package(z, "cap.zip")
    assert att == {"docs/ref.md": b"# ref"}


def test_extract_package_zip_missing_skill_md():
    z = _zip({"docs/ref.md": b"# ref"})
    with pytest.raises(SkillValidationError):
        extract_package(z, "cap.zip")


def test_extract_package_zip_traversal():
    z = _zip({"../evil.md": b"x"})
    with pytest.raises(SkillValidationError):
        extract_package(z, "cap.zip")


def test_extract_package_zip_too_many_members():
    z = _zip({f"f{i}.md": b"x" for i in range(51)})
    # SKILL.md still required; if 51 members with no SKILL.md → 422 either way
    with pytest.raises(SkillValidationError):
        extract_package(z, "cap.zip")


def test_extract_package_bad_suffix():
    with pytest.raises(SkillValidationError):
        extract_package(b"x", "cap.txt")


def test_validate_allowed_tools_default():
    fm = SkillFrontmatter(name="cap", description="x")  # allowed_tools None
    out = validate_allowed_tools(fm, registered={"query_orders", "query_work_orders"},
                                 default=["query_orders"], named={"dispatch_ready"})
    assert out == ["query_orders"]


def test_validate_allowed_tools_unknown():
    fm = SkillFrontmatter(name="cap", description="x", allowed_tools=["nope"])
    with pytest.raises(SkillValidationError):
        validate_allowed_tools(fm, registered={"query_orders"}, default=[], named=set())


def test_validate_allowed_tools_precond_key_outside():
    fm = SkillFrontmatter(name="cap", description="x",
                          allowed_tools=["query_orders"],
                          tool_preconditions={"dispatch_work_order": ["dispatch_ready"]})
    with pytest.raises(SkillValidationError):
        validate_allowed_tools(fm, registered={"query_orders"}, default=[], named={"dispatch_ready"})


def test_validate_allowed_tools_precond_unknown_assertion():
    fm = SkillFrontmatter(name="cap", description="x",
                          allowed_tools=["dispatch_work_order"],
                          tool_preconditions={"dispatch_work_order": ["mystery"]})
    with pytest.raises(SkillValidationError):
        validate_allowed_tools(fm, registered={"dispatch_work_order"},
                               default=[], named={"dispatch_ready"})


# --- Task 1.3: store.py ---

from scheduling_platform.skills.store import SkillStore


def _meta(name="cap", **kw):
    return SkillMeta(name=name, description="x", added_at="2026-07-05T00:00:00Z", **kw)


def test_store_save_get_list(tmp_path):
    s = SkillStore(tmp_path)
    s.save(_meta("cap"), "正文", {})
    assert s.get("cap").name == "cap"
    assert s.get_body("cap") == "正文"
    assert [m.name for m in s.list_all()] == ["cap"]
    assert s.version == 1


def test_store_save_duplicate(tmp_path):
    s = SkillStore(tmp_path)
    s.save(_meta("cap"), "正文", {})
    with pytest.raises(KeyError):
        s.save(_meta("cap"), "正文2", {})


def test_store_persist_reload(tmp_path):
    s = SkillStore(tmp_path)
    s.save(_meta("cap", file_count=1), "正文", {"docs/r.md": b"# r"})
    s2 = SkillStore(tmp_path)  # 重启重载
    assert s2.get("cap").file_count == 1
    assert s2.get_body("cap") == "正文"
    assert s2.read_attachment("cap", "docs/r.md") == {"path": "docs/r.md", "bytes": b"# r"}


def test_store_delete(tmp_path):
    s = SkillStore(tmp_path)
    s.save(_meta("cap"), "正文", {})
    assert s.delete("cap") is True
    assert s.get("cap") is None
    assert s.delete("cap") is False
    assert s.version == 2


def test_store_read_attachment_traversal(tmp_path):
    s = SkillStore(tmp_path)
    s.save(_meta("cap"), "正文", {})
    with pytest.raises(SkillValidationError):
        s.read_attachment("cap", "../../etc/passwd")


def test_store_read_attachment_sibling_prefix_traversal(tmp_path):
    """同前缀兄弟目录穿越: skill 'cap' + '../caption/secret'。
    旧的 str.startswith 检查会因 'caption' 以 'cap' 开头而放行;is_relative_to 正确拦截。"""
    s = SkillStore(tmp_path)
    s.save(_meta("cap"), "正文", {})
    sibling = tmp_path / "caption"
    sibling.mkdir()
    (sibling / "secret").write_bytes(b"x")
    with pytest.raises(SkillValidationError):
        s.read_attachment("cap", "../caption/secret")


def test_store_routable_and_examples(tmp_path):
    s = SkillStore(tmp_path)
    s.save(_meta("aa", disable_model_invocation=False, when_to_use=["出报告"]), "b", {})
    s.save(_meta("bb", disable_model_invocation=True, when_to_use=["x"]), "b", {})
    routable = [m.name for m in s.routable()]
    assert routable == ["aa"]
    assert s.routing_examples() == {"skill:aa": ["出报告"]}


# --- Task 2.1: bootstrap 装配 SkillStore / read_skill_file / named_preconditions ---

from scheduling_platform.bootstrap import build_platform
from scheduling_platform.config import Settings


def test_bootstrap_wires_skill_store_and_tool(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = Settings(llm_api_key="", audit_log_file=None,
                 sessions_dir=tmp_path / "sessions", skills_dir=tmp_path / "skills")
    p = build_platform(settings=s)
    assert p.skill_store is not None
    assert "read_skill_file" in p.tools.names()
    assert "dispatch_ready" in p.named_preconditions
    assert "expedite_valid" in p.named_preconditions
