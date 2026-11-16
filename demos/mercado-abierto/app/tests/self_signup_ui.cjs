const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../rio_pey_codi/static/app.js'), 'utf8')
  .replace(/\nboot\(\);\s*$/, '\n');
const elements=new Map();
function get(id){
  if(!elements.has(id))elements.set(id,{listeners:{},value:'',hidden:false,disabled:false,textContent:'',
    button:{disabled:false},addEventListener(name,fn){this.listeners[name]=fn},
    querySelector(){return this.button},replaceChildren(){},append(){}});
  return elements.get(id);
}
const reply=(status,body)=>({ok:status>=200&&status<300,status,json:async()=>body});
let sent=[];
const context=vm.createContext({document:{getElementById:get,createElement:()=>get('created')},
  location:{hash:'',search:'',pathname:'/'},history:{replaceState(){}},navigator:{},
  localStorage:{getItem(){return null},setItem(){throw Error('Should not store the key')}},
  crypto:{randomUUID:()=> '11111111-2222-4333-8444-555555555555'},
  fetch:async(url,options={})=>{
    if(url==='/public-status')return reply(200,{mode:'DEMO',launch_mode:'LIMITED',
      access_enabled:true,registration_enabled:true,registration_email_required:false,
      verification_email_enabled:false,password_reset_enabled:false});
    if(url==='/v1/auth/me')return reply(401,{detail:'Sign in required'});
    sent.push({url,body:JSON.parse(options.body),headers:options.headers});
    return reply(201,{key_saved:false,observation:{status:'ACTIVE',source:'SERVER_PEY_HTTPS_READ_ONLY',
      merchant_ownership_verified:false,live_payments_enabled:false}});
  },URLSearchParams,URL,AbortController,setTimeout,clearTimeout,Uint32Array,Blob,TextEncoder});
vm.runInContext(source,context);
(async()=>{
  await vm.runInContext('boot()',context);
  assert.equal(get('signup-submit').disabled,false);
  assert.equal(get('reset-request').hidden,true);
  assert.equal(get('resend-verification').hidden,true);
  assert.match(get('signup-state').textContent,/correo no se verifica/i);
  const merchant='a'.repeat(32), user='b'.repeat(32);
  vm.runInContext(`currentUserId='${user}';currentMerchant='${merchant}';csrf='test';merchantRoles.set('${merchant}','owner');resetBeneficiary()`,context);
  get('own-pey-key').value='synthetic-merchant-key';
  await get('own-pey-form').listeners.submit({preventDefault(){}});
  assert.equal(sent.length,1);
  assert.equal(sent[0].url,`/v1/merchants/${merchant}/own-pey-account-checks`);
  assert.equal(sent[0].body.api_key,'synthetic-merchant-key');
  assert.equal(sent[0].headers['X-CSRF-Token'],'test');
  assert.equal(get('own-pey-key').value,'');
  assert.match(get('own-pey-status').textContent,/clave no se guardó/);
  assert.match(get('own-pey-status').textContent,/no activa cobros/);
  console.log('SELF_SIGNUP_UI_OK');
})().catch(error=>{console.error(error);process.exitCode=1});
