# Desktop Runtime & Provider Config — Implementation Plan (Plan 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Electron shell launch and lifecycle-manage the Python backend as a self-contained desktop app, with an in-app multi-provider LLM/Embedding settings UI — fully testable locally via `electron:preview` (no PyInstaller, no certs).

**Architecture:** Electron `main.cjs` spawns the backend as a child process (venv `python -m maestro.sidecar_entry` in preview, frozen `MaestroBackend` exe when packaged) on a dynamically-picked loopback port, polls `/health`, then loads the renderer with the port as a `?bp=` query param. The renderer's `API_BASE` reads `bp` and points at the backend. Runtime data is relocated to Electron `userData` via `MAESTRO_DATA_DIR`. Provider config (`providers.json`) is managed in the left-bottom settings menu; Electron resolves the active provider into flat `LLM_*`/`EMBED_*` process env at spawn (backend LLM/Embedding reading unchanged).

**Tech Stack:** Python 3.12, FastAPI, uvicorn, pydantic-settings; Electron 33, electron-builder 25, React 18, Vite, TypeScript, Tailwind, TanStack Query, Zustand; pytest, vitest (jsdom), node:test.

## Global Constraints

- Python 3.12 (ortools needs 3.11–3.13, NOT 3.14). Package is `maestro`, not `platform`.
- macOS arm64 only; Windows x64 only (Plan 2).
- Backend binds `127.0.0.1` only; port via env `MAESTRO_BACKEND_PORT` (dynamic, picked by Electron).
- Runtime data via env `MAESTRO_DATA_DIR` (= Electron `userData`); seed data (`mock_data_dir`, `knowledge_dir`) stays bundled at `project_root()`, not relocated.
- `LLM_*`/`EMBED_*` injected as process env at spawn — backend never reads an `.env` file in the packaged app. `providers.json` lives in `userData` (v1 plaintext).
- No auto-update, no `safeStorage`, no EV cert in v1.
- Frontend uses semantic Tailwind tokens only (`bg-surface-1`, `text-text-secondary`, `border-border-subtle`, `text-accent-fg`, `ring-accent-border`, etc.) — never raw hex.
- `electron:dev` (Vite + Electron against the Vite dev server) must stay UNCHANGED: it loads `DEV_URL` and does NOT spawn the backend (dev backend still run via `./restart.sh`). The sidecar spawn happens only in `electron:preview` (env `MAESTRO_SIDECAR=1`) and packaged builds.

## File Structure

**Backend (Python):**
- `maestro/src/maestro/config.py` — add `_runtime_data_root()`; repoint writable dirs (sessions/chroma/skills/knowledge_uploads/audit) to it. Seeds stay at `project_root()`.
- `maestro/src/maestro/sidecar_entry.py` (new) — thin uvicorn launcher: reads `MAESTRO_BACKEND_PORT`, binds `127.0.0.1`, runs `app` from `main`. PyInstaller entrypoint (Plan 2).
- `maestro/tests/test_config_data_dir.py` (new) — data-dir behavior.
- `maestro/tests/test_sidecar_entry.py` (new) — `resolve_bind()`.

**Frontend renderer (TS/React):**
- `frontend/src/api/client.ts` — `API_BASE` resolves from `?bp=` query param, falls back to `VITE_API_BASE_URL`/`/api/v1`. Single source for HTTP (`client.ts`) + SSE (`streaming.ts`, imports `API_BASE`).
- `frontend/src/api/client.test.ts` (new) — `bp` resolution.
- `frontend/src/features/orchestrator/settings/SettingsModal.tsx` (new) — provider CRUD (LLM + Embedding sections), reads/writes via Electron IPC.
- `frontend/src/features/orchestrator/settings/SettingsModal.test.tsx` (new).
- `frontend/src/components/layout/Sidebar.tsx` — add "模型" group + "LLM / Embedding 供应商…" item to the existing settings Popover, gated on `electronAPI.isElectron`; render `<SettingsModal>`.

**Electron main/preload (CJS):**
- `frontend/electron/backend-config.cjs` (new) — pure helpers (no `electron` import): `readProviders/writeProviders/upsertProvider/removeProvider/setActive/resolveActiveEnv/pickFreePort`. Unit-testable.
- `frontend/electron/backend-config.test.cjs` (new) — node:test.
- `frontend/electron/main.cjs` — rewrite: sidecar lifecycle (spawn/health/splash/single-instance/shutdown), dev/preview/packaged modes, providers IPC + respawn-on-change.
- `frontend/electron/preload.cjs` — expose `providers` IPC bridge + `onBackendReconnecting`.

**Wiring:**
- `frontend/package.json` — `electron:preview` adds `MAESTRO_SIDECAR=1`; add `test:electron` script.

---

## Task 1: Backend — relocate writable data to `MAESTRO_DATA_DIR`

**Files:**
- Modify: `maestro/src/maestro/config.py`
- Test: `maestro/tests/test_config_data_dir.py` (new)

**Interfaces:**
- Produces: `Settings.sessions_dir` / `chroma_dir` / `skills_dir` / `knowledge_upload_dir` / `audit_log_file` now honor `MAESTRO_DATA_DIR` env; `Settings.mock_data_dir` / `knowledge_dir` unchanged (bundled seeds). No signature changes — consumers (`bootstrap.py`) read these fields as before.

- [ ] **Step 1: Write the failing test**

```python
# maestro/tests/test_config_data_dir.py
from maestro.config import Settings, project_root


def test_data_dir_defaults_to_project_data(monkeypatch):
    monkeypatch.delenv("MAESTRO_DATA_DIR", raising=False)
    s = Settings()
    assert s.sessions_dir == project_root() / "data" / "sessions"
    assert s.chroma_dir == project_root() / "data" / "chroma"


def test_data_dir_honors_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRO_DATA_DIR", str(tmp_path))
    s = Settings()
    assert s.sessions_dir == tmp_path / "sessions"
    assert s.chroma_dir == tmp_path / "chroma"
    assert s.skills_dir == tmp_path / "skills"
    assert s.knowledge_upload_dir == tmp_path / "knowledge_uploads"
    assert s.audit_log_file == tmp_path / "logs" / "audit.jsonl"


def test_seed_dirs_not_relocated_by_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRO_DATA_DIR", str(tmp_path))
    s = Settings()
    # 种子数据随包发布，不走 userData
    assert s.mock_data_dir == project_root() / "data" / "mock"
    assert s.knowledge_dir == project_root() / "data" / "mock" / "knowledge"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd maestro && pytest tests/test_config_data_dir.py -v`
