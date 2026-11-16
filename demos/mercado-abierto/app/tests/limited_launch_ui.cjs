const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../rio_pey_codi/static/app.js'), 'utf8')
  .replace(/\nboot\(\);\s*$/, '\n');
const html = fs.readFileSync(path.join(__dirname, '../rio_pey_codi/static/index.html'), 'utf8');
assert.match(html, /id="signup-submit"[^>]*disabled/);
assert.match(html, /id="resend-verification"[^>]*disabled/);
assert.match(html, /id="reset-request"[^>]*disabled/);
assert.match(html, /id="login-submit"[^>]*disabled/);
const elements = new Map();
function get(id) {
  if (!elements.has(id)) elements.set(id, {
    listeners: {}, value: '', hidden: false, disabled: false, textContent: '',
    button: {disabled: false}, addEventListener(name, fn) { this.listeners[name] = fn; },
    querySelector() { return this.button; },
  });
  return elements.get(id);
}
(async () => {
  const reply = (status, body) => ({ok: status >= 200 && status < 300, status, json: async () => body});
  const context = vm.createContext({
    document: {getElementById: get}, location: {hash: '', search: '', pathname: '/'},
    history: {replaceState() {}}, URLSearchParams, AbortController, setTimeout, clearTimeout,
    fetch: async url => url === '/public-status'
      ? reply(200, {mode: 'DEMO', launch_mode: 'LIMITED', access_enabled: false, registration_enabled: false,
                    payment_requests_enabled: false})
      : reply(401, {detail: 'Sign in required'}),
  });
  vm.runInContext(source, context);
  await vm.runInContext('boot()', context);
  assert.equal(get('signup-submit').disabled, true);
  assert.equal(get('login-submit').disabled, true);
  assert.equal(get('resend-verification').disabled, true);
  assert.equal(get('reset-request').disabled, true);
  assert.equal(get('charge').button.disabled, true);
  assert.match(get('launch-status').textContent, /registro.*temporalmente/i);
  assert.match(get('launch-status').textContent, /cobros.*desactivados/i);
  assert.match(get('launch-status').textContent, /acceso.*temporalmente/i);
  console.log('LIMITED_LAUNCH_UI_OK');
})().catch(error => {console.error(error); process.exitCode = 1;});
