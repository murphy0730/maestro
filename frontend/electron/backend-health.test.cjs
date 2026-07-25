const test = require('node:test');
const assert = require('node:assert');
const { EventEmitter } = require('node:events');
const { backendReady } = require('./backend-health.cjs');

function fakeHttp(statuses) {
  return {
    get(url, callback) {
      const request = new EventEmitter();
      request.setTimeout = () => request;
      request.destroy = () => undefined;
      queueMicrotask(() => {
        const path = new URL(url).pathname;
        const response = new EventEmitter();
        response.statusCode = statuses[path] ?? 0;
        response.resume = () => undefined;
        callback(response);
      });
      return request;
    },
  };
}

test('accepts the canonical health endpoint when a host provides it', async () => {
  assert.equal(await backendReady(8000, fakeHttp({ '/health': 200 })), true);
});

test('falls back to the unified Runtime sessions endpoint when /health is absent', async () => {
  assert.equal(await backendReady(8000, fakeHttp({ '/health': 404, '/sessions': 200 })), true);
});

test('does not report readiness when neither endpoint responds successfully', async () => {
  assert.equal(await backendReady(8000, fakeHttp({ '/health': 404, '/sessions': 503 })), false);
});
