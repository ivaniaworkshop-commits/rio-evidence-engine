const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');
const source = fs.readFileSync(path.join(__dirname, '../rio_pey_codi/static/app.js'), 'utf8')
  .replace(/\nboot\(\);\s*$/, '\n');
const merchant = 'a'.repeat(32);

class Element {
  constructor() {
    this.listeners={}; this.children=[]; this.button={disabled:false}; this.data={};
    this.value=''; this.hidden=false; this.disabled=false; this.textContent='';
    this.elements={namedItem:name => ({get value(){return this.owner.data[name]},
      set value(value){this.owner.data[name]=value},owner:this})};
  }
  // Native HTMLSelectElement always exposes a selectedOptions collection.
  get selectedOptions() { return []; }
  scrollIntoView() {}
  removeAttribute(name) { delete this[name]; }
  addEventListener(name,fn){this.listeners[name]=fn}
  querySelector(){return this.button}
  replaceChildren(){this.children=[]}
  append(child){this.children.push(child)}
  add(){} focus(){}
}
function reply(status,body){return {ok:status>=200&&status<300,status,json:async()=>body}}
function sharedServer(){
  return {intents:new Map(),providerCalls:0,posts:[],ids:0,random:100,
          holdLookups:true,lookupWaiters:[],lookupCount:0};
}
function page(server,user,opts={}) {
  const elements=new Map(),storage=new Map();
  const get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id)};
  const context=vm.createContext({
    window:{dispatchEvent(){},confirm(){return false}}, Event:class {constructor(type){this.type=type}},
    document:{getElementById:get,createElement:()=>new Element()},
    location:{hash:'',search:'',pathname:'/'},history:{replaceState(){}},
    FormData:class{constructor(e){this.data=e.data}entries(){return Object.entries(this.data)}},
    localStorage:{getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
    navigator:{locks:{request:async(name,_options,fn)=>fn({name})}},
    crypto:{subtle:webcrypto.subtle,
      randomUUID:()=>`00000000-0000-4000-8000-${String(++server.ids).padStart(12,'0')}`,
      getRandomValues:values=>{values[0]=++server.random;return values}},
    fetch:async(url,options={})=>{
      if(url.includes('/checkout-history'))return reply(200,{intents:[]});
      if(url.includes('/checkout-unresolved'))return reply(200,{intents:[],next_cursor:null});
      if(url.includes('/checkout-orders/')){
        if(opts.failLookup)return reply(503,{detail:'Lookup unavailable'});
        if(opts.unknown404)return reply(404,{detail:'Unknown route'});
        if(opts.malformedLookup)return reply(200,{});
        const id=decodeURIComponent(url.split('/').pop());
        if(server.holdLookups && id==='sale-123'){
          server.lookupCount++;
          await new Promise(resolve=>{
            server.lookupWaiters.push(resolve);
            if(server.lookupWaiters.length===2){
              server.holdLookups=false;
              for(const waiter of server.lookupWaiters)waiter();
            }
          });
          return reply(404,{detail:'Payment intent not found',code:'ORDER_NOT_FOUND'});
        }
        const intent=server.intents.get(id);
        return intent?reply(200,{intent}):reply(404,{detail:'Payment intent not found',code:'ORDER_NOT_FOUND'});
      }
      assert.equal(url,'/v1/checkout/qr');
      const body=JSON.parse(options.body);server.posts.push(body);
      const prior=server.intents.get(body.order_id);
      if(prior){
        if(prior.numref!==body.numref||prior.concept!==body.concept||
           prior.amount_minor!==body.amount_minor||prior.expiration_s!==body.expiration_s)
          return reply(409,{detail:'Order conflict'});
        return reply(201,{status:'REPLAY_NO_PROVIDER_RETRY',intent:prior});
      }
      server.providerCalls++;
      server.intents.set(body.order_id,{id:String(server.providerCalls).padStart(32,'0'),
        merchant_id:body.merchant_id,order_id:body.order_id,numref:body.numref,
        concept:body.concept,amount_minor:body.amount_minor,expiration_s:body.expiration_s,
        status:'PROVIDER_UNCERTAIN',qr_display:null,expired:false});
      return reply(502,{detail:'Provider status uncertain'});
    },
    Uint32Array,URLSearchParams,Blob,URL,TextEncoder,AbortController,setTimeout,clearTimeout,
  });
  vm.runInContext(source,context);
  vm.runInContext(`currentMerchant='${merchant}';currentUserId='${user}';csrf='synthetic';paymentRequestsEnabled=true;merchantRoles.set('${merchant}','cashier')`,context);
  get('merchant').value=merchant;
  get('charge').data={order_id:'sale-123',concept:'Pedido compartido',amount:'150.00'};
  return {get,storage,submit:()=>get('charge').listeners.submit({preventDefault(){},currentTarget:get('charge')})};
}

(async()=>{
  const server=sharedServer(), a=page(server,'b'.repeat(32)), b=page(server,'c'.repeat(32));
  await Promise.all([a.submit(),b.submit()]);
  assert.equal(server.providerCalls,1,'the same shared sale must trigger one provider attempt');
  assert.equal(server.posts.length,2,'the race should reach the server from both contexts');
  assert.equal(server.posts[0].order_id,'sale-123');
  assert.equal(server.posts[1].order_id,'sale-123');
  const recorded=server.intents.get('sale-123');
  assert.equal(JSON.parse([...a.storage.values()][0]).reference,recorded.numref);
  assert.equal(JSON.parse([...b.storage.values()][0]).reference,recorded.numref);

  const other=page(server,'d'.repeat(32));
  await other.submit();
  assert.equal(server.posts.length,2,'an existing matching folio must be recovered without POST');
  assert.equal(other.get('folio').textContent,'sale-123');
  assert.equal(JSON.parse([...other.storage.values()][0]).reference,recorded.numref);

  const mismatch=page(server,'e'.repeat(32));
  mismatch.get('charge').data.amount='151.00';
  await mismatch.submit();
  assert.equal(server.posts.length,2,'different sale data must not send an order');
  assert.equal(mismatch.storage.size,0);
  assert.match(mismatch.get('notice').textContent,/otros datos/i);

  b.get('charge').data.order_id='different-sale';
  await b.submit();
  assert.equal(server.posts.length,2,'a pending folio cannot be changed');
  assert.match(b.get('notice').textContent,/folio/i);

  const unavailable=page(server,'f'.repeat(32),{failLookup:true});
  await unavailable.submit();
  assert.equal(server.posts.length,2,'failed lookup must not fall through to a new order');
  assert.equal(unavailable.storage.size,0);

  for(const option of ['unknown404','malformedLookup']){
    const bad=page(server,'2'.repeat(32),{[option]:true});
    await bad.submit();
    assert.equal(server.posts.length,2,'an unrecognized lookup response must fail closed');
    assert.equal(bad.storage.size,0);
  }

  const invalid=page(server,'1'.repeat(32));
  invalid.get('charge').data.order_id='bad folio';
  await invalid.submit();
  assert.equal(server.posts.length,2);
  assert.match(invalid.get('notice').textContent,/folio/i);
  console.log('SHARED_SALE_UI_OK');
})().catch(error=>{console.error(error);process.exitCode=1});
