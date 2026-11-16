'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const base=path.resolve(__dirname,'../rio_pey_codi/static/unificada');
const bridge=require(path.join(base,'puente.js'));
const importer=require(path.join(base,'caja/carrito-import.js'));
const core=require(path.join(base,'caja/caja-1.js'));
const persistence=require(path.join(base,'caja/caja-4.js'));
const clock=1700000000000;
const lines=[{name:'ARROZ 1KG',quantity:4,priceCents:3500},{name:'LECHE 1L',quantity:8,priceCents:3000}];
const sale={saleId:'DEMO-123456-001',amountCents:38000};
function storage(initial={}) { const x=new Map(Object.entries(initial)); return {getItem:k=>x.has(k)?x.get(k):null,setItem:(k,v)=>x.set(k,String(v)),removeItem:k=>x.delete(k),dump:()=>Object.fromEntries(x)}; }
function element(){ return {hidden:false,disabled:false,textContent:'',value:'',handlers:{},addEventListener(event,fn){this.handlers[event]=fn;}}; }
function page(file,globals,ids){const dom=Object.fromEntries(ids.map(x=>[x,element()]));const sandbox={...globals,document:{getElementById:id=>dom[id]}};sandbox.globalThis=sandbox;vm.runInNewContext(readFileSync(path.join(base,file),'utf8'),sandbox);return {dom,sandbox};}

