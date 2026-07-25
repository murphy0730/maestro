"""Reading back a stored artifact.

When a capability result exceeds the coordinator's inline budget it is spilled
into the `ArtifactStore` and the model is handed a reference instead of the
content.  Without a way to dereference that reference the result is simply lost,
so this primitive exists to complete the round trip.

Read-only and low risk, but not unrestricted: `RunCoordinator._artifact_call_is_owned`
confines it to artifacts the Run has actually seen.
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
from maestro.runtime.store import ARTIFACT_READ_CAPABILITY, ArtifactStore, InvalidStorageId

_MAX_READ_BYTES = 256 * 1024


def register_artifact_capability(registry: CapabilityRegistry, artifacts: ArtifactStore) -> None:
    """Register the artifact read-back primitive into `registry`."""

    async def read_artifact(call: CapabilityCall, _key: str | None) -> CapabilityResult:
        artifact_id = call.arguments.get("artifact_id")
        if not isinstance(artifact_id, str) or not artifact_id:
            return CapabilityResult(status="failed", error_message="缺少必填参数 artifact_id")
        try:
            content = artifacts.get(artifact_id)
        except InvalidStorageId as error:
            return CapabilityResult(status="failed", error_message=str(error))
        except OSError:
            return CapabilityResult(
                status="failed", error_message=f"产物不存在: {artifact_id}"
            )
        truncated = len(content) > _MAX_READ_BYTES
        text = content[:_MAX_READ_BYTES].decode("utf-8", "replace")
        return CapabilityResult(
            status="succeeded",
            content={
                "artifact_id": artifact_id,
                "content": text,
                "bytes": len(content),
                "truncated": truncated,
            },
        )

    registry.register(
        CapabilitySpec(
            name=ARTIFACT_READ_CAPABILITY,
            kind=CapabilityKind.TOOL,
            description=(
                "读取此前被存为产物的能力结果。参数 artifact_id 为上下文中 "
                "'Reference: artifact:<id>' 里的 id。"
            ),
            input_schema={
                "type": "object",
                "properties": {"artifact_id": {"type": "string"}},
                "required": ["artifact_id"],
            },
            risk=RiskLevel.LOW,
            executor=read_artifact,
        ),
        replace=True,
    )
