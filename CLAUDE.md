# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

Two independently-run apps that talk over an HTTP/SSE contract:

- `scheduling_platform/` — Python 3.12 FastAPI backend ("一个平台 / 三个引擎 / 一个入口"). Source under `src/scheduling_platform/`. Source of truth for behavior; see its `README.md`.
- `frontend/` — React 18 + Vite + TypeScript + Tailwind SPA (internal name "Cadence"/"Maestro"). Talks to the backend contract in `docs/api-contract.md`; ships with MSW mocks so it runs without the backend.

The package is `scheduling_platform`, **not** `platform` — `platform` is a stdlib name that shadows dependency imports. Design docs say `src/platform/`; the real path is `src/scheduling_platform/`.

## Commands

### Backend (`scheduling_platform/`)
```bash
uv venv --python 3.12 && source .venv/bin/activate   # ortools needs 3.11–3.13, NOT 3.14
uv pip install -e ".[dev]"                            # or: python3.12 -m venv .venv && pip install -e ".[dev]"
cp .env.example .env                                  # fill LLM_API_KEY (DeepSeek default); runs without it (degraded mode)

uvicorn scheduling_platform.main:app --reload         # HTTP API on :8000
python -m scheduling_platform.cli                     # interactive CLI (best first experience)

pytest                                                # all LLM calls mocked, no network
pytest tests/test_planning.py::test_strategy_plugin_registration   # single test
```

### Frontend (`frontend/`)
```bash
npm install
npm run dev        # Vite on :5173; MSW mocks by default (VITE_API_MOCKING=enabled in .env.development)
npm run build      # tsc -b && vite build
npm run lint       # eslint, --max-warnings 0
npm run format     # prettier
```
To hit the real backend instead of mocks, set `VITE_API_MOCKING=disabled` in `frontend/.env.development` (API base is `/api/v1`; Vite has no proxy configured, so wire one to `:8000` if needed).

## Backend architecture

Request flow: **user (CLI/HTTP) → Orchestrator → one of three engines**, with an **event layer** that can wake the scheduling engine without a user.

- **Orchestrator** (`orchestrator/`) — three-layer intent routing: ① embedding semantic route (vector similarity + margin; `EMBED_MODEL` must be set or this layer is skipped) → ② LLM structured classification → ③ low-confidence clarification (option answers route directly; open answers return to the LLM layer).
- **PlanningEngine** (`engines/planning/`) — **fixed workflow**: extract params → select strategy → solve → validate → explain. Algorithm-agnostic: a product line = a `PlanningStrategy` subclass registered in `bootstrap.py`. Ships 3 strategies (FlowShopTardiness/JobShopMakespan = OR-Tools CP-SAT, SimpleDispatch = EDD rule). Strategy choice itself is 3-layer: `strategy_mapping.yaml` rules → LLM assist → clarification.
- **SchedulingEngine** (`engines/scheduling/`) — **ReAct agent** (`agent_loop.py`): think→act→observe over a tool whitelist with loop guards (max steps / whitelist / cycle detection) and **two write guards** (`preconditions.py` assertions + `ActionGate` authorization). Triggered by both chat and events.
- **QueryEngine** (`engines/query/`) — **RAG + LLM**: retrieve from vector store → augment → generate, read-only tools, answers cite sources.

### Cross-cutting foundation (`foundation/`)
- **Integration abstraction** — business code depends only on the `IntegrationAdapter` interface. `MockAdapter` is wired in `bootstrap.py`; swapping in a real MES/ERP/WMS means implementing the interface and replacing it there — engines/tools unchanged.
- **Action authorization** — every write goes through `ActionGate` (`auto` vs `requires_confirmation`) and is audited. Supplier expediting, work-order dispatch, and exception notifications require human confirmation (`/chat/confirm` or CLI `confirm <action_id>`).
- **Event-driven** (`events/`) — scheduler patrol (pull external events + predictive kitting scan) → in-memory event bus → events translated into task descriptions that wake the same ReAct agent, reusing the chat path's tools and guards.

`bootstrap.py::build_platform()` is the composition root — it constructs and wires the adapter, registries, all engines, and the orchestrator into a `Platform`; both FastAPI (`main.py`) and the CLI use it.

### HTTP endpoints (`main.py`)
`POST /chat`, `POST /chat/confirm`, `POST /events` (inject system events to test event-driven wakeup), `GET /audit`, `GET /pending`, `GET /health`.

### Degraded mode
With no API key: routing falls back to clarification, param extraction to regex, explanation to templates — but solving / kitting / expediting / dispatch / event-driven flow / audit all still work, so the architecture is verifiable offline.

## Frontend architecture

- **Data layer** (`src/api/`) — plain request fns + TanStack Query hooks + SSE streaming hooks (`useStreamingChat`, `useStreamingQuery`), all re-exported from `api/index.ts`. Contract in `docs/api-contract.md`.
- **MSW mocks** (`src/mocks/`) — `api/` handlers + SSE simulation intercept requests in dev; `session.ts`/`conversation.ts`/`panels.ts` hold demo UI state.
- **Features** (`src/features/`) — `orchestrator` (chat thread + Composer with route/mode selectors), `planning`/`scheduling`/`query` panels mirror the three backend engines.
- **Shell** — `components/layout/` (`Sidebar` + `Layout` + `TopBar`); `Workspace.tsx` is the page; Zustand `conversationStore` holds committed messages + active engine + panel state (the in-flight streaming turn lives in the hook, not the store).
- Design tokens are defined once in `src/index.css` (`:root` CSS vars) and mirrored as Tailwind utilities in `tailwind.config.ts` — use the semantic tokens (`bg-planning`, `text-route-query-fg`, etc.), never raw hex.
- Import alias: `@/` → `src/`.

## Conventions specific to this repo

- The four engine "routes" (planning/scheduling/query + uncertain) carry consistent color identities across backend logs and frontend tokens; keep new UI on the existing `ROUTE_META` tokens.
- `scheduling_platform/.env` is gitignored and holds real credentials — never commit it. `.env.example` is the template; `frontend/.env.development` holds non-secret dev defaults and is committed.
- Items marked `TODO(v0.2)` in the backend are intentionally deferred (session-sticky routing, composite task decomposition, expediting timeout escalation, etc.) — don't implement them unless asked.
