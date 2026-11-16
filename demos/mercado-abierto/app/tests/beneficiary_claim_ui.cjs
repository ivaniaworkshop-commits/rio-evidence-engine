const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../rio_pey_codi/static/app.js'), 'utf8')
  .replace(/\nboot\(\);\s*$/, '\n');
const merchant='a'.repeat(32), other='b'.repeat(32), user='c'.repeat(32);
const account='01JBAVWE4NS5TGXHWGMX3KH23Q'; // public example
class Element {
  constructor(){this.listeners={};this.children=[];this.value='';this.hidden=false;this.disabled=false;this.textContent=''}
  addEventListener(name,fn){this.listeners[name]=fn} replaceChildren(){this.children=[]}
  append(value){this.children.push(value)} querySelector(){return {disabled:false}} focus(){}
}
const elements=new Map(), get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id)};
const reply=(status,body)=>({ok:status>=200&&status<300,status,json:async()=>body});
let mode='success', posts=[], release, uuid=0, storageWrites=0;
const flags={provider_status_verified:false,live_payments_enabled:false,bank_payment_confirmed:false};
const context=vm.createContext({
  document:{getElementById:get,createElement:()=>new Element()}, location:{hash:'',search:'',pathname:'/'},
  history:{replaceState(){}}, navigator:{}, localStorage:{setItem(){storageWrites++},getItem(){return null}},
  crypto:{randomUUID:()=>`${String(++uuid).padStart(8,'0')}-1111-4111-8111-111111111111`},
  fetch:async(url,options={})=>{
    if(options.method==='POST'){
      posts.push({url,headers:options.headers,body:JSON.parse(options.body)});
      if(mode==='retry' && posts.length===1) throw Error('Conexión interrumpida');
      if(mode==='timeout' && posts.length===1) return await new Promise((_resolve,reject)=>{
        options.signal.addEventListener('abort',()=>reject(Error('Tiempo agotado')));
      });
      const row={id:'d'.repeat(32),merchant_id:merchant,created_at:1704067200, ...posts.at(-1).body};
      if(mode==='stale') return await new Promise(resolve=>{release=()=>resolve(reply(201,{claim:row,...flags}))});
      return reply(201,{claim:row,...flags});
    }
    if(mode==='refresh-fails') throw Error('Sin conexión');
    return reply(200,{claims:[],truncated:false,...flags});
  }, Uint32Array,URLSearchParams,Blob,URL,TextEncoder,AbortController,
  setTimeout:(fn,ms)=>setTimeout(fn,mode==='timeout'?5:ms),clearTimeout,
});
vm.runInContext(source,context);
function select(){vm.runInContext(`currentUserId='${user}';currentMerchant='${merchant}';csrf='fixture';merchantRoles.set('${merchant}','owner');resetBeneficiary()`,context)}
function submit(claim='OWNER_REPORTED_VERIFIED'){return vm.runInContext(`submitBeneficiary('${claim}')`,context)}

(async()=>{
  select();get('beneficiary-account').value=account;await submit();
  assert.equal(posts.length,1);assert.equal(posts[0].body.provider_account_id,account);
  assert.match(posts[0].headers['Idempotency-Key'],/^[0-9a-f]{32}$/);
  assert.equal(posts[0].headers['X-CSRF-Token'],'fixture');
  assert.match(get('beneficiary-status').textContent,/Confirmación guardada/);
  assert.equal(get('beneficiary-account').value,'');assert.equal(storageWrites,0);

  mode='retry';posts=[];select();get('beneficiary-account').value=account;await submit();
  get('beneficiary-account').value='';await submit();assert.equal(posts.length,1);
  get('beneficiary-account').value=account;await submit();assert.equal(posts.length,2);
  assert.equal(posts[0].headers['Idempotency-Key'],posts[1].headers['Idempotency-Key']);

  mode='timeout';posts=[];select();await submit();
  assert.match(get('beneficiary-status').textContent,/mismos datos/);
  assert.equal(get('beneficiary-save').disabled,false);
  mode='success';await submit();
  assert.equal(posts[0].headers['Idempotency-Key'],posts[1].headers['Idempotency-Key']);

  mode='refresh-fails';posts=[];select();await submit();
  assert.match(get('beneficiary-status').textContent,/Confirmación guardada/);
  assert.match(get('beneficiary-status').textContent,/No se pudo actualizar/);

  mode='stale';posts=[];select();get('beneficiary-account').value=account;
  const pending=submit();
  for(let i=0;i<100&&!release;i++)await new Promise(resolve=>setTimeout(resolve,1));
  assert(release);
  vm.runInContext(`currentMerchant='${other}';resetBeneficiary()`,context);
  release();await pending;
  assert.equal(get('beneficiary-panel').hidden,true);
  assert.equal(get('beneficiary-account').value,'');
  assert.equal(get('beneficiary-status').textContent,'');
  console.log('BENEFICIARY_CLAIM_UI_OK');
})().catch(error=>{console.error(error);process.exitCode=1});
