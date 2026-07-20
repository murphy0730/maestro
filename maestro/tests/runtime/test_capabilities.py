import pytest

from maestro.runtime.capabilities import CapabilityKind, CapabilityRegistry, CapabilitySpec, RiskLevel


def test_snapshot_pins_content_hash() -> None:
    registry = CapabilityRegistry()
    registry.register(CapabilitySpec(name="read", kind=CapabilityKind.TOOL, version="1"))
    snapshot = registry.snapshot()
    registry.register(CapabilitySpec(name="read", kind=CapabilityKind.TOOL, version="2"), replace=True)
    assert snapshot.require("read").version == "1"


def test_registry_does_not_expose_mutable_descriptor_data() -> None:
    registry = CapabilityRegistry()
    registry.register(CapabilitySpec(name="read", kind=CapabilityKind.TOOL, input_schema={"x": {}}))
    registry.require("read").input_schema["x"] = {"changed": True}
    assert registry.require("read").input_schema == {"x": {}}


def test_capability_risk_is_normalized_and_validated() -> None:
    assert CapabilitySpec(name="write", kind=CapabilityKind.MCP, risk="high").risk is RiskLevel.HIGH  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="invalid capability risk"):
        CapabilitySpec(name="write", kind=CapabilityKind.MCP, risk="critical")  # type: ignore[arg-type]
