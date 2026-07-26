# AGENTS.md

Guidance for coding agents (Codex, Claude Code, and others) working in this repository.

**The full guide lives in [`CLAUDE.md`](CLAUDE.md) — read it first.** It is the single source of truth for repository layout, commands, backend/frontend architecture and repo conventions. This file used to duplicate that content and drifted out of date; it now defers deliberately so the two cannot disagree.

Two points worth repeating here, because getting them wrong breaks the architecture rather than just a build:

1. **The Runtime is domain-neutral.** `maestro/src/maestro/runtime/` must not gain scheduling, kitting, expediting, dispatch or RAG logic. Business capability is installed at runtime as a governed Skill, Tool or MCP capability, registered into the platform from `bootstrap.py` after construction. `maestro/tests/runtime/test_b1_invariants.py` enforces this.
2. **Every side effect goes through the Policy Gate**, and host-administration APIs (skill import / trust / delete) require the privileged bearer token — they are never model-callable.

Rules & Constraints
- Do not use the Superpowers skill by default. Only use it when I explicitly request it.
- Prefer minimal changes; avoid unnecessary refactors.