Expected: FAIL — `s.sessions_dir` is still `project_root()/data/sessions` (passes by coincidence) but the env test fails (still points at project `data/`, not `tmp_path`). The seed test passes already.

> Note: only the `honors_env` test truly fails before the change; the other two pin current behavior so the refactor doesn't silently break dev.

- [ ] **Step 3: Write minimal implementation**

In `config.py`, add `import os` at top (after `from pathlib import Path`) and a helper below `project_root()`:

```python
def _runtime_data_root() -> Path:
    """运行时可写数据根目录。打包后由 Electron 经 MAESTRO_DATA_DIR 注入 (userData)；
    未设置时回退到项目内 data/ (CLI/dev 不变)。种子数据 (mock/knowledge) 不走此处。"""
    env = os.environ.get("MAESTRO_DATA_DIR")
    return Path(env) if env else project_root() / "data"
```

Replace the writable-path field defaults (leave `mock_data_dir` and `knowledge_dir` as-is):

```python
    # 用户上传的知识文档落盘目录 (运行时数据，与种子知识库分开，不入 git)
    knowledge_upload_dir: Path = Field(
        default_factory=lambda: _runtime_data_root() / "knowledge_uploads"
    )
    audit_log_file: Path | None = Field(
        default_factory=lambda: _runtime_data_root() / "logs" / "audit.jsonl"
    )
    sessions_dir: Path = Field(
        default_factory=lambda: _runtime_data_root() / "sessions"
    )
    # 技能包落盘目录 (SkillStore 索引 + 各技能包 SKILL.md 与附属文件，运行时数据，不入 git)
    skills_dir: Path = Field(default_factory=lambda: _runtime_data_root() / "skills")
    # Chroma 向量库持久化目录 (vector_backend=chroma 时使用，运行时数据，不入 git)
    chroma_dir: Path = Field(default_factory=lambda: _runtime_data_root() / "chroma")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd maestro && pytest tests/test_config_data_dir.py -v`
Expected: PASS (3 tests). Also run `pytest -q` to confirm no regressions in the wider suite (consumers create their own dirs — `SessionStore.__init__` does `mkdir`, `AuditLog.__init__` does `file_path.parent.mkdir`).

- [ ] **Step 5: Commit**

```bash
git add maestro/src/maestro/config.py maestro/tests/test_config_data_dir.py
git commit -m "feat(config): writable data dirs honor MAESTRO_DATA_DIR (desktop userData)"
```

---

## Task 2: Backend — `sidecar_entry.py` launcher

**Files:**
- Create: `maestro/src/maestro/sidecar_entry.py`
- Test: `maestro/tests/test_sidecar_entry.py` (new)

**Interfaces:**
- Produces: `maestro.sidecar_entry.resolve_bind() -> tuple[str, int]` and `main()`. `main()` runs `uvicorn.run(app, host="127.0.0.1", port=<env>, workers=1, reload=False)` where `app` is `maestro.main.app`. Plan 2 freezes this module with PyInstaller.

- [ ] **Step 1: Write the failing test**

```python
# maestro/tests/test_sidecar_entry.py
from maestro.sidecar_entry import resolve_bind


def test_resolve_bind_defaults(monkeypatch):
    monkeypatch.delenv("MAESTRO_BACKEND_PORT", raising=False)
    assert resolve_bind() == ("127.0.0.1", 8000)


def test_resolve_bind_reads_env(monkeypatch):
    monkeypatch.setenv("MAESTRO_BACKEND_PORT", "9123")
    assert resolve_bind() == ("127.0.0.1", 9123)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd maestro && pytest tests/test_sidecar_entry.py -v`
Expected: FAIL — `ModuleNotFoundError: maestro.sidecar_entry`.

- [ ] **Step 3: Write minimal implementation**

```python
# maestro/src/maestro/sidecar_entry.py
"""Electron 侧车入口：被 main.cjs 作为子进程拉起，从 env 读端口绑定 loopback。

打包后 (Plan 2) 由 PyInstaller 冻结为 MaestroBackend；本模块是其 entrypoint。
端口经 MAESTRO_BACKEND_PORT 注入 (Electron 动态挑选空闲端口)。
"""

import os

import uvicorn

from maestro.main import app


def resolve_bind() -> tuple[str, int]:
    """从 env 解析 (host, port)。仅绑 loopback，避免对外暴露。"""
    port = int(os.environ.get("MAESTRO_BACKEND_PORT", "8000"))
    return "127.0.0.1", port


def main() -> None:
    host, port = resolve_bind()
    uvicorn.run(app, host=host, port=port, workers=1, reload=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd maestro && pytest tests/test_sidecar_entry.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Manual boot check**

Run (one command, then probe, then kill):
```bash
cd maestro && \
MAESTRO_BACKEND_PORT=9123 .venv/bin/python -m maestro.sidecar_entry & \
sleep 3 && curl -s http://127.0.0.1:9123/health && \
kill %1
```
Expected: `{"status":"ok","llm_available":false}` (degraded, no key) then process killed.

- [ ] **Step 6: Commit**

```bash
git add maestro/src/maestro/sidecar_entry.py maestro/tests/test_sidecar_entry.py
git commit -m "feat(backend): sidecar_entry — uvicorn launcher for Electron spawn"
```

---

## Task 3: Frontend — `API_BASE` from `?bp=` query param

**Files:**
- Modify: `frontend/src/api/client.ts:4`
- Test: `frontend/src/api/client.test.ts` (new)

**Interfaces:**
- Produces: `API_BASE` (string) now resolves `http://127.0.0.1:<bp>` when the URL has `?bp=<port>`, else `import.meta.env.VITE_API_BASE_URL ?? '/api/v1'`. `streaming.ts` imports `API_BASE` from `client.ts`, so SSE is covered by the same change.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/api/client.test.ts
import { describe, expect, it, vi } from 'vitest';

