const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../rio_pey_codi/static/app.js'), 'utf8')
  .replace(/\nboot\(\);\s*$/, '\n');
const merchant='a'.repeat(32), other='b'.repeat(32), user='c'.repeat(32);
class Element {
  constructor(){this.listeners={};this.children=[];this.value='';this.hidden=false;this.disabled=false;this.textContent=''}
  addEventListener(name,fn){this.listeners[name]=fn} replaceChildren(){this.children=[]}
  append(value){this.children.push(value)} querySelector(){return {disabled:false}} focus(){}
}
const elements=new Map(), get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id)};
const reply=(status,body)=>({ok:status>=200&&status<300,status,json:async()=>body});
const observation={id:'d'.repeat(32),status:'ACTIVE',checked_at:1704067200,source:'SERVER_PEY_HTTPS_READ_ONLY',
                   merchant_ownership_verified:false,bank_payment_confirmed:false,live_payments_enabled:false};
let mode='success', posts=[], release, uuid=0;
const state=()=>({production:'BLOCKED',live_payments_enabled:false,merchant_ownership_verified:false,
  independent_bank_source_verified:false,bank_payment_confirmed:false,account_lookup_configured:true,
  provider_observation:observation,provider_observation_matches_current_declaration:true});
const context=vm.createContext({
 document:{getElementById:get,createElement:()=>new Element()},location:{hash:'',search:'',pathname:'/'},
 history:{replaceState(){}},navigator:{},localStorage:{setItem(){throw Error('not expected')},getItem(){return null}},
 crypto:{randomUUID:()=>`${String(++uuid).padStart(8,'0')}-1111-4111-8111-111111111111`},
 fetch:async(url,options={})=>{
   if(options.method==='POST'){
     posts.push({url,headers:options.headers,body:options.body});
     if(mode==='retry' && posts.length===1)throw Error('timeout');
     if(mode==='duplicate')return reply(409,{detail:'Account check request already used'});
     if(mode==='stale')return await new Promise(resolve=>{release=()=>resolve(reply(201,{observation}))});
     return reply(201,{observation});
   }
   return reply(200,state());
 },Uint32Array,URLSearchParams,Blob,URL,TextEncoder,AbortController,setTimeout,clearTimeout,
});
vm.runInContext(source,context);
function select(){vm.runInContext(`currentUserId='${user}';currentMerchant='${merchant}';csrf='fixture';merchantRoles.set('${merchant}','owner');resetBeneficiary()`,context)}
async function readiness(){return vm.runInContext('loadProviderReadiness()',context)}
async function check(){return vm.runInContext('checkProviderAccount()',context)}

(async()=>{
  select(); await readiness();
  assert.equal(get('provider-account-check').hidden,false);
  assert.match(get('provider-readiness').textContent,/activa/);
  assert.match(get('provider-readiness').textContent,/No acredita titularidad ni abono/);
  await check();
  assert.equal(posts.length,1);
  assert.equal(posts[0].body,undefined,'provider credential and account must not be sent by the browser');
  assert.equal(posts[0].headers['X-CSRF-Token'],'fixture');
  assert.match(posts[0].headers['Idempotency-Key'],/^[0-9a-f]{32}$/);

  mode='retry';posts=[];select();await check();
  assert.match(get('provider-readiness').textContent,/resultado es incierto/);
  await check();
  assert.equal(posts[0].headers['Idempotency-Key'],posts[1].headers['Idempotency-Key']);

  mode='duplicate';posts=[];select();await check();
  assert.match(get('provider-readiness').textContent,/consulta ya se registró/);
  assert.match(get('provider-readiness').textContent,/Última consulta a pey/);

  mode='stale';posts=[];select();
  const pending=check();
  for(let i=0;i<100&&!release;i++)await new Promise(resolve=>setTimeout(resolve,1));
  assert(release);
  vm.runInContext(`currentMerchant='${other}';resetBeneficiary()`,context);
  release();await pending;
  assert.equal(get('provider-readiness').textContent,'');
  assert.equal(get('provider-account-check').hidden,true);
  console.log('PROVIDER_READINESS_UI_OK');
})().catch(error=>{console.error(error);process.exitCode=1});
