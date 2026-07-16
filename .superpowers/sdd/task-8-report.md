# Task 8 report — controlled upgrades and Child Runs

## Requirement mapping

- Complex intents now enter the existing controlled, single-action loop; no goal or plan model is added.
- A fast run upgrades once before a write, keeps its run ID, counters, approvals and pinned capability versions, freezes its working set as an Artifact, and journals one `run.path_upgraded` event before the next controlled model turn.
- Fork Skills create an isolated child `RunRecord` with `parent_run_id`, a reduced step budget, the parent's capability-version snapshot, and the intersection of parent and Skill tool permissions.
- The parent receives only `ChildRunResult` metadata and an Artifact reference; it never receives the child prompt or full child transcript. Tool execution remains behind `PolicyGate`.
- Journal replay accepts the new controlled-execution and child/artifact event vocabulary while retaining the legacy upgrade event format.

## RED / GREEN

- RED: `pytest tests/runtime/test_path_upgrade.py -v` initially failed all three tests because complex runs stopped at `structuring`, fast runs did not continue after upgrade, and no child run existed.
- GREEN: the same command passed after the bounded controlled loop, one-way upgrade, Artifact freeze, and Child Run implementation.

## Verification

- `pytest tests/runtime/test_path_upgrade.py -v` — 3 passed.
- `pytest tests/runtime -q` — 134 passed.
- `pytest -q` — 428 passed.
- `uv run ruff check …` and `uv run ruff format --check …` — passed.

## Commit

- Current `HEAD`: `feat: upgrade controlled runtime execution`.

## Concerns

- `RunPath.STRUCTURED` and `RUNNING_STRUCTURED` are retained legacy names for compatibility, but this implementation treats them solely as controlled execution; it creates no plan, DAG, topology, or dependency model.
- A parent with a one-step budget now rejects fork creation before any Child Run is created, because no smaller valid child budget exists.
- Resuming a controlled Run requires an exact local capability snapshot matching its pinned versions; if a host has evicted that version, the Run safely fails rather than using a newer capability.

## Review follow-up

- `run.failed` replay now validates a non-empty reason, rebuilds the failed terminal state, and rejects later lifecycle/activity events.
- Forking with a one-step parent is rejected before a Child Run is created.
- Every controlled call, including Skill calls, consumes and persists one strict step; distinct Skills cannot bypass the controlled budget.
- The post-upgrade `RUNNING_STRUCTURED` snapshot is saved before the next controlled model turn.
- Controlled recovery now validates the exact pinned capability versions before any model turn; replaced registry capabilities are never executed during resume.
- Follow-up verification: `pytest tests/runtime -q` — 139 passed; `pytest -q` — 433 passed.