describe('API_BASE resolution', () => {
  it('uses bp query param when present', async () => {
    vi.resetModules();
    window.history.replaceState({}, '', '/?bp=9123');
    const { API_BASE } = await import('./client');
    expect(API_BASE).toBe('http://127.0.0.1:9123');
  });

  it('falls back to /api/v1 when no bp and no VITE_API_BASE_URL', async () => {
    vi.resetModules();
    window.history.replaceState({}, '', '/');
    const { API_BASE } = await import('./client');
    expect(API_BASE).toBe('/api/v1');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/api/client.test.ts`
Expected: FAIL — `API_BASE` is `/api/v1` even with `?bp=9123` (current line 4 ignores query).

- [ ] **Step 3: Write minimal implementation**

Replace line 4 of `frontend/src/api/client.ts`:

```ts
/** API base URL + version prefix. Same-origin by default so MSW can intercept. */
function resolveApiBase(): string {
  // 打包后 Electron 经 URL 查询参数 bp 注入动态端口 (?bp=<port>)；
  // dev (Vite 代理) 与浏览器回落到 VITE_API_BASE_URL / /api/v1。
  if (typeof window !== 'undefined') {
    const bp = new URLSearchParams(window.location.search).get('bp');
    if (bp) return `http://127.0.0.1:${bp}`;
  }
  return import.meta.env.VITE_API_BASE_URL ?? '/api/v1';
}
export const API_BASE = resolveApiBase();
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/api/client.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/api/client.test.ts
git commit -m "feat(api): API_BASE resolves dynamic backend port from ?bp= query"
```

---

## Task 4: Electron — `backend-config.cjs` pure helpers

**Files:**
- Create: `frontend/electron/backend-config.cjs`
- Test: `frontend/electron/backend-config.test.cjs` (new)

**Interfaces:**
- Produces (CJS exports): `readProviders(userDataDir)`, `writeProviders(userDataDir, config)`, `upsertProvider(config, section, provider)`, `removeProvider(config, section, id)`, `setActive(config, section, id)`, `resolveActiveEnv(config) -> {LLM_BASE_URL?, LLM_API_KEY?, LLM_MODEL?, EMBED_BASE_URL?, EMBED_API_KEY?, EMBED_MODEL?}`, `pickFreePort() -> Promise<number>`, `DEFAULT_CONFIG`. `section` is `'llm' | 'embedding'`. Provider shape: `{id?, name, base_url, api_key, model}`.

- [ ] **Step 1: Write the failing test**

```js
// frontend/electron/backend-config.test.cjs
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const bc = require('./backend-config.cjs');

test('readProviders returns default when file missing', () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'bc-'));
  const cfg = bc.readProviders(d);
  assert.deepEqual(cfg.llm.providers, []);
  assert.equal(cfg.llm.active_id, null);
});

test('write → read round-trip preserves providers + active', () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'bc-'));
  const cfg = bc.DEFAULT_CONFIG;
  const p = bc.upsertProvider(cfg, 'llm', { name: 'DeepSeek', base_url: 'u', api_key: 'k', model: 'm' });
  bc.setActive(cfg, 'llm', p.id);
  bc.writeProviders(d, cfg);
  const read = bc.readProviders(d);
  assert.equal(read.llm.providers.length, 1);
  assert.equal(read.llm.active_id, p.id);
});

test('resolveActiveEnv maps active LLM provider to flat env', () => {
  const cfg = bc.DEFAULT_CONFIG;
  const p = bc.upsertProvider(cfg, 'llm', { name: 'D', base_url: 'bu', api_key: 'bk', model: 'bm' });
  bc.setActive(cfg, 'llm', p.id);
  const env = bc.resolveActiveEnv(cfg);
  assert.equal(env.LLM_BASE_URL, 'bu');
  assert.equal(env.LLM_API_KEY, 'bk');
  assert.equal(env.LLM_MODEL, 'bm');
  assert.equal(env.EMBED_MODEL, undefined);
});

test('resolveActiveEnv is empty when no active provider', () => {
  assert.deepEqual(bc.resolveActiveEnv(bc.DEFAULT_CONFIG), {});
});

test('removeProvider clears active_id when removing the active one', () => {
  const cfg = bc.DEFAULT_CONFIG;
  const p = bc.upsertProvider(cfg, 'embedding', { name: 'OAI', base_url: 'u', api_key: 'k', model: 'm' });
  bc.setActive(cfg, 'embedding', p.id);
  bc.removeProvider(cfg, 'embedding', p.id);
  assert.equal(cfg.embedding.providers.length, 0);
  assert.equal(cfg.embedding.active_id, null);
});

