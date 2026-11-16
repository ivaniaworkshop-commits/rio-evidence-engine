const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');
const source = fs.readFileSync(path.join(__dirname, '../rio_pey_codi/static/app.js'), 'utf8')
  .replace(/\nboot\(\);\s*$/, '\n');
const user='b'.repeat(32), merchant='a'.repeat(32), id='sale-123';
class Element {
  constructor(){this.listeners={};this.children=[];this.data={};this.dataset={};this.button={disabled:false};
    this.value='';this.hidden=false;this.disabled=false;this.textContent='';
    this.elements={namedItem:name=>({get value(){return this.owner.data[name]},
      set value(value){this.owner.data[name]=value},owner:this})};}
  // Native HTMLSelectElement always exposes a selectedOptions collection.
  get selectedOptions() { return []; }
  scrollIntoView() {}
  removeAttribute(name) { delete this[name]; }
  setAttribute(name,value) { this[name]=value; }
  addEventListener(name,fn){this.listeners[name]=fn} querySelector(){return this.button}
  replaceChildren(){this.children=[]} append(...children){this.children.push(...children)} add(){} focus(){}
}
const reply=(status,body)=>({ok:status>=200&&status<300,status,json:async()=>body});
(async()=>{
  const encoded=new TextEncoder().encode(JSON.stringify([user,merchant,'Pedido',15000,600]));
  const bytes=await webcrypto.subtle.digest('SHA-256',encoded);
  const fingerprint=Array.from(new Uint8Array(bytes),b=>b.toString(16).padStart(2,'0')).join('');
  const saved={version:1,user,merchant,id,reference:'1234567',expiration:600,fingerprint,shared:true};
  const storage=new Map([[`rio.checkout.v1:${user}:${merchant}`,JSON.stringify(saved)]]);
  const elements=new Map(),get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id)};
  const secondMerchant='c'.repeat(32);
  let release, releaseCheckout, posts=0, merchantCreates=0, holdRecovery=true, holdCheckout=false, failHistory=false;
  const context=vm.createContext({
    window:{dispatchEvent(){},confirm(){return false}}, Event:class {constructor(type){this.type=type}},
    document:{getElementById:get,createElement:()=>new Element()},Option:class{},location:{hash:'',search:'',pathname:'/'},
    history:{replaceState(){}},FormData:class{constructor(e){this.data=e.data}entries(){return Object.entries(this.data)}},
    localStorage:{getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
    navigator:{locks:{request:async(name,_options,fn)=>fn({name})}},
    crypto:{subtle:webcrypto.subtle,randomUUID:()=>{throw Error('Unexpected new order')},getRandomValues:()=>{}},
    fetch:async(url,options={})=>{
      if(url==='/v1/merchants'){
        if(options.method==='POST'){merchantCreates++;return reply(500,{detail:'Unexpected merchant creation'});}
        return reply(200,{merchants:[{id:merchant,name:'Principal',role:'cashier'},{id:secondMerchant,name:'Segundo',role:'cashier'}]});
      }
      if(url==='/v1/merchants/archived')return reply(200,{merchants:[]});
      if(url.includes('/checkout-history'))return failHistory?reply(503,{detail:'Historial temporalmente no disponible'}):reply(200,{intents:[]});
      if(url.includes('/checkout-unresolved'))return reply(200,{intents:[],next_cursor:null});
      if(url.includes('/checkout-orders/')){
        if(holdRecovery)await new Promise(resolve=>{release=resolve});
        return reply(200,{intent:{id:'f'.repeat(32),merchant_id:merchant,order_id:id,numref:'1234567',
          concept:'Pedido',amount_minor:15000,expiration_s:600,status:'PROVIDER_UNCERTAIN',qr_display:null,expired:false}});
      }
      posts++;
      if(holdCheckout)await new Promise(resolve=>{releaseCheckout=resolve});
      return reply(502,{detail:'Synthetic provider timeout'});
    },Uint32Array,URLSearchParams,Blob,URL,TextEncoder,AbortController,setTimeout,clearTimeout,
  });
  vm.runInContext(source,context);
  vm.runInContext(`currentUserId='${user}';csrf='synthetic';paymentRequestsEnabled=true;merchantRoles.set('${merchant}','cashier')`,context);
  get('merchant').value=merchant;get('charge').data={order_id:id,concept:'Pedido',amount:'151.00'};
  get('qrstate').textContent='PROVIDER_UNCERTAIN';
  const restoring=vm.runInContext('selectMerchant()',context);
  for(let i=0;i<100&&!release;i++)await new Promise(resolve=>setTimeout(resolve,1));
  assert(release,'fixture must hold the server lookup');
  assert.equal(get('amount').disabled,true,'pending restoration must disable amount input');
  assert.equal(get('charge').button.disabled,true,'pending restoration must disable submit');
  assert.equal(get('qrstate').textContent,'','a stale status must not appear current');
  await get('charge').listeners.submit({preventDefault(){},currentTarget:get('charge')});
  assert.equal(posts,0,'the checkout must not submit while restoration is pending');
  holdRecovery=false;release();await restoring;
  assert.equal(get('amount').disabled,false);
  assert.equal(get('charge').button.disabled,false);
  assert.equal(get('charge').data.amount,'150.00');
  assert.equal(get('qrstate').textContent,'Resultado incierto · conserva el folio');
  // New business shortcuts must obey the same in-flight checkout protection
  // as the disabled merchant selector, including when navigation stays usable.
  await vm.runInContext('merchants()',context);
  const secondButton=get('business-list').children[1].children[1];
  holdCheckout=true;
  const charging=get('charge').listeners.submit({preventDefault(){},currentTarget:get('charge')});
  for(let i=0;i<100&&!releaseCheckout;i++)await new Promise(resolve=>setTimeout(resolve,1));
  assert(releaseCheckout,'fixture must hold an actual checkout request');
  await secondButton.listeners.click();
  assert.equal(vm.runInContext('currentMerchant',context),merchant,'business card cannot switch the in-flight receiver');
  assert.equal(get('merchant').value,merchant);
  await get('add-merchant').listeners.submit({preventDefault(){},target:get('add-merchant')});
  assert.equal(merchantCreates,0,'new-business form cannot create/switch while checkout is pending');
  releaseCheckout();await charging;
  assert.equal(posts,1,'the synthetic checkout was submitted only once');
  failHistory=true;
  await secondButton.listeners.click();
  assert.equal(get('notice').textContent,'Historial temporalmente no disponible','failed business selection is handled without an unhandled rejection');
  console.log('SELECTION_LOADING_UI_OK');
})().catch(error=>{console.error(error);process.exitCode=1});
