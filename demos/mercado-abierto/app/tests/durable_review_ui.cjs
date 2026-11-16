const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../rio_pey_codi/static/app.js'), 'utf8')
  .replace(/\nboot\(\);\s*$/, '\n');
const merchant='a'.repeat(32), otherMerchant='b'.repeat(32), user='c'.repeat(32);
const intent='d'.repeat(32), second='e'.repeat(32), reviewId='f'.repeat(32);
class Element {
  constructor(){this.listeners={};this.children=[];this.value='';this.hidden=false;this.disabled=false;this.textContent='';}
  addEventListener(name,fn){this.listeners[name]=fn} replaceChildren(){this.children=[]}
  append(value){this.children.push(value)} querySelector(){return {disabled:false}} focus(){}
}
const elements=new Map(), get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id)};
const reply=(status,body)=>({ok:status>=200&&status<300,status,json:async()=>body});
const saved=(id)=>({review:{id:reviewId,intent_id:id,source:'USER_REPORTED_UNVERIFIED',
   classification:'MATCH_CANDIDATE_UNVERIFIED',created_at:1704067200,signature_assessment_at_review:'VERIFIED',account_assessment_at_review:'WEBHOOK_ACCOUNT_ID_ABSENT'},bank_payment_confirmed:false,
   independent_bank_source_verified:false,provider_signature_reverified:true,
   beneficiary_binding_verified:false,bank_records_persisted:false});
let mode='success', posts=[], release, uuid=0, storageWrites=0;
const context=vm.createContext({
  document:{getElementById:get,createElement:()=>new Element()}, location:{hash:'',search:'',pathname:'/'},
  history:{replaceState(){}}, navigator:{}, localStorage:{setItem(){storageWrites++},getItem(){return null}},
  crypto:{randomUUID:()=>`${String(++uuid).padStart(8,'0')}-1111-4111-8111-111111111111`},
  fetch:async(url,options={})=>{
    if(options.method==='POST'){
      posts.push({url,headers:options.headers,body:JSON.parse(options.body)});
      if(url.endsWith('/reconciliation-preview') && mode==='preview-stale') return reply(409,{detail:'Payment review context changed'});
      if(url.endsWith('/reconciliation-preview')) return reply(200,{
        classification:'MATCH_CANDIDATE_UNVERIFIED',bank_payment_confirmed:false,
        provider_signature_reverified:true,signature_assessment:'VERIFIED',account_assessment:'WEBHOOK_ACCOUNT_ID_ABSENT'});
      if(mode==='retry' && posts.length===1) throw Error('Conexión interrumpida');
      if(mode==='retry') return reply(409,{detail:'already used',code:'REVIEW_REQUEST_ALREADY_USED'});
      if(mode==='invalid' && posts.length===1) return reply(422,{detail:'Invalid reconciliation data'});
      if(mode==='invalid') return reply(201,saved(second));
      if(mode==='stale') return await new Promise(resolve=>{release=()=>resolve(reply(201,saved(second)))});
      return reply(201,saved(intent));
    }
    if(url.includes('/by-request/'))return reply(200,saved(second));
    return reply(200,{reviews:[saved(mode==='success'?intent:second).review],truncated:false});
  }, Uint32Array,URLSearchParams,Blob,URL,TextEncoder,AbortController,setTimeout,clearTimeout,
});
vm.runInContext(source,context);
function populate(){
  get('review-clabe').value='0'.repeat(18);get('review-tracking').value='synthetic-track';
  get('review-amount').value='150.05';get('review-direction').value='credit';get('review-reference').value='fixture-reference';
}
function select(id){
  vm.runInContext(`currentUserId='${user}';currentMerchant='${merchant}';csrf='fixture-csrf';merchantRoles.set('${merchant}','owner');showIntent({id:'${id}',order_id:'order',status:'PROVIDER_REPORTED',expired:false})`,context);
}
async function submit(){return get('review-form').listeners.submit({preventDefault(){}})}

(async()=>{
  select(intent);populate();
  assert.equal(get('review').hidden,false);
  await get('review-preview').listeners.click();
  assert.match(get('review-status').textContent,/Firma comprobada/);
  assert.match(get('review-status').textContent,/webhook no incluye un ID de cuenta/);
  mode='preview-stale';
  await get('review-preview').listeners.click();
  assert.match(get('review-status').textContent,/información del cobro cambió.*vuelve a generar la vista previa/i);
  assert.equal(get('review-clabe').value,'0'.repeat(18),'a conflict should preserve user input for retry');
  assert.equal(get('review-preview').disabled,false);
  mode='success';
  posts=[];
  await submit();
  assert.equal(posts.length,1);
  assert.match(posts[0].headers['Idempotency-Key'],/^[0-9a-f]{32}$/);
  assert.equal(posts[0].headers['X-CSRF-Token'],'fixture-csrf');
  assert.equal(posts[0].body.bank_records[0].amount_minor,15005);
  assert.match(get('review-status').textContent,/Revisión guardada/);
  assert.equal(get('review-clabe').value,'');
  assert.equal(storageWrites,0,'bank fields must not be written to browser storage');

  mode='retry';posts=[];select(second);populate();
  await submit();
  assert.match(get('review-status').textContent,/mismos datos/);
  get('review-amount').value='151.00';await submit();
  assert.equal(posts.length,1,'changed input cannot replace an uncertain request');
  get('review-amount').value='150.05';await submit();
  assert.equal(posts.length,2);
  assert.equal(posts[0].headers['Idempotency-Key'],posts[1].headers['Idempotency-Key']);
  assert.match(get('review-status').textContent,/Se recuperó una revisión anterior/);
  assert.match(get('review-status').textContent,/no conservó los datos bancarios/);

  mode='invalid';posts=[];select(second);populate();
  await submit();
  assert.match(get('review-status').textContent,/Revisa los datos/);
  get('review-amount').value='151.00';await submit();
  assert.equal(posts.length,2,'a rejected input can be corrected');
  assert.notEqual(posts[0].headers['Idempotency-Key'],posts[1].headers['Idempotency-Key']);

  mode='stale';posts=[];select(second);populate();
  const pending=submit();
  for(let i=0;i<100&&!release;i++)await new Promise(resolve=>setTimeout(resolve,1));
  assert(release,'fixture must pause the save');
  vm.runInContext(`currentMerchant='${otherMerchant}';resetReview()`,context);
  release();await pending;
  assert.equal(get('review').hidden,true);
  assert.equal(get('review-clabe').value,'');
  assert.equal(get('review-status').textContent,'','stale result must not appear under another company');
  console.log('DURABLE_REVIEW_UI_OK');
})().catch(error=>{console.error(error);process.exitCode=1});