test('pickFreePort returns a positive integer', async () => {
  const port = await bc.pickFreePort();
  assert.ok(Number.isInteger(port) && port > 0);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && node --test electron/backend-config.test.cjs`
Expected: FAIL — `Cannot find module './backend-config.cjs'`.

- [ ] **Step 3: Write minimal implementation**

```js
// frontend/electron/backend-config.cjs
// Pure helpers (no `electron` import) so they are unit-testable with node:test.
// main.cjs requires this module for provider persistence + env resolution.
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const crypto = require('node:crypto');

const DEFAULT_CONFIG = {
  llm: { providers: [], active_id: null },
  embedding: { providers: [], active_id: null },
};

function providersPath(userDataDir) {
  return path.join(userDataDir, 'providers.json');
}

function readProviders(userDataDir) {
  const p = providersPath(userDataDir);
  if (!fs.existsSync(p)) return structuredClone(DEFAULT_CONFIG);
  try {
    const raw = JSON.parse(fs.readFileSync(p, 'utf-8'));
    return {
      llm: { providers: raw.llm?.providers ?? [], active_id: raw.llm?.active_id ?? null },
      embedding: { providers: raw.embedding?.providers ?? [], active_id: raw.embedding?.active_id ?? null },
    };
  } catch {
    return structuredClone(DEFAULT_CONFIG);
  }
}

function writeProviders(userDataDir, config) {
  fs.mkdirSync(userDataDir, { recursive: true });
  fs.writeFileSync(providersPath(userDataDir), JSON.stringify(config, null, 2), 'utf-8');
}

function _newId() {
  return crypto.randomBytes(6).toString('hex');
}

function upsertProvider(config, section, provider) {
  const list = config[section].providers;
  const id = provider.id || _newId();
  const next = { ...provider, id };
  const idx = list.findIndex((p) => p.id === id);
  if (idx >= 0) list[idx] = next;
  else list.push(next);
  return next;
}

function removeProvider(config, section, id) {
  config[section].providers = config[section].providers.filter((p) => p.id !== id);
  if (config[section].active_id === id) config[section].active_id = null;
}

function setActive(config, section, id) {
  config[section].active_id = id;
}

// Resolve the active LLM + embedding providers into flat LLM_*/EMBED_* env vars
// injected into the backend child process. No active provider → key absent (backend degraded).
function resolveActiveEnv(config) {
  const env = {};
  const llm = (config.llm.providers || []).find((p) => p.id === config.llm.active_id);
  if (llm) {
    env.LLM_BASE_URL = llm.base_url;
    env.LLM_API_KEY = llm.api_key;
    env.LLM_MODEL = llm.model;
  }
  const emb = (config.embedding.providers || []).find((p) => p.id === config.embedding.active_id);
  if (emb) {
    env.EMBED_BASE_URL = emb.base_url;
    env.EMBED_API_KEY = emb.api_key;
    env.EMBED_MODEL = emb.model;
  }
  return env;
}

// Pick a free TCP port on loopback (bind 0 then release for the backend to reuse).
function pickFreePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.unref();
    srv.on('error', reject);
    srv.listen(0, '127.0.0.1', () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

module.exports = {
  DEFAULT_CONFIG,
  providersPath,
  readProviders,
  writeProviders,
  upsertProvider,
  removeProvider,
  setActive,
  resolveActiveEnv,
  pickFreePort,
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && node --test electron/backend-config.test.cjs`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/electron/backend-config.cjs frontend/electron/backend-config.test.cjs
git commit -m "feat(electron): backend-config pure helpers (providers.json + env resolve + port pick)"
```

---

## Task 5: Electron — `main.cjs` sidecar lifecycle + `preload.cjs`

**Files:**
- Modify: `frontend/electron/main.cjs` (rewrite)
- Modify: `frontend/electron/preload.cjs`

**Interfaces:**
- Consumes: `backend-config.cjs` (`pickFreePort`, `readProviders`, `resolveActiveEnv`); `sidecar_entry` module (Task 2) in preview, frozen `MaestroBackend` exe when packaged.
- Produces: on launch, Electron spawns the backend child with env `{MAESTRO_BACKEND_PORT, MAESTRO_DATA_DIR=<userData>, ...LLM_*/EMBED_*}`, polls `/health` behind a splash window, then loads `dist/index.html?bp=<port>`. `electron:dev` (`MAESTRO_DEV_SERVER` not set, `!app.isPackaged`) is unchanged: loads `DEV_URL`, no spawn. Single-instance lock prevents duplicate backends; `before-quit` stops the child with SIGTERM → 2s → SIGKILL.

> Dev/preview/packaged detection:
> - `app.isPackaged` → packaged (Plan 2): load `dist` + spawn frozen exe.
> - `!app.isPackaged` && `process.env.MAESTRO_SIDECAR === '1'` → `electron:preview`: load `dist` + spawn venv python `-m maestro.sidecar_entry`.
> - `!app.isPackaged` && no `MAESTRO_SIDECAR` → `electron:dev`: load `DEV_URL`, no spawn (unchanged).

- [ ] **Step 1: Replace `main.cjs` with the sidecar lifecycle**

```js
// frontend/electron/main.cjs
// Electron main process. Runs the same React app as a cross-platform desktop
// shell AND lifecycle-manages the Python backend as a child process (sidecar).
//
// Modes (see Global Constraints):
//   - packaged            : load dist + spawn frozen MaestroBackend
//   - preview (MAESTRO_SIDECAR=1): load dist + spawn venv python -m sidecar_entry
//   - dev (electron:dev)  : load Vite DEV_URL, NO spawn (backend via ./restart.sh)
const { app, BrowserWindow, nativeTheme, shell, dialog, ipcMain } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const http = require('node:http');
const { spawn, execSync } = require('node:child_process');
const bc = require('./backend-config.cjs');

const isMac = process.platform === 'darwin';
const isSidecar = app.isPackaged || process.env.MAESTRO_SIDECAR === '1';
const isDevServer = !app.isPackaged && !isSidecar;
const DEV_URL = process.env.ELECTRON_RENDERER_URL || 'http://127.0.0.1:5173';

let backend = null; // { child, port }
let splash = null;
let quitting = false;

function userDataDir() {
  return app.getPath('userData');
}
function backendLogPath() {
  return path.join(userDataDir(), 'backend.log');
}

function backendBinary() {
  if (app.isPackaged) {
    const exe = process.platform === 'win32' ? 'MaestroBackend.exe' : 'MaestroBackend';
    return path.join(process.resourcesPath, 'backend', exe);
  }
  // preview: 仓库 venv 的 python 跑 sidecar_entry
  return process.platform === 'win32'
    ? path.join(__dirname, '..', '..', 'maestro', '.venv', 'Scripts', 'python.exe')
    : path.join(__dirname, '..', '..', 'maestro', '.venv', 'bin', 'python');
}

function backendArgs() {
  return app.isPackaged ? [] : ['-m', 'maestro.sidecar_entry'];
}

function buildBackendEnv(port) {
  const env = {
    ...process.env,
    MAESTRO_BACKEND_PORT: String(port),
    MAESTRO_DATA_DIR: userDataDir(),
  };
  // 把「当前生效」供应商解析为扁平 LLM_*/EMBED_* (后端零改动)
  const cfg = bc.readProviders(userDataDir());
  Object.assign(env, bc.resolveActiveEnv(cfg));
  return env;
}

function waitForHealth(port, timeoutMs) {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + timeoutMs;
    const tick = () => {
      const req = http.get(`http://127.0.0.1:${port}/health`, (res) => {
        res.resume();
        if (res.statusCode === 200) return resolve();
        if (Date.now() > deadline) return reject(new Error(`/health non-200 on ${port}`));
        setTimeout(tick, 200);
      });
      req.on('error', () => {
        if (Date.now() > deadline) return reject(new Error(`/health timeout on ${port}`));
        setTimeout(tick, 200);
      });
      req.setTimeout(500, () => req.destroy());
    };
    tick();
  });
}

