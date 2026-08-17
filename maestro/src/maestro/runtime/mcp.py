"""Generic local MCP capability registration boundary.

Transport clients call this adapter after discovery; remote metadata never sets
write/risk policy on its own.  The adapter is deliberately transport-agnostic —
it takes an executor and knows nothing about how the call travels.
"""

from collections.abc import Awaitable, Callable

from maestro.runtime.capabilities import (
    CapabilityCall,
    CapabilityKind,
    CapabilityRegistry,
    CapabilityResult,
    CapabilitySpec,
    RiskLevel,
)
from maestro.runtime.models import RuntimeErrorKind

MCPExecutor = Callable[[str, dict[str, object], str | None], Awaitable[object]]
_MAX_MCP_SUMMARY_CHARS = 2_000


class MCPCapabilityConflict(ValueError):
    """A remote tool tried to take a name an operational capability already holds."""


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
        self._refuse_foreign_owner(name)

        async def execute(call: CapabilityCall, _key: str | None) -> CapabilityResult:
            # A transport or remote failure is this capability failing, not the
            # Runtime crashing: report it as data so the Run can react.
            try:
                content = await executor(tool_name, call.arguments, call.principal_id)
            except Exception as error:  # noqa: BLE001 — boundary to an external process
                return CapabilityResult(
                    status="failed",
                    error_kind=RuntimeErrorKind.TRANSIENT_INFRASTRUCTURE,
                    error_message=f"{type(error).__name__}: {error}",
                )
            if isinstance(content, CapabilityResult):
                return content
            return CapabilityResult(
                status="succeeded",
                content=_normalize_result(server_name, tool_name, content),
            )

        self._capabilities.register(
            CapabilitySpec(
                name=name, kind=CapabilityKind.MCP, description=description,
                input_schema=input_schema or {}, writes=writes, risk=risk,
                idempotent=idempotent, executor=execute,
            ),
            replace=True,
        )
        return name

    def unregister(self, server_name: str, tool_name: str) -> bool:
        return self._capabilities.unregister(
            f"mcp__{server_name}__{tool_name}", kind=CapabilityKind.MCP
        )

    def _refuse_foreign_owner(self, name: str) -> None:
        """Mirror the Skill rule: a remote tool may only replace its own entry.

        Registration is `replace=True` so a reconnect can refresh metadata, which
        would otherwise let a server called `read` shadow the host's own tool.
        """
        try:
            existing = self._capabilities.require(name)
        except KeyError:
            return
        if existing.kind is not CapabilityKind.MCP:
            raise MCPCapabilityConflict(
                f"capability {name} is already registered as {existing.kind.value}"
            )


def _normalize_result(server_name: str, tool_name: str, result: object) -> object:
    if (
        not isinstance(result, dict)
        or "structuredContent" not in result
        or result["structuredContent"] is None
    ):
        return result
    return {
        "data": result["structuredContent"],
        "summary": _text_summary(result),
        "mcp": {"server": server_name, "tool": tool_name},
    }


def _text_summary(result: dict) -> str:
    texts: list[str] = []
    content = result.get("content")
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "text":
                continue
            text = item.get("text")
            if isinstance(text, str) and text:
                texts.append(text)
    return "\n".join(texts).strip()[:_MAX_MCP_SUMMARY_CHARS]
