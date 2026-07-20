from maestro.runtime.capabilities import (
    CapabilityCall,
    CapabilityKind,
    CapabilityRegistry,
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


def test_run_and_skill_allowlists_deny_before_high_risk_confirmation() -> None:
    spec = CapabilitySpec(
        name="dangerous_write",
        kind=CapabilityKind.TOOL,
        risk=RiskLevel.HIGH,
        writes=True,
    )

    decision = PolicyGate(
        [
            PolicyRule(
                pattern="dangerous_*",
                effect=PolicyEffect.REQUIRE_CONFIRMATION,
                source="organization",
            )
        ]
    ).evaluate(
        CapabilityCall(name=spec.name),
        spec,
        PolicyContext(
            principal_id="u1",
            run_allowed_tools={"other_tool"},
            skill_allowed_tools={"other_tool"},
        ),
    )

    assert decision.effect is PolicyEffect.DENY


def test_organization_confirmation_dominates_allow_regardless_of_rule_order() -> None:
    spec = CapabilitySpec(name="write", kind=CapabilityKind.TOOL)
    rules = [
        PolicyRule(pattern="*", effect=PolicyEffect.ALLOW, source="organization"),
        PolicyRule(
            pattern="write",
            effect=PolicyEffect.REQUIRE_CONFIRMATION,
            source="organization",
        ),
    ]

    decision = PolicyGate(rules).evaluate(
        CapabilityCall(name=spec.name), spec, PolicyContext(principal_id="u1")
    )

    assert decision.effect is PolicyEffect.REQUIRE_CONFIRMATION


def test_argument_deny_precedes_high_risk_write_confirmation() -> None:
    spec = CapabilitySpec(
        name="write_record",
        kind=CapabilityKind.MCP,
        risk=RiskLevel.HIGH,
        writes=True,
    )
    decision = PolicyGate(
        [
            PolicyRule(
                pattern="write_*",
                effect=PolicyEffect.DENY,
                source="argument",
                argument_constraints={"environment": "production"},
            )
        ]
    ).evaluate(
        CapabilityCall(name=spec.name, arguments={"environment": "production"}),
        spec,
        PolicyContext(principal_id="u1"),
    )

    assert decision.effect is PolicyEffect.DENY


def test_registered_string_high_risk_write_requires_confirmation() -> None:
    registry = CapabilityRegistry()
    registry.register(
        CapabilitySpec(  # type: ignore[arg-type]
            name="write_record",
            kind=CapabilityKind.MCP,
            risk="high",
            writes=True,
        )
    )

    decision = PolicyGate([]).evaluate(
        CapabilityCall(name="write_record"),
        registry.snapshot().require("write_record"),
        PolicyContext(principal_id="u1"),
    )

    assert decision.effect is PolicyEffect.REQUIRE_CONFIRMATION


def test_direct_string_high_risk_write_requires_confirmation() -> None:
    spec = CapabilitySpec(  # type: ignore[arg-type]
        name="write_record",
        kind=CapabilityKind.MCP,
        risk="high",
        writes=True,
    )

    decision = PolicyGate([]).evaluate(
        CapabilityCall(name=spec.name), spec, PolicyContext(principal_id="u1")
    )

    assert spec.risk is RiskLevel.HIGH
    assert decision.effect is PolicyEffect.REQUIRE_CONFIRMATION


def test_organization_reconfirmation_dominates_confirmation_in_reverse_order() -> None:
    spec = CapabilitySpec(name="write", kind=CapabilityKind.TOOL)
    decision = PolicyGate(
        [
            PolicyRule(
                pattern="write",
                effect=PolicyEffect.REQUIRE_CONFIRMATION,
                source="organization",
            ),
            PolicyRule(
                pattern="write",
                effect=PolicyEffect.REQUIRE_RECONFIRMATION,
                source="organization",
            ),
        ]
    ).evaluate(CapabilityCall(name=spec.name), spec, PolicyContext(principal_id="u1"))

    assert decision.effect is PolicyEffect.REQUIRE_RECONFIRMATION
    assert decision.revalidate_before_execute is True


def test_argument_reconfirmation_dominates_confirmation_in_reverse_order() -> None:
    spec = CapabilitySpec(name="write", kind=CapabilityKind.TOOL)
    decision = PolicyGate(
        [
            PolicyRule(
                pattern="write",
                effect=PolicyEffect.REQUIRE_CONFIRMATION,
                source="argument",
            ),
            PolicyRule(
                pattern="write",
                effect=PolicyEffect.REQUIRE_RECONFIRMATION,
                source="argument",
            ),
        ]
    ).evaluate(CapabilityCall(name=spec.name), spec, PolicyContext(principal_id="u1"))

    assert decision.effect is PolicyEffect.REQUIRE_RECONFIRMATION
    assert decision.revalidate_before_execute is True


def test_argument_reconfirmation_dominates_organization_confirmation_in_any_order() -> None:
    spec = CapabilitySpec(name="write", kind=CapabilityKind.TOOL)
    organization_confirmation = PolicyRule(
        pattern="write",
        effect=PolicyEffect.REQUIRE_CONFIRMATION,
        source="organization",
    )
    argument_reconfirmation = PolicyRule(
        pattern="write",
        effect=PolicyEffect.REQUIRE_RECONFIRMATION,
        source="argument",
    )

    for rules in (
        [organization_confirmation, argument_reconfirmation],
        [argument_reconfirmation, organization_confirmation],
    ):
        decision = PolicyGate(rules).evaluate(
            CapabilityCall(name=spec.name), spec, PolicyContext(principal_id="u1")
        )
        assert decision.effect is PolicyEffect.REQUIRE_RECONFIRMATION
        assert decision.revalidate_before_execute is True


def test_argument_reconfirmation_dominates_organization_allow_in_any_order() -> None:
    spec = CapabilitySpec(name="write", kind=CapabilityKind.TOOL)
    organization_allow = PolicyRule(
        pattern="write", effect=PolicyEffect.ALLOW, source="organization"
    )
    argument_reconfirmation = PolicyRule(
        pattern="write",
        effect=PolicyEffect.REQUIRE_RECONFIRMATION,
        source="argument",
    )

    for rules in (
        [organization_allow, argument_reconfirmation],
        [argument_reconfirmation, organization_allow],
    ):
        decision = PolicyGate(rules).evaluate(
            CapabilityCall(name=spec.name), spec, PolicyContext(principal_id="u1")
        )
        assert decision.effect is PolicyEffect.REQUIRE_RECONFIRMATION
        assert decision.revalidate_before_execute is True


def test_same_priority_confirmation_aggregates_revalidation_in_any_order() -> None:
    spec = CapabilitySpec(name="write", kind=CapabilityKind.TOOL)
    organization_confirmation = PolicyRule(
        pattern="write",
        effect=PolicyEffect.REQUIRE_CONFIRMATION,
        source="organization",
        revalidate_before_execute=False,
    )
    argument_confirmation = PolicyRule(
        pattern="write",
        effect=PolicyEffect.REQUIRE_CONFIRMATION,
        source="argument",
        revalidate_before_execute=True,
    )

    for rules in (
        [organization_confirmation, argument_confirmation],
        [argument_confirmation, organization_confirmation],
    ):
        decision = PolicyGate(rules).evaluate(
            CapabilityCall(name=spec.name), spec, PolicyContext(principal_id="u1")
        )
        assert decision.effect is PolicyEffect.REQUIRE_CONFIRMATION
        assert decision.revalidate_before_execute is True
