'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

// Execute the actual browser bridge with mutable browser/account state. The
// server response is synthetic; this is not a browser or provider E2E claim.
const source=fs.readFileSync(path.join(__dirname,'../rio_pey_codi/static/market-checkout.js'),'utf8');
const USER='a'.repeat(32),SELLER='b'.repeat(32),OTHER='c'.repeat(32),ORDER='d'.repeat(32);
const order=(changes={})=>({id:ORDER,seller_merchant_id:SELLER,checkout_order_id:'market-'+ORDER,
 total_minor:12345,status:'ACCEPTED',listing_name:'Oferta del vendedor',payment:{status:'UNVERIFIED'},...changes});
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function deferred(){let resolve;const promise=new Promise(done=>{resolve=done});return {promise,resolve};}

function harness(options={}){
 const elements=new Map(),calls=[],notices=[],views=[],selections=[];
 function element(id){if(!elements.has(id))elements.set(id,{value:'',events:[],dispatchEvent(event){this.events.push(event.type)}});return elements.get(id);}
 const sandbox={
  document:{getElementById:element},location:{search:options.search??'?market_order='+ORDER},URLSearchParams,
  Event:class {constructor(type){this.type=type}},
  currentUserId:options.auto?USER:'',currentMerchant:options.merchant||SELLER,
  checkoutBusy:false,selectionBusy:false,pendingOrder:undefined,selectionGeneration:4,
  merchantRoles:new Map(options.roles||[[SELLER,'owner'],[OTHER,'owner']]),
  notice:message=>notices.push(message),window:{RioWorkspace:{open:view=>views.push(view)}},
  call:async(url,opts={})=>{calls.push({url,method:opts.method||'GET'});return options.respond?options.respond(url,opts):{order:order(options.order)};},
 };
 element('merchant').value=sandbox.currentMerchant;
 for(const [id,value] of Object.entries(options.fields||{}))element(id).value=value;
 sandbox.selectMerchant=async()=>{
  selections.push(element('merchant').value);sandbox.selectionGeneration++;
  sandbox.currentMerchant=element('merchant').value;
  if(options.select)await options.select(sandbox,element);
 };
 const context=vm.createContext(sandbox);vm.runInContext(source,context,{filename:'market-checkout.js'});
 return {context,element,calls,notices,views,selections,
  async prepare(){if(!context.currentUserId)context.currentUserId=USER;await context.window.MercadoMarketCheckout.prepare();},
  fields(){return ['sale-order','sale-concept','amount','payment-method'].map(id=>element(id).value)},
 };
}

test('a database-validated accepted seller order prepares exact fields and never posts a payment',async()=>{
 const h=harness();await h.prepare();
 assert.deepEqual(h.fields(),['market-'+ORDER,'Pedido · Oferta del vendedor','123.45','codi']);
 assert.deepEqual(h.calls,[{url:'/v1/market/orders/'+ORDER,method:'GET'}]);
 assert.deepEqual(h.element('payment-method').events,['change']);
 assert.deepEqual(h.views,['caja']);assert.match(h.notices.at(-1),/Revisa el total.*único QR de pago/);
 await h.prepare();assert.equal(h.calls.length,1,'repeated ready callbacks do not repeat the lookup');
});

test('already authenticated page boot prepares only once and an unrelated URL does nothing',async()=>{
 const auto=harness({auto:true});await tick();await tick();
 assert.equal(auto.element('sale-order').value,'market-'+ORDER);assert.equal(auto.calls.length,1);
 const unrelated=harness({search:'?unrelated=1'});await unrelated.prepare();
 assert.equal(unrelated.calls.length,0);assert.deepEqual(unrelated.fields(),['','','','']);
});

