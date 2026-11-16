'use strict';
// Synthetic DOM and HTTP response harness; NEVER a Chromium or backend E2E claim.
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
const handlers={},ui={},storage=new Map(),requests=[];
const el=id=>ui[id]||(ui[id]={style:{},innerHTML:'',textContent:'',focus(){},replaceChildren(){},append(){},addEventListener(){}});
const document={getElementById:el,querySelector:q=>q.includes('topbar')?el('topbar'):null,querySelectorAll:()=>[],addEventListener:(k,f)=>(handlers[k]??=[]).push(f),createElement:()=>({style:{},focus(){},remove(){},click(){}}),body:{append(){}}};
let authStatus=200,identity='synthetic-owner',canAccessMarket=true,revision=0,remoteState=null;
const fetch=async (route,opts)=>{
 requests.push(route);
 if(route==='/api/hackaton/commercial-state'){
  if(opts?.method==='PUT'){
   const data=JSON.parse(opts.body);assert.equal(data.revision,revision,'synthetic optimistic revision');
   remoteState=data.state;revision++;
  }
  return {ok:true,status:200,json:async()=>({state:remoteState,revision})};
 }
 assert.equal(route,'/api/auth/me','explicit synthetic endpoint');
 return {ok:authStatus===200,status:authStatus,json:async()=>({user:{id:identity,email:'synthetic@example.org',display_name:'Synthetic',role:'GATEWAY_ACCOUNT',active:true,can_access_market:canAccessMarket},csrf_token:'synthetic-csrf',permissions:['account.manage']})};
};
class FormData{constructor(form){this.fields=form.fields||{}}get(k){return this.fields[k]??null}}
const window={scrollTo(){},setTimeout(){return 0},clearTimeout(){},print(){}};
const location={hash:'',protocol:'http:',replace(){},assign(){}};
const context={document,window,location,fetch,FormData,confirm:()=>true,localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},navigator:{clipboard:{writeText:async()=>{}}},setInterval:()=>0,setTimeout:()=>0,clearTimeout:()=>{},URL,Blob,console};
vm.createContext(context);
const code=fs.readFileSync(path.join(__dirname,'../rio_pey_codi/static/unificada/hackaton/app.js'),'utf8');
vm.runInContext(code,context,{filename:'app.js'});
const tick=()=>new Promise(resolve=>setImmediate(resolve));
async function click(action,id=''){for(const fn of handlers.click||[])fn({target:{closest:s=>s==='[data-action]'?{dataset:{action,id}}:null}});await tick()}
async function submit(type,fields){for(const fn of handlers.submit||[])fn({target:{closest:s=>s==='form[data-form]'?{dataset:{form:type},fields}:null},preventDefault(){}});await tick()}
(async()=>{
 await tick();await tick();assert(window.RIO_DEMO.isReady(),'synthetic login');
 const views=['panel','mercado','solicitudes','ofertas','pedidos','fletes','caja','inventario','negocios','tickets','historial'];
 for(const name of views){window.RIO_DEMO.go(name);assert.equal(window.RIO_DEMO.getPage(),name)}
 await click('market-add','SKU-001');await click('rfq-from-cart');
 await submit('rfq',{fromCart:'1',buyer:'NEG-001',destination:'Ciudad de México',notes:'sintético'});
 let state=window.RIO_DEMO.getState();assert.equal(state.rfqs.length,1);
 await click('new-offer');
 await submit('offer',{rfqId:state.rfqs[0].id,supplier:'NEG-002',deliveryFee:'20','unit_SKU-001':'40',notes:''});
 state=window.RIO_DEMO.getState();assert.equal(state.offers.length,1);
 await click('accept-offer',state.offers[0].id);
 state=window.RIO_DEMO.getState();assert.equal(state.orders.length,1);
 await submit('freight',{orderId:state.orders[0].id,carrier:'NEG-003',cost:'80'});
 state=window.RIO_DEMO.getState();assert.equal(state.freights.length,1);
 await click('accept-freight',state.freights[0].id);await click('complete-freight',state.freights[0].id);
 assert.equal(window.RIO_DEMO.getState().orders[0].status,'recibido');
 await click('pos-add','SKU-002');await submit('checkout',{payment:'efectivo',received:'100'});
 assert.equal(window.RIO_DEMO.getState().sales.length,1);
 canAccessMarket=false;window.RIO_DEMO.go('panel');await tick();await tick();
 assert(!window.RIO_DEMO.getUiRoutes().includes('mercado'),'revoked market absent from available routes');
 window.RIO_DEMO.go('mercado');assert.equal(window.RIO_DEMO.getPage(),'panel','non-owner cannot enter market');
 assert(!ui.sidebar.innerHTML.includes('data-nav="mercado"'),'non-owner market navigation hidden');
 identity='synthetic-other';window.RIO_DEMO.go('panel');await tick();await tick();
 assert.equal(window.RIO_DEMO.isReady(),false,'session invalidation');
 console.log(JSON.stringify({result:'PASS',scope:'SYNTHETIC_NODE_VM_NOT_BROWSER',views:views.length,rfq:1,offers:1,orders:1,freights:1,sales:1,identityChangedFailClosed:true,marketRevocationWithoutReload:true,requests:requests.length}));
})().catch(error=>{console.error(error.stack);process.exitCode=1});
