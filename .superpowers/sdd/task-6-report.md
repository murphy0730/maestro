# Task 6 — RunIntent and H2 Initial Path Selection

## Requirement mapping

| Requirement | Implementation / test evidence |
| --- | --- |
| Add `runtime/intent.py` with `IntentRequest` and `IntentClassifier.build()` | `maestro/src/maestro/runtime/intent.py` defines both and returns a fully populated `RunIntent`. |
| Fast path for explanation or one read capability | `test_path_matrix` covers `解释 OEE` and `read_file`. |
| Structured path for multi-capability work, background work, and fork skills | `test_path_matrix` covers registered `read_erp` + high-risk `write_mes`, `allow_background=True`, and `fork-skill`. |
| Deterministic signals first | Classifier derives capability, skill count/fork, background, external-wait, and explicit wording signals before consulting the optional model classifier. |
| No downgrade from deterministic high-risk write | `test_model_cannot_downgrade_registered_high_risk_write` supplies model output `low`; the result is structured and contains `deterministic_high_risk_write`. |
| Preserve legacy behavior during Tasks 1–9 migration | No old orchestrator, engine, HTTP API, or SkillEngine files were changed. This module is standalone and is not wired into legacy execution. |

## TDD record

### RED

1. Added the parameterized path matrix and the high-risk non-downgrade test in `maestro/tests/runtime/test_intent.py` before adding production code.
2. Ran `cd maestro && pytest tests/runtime/test_intent.py -v`.
3. Observed the expected collection failure: `ModuleNotFoundError: No module named 'maestro.runtime.intent'`.
4. The supplied parameter name `request` is reserved by pytest 9, so it was renamed to `intent_request`; this was a test-runner compatibility correction, not a behavioral change.

### GREEN

1. Added the minimal standalone `IntentRequest` and deterministic-first `IntentClassifier` implementation.
2. Re-ran `cd maestro && pytest tests/runtime/test_intent.py -v`: `6 passed in 0.03s`.

## Verification

| Command | Result |
| --- | --- |
| `cd maestro && pytest tests/runtime/test_intent.py -v` | 6 passed in 0.03s |
| `cd maestro && pytest` | 394 passed in 6.99s |
| `git diff --check` | Exit 0 |

## Commit

`feat: select adaptive runtime path` (this report is included in the same commit).

## Concerns / deferred work

- Task 6 only selects an initial path. It does not introduce a RunCoordinator, execute tools/MCP, mutate run state, or wire an API; those belong to later migration tasks. Therefore PolicyGate side-effect sequencing is intentionally untouched here.
- The optional model classifier accepts simple labels (`complex`, `high`, or `structured`) as additional structure signals. Deterministic signals are never removed, so a fast path cannot be selected after a structured decision.
- Unknown requested capabilities are conservatively structured via `unknown_capability`; no external side effect is possible in this module.

## Review remediation

### Added coverage and RED result

Added nine focused cases before changing the implementation:

- model classifier exception, mixed non-string list output, and unknown label;
- external wait, unknown capability, multiple requested Skills, and explicit high-risk/complex wording;
- metadata-driven fork behavior, including the `forklift-inspection` false-positive guard.

`cd maestro && pytest tests/runtime/test_intent.py -v` initially failed 5 cases: model exceptions escaped, non-string output raised `AttributeError`, unknown labels selected FAST, `复杂` was not detected, and a skill name containing `fork` falsely selected STRUCTURED.

### GREEN implementation

- Model invocation failures now emit `model_unavailable`; malformed or unknown outputs emit `model_unknown_output`. Both are complexity signals and conservatively select STRUCTURED while still returning `RunIntent`.
- Fork selection now requires `SkillMetadata.agent == "fork"`; names alone have no routing effect.
- Added deterministic `explicit_complex_wording` alongside existing high-risk wording detection.

### Review verification

| Command | Result |
| --- | --- |
| `cd maestro && pytest tests/runtime/test_intent.py -v` | 15 passed in 0.03s |
| `cd maestro && pytest` | 403 passed in 3.01s |

## Final review remediation

The Runtime Skill contract defines fork execution through `SkillMetadata.context == "fork"`; `agent` identifies an agent and is not a fork-routing flag.

### RED

Updated the fork test before implementation so a skill with `context="fork"` and `agent="general-purpose"` must select STRUCTURED, while `forklift-inspection` remains FAST. The focused suite failed because the classifier checked `agent == "fork"`.

### GREEN

Changed only `_requests_fork()` to test `skill.context == "fork"`; skill names and agent identifiers no longer affect the decision.

### Final verification

| Command | Result |
| --- | --- |
| `cd maestro && pytest tests/runtime/test_intent.py -v` | 15 passed in 0.03s |
| `cd maestro && pytest` | 403 passed in 2.99s |
