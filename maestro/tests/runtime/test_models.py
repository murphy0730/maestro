from pydantic import ValidationError
import pytest

from maestro.runtime.models import (
    ApprovalRecord,
    GoalSpec,
    PlanStep,
    RunIntent,
    RunPath,
    RunRecord,
    StepRecord,
    TypedPlan,
)


def test_run_intent_defaults_to_unselected_path() -> None:
    intent = RunIntent(objective="读取库存")
    assert intent.path is RunPath.UNSELECTED
    assert intent.risk_signals == []


def test_typed_plan_rejects_missing_dependency() -> None:
    with pytest.raises(ValidationError, match="missing dependency"):
        TypedPlan(
            goal=GoalSpec(objective="汇总结果", success_criteria=["生成摘要"]),
            steps=[PlanStep(step_id="summarize", kind="model", depends_on=["read"])],
        )


@pytest.mark.parametrize(
    ("steps", "message"),
    [
        (
            [
                PlanStep(step_id="read", kind="tool"),
                PlanStep(step_id="read", kind="model"),
            ],
            "duplicate step id",
        ),
        (
            [PlanStep(step_id="read", kind="tool", depends_on=["read"])],
            "step cannot depend on itself",
        ),
    ],
)
def test_typed_plan_rejects_invalid_graph(
    steps: list[PlanStep], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        TypedPlan(
            goal=GoalSpec(objective="x", success_criteria=["done"]), steps=steps
        )


def test_identifier_fields_are_frozen() -> None:
    identifiers = {
        PlanStep: ("step_id",),
        ApprovalRecord: ("approval_id", "run_id", "step_id"),
        StepRecord: ("run_id", "step_id"),
        RunRecord: ("run_id",),
    }

    for model, field_names in identifiers.items():
        for field_name in field_names:
            assert model.model_fields[field_name].frozen is True
