const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');

const merchant = 'a'.repeat(32);
const user = 'b'.repeat(32);
const source = fs.readFileSync(path.join(__dirname, '../rio_pey_codi/static/app.js'), 'utf8')
  .replace(/\nboot\(\);\s*$/, '\n');

class Element {
  constructor() {
    this.listeners = {};
    this.button = {disabled:false};
    this.value = '';
    this.hidden = false;
    this.textContent = '';
    this.data = {};
    this.children = [];
    this.elements = {namedItem: name => ({
      get value() { return this.owner.data[name]; },
      set value(value) { this.owner.data[name] = value; },
      owner: this,
    })};
  }
  // Native HTMLSelectElement always exposes a selectedOptions collection.
  get selectedOptions() { return []; }
  scrollIntoView() {}
  removeAttribute(name) { delete this[name]; }
  addEventListener(name, listener) { this.listeners[name] = listener; }
  querySelector() { return this.button; }
  replaceChildren() { this.children = []; }
  append(child) { this.children.push(child); }
  add() {}
  focus() {}
}

function reply(status, body) {
  return {ok:status >= 200 && status < 300, status, json:async () => body};
}

function page(shared, opts = {}) {
  const elements = new Map();
  const get = id => {
    if (!elements.has(id)) elements.set(id, new Element());
    return elements.get(id);
  };
  const context = vm.createContext({
    window:{dispatchEvent(){},confirm(){return false}}, Event:class {constructor(type){this.type=type}},
    document:{getElementById:get, createElement:() => new Element()},
    location:{hash:'', search:'', pathname:'/'},
    history:{replaceState() {}},
    FormData:class { constructor(element) { this.data=element.data; } entries() { return Object.entries(this.data); } },
    localStorage:{
      getItem:key => { if (opts.readFails) throw Error('storage blocked'); return shared.storage.get(key) ?? null; },
      setItem:(key, value) => {
        if (opts.storageFails) throw Error('storage blocked');
        shared.storage.set(key, opts.storageMismatch ? 'invalid' : value);
      },
      removeItem:key => shared.storage.delete(key),
    },
    navigator:opts.noLocks ? {} : {locks:{request:async (name, _options, callback) => {
      if (shared.locks.has(name)) return callback(null);
      shared.locks.add(name);
      try { return await callback({name}); } finally { shared.locks.delete(name); }
    }}},
    crypto:{
      subtle:webcrypto.subtle,
      randomUUID:() => `00000000-0000-4000-8000-${String(++shared.ids).padStart(12, '0')}`,
      getRandomValues:values => { values[0] = ++shared.random; return values; },
    },
    fetch:async (url, options = {}) => {
      if (url.endsWith('/checkout-history')) return reply(200, {intents:opts.includeHistory && shared.intent ? [shared.intent] : []});
      if (url.includes('/checkout-unresolved')) return reply(200, {intents:[], next_cursor:null});
      if (url.includes('/checkout-orders/')) {
        return shared.intent ? reply(200, {intent:shared.intent, bank_payment_confirmed:false}) : reply(404, {detail:'Not found'});
      }
      assert.equal(url, '/v1/checkout/qr');
      const body = JSON.parse(options.body);
      shared.requests.push(body);
      if (shared.firstRequest) {
        shared.firstRequest = false;
        assert.equal(shared.storage.size, 1, 'order identity must be saved before network');
        if (opts.failBeforeProvider) throw Error('network unavailable');
        shared.intent = {id:'f'.repeat(32), merchant_id:merchant, order_id:body.order_id,
          numref:body.numref, concept:body.concept, amount_minor:body.amount_minor,
          expiration_s:600, status:'PROVIDER_UNCERTAIN', qr_display:null, expired:false};
        shared.providerCalls += 1;
        if (opts.holdFirst) await new Promise(resolve => { shared.release = resolve; });
        return reply(502, {detail:'Provider status uncertain'});
      }
      if (!shared.intent) {
        shared.providerCalls += 1;
        shared.intent = {id:'f'.repeat(32), merchant_id:merchant, order_id:body.order_id,
          numref:body.numref, concept:body.concept, amount_minor:body.amount_minor,
          expiration_s:600, status:'QR_ISSUED', qr_display:'synthetic', expired:false};
      }
      const intent = opts.tamperResponse ? {...shared.intent, amount_minor:1} : shared.intent;
      return reply(201, {status:'REPLAY_NO_PROVIDER_RETRY', intent});
    },
    Uint32Array, URLSearchParams, Blob, URL, TextEncoder, AbortController,
    setTimeout, clearTimeout,
  });
  vm.runInContext(source, context);
  vm.runInContext(`currentMerchant = '${merchant}'; csrf = 'synthetic'; if (typeof currentUserId !== 'undefined') currentUserId = '${user}'; paymentRequestsEnabled = true; merchantRoles.set('${merchant}', 'cashier');`, context);
  get('merchant').value = merchant;
  get('charge').data = {amount:'150.00', concept:'Pedido privado'};
  return {
    get,
    restore:() => vm.runInContext('selectMerchant()', context),
    submit:() => get('charge').listeners.submit({preventDefault() {}, currentTarget:get('charge')}),
    newOrder:() => get('new-order').listeners.click(),
  };
}

