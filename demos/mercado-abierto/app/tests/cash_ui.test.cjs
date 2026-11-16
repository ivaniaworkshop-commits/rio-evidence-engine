'use strict';
const test=require('node:test');const assert=require('node:assert/strict');
const C=require('../rio_pey_codi/static/cash-ui.js');
const scope=C.scope('a'.repeat(32),'b'.repeat(32));
const item=C.line({name:'Arroz',price:'19.99',qty:'3',unit:'piece'});
const record=()=>C.sale({id:'CASH-12345678-0000',createdAt:'2026-11-13T12:00:00Z',folio:'VENTA-1',concept:'Arroz',amountMinor:5997,receivedMinor:6000,lines:[item]});
test('cart keeps exact cents for pieces and fractional kilograms',()=>{
 assert.equal(item.amountCents,5997);
 assert.equal(C.line({name:'Manzana',price:'12.50',qty:'0.250',unit:'kg'}).amountCents,313);
 assert.equal(C.grams('1.005'),1005);
 assert.equal(C.sum([item,C.line({name:'Agua',price:'0.29',qty:'2',unit:'piece'})]),6055);
});
test('rejects ambiguous quantities, negative cash and overflow',()=>{
 for(const qty of ['0','-1','1.0001','1e3'])assert.throws(()=>C.line({name:'Peso',price:'10',qty,unit:'kg'}));
 for(const price of ['-10','1e4','1000000.01'])assert.throws(()=>C.amount(price));
 assert.throws(()=>C.sale({...record(),receivedMinor:5000}));
});
test('cash record calculates change and never marks a bank payment',()=>{
 const sale=record();assert.equal(sale.changeMinor,3);assert.equal(sale.bankPaymentConfirmed,false);
 assert.equal(sale.source,'USER_DECLARED_CASH');assert.equal(sale.paymentMethod,'cash');
 const text=C.ticket(sale,'Local\nInyección');assert(text.includes('No es CFDI'));assert(text.includes('EFECTIVO REGISTRADO MANUALMENTE'));assert(!text.includes('Local\nInyección'));
});
test('backup persists and round trips only in the same user and business scope',()=>{
 const text=C.encode([record()],scope);assert.deepEqual(C.decode(text,scope),[record()]);
 assert.throws(()=>C.decode(text,C.scope('c'.repeat(32),scope.merchant)),/otra cuenta/);
 assert.throws(()=>C.decode(text,C.scope(scope.user,'d'.repeat(32))),/otra cuenta/);
 assert.notEqual(C.storageKey(scope),C.storageKey(C.scope(scope.user,'d'.repeat(32))));
});
test('rejects imported payment confirmations and tampered totals',()=>{
 const raw=C.payload([record()],scope);raw.sales[0].bankPaymentConfirmed=true;assert.throws(()=>C.decode(JSON.stringify(raw),scope));
 const changed=C.payload([record()],scope);changed.sales[0].amountMinor=1;assert.throws(()=>C.decode(JSON.stringify(changed),scope));
 const badChange=C.payload([record()],scope);badChange.sales[0].changeMinor=500;assert.throws(()=>C.decode(JSON.stringify(badChange),scope));
});
test('reimport is idempotent and conflicting folios fail without overwriting',()=>{
 const existing=[record()];assert.equal(C.merge(existing,[record()]).length,1);
 assert.throws(()=>C.merge(existing,[{...record(),concept:'Conflicting'}]),/datos diferentes/);
 assert.equal(existing[0].concept,'Arroz');
});
test('unknown imported properties cannot enter restored records',()=>{
 const raw=C.payload([record()],scope);raw.sales[0].api_key='must-not-return';raw.sales[0].provider_status='PAID';
 const restored=C.decode(JSON.stringify(raw),scope)[0];assert(!('api_key' in restored));assert(!('provider_status' in restored));
});
test('stale tab cannot overwrite another tab record or import',()=>{
 const values=new Map(),storage={getItem:key=>values.get(key)??null,setItem:(key,text)=>values.set(key,text)};
 const first=record(),second=C.sale({...record(),id:'CASH-87654321-0000',folio:'VENTA-2'});
 const tabA=storage.getItem(C.storageKey(scope)),tabB=storage.getItem(C.storageKey(scope));
 const latest=C.commit(storage,scope,tabA,[first]);
 assert.throws(()=>C.commit(storage,scope,tabB,[second]),/otra pestaña/,'stale recording is refused');
 assert.equal(storage.getItem(C.storageKey(scope)),latest,'newer bytes are preserved');
 const imported=C.decode(C.encode([second],scope),scope);
 assert.throws(()=>C.commit(storage,scope,tabB,C.merge([],imported)),/otra pestaña/,'stale import is refused');
 assert.equal(storage.getItem(C.storageKey(scope)),latest);
 const refreshed=C.decode(latest,scope);
 C.commit(storage,scope,latest,C.merge(refreshed,imported));
 assert.deepEqual(C.decode(storage.getItem(C.storageKey(scope)),scope),[first,second],'refreshing keeps both records');
});
test('server save requires exact database readback before confirming success',async()=>{
 const item=record(),calls=[];
 const saved={...item,persisted:true,recordedAt:'2026-11-14T12:00:00Z'};
 const response=await C.saveRemote(async(path,options={})=>{calls.push({path,method:options.method||'GET'});return options.method==='POST'?{sale:saved,persisted:true}:{sale:saved}},scope.merchant,item);
 assert.equal(response.persisted,true);assert.deepEqual(calls.map(x=>x.method),['POST','GET']);
 assert(calls[1].path.endsWith('/'+item.id));
 await assert.rejects(C.saveRemote(async(_path,options={})=>options.method==='POST'?{persisted:true}:{sale:{...saved,amountMinor:1}},scope.merchant,item),/datos diferentes|productos no coinciden/i);
 await assert.rejects(C.saveRemote(async(_path,options={})=>options.method==='POST'?{persisted:true}:{sale:{...saved,persisted:false}},scope.merchant,item),/comprobar/);
});
test('an offline or uncertain write is not success; retry keeps the same idempotent folio',async()=>{
 const item=record();let database=null,postIds=[];
 const transport=async(_path,options={})=>{
  if(options.method==='POST'){postIds.push(options.body.id);if(!database){database={...options.body,persisted:true};throw Error('Timeout after commit')}return {sale:database,persisted:true,replayed:true}}
  return {sale:database};
 };
 const readback=await C.saveRemote(transport,scope.merchant,item);
 assert.equal(readback.id,item.id,'post-timeout readback proves existing record');
 const replay=await C.saveRemote(transport,scope.merchant,item);
 assert.equal(replay.id,item.id);assert.deepEqual(postIds,[item.id,item.id]);
 await assert.rejects(C.saveRemote(async()=>{throw Error('Offline')},scope.merchant,item),/Offline/);
});
