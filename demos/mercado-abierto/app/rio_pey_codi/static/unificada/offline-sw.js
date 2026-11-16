/* Sólo archivos estáticos. Las páginas siempre requieren autenticación en red. */
'use strict';
importScripts('/static/unificada/offline-manifiesto.js');
const manifest=self.RioOfflineManifest;
const assets=Object.entries(manifest.assets).filter(([path])=>!path.toLowerCase().endsWith('.html'));
const allowed=new Set(assets.map(([path])=>path));
const manifestPath='/static/unificada/offline-manifiesto.js';

self.addEventListener('install',event=>event.waitUntil((async()=>{
  const cache=await caches.open(manifest.cache);
  try {
    for(const [path,expected] of assets) {
      const response=await fetch(path,{cache:'no-store',credentials:'omit',redirect:'error'});
      if(!response.ok || response.redirected || response.url!==self.location.origin+path) throw Error('Recurso no disponible');
      const type=(response.headers.get('content-type')||'').toLowerCase();
      if((path.endsWith('.html')&&!type.startsWith('text/html')) ||
         (path.endsWith('.css')&&!type.startsWith('text/css')) ||
         (path.endsWith('.js')&&!type.includes('javascript'))) throw Error('Tipo de recurso inesperado');
      const hash=await crypto.subtle.digest('SHA-256',await response.clone().arrayBuffer());
      const actual=Array.from(new Uint8Array(hash),v=>v.toString(16).padStart(2,'0')).join('');
      if(actual!==expected) throw Error('Contenido de recurso inconsistente');
      await cache.put(path,response);
    }
  } catch(error) { await caches.delete(manifest.cache); throw error; }
})()));

self.addEventListener('activate',event=>event.waitUntil((async()=>{
  for(const key of await caches.keys()) {
    if(key.startsWith('rio-unificada-') && key!==manifest.cache) await caches.delete(key);
  }
  await self.clients.claim();
})()));

self.addEventListener('fetch',event=>{
  if(event.request.method!=='GET')return;
  let url;try{url=new URL(event.request.url)}catch(_){return}
  if(url.origin!==self.location.origin || url.search) return;
  if(event.request.mode==='navigate' || url.pathname.toLowerCase().endsWith('.html'))return;
  if(url.pathname===manifestPath) {
    const text='globalThis.RioOfflineManifest=Object.freeze('+JSON.stringify(manifest)+');\n';
    event.respondWith(Promise.resolve(new Response(text,{headers:{'content-type':'text/javascript; charset=utf-8','cache-control':'no-store'}})));
    return;
  }
  if(!allowed.has(url.pathname))return;
  event.respondWith((async()=>{
    const cache=await caches.open(manifest.cache);
    return await cache.match(url.pathname) || fetch(event.request);
  })());
});
