const http = require('node:http');

function probe(port, path, httpModule = http) {
  return new Promise((resolve) => {
    const req = httpModule.get(`http://127.0.0.1:${port}${path}`, (res) => {
      res.resume();
      resolve(res.statusCode ?? 0);
    });
    req.on('error', () => resolve(0));
    req.setTimeout(500, () => req.destroy());
  });
}

/**
 * The unified Runtime currently exposes no /health route. Prefer it when a
 * host adds one, but accept a successful read-only /sessions probe as the
 * authoritative readiness signal for the checked-in backend.
 */
async function backendReady(port, httpModule = http) {
  const health = await probe(port, '/health', httpModule);
  if (health >= 200 && health < 300) return true;
  const sessions = await probe(port, '/sessions', httpModule);
  return sessions >= 200 && sessions < 300;
}

async function waitForBackend(port, timeoutMs, httpModule = http) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() <= deadline) {
    if (await backendReady(port, httpModule)) return;
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`Runtime readiness timeout on ${port} (/health and /sessions)`);
}

module.exports = { backendReady, waitForBackend };
