from datetime import UTC, datetime

from maestro.runtime.models import RunPath, RunRecord, RunStatus, StepRecord, StepStatus


class InvalidTransition(ValueError):
    pass


RUN_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.CREATED: frozenset(
        {
            RunStatus.RUNNING_FAST,
            RunStatus.STRUCTURING,
            RunStatus.CANCELLING,
            RunStatus.FAILED,
        }
    ),
    RunStatus.RUNNING_FAST: frozenset(
        {
            RunStatus.STRUCTURING,
            RunStatus.WAITING_APPROVAL,
            RunStatus.WAITING_EXTERNAL,
            RunStatus.RECONCILING,
            RunStatus.CANCELLING,
            RunStatus.FAILED,
            RunStatus.COMPLETED,
        }
    ),
    RunStatus.STRUCTURING: frozenset(
        {
            RunStatus.RUNNING_STRUCTURED,
            RunStatus.WAITING_EXTERNAL,
            RunStatus.CANCELLING,
            RunStatus.FAILED,
        }
    ),
    RunStatus.RUNNING_STRUCTURED: frozenset(
        {
            RunStatus.WAITING_APPROVAL,
            RunStatus.WAITING_EXTERNAL,
            RunStatus.RECONCILING,
            RunStatus.CANCELLING,
            RunStatus.FAILED,
            RunStatus.COMPLETED,
        }
    ),
    RunStatus.WAITING_APPROVAL: frozenset(
        {
            RunStatus.RUNNING_FAST,
            RunStatus.RUNNING_STRUCTURED,
            RunStatus.CANCELLING,
            RunStatus.FAILED,
        }
    ),
    RunStatus.WAITING_EXTERNAL: frozenset(
        {
            RunStatus.RUNNING_FAST,
            RunStatus.RUNNING_STRUCTURED,
            RunStatus.RECONCILING,
            RunStatus.CANCELLING,
            RunStatus.FAILED,
        }
    ),
    RunStatus.RECONCILING: frozenset(
        {
            RunStatus.RUNNING_FAST,
            RunStatus.RUNNING_STRUCTURED,
            RunStatus.CANCELLING,
            RunStatus.FAILED,
            RunStatus.COMPLETED,
        }
    ),
    RunStatus.CANCELLING: frozenset({RunStatus.CANCELLED, RunStatus.RECONCILING, RunStatus.FAILED}),
    RunStatus.CANCELLED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.COMPLETED: frozenset(),
}


STEP_TRANSITIONS: dict[StepStatus, frozenset[StepStatus]] = {
    StepStatus.PENDING: frozenset(
        {StepStatus.READY, StepStatus.CANCELLED, StepStatus.SKIPPED}
    ),
    StepStatus.READY: frozenset(
        {
            StepStatus.WAITING_APPROVAL,
            StepStatus.RUNNING,
            StepStatus.CANCELLED,
            StepStatus.SKIPPED,
        }
    ),
    StepStatus.WAITING_APPROVAL: frozenset(
        {
            StepStatus.RUNNING,
            StepStatus.FAILED,
            StepStatus.CANCELLED,
            StepStatus.SKIPPED,
        }
    ),
    StepStatus.RUNNING: frozenset(
        {
            StepStatus.WAITING_EXTERNAL,
            StepStatus.RECONCILING,
            StepStatus.SUCCEEDED,
            StepStatus.FAILED,
            StepStatus.CANCELLED,
        }
    ),
    StepStatus.WAITING_EXTERNAL: frozenset(
        {
            StepStatus.RUNNING,
            StepStatus.RECONCILING,
            StepStatus.SUCCEEDED,
            StepStatus.FAILED,
            StepStatus.CANCELLED,
        }
    ),
    StepStatus.RECONCILING: frozenset(
        {
            StepStatus.RUNNING,
            StepStatus.SUCCEEDED,
            StepStatus.FAILED,
            StepStatus.CANCELLED,
        }
    ),
    StepStatus.SUCCEEDED: frozenset(),
    StepStatus.FAILED: frozenset(),
    StepStatus.CANCELLED: frozenset(),
    StepStatus.SKIPPED: frozenset(),
}


def transition_run(run: RunRecord, target: RunStatus, reason: str) -> RunRecord:
    can_enter_fast = run.path is RunPath.FAST or (
        run.status is RunStatus.CREATED and run.path is RunPath.UNSELECTED
    )
    has_invalid_fast_path = target is RunStatus.RUNNING_FAST and not can_enter_fast
    if target not in RUN_TRANSITIONS[run.status] or has_invalid_fast_path:
        raise InvalidTransition(
            f"invalid run transition {run.status.value} -> {target.value}: {reason}"
        )
    path = run.path
    if target in {RunStatus.STRUCTURING, RunStatus.RUNNING_STRUCTURED}:
        path = RunPath.STRUCTURED
    elif target is RunStatus.RUNNING_FAST and path is RunPath.UNSELECTED:
        path = RunPath.FAST
    return run.model_copy(
        update={
            "path": path,
            "status": target,
            "revision": run.revision + 1,
            "updated_at": datetime.now(UTC),
        }
    )


def transition_step(step: StepRecord, target: StepStatus, reason: str) -> StepRecord:
    if target not in STEP_TRANSITIONS[step.status]:
        raise InvalidTransition(
            f"invalid step transition {step.status.value} -> {target.value}: {reason}"
        )
    return step.model_copy(
        update={"status": target, "revision": step.revision + 1}
    )