async function startBackend() {
  fs.mkdirSync(userDataDir(), { recursive: true });
  const port = await bc.pickFreePort();
  const logStream = fs.createWriteStream(backendLogPath(), { flags: 'a' });
  const child = spawn(backendBinary(), backendArgs(), {
    env: buildBackendEnv(port),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  child.stdout.pipe(logStream);
  child.stderr.pipe(logStream);
  child.on('exit', () => {
    if (backend && backend.child === child && !quitting) {
      // 非预期退出：主流程会在 health 超时或后续操作中暴露
    }
  });
  backend = { child, port };
  await waitForHealth(port, 15000);
  return backend;
}

function killChild(child) {
  try {
    if (process.platform === 'win32') execSync(`taskkill /pid ${child.pid} /T /F`);
    else child.kill('SIGTERM');
  } catch { /* best effort */ }
}

function stopBackendAsync() {
  return new Promise((resolve) => {
    if (!backend) return resolve();
    const { child } = backend;
    backend = null;
    let done = false;
    const finish = () => { if (!done) { done = true; resolve(); } };
    child.once('exit', finish);
    killChild(child);
    // 2s 宽限后 SIGKILL
    setTimeout(() => {
      if (!done) {
        try { if (process.platform !== 'win32') child.kill('SIGKILL'); } catch { /* noop */ }
        finish();
      }
    }, 2000);
  });
}

function createSplash() {
  splash = new BrowserWindow({
    width: 360, height: 220, frame: false, resizable: false,
    transparent: false, backgroundColor: '#f5f5f7', show: true,
    webPreferences: { contextIsolation: true },
  });
  splash.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(
    `<body style="margin:0;font-family:-apple-system,system-ui,sans-serif;background:#f5f5f7;height:100vh;display:flex;align-items:center;justify-content:center;color:#1a1a1e;font-size:14px;">Maestro 正在准备…</body>`
  ));
}

function createWindow(port) {
  const win = new BrowserWindow({
    width: 1440, height: 900, minWidth: 1024, minHeight: 680,
    backgroundColor: nativeTheme.shouldUseDarkColors ? '#1a1a1e' : '#f5f5f7',
    title: 'Maestro', autoHideMenuBar: true,
    ...(isMac && { titleBarStyle: 'hiddenInset', trafficLightPosition: { x: 18, y: 16 } }),
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http')) { shell.openExternal(url); return { action: 'deny' }; }
    return { action: 'allow' };
  });

  if (isDevServer) {
    win.loadURL(DEV_URL);
    win.webContents.openDevTools({ mode: 'detach' });
  } else {
    win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'), { query: { bp: String(port) } });
  }
}

// 单实例锁：第二次启动只聚焦已有窗口，避免重复拉起后端
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    const wins = BrowserWindow.getAllWindows();
    if (wins.length) { if (wins[0].isMinimized()) wins[0].restore(); wins[0].focus(); }
  });

  app.whenReady().then(async () => {
    if (isSidecar) {
      createSplash();
      try {
        await startBackend();
      } catch (e) {
        splash?.destroy();
        dialog.showErrorBox('Maestro 启动失败', `后端未就绪: ${e.message}\n日志: ${backendLogPath()}`);
        app.quit();
        return;
      }
      splash?.destroy();
    }
    createWindow(backend?.port);
    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow(backend?.port);
    });
  });
}

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

// 优雅退出：SIGTERM → 2s → SIGKILL（见 stopBackendAsync）
app.on('before-quit', (e) => {
  if (quitting || !backend) return;
  e.preventDefault();
  quitting = true;
  stopBackendAsync().then(() => app.exit(0));
});
```

- [ ] **Step 2: Update `preload.cjs` (add `isElectron` stays; no providers bridge yet — added in Task 6)**

For Task 5 the preload is unchanged from current (it already exposes `isElectron` + `platform`). Confirm `frontend/electron/preload.cjs` still reads:

```js
const { contextBridge } = require('electron');
contextBridge.exposeInMainWorld('electronAPI', {
  isElectron: true,
  platform: process.platform,
});
```

(No edit needed in this task — Task 6 extends it.)

- [ ] **Step 3: Wire `electron:preview` to set `MAESTRO_SIDECAR=1`**

In `frontend/package.json`, change:
```jsonc
"electron:preview": "vite build --mode electron && electron .",
```
to:
```jsonc
"electron:preview": "vite build --mode electron && MAESTRO_SIDECAR=1 electron .",
```
> macOS/Linux dev: inline env works. Windows dev: use `cross-env MAESTRO_SIDECAR=1 electron .` (add `cross-env` to devDeps if needed).

- [ ] **Step 4: Manual end-to-end (this is the test for this task — main.cjs is Electron glue, not unit-testable)**

Precondition: backend venv exists at `maestro/.venv` and `./restart.sh stop` (so port 8000 is free / no conflicting backend).
```bash
cd frontend && npm run electron:preview
```
Expected: a splash window ("Maestro 正在准备…") appears briefly, then the main Maestro window loads and is usable (chat works in degraded mode). Verify:
- `tail -f ~/Library/Application\ Support/Maestro/backend.log` shows uvicorn startup logs (`Uvicorn running on http://127.0.0.1:<port>`).
- Quit (Cmd-Q) → no orphan `python`/`uvicorn` process in Activity Monitor.

If the window shows a connection error, check `backend.log` for import errors (e.g., a missing dep) and fix before proceeding.

- [ ] **Step 5: Commit**

```bash
git add frontend/electron/main.cjs frontend/package.json
git commit -m "feat(electron): sidecar lifecycle — spawn backend, health gate, splash, single-instance, clean shutdown"
```

---

## Task 6: Electron — providers IPC + respawn on change

**Files:**
- Modify: `frontend/electron/main.cjs` (append IPC + `restartBackend`)
- Modify: `frontend/electron/preload.cjs` (expose `providers` + `onBackendReconnecting`)

**Interfaces:**
- Produces: IPC channels `providers:get` → `readProviders(userDataDir)`; `providers:save(config)` → `writeProviders` + `restartBackend()` (stop child, spawn new with re-resolved env, reload all windows with new `?bp=`). Preload exposes `electronAPI.providers.{get,save}` and `electronAPI.onBackendReconnecting(cb)`.

- [ ] **Step 1: Append providers IPC + `restartBackend` to `main.cjs`**

Add near the other `ipcMain`/`app` setup (e.g., after `createWindow` definition, before the single-instance lock block):

```js
// 供应商配置 IPC：读写 providers.json，保存后按新 env 重启后端
ipcMain.handle('providers:get', () => bc.readProviders(userDataDir()));

ipcMain.handle('providers:save', async (_e, config) => {
  bc.writeProviders(userDataDir(), config);
  await restartBackend();
  return { ok: true };
});

async function restartBackend() {
  for (const w of BrowserWindow.getAllWindows()) w.webContents.send('backend:reconnecting');
  await stopBackendAsync();
  await startBackend();
  for (const w of BrowserWindow.getAllWindows()) {
    w.loadFile(path.join(__dirname, '..', 'dist', 'index.html'), {
      query: { bp: String(backend.port) },
    });
  }
}
```

> `restartBackend` is only reachable when `isSidecar` (the settings UI is hidden in dev — Task 8 gates on `electronAPI.isElectron`), so `loadFile` (not `DEV_URL`) is correct here.

- [ ] **Step 2: Expose the bridge in `preload.cjs`**

```js
// frontend/electron/preload.cjs
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  isElectron: true,
  platform: process.platform,
  providers: {
    get: () => ipcRenderer.invoke('providers:get'),
    save: (config) => ipcRenderer.invoke('providers:save', config),
  },
  onBackendReconnecting: (cb) => {
    const listener = () => cb();
    ipcRenderer.on('backend:reconnecting', listener);
    return () => ipcRenderer.removeListener('backend:reconnecting', listener);
  },
});
```

