# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

Two independently-run apps that talk over an HTTP/SSE contract:

- `maestro/` — Python 3.12 FastAPI backend: a generic, policy-governed **Agent Runtime**. Source under `src/maestro/`. Source of truth for behavior; see its `README.md`.
- `frontend/` — React 18 + Vite + TypeScript + Tailwind SPA, with an optional Electron shell (`frontend/electron/`). Canonical contract in `docs/api-contract/agent-runtime-v2.md`; MSW mocks are only an offline demo aid.

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

The canonical backend is the SQLite-backed v2 Runtime:

- **`runtime/agent.py` — `AgentRuntime`** is the sole owner of Run lifecycle changes. It executes one model action per turn, enforces exact transition legality, detects repeated calls, upgrades FAST to STRUCTURED before governed writes, and stops on unknown write outcomes.
- **`foundation/sqlite_store.py`** owns the local-first database at `<data root>/runtime-v2/maestro.db` (WAL, foreign keys, optimistic Run revisions). `agent_event` is the durable fact log; Session, Run, Checkpoint, Plan, approval, evidence and model-turn rows are projections or referenced records.
- **`runtime/trajectory.py`** defines the canonical uppercase `AgentEvent` protocol and accumulated state. Provider messages are rendered from Checkpoint + hot events; raw Tool results live once in `tool_result` and enter model context only as bounded digests/references.
- **`runtime/session_context.py` / `checkpointing.py`** build the exact frozen prefix, current Checkpoint, hot trajectory, lazy working content and sparse StatusBar under the model profile's explicit budget. Compaction is deterministic over explicit state events.
- **`runtime/resolver.py` / `meta_tools.py`** expose a small fixed core. Non-core schemas become callable only after `tool_search` pins their exact version. Skill bodies are persisted once by version and rehydrated after `load_skill`; they are not copied into Run state.
- **`extensions/retrieval.py`** installs bounded, read-only local `knowledge_search` and `memory_search` capabilities outside `runtime/`. Recall creates Evidence records; final answers cannot cite an unknown Evidence id.

`runtime/coordinator.py`, JSON Run files and the unversioned `/runs` endpoints remain only as a temporary v1 compatibility surface. Do not add new behavior there; all new Agent work belongs to v2.

Every request becomes a persisted **Run**. `IntentClassifier` picks the initial path; the Run may escalate from fast to structured, **never the reverse**.

- **`runtime/coordinator.py` — `RunCoordinator`** is the only component that mutates Run state. It owns the bounded fast loop (`run_until_blocked`) and controlled execution (`_run_controlled`), consults the Policy Gate before every capability call, and creates approval records when a call needs a human.
- **`runtime/state_machine.py`** — explicit `RUN_TRANSITIONS` / step transition tables; anything illegal raises `InvalidTransition`. Run statuses: `created → running_fast | structuring → running_structured → waiting_approval | waiting_external | reconciling → completed | failed | cancelled`.
- **`runtime/capabilities.py` — `CapabilityRegistry`** is the single namespace for TOOL / MCP / SKILL capabilities, each with a `RiskLevel`. A Skill can never raise a Tool/MCP's risk level, only narrow it.
- **`runtime/policy.py` — `PolicyGate`** evaluates deterministic rules in fixed precedence and returns allow / require-approval / deny. It is the only authorization path. `require_reconfirmation` asks for two human confirmations; each round rebinds the external-state token, so the second one is what proves nothing moved in between. `approve()` must treat the confirmation effects as *satisfied* — reading them as staleness re-issues an approval forever and no high-risk write can ever run.
- **`runtime/intent.py` — `IntentClassifier`** selects FAST only when neither a deterministic signal nor a model complexity signal demands structure.
- **`runtime/context.py`** — priority + trust-ranked context assembly with a char budget and a truncating summarizer. `assemble()` governs **both** channels — the system context and the conversation — under one token budget (`context_max_prompt_tokens`, default 48000), because the conversation is what grows fastest and used to be bounded by nothing at all. Over budget it demotes the *oldest* bulky `role=tool` results to artifact references, never the newest `keep_recent_tool_results`, and never silently: every demotion is reported in `BudgetReport.shed` and published as `context.shed`. Sizing comes from `runtime/tokens.py`, a dependency-free estimator calibrated against real `usage` (CJK ≈1 tok/char, ASCII letters ≈0.25, digits/punctuation ≈0.5, plus a large fixed cost per tool schema). It is a best fit, not an upper bound — the safety margin is the gap between `context_max_prompt_tokens` and the model's real window, kept explicit rather than hidden in the estimator.

