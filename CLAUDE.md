# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

Two independently-run apps that talk over an HTTP/SSE contract:

- `maestro/` — Python 3.12 FastAPI backend: a generic, policy-governed **Agent Runtime**. Source under `src/maestro/`. Source of truth for behavior; see its `README.md`.
- `frontend/` — React 18 + Vite + TypeScript + Tailwind SPA, with an optional Electron shell (`frontend/electron/`). Contract in `docs/api-contract/agent-runtime-v1.md`; MSW mocks available for offline demo.

The package is `maestro`, **not** `platform` — `platform` is a stdlib name that shadows dependency imports.

**The Runtime is domain-neutral.** It does not build in scheduling, kitting, expediting, dispatch, RAG, or any other manufacturing behavior. Business capability is installed at runtime as a governed Skill, Tool, or MCP capability, and every side effect passes the Policy Gate first. Two tests enforce this (`tests/runtime/test_b1_invariants.py`) — do not add domain logic under `runtime/`.

## Commands

### Backend (`maestro/`)
```bash
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -e ".[dev]"                # or: python3.12 -m venv .venv && pip install -e ".[dev]"
cp .env.example .env                      # fill LLM_API_KEY (DeepSeek default); runs without it (degraded mode)

uvicorn maestro.main:app --reload         # HTTP API on :8000
python -m maestro.cli                     # interactive CLI

pytest                                                    # all LLM calls mocked, no network
pytest tests/runtime/test_state_machine.py -k transition   # single test
```

### Frontend (`frontend/`)
```bash
npm install
npm run dev        # Vite on :5173; hits the real backend by default via /api/v1 proxy → :8000
npm test           # vitest run (jsdom + React Testing Library)
npm run build      # tsc -b && vite build
npm run lint       # eslint, --max-warnings 0
npm run format     # prettier
npm run electron:dev    # desktop shell against the Vite dev server
npm run test:electron   # node --test over electron/*.test.cjs
```
`VITE_API_MOCKING=disabled` is the committed default in `frontend/.env.development`; set it to `enabled` to run offline on MSW mocks. `./restart.sh` at the repo root restarts backend (:8000) + frontend (:5173) in the background and injects a matching `PRIVILEGED_API_TOKEN` on both sides (Windows: `restart.bat`, same `all|backend|frontend|stop` subcommands).

### Packaging the desktop app
`./build-mac.sh` (macOS → `frontend/release/*.dmg`) and `build-win.bat` (Windows → `frontend/release/*.exe`) are one-click build scripts: each freezes the backend via PyInstaller (`maestro/maestro_backend.spec`) then runs `npm run electron:build`. The bundled backend is a native binary and **cannot be cross-compiled** — run each script on its own OS to get a working package.

## Backend architecture

Every request becomes a persisted **Run**. `IntentClassifier` picks the initial path; the Run may escalate from fast to structured, **never the reverse**.

- **`runtime/coordinator.py` — `RunCoordinator`** is the only component that mutates Run state. It owns the bounded fast loop (`run_until_blocked`) and controlled execution (`_run_controlled`), consults the Policy Gate before every capability call, and creates approval records when a call needs a human.
- **`runtime/state_machine.py`** — explicit `RUN_TRANSITIONS` / step transition tables; anything illegal raises `InvalidTransition`. Run statuses: `created → running_fast | structuring → running_structured → waiting_approval | waiting_external | reconciling → completed | failed | cancelled`.
- **`runtime/capabilities.py` — `CapabilityRegistry`** is the single namespace for TOOL / MCP / SKILL capabilities, each with a `RiskLevel`. A Skill can never raise a Tool/MCP's risk level, only narrow it.
- **`runtime/policy.py` — `PolicyGate`** evaluates deterministic rules in fixed precedence and returns allow / require-approval / deny. It is the only authorization path.
- **`runtime/intent.py` — `IntentClassifier`** selects FAST only when neither a deterministic signal nor a model complexity signal demands structure.
- **`runtime/context.py`** — priority + trust-ranked context assembly with a char budget and a truncating summarizer.
- **`runtime/journal.py` — `JsonlJournal`** is a per-process locked, fsynced JSONL journal; `runtime/recovery.py` refuses to resume a Run it cannot prove safe.
- **`runtime/store.py`** — `RunStore` + content-addressed `ArtifactStore`; **`runtime/mcp.py`** — `MCPConnector` registers MCP capabilities post-startup; **`runtime/skills.py`** — `SkillCatalog` does read-only, bounded-metadata skill discovery.

