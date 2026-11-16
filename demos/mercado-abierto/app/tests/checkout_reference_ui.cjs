const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');

class Element {
  constructor() {
    this.listeners = {};
    this.button = {disabled:false};
    this.value = '';
    this.hidden = false;
    this.textContent = '';
    this.data = {};
  }
  // Native HTMLSelectElement always exposes a selectedOptions collection.
  get selectedOptions() { return []; }
  scrollIntoView() {}
  removeAttribute(name) { delete this[name]; }
  addEventListener(name, listener) { this.listeners[name] = listener; }
  querySelector() { return this.button; }
  replaceChildren() {}
  append() {}
  add() {}
  focus() {}
}

const elements = new Map();
const get = id => {
  if (!elements.has(id)) elements.set(id, new Element());
  return elements.get(id);
};
const requests = [];
const references = [4293000000, 12345, 12346, 12347];
let uuid = 0;
let lastIntent;
const storage = new Map();

function reply(status, data) {
  return {ok: status >= 200 && status < 300, status, json: async () => data};
}

const context = vm.createContext({
  window:{dispatchEvent(){},confirm(){return false}}, Event:class {constructor(type){this.type=type}},
  document: {getElementById:get, createElement:() => new Element()},
  location: {hash:'', search:'', pathname:'/'},
  history: {replaceState() {}},
  FormData: class { constructor(element) { this.data = element.data; } entries() { return Object.entries(this.data); } },
  localStorage: {
    getItem:key => storage.get(key) ?? null,
    setItem:(key, value) => storage.set(key, value),
    removeItem:key => storage.delete(key),
  },
  navigator:{locks:{request:async (name, _options, callback) => callback({name})}},
  crypto: {
    subtle:webcrypto.subtle,
    randomUUID: () => `00000000-0000-4000-8000-${String(++uuid).padStart(12, '0')}`,
    getRandomValues: values => { values[0] = references.shift(); return values; },
  },
  fetch: async (url, options) => {
    if (url.endsWith('/checkout-history')) return reply(200, {intents:[]});
    if (url.includes('/checkout-unresolved')) return reply(200, {intents:[], next_cursor:null});
    if (url.includes('/checkout-orders/')) return reply(200, {intent:lastIntent});
    assert.equal(url, '/v1/checkout/qr');
    const body = JSON.parse(options.body);
    requests.push(body);
    if (requests.length === 1) return reply(409, {detail:'Used', code:'REFERENCE_TAKEN'});
    if (requests.length === 3) return reply(502, {detail:'Provider status uncertain'});
    lastIntent = {id:'intent', merchant_id:body.merchant_id, order_id:body.order_id,
      numref:body.numref, concept:body.concept, amount_minor:body.amount_minor,
      expiration_s:body.expiration_s, status:'QR_ISSUED', qr_display:'synthetic'};
    return reply(201, {intent:lastIntent});
  },
  Uint32Array, URLSearchParams, Blob, URL, TextEncoder, AbortController, setTimeout, clearTimeout,
});

const source = fs.readFileSync(path.join(__dirname, '../rio_pey_codi/static/app.js'), 'utf8');
vm.runInContext(source.replace(/\nboot\(\);\s*$/, '\n'), context);
vm.runInContext("currentMerchant = 'a'.repeat(32); currentUserId = 'b'.repeat(32); csrf = 'synthetic'; paymentRequestsEnabled = true; merchantRoles.set(currentMerchant, 'cashier')", context);
get('charge').data = {amount:'150.00', concept:'Pedido #12345'};

async function submit() {
  await get('charge').listeners.submit({preventDefault() {}, currentTarget:get('charge')});
}

(async () => {
  await submit();
  assert.equal(requests.length, 1);
  assert.equal(requests[0].numref, '1012345');
  assert.equal(requests[0].amount_minor, 15000);
  await submit();
  assert.equal(requests[1].order_id, requests[0].order_id);
  assert.equal(requests[1].numref, '1012346');
  await get('new-order').listeners.click();
  await submit();
  assert.notEqual(requests[2].order_id, requests[1].order_id);
  assert.equal(requests[2].numref, '1012347');
  await submit();
  assert.equal(requests[3].order_id, requests[2].order_id);
  assert.equal(requests[3].numref, requests[2].numref);
  console.log('CHECKOUT_REFERENCE_UI_OK');
})().catch(error => { console.error(error); process.exitCode = 1; });