function state() {
  return {storage:new Map(), locks:new Set(), ids:0, random:12345, requests:[], providerCalls:0, firstRequest:true, intent:null};
}

(async () => {
  const shared = state();
  const first = page(shared);
  await first.submit();
  assert.equal(shared.requests.length, 1);
  assert.equal(shared.storage.size, 1, 'order identity must survive a reload');
  assert.equal(shared.providerCalls, 1);
  const saved = [...shared.storage.values()][0];
  assert(!saved.includes('Pedido privado'));
  assert(!saved.includes('150.00'));

  const reloaded = page(shared);
  await reloaded.restore();
  reloaded.get('charge').data.amount = '151.00';
  await reloaded.submit();
  assert.equal(shared.requests.length, 1, 'editing an uncertain order must not send another request');
  reloaded.get('charge').data.amount = '150';
  await reloaded.submit();
  assert.equal(shared.requests.length, 2);
  assert.equal(shared.requests[1].order_id, shared.requests[0].order_id);
  assert.equal(shared.requests[1].numref, shared.requests[0].numref);
  assert.equal(shared.providerCalls, 1);
  await reloaded.newOrder();
  assert.equal(shared.storage.size, 1, 'uncertain order cannot be discarded as a new order');

  const blockedStorage = state();
  await page(blockedStorage, {storageFails:true}).submit();
  assert.equal(blockedStorage.requests.length, 0);
  const blockedRead = state();
  await page(blockedRead, {readFails:true}).submit();
  assert.equal(blockedRead.requests.length, 0);
  const badReadback = state();
  await page(badReadback, {storageMismatch:true}).submit();
  assert.equal(badReadback.requests.length, 0);
  const missingLocks = state();
  await page(missingLocks, {noLocks:true}).submit();
  assert.equal(missingLocks.requests.length, 0);

  const divergent = state();
  divergent.firstRequest = false;
  const divergentPage = page(divergent, {tamperResponse:true});
  await divergentPage.submit();
  assert.match(divergentPage.get('notice').textContent, /no coincide/);
  assert.equal(divergent.storage.size, 1);

  const mismatch = state();
  const mismatchPage = page(mismatch);
  await mismatchPage.submit();
  mismatch.intent.status = 'QR_ISSUED';
  mismatch.intent.numref = '7654321';
  await mismatchPage.newOrder();
  assert.equal(mismatch.storage.size, 1, 'mismatched server reference must not clear the pending order');

  const beforeProvider = state();
  const offline = page(beforeProvider, {failBeforeProvider:true});
  await offline.submit();
  const resumed = page(beforeProvider);
  await resumed.restore();
  await resumed.newOrder();
  assert.equal(beforeProvider.storage.size, 1, 'a missing server order cannot be discarded automatically');
  await resumed.submit();
  assert.equal(beforeProvider.requests[1].order_id, beforeProvider.requests[0].order_id);
  assert.equal(beforeProvider.requests[1].numref, beforeProvider.requests[0].numref);
  assert.equal(beforeProvider.providerCalls, 1);

  const concurrent = state();
  const tabA = page(concurrent, {holdFirst:true});
  const tabB = page(concurrent);
  const pending = tabA.submit();
  for (let i = 0; i < 100 && !concurrent.release; i++) await new Promise(resolve => setTimeout(resolve, 1));
  assert(concurrent.release, 'first tab must enter the provider request');
  await tabB.submit();
  assert.equal(concurrent.requests.length, 1, 'second tab must not send while the first holds the lock');
  concurrent.release();
  await pending;

  const legacy = state();
  legacy.firstRequest = false;
  legacy.intent = {id:'f'.repeat(32), merchant_id:merchant, order_id:'legacy-1', numref:'a1',
    concept:'Pedido privado', amount_minor:15000, expiration_s:900,
    status:'PROVIDER_UNCERTAIN', qr_display:null, expired:false};
  const legacyPage = page(legacy, {includeHistory:true});
  await legacyPage.restore();
  const recoverButton = legacyPage.get('history').children[0].children[0];
  assert.equal(recoverButton.textContent, 'Recuperar');
  await recoverButton.listeners.click();
  assert.equal(legacy.storage.size, 1);
  await legacyPage.submit();
  assert.equal(legacy.requests[0].order_id, 'legacy-1');
  assert.equal(legacy.requests[0].expiration_s, 900);
  assert.equal(legacy.providerCalls, 0);
  console.log('CHECKOUT_RECOVERY_UI_OK');
})().catch(error => { console.error(error); process.exitCode = 1; });
