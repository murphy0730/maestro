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
  const cfg = structuredClone(bc.DEFAULT_CONFIG);
  const p = bc.upsertProvider(cfg, 'llm', { name: 'DeepSeek', base_url: 'u', api_key: 'k', model: 'm' });
  bc.setActive(cfg, 'llm', p.id);
  bc.writeProviders(d, cfg);
  const read = bc.readProviders(d);
  assert.equal(read.llm.providers.length, 1);
  assert.equal(read.llm.active_id, p.id);
});

test('resolveActiveEnv maps active LLM provider to flat env', () => {
  const cfg = structuredClone(bc.DEFAULT_CONFIG);
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
  const cfg = structuredClone(bc.DEFAULT_CONFIG);
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
