from __future__ import annotations

from pathlib import Path

import pytest

from maestro.runtime.capabilities import CapabilityKind, CapabilityRegistry, CapabilitySpec
from maestro.runtime.skills import (
    RemoteSkillExecutionDenied,
    SkillCatalog,
    SkillResourceError,
    SkillValidationError,
)


@pytest.fixture
def skill_catalog() -> SkillCatalog:
    registry = CapabilityRegistry()
    registry.register(CapabilitySpec(name="read_file", kind=CapabilityKind.TOOL))
    registry.register(CapabilitySpec(name="grep", kind=CapabilityKind.TOOL))
    fixtures = Path(__file__).parent / "fixtures" / "skills"
    return SkillCatalog({"project": fixtures / "resources"}, registry.snapshot())


def test_discovery_does_not_read_body_or_resources(skill_catalog: SkillCatalog) -> None:
    metadata = skill_catalog.discover()
    assert metadata["resources"].description
    assert skill_catalog.io_log == ["resources/SKILL.md:frontmatter"]


def test_load_reads_full_skill_only(skill_catalog: SkillCatalog) -> None:
    loaded = skill_catalog.load("resources", arguments="WO-1", session_id="run-1")
    assert "references/guide.md" in loaded.prompt
    assert "guide body" not in loaded.prompt
    assert "run-1" in loaded.prompt
    assert skill_catalog.io_log == ["resources/SKILL.md:full"]


def test_resource_read_rejects_traversal(skill_catalog: SkillCatalog) -> None:
    with pytest.raises(SkillResourceError):
        skill_catalog.read_resource("resources", "../secret")


def test_claude_tool_aliases_map_to_registered_capabilities() -> None:
    registry = CapabilityRegistry()
    registry.register(CapabilitySpec(name="read_file", kind=CapabilityKind.TOOL))
    registry.register(CapabilitySpec(name="grep", kind=CapabilityKind.TOOL))
    fixtures = Path(__file__).parent / "fixtures" / "skills"
    catalog = SkillCatalog({"project": fixtures / "inline"}, registry.snapshot())

    metadata = catalog.discover()["inspect-order"]

    assert metadata.allowed_tools == ("read_file", "grep")


def test_unknown_allowed_tool_fails_validation(tmp_path: Path) -> None:
    skill = tmp_path / "bad" / "SKILL.md"
    skill.parent.mkdir()
    skill.write_text("---\nname: bad\ndescription: bad\nallowed-tools: Mystery\n---\nbody\n")
    catalog = SkillCatalog({"project": skill.parent}, CapabilityRegistry().snapshot())

    with pytest.raises(SkillValidationError, match="unknown capability"):
        catalog.discover()


def test_remote_mcp_inline_shell_is_denied(tmp_path: Path) -> None:
    skill = tmp_path / "remote" / "SKILL.md"
    skill.parent.mkdir()
    skill.write_text("---\nname: remote\ndescription: remote\nshell: echo dangerous\n---\nbody\n")
    catalog = SkillCatalog({"mcp": skill.parent}, CapabilityRegistry().snapshot())

    with pytest.raises(RemoteSkillExecutionDenied):
        catalog.discover()


def test_higher_priority_source_wins_and_loser_is_diagnosable(tmp_path: Path) -> None:
    for source, description in (("project", "project copy"), ("managed", "managed copy")):
        skill = tmp_path / source / "same" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(f"---\nname: same\ndescription: {description}\n---\nbody\n")
    catalog = SkillCatalog(
        {"project": tmp_path / "project", "managed": tmp_path / "managed"},
        CapabilityRegistry().snapshot(),
    )

    discovered = catalog.discover()

    assert discovered["same"].description == "managed copy"
    assert [item.source for item in catalog.inactive] == ["project"]


def test_discovery_stays_bounded_when_skill_body_is_large(tmp_path: Path) -> None:
    skill = tmp_path / "large" / "SKILL.md"
    skill.parent.mkdir()
    skill.write_text("---\nname: large\ndescription: large\n---\n" + "x" * (17 * 1024))
    catalog = SkillCatalog({"project": skill.parent}, CapabilityRegistry().snapshot())

    assert catalog.discover()["large"].description == "large"
