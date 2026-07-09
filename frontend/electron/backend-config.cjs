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

// 从 settings.json 的 model_providers 解析「已启用」供应商为 flat env。
// settings.json 是设置弹框的单一数据源 (经 PUT /models 写入)，与弹框展示完全联动。
function readModelProviders(userDataDir) {
  const p = path.join(userDataDir, 'settings.json');
  if (!fs.existsSync(p)) return null;
  try {
    const raw = JSON.parse(fs.readFileSync(p, 'utf-8'));
    return raw.model_providers ?? null;
  } catch {
    return null;
  }
}

function resolveActiveEnvFromSettings(userDataDir) {
  const mp = readModelProviders(userDataDir);
  if (!mp) return null;
  const env = {};
  const llm = (mp.llm?.providers || []).find((p) => p.id === mp.llm?.active_id);
  if (llm) {
    env.LLM_BASE_URL = llm.base_url;
    env.LLM_API_KEY = llm.api_key;
    env.LLM_MODEL = llm.model;
  }
  const emb = (mp.embedding?.providers || []).find((p) => p.id === mp.embedding?.active_id);
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
  resolveActiveEnvFromSettings,
  pickFreePort,
};
