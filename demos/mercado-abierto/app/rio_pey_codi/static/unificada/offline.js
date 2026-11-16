(function(){
  'use strict';
  const status=document.getElementById('rio-offline-status');
  if(!status)return;
  const manifest=globalThis.RioOfflineManifest;
  const scope='/static/unificada/';
  async function show(){
    if(!window.isSecureContext || !('serviceWorker' in navigator) || !('caches' in window) || !manifest){
      status.textContent='Modo sin conexión no disponible en este navegador.';return;
    }
    try{
      let registration=await navigator.serviceWorker.getRegistration(scope);
      if(!registration || !registration.active){
        if(!navigator.onLine)throw Error('Primero abre la aplicación con conexión.');
        await navigator.serviceWorker.register(scope+'offline-sw.js',{scope,updateViaCache:'none'});
        let timer;
        try{
          registration=await Promise.race([navigator.serviceWorker.ready,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Sigue preparando los archivos.')),10000)})]);
        } finally { clearTimeout(timer); }
      } else if(navigator.onLine){
        navigator.serviceWorker.register(scope+'offline-sw.js',{scope,updateViaCache:'none'}).catch(()=>{});
      }
      if(!registration.active || new URL(registration.active.scriptURL).origin!==location.origin ||
         new URL(registration.active.scriptURL).pathname!==scope+'offline-sw.js')throw Error('Servicio sin conexión no reconocido.');
      const cache=await caches.open(manifest.cache);
      for(const path of Object.keys(manifest.assets))if(!await cache.match(path))throw Error('Archivos sin conexión incompletos.');
      status.textContent='Al volver a abrir un módulo, conecta Internet para comprobar tu sesión.';
    }catch(error){status.textContent='Sin conexión aún no disponible: '+String(error.message||error)}
  }
  window.addEventListener('online',show);window.addEventListener('offline',show);show();
})();
