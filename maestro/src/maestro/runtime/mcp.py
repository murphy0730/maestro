"""Generic local MCP capability registration boundary.

Transport clients may call this adapter after discovery; remote metadata never
sets write/risk policy on its own.
"""

from collections.abc import Awaitable, Callable

from maestro.runtime.capabilities import CapabilityCall, CapabilityKind, CapabilityRegistry, CapabilityResult, CapabilitySpec, RiskLevel


MCPExecutor = Callable[[str, dict[str, object]], Awaitable[object]]


class MCPConnector:
    def __init__(self, capabilities: CapabilityRegistry) -> None:
        self._capabilities = capabilities

    def register(
        self,
        server_name: str,
        tool_name: str,
        *,
        description: str = "",
        input_schema: dict[str, object] | None = None,
        writes: bool = False,
        risk: RiskLevel = RiskLevel.LOW,
        executor: MCPExecutor,
        idempotent: bool = True,
    ) -> str:
        """Register locally governed MCP metadata and its transport executor."""
        name = f"mcp__{server_name}__{tool_name}"

        async def execute(call: CapabilityCall, _key: str | None) -> CapabilityResult:
            return CapabilityResult(status="succeeded", content=await executor(tool_name, call.arguments))

        self._capabilities.register(
            CapabilitySpec(
                name=name, kind=CapabilityKind.MCP, description=description,
                input_schema=input_schema or {}, writes=writes, risk=risk,
                idempotent=idempotent, executor=execute,
            ),
            replace=True,
        )
        return name
