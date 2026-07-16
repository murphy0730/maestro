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

## Review remediation

- `RunStore` now exposes a per-run async serialization lock plus `compare_and_save`; approval claiming occurs under that lock and replacement approvals advance the run revision, so a concurrent caller observes a stale revision.
- Approval checks expiry, preserves the run allowlist during policy re-evaluation, and converts expiry, changed external state, denial, or any confirmation/reconfirmation decision into a fresh approval rather than executing.
- Cancellation is serialized with state changes. An executor completing after cancellation reloads the current snapshot and returns the already-cancelled run instead of writing its stale result; unknown writes remain reconciling.
- Every persisted runtime event now carries a validated `run_snapshot`. Journal replay applies that snapshot as the projection, and recovery rejects terminal runs plus any mismatch of the complete projection and stored snapshot, including same-revision content tampering.
- Added adversarial tests for concurrent approval, expiry, terminal restore rejection, same-revision snapshot tampering, and in-flight cancellation.

Final remediation verification: focused approval/recovery/cancellation tests pass, Runtime tests pass (`151 passed`), and full backend tests pass (`446 passed`, one existing Starlette/httpx deprecation warning).
