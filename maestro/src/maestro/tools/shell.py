"""Running one shell command in the workspace.

This exists because `allowed-tools: Bash` is the single most common declaration
in real Claude Code skills, and an alias pointing at nothing turns every such
package into a discovery failure.  It is a generic host primitive, not domain
logic.

Be clear about what it is: **arbitrary command execution**.  It is declared
`writes=True, risk=HIGH`, so the Policy Gate demands a human approval before
every single call — that approval is the real gate.  `tools/sandbox.py` adds
containment (no inherited API keys, no network and workspace-scoped writes under
a macOS seatbelt profile, wall-clock and output caps), but containment is not a
security boundary, and unlike `read_file`/`write_file` a shell cannot be proven
to stay inside the workspace.  `isolation` in the result reports what actually
took effect rather than implying a guarantee the host cannot make.
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

SHELL_CAPABILITY = "bash"

_TIMEOUT_SECONDS = 60.0
_MAX_COMMAND_CHARS = 8_000


def register_shell_capability(registry: CapabilityRegistry, workspace_root: Path) -> None:
    """Register the workspace shell primitive into `registry`."""
    from maestro.tools.sandbox import run_command

    root = Path(workspace_root)

    async def execute(call: CapabilityCall, _key: str | None) -> CapabilityResult:
        command = call.arguments.get("command")
        if not isinstance(command, str) or not command.strip():
            return CapabilityResult(status="failed", error_message="缺少必填参数 command")
        if len(command) > _MAX_COMMAND_CHARS:
            return CapabilityResult(
                status="failed",
                error_message=f"命令过长（>{_MAX_COMMAND_CHARS} 字符）",
            )

        result = await run_command(command, root, timeout_seconds=_TIMEOUT_SECONDS)
        content = {
            "command": command,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timed_out": result.timed_out,
            "isolation": result.isolation,
        }
        if result.timed_out:
            return CapabilityResult(
                status="failed", content=content,
                error_message=f"命令超时（>{_TIMEOUT_SECONDS:.0f}s）已被终止",
            )
        # A non-zero exit is the command's own answer, not a runtime failure:
        # returning it as a result lets the model read stderr and correct itself.
        return CapabilityResult(status="succeeded", content=content)

    registry.register(
        CapabilitySpec(
            name=SHELL_CAPABILITY,
            kind=CapabilityKind.TOOL,
            description=(
                "在工作区目录内执行一条 shell 命令，返回 stdout/stderr/exit_code。"
                "每次执行都需人工确认。"
            ),
            input_schema={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
            risk=RiskLevel.HIGH,
            writes=True,
            idempotent=False,
            executor=execute,
        ),
        replace=True,
    )
