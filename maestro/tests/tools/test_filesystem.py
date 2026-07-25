from __future__ import annotations

from pathlib import Path

import pytest

from maestro.bootstrap import build_platform
from maestro.config import Settings
from maestro.runtime.capabilities import CapabilityCall, CapabilityRegistry, RiskLevel
from maestro.tools import register_filesystem_capabilities


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    (root / "notes").mkdir(parents=True)
    (root / "notes" / "a.md").write_text("hello\nworld\n", "utf-8")
    (root / "b.txt").write_text("needle here\n", "utf-8")
    return root


@pytest.fixture
def registry(workspace: Path) -> CapabilityRegistry:
    registry = CapabilityRegistry()
    register_filesystem_capabilities(registry, workspace)
    return registry


async def call(registry: CapabilityRegistry, name: str, **arguments):
    spec = registry.require(name)
    assert spec.executor is not None
    return await spec.executor(CapabilityCall(name=name, arguments=arguments), None)


async def test_read_file_returns_content(registry: CapabilityRegistry) -> None:
    result = await call(registry, "read_file", path="notes/a.md")

    assert result.status == "succeeded"
    assert result.content["content"] == "hello\nworld"
    assert result.content["total_lines"] == 2


async def test_glob_lists_workspace_files(registry: CapabilityRegistry) -> None:
    result = await call(registry, "glob", pattern="**/*.md")

    assert result.content["matches"] == ["notes/a.md"]


async def test_grep_finds_matches_with_line_numbers(registry: CapabilityRegistry) -> None:
    result = await call(registry, "grep", pattern="needle")

    assert result.content["matches"] == [{"path": "b.txt", "line": 1, "text": "needle here"}]


@pytest.mark.parametrize(
    "path",
    ["../outside.txt", "/etc/passwd", "C:/secret", r"notes\a.md", "notes/\x7f.md", ""],
)
async def test_read_file_refuses_to_escape_the_workspace(
    registry: CapabilityRegistry, path: str
) -> None:
    result = await call(registry, "read_file", path=path)

    assert result.status == "failed"


async def test_read_file_refuses_a_symlink_pointing_outside(
    registry: CapabilityRegistry, workspace: Path, tmp_path: Path
) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("classified", "utf-8")
    (workspace / "link.txt").symlink_to(secret)

    result = await call(registry, "read_file", path="link.txt")

    assert result.status == "failed"
    assert "classified" not in str(result.content)


async def test_write_and_edit_are_high_risk_writes(registry: CapabilityRegistry) -> None:
    """The Policy Gate turns writes=True + HIGH into a human approval."""
    for name in ("write_file", "edit_file"):
        spec = registry.require(name)
        assert spec.writes is True
        assert spec.risk is RiskLevel.HIGH


async def test_write_file_stays_inside_the_workspace(
    registry: CapabilityRegistry, workspace: Path
) -> None:
    denied = await call(registry, "write_file", path="../escaped.txt", content="x")
    assert denied.status == "failed"
    assert not (workspace.parent / "escaped.txt").exists()

    allowed = await call(registry, "write_file", path="out/new.txt", content="x")
    assert allowed.status == "succeeded"
    assert (workspace / "out" / "new.txt").read_text("utf-8") == "x"


async def test_edit_file_requires_a_unique_match(
    registry: CapabilityRegistry, workspace: Path
) -> None:
    (workspace / "dup.txt").write_text("a\na\n", "utf-8")

    result = await call(registry, "edit_file", path="dup.txt", old="a", new="b")

    assert result.status == "failed"
    assert "唯一" in (result.error_message or "")
    assert (workspace / "dup.txt").read_text("utf-8") == "a\na\n"


def test_skill_declaring_claude_tool_names_now_discovers(tmp_path: Path) -> None:
    """`allowed-tools: [Read, Grep]` used to fail: nothing was registered."""
    skills = tmp_path / "skills"
    path = skills / "inspect" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "---\nname: inspect\ndescription: inspect\nallowed-tools: [Read, Grep]\n---\ninspect\n"
    )

    platform = build_platform(
        Settings(skills_dir=skills, workspace_root=tmp_path / "workspace")
    )

    assert platform.skill_catalog.metadata("inspect").allowed_tools == ("read_file", "grep")
    assert not [error for error in platform.skill_catalog.errors if "inspect" in str(error.path)]
