import pytest

import maestro.runtime as runtime
import maestro.runtime.models as runtime_models
from maestro.runtime.model import RuntimeModel
from maestro.runtime.models import ApprovalRecord, RunIntent, RunPath, RunRecord, StepRecord


def test_run_intent_defaults_to_unselected_path() -> None:
    intent = RunIntent(objective="读取库存")
    assert intent.path is RunPath.UNSELECTED
    assert intent.risk_signals == []


@pytest.mark.parametrize("name", ["GoalSpec", "PlanStep", "TypedPlan"])
def test_typed_plan_contract_symbols_are_not_importable(name: str) -> None:
    with pytest.raises(ImportError):
        exec(f"from maestro.runtime.models import {name}")


@pytest.mark.parametrize("name", ["GoalSpec", "PlanStep", "TypedPlan"])
def test_typed_plan_contract_symbols_are_not_publicly_exported(name: str) -> None:
    assert not hasattr(runtime_models, name)
    assert not hasattr(runtime, name)


def test_runtime_model_protocol_has_no_goal_or_plan_methods() -> None:
    assert not hasattr(RuntimeModel, "structure_goal")
    assert not hasattr(RuntimeModel, "create_plan")


def test_run_record_serialization_excludes_typed_plan_fields() -> None:
    record = RunRecord(objective="读取库存")

    assert "goal_spec" not in RunRecord.model_fields
    assert "typed_plan" not in RunRecord.model_fields
    assert "goal_spec" not in record.model_dump()
    assert "typed_plan" not in record.model_dump()


def test_identifier_fields_are_frozen() -> None:
    identifiers = {
        ApprovalRecord: ("approval_id", "run_id", "step_id"),
        StepRecord: ("run_id", "step_id"),
        RunRecord: ("run_id",),
    }

    for model, field_names in identifiers.items():
        for field_name in field_names:
            assert model.model_fields[field_name].frozen is True
