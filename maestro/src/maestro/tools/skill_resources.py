"""Third-tier skill loading: reading a selected Skill's bundled resources.

Tier 1 is the frontmatter read during discovery, tier 2 is the SKILL.md body
injected when a Skill is selected.  This capability is tier 3 — it lets the
model pull in a `references/` file only when it actually needs it, instead of
paying for the whole package up front.

Which Skills a call may target is enforced by the RunCoordinator against the
Skills loaded into the current Run, because only the Run knows that.
"""

from __future__ import annotations

from maestro.runtime.capabilities import (
    CapabilityCall,
    CapabilityKind,
    CapabilityRegistry,
    CapabilityResult,
    CapabilitySpec,
    RiskLevel,
)
from maestro.runtime.skills import (
    SKILL_RESOURCE_CAPABILITY,
    SkillCatalog,
    SkillResourceError,
)
_MAX_RESOURCE_BYTES = 256 * 1024


def register_skill_resource_capability(
    registry: CapabilityRegistry, catalog: SkillCatalog
) -> None:
    async def read_resource(call: CapabilityCall, _key: str | None) -> CapabilityResult:
        skill = call.arguments.get("skill")
        resource = call.arguments.get("resource")
        if not isinstance(skill, str) or not skill:
            return CapabilityResult(status="failed", error_message="缺少必填参数 skill")
        if not isinstance(resource, str) or not resource:
            return CapabilityResult(status="failed", error_message="缺少必填参数 resource")
        try:
            content = catalog.read_resource(skill, resource)
        except KeyError:
            return CapabilityResult(status="failed", error_message=f"技能不存在: {skill}")
        except SkillResourceError as error:
            return CapabilityResult(status="failed", error_message=str(error))
        except (OSError, UnicodeDecodeError) as error:
            return CapabilityResult(status="failed", error_message=f"无法读取资源: {error}")
        truncated = len(content.encode("utf-8")) > _MAX_RESOURCE_BYTES
        if truncated:
            content = content.encode("utf-8")[:_MAX_RESOURCE_BYTES].decode("utf-8", "ignore")
        return CapabilityResult(
            status="succeeded",
            content={
                "skill": skill,
                "resource": resource,
                "content": content,
                "truncated": truncated,
            },
        )

    registry.register(
        CapabilitySpec(
            name=SKILL_RESOURCE_CAPABILITY,
            kind=CapabilityKind.TOOL,
            description=(
                "读取当前已加载技能自带的资源文件（references/ 或 scripts/ 下），"
                "resource 为相对该技能目录的路径。"
            ),
            input_schema={
                "type": "object",
                "properties": {"skill": {"type": "string"}, "resource": {"type": "string"}},
                "required": ["skill", "resource"],
            },
            risk=RiskLevel.LOW,
            executor=read_resource,
        ),
        replace=True,
    )
