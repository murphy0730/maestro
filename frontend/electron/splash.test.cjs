const test = require('node:test');
const assert = require('node:assert');
const { splashHtml } = require('./splash.cjs');

test('Electron splash renders the deep-field Maestro brand and progress state', () => {
  const html = splashHtml();
  assert.match(html, /MAESTRO/);
  assert.match(html, /正在准备运行时/);
  assert.match(html, /#04060D/i);
  assert.match(html, /prefers-reduced-motion/);
});