test('an owned seller can be selected, while buyers and read-only seller members are refused',async()=>{
 const switchable=harness({merchant:OTHER});await switchable.prepare();
 assert.deepEqual(switchable.selections,[SELLER]);assert.equal(switchable.context.currentMerchant,SELLER);
 assert.equal(switchable.element('amount').value,'123.45');
 for(const roles of [[[OTHER,'owner']],[[SELLER,'reader']]]){
  const h=harness({roles});await h.prepare();assert.deepEqual(h.fields(),['','','','']);
  assert.match(h.notices.at(-1),/negocio vendedor/);assert.deepEqual(h.selections,[]);
 }
});

test('invalid order links never trigger a lookup',async()=>{
 for(const search of ['?market_order=bad','?market_order='+ORDER+'&market_order='+ORDER,'?market_order=']){
  const h=harness({search});await h.prepare();assert.equal(h.calls.length,0);assert.match(h.notices.at(-1),/enlace/);
 }
});

test('wrong ids, folios and malformed money from the server cannot prefill the charge',async()=>{
 for(const changes of [{id:'e'.repeat(32)},{seller_merchant_id:'not-a-merchant'},
  {checkout_order_id:'other-sale'},{total_minor:0},{total_minor:-1},{total_minor:1.1},
  {total_minor:'12345'},{total_minor:true},{total_minor:100000001},{total_minor:Number.NaN}]){
  const h=harness({order:changes});await h.prepare();assert.deepEqual(h.fields(),['','','',''],JSON.stringify(changes));
  assert.match(h.notices.at(-1),/validar/);assert.equal(h.views.length,0);
 }
});

test('unaccepted, rejected, cancelled and already paid orders do not create another payment',async()=>{
 for(const status of ['REQUESTED','REJECTED','CANCELLED','UNKNOWN']){
  const h=harness({order:{status}});await h.prepare();assert.equal(h.element('amount').value,'');
  assert.match(h.notices.at(-1),/aceptar/);
 }
 const paid=harness({order:{payment:{status:'PEY_CONFIRMED'}}});await paid.prepare();
 assert.equal(paid.element('amount').value,'');assert.match(paid.notices.at(-1),/ya tiene un pago confirmado/);
 assert(paid.calls.every(request=>request.method==='GET'));
});

test('pending checkout and each existing draft field remain untouched without querying another order',async()=>{
 for(const fields of [{'sale-order':'EXISTING'},{'sale-concept':'Venta empezada'},{amount:'9.99'}]){
  const h=harness({fields}),before=h.fields();await h.prepare();assert.deepEqual(h.fields(),before);
  assert.equal(h.calls.length,0);assert.match(h.notices.at(-1),/venta actual/);
 }
 for(const flag of ['pendingOrder','checkoutBusy','selectionBusy']){
  const h=harness();h.context[flag]=flag==='pendingOrder'?{id:'EXISTING'}:true;
  await h.prepare();assert.equal(h.calls.length,0);assert.deepEqual(h.fields(),['','','','']);
 }
});

test('a form, identity or selection changed during server lookup cannot be overwritten',async()=>{
 for(const change of [h=>h.element('amount').value='7.99',h=>h.context.selectionGeneration++,
  h=>h.context.currentUserId='f'.repeat(32),h=>h.context.currentMerchant=OTHER]){
  const response=deferred(),h=harness({respond:()=>response.promise});
  const pending=h.prepare();change(h);const before=h.fields();response.resolve({order:order()});await pending;
  assert.deepEqual(h.fields(),before);assert.match(h.notices.at(-1),/caja cambió/);assert.equal(h.views.length,0);
 }
});

test('switching to the seller preserves a recovered pending order instead of replacing it',async()=>{
 const h=harness({merchant:OTHER,select:async(context,element)=>{
  context.pendingOrder={id:'RECOVERED'};element('sale-order').value='RECOVERED';
  element('sale-concept').value='Venta recuperada';element('amount').value='55.00';
 }});
 await h.prepare();assert.deepEqual(h.fields(),['RECOVERED','Venta recuperada','55.00','']);
 assert.match(h.notices.at(-1),/solicitud guardada/);assert.equal(h.views.length,0);
 assert(h.calls.every(request=>request.method==='GET'));
});
