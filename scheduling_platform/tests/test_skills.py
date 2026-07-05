import pytest
from datetime import datetime, timezone
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
