(function () {
  'use strict';
  const panel=document.getElementById('rio-basket-panel');
  const status=document.getElementById('rio-basket-status');
  const cashStatus=document.getElementById('rio-sale-transfer-status');
  const money=cents => new Intl.NumberFormat('es-MX',{style:'currency',currency:'MXN'}).format(cents/100);
  let pending=null;
  try {
    const raw=sessionStorage.getItem(RioBridge.BASKET_KEY);
    if (raw !== null) {
      pending=RioBridge.decode(raw,'basket');
      panel.hidden=false;
      status.textContent=`${pending.lines.length} productos ficticios · ${money(pending.totalCents)}. El carrito actual no se reemplazará.`;
    }
  } catch (error) {
    panel.hidden=false;
    status.textContent='No se puede usar la cesta: '+String(error.message || error);
  }
  document.getElementById('rio-import-basket').addEventListener('click',() => {
    try {
      /* Releer y validar después de la vista previa, antes de cualquier escritura. */
      const value=RioBridge.decode(sessionStorage.getItem(RioBridge.BASKET_KEY),'basket');
      window.RioApp.importDemoBasket(value.lines);
      try { sessionStorage.removeItem(RioBridge.BASKET_KEY); panel.hidden=true; }
      catch (_) { status.textContent='La cesta ya se importó, pero no se pudo borrar el traslado pendiente; evita repetirlo.'; }
    } catch (error) { status.textContent='No se importó la cesta: '+String(error.message || error); }
  });
  document.getElementById('rio-dismiss-basket').addEventListener('click',() => {
    try { sessionStorage.removeItem(RioBridge.BASKET_KEY); panel.hidden=true; }
    catch (_) { status.textContent='No se pudo descartar el traslado.'; }
  });
  document.getElementById('rio-sale-to-gateway').addEventListener('click',() => {
    try {
      const sale=window.RioApp.readState().sale;
      if (!sale || sale.method!=='qr' || sale.state!=='DIGITAL_DEMO_PENDING' || sale.realPaymentConfirmed!==false) {
        throw Error('Primero crea una venta QR de práctica que esté pendiente.');
      }
      const raw=RioBridge.encode('sale',{saleId:sale.saleId,amountCents:sale.totalCents});
      const previous=sessionStorage.getItem(RioBridge.SALE_KEY);
      if(previous !== null) throw Error('Ya hay otra venta pendiente de pasar a la cuenta.');
      sessionStorage.setItem(RioBridge.SALE_KEY,raw);
      if(sessionStorage.getItem(RioBridge.SALE_KEY)!==raw) throw Error('No se pudo guardar el traslado.');
      window.location.assign('/#rio-gateway-panel');
    } catch(error) { cashStatus.textContent='No se trasladó la venta: '+String(error.message || error); }
  });
})();
