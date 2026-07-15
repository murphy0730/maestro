from __future__ import annotations

from enum import StrEnum
from fnmatch import fnmatchcase

from pydantic import BaseModel, Field

from maestro.runtime.capabilities import CapabilityCall, CapabilitySpec, RiskLevel


class PolicyEffect(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_CONFIRMATION = "require_confirmation"
    REQUIRE_RECONFIRMATION = "require_reconfirmation"


class PolicyRule(BaseModel):
    pattern: str
    effect: PolicyEffect
    source: str = "organization"
    argument_constraints: dict[str, object] = Field(default_factory=dict)
    resource_pattern: str | None = None
    revalidate_before_execute: bool = False


class PolicyContext(BaseModel):
    principal_id: str
    skill_allowed_tools: set[str] | None = None
    run_allowed_tools: set[str] | None = None
    argument_rules: list[PolicyRule] = Field(default_factory=list)


class PolicyDecision(BaseModel):
    effect: PolicyEffect
    reason: str
    matched_rule: str | None = None
    revalidate_before_execute: bool = False


class PolicyGate:
    """Evaluate deterministic safety restrictions in their fixed precedence order."""

    def __init__(self, rules: list[PolicyRule]) -> None:
        self._rules = tuple(rules)

    def evaluate(
        self,
        call: CapabilityCall,
        spec: CapabilitySpec,
        context: PolicyContext,
    ) -> PolicyDecision:
        if call.name != spec.name:
            return PolicyDecision(
                effect=PolicyEffect.DENY,
                reason="call name does not match capability descriptor",
            )

        organization_rules = [
            rule for rule in self._rules if rule.source == "organization"
        ]
        decision = self._rule_decision(organization_rules, call, "organization")
        if decision is not None and decision.effect is PolicyEffect.DENY:
            return decision

        if context.run_allowed_tools is not None and spec.name not in context.run_allowed_tools:
            return PolicyDecision(
                effect=PolicyEffect.DENY,
                reason="capability is not authorized for this run",
            )

        if (
            context.skill_allowed_tools is not None
            and spec.name not in context.skill_allowed_tools
        ):
            return PolicyDecision(
                effect=PolicyEffect.DENY,
                reason="capability is not allowed by the skill",
            )

        argument_rules = [
            rule for rule in self._rules if rule.source != "organization"
        ] + context.argument_rules
        explicit_decision = self._rule_decision(
            organization_rules + argument_rules, call, "policy"
        )
        if (
            explicit_decision is not None
            and explicit_decision.effect is not PolicyEffect.ALLOW
        ):
            return explicit_decision

        if spec.writes and spec.risk is RiskLevel.HIGH:
            return PolicyDecision(
                effect=PolicyEffect.REQUIRE_CONFIRMATION,
                reason="high-risk write requires confirmation",
                revalidate_before_execute=True,
            )

        if explicit_decision is not None:
            return explicit_decision

        return PolicyDecision(effect=PolicyEffect.ALLOW, reason="allowed")

    @staticmethod
    def _rule_decision(
        rules: list[PolicyRule], call: CapabilityCall, stage: str
    ) -> PolicyDecision | None:
        matches = [rule for rule in rules if PolicyGate._matches(rule, call)]
        if not matches:
            return None
        priorities = {
            PolicyEffect.DENY: 3,
            PolicyEffect.REQUIRE_RECONFIRMATION: 2,
            PolicyEffect.REQUIRE_CONFIRMATION: 1,
            PolicyEffect.ALLOW: 0,
        }
        rule = max(matches, key=lambda item: priorities[item.effect])
        if rule is None:
            return None
        same_effect_rules = [item for item in matches if item.effect is rule.effect]
        return PolicyDecision(
            effect=rule.effect,
            reason=f"{stage} policy requires {rule.effect.value}",
            matched_rule=f"{rule.source}:{rule.pattern}",
            revalidate_before_execute=(
                any(item.revalidate_before_execute for item in same_effect_rules)
                or rule.effect is PolicyEffect.REQUIRE_RECONFIRMATION
            ),
        )

    @staticmethod
    def _matches(rule: PolicyRule, call: CapabilityCall) -> bool:
        if not fnmatchcase(call.name, rule.pattern):
            return False
        if any(call.arguments.get(key) != value for key, value in rule.argument_constraints.items()):
            return False
        if rule.resource_pattern is None:
            return True
        resource = call.arguments.get("resource")
        return isinstance(resource, str) and fnmatchcase(resource, rule.resource_pattern)
