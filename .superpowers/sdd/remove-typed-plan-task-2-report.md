# Remove Typed Plan Task 2 Report

## Requirements mapping

- The coordinator upgrades a fast run only through `RUNNING_FAST -> STRUCTURING -> RUNNING_STRUCTURED` when a non-inline Skill requires controlled execution.
- The upgrade uses the existing `RunRecord` and `transition_run`; it does not create `GoalSpec`, `TypedPlan`, or `PlanStep` objects.
- Both transition snapshots retain the run ID, consumed-step budget, approval history, and capability-version snapshot.
- `run.upgrading` and `run.upgraded` journal events record the upgrade reason and the same frozen list of immutable Artifact references.
- The fast loop keeps its read-only capability and `PolicyGate` checks unchanged; the upgrade itself invokes no executor and adds no business capability.
- A regression test loads a legacy snapshot containing `goal_spec` and `typed_plan`; Pydantic safely ignores the obsolete fields and serialization does not re-expose them.

## RED / GREEN

RED:

```text
./.venv/bin/pytest tests/runtime/test_fast_loop.py::test_fast_run_upgrades_to_controlled_execution_without_typed_plan tests/runtime/test_store.py::test_run_store_ignores_legacy_typed_plan_snapshot_fields -v
```

The new upgrade test failed as expected because the fast loop returned `FAILED` with `skill_upgrade_required` rather than `RUNNING_STRUCTURED`. The legacy-snapshot regression already passed because model validation ignores unknown fields.

GREEN:

```text
./.venv/bin/pytest tests/runtime/test_fast_loop.py::test_fast_run_upgrades_to_controlled_execution_without_typed_plan tests/runtime/test_store.py::test_run_store_ignores_legacy_typed_plan_snapshot_fields -v
```

Result: `2 passed`.

## Verification commands

```text
./.venv/bin/pytest tests/runtime -v
```

Result: `120 passed`.

```text
./.venv/bin/pytest
```

Result: `414 passed, 1 warning`. The warning is the existing Starlette `TestClient` deprecation warning for `httpx`.

`git diff --check` completed with no whitespace errors.

## Commit

`feat: upgrade runs without typed plans`

## Concerns

- This task establishes and journals the one-way handoff into controlled execution. It deliberately does not add a controlled-execution loop, write path, or manufacturing capability; those remain outside the stated scope.
- Legacy snapshot compatibility relies on the intentional Pydantic default of ignoring unknown input fields. The regression test ensures obsolete plan fields cannot reappear in the loaded record or a subsequent serialized snapshot.

## Review follow-up: upgrade replay

The first implementation journaled `run.upgrading` and `run.upgraded`, but the replay reducer rejected both as unknown. The reducer now validates the required non-empty upgrade reason and ArtifactRef working-set payload, applies `STRUCTURING` at `run.upgrading`, and permits `RUNNING_STRUCTURED` only for a following `run.upgraded` whose reason and frozen working set are identical. It rejects an upgrade without its predecessor, altered payload, and a post-completion upgrade; existing unknown-event rejection remains covered.

The fast-loop upgrade test now provides an executor on the non-inline Skill and asserts it is never called. The preceding read-only lookup remains the only executor invocation before the handoff.

Follow-up RED:

```text
./.venv/bin/pytest tests/runtime/test_journal.py tests/runtime/test_fast_loop.py tests/runtime/test_store.py -v
```

Result: the new replay cases failed because `replay_run()` reported `unknown journal event: run.upgrading` / `run.upgraded`. The final terminal-state ordering case then failed until the reducer rejected `COMPLETED -> run.upgrading`.

Follow-up GREEN and verification:

```text
./.venv/bin/pytest tests/runtime/test_journal.py tests/runtime/test_fast_loop.py tests/runtime/test_store.py -v
```

Result: `27 passed`.

```text
./.venv/bin/pytest
```

Result: `419 passed, 1 warning` (the same existing Starlette `TestClient` deprecation warning).