`bootstrap.py::build_platform()` is the composition root — it wires stores, registries, gate, classifier and coordinator into a `Platform`; both FastAPI (`main.py` / `api/app.py`) and the CLI use it. It registers **only** generic host primitives (see `tools/` below) — there is currently no domain capability in the tree. A host adds one by calling `platform.capabilities.register(...)` after `build_platform()` returns; do it before `refresh_skills()` so skills naming that tool in `allowed-tools` can still be discovered.

### HTTP endpoints (`api/routes/`)
- `POST /runs` (202) — create and execute asynchronously; `GET /runs/{id}`; `GET /runs/{id}/stream` — resumable SSE.
- `POST /runs/{id}/approvals/{approval_id}` — approve/reject by revision (stale revision ⇒ rejected); `POST /runs/{id}/cancel` — idempotent.
- `/sessions` CRUD + `GET /sessions/{id}/messages`; `/artifacts` POST/GET.
- `GET /skills`, `POST /skills/validate` are read-only. **Mutating skill APIs** (`POST /skills/import`, `POST|DELETE /skills/{name}/trust`, `DELETE /skills/{name}`) are host administration, not model capabilities: they require `Authorization: Bearer <PRIVILEGED_API_TOKEN>` via `api/security.py::require_privileged` and return **403**, never 401.

Shapes in `docs/api-contract/agent-runtime-v1.md`.

### Runtime data root
`config.py::runtime_data_root()` = `$MAESTRO_DATA_DIR` or `~/.maestro`. Under it: `sessions-v3/`, `runs/`, `artifacts/`, `skills/` (incl. `trust.json`), `workspace/`, `runtime/journal.jsonl`. Tests get an isolated tmp root via the autouse `_isolate_runtime_data` fixture in `tests/conftest.py` — never write to the user's real data root from a test.

### Skills
Claude Code-compatible directories, loaded in **three tiers**, each backed by a distinct code path:

1. **Metadata** — `SkillCatalog._read_metadata` reads at most 16 KB of frontmatter at discovery; the body is never touched. Only `name` + `description` reach the model, as a `CapabilityKind.SKILL` entry.
2. **Body** — `SkillCatalog.load` injects `SKILL.md`'s prompt once the skill is actually selected, wrapped as untrusted data, and narrows the allowlist to the skill's `allowed-tools`.
3. **Resources** — `skill_read_resource` pulls one `references/` or `scripts/` file in on demand. Tier 2 injects only the *manifest* of filenames, so contents cost nothing until asked for.

A loaded skill is implicitly granted `skill_read_resource` (and `skill_run_script` when it ships scripts) so that declaring no `allowed-tools` doesn't narrow the allowlist to nothing. Authorization still runs through the Policy Gate. `RunCoordinator._skill_resource_call_is_owned` confines both to skills the Run actually loaded.

`disable-model-invocation: true` keeps a skill out of the model-visible capability list while leaving it explicitly invocable. Frontmatter schema lives in `skills/schemas.py`, parsing in `skills/parser.py`; `POST /skills/validate` and `POST /skills/import` share `validate_runtime_package`, so nothing can be installed under looser rules than the preflight showed.

One broken package never hides the others: `discover()` collects per-skill failures into `SkillCatalog.errors` and surfaces them in `GET /skills`.

