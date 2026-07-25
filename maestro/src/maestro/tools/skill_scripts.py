"""Executing a skill's bundled scripts.

Three independent gates stand in front of any script:

1. the capability is declared ``writes=True, risk=HIGH``, so the Policy Gate
   always demands a human approval before the Runtime will run it;
2. the package must carry a trust record matching its **current** content hash,
   so editing a trusted skill revokes its own permission;
3. the script path is confined to the package's ``scripts/`` directory.

Only then does `sandbox.run_script` get involved, and that is containment
rather than a security boundary.
"""

from __future__ import annotations

from pathlib import Path

from maestro.runtime.capabilities import (
    CapabilityCall,
    CapabilityKind,
    CapabilityRegistry,
    CapabilityResult,
    CapabilitySpec,
    RiskLevel,
)
from maestro.runtime.paths import UnsafePathError, safe_join
from maestro.runtime.skills import SKILL_SCRIPT_CAPABILITY, SkillCatalog
from maestro.runtime.store import ArtifactStore
from maestro.skills.trust import SkillTrustStore

_TIMEOUT_SECONDS = 60.0


def normalize_script(script: str) -> str:
    """Models routinely drop the `scripts/` prefix; accept both spellings."""
    cleaned = script.strip().lstrip("./")
    if not cleaned.startswith("scripts/"):
        cleaned = f"scripts/{cleaned}"
    return cleaned


def _failed(message: str) -> CapabilityResult:
    return CapabilityResult(status="failed", error_message=message)


def register_skill_script_capability(
    registry: CapabilityRegistry,
    catalog: SkillCatalog,
    trust: SkillTrustStore,
    artifacts: ArtifactStore,
) -> None:
    from maestro.tools.sandbox import run_script

    async def execute(call: CapabilityCall, _key: str | None) -> CapabilityResult:
        name = call.arguments.get("skill")
        script = call.arguments.get("script")
        if not isinstance(name, str) or not name:
            return _failed("缺少必填参数 skill")
        if not isinstance(script, str) or not script:
            return _failed("缺少必填参数 script")
        raw_arguments = call.arguments.get("arguments") or []
        if not isinstance(raw_arguments, list) or not all(
            isinstance(item, str) for item in raw_arguments
        ):
            return _failed("arguments 必须是字符串数组")

        metadata = catalog.metadata(name)
        if metadata is None:
            return _failed(f"技能不存在或未启用: {name}")
        package_root = metadata.path.parent

        if not trust.is_trusted(name, package_root):
            status = trust.status(name, package_root)
            reason = (
                "技能内容已变更，原信任已失效"
                if not status.valid
                else "技能脚本未被信任"
            )
            return _failed(f"{reason}；请在扩展中心确认当前包 hash 后重试")

        relative = normalize_script(script)
        try:
            target = safe_join(package_root, relative)
        except UnsafePathError:
            return _failed(f"unsafe script path: {script!r}")
        if not target.is_file():
            return _failed(f"脚本不存在: {relative}")

        result = await run_script(
            package_root, relative, list(raw_arguments), timeout_seconds=_TIMEOUT_SECONDS
        )

        stored = []
        for produced, content in result.artifacts:
            reference = artifacts.put(content, "application/octet-stream")
            stored.append({"path": produced, "artifact_id": reference.artifact_id})

        content = {
            "skill": name,
            "script": relative,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timed_out": result.timed_out,
            # Report what containment actually took effect rather than implying
            # a guarantee the host cannot provide.
            "isolation": result.isolation,
            "artifacts": stored,
        }
        if result.timed_out:
            return CapabilityResult(
                status="failed", content=content,
                error_message=f"脚本超时（>{_TIMEOUT_SECONDS:.0f}s）已被终止",
            )
        if result.exit_code != 0:
            return CapabilityResult(
                status="failed", content=content,
                error_message=f"脚本以退出码 {result.exit_code} 结束",
            )
        return CapabilityResult(status="succeeded", content=content)

    registry.register(
        CapabilitySpec(
            name=SKILL_SCRIPT_CAPABILITY,
            kind=CapabilityKind.TOOL,
            description=(
                "运行当前已加载技能自带的脚本（scripts/ 下的 .py 或 .sh）。"
                "需要该技能已被信任，且每次执行都需人工确认。"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "skill": {"type": "string"},
                    "script": {"type": "string"},
                    "arguments": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["skill", "script"],
            },
            risk=RiskLevel.HIGH,
            writes=True,
            idempotent=False,
            executor=execute,
        ),
        replace=True,
    )
