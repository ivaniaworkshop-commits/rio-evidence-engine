(function () {
  'use strict';
  const panel=document.getElementById('rio-gateway-panel');
  const status=document.getElementById('rio-gateway-transfer-status');
  function refresh() {
    try {
      const raw=sessionStorage.getItem(RioBridge.SALE_KEY);
      panel.hidden=raw===null;
      if(raw!==null) {
        const sale=RioBridge.decode(raw,'sale');
        status.textContent=`Folio ${sale.saleId} · ${(sale.amountCents/100).toFixed(2)} MXN. Entra a tu comercio y copia los datos; no se creará ninguna solicitud automáticamente.`;
      }
    } catch(error) { panel.hidden=false;status.textContent='No se puede usar el traslado: '+String(error.message || error); }
  }
  document.getElementById('rio-gateway-import').addEventListener('click',async () => {
    const button=document.getElementById('rio-gateway-import');
    button.disabled=true;
    try {
      const original=sessionStorage.getItem(RioBridge.SALE_KEY);
      const sale=RioBridge.decode(original,'sale');
      if (typeof currentUserId === 'undefined' || !currentUserId || !currentMerchant || selectionBusy) {
        throw Error('Inicia sesión y espera a que termine de cargar tu comercio.');
      }
      if (pendingOrder) throw Error('Hay una solicitud pendiente; revísala antes de continuar.');
      const conceptBefore=document.getElementById('sale-concept').value;
      if (document.getElementById('sale-order').value || document.getElementById('amount').value ||
          (conceptBefore!=='' && conceptBefore!=='Venta de ejemplo')) {
        throw Error('El formulario ya tiene datos; revísalos antes de copiar otros.');
      }
      const user=currentUserId, merchant=currentMerchant;
      const response=await fetch('/public-status',{cache:'no-store'});
      if (!response.ok) throw Error('No se pudo verificar el modo del servicio.');
      const mode=await response.json();
      if (mode.mode!=='DEMO' || mode.live_payments_enabled!==false) throw Error('El traslado sólo se permite en modo DEMO sin pagos reales.');
      if (currentUserId!==user || currentMerchant!==merchant || selectionBusy || pendingOrder ||
          document.getElementById('sale-order').value || document.getElementById('amount').value ||
          document.getElementById('sale-concept').value!==conceptBefore ||
          sessionStorage.getItem(RioBridge.SALE_KEY)!==original) throw Error('El estado cambió durante la comprobación. Inténtalo de nuevo.');
      /* Validar también la caducidad después de la operación asíncrona. */
      RioBridge.decode(original,'sale');
      sessionStorage.removeItem(RioBridge.SALE_KEY);
      document.getElementById('sale-order').value=sale.saleId;
      document.getElementById('sale-concept').value='Venta local de práctica';
      document.getElementById('amount').value=(sale.amountCents/100).toFixed(2);
      status.textContent='Datos copiados al formulario. No se creó una solicitud y no se confirmó ningún pago.';
    } catch(error) { status.textContent=String(error.message || error); }
    finally { button.disabled=false; }
  });
  document.getElementById('rio-gateway-dismiss').addEventListener('click',() => {
    try { sessionStorage.removeItem(RioBridge.SALE_KEY); panel.hidden=true; }
    catch (_) { status.textContent='No se pudo descartar el traslado.'; }
  });
  refresh();
})();