### Skill scripts, trust and the sandbox
`skill_run_script` runs a package's `scripts/*.py|sh` behind three independent gates: the capability is `writes=True, risk=HIGH` so the Policy Gate always demands human approval; `SkillTrustStore` (`skills/trust.py`, persisted to `skills_dir/trust.json`) requires a trust record matching the package's **current** content hash, so editing a trusted skill revokes its own permission; and the script path is confined to `scripts/`.

`tools/sandbox.py` is **containment, not a security boundary** — the approval and the hash binding are the real gates. It always spawns via `create_subprocess_exec` (never a shell) into a throwaway workspace with an allowlisted environment (no API keys inherited), wall-clock and output caps, and copies artifacts out before deleting the workspace. macOS adds a `sandbox-exec` profile; Windows gets the baseline only. `SandboxResult.isolation` reports what actually took effect — do not claim more.

### Host capabilities (`tools/`)
`tools/` holds generic primitives a skill's `allowed-tools` can name — `read_file`/`glob`/`grep` (read-only, fast path) and `write_file`/`edit_file` (`writes=True, risk=HIGH`, so they require approval). All are confined to `config.py::workspace_root` via `runtime/paths.py::safe_join`, the single path-confinement helper shared with skill resources. They live outside `runtime/` and are registered from `bootstrap.py`, keeping the Runtime core capability-agnostic. These are the only capabilities a default platform has; `test_b1_invariants.py::GENERIC_PRIMITIVES` is the allowlist that keeps it that way — add a primitive there, never a domain tool.

### Degraded mode
With no `LLM_API_KEY`, Runs can still be created, resumed, cancelled, approved and audited; only the model's answers degrade. The test suite never touches the network.

## Frontend architecture

- **Data layer** (`src/api/`) — plain request fns (`client.ts`, `runs.ts`, `sessions.ts`, `skills.ts`, `artifacts.ts`) + the `useRunStream` SSE hook + TanStack Query hooks (`hooks.ts`), all re-exported from `api/index.ts`. Server state lives in the Query cache.
- **Zustand stores** (`src/stores/`) — client-only state, imported by direct path (there is no barrel): `runStore` (in-flight run + trace), `sessionStore` (active session id), `themeStore`, `uiPreferencesStore` (run mode, trace default), `personalizationStore`.
- **Features** (`src/features/`) — `orchestrator/` (Composer + ConversationPanel + `skills/` import & manager modals), `runtime/RunTrace.tsx` (step trace + approval UI), `settings/SettingsModal.tsx`.
- **Shell** — `components/layout/` (`Layout` + `TopBar` + `SessionSidebar`); `pages/Workspace.tsx` is the single page and wires stores, streaming and modals together.
- **MSW mocks** (`src/mocks/api/`) — handlers + SSE simulation, active only when `VITE_API_MOCKING=enabled`.
- Design tokens are defined once in `src/index.css` (`:root` CSS vars) and mirrored as Tailwind utilities in `tailwind.config.ts` — use the semantic tokens, never raw hex. Note `tailwind.config.ts` **redefines the default spacing scale**; check it before assuming stock Tailwind values.
- Import alias: `@/` → `src/`.

## Conventions specific to this repo

- `maestro/.env` is gitignored and holds real credentials — never commit it. `.env.example` is the template; `frontend/.env.development` holds non-secret dev defaults and is committed.
- The privileged token must match on both sides (`PRIVILEGED_API_TOKEN` backend, `VITE_PRIVILEGED_API_TOKEN` frontend), otherwise skill install/trust calls fail as a silent 403. `restart.sh` keeps them in sync; changing the backend token requires a backend restart.
- When revising a design doc under `docs/design/`, add a new `vN+1` file rather than overwriting the previous version.
- `AGENTS.md` intentionally defers to this file — keep guidance here so the two cannot drift apart.
