/* Importación conservadora: comprueba el estado persistido antes de escribir. */
(function (root, factory) {
  const api=factory();
  if(typeof module==='object' && module.exports) module.exports=api;
  root.RioCartImport=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  function importBasket(options, incoming) {
    const {bridge, core, persistence, storage, cartKey, currentSale, currentLines, restoreLock}=options;
    if (currentSale || currentLines.length || restoreLock) throw Error('Hay una venta, carrito o respaldo pendiente de revisar.');
    let sessionRaw, cartRaw, storedSession;
    try {
      sessionRaw=storage.getItem(persistence.KEY);
      storedSession=persistence.load(storage);
      if (storage.getItem(persistence.KEY)!==sessionRaw) throw Error('La sesión cambió.');
      cartRaw=storage.getItem(cartKey);
    } catch (_) { throw Error('No se pudo comprobar el almacenamiento; no se importó la cesta.'); }
    if (!storedSession || storedSession.status==='ERROR' || !storedSession.data || storedSession.data.active) {
      throw Error('Hay una venta guardada o un respaldo dañado; revísalo antes de importar.');
    }
    if (cartRaw!==null) {
      let cart;
      try { cart=JSON.parse(cartRaw); } catch (_) { throw Error('El carrito guardado está dañado; no se sobrescribirá.'); }
      if (!cart || cart.schema!=='RIO_CART_R012' || !Array.isArray(cart.lines) || cart.lines.length!==0) {
        throw Error('Hay un carrito guardado o incompatible; no se sobrescribirá.');
      }
    }
    const valid=bridge.decode(bridge.encode('basket',{lines:incoming}),'basket');
    const candidate=valid.lines.map(x=>core.calculateLine({
      description:'DEMO - '+x.name, kind:'piece', qty:String(x.quantity), price:(x.priceCents/100).toFixed(2)
    }));
    core.totalCents(candidate);
    const raw=JSON.stringify({schema:'RIO_CART_R012',lines:candidate.map(x=>({
      description:x.description,kind:x.kind,qty:String(x.quantity),price:(x.priceCents/100).toFixed(2)
    }))});
    try {
      if(storage.getItem(cartKey)!==cartRaw || storage.getItem(persistence.KEY)!==sessionRaw) {
        throw Error('El estado cambió en otra pestaña.');
      }
      storage.setItem(cartKey,raw);
      if(storage.getItem(cartKey)!==raw) throw Error('El guardado no coincide.');
    } catch (_) { throw Error('No se pudo guardar la cesta de forma comprobable; revisa el carrito.'); }
    return candidate;
  }
  return Object.freeze({importBasket});
});