- [ ] **Step 3: Manual end-to-end (provider change → backend restart)**

```bash
cd frontend && npm run electron:preview
```
In the app: open left-bottom ⚙️ (after Task 8 wires the menu item) → add an LLM provider (real `base_url`/`api_key`/`model`) → "添加供应商". Expected: "应用中，后端重启…" briefly, the window reloads, and a real LLM chat now works (the orchestrator no longer degrades).

> This step depends on Task 8's menu item being present. If testing Task 6 in isolation before Task 8, call the IPC from DevTools instead: `await window.electronAPI.providers.save({llm:{providers:[{name:'D',base_url:'https://api.deepseek.com',api_key:'sk-…',model:'deepseek-chat'}],active_id:null},embedding:{providers:[],active_id:null}})` — wait, `active_id` must be the provider's id (assigned by upsert on save? No — `providers:save` writes verbatim, so set `active_id` to the id you passed). For an isolated test, give the provider an explicit `id:'p1'` and `active_id:'p1'`. Then verify the window reloads and `/health` (or a chat) shows `llm_available: true`.

- [ ] **Step 4: Commit**

```bash
git add frontend/electron/main.cjs frontend/electron/preload.cjs
git commit -m "feat(electron): providers IPC + respawn backend on config change"
```

---

## Task 7: Frontend — `SettingsModal` (provider CRUD)

**Files:**
- Create: `frontend/src/features/orchestrator/settings/SettingsModal.tsx`
- Test: `frontend/src/features/orchestrator/settings/SettingsModal.test.tsx`

**Interfaces:**
- Consumes: `window.electronAPI.providers.{get,save}` (Task 6). `window.electronAPI.onBackendReconnecting(cb)`.
- Produces: `<SettingsModal open onClose />` — two sections (LLM, Embedding), each with a provider list (set-active radio, delete) + an add form (name/base_url/api_key/model). Calls `save` on every mutation.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/features/orchestrator/settings/SettingsModal.test.tsx
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { SettingsModal } from './SettingsModal';

const mockProviders = { get: vi.fn(), save: vi.fn() };

beforeEach(() => {
  mockProviders.get.mockResolvedValue({
    llm: {
      providers: [{ id: 'p1', name: 'DeepSeek', base_url: 'u', api_key: 'k', model: 'deepseek-chat' }],
      active_id: 'p1',
    },
    embedding: { providers: [], active_id: null },
  });
  mockProviders.save.mockResolvedValue({ ok: true });
  (window as unknown as { electronAPI: unknown }).electronAPI = {
    providers: mockProviders,
    onBackendReconnecting: () => () => {},
  };
});

afterEach(cleanup);

