'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {webcrypto}=require('node:crypto');
const root=path.resolve(__dirname,'../rio_pey_codi/static/unificada');
const origin='https://rio.example';

function installed(){
  for(const name of ['offline-sw.js','offline-manifiesto.js','offline.js']) {
    assert(fs.existsSync(path.join(root,name)),`OFFLINE_ASSET_MISSING:${name}`);
  }
}
function sandboxWorker({failPath=null,tamperPath=null}={}){
  installed();const listeners={}, buckets=new Map();let network=true;
  const caches={
    async open(name){if(!buckets.has(name))buckets.set(name,new Map());const b=buckets.get(name);return {
      async put(key,value){b.set(key,value.clone())},async match(key){const r=b.get(key);return r?r.clone():undefined}
    }}, async keys(){return [...buckets.keys()]},async delete(name){return buckets.delete(name)}
  };
  const ctx={URL,Response,Request,TextEncoder,crypto:webcrypto,caches,console,
    location:{origin},clients:{claim:async()=>{}},addEventListener:(name,fn)=>{listeners[name]=fn},
    fetch:async(input)=>{
      if(!network)throw Error('OFFLINE');
      const u=new URL(typeof input==='string'?input:input.url,origin);
      if(u.pathname===failPath)return new Response('no',{status:503});
      const rel=u.pathname.replace('/static/unificada/','');
      const bytes=u.pathname===tamperPath?Buffer.from('contenido alterado'):fs.readFileSync(path.join(root,rel));
      const type=rel.endsWith('.html')?'text/html':rel.endsWith('.css')?'text/css':'text/javascript';
      const response=new Response(bytes,{status:200,headers:{'content-type':type}});
      Object.defineProperty(response,'url',{value:origin+u.pathname});return response;
    }};
  ctx.self=ctx;ctx.globalThis=ctx;
  const context=vm.createContext(ctx);
  ctx.importScripts=()=>vm.runInContext(fs.readFileSync(path.join(root,'offline-manifiesto.js'),'utf8'),context);
  vm.runInContext(fs.readFileSync(path.join(root,'offline-sw.js'),'utf8'),context);
  return {ctx,listeners,buckets,caches,setNetwork:v=>{network=v}};
}
async function dispatchWait(fn){let result;fn({waitUntil:p=>{result=p}});assert(result);return result;}
async function dispatchFetch(fn,url,method='GET'){
  let result;fn({request:{url,method},respondWith:p=>{result=p}});return result?await result:undefined;
}

test('las dos pantallas registran recursos para trabajar sin conexión',()=>{
  installed();
  for(const area of ['caja','mercado']){
    const html=fs.readFileSync(path.join(root,area,'index.html'),'utf8');
    assert.match(html,/offline-manifiesto\.js/);assert.match(html,/offline\.js/);assert.match(html,/rio-offline-status/);
  }
});
test('instalación valida archivos estáticos y nunca guarda pantallas privadas',async()=>{
  const w=sandboxWorker();await dispatchWait(w.listeners.install);
  const m=w.ctx.RioOfflineManifest;assert(m&&m.cache&&Object.keys(m.assets).length>=18);
  w.setNetwork(false);
  assert(Object.keys(m.assets).every(p=>!p.endsWith('.html')));
  for(const p of ['/static/unificada/puente.js','/static/unificada/caja/caja-1.js']){
    const response=await dispatchFetch(w.listeners.fetch,origin+p);assert(response);assert.equal(response.status,200);assert((await response.text()).length>0);
  }
  for(const p of ['/static/unificada/caja/index.html','/static/unificada/mercado/index.html']){
    assert.equal(await dispatchFetch(w.listeners.fetch,origin+p),undefined);
  }
});
test('una instalación incompleta se rechaza sin borrar otra caché',async()=>{
  const w=sandboxWorker({failPath:'/static/unificada/caja/caja-1.js'});await w.caches.open('rio-unificada-anterior');
  await assert.rejects(dispatchWait(w.listeners.install));
  assert(w.buckets.has('rio-unificada-anterior'));assert(!w.buckets.has(w.ctx.RioOfflineManifest.cache));
});
test('rechaza un archivo HTTP 200 cuando sus bytes no corresponden al manifiesto',async()=>{
  const w=sandboxWorker({tamperPath:'/static/unificada/caja/caja-1.js'});
  await assert.rejects(dispatchWait(w.listeners.install));assert(!w.buckets.has(w.ctx.RioOfflineManifest.cache));
});
test('el service worker no intercepta cuenta, API, otros orígenes ni escrituras',async()=>{
  const w=sandboxWorker();
  for(const [u,method] of [[origin+'/','GET'],[origin+'/v1/auth/me','GET'],[origin+'/api/help','POST'],['https://other.example/static/unificada/caja/index.html','GET'],[origin+'/static/unificada/caja/index.html','POST'],[origin+'/static/unificada/caja/index.html?token=private','GET']]){
    assert.equal(await dispatchFetch(w.listeners.fetch,u,method),undefined);
  }
});
test('activación borra sólo versiones anteriores de su propia caché',async()=>{
  const w=sandboxWorker();await w.caches.open('rio-unificada-anterior');await w.caches.open('otro-producto');await w.caches.open(w.ctx.RioOfflineManifest.cache);
  await dispatchWait(w.listeners.activate);
  assert(!w.buckets.has('rio-unificada-anterior'));assert(w.buckets.has('otro-producto'));assert(w.buckets.has(w.ctx.RioOfflineManifest.cache));
});