A capability result goes to **exactly one** channel: inline into the conversation as `role=tool`, or — above `artifact_threshold_bytes` — into an artifact whose P3 reference is all the system context keeps. It used to go to both, so every result under the threshold was billed twice in the same prompt (~50% of tool-result cost). Tool results are threaded as plain JSON on purpose: an `<untrusted-data>` fence would escape the payload and hide the `artifact_ref` the model must read back out of it. What frames them as data is the standing instruction in `MAESTRO_SYSTEM_PROMPT`.
- **`runtime/journal.py` — `JsonlJournal`** is a per-process locked, fsynced JSONL journal; `runtime/recovery.py` refuses to resume a Run it cannot prove safe.
- **`runtime/store.py`** — `RunStore` + content-addressed `ArtifactStore`; **`runtime/mcp.py`** — `MCPConnector` is the governed registration boundary for MCP capabilities (transport-agnostic; see `mcp/` below); **`runtime/skills.py`** — `SkillCatalog` does read-only, bounded-metadata skill discovery.

The agent loop speaks standard function calling: after each capability call the coordinator appends the assistant turn and a matching `role=tool` result to the conversation. A recoverable failure — executor exception, `status="failed"`, schema mismatch, undecodable arguments — is fed back to the model to correct and costs a step; only authorization decisions, ownership violations and budgets end a Run. A definitive write returns to the loop so the model can answer, rather than stranding the Run in `running_structured`.

`bootstrap.py::build_platform()` is the composition root — it wires stores, registries, gate, classifier and coordinator into a `Platform`; both FastAPI (`main.py` / `api/app.py`) and the CLI use it. It registers **only** generic host primitives (see `tools/` below) — there is currently no domain capability in the tree. A host adds one by calling `platform.capabilities.register(...)` after `build_platform()` returns; do it before `refresh_skills()` so skills naming that tool in `allowed-tools` can still be discovered.

### HTTP endpoints (`api/routes/`)
- Canonical Agent API: `POST /api/v2/sessions`, `POST /api/v2/sessions/{id}/runs`, `GET /api/v2/runs/{id}`, and resumable `GET /api/v2/runs/{id}/stream`. SSE `event` names are canonical uppercase `AgentEventType` values and `data` is the complete serialized `AgentEvent`.
- `POST /api/v2/runs/{id}/approvals/{approval_id}` binds the decision to `expected_revision`; the approved continuation runs in the background. `POST /api/v2/runs/{id}/cancel` transitions through `cancelling`.
- `/api/v2/sessions/{id}/debug`, `/api/v2/runs/{id}/debug` and `/api/v2/sessions/{id}/replay` expose trajectory, Checkpoint, Plan, approval and ContextManifest diagnostics. Knowledge/Memory writes under `/api/v2` require the privileged host token.
- `POST /runs` (202) — create and execute asynchronously; `GET /runs/{id}`; `GET /runs/{id}/stream` — resumable SSE.
- `POST /runs/{id}/approvals/{approval_id}` — approve/reject by revision (stale revision ⇒ rejected). Answers **202** with a non-terminal snapshot as soon as the decision is made; the approved write and the model turn reporting it continue in the background, so the client re-subscribes to the stream rather than waiting on the response. `POST /runs/{id}/cancel` — idempotent.
- `/sessions` CRUD + `GET /sessions/{id}/messages`; `/artifacts` POST/GET.
- `GET /mcp/servers` is read-only; `PUT|DELETE /mcp/servers/{name}` and `POST /mcp/servers/{name}/reconnect` are host administration and require the same privileged token as the skill APIs.
- `GET /models` is read-only and always redacts `api_key` (empty string + a derived `api_key_set`); `PUT /models` and `POST /models/test` are host administration behind the same privileged token. The active provider in `settings.json` **overrides** the flat `llm_*`/`embed_*` env values; `PUT` hot-reloads the live client in place via `LLMClient.reconfigure` — never replace `platform.llm`, the coordinator and summarizer hold it by reference.
- `GET /skills`, `POST /skills/validate` are read-only. **Mutating skill APIs** (`POST /skills/import`, `POST|DELETE /skills/{name}/trust`, `DELETE /skills/{name}`) are host administration, not model capabilities: they require `Authorization: Bearer <PRIVILEGED_API_TOKEN>` via `api/security.py::require_privileged` and return **403**, never 401.