describe('SettingsModal', () => {
  it('lists existing providers', async () => {
    render(<SettingsModal open onClose={() => {}} />);
    expect(await screen.findByText('DeepSeek')).toBeTruthy();
  });

  it('adds a provider via the LLM form', async () => {
    render(<SettingsModal open onClose={() => {}} />);
    await screen.findByText('DeepSeek');
    fireEvent.change(screen.getAllByPlaceholderText('名称')[0], { target: { value: 'OpenAI' } });
    fireEvent.change(screen.getAllByPlaceholderText('base_url')[0], { target: { value: 'https://api.openai.com/v1' } });
    fireEvent.change(screen.getAllByPlaceholderText('模型 model')[0], { target: { value: 'gpt-4o-mini' } });
    fireEvent.change(screen.getAllByPlaceholderText('api_key')[0], { target: { value: 'sk-x' } });
    fireEvent.click(screen.getAllByText('添加供应商')[0]);
    await waitFor(() => expect(mockProviders.save).toHaveBeenCalled());
    const saved = mockProviders.save.mock.calls[0][0];
    expect(saved.llm.providers.some((p: { name: string }) => p.name === 'OpenAI')).toBe(true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/features/orchestrator/settings/SettingsModal.test.tsx`
Expected: FAIL — `Cannot find module './SettingsModal'`.

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/src/features/orchestrator/settings/SettingsModal.tsx
import { useEffect, useState } from 'react';
import { Modal } from '@/components/ui/Modal';
import { Plus, Trash2, CircleDot } from 'lucide-react';

type SectionKey = 'llm' | 'embedding';

interface Provider {
  id?: string;
  name: string;
  base_url: string;
  api_key: string;
  model: string;
}

interface ProvidersConfig {
  llm: { providers: Provider[]; active_id: string | null };
  embedding: { providers: Provider[]; active_id: string | null };
}

const EMPTY: ProvidersConfig = {
  llm: { providers: [], active_id: null },
  embedding: { providers: [], active_id: null },
};

const EMPTY_FORM: Provider = { name: '', base_url: '', api_key: '', model: '' };

interface ElectronProviders {
  get: () => Promise<ProvidersConfig>;
  save: (config: ProvidersConfig) => Promise<{ ok: boolean }>;
}

function getElectronProviders(): ElectronProviders | undefined {
  return (window as unknown as { electronAPI?: { providers?: ElectronProviders } }).electronAPI
    ?.providers;
}

export function SettingsModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [cfg, setCfg] = useState<ProvidersConfig>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [drafts, setDrafts] = useState<Record<SectionKey, Provider>>({
    llm: { ...EMPTY_FORM },
    embedding: { ...EMPTY_FORM },
  });

  useEffect(() => {
    if (!open) return;
    getElectronProviders()?.get().then((c) => setCfg(c ?? EMPTY));
  }, [open]);

  // 后端重启时窗口会 reload，这里仅订阅以避免 lint 未用告警；reload 自然清理状态。
  useEffect(() => {
    if (!open) return;
    return (window as unknown as { electronAPI?: { onBackendReconnecting?: (cb: () => void) => () => void } })
      .electronAPI?.onBackendReconnecting?.(() => {});
  }, [open]);

  async function persist(next: ProvidersConfig) {
    setCfg(next);
    setSaving(true);
    try {
      await getElectronProviders()?.save(next);
    } finally {
      setSaving(false);
    }
  }

  function add(section: SectionKey) {
    const d = drafts[section];
    if (!d.name || !d.base_url || !d.model) return;
    const next: ProvidersConfig = structuredClone(cfg);
    next[section].providers.push({ ...d });
    setDrafts((s) => ({ ...s, [section]: { ...EMPTY_FORM } }));
    void persist(next);
  }

  function remove(section: SectionKey, id: string) {
    const next: ProvidersConfig = structuredClone(cfg);
    next[section].providers = next[section].providers.filter((p) => p.id !== id);
    if (next[section].active_id === id) next[section].active_id = null;
    void persist(next);
  }

  function activate(section: SectionKey, id: string) {
    const next: ProvidersConfig = structuredClone(cfg);
    next[section].active_id = id;
    void persist(next);
  }

  return (
    <Modal open={open} onClose={onClose} title="模型供应商" widthClassName="w-[560px]">
      <div className="space-y-5">
        {(['llm', 'embedding'] as SectionKey[]).map((sec) => (
          <section key={sec}>
            <h3 className="mb-2 text-body-sm font-semibold text-text-primary">
              {sec === 'llm' ? 'LLM 供应商' : 'Embedding 供应商'}
            </h3>
            <ul className="mb-3 space-y-1">
              {cfg[sec].providers.map((p) => {
                const active = cfg[sec].active_id === p.id;
                return (
                  <li
                    key={p.id}
                    className="flex items-center gap-2 rounded-md border border-border-subtle px-2 py-1.5"
                  >
                    <button
                      title={active ? '当前生效' : '设为生效'}
                      onClick={() => p.id && activate(sec, p.id)}
                      className={`grid h-5 w-5 place-items-center rounded-full ${
                        active ? 'text-accent-fg' : 'text-text-tertiary hover:text-text-secondary'
                      }`}
                    >
                      <CircleDot size={15} />
                    </button>
                    <span className="min-w-0 flex-1 truncate text-body-sm">{p.name}</span>
                    <span className="truncate font-mono text-[10px] text-text-tertiary">{p.model}</span>
                    <button
                      title="删除"
                      onClick={() => p.id && remove(sec, p.id)}
                      className="text-text-tertiary hover:text-text-secondary"
                    >
                      <Trash2 size={14} />
                    </button>
                  </li>
                );
              })}
              {cfg[sec].providers.length === 0 && (
                <li className="text-caption text-text-tertiary">尚未添加供应商（降级模式）</li>
              )}
            </ul>
            <ProviderForm
              draft={drafts[sec]}
              onChange={(d) => setDrafts((s) => ({ ...s, [sec]: d }))}
              onAdd={() => add(sec)}
            />
          </section>
        ))}
        {saving && <p className="text-caption text-text-tertiary">应用中，后端重启…</p>}
      </div>
    </Modal>
  );
}

function ProviderForm({
  draft,
  onChange,
  onAdd,
}: {
  draft: Provider;
  onChange: (d: Provider) => void;
  onAdd: () => void;
}) {
  const inputCls =
    'w-full rounded-md border border-border-default bg-surface-1 px-2 py-1 text-body-sm text-text-primary outline-none focus:ring-1 focus:ring-accent-border';
  return (
    <div className="space-y-2 rounded-md border border-border-subtle p-2">
      <div className="grid grid-cols-2 gap-2">
        <input
          className={inputCls}
          placeholder="名称"
          value={draft.name}
          onChange={(e) => onChange({ ...draft, name: e.target.value })}
        />
        <input
          className={inputCls}
          placeholder="模型 model"
          value={draft.model}
          onChange={(e) => onChange({ ...draft, model: e.target.value })}
        />
      </div>
      <input
        className={inputCls}
        placeholder="base_url"
        value={draft.base_url}
        onChange={(e) => onChange({ ...draft, base_url: e.target.value })}
      />
      <input
        className={inputCls}
        placeholder="api_key"
        type="password"
        value={draft.api_key}
        onChange={(e) => onChange({ ...draft, api_key: e.target.value })}
      />
      <button
        onClick={onAdd}
        className="inline-flex items-center gap-1 rounded-md border border-border-default bg-surface-1 px-2 py-1 text-body-sm font-semibold text-text-primary hover:bg-surface-3"
      >
        <Plus size={14} /> 添加供应商
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/features/orchestrator/settings/SettingsModal.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/orchestrator/settings/SettingsModal.tsx frontend/src/features/orchestrator/settings/SettingsModal.test.tsx
git commit -m "feat(settings): SettingsModal — multi-provider CRUD (LLM + Embedding)"
```

---

## Task 8: Frontend — Sidebar settings menu item (gated on Electron)

**Files:**
- Modify: `frontend/src/components/layout/Sidebar.tsx`
- Test: `frontend/src/components/layout/Sidebar.test.tsx` (new)

**Interfaces:**
- Consumes: `<SettingsModal>` (Task 7), `window.electronAPI.isElectron` (preload).
- Produces: a "模型" group in the existing settings Popover with item "LLM / Embedding 供应商…" that opens `<SettingsModal>`. The item + modal render only when `electronAPI.isElectron` (hidden in browser dev, where provider config isn't applicable).

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/layout/Sidebar.test.tsx
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, fireEvent } from '@testing-library/react';
import { Sidebar } from './Sidebar';

const baseProps = {
  appName: 'Maestro', user: 'u', role: 'r', conversations: [], activeId: '',
  onSelect: () => {}, onNewConversation: () => {}, onRenameSession: () => {},
  onDeleteSession: () => {}, onCollapse: () => {}, theme: 'light' as const, onSetTheme: () => {},
};

function setElectron(on: boolean) {
  const w = window as unknown as { electronAPI?: unknown };
  if (on) w.electronAPI = { isElectron: true, providers: { get: () => Promise.resolve(undefined), save: () => Promise.resolve({ ok: true }) }, onBackendReconnecting: () => () => {} };
  else delete w.electronAPI;
}

afterEach(cleanup);

describe('Sidebar settings menu', () => {
  it('shows the provider menu item in Electron', () => {
    setElectron(true);
    render(<Sidebar {...baseProps} />);
    fireEvent.click(screen.getByTitle('设置'));
    expect(screen.queryByText('LLM / Embedding 供应商…')).toBeTruthy();
  });

  it('hides the provider menu item in browser dev', () => {
    setElectron(false);
    render(<Sidebar {...baseProps} />);
    fireEvent.click(screen.getByTitle('设置'));
    expect(screen.queryByText('LLM / Embedding 供应商…')).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/layout/Sidebar.test.tsx`
Expected: FAIL — no "LLM / Embedding 供应商…" item (the Popover only has "外观").

- [ ] **Step 3: Wire the menu item + modal into `Sidebar.tsx`**

At the top of `Sidebar.tsx`, add the import and an `isElectron` helper:

```tsx
import { SettingsModal } from '@/features/orchestrator/settings/SettingsModal';

const isElectron =
  typeof window !== 'undefined' &&
  (window as unknown as { electronAPI?: { isElectron?: boolean } }).electronAPI?.isElectron === true;
```

Add a `providersOpen` state next to `settingsOpen`:

```tsx
const [settingsOpen, setSettingsOpen] = useState(false);
const [providersOpen, setProvidersOpen] = useState(false);
```

Inside the settings `Popover` (after the theme items block, still inside `{settingsOpen && (...)}`), add the gated "模型" group — insert before the closing `</Popover>` of the appearance popover:

```tsx
              {isElectron && (
                <>
                  <PopoverLabel>模型</PopoverLabel>
                  <PopoverItem
                    onClick={() => {
                      setSettingsOpen(false);
                      setProvidersOpen(true);
                    }}
                  >
                    LLM / Embedding 供应商…
                  </PopoverItem>
                </>
              )}
```

Finally, render the modal once at the end of the returned `<aside>` (just before `</aside>`):

```tsx
      {isElectron && <SettingsModal open={providersOpen} onClose={() => setProvidersOpen(false)} />}
```

> The Popover/PopoverItem/PopoverLabel imports already exist in `Sidebar.tsx`. Place the "模型" block inside the existing `{settingsOpen && (<Popover>…</Popover>)}` so it appears in the same popover.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/layout/Sidebar.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/layout/Sidebar.tsx frontend/src/components/layout/Sidebar.test.tsx
git commit -m "feat(sidebar): add LLM/Embedding providers menu item (Electron-gated)"
```

---

## Task 9: Wire-up — `test:electron` script + final Plan-1 e2e checklist

**Files:**
- Modify: `frontend/package.json` (add `test:electron`)
- Modify: `maestro/README.md` (note the local desktop test path) — optional, only if a relevant section exists

**Interfaces:**
- Produces: `npm run test:electron` runs the CJS unit tests; the Plan-1 acceptance checklist (G2/G3/G4/G5 local) is runnable via `npm run electron:preview`.

- [ ] **Step 1: Add the `test:electron` script**

In `frontend/package.json` `scripts`, add:
```jsonc
"test:electron": "node --test electron/*.test.cjs",
```

- [ ] **Step 2: Run the full test suite (Plan 1 has no code change here, just verification)**

```bash
cd frontend && npm test && npm run test:electron
cd ../maestro && pytest -q
```
Expected: all green (vitest + node:test + pytest). `npm run lint` should also pass — run `cd frontend && npm run lint` and fix any lint errors your changes introduced (unused imports, etc.).

- [ ] **Step 3: Plan-1 acceptance checklist (manual, on the dev Mac)**

Precondition: `./restart.sh stop` (no backend on :8000). Then:
```bash
cd frontend && npm run electron:preview
```
- **G2 (launch):** splash → main window → usable. `~/Library/Application Support/Maestro/backend.log` shows uvicorn on a dynamic port.
- **G3 (provider config):** left-bottom ⚙️ → "LLM / Embedding 供应商…" → add a real LLM provider (e.g. DeepSeek `base_url`/`api_key`/`model`) → "添加供应商" → set it active (CircleDot). Window reloads; a real LLM chat now succeeds (no longer degraded). Add an embedding provider → embedding route layer enables.
- **G4 (persistence):** create a session + upload a knowledge doc → quit → relaunch `electron:preview` → session + doc are still present in `~/Library/Application Support/Maestro/` (`sessions/`, `knowledge_uploads/`, `chroma/`, `providers.json`).
- **G5 (clean exit):** Cmd-Q → Activity Monitor shows no orphan `python`/`uvicorn`/`MaestroBackend` process.

- [ ] **Step 4: Commit**

```bash
git add frontend/package.json
git commit -m "chore(electron): add test:electron script for CJS unit tests"
```

---

## Plan 1 Self-Review (against spec §3, §4)

- **Spec coverage:** §3.1 layout — Task 5 `process.resourcesPath` + `backendBinary()` (packaged branch) covers it (full `extraResources` wiring is Plan 2). §3.2 port handshake — Tasks 2, 3, 5 (`MAESTRO_BACKEND_PORT`, `pickFreePort`, `?bp=`, `API_BASE`). §3.3 readiness+splash — Task 5 (`waitForHealth`, `createSplash`). §3.4 single-instance + shutdown — Task 5 (`requestSingleInstanceLock`, `stopBackendAsync` SIGTERM→SIGKILL). §3.5 change surface — config.py (T1), preload (T6), api/index.ts→client.ts (T3), main.cjs (T5/T6); sidecar_entry instead of a `config.py` port field (YAGNI — port read in sidecar_entry; spec §3.5 listed config.py but the intent, "port from env + bind loopback," is satisfied in sidecar_entry). §4.1 userData — T1. §4.2 left-bottom menu item — T8. §4.3 `providers.json` model — T4. §4.4 backend LLM/Embedding zero-change — T4 `resolveActiveEnv` + T6 spawn env (no `.env`). §4.5 first-run degraded hint — T7 shows "降级模式" placeholder; the one-time toast is a minor UX nicety deferred (degraded mode already visible). §4.6 v1 plaintext — T4 writes JSON plaintext; safeStorage is Plan-2/后续. §4.7 change surface — all hit.
- **Deviation noted:** spec §3.2 said preload exposes `backendBaseUrl`; the plan passes the port via `?bp=` URL query and resolves `API_BASE` in `client.ts` instead — deterministic at module-load (no env-propagation race). Intent (renderer learns dynamic port) preserved.
- **Type consistency:** `ProvidersConfig` / `Provider` shapes match across `backend-config.cjs` (CJS, untyped), `preload.cjs` (IPC passes through), and `SettingsModal.tsx` (TS). `SectionKey = 'llm' | 'embedding'` matches `bc` `section` arg. IPC channel names (`providers:get`/`providers:save`/`backend:reconnecting`) match between `main.cjs` and `preload.cjs`.
- **Scope:** Plan 1 produces a working local desktop app (launches + manages backend + provider config), testable via `electron:preview`. Plan 2 (freeze/package/CI/signing) follows.

## Plan 2 (follow-up, not in this document)

PyInstaller `onefolder` spec (`--collect-all ortools/chromadb/onnxruntime`) → `MaestroBackend` exe; electron-builder `extraResources` + NSIS (`oneClick:false`/`allowToChangeInstallationDirectory:true`/`perMachine:true`); `scripts/smoke_backend.{sh,ps1}` (G1); GitHub Actions (`build-mac-arm64`/`build-win-x64`); macOS deep-sign + notarize; Windows OV sign. Depends on Plan 1.
