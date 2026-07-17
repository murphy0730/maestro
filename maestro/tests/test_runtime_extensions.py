from maestro.bootstrap import build_platform
from maestro.config import Settings
from maestro.runtime.capabilities import CapabilityKind, CapabilityResult, CapabilitySpec
from maestro.runtime.intent import IntentRequest


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

    assert intent.candidate_capabilities == ["read"]
