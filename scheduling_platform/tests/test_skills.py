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
