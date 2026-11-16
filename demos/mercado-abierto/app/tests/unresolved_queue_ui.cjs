const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');

const merchantA = 'a'.repeat(32), merchantB = 'b'.repeat(32), user = 'c'.repeat(32);
const source = fs.readFileSync(path.join(__dirname, '../rio_pey_codi/static/app.js'), 'utf8')
  .replace(/\nboot\(\);\s*$/, '\n');
class Element {
  constructor() {
    this.listeners={}; this.children=[]; this.button={disabled:false}; this.data={};
    this.value=''; this.hidden=false; this.disabled=false; this.textContent='';
    this.elements={namedItem:name => ({get value() { return this.owner.data[name]; },
      set value(value) { this.owner.data[name]=value; }, owner:this})};
  }
  // Native HTMLSelectElement always exposes a selectedOptions collection.
  get selectedOptions() { return []; }
  scrollIntoView() {}
  removeAttribute(name) { delete this[name]; }
  addEventListener(name, fn) { this.listeners[name]=fn; }
  querySelector() { return this.button; }
  replaceChildren() { this.children=[]; }
  append(child) { this.children.push(child); }
  add() {}
  focus() {}
}
function reply(status, body) { return {ok:status>=200 && status<300, status, json:async()=>body}; }
const row = (merchant, n) => ({id:String(n).padStart(32,'0'), merchant_id:merchant,
  order_id:`old-${n}`, numref:`ref-${n}`, concept:`Pedido ${n}`, amount_minor:15000+n,
  expiration_s:600, status:'PROVIDER_UNCERTAIN', qr_display:null, expired:false, created_at:1700000000});

function makePage(opts={}) {
  const elements=new Map(), storage=new Map(), requests=[], queueCalls=[];
  const get=id=>{if (!elements.has(id)) elements.set(id,new Element()); return elements.get(id);};
  const rowsA=[row(merchantA,1),row(merchantA,2),row(merchantA,3)], rowsB=[row(merchantB,4)];
  let release, releaseHistory;
  const context=vm.createContext({
    window:{dispatchEvent(){},confirm(){return false}}, Event:class {constructor(type){this.type=type}},
    document:{getElementById:get,createElement:()=>new Element()},
    location:{hash:'',search:'',pathname:'/'}, history:{replaceState(){}},
    FormData:class {constructor(element){this.data=element.data} entries(){return Object.entries(this.data)}},
    localStorage:{getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
    navigator:{locks:{request:async(name,_opts,fn)=>fn({name})}},
    crypto:{subtle:webcrypto.subtle,randomUUID:()=>{throw Error('Must recover the old order')},getRandomValues:()=>{}},
    fetch:async(url, options={})=>{
      if (url.includes('/checkout-history')) {
        if (opts.deferHistory && !releaseHistory) await new Promise(resolve=>{releaseHistory=resolve});
        return reply(200,{intents:[]});
      }
      if (url.includes('/checkout-unresolved')) {
        const u=new URL(url,'http://localhost');
        const merchant=u.pathname.split('/')[3];
        queueCalls.push(merchant);
        if (opts.error) return reply(503,{detail:'Queue unavailable'});
        if (opts.defer && merchant===merchantA) await new Promise(resolve=>{release=resolve});
        const values=merchant===merchantA?rowsA:rowsB;
        const after=u.searchParams.get('after_id');
        const page=after?values.slice(2):values.slice(0,2);
        return reply(200,{intents:page,next_cursor:!after&&values.length>2?{created_at:1700000000,id:values[1].id}:null});
      }
      if (url.includes('/checkout-orders/')) {
        const id=decodeURIComponent(url.split('/').pop());
        return reply(200,{intent:[...rowsA,...rowsB].find(x=>x.order_id===id)});
      }
      assert.equal(url,'/v1/checkout/qr');
      const body=JSON.parse(options.body); requests.push(body);
      return reply(201,{status:'REPLAY_NO_PROVIDER_RETRY',intent:rowsA[0]});
    },
    Uint32Array,URLSearchParams,Blob,URL,TextEncoder,AbortController,setTimeout,clearTimeout,
  });
  vm.runInContext(source,context);
  vm.runInContext(`currentUserId='${user}'; csrf='synthetic';paymentRequestsEnabled=true;merchantRoles.set('${merchantA}','cashier');merchantRoles.set('${merchantB}','cashier');`,context);
  get('merchant').value=merchantA;
  return {get,requests,storage,queueCalls,restore:()=>vm.runInContext('selectMerchant()',context),
    submit:()=>get('charge').listeners.submit({preventDefault(){},currentTarget:get('charge')}),
    release:()=>release&&release(), hasRelease:()=>!!release,
    releaseHistory:()=>releaseHistory&&releaseHistory(), hasHistory:()=>!!releaseHistory};
}

(async()=>{
  const page=makePage();
  await page.restore();
  assert.equal(page.get('history').children.length,0,'the recent history intentionally omits old orders');
  assert.equal(page.get('unresolved').children.length,2);
  assert.equal(page.get('unresolved-more').hidden,false);
  await page.get('unresolved-more').listeners.click();
  assert.equal(page.get('unresolved').children.length,3);
  assert.equal(page.get('unresolved-more').hidden,true);
  const button=page.get('unresolved').children[0].children[0];
  assert.equal(button.textContent,'Recuperar');
  await button.listeners.click();
  assert.equal(page.get('charge').data.concept,'Pedido 1');
  assert.equal(page.get('charge').data.amount,'150.01');
  await page.submit();
  assert.equal(page.requests.length,1);
  assert.equal(page.requests[0].order_id,'old-1');
  assert.equal(page.requests[0].numref,'ref-1');

  const failed=makePage({error:true});
  await failed.restore();
  assert.match(failed.get('unresolved-status').textContent,/No se pudo consultar/);
  assert.equal(failed.get('unresolved-more').hidden,true);

  const raced=makePage({defer:true});
  const old=raced.restore();
  for(let i=0;i<100&&!raced.hasRelease();i++) await new Promise(resolve=>setTimeout(resolve,1));
  assert(raced.hasRelease());
  raced.get('merchant').value=merchantB;
  await raced.restore();
  raced.release(); await old;
  assert.equal(raced.get('unresolved').children.length,1);
  assert.match(raced.get('unresolved').children[0].textContent,/old-4/);
  assert.doesNotMatch(raced.get('unresolved').children[0].textContent,/old-1/);

  const back=makePage({deferHistory:true});
  const stale=back.restore();
  for(let i=0;i<100&&!back.hasHistory();i++) await new Promise(resolve=>setTimeout(resolve,1));
  assert(back.hasHistory());
  back.get('merchant').value=merchantB; await back.restore();
  back.get('merchant').value=merchantA; await back.restore();
  back.releaseHistory(); await stale;
  assert.equal(back.queueCalls.filter(id=>id===merchantA).length,1,
    'an old selection must not refresh the queue after switching away and back');
  console.log('UNRESOLVED_QUEUE_UI_OK');
})().catch(error=>{console.error(error);process.exitCode=1});
