/* RÍO Primer Cobro R014. Validated local snapshot, not independent payment evidence. */
(function(root,factory){const api=factory(root.RioCore || (typeof require==='function'?require('./logic.js'):null));if(typeof module==='object'&&module.exports)module.exports=api;root.RioPersistence=api;})(typeof globalThis!=='undefined'?globalThis:this,function(C){
'use strict';
const KEY='RIO_PRIMER_COBRO_R014_SESSION_V1', SCHEMA='RIO_PRIMER_COBRO_R014_SESSION_V1', MAX_HISTORY=50, MAX_JSON_BYTES=400000;
function check(ok,message){if(!ok)throw new Error(message)}
function own(o,k){return Object.prototype.hasOwnProperty.call(o,k)}
function normalizeName(name){check(typeof name==='string'&&name.length<=60,'Nombre de comercio inválido');return name.replace(/[\r\n\t\x00-\x1f]/g,' ').trim()}
function normalizeTime(t){check(typeof t==='string'&&/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(t)&&!Number.isNaN(Date.parse(t)),'Fecha inválida');return new Date(t).toISOString()}
function normalizeSale(src){
 check(src&&typeof src==='object'&&!Array.isArray(src)&&src.schema==='RIO_PRIMER_COBRO_R010_SALE','Esquema de venta inválido');
 check(src.mode==='SIMULATION_LOCAL'&&src.realPaymentConfirmed===false,'No se permite acreditar pagos reales mediante un respaldo local');
 check(src.method==='cash'||src.method==='qr','Método de cobro inválido');
 check(Array.isArray(src.lines)&&src.lines.length>=1&&src.lines.length<=30,'Productos fuera del límite');
 const lines=src.lines.map(l=>{
  check(l&&typeof l==='object'&&Number.isSafeInteger(l.quantity)&&Number.isSafeInteger(l.priceCents)&&Number.isSafeInteger(l.amountCents),'Producto no verificable');
  const rebuilt=C.calculateLine({description:l.description,kind:l.kind,qty:String(l.quantity),price:(l.priceCents/100).toFixed(2)});
  check(['description','kind','quantity','priceCents','amountCents'].every(k=>rebuilt[k]===l[k]),'Producto no coincide con el cálculo');return rebuilt;
 });
 let restored=C.createSale(lines,src.method,src.saleId);
 check(restored.totalCents===src.totalCents,'Total de venta alterado');
 check(Array.isArray(src.events)&&src.events.length<=8,'Eventos de venta inválidos');
 for(const event of src.events){
  check(event&&typeof event==='object'&&typeof event.type==='string','Evento sin tipo');
  let input;
  if(event.type==='CASH_USER_SAYS_RECEIVED')input={type:event.type,receivedCents:src.cashReceivedCents};
  else if(event.type==='DEMO_CONFIRM')input={type:event.type,demoOnly:true,provider:'LOCAL_SIMULATOR_R010',saleId:src.saleId,amountCents:src.totalCents};
  else if(event.type==='DEMO_DISCONNECT'||event.type==='DEMO_RECONNECT')input={type:event.type};
  else throw new Error('Evento no permitido en respaldo');
  const applied=C.applyEvent(restored,input);check(applied.accepted,'Evento de venta inválido');
  const rebuiltEvent=applied.sale.events.at(-1);
  check(rebuiltEvent.type===event.type&&rebuiltEvent.result===event.result&&rebuiltEvent.origin===event.origin,'Procedencia o resultado de evento alterado');restored=applied.sale;
 }
 check(restored.state===src.state,'Estado de venta no coincide con sus eventos');
 check((restored.cashReceivedCents??null)===(src.cashReceivedCents??null),'Efectivo declarado no corresponde');
 check((restored.changeCents??null)===(src.changeCents??null),'Cambio no corresponde');
 return restored;
}
function normalizeRecord(raw){
 check(raw&&typeof raw==='object'&&!Array.isArray(raw),'Registro de venta inválido');
 const sale=normalizeSale(raw.sale), issuedAt=normalizeTime(raw.issuedAt), merchantName=normalizeName(raw.merchantName);
 return {sale,issuedAt,merchantName};
}
function normalizeSession(raw){
 check(raw&&typeof raw==='object'&&!Array.isArray(raw)&&raw.schema===SCHEMA,'Esquema de respaldo desconocido');
 check(Array.isArray(raw.history)&&raw.history.length<=MAX_HISTORY,'Historial excede el límite de 50 ventas');
 check(raw.active===null||raw.active&&typeof raw.active==='object','Venta activa inválida');
 const active=raw.active?normalizeRecord(raw.active):null;
 const history=raw.history.map(normalizeRecord);
 const ids=new Set();for(const r of [...history,...(active?[active]:[])]){check(!ids.has(r.sale.saleId),'Folio duplicado en respaldo');ids.add(r.sale.saleId)}
 return {schema:SCHEMA,active,history,updatedAt:normalizeTime(raw.updatedAt)};
}
function serialize(session){const canonical=normalizeSession(session),raw=JSON.stringify(canonical);check(new TextEncoder().encode(raw).length<=MAX_JSON_BYTES,'Respaldo demasiado grande');return raw}
function empty(){return {schema:SCHEMA,active:null,history:[],updatedAt:new Date().toISOString()}}
function save(storage,session){const raw=serialize(session);storage.setItem(KEY,raw);return {saved:true,bytes:new TextEncoder().encode(raw).length}}
function load(storage){try{const raw=storage.getItem(KEY);if(raw===null)return {status:'EMPTY',data:empty()};check(raw.length<=MAX_JSON_BYTES,'Respaldo supera tamaño permitido');return {status:'OK',data:normalizeSession(JSON.parse(raw))}}catch(error){return {status:'ERROR',message:String(error.message||error)}}}
function importJSON(raw){check(typeof raw==='string'&&raw.length<=MAX_JSON_BYTES,'Archivo excede el límite');return normalizeSession(JSON.parse(raw))}
function archive(session,record){const n=normalizeSession(session);const clean=normalizeRecord(record);const previous=n.history.filter(x=>x.sale.saleId!==clean.sale.saleId);return {schema:SCHEMA,active:null,history:[clean,...previous].slice(0,MAX_HISTORY),updatedAt:new Date().toISOString()}}
return {KEY,SCHEMA,MAX_HISTORY,MAX_JSON_BYTES,empty,save,load,serialize,importJSON,normalizeSession,normalizeRecord,normalizeSale,archive};
});
