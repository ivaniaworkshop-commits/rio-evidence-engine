const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../rio_pey_codi/static/app.js'), 'utf8')
  .replace(/\nboot\(\);\s*$/, '\n');
const html = fs.readFileSync(path.join(__dirname, '../rio_pey_codi/static/index.html'), 'utf8');
assert.match(html, /id="signup-email"[^>]*type="text"[^>]*inputmode="email"[^>]*aria-describedby="signup-email-help"/);
assert.match(html, /<button type="button"[^>]*id="resend-verification"/);
const elements = new Map();
function get(id) {
  if (!elements.has(id)) elements.set(id, {
    listeners: {}, value: '', disabled: false, textContent: '',
    addEventListener(event, fn) { this.listeners[event] = fn; },
    reportValidity() { return Boolean(this.value); },
  });
  return elements.get(id);
}

(async () => {
  let requests = [], release;
  const context = vm.createContext({
    document: {getElementById: get},
    FormData: class { constructor(form) { this.data = form.data; } entries() { return Object.entries(this.data); } },
    fetch: async (url, opts) => {
      requests.push({url, opts});
      if (JSON.parse(opts.body).email === 'not-an-email') {
        return {ok: false, status: 422, json: async () => ({detail: []})};
      }
      if (JSON.parse(opts.body).email === 'straße@example.org') {
        return {ok: false, status: 422,
          json: async () => ({detail: 'Esta dirección cambiaría al guardarse. Usa por ahora otro correo.'})};
      }
      await new Promise(resolve => { release = resolve; });
      return {ok: true, status: 200, json: async () => ({status: 'IF_ELIGIBLE_EMAIL_SENT'})};
    },
    URLSearchParams, AbortController, setTimeout, clearTimeout,
  });
  vm.runInContext(source, context);
  const button = get('resend-verification');
  assert.equal(typeof button.listeners.click, 'function');
  await button.listeners.click();
  assert.equal(requests.length, 0, 'an empty address must not be submitted');
  get('signup-email').value = 'usuario.ñ@example.org';
  const pending = button.listeners.click();
  assert.equal(button.disabled, true);
  await button.listeners.click();
  assert.equal(requests.length, 1, 'a pending request must not be duplicated');
  assert.equal(requests[0].url, '/v1/auth/resend-verification');
  assert.equal(requests[0].opts.method, 'POST');
  assert.equal(JSON.parse(requests[0].opts.body).email, 'usuario.ñ@example.org');
  release();
  await pending;
  assert.equal(button.disabled, false);
  assert.match(get('notice').textContent, /Si existe una cuenta pendiente/);
  assert.match(get('notice').textContent, /intentaremos enviar/);
  get('signup-email').value = 'not-an-email';
  await button.listeners.click();
  assert.equal(get('notice').textContent, 'Revisa la dirección de correo.');
  assert.equal(button.disabled, false);
  get('signup').data = {email: 'straße@example.org', business_name: 'Synthetic', password: 'synthetic'};
  await get('signup').listeners.submit({preventDefault() {}, target: get('signup')});
  assert.equal(get('notice').textContent, 'Esta dirección cambiaría al guardarse. Usa por ahora otro correo.');
  console.log('SIGNUP_EMAIL_UI_OK');
})().catch(error => {console.error(error); process.exitCode = 1;});
