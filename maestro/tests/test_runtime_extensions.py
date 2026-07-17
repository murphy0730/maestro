from maestro.bootstrap import build_platform
from maestro.config import Settings
from maestro.runtime.capabilities import CapabilityKind, CapabilityResult, CapabilitySpec
from maestro.runtime.intent import IntentRequest
from maestro.runtime.models import RunStatus


async def test_platform_accepts_mcp_registration_after_startup(tmp_path) -> None:
    platform = build_platform(Settings(skills_dir=tmp_path / "skills"))

    async def transport(_tool: str, _args: dict[str, object]) -> object:
        return {"ok": True}

    name = platform.mcp.register("demo", "lookup", executor=transport)
    intent = platform.runtime._intent_classifier.build(IntentRequest(message="lookup", tool_names=[name]))

    assert name in intent.candidate_capabilities
    assert platform.capabilities.require(name).kind is CapabilityKind.MCP


def test_skill_discovery_uses_current_capability_registry(tmp_path) -> None:
    skills = tmp_path / "skills"
    platform = build_platform(Settings(skills_dir=skills))

    async def read(_call, _key) -> CapabilityResult:
        return CapabilityResult(status="succeeded", content={})

    platform.capabilities.register(CapabilitySpec(name="read", kind=CapabilityKind.TOOL, executor=read))
    path = skills / "inspect" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text("---\nname: inspect\ndescription: inspect\nallowed-tools: read\n---\ninspect\n")

    intent = platform.runtime._intent_classifier.build(
        IntentRequest(message="inspect", requested_skills=["inspect"])
    )

    assert intent.candidate_capabilities == ["inspect", "read"]


def test_build_platform_registers_discovered_skill_as_runtime_capability(tmp_path) -> None:
    skills = tmp_path / "skills"
    path = skills / "inspect" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text("---\nname: inspect\ndescription: inspect\ncontext: inline\n---\ninspect\n")

    platform = build_platform(Settings(skills_dir=skills))

    assert platform.capabilities.require("inspect").kind is CapabilityKind.SKILL
    assert "inspect" in platform.refresh_skills()
    intent = platform.runtime._intent_classifier.build(IntentRequest(message="inspect", requested_skills=["inspect"]))
    assert "inspect" in intent.candidate_capabilities


def test_refresh_skills_does_not_replace_a_same_named_tool_or_mcp(tmp_path) -> None:
    skills = tmp_path / "skills"
    for name in ("tool-collision", "mcp-collision"):
        path = skills / name / "SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text(f"---\nname: {name}\ndescription: collision\n---\ncollision\n")
    platform = build_platform(Settings(skills_dir=skills))

    async def tool_executor(_call, _key) -> CapabilityResult:
        return CapabilityResult(status="succeeded")

    platform.capabilities.register(
        CapabilitySpec(name="tool-collision", kind=CapabilityKind.TOOL, risk="high", executor=tool_executor),
        replace=True,
    )
    platform.capabilities.register(
        CapabilitySpec(name="mcp-collision", kind=CapabilityKind.MCP, risk="medium", executor=tool_executor),
        replace=True,
    )

    assert platform.refresh_skills() == {}
    assert platform.skill_catalog.metadata("tool-collision") is None
    assert platform.skill_catalog.metadata("mcp-collision") is None
    tool = platform.capabilities.require("tool-collision")
    mcp = platform.capabilities.require("mcp-collision")
    assert tool.kind is CapabilityKind.TOOL
    assert tool.risk == "high"
    assert tool.executor is tool_executor
    assert mcp.kind is CapabilityKind.MCP
    assert mcp.risk == "medium"
    assert mcp.executor is tool_executor


def test_disabled_skill_is_registered_for_explicit_use_but_never_model_visible(tmp_path) -> None:
    skills = tmp_path / "skills"
    path = skills / "manual-only" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text("---\nname: manual-only\ndescription: manual\ndisable-model-invocation: true\n---\nmanual\n")
    platform = build_platform(Settings(skills_dir=skills))

    assert platform.capabilities.require("manual-only").kind is CapabilityKind.SKILL
    assert "manual-only" not in {
        spec.name for spec in platform.runtime._available(platform.capabilities.snapshot(), None, None)
    }


def test_refresh_removes_deleted_skill_capability(tmp_path) -> None:
    skills = tmp_path / "skills"
    path = skills / "temporary" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text("---\nname: temporary\ndescription: temporary\n---\ntemporary\n")
    platform = build_platform(Settings(skills_dir=skills))
    assert platform.capabilities.require("temporary").kind is CapabilityKind.SKILL

    path.unlink()
    path.parent.rmdir()
    platform.refresh_skills()

    try:
        platform.capabilities.require("temporary")
    except KeyError:
        pass
    else:
        raise AssertionError("deleted Skill remained registered")


async def test_run_with_deleted_skill_fails_terminally_instead_of_lingering(tmp_path) -> None:
    skills = tmp_path / "skills"
    path = skills / "gone" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text("---\nname: gone\ndescription: gone\n---\ngone\n")
    platform = build_platform(Settings(skills_dir=skills))
    run = await platform.runtime.create("use gone", requested_skills=["gone"])

    path.unlink()
    path.parent.rmdir()
    platform.refresh_skills()
    finished = await platform.runtime.execute(run.run_id)

    assert finished.status is RunStatus.FAILED
    assert finished.status not in {RunStatus.RUNNING_FAST, RunStatus.RUNNING_STRUCTURED}
