"""Return the current date and time, optionally in a given IANA timezone.

Read-only, low-risk host primitive. Skill ``time-query`` exposes it through
``allowed-tools: [get_current_time]`` so the model can answer time questions
without shelling out.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from maestro.runtime.capabilities import (
    CapabilityCall,
    CapabilityKind,
    CapabilityRegistry,
    CapabilityResult,
    CapabilitySpec,
    RiskLevel,
)

DATETIME_CAPABILITY = "get_current_time"


def register_datetime_capability(registry: CapabilityRegistry, workspace_root) -> None:
    """Register the current-time primitive into ``registry``."""

    async def execute(call: CapabilityCall, _key: str | None) -> CapabilityResult:
        tz_name = call.arguments.get("timezone")
        try:
            tz = ZoneInfo(tz_name) if tz_name else ZoneInfo("UTC")
        except Exception:  # noqa: BLE001 -- untrusted IANA name from the model
            return CapabilityResult(
                status="failed",
                error_message=(
                    f"无法识别的时区: {tz_name!r}（请使用 IANA 名称，如 Asia/Shanghai）"
                ),
            )

        now = datetime.now(tz)
        content = {
            "datetime": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "weekday": now.strftime("%A"),
            "timezone": str(tz),
        }
        return CapabilityResult(status="succeeded", content=content)

    registry.register(
        CapabilitySpec(
            name=DATETIME_CAPABILITY,
            kind=CapabilityKind.TOOL,
            description=(
                "返回当前日期与时间，可选指定 IANA 时区（如 Asia/Shanghai）。"
                "只读，不改变任何状态。"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "IANA 时区名，如 Asia/Shanghai / America/New_York，缺省为 UTC",
                    }
                },
                "required": [],
            },
            risk=RiskLevel.LOW,
            writes=False,
            idempotent=True,
            executor=execute,
        ),
        replace=True,
    )
