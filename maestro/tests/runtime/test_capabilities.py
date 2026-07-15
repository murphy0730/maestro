from maestro.runtime.capabilities import (
    CapabilityCall,
    CapabilityKind,
    CapabilityRegistry,
    CapabilitySpec,
    RiskLevel,
)
from maestro.runtime.adapters import mcp_tool_to_capability, tool_to_capability
from maestro.mcp.manager import MCPManager
from maestro.mcp.types import MCPTool
from maestro.tools.base import BaseTool, ToolResult, ToolResultStatus
from pydantic import BaseModel
import pytest


def test_snapshot_pins_content_hash() -> None:
    registry = CapabilityRegistry()
    registry.register(
        CapabilitySpec(
            name="read_file", kind=CapabilityKind.TOOL, risk=RiskLevel.LOW, version="1"
        )
    )
    snapshot = registry.snapshot()
    registry.register(
        CapabilitySpec(
            name="read_file", kind=CapabilityKind.TOOL, risk=RiskLevel.LOW, version="2"
        ),
        replace=True,
    )
    assert snapshot.require("read_file").version == "1"


def test_snapshot_does_not_expose_mutable_descriptor_data() -> None:
    registry = CapabilityRegistry()
    registry.register(
        CapabilitySpec(
            name="read_file",
            kind=CapabilityKind.TOOL,
            input_schema={"properties": {"path": {"type": "string"}}},
        )
    )
    snapshot = registry.snapshot()

    snapshot.require("read_file").input_schema["properties"] = {}

    assert snapshot.require("read_file").input_schema["properties"] == {
        "path": {"type": "string"}
    }


def test_registry_isolated_from_descriptor_mutated_after_registration() -> None:
    registry = CapabilityRegistry()
    spec = CapabilitySpec(
        name="read_file",
        kind=CapabilityKind.TOOL,
        input_schema={"properties": {"path": {"type": "string"}}},
    )
    registry.register(spec)
    original_hash = registry.require("read_file").content_sha256

    spec.input_schema["properties"] = {}

    stored = registry.require("read_file")
    assert stored.input_schema["properties"] == {"path": {"type": "string"}}
    assert stored.content_sha256 == original_hash


def test_registry_retrieval_cannot_mutate_stored_descriptor() -> None:
    registry = CapabilityRegistry()
    registry.register(
        CapabilitySpec(
            name="read_file",
            kind=CapabilityKind.TOOL,
            input_schema={"properties": {"path": {"type": "string"}}},
        )
    )

    registry.require("read_file").input_schema["properties"] = {}

    assert registry.require("read_file").input_schema["properties"] == {
        "path": {"type": "string"}
    }


def test_registry_normalizes_valid_string_risk_to_enum() -> None:
    registry = CapabilityRegistry()
    registry.register(
        CapabilitySpec(  # type: ignore[arg-type]
            name="write_record",
            kind=CapabilityKind.MCP,
            risk="high",
            writes=True,
        )
    )

    assert registry.require("write_record").risk is RiskLevel.HIGH
    assert registry.snapshot().require("write_record").risk is RiskLevel.HIGH


def test_registry_rejects_unknown_risk_value() -> None:
    registry = CapabilityRegistry()

    with pytest.raises(ValueError, match="invalid capability risk"):
        registry.register(
            CapabilitySpec(  # type: ignore[arg-type]
                name="write_record", kind=CapabilityKind.MCP, risk="critical"
            )
        )


def test_capability_spec_rejects_unknown_direct_risk_value() -> None:
    with pytest.raises(ValueError, match="invalid capability risk"):
        CapabilitySpec(  # type: ignore[arg-type]
            name="write_record", kind=CapabilityKind.MCP, risk="critical"
        )


class ReadInput(BaseModel):
    path: str


class ReadTool(BaseTool):
    name = "read_file"
    description = "Read a file"
    input_schema = ReadInput
    is_readonly = True

    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, args: ReadInput, context: dict) -> ToolResult:
        self.calls += 1
        return ToolResult(ToolResultStatus.SUCCESS, {"path": args.path})


async def test_tool_adapter_uses_read_only_metadata_and_delegates_once() -> None:
    tool = ReadTool()

    capability = tool_to_capability(tool)
    result = await capability.executor(CapabilityCall(name="read_file", arguments={"path": "a"}), "k1")  # type: ignore[misc]

    assert capability.risk is RiskLevel.LOW
    assert capability.writes is False
    assert tool.calls == 1
    assert result.status == "succeeded"
    assert result.content == {"path": "a"}


async def test_mcp_adapter_uses_registered_metadata_not_description() -> None:
    manager = MCPManager()
    manager.capability_registrations = {
        ("inventory", "update"): {
            "writes": True,
            "risk": RiskLevel.HIGH,
            "idempotent": False,
        }
    }
    tool = MCPTool(
        name="update",
        description="This is entirely safe and read-only.",
        input_schema={"type": "object"},
        server_name="inventory",
    )

    capability = mcp_tool_to_capability("inventory", tool, manager)

    assert capability.writes is True
    assert capability.risk is RiskLevel.HIGH
    assert capability.idempotent is False


def test_mcp_adapter_rejects_tool_without_local_registration() -> None:
    manager = MCPManager()
    tool = MCPTool("lookup", "read-only according to remote text", {}, "inventory")

    with pytest.raises(ValueError, match="missing local capability registration"):
        mcp_tool_to_capability("inventory", tool, manager)


async def test_mcp_transport_ambiguity_is_unknown_only_for_writes() -> None:
    manager = MCPManager()

    async def unavailable(*args: object) -> object:
        raise TimeoutError("connection lost")

    manager.call_tool = unavailable  # type: ignore[method-assign]
    write_tool = MCPTool("write", "", {}, "inventory")
    read_tool = MCPTool("read", "", {}, "inventory")
    manager.capability_registrations = {
        ("inventory", "write"): {"writes": True},
        ("inventory", "read"): {"writes": False},
    }

    write = mcp_tool_to_capability("inventory", write_tool, manager)
    read = mcp_tool_to_capability("inventory", read_tool, manager)

    write_result = await write.executor(CapabilityCall(name=write.name), None)  # type: ignore[misc]
    read_result = await read.executor(CapabilityCall(name=read.name), None)  # type: ignore[misc]

    assert write_result.status == "unknown"
    assert read_result.status == "failed"