test('cesta sintética conserva productos e importe en centavos',()=>{
 const raw=bridge.encode('basket',{lines},clock), out=bridge.decode(raw,'basket',clock);
 assert.deepEqual(out.lines,lines);assert.equal(out.totalCents,38000);
});
test('venta transfiere folio e importe, sin estado de pago ni secretos',()=>{
 const raw=bridge.encode('sale',sale,clock);
 assert.deepEqual(bridge.decode(raw,'sale',clock),sale);
 assert(!raw.includes('confirmed'));assert(!raw.includes('password'));
});
test('caducidad, futuro excesivo, tipo y clasificación se rechazan',()=>{
 const raw=bridge.encode('sale',sale,clock);
 assert.throws(()=>bridge.decode(raw,'sale',clock+bridge.MAX_AGE_MS+1));
 assert.throws(()=>bridge.decode(raw,'sale',clock-30001));
 assert.throws(()=>bridge.decode(raw,'basket',clock));
 const bad=JSON.parse(raw);bad.classification='REAL';assert.throws(()=>bridge.decode(JSON.stringify(bad),'sale',clock));
});
test('rechaza importes, folios y contenido extra ajenos al contrato',()=>{
 for(const x of [0,-1,1.5,Number.MAX_SAFE_INTEGER]) assert.throws(()=>bridge.encode('sale',{...sale,amountCents:x},clock));
 assert.throws(()=>bridge.encode('sale',{...sale,saleId:'REAL-12345'},clock));
 assert.throws(()=>bridge.encode('sale',{...sale,password:'x'},clock));
 assert.throws(()=>bridge.decode('{','sale',clock));
 assert.throws(()=>bridge.decode('x'.repeat(16001),'sale',clock));
 assert.throws(()=>bridge.encode('basket',{lines:[{...lines[0],name:'<script>'}]},clock));
 assert.throws(()=>bridge.encode('basket',{lines:[{...lines[0],quantity:0}]},clock));
 assert.throws(()=>bridge.encode('basket',{lines:Array(31).fill(lines[0])},clock));
});
test('Mercado prepara cesta sin pisar una pendiente',()=>{
 const session=storage(), location={assign(v){this.url=v}};
 const fixture={scenario:{basket:[{sku:'ARROZ_1KG',qty:4,retail_unit:35}]}};
 const {dom}=page('mercado/integracion.js',{RIO_BOOTSTRAP:fixture,RioBridge:bridge,sessionStorage:session,window:{location}},['rio-basket-to-cash','rio-market-transfer-status']);
 dom['rio-basket-to-cash'].handlers.click();
 assert.equal(location.url,'/static/unificada/caja/index.html');
 const raw=session.getItem(bridge.BASKET_KEY);assert.equal(bridge.decode(raw,'basket').totalCents,14000);
 location.url='';dom['rio-basket-to-cash'].handlers.click();
 assert.equal(location.url,'');assert.equal(session.getItem(bridge.BASKET_KEY),raw);assert.match(dom['rio-market-transfer-status'].textContent,/pendiente/);
});
test('Caja requiere acción para importar y conserva el traslado si la caja está ocupada',()=>{
 const session=storage({[bridge.BASKET_KEY]:bridge.encode('basket',{lines})});let imports=0;
 const app={importDemoBasket:()=>{imports++;throw Error('Caja ocupada');},readState:()=>({sale:null})};
 const {dom}=page('caja/integracion.js',{RioBridge:bridge,sessionStorage:session,window:{RioApp:app,location:{}},Intl},['rio-basket-panel','rio-basket-status','rio-sale-transfer-status','rio-import-basket','rio-dismiss-basket','rio-sale-to-gateway']);
 assert.equal(imports,0);assert.equal(dom['rio-basket-panel'].hidden,false);
 dom['rio-import-basket'].handlers.click();assert.equal(imports,1);assert(session.getItem(bridge.BASKET_KEY));assert.match(dom['rio-basket-status'].textContent,/ocupada/);
});
test('Caja informa si importa pero no puede borrar el traslado',()=>{
 const session=storage({[bridge.BASKET_KEY]:bridge.encode('basket',{lines})});session.removeItem=()=>{throw Error('blocked')};let imports=0;
 const app={importDemoBasket:()=>{imports++;},readState:()=>({sale:null})};
 const {dom}=page('caja/integracion.js',{RioBridge:bridge,sessionStorage:session,window:{RioApp:app,location:{}},Intl},['rio-basket-panel','rio-basket-status','rio-sale-transfer-status','rio-import-basket','rio-dismiss-basket','rio-sale-to-gateway']);
 dom['rio-import-basket'].handlers.click();assert.equal(imports,1);assert(session.getItem(bridge.BASKET_KEY));assert.match(dom['rio-basket-status'].textContent,/ya se importó/);
});
test('Caja sólo traslada QR pendiente y no pisa otra venta',()=>{
 const session=storage(), loc={assign(v){this.url=v}}, state={sale:{...sale,totalCents:sale.amountCents,method:'qr',state:'DIGITAL_DEMO_PENDING',realPaymentConfirmed:false}};
 const app={readState:()=>state};
 const {dom}=page('caja/integracion.js',{RioBridge:bridge,sessionStorage:session,window:{RioApp:app,location:loc},Intl},['rio-basket-panel','rio-basket-status','rio-sale-transfer-status','rio-import-basket','rio-dismiss-basket','rio-sale-to-gateway']);
 dom['rio-sale-to-gateway'].handlers.click();assert.equal(loc.url,'/#rio-gateway-panel');const raw=session.getItem(bridge.SALE_KEY);
 loc.url='';dom['rio-sale-to-gateway'].handlers.click();assert.equal(loc.url,'');assert.equal(session.getItem(bridge.SALE_KEY),raw);
 session.removeItem(bridge.SALE_KEY);state.sale.realPaymentConfirmed=true;dom['rio-sale-to-gateway'].handlers.click();assert.equal(session.getItem(bridge.SALE_KEY),null);
});
test('importación conserva centavos, etiquetas DEMO y carrito persistido',()=>{
 const s=storage();const opts={bridge,core,persistence,storage:s,cartKey:'cart',currentSale:null,currentLines:[],restoreLock:false};
 const result=importer.importBasket(opts,lines);
 assert.equal(core.totalCents(result),38000);assert(result.every(x=>x.description.startsWith('DEMO - ')));
 assert.equal(JSON.parse(s.getItem('cart')).lines.length,2);
 assert.throws(()=>importer.importBasket(opts,lines));
});
test('el carrito guardado por otra pestaña o corrupto no se sobrescribe',()=>{
 for(const previous of ['{bad',JSON.stringify({schema:'RIO_CART_R012',lines:[{description:'Existente'}]})]) {
  const s=storage({cart:previous});const opts={bridge,core,persistence,storage:s,cartKey:'cart',currentSale:null,currentLines:[],restoreLock:false};
  assert.throws(()=>importer.importBasket(opts,lines));assert.equal(s.getItem('cart'),previous);
 }
});
test('venta activa o copia de sesión dañada impide importar sin alterar datos',()=>{
 const line=core.calculateLine({description:'ejemplo',kind:'piece',qty:'1',price:'1.00'});
 const current=core.createSale([line],'qr','DEMO-12345');
 const active={schema:persistence.SCHEMA,active:{sale:current,issuedAt:'2026-11-08T12:00:00.000Z',merchantName:'Demo'},history:[],updatedAt:'2026-11-08T12:00:00.000Z'};
 for(const prior of ['{damaged',persistence.serialize(active)]) {
  const s=storage({[persistence.KEY]:prior});const opts={bridge,core,persistence,storage:s,cartKey:'cart',currentSale:null,currentLines:[],restoreLock:false};
  assert.throws(()=>importer.importBasket(opts,lines));assert.equal(s.getItem(persistence.KEY),prior);assert.equal(s.getItem('cart'),null);
 }
});
test('si el guardado falla no se devuelve una importación exitosa',()=>{
 const s=storage();s.setItem=()=>{throw Error('blocked')};
 const opts={bridge,core,persistence,storage:s,cartKey:'cart',currentSale:null,currentLines:[],restoreLock:false};
 assert.throws(()=>importer.importBasket(opts,lines));assert.equal(s.getItem('cart'),null);
});
test('una actualización observada durante la importación cancela la escritura',()=>{
 const s=storage(), get=s.getItem;let reads=0, writes=0;
 s.getItem=k=>k==='cart' && ++reads>=2 ? '{"schema":"RIO_CART_R012","lines":[{"description":"otra pestaña"}]}' : get(k);
 s.setItem=()=>{writes++};
 const opts={bridge,core,persistence,storage:s,cartKey:'cart',currentSale:null,currentLines:[],restoreLock:false};
 assert.throws(()=>importer.importBasket(opts,lines));assert.equal(writes,0);
});
test('Gateway copia sólo en modo demo y nunca envía solicitud automática',async()=>{
 const session=storage({[bridge.SALE_KEY]:bridge.encode('sale',sale)});let fetches=[];
 const ids=['rio-gateway-panel','rio-gateway-transfer-status','rio-gateway-import','rio-gateway-dismiss','sale-order','sale-concept','amount'];
 const {dom}=page('cuenta.js',{RioBridge:bridge,sessionStorage:session,currentUserId:'u1',currentMerchant:'m1',selectionBusy:false,pendingOrder:null,fetch:async(url)=>{fetches.push(url);return {ok:true,json:async()=>({mode:'DEMO',live_payments_enabled:false})}}},ids);
 assert.equal(dom['sale-order'].value,'');assert.deepEqual(fetches,[]);
 await dom['rio-gateway-import'].handlers.click();
 assert.equal(dom['sale-order'].value,sale.saleId);assert.equal(dom.amount.value,'380.00');assert.equal(session.getItem(bridge.SALE_KEY),null);
 assert.deepEqual(fetches,['/public-status']);assert.match(dom['rio-gateway-transfer-status'].textContent,/No se creó una solicitud/);
});
test('Gateway rechaza modo real, orden pendiente y no reemplaza el formulario',async()=>{
 for(const mode of ['live','pending','filled']) {
  const raw=bridge.encode('sale',sale),session=storage({[bridge.SALE_KEY]:raw});let fetches=0;
  const ids=['rio-gateway-panel','rio-gateway-transfer-status','rio-gateway-import','rio-gateway-dismiss','sale-order','sale-concept','amount'];
  const {dom}=page('cuenta.js',{RioBridge:bridge,sessionStorage:session,currentUserId:'u1',currentMerchant:'m1',selectionBusy:false,pendingOrder:mode==='pending'?{id:'old'}:null,fetch:async()=>{fetches++;return {ok:true,json:async()=>({mode:'LIVE',live_payments_enabled:true})}}},ids);
  if(mode==='filled')dom.amount.value='12.34';
  await dom['rio-gateway-import'].handlers.click();assert.equal(session.getItem(bridge.SALE_KEY),raw);assert.equal(dom['sale-order'].value,'');
  assert.equal(dom.amount.value,mode==='filled'?'12.34':'');
  assert.equal(fetches,mode==='live'?1:0);
 }
});
test('Gateway no rellena el formulario si no puede retirar el traslado',async()=>{
 const session=storage({[bridge.SALE_KEY]:bridge.encode('sale',sale)});session.removeItem=()=>{throw Error('blocked')};
 const ids=['rio-gateway-panel','rio-gateway-transfer-status','rio-gateway-import','rio-gateway-dismiss','sale-order','sale-concept','amount'];
 const {dom}=page('cuenta.js',{RioBridge:bridge,sessionStorage:session,currentUserId:'u1',currentMerchant:'m1',selectionBusy:false,pendingOrder:null,fetch:async()=>({ok:true,json:async()=>({mode:'DEMO',live_payments_enabled:false})})},ids);
 await dom['rio-gateway-import'].handlers.click();assert.equal(dom['sale-order'].value,'');assert.equal(dom.amount.value,'');assert(session.getItem(bridge.SALE_KEY));
});
test('Gateway preserva un concepto ya escrito por la persona',async()=>{
 const raw=bridge.encode('sale',sale),session=storage({[bridge.SALE_KEY]:raw});let fetches=0;
 const ids=['rio-gateway-panel','rio-gateway-transfer-status','rio-gateway-import','rio-gateway-dismiss','sale-order','sale-concept','amount'];
 const {dom}=page('cuenta.js',{RioBridge:bridge,sessionStorage:session,currentUserId:'u1',currentMerchant:'m1',selectionBusy:false,pendingOrder:null,fetch:async()=>{fetches++;return {ok:true,json:async()=>({mode:'DEMO',live_payments_enabled:false})}}},ids);
 dom['sale-concept'].value='Concepto escrito';await dom['rio-gateway-import'].handlers.click();
 assert.equal(dom['sale-concept'].value,'Concepto escrito','CUSTOM_CONCEPT_MUST_NOT_BE_OVERWRITTEN');
 assert.equal(session.getItem(bridge.SALE_KEY),raw);assert.equal(fetches,0);
});
test('Gateway cancela si el concepto cambia durante la comprobación',async()=>{
 const raw=bridge.encode('sale',sale),session=storage({[bridge.SALE_KEY]:raw});let dom;
 const ids=['rio-gateway-panel','rio-gateway-transfer-status','rio-gateway-import','rio-gateway-dismiss','sale-order','sale-concept','amount'];
 const built=page('cuenta.js',{RioBridge:bridge,sessionStorage:session,currentUserId:'u1',currentMerchant:'m1',selectionBusy:false,pendingOrder:null,fetch:async()=>({ok:true,json:async()=>{dom['sale-concept'].value='Editado mientras esperaba';return {mode:'DEMO',live_payments_enabled:false}}})},ids);dom=built.dom;
 await dom['rio-gateway-import'].handlers.click();assert.equal(dom['sale-concept'].value,'Editado mientras esperaba','CONCURRENT_CONCEPT_MUST_NOT_BE_OVERWRITTEN');
 assert.equal(session.getItem(bridge.SALE_KEY),raw);assert.equal(dom['sale-order'].value,'');
});
