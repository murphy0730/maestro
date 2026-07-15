from maestro.runtime.capabilities import (
    CapabilityCall,
    CapabilityKind,
    CapabilitySpec,
    RiskLevel,
)
from maestro.runtime.policy import PolicyContext, PolicyEffect, PolicyGate, PolicyRule


def test_skill_allow_cannot_override_policy_deny() -> None:
    gate = PolicyGate(
        [
            PolicyRule(
                pattern="dangerous_*", effect=PolicyEffect.DENY, source="organization"
            )
        ]
    )
    spec = CapabilitySpec(
        name="dangerous_write",
        kind=CapabilityKind.TOOL,
        risk=RiskLevel.HIGH,
        writes=True,
    )
    decision = gate.evaluate(
        CapabilityCall(name=spec.name, arguments={}),
        spec,
        PolicyContext(principal_id="u1", skill_allowed_tools={spec.name}),
    )
    assert decision.effect is PolicyEffect.DENY


def test_high_risk_write_requires_confirmation() -> None:
    spec = CapabilitySpec(
        name="write_mes", kind=CapabilityKind.MCP, risk=RiskLevel.HIGH, writes=True
    )
    decision = PolicyGate([]).evaluate(
        CapabilityCall(name=spec.name, arguments={}),
        spec,
        PolicyContext(principal_id="u1"),
    )
    assert decision.effect is PolicyEffect.REQUIRE_CONFIRMATION


def test_skill_allowed_tools_is_a_narrowing_allowlist() -> None:
    spec = CapabilitySpec(name="read_file", kind=CapabilityKind.TOOL)

    decision = PolicyGate([]).evaluate(
        CapabilityCall(name=spec.name),
        spec,
        PolicyContext(principal_id="u1", skill_allowed_tools={"other_tool"}),
    )

    assert decision.effect is PolicyEffect.DENY


def test_organization_approval_precedes_capability_metadata() -> None:
    spec = CapabilitySpec(name="read_file", kind=CapabilityKind.TOOL)
    decision = PolicyGate(
        [
            PolicyRule(
                pattern="read_*",
                effect=PolicyEffect.REQUIRE_CONFIRMATION,
                source="organization",
            )
        ]
    ).evaluate(CapabilityCall(name=spec.name), spec, PolicyContext(principal_id="u1"))

    assert decision.effect is PolicyEffect.REQUIRE_CONFIRMATION
    assert decision.matched_rule == "organization:read_*"
