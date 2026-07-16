# Task 7 report — Model Adapter and Bounded Fast Loop

## Requirement mapping

| Requirement | Implementation / evidence |
| --- | --- |
| Stable model protocol | `runtime/model.py`: `ModelAction`, `RuntimeModel`, and `LLMRuntimeModel`; the adapter delegates only to `chat_turn` / `classify`. |
| Durable public events | `runtime/events.py`: `EventPublisher` appends a matching `JournalEvent` before subscriber notification. |
| Fast path lifecycle | `runtime/coordinator.py`: creates and persists a run, snapshots capabilities, selects the intent path, uses state-machine transitions, and ends only on final or explicit failure. |
| Bounded, safe calls | The coordinator enforces wall-clock and step budgets, canonical call-cycle detection, basic object-schema required fields, PolicyGate evaluation, and read-only TOOL/MCP execution only. |
| Skill boundary | Inline skills load their complete prompt once into untrusted context, narrow the next turn's tool descriptors by intersection, and execute nothing themselves. Fork/non-inline skills return an upgrade signal for Task 8. |
| Artifact boundary | Large JSON results go through `ArtifactStore` and are represented as artifact context references. |
| Pinned callable boundary | `CapabilitySnapshot` continues to deep-copy mutable descriptor data while preserving an executor callable's identity, so a snapshotted capability can invoke its registered adapter. |

No legacy orchestrator, engines, API endpoints, or legacy SkillEngine were edited.

## RED / GREEN

RED: `cd maestro && pytest tests/runtime/test_fast_loop.py -v` initially failed at collection with `ModuleNotFoundError: maestro.runtime.coordinator`, because Task 7 modules did not exist.

GREEN: the same focused suite passed 4 tests after the minimal implementation. It exercises a final-only fast run, max-step exhaustion, normalized repeated-call detection before the third execution, and inline-skill context/tool narrowing without a side effect.

## Verification

- `cd maestro && pytest tests/runtime/test_fast_loop.py -v` — 4 passed.
- `cd maestro && pytest tests/runtime/test_capabilities.py -v` — 11 passed.
- `cd maestro && pytest -v` — 407 passed.
- `git diff --check` — clean.

## Commit

Pending at report creation; the completion commit is recorded after final verification.

## Concerns / follow-up

- Structured execution, plan validation, approvals, recovery, and fork-skill upgrades intentionally remain Tasks 8–9 work.
- The LLM adapter intentionally accepts only the first returned tool call; each model turn is one bounded coordinator action.
- The coordinator's schema guard currently validates the JSON-object shape and required keys. Rich JSON Schema constraints belong in a dedicated validator if a later task needs them.
