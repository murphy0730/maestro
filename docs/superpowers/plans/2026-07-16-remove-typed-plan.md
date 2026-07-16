# Remove Typed Plan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove GoalSpec/TypedPlan from the new Runtime and retain adaptive, policy-governed fast and controlled execution modes.

**Architecture:** Keep `RunIntent` as the initial routing contract. Complex signals select a controlled loop rather than a pre-built plan; a fast Run can upgrade once, preserving its audit state and snapshot.

**Tech Stack:** Python 3.12, Pydantic 2, pytest/pytest-asyncio.

## Global Constraints

- Runtime Core contains no manufacturing business capability.
- Every request creates RunIntent; no Runtime model, journal or API contains GoalSpec, TypedPlan or PlanStep.
- A fast Run can upgrade only to controlled execution; no downgrade exists.
- Only RunCoordinator changes Run or Step state.
- Every Tool/MCP side effect passes through PolicyGate.
- Preserve the Tasks 1–9 migration coexistence until the final cutover.

### Task 1: Remove typed-plan contracts

**Files:**
- Modify: `maestro/src/maestro/runtime/models.py`, `maestro/src/maestro/runtime/model.py`, `maestro/src/maestro/runtime/__init__.py`
- Modify: `maestro/tests/runtime/test_models.py`, `maestro/tests/runtime/fakes.py`

- [ ] Write failing import/serialization tests asserting the removed names and RunRecord fields are absent, then run `cd maestro && pytest tests/runtime/test_models.py -v`.
- [ ] Remove the three models, the two RunRecord fields, model protocol methods and fakes; retain `RunIntent` and action-turn protocol.
- [ ] Run `cd maestro && pytest tests/runtime/test_models.py tests/runtime -v` and commit `refactor: remove typed plan runtime contracts`.

### Task 2: Replace structured upgrade semantics

**Files:**
- Modify: `maestro/src/maestro/runtime/state_machine.py`, `maestro/src/maestro/runtime/coordinator.py`, `maestro/tests/runtime/test_fast_loop.py`

- [ ] Write failing tests for one-way `RUNNING_FAST -> STRUCTURING -> RUNNING_STRUCTURED` transition that assert no goal/plan allocation and preservation of run id, budget, approvals and snapshot.
- [ ] Implement controlled-execution upgrade as a coordinator-only state transition with a journaled reason and frozen Artifact working set.
- [ ] Run focused Runtime tests and commit `feat: upgrade runs without typed plans`.

### Task 3: Remove obsolete planning work and revise roadmap

**Files:**
- Modify: `docs/superpowers/plans/2026-07-16-agent-runtime-redesign.md`, `docs/superpowers/specs/2026-07-16-agent-runtime-redesign-design.md`
- Modify or delete: any Task 8 planning-specific tests/files introduced during this branch

- [ ] Search `rg -n 'GoalSpec|TypedPlan|PlanStep|structure_goal|create_plan' maestro/src maestro/tests` and remove all Runtime production/test references.
- [ ] Revise the original roadmap so its former structured-planning task becomes controlled execution, approval, reconciliation, cancellation, recovery and Child Run work.
- [ ] Run full backend tests and `git diff --check`; commit `docs: retire typed plan runtime design`.
