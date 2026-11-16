'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../rio_pey_codi/static');
const appSource = fs.readFileSync(process.argv[2] || path.join(root, 'app.js'), 'utf8');
const shellSource = fs.readFileSync(process.argv[3] || path.join(root, 'unificada/shell.js'), 'utf8');
const callStart = appSource.indexOf('async function call(');
const callEnd = appSource.indexOf('\nfunction form(', callStart);
assert(callStart >= 0 && callEnd > callStart);
const callSource = appSource.slice(callStart, callEnd);

function clock() {
  const timers = [];
  return {
    timers,
    setTimeout(fn, ms) { const timer = {fn, ms, active:true}; timers.push(timer); return timer; },
    clearTimeout(timer) { if (timer) timer.active = false; },
    expire() { for (const timer of timers) if (timer.active) { timer.active = false; timer.fn(); } },
  };
}
const tick = () => new Promise(resolve => setImmediate(resolve));
async function outcome(promise) {
  return Promise.race([
    promise.then(value => ({state:'resolved', value}), error => ({state:'rejected', error})),
    tick().then(() => ({state:'pending'})),
  ]);
}
function waitingForAbort(signal) {
  return new Promise((_resolve, reject) => {
    if (!signal) return;
    if (signal.aborted) reject(signal.reason);
    else signal.addEventListener('abort', () => reject(signal.reason), {once:true});
  });
}
function api(fetch, timer = clock()) {
  const context = vm.createContext({csrf:'fixture-csrf', fetch, AbortController,
    setTimeout:timer.setTimeout, clearTimeout:timer.clearTimeout});
  vm.runInContext(callSource, context);
  return {context, timer, request:(url, options) => context.call(url, options)};
}

(async () => {
  for (const method of ['GET', 'POST']) {
    let calls = 0;
    const harness = api((_url, options) => { calls++; return waitingForAbort(options.signal); });
    const pending = harness.request('/v1/merchants/test/pey-settings', {method, write:method === 'POST'});
    harness.timer.expire();
    const result = await outcome(pending);
    assert.equal(result.state, 'rejected', `${method}: unresponsive server must stop waiting`);
    assert.equal(result.error.name, 'AbortError');
    assert.equal(result.error.code, 'REQUEST_TIMEOUT');
    assert.match(result.error.message, method === 'POST' ? /Consulta el estado antes de repetir/ : /Intenta consultar de nuevo/);
    assert.equal(calls, 1, 'A timeout must never repeat a request automatically');
    assert.equal(harness.timer.timers.length, 1);
    assert.equal(harness.timer.timers[0].ms, 15000);
  }

  {
    let captured;
    const harness = api(async (_url, options) => {
      captured = options;
      return {ok:true, json:async () => ({status:'saved'})};
    });
    const result = await harness.request('/settings', {method:'PUT', body:{value:'fixture'}, write:true});
    assert.equal(result.status, 'saved');
    assert.equal(captured.headers['X-CSRF-Token'], 'fixture-csrf');
    assert.equal(captured.headers['Content-Type'], 'application/json');
    assert.equal(captured.body, '{"value":"fixture"}');
    assert(harness.timer.timers.every(timer => !timer.active), 'Successful response clears deadline');
  }

  {
    const harness = api(async (_url, options) => ({ok:true, json:() => waitingForAbort(options.signal)}));
    const pending = harness.request('/slow-body');
    await tick();
    harness.timer.expire();
    const result = await outcome(pending);
    assert.equal(result.state, 'rejected');
    assert.equal(result.error.code, 'REQUEST_TIMEOUT', 'Deadline covers a stalled response body');
  }

  {
    const controller = new AbortController();
    let captured;
    const harness = api((_url, options) => { captured = options; return waitingForAbort(options.signal); });
    const pending = harness.request('/checkout', {signal:controller.signal});
    assert.equal(captured.signal, controller.signal);
    assert.equal(harness.timer.timers.length, 0, 'Caller owns its explicit checkout deadline');
    controller.abort();
    const result = await outcome(pending);
    assert.equal(result.state, 'rejected');
    assert.equal(result.error, controller.signal.reason);
  }

  {
    const harness = api(async () => ({ok:false, status:409,
      json:async () => ({detail:'Already registered', code:'ORDER_CONFLICT'})}));
    const result = await outcome(harness.request('/checkout'));
    assert.equal(result.state, 'rejected');
    assert.equal(result.error.status, 409);
    assert.equal(result.error.code, 'ORDER_CONFLICT');
    assert(harness.timer.timers.every(timer => !timer.active));
  }

  function landing(fetch) {
    const ids = Object.fromEntries(['moduleSection','entryStatus','entryActions','sessionLabel']
      .map(id => [id, {hidden:id === 'moduleSection', textContent:id === 'entryStatus' ? 'Comprobando sesión…' : ''}]));
    const timer = clock();
    const context = vm.createContext({document:{getElementById:id => ids[id], querySelectorAll:() => []},
      fetch, AbortController, setTimeout:timer.setTimeout, clearTimeout:timer.clearTimeout});
    vm.runInContext(shellSource, context);
    return {ids, timer};
  }
  for (const slowBody of [false, true]) {
    const harness = landing((_url, options) => slowBody
      ? Promise.resolve({ok:true, status:200, json:() => waitingForAbort(options.signal)})
      : waitingForAbort(options.signal));
    await tick();
    harness.timer.expire();
    await tick();
    assert.equal(harness.ids.moduleSection.hidden, true);
    assert.equal(harness.ids.entryActions.hidden, false);
    assert.match(harness.ids.entryStatus.textContent, /tiempo/i, 'Session lookup must finish with a useful timeout message');
  }
  {
    const harness = landing(async () => ({ok:true, status:200, json:async () => ({id:'fixture-user'})}));
    await tick();
    assert.equal(harness.ids.moduleSection.hidden, false);
    assert.equal(harness.ids.entryActions.hidden, true);
    assert(harness.timer.timers.every(timer => !timer.active), 'Session success clears deadline');
  }
  console.log('REQUEST_TIMEOUT_UI_OK');
})().catch(error => { console.error(error); process.exitCode = 1; });
