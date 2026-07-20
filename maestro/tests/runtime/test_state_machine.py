import pytest

from maestro.runtime.models import RunPath, RunRecord, RunStatus, StepRecord, StepStatus
from maestro.runtime.state_machine import (
    RUN_TRANSITIONS,
    STEP_TRANSITIONS,
    InvalidTransition,
    transition_run,
    transition_step,
)


def test_structured_run_cannot_downgrade() -> None:
    run = RunRecord(objective="x", status=RunStatus.RUNNING_STRUCTURED)
    with pytest.raises(InvalidTransition, match="downgrade"):
        transition_run(run, RunStatus.RUNNING_FAST, "downgrade")


def test_structured_run_cannot_downgrade_after_waiting() -> None:
    run = RunRecord(
        objective="x",
        path=RunPath.STRUCTURED,
        status=RunStatus.WAITING_APPROVAL,
    )
    with pytest.raises(InvalidTransition, match="downgrade"):
        transition_run(run, RunStatus.RUNNING_FAST, "downgrade")


def test_transition_api_preserves_structured_upgrade() -> None:
    run = RunRecord(objective="x")
    run = transition_run(run, RunStatus.STRUCTURING, "select structured path")
    assert run.path is RunPath.STRUCTURED
    run = transition_run(run, RunStatus.RUNNING_STRUCTURED, "plan ready")
    run = transition_run(run, RunStatus.WAITING_APPROVAL, "approval required")

    with pytest.raises(InvalidTransition, match="downgrade"):
        transition_run(run, RunStatus.RUNNING_FAST, "downgrade")


def test_unselected_waiting_run_cannot_enter_fast_path() -> None:
    run = RunRecord(objective="x", status=RunStatus.WAITING_APPROVAL)

    with pytest.raises(InvalidTransition, match="path not selected"):
        transition_run(run, RunStatus.RUNNING_FAST, "path not selected")


def test_transition_api_selects_fast_path() -> None:
    run = transition_run(
        RunRecord(objective="x"), RunStatus.RUNNING_FAST, "select fast path"
    )

    assert run.path is RunPath.FAST


def test_completed_step_cannot_restart() -> None:
    step = StepRecord(
        run_id="run-1", step_id="read", kind="tool", status=StepStatus.SUCCEEDED
    )
    with pytest.raises(InvalidTransition, match="restart"):
        transition_step(step, StepStatus.RUNNING, "restart")


def test_transition_tables_cover_every_status() -> None:
    assert set(RUN_TRANSITIONS) == set(RunStatus)
    assert set(STEP_TRANSITIONS) == set(StepStatus)


@pytest.mark.parametrize(
    "terminal", [RunStatus.CANCELLED, RunStatus.FAILED, RunStatus.COMPLETED]
)
def test_terminal_runs_have_no_outgoing_transition(terminal: RunStatus) -> None:
    assert RUN_TRANSITIONS[terminal] == frozenset()


@pytest.mark.parametrize(
    "terminal",
    [
        StepStatus.SUCCEEDED,
        StepStatus.FAILED,
        StepStatus.CANCELLED,
        StepStatus.SKIPPED,
    ],
)
def test_terminal_steps_have_no_outgoing_transition(terminal: StepStatus) -> None:
    assert STEP_TRANSITIONS[terminal] == frozenset()


def test_run_transition_invariants() -> None:
    assert RunStatus.RUNNING_FAST not in RUN_TRANSITIONS[RunStatus.RUNNING_STRUCTURED]
    assert RunStatus.CANCELLED in RUN_TRANSITIONS[RunStatus.CANCELLING]


def test_running_step_can_enter_reconciliation() -> None:
    assert StepStatus.RECONCILING in STEP_TRANSITIONS[StepStatus.RUNNING]


def test_transition_run_returns_updated_copy() -> None:
    run = RunRecord(objective="x")

    transitioned = transition_run(run, RunStatus.RUNNING_FAST, "fast path selected")

    assert transitioned is not run
    assert run.status is RunStatus.CREATED
    assert transitioned.status is RunStatus.RUNNING_FAST
    assert transitioned.revision == run.revision + 1
    assert transitioned.updated_at >= run.updated_at


def test_transition_step_returns_updated_copy() -> None:
    step = StepRecord(run_id="run-1", step_id="read", kind="tool")

    transitioned = transition_step(step, StepStatus.READY, "dependencies satisfied")

    assert transitioned is not step
    assert step.status is StepStatus.PENDING
    assert transitioned.status is StepStatus.READY
    assert transitioned.revision == step.revision + 1