The v2 shape is in `docs/api-contract/agent-runtime-v2.md`. The v1 document describes only the compatibility surface.

### Runtime data root
`config.py::runtime_data_root()` = `$MAESTRO_DATA_DIR` or `~/.maestro`. Canonical Agent state is `runtime-v2/maestro.db`; artifacts, skill packages/trust, workspace and host `settings.json` remain separate host data. v1 `sessions-v3/`, `runs/` and `runtime/journal.jsonl` are not migrated into v2. Tests get an isolated tmp root via the autouse `_isolate_runtime_data` fixture in `tests/conftest.py` — never write to the user's real data root from a test.

### Skills
Claude Code-compatible directories, loaded in **three tiers**, each backed by a distinct code path:

1. **Metadata** — `SkillCatalog._read_metadata` reads at most 16 KB of frontmatter at discovery; the body is never touched. Only `name` + `description` reach the model, as a `CapabilityKind.SKILL` entry.
2. **Body** — `SkillCatalog.load_body` reads `SKILL.md` only when selected. v2 stores the immutable body in `skill_definition` by exact version and keeps only version + arguments + narrowed allowlist on the Run, so restart/replay does not depend on duplicated prompt text.
3. **Resources** — `skill_read_resource` pulls one `references/` or `scripts/` file in on demand. Tier 2 injects only the *manifest* of filenames, so contents cost nothing until asked for.

A loaded skill is implicitly granted `skill_read_resource` (and `skill_run_script` when it ships scripts) so that declaring no `allowed-tools` doesn't narrow the allowlist to nothing. Authorization still runs through the Policy Gate. `RunCoordinator._skill_resource_call_is_owned` confines both to skills the Run actually loaded.

`disable-model-invocation: true` keeps a skill out of the model-visible capability list while leaving it explicitly invocable. Frontmatter schema lives in `skills/schemas.py`, parsing in `skills/parser.py`; `POST /skills/validate` and `POST /skills/import` share `validate_runtime_package`, so nothing can be installed under looser rules than the preflight showed.

One broken package never hides the others: `discover()` collects per-skill failures into `SkillCatalog.errors` and surfaces them in `GET /skills`.

### Skill scripts, trust and the sandbox
`skill_run_script` runs a package's `scripts/*.py|sh` behind three independent gates: the capability is `writes=True, risk=HIGH` so the Policy Gate always demands human approval; `SkillTrustStore` (`skills/trust.py`, persisted to `skills_dir/trust.json`) requires a trust record matching the package's **current** content hash, so editing a trusted skill revokes its own permission; and the script path is confined to `scripts/`.

`tools/sandbox.py` is **containment, not a security boundary** — the approval and the hash binding are the real gates. It always spawns via `create_subprocess_exec` (never a shell) into a throwaway workspace with an allowlisted environment (no API keys inherited), wall-clock and output caps, and copies artifacts out before deleting the workspace. macOS adds a `sandbox-exec` profile; Windows gets the baseline only. `SandboxResult.isolation` reports what actually took effect — do not claim more.

### Host capabilities (`tools/`)
`tools/` holds generic primitives a skill's `allowed-tools` can name — `read_file`/`glob`/`grep` (read-only, fast path), `write_file`/`edit_file` (`writes=True, risk=HIGH`, so they require approval), and `read_artifact`, which dereferences a result too large to inline. All filesystem paths are confined to `config.py::workspace_root` via `runtime/paths.py::safe_join`, the single path-confinement helper shared with skill resources; `glob` and `grep` additionally re-check every match, since `safe_join` only vets the scope they were pointed at. They live outside `runtime/` and are registered from `bootstrap.py`, keeping the Runtime core capability-agnostic. These are the only capabilities a default platform has; `test_b1_invariants.py::GENERIC_PRIMITIVES` is the allowlist that keeps it that way — add a primitive there, never a domain tool.

