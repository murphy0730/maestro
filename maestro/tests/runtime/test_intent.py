from pathlib import Path

import pytest

from maestro.runtime.capabilities import (
    CapabilityKind,
    CapabilityRegistry,
    CapabilitySpec,
    RiskLevel,
)
from maestro.runtime.intent import IntentClassifier, IntentRequest
from maestro.runtime.models import RunPath
from maestro.runtime.skills import SkillMetadata


@pytest.fixture
def capabilities():
    registry = CapabilityRegistry()
    registry.register(CapabilitySpec(name="read_file", kind=CapabilityKind.TOOL))
    registry.register(CapabilitySpec(name="read_erp", kind=CapabilityKind.TOOL))
    registry.register(
        CapabilitySpec(
            name="write_mes",
            kind=CapabilityKind.MCP,
            risk=RiskLevel.HIGH,
            writes=True,
        )
    )
    return registry.snapshot()


@pytest.fixture
def classifier(capabilities):
    fork_skill = _skill("fork-skill", context="fork", agent="general-purpose")
    return IntentClassifier(capabilities, skills={fork_skill.name: fork_skill})


@pytest.mark.parametrize(
    ("intent_request", "expected"),
    [
        (IntentRequest(message="解释 OEE", tool_names=[]), RunPath.FAST),
        (IntentRequest(message="读取文件", tool_names=["read_file"]), RunPath.FAST),
        (
            IntentRequest(message="执行多系统更新", tool_names=["read_erp", "write_mes"]),
            RunPath.STRUCTURED,
        ),
        (IntentRequest(message="后台等待完成", allow_background=True), RunPath.STRUCTURED),
        (
            IntentRequest(message="调用 fork skill", requested_skills=["fork-skill"]),
            RunPath.STRUCTURED,
        ),
    ],
)
def test_path_matrix(classifier, intent_request, expected) -> None:
    assert classifier.build(intent_request).path is expected


def test_model_cannot_downgrade_registered_high_risk_write(capabilities) -> None:
    classifier = IntentClassifier(capabilities, model_classifier=lambda _: "low")

    intent = classifier.build(
        IntentRequest(message="更新 MES", tool_names=["write_mes"])
    )

    assert intent.path is RunPath.STRUCTURED
    assert "deterministic_high_risk_write" in intent.risk_signals


@pytest.mark.parametrize(
    "model_classifier",
    [
        lambda _: (_ for _ in ()).throw(RuntimeError("model unavailable")),
        lambda _: ["low", object()],
        lambda _: "unrecognized-label",
    ],
)
def test_invalid_model_output_is_auditable_and_conservatively_structured(
    capabilities, model_classifier
) -> None:
    intent = IntentClassifier(capabilities, model_classifier=model_classifier).build(
        IntentRequest(message="解释 OEE")
    )

    assert intent.path is RunPath.STRUCTURED
    assert intent.complexity_signals in (["model_unavailable"], ["model_unknown_output"])


def test_external_wait_selects_structured_path(classifier) -> None:
    intent = classifier.build(IntentRequest(message="等待结果", external_wait=True))

    assert intent.path is RunPath.STRUCTURED
    assert "external_wait" in intent.complexity_signals


def test_unknown_capability_selects_structured_path(classifier) -> None:
    intent = classifier.build(IntentRequest(message="运行工具", tool_names=["unknown"]))

    assert intent.path is RunPath.STRUCTURED
    assert "unknown_capability" in intent.risk_signals


def test_multiple_skills_select_structured_path(classifier) -> None:
    intent = classifier.build(
        IntentRequest(message="组合技能", requested_skills=["first", "second"])
    )

    assert intent.path is RunPath.STRUCTURED
    assert "multiple_skills" in intent.complexity_signals


@pytest.mark.parametrize("message", ["执行更新", "处理复杂流程"])
def test_explicit_high_risk_or_complex_wording_selects_structured_path(
    classifier, message
) -> None:
    intent = classifier.build(IntentRequest(message=message))

    assert intent.path is RunPath.STRUCTURED


def test_fork_context_requires_explicit_skill_metadata(capabilities) -> None:
    forklift = _skill("forklift-inspection")
    fork = _skill("delegate", context="fork", agent="general-purpose")
    classifier = IntentClassifier(
        capabilities, skills={forklift.name: forklift, fork.name: fork}
    )

    forklift_intent = classifier.build(
        IntentRequest(message="检查", requested_skills=[forklift.name])
    )
    fork_intent = classifier.build(IntentRequest(message="委派", requested_skills=[fork.name]))

    assert forklift_intent.path is RunPath.FAST
    assert "fork_context" not in forklift_intent.complexity_signals
    assert fork_intent.path is RunPath.STRUCTURED
    assert "fork_context" in fork_intent.complexity_signals


def _skill(
    name: str, *, context: str = "inline", agent: str | None = None
) -> SkillMetadata:
    return SkillMetadata(
        name=name,
        description="",
        allowed_tools=(),
        argument_hint=None,
        user_invocable=True,
        disable_model_invocation=False,
        context=context,
        agent=agent,
        model=None,
        effort=None,
        hooks={},
        extensions={},
        source="project",
        path=Path(f"/{name}/SKILL.md"),
    )
