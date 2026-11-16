'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const {TextEncoder}=require('node:util');
const dir=path.resolve(__dirname,'../rio_pey_codi/static/unificada/caja');
const Core=require(path.join(dir,'caja-1.js'));
const Persistence=require(path.join(dir,'caja-4.js'));

function record(method){
  const line=Core.calculateLine({description:'Manzana',kind:'piece',qty:'2',price:'12.50'});
  const sale=Core.createSale([line],method,'DEMO-123456-001');
  return {sale,issuedAt:'2026-11-08T20:44:44.657Z',merchantName:'Prueba'};
}
function build(active,history=[]){
  const raw=Persistence.serialize({schema:Persistence.SCHEMA,active,history,updatedAt:'2026-11-08T20:44:44.657Z'});
  const store=new Map([[Persistence.KEY,raw]]);
  const storage={getItem:k=>store.has(k)?store.get(k):null,setItem:(k,v)=>store.set(k,String(v)),removeItem:k=>store.delete(k)};
  class Element{
    constructor(id=''){this.id=id;this.children=[];this.dataset={};this.classList={add(){},remove(){},toggle(){}};this.handlers={};this.value='';this.textContent='';this.hidden=false;this.disabled=false;}
    addEventListener(k,fn){this.handlers[k]=fn} setAttribute(){} append(...v){this.children.push(...v)} appendChild(v){this.children.push(v);return v} replaceChildren(...v){this.children=v} focus(){} dispatchEvent(){}
  }
  const els=new Map(),cash=new Element('cash'),qr=new Element('qr');cash.value='cash';cash.checked=true;qr.value='qr';qr.checked=false;
  const document={getElementById(id){if(!els.has(id))els.set(id,new Element(id));return els.get(id)},
    createElement:()=>new Element(),querySelectorAll:s=>s==='input[name=method]'?[cash,qr]:[],querySelector:s=>s==='input[name=method]:checked'?(cash.checked?cash:qr):null};
  const context={document,localStorage:storage,TextEncoder,console,URL,Blob,Intl,Event:class{},setTimeout,clearTimeout};
  context.window=context;context.globalThis=context;context.confirm=()=>true;
  vm.createContext(context);
  for(const name of ['caja-1.js','caja-2.js','caja-3.js','caja-4.js','caja-5.js'])vm.runInContext(fs.readFileSync(path.join(dir,name),'utf8'),context,{filename:name});
  return {cash,qr,els,store,storage,raw,context};
}
function findButton(el,label){if(el.textContent===label && el.handlers?.click)return el;for(const c of el.children||[]){const result=findButton(c,label);if(result)return result}return null;}

test('una venta QR recuperada conserva el método seleccionado y el estado de almacenamiento',()=>{
  const x=build(record('qr'));
  assert.equal(x.context.RioApp.readState().sale.method,'qr');
  assert.equal(x.qr.checked,true,'RECOVERED_METHOD_MUST_BE_QR');assert.equal(x.cash.checked,false);
  assert.match(x.els.get('cart-storage-status').textContent,/guardada|recuperada/i,'RECOVERED_STORAGE_MUST_NOT_REPORT_FAILURE');
  assert.equal(x.store.get(Persistence.KEY),x.raw);
});
test('una venta en efectivo recuperada conserva efectivo seleccionado',()=>{
  const x=build(record('cash'));assert.equal(x.cash.checked,true);assert.equal(x.qr.checked,false);
});
test('una sesión recuperada no se anuncia como almacenamiento no disponible',()=>{
  const x=build(record('qr'));
  assert.match(x.els.get('cart-storage-status').textContent,/guardada|recuperada/i,'RECOVERED_STORAGE_MUST_NOT_REPORT_FAILURE');
});
test('al recuperar un ticket histórico se actualiza el método visible',()=>{
  const x=build(null,[record('qr')]);const button=findButton(x.els.get('history-list'),'Recuperar ticket');assert(button);
  button.handlers.click();assert.equal(x.qr.checked,true,'HISTORY_METHOD_MUST_BE_QR');assert.equal(x.cash.checked,false);
});
test('al importar un respaldo también se actualiza el método visible',async()=>{
  const x=build(null),backup=Persistence.serialize({schema:Persistence.SCHEMA,active:record('qr'),history:[],updatedAt:'2026-11-08T20:44:44.657Z'});
  await x.els.get('import-backup').handlers.change({target:{files:[{size:backup.length,text:async()=>backup}],value:'x'}});
  assert.equal(x.qr.checked,true);assert.equal(x.cash.checked,false);assert.match(x.els.get('cart-storage-status').textContent,/guardada|recuperada/i);
});
test('si falla guardar un cambio de estado, el aviso ya no afirma que está guardado',()=>{
  const x=build(record('qr'));x.storage.setItem=()=>{throw Error('fallo de almacenamiento')};
  const button=findButton(x.els.get('sale-actions'),'Simular aviso correcto');assert(button);button.handlers.click();
  assert.match(x.els.get('cart-storage-status').textContent,/no se pudo comprobar/i);assert.equal(x.store.get(Persistence.KEY),x.raw);
});