`bash` (`tools/shell.py`) is **arbitrary command execution**, registered because `allowed-tools: Bash` is the commonest declaration in real Claude Code skills. It is `writes=True, risk=HIGH`, so the approval the Policy Gate demands before every call is the real gate; `sandbox.run_command` adds containment only. Unlike the filesystem capabilities it cannot be proven to stay inside the workspace — say so rather than implying otherwise.

`DEFAULT_TOOL_ALIASES` (`skills/parser.py`) maps Claude's tool names onto these. Only map a name the host actually registers — an alias pointing at nothing turns every skill declaring it into a discovery failure. `PowerShell`, `WebFetch` and `TodoWrite` have no counterpart here by design.

### MCP (`mcp/`)
`mcp/` is the stdio client: `transport.py` (newline-delimited JSON-RPC over a child process), `client.py` (protocol `2024-11-05` — `initialize`, `notifications/initialized`, `ping`, `tools/list`, `tools/call`), `manager.py` (lifecycle + publication). Resources, SSE and HTTP are **not** implemented; don't document them as if they were.

Two properties are load-bearing. The child inherits only `PATH`/`LANG`/`LC_ALL`/`TZ`/`HOME`/`TMPDIR` plus its own configured `env`, so `LLM_API_KEY` never reaches an MCP server; and stderr is drained continuously, because a server that logs freely will otherwise fill the pipe and hang. Every discovered tool defaults to `writes=True, risk=HIGH`; a local administrator may name specific tools in the server's `read_only_tools` list, which registers only those tools as `writes=False, risk=LOW, idempotent=True`. Remote metadata and annotations can never lower risk or shadow a same-named TOOL/SKILL (`MCPCapabilityConflict`); an explicit remote `readOnlyHint=false` or `destructiveHint=true` may only veto a mistaken local downgrade. Negotiated protocol/server metadata and remote instructions are retained for diagnostics, but remote instructions are never injected as privileged Runtime instructions. MCP `isError=true` becomes a failed capability result, while successful `structuredContent` is preferred and paired with a bounded text summary.

Every MCP tool call carries the Run owner in `_meta.maestro/principalId`; this host-owned value is attached only after policy approval and is never model-controlled or serialized into the model-visible call. An MCP server may return structured `AUTH_REQUIRED` details to request interactive login. The client opens each challenge once only when its URL is HTTP(S) on loopback (`localhost`, `127.0.0.1`, or `::1`), then retries the unchanged tool call until it succeeds or the bounded five-minute wait expires. The MCP server remains responsible for binding that principal to an isolated authenticated session.

Servers are configured under the `mcp_servers` key of `<data root>/settings.json` (`foundation/mcp_config_store.py`), never via env vars, and connected from `api/app.py::lifespan` — after `build_platform()`, so a slow or broken server cannot stop the Runtime coming up. `api/routes/mcp.py` mirrors the skills routes: reads are open, mutations need `PRIVILEGED_API_TOKEN` and answer 403.

### Degraded mode
With no `LLM_API_KEY`, Runs can still be created, resumed, cancelled, approved and audited; only the model's answers degrade. A Run whose model call fails now **fails** (`run.failed` with `model_unavailable`, or `context_overflow` when the prompt exceeded the window) instead of completing with a fabricated "模型当前不可用。" that was written into the session history as if it were a real reply. The test suite never touches the network.

## Frontend architecture

