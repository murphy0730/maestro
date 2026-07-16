# Task 9 Report — Runtime side-effect governance and recovery

## Scope delivered

| Requirement | Result |
| --- | --- |
| Approval CAS and revalidation | `RunCoordinator.approve()` rejects stale revisions, evaluates policy again, compares the external-state token immediately before execution, and replaces changed approvals without executing the write. |
| Unknown writes | Idempotency keys are journaled before writes. `UnknownWriteOutcome` enters `reconciling`; `reconcile()` invokes only the registered reconciler and never reruns the executor. |
| Retry and compensation | A single automatic retry is limited to idempotent writes whose returned `TRANSIENT_INFRASTRUCTURE` error is explicitly in `retryable_errors` and whose controlled budget remains. No implicit compensation path exists; compensation remains an explicit model-selected capability and passes PolicyGate. |
| Cancellation | Safe active runs transition through `cancelling` to `cancelled`. Unknown writes stay `reconciling` and retain `requires_reconciliation=True`; cancellation is deferred. |
| Recovery | `RunRecovery.restore()` validates replayable Journal history, requires its final saved `snapshot_revision` to equal the snapshot revision, and requires the exact pinned capability snapshot. Any mismatch raises `UnsafeRecovery`. |

## TDD evidence

Initial focused execution failed at collection because `maestro.runtime.recovery` did not exist, and the new revalidation/reconciliation interfaces were absent. Follow-up RED for configured transient retries failed with the run in `failed`, demonstrating retry behavior was not present. The minimal retry implementation then made the focused regression pass.

## Verification

- `cd maestro && ./.venv/bin/pytest tests/runtime/test_approval.py tests/runtime/test_reconciliation.py tests/runtime/test_recovery.py tests/runtime/test_cancellation.py -v`
- `cd maestro && ./.venv/bin/pytest tests/runtime -v`
- `cd maestro && ./.venv/bin/pytest -q`
- `git diff --check`

The final complete backend run passed with `441 passed` and one pre-existing Starlette/httpx deprecation warning.

## Scope guard

No `GoalSpec`, `TypedPlan`, `PlanStep`, DAG/planning logic, or manufacturing-domain behavior was added. Run status transitions remain in `RunCoordinator` through `transition_run`.