- **Data layer** (`src/api/`) — Session/Run calls target `/api/v2`; `streamRun` parses complete canonical `AgentEvent` frames and `runStore` projects them. Host settings/Skill/MCP/Artifact calls retain their host routes.
- **Zustand stores** (`src/stores/`) — client-only state, imported by direct path (there is no barrel): `runStore` (in-flight run + trace), `sessionStore` (active session id), `themeStore`, `uiPreferencesStore` (run mode, trace default), `personalizationStore`.
- **Features** (`src/features/`) — `orchestrator/` (Composer + ConversationPanel + `skills/SkillMenu`, a per-run picker only), `runtime/RunTrace.tsx` (step trace + approval UI), `settings/SettingsModal.tsx`, `extensions/` (the Extensions Center).
- **Shell** — `components/layout/` (`Layout` + `TopBar` + `SessionSidebar`); `pages/Workspace.tsx` wires stores, streaming and modals for `/`.
- **Routes** — `/` is the Workspace; `/debug/runs/:runId` is the v2 trajectory inspector; `/settings/skills` and `/settings/connectors` are the full-width Extensions Center. The debug view reads durable events, replay integrity, Checkpoint, Plan/approvals and per-turn token/hash manifests from the backend rather than reconstructing them from UI state.
- **MSW mocks** (`src/mocks/api/`) — handlers + SSE simulation, active only when `VITE_API_MOCKING=enabled`.
- Design tokens are defined once in `src/index.css` (`:root` CSS vars) and mirrored as Tailwind utilities in `tailwind.config.ts` — use the semantic tokens, never raw hex. Note `tailwind.config.ts` **redefines the default spacing scale**; check it before assuming stock Tailwind values.
- Import alias: `@/` → `src/`.

## Conventions specific to this repo

- `maestro/.env` is gitignored and holds real credentials — never commit it. `.env.example` is the template; `frontend/.env.development` holds non-secret dev defaults and is committed.
- The privileged token must match on both sides (`PRIVILEGED_API_TOKEN` backend, `VITE_PRIVILEGED_API_TOKEN` frontend), otherwise skill install/trust calls fail as a silent 403. `restart.sh` keeps them in sync; changing the backend token requires a backend restart.
- When revising a design doc under `docs/design/`, add a new `vN+1` file rather than overwriting the previous version.
- `AGENTS.md` intentionally defers to this file — keep guidance here so the two cannot drift apart.

## 上下文结构（Context Layout）

上下文由两段构成，Agent 必须能显式区分二者：

| 分段 | 内容 | 变化特征 |
|---|---|---|
| **静态前缀** Static Prefix | 系统提示词、工具定义（schema）、长期不变的领域知识与示例 | 跨轮次逐 token 完全一致 |
| **对话轨迹** Trajectory | user / assistant 消息、tool_use、tool_result | 只追加（append-only），随交互单调增长 |

**排布原则：按变化频率从低到高排列**——最稳定的放最前，最易变的放最后。

### 利用不变性加速推理

原理：Transformer 的 KV Cache 可按前缀复用。命中前缀缓存后，这部分无需重新 prefill，直接体现为 **TTFT 下降**与**成本下降**（缓存命中的 token 计费通常为未命中的 1/10）。

**硬性前提：从第 0 个 token 起逐字节一致。** 任何一处差异，从该位置往后的缓存全部作废。

由此推出以下约束：

1. **前缀内零变量**：禁止在静态前缀中写入时间戳、随机 ID、session ID、剩余步数等动态值。需要时间信息就放到轨迹的最后一条消息里。
2. **工具集合固定**：不要根据状态动态增删工具定义。需要限制可用工具时，用 logits mask / 约束解码在解码阶段屏蔽，而不是改前缀。
3. **序列化确定性**：JSON 的 key 顺序、空格、转义必须稳定；很多序列化库默认不保证 key 有序。
4. **历史严格 append-only**：不回改、不重排、不删除中间轮次。中间一次改写 = 其后所有缓存失效。
5. **压缩发生在边界**：需要裁剪/摘要历史时，在明确的切分点整段处理，保留静态前缀不动，并保证摘要产物本身稳定可复用。
6. **显式标记缓存断点**：使用 API 的缓存控制字段（如 `cache_control`）标出前缀末尾；自托管则开启 prefix caching，并在多副本部署下做会话亲和路由，避免请求打到没有缓存的实例。

### 需要监控的指标

- 前缀缓存命中率（首要指标）
- TTFT
- cached / uncached token 比例与由此产生的成本

任何对提示词或工具定义的改动，都应视为一次全量缓存失效，评估其代价后再决定是否上线。
