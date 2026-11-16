'use strict';
(() => {
  const id=location.pathname.split('/').pop(), status=document.getElementById('payment-return-status');let busy=false,done=false;
  async function refresh(){if(busy||!/^\w{32}$/.test(id))return;busy=true;try{const r=await fetch('/v1/public/payments/'+encodeURIComponent(id),{signal:AbortSignal.timeout(10000)});if(!r.ok)throw Error('Estado no disponible. Intenta nuevamente.');const v=await r.json();done=v.state==='PAID';status.textContent=done?'Pago confirmado por pey':'Confirmación pendiente. No repitas el pago mientras verificamos su estado.';document.getElementById('payment-return-amount').textContent=new Intl.NumberFormat('es-MX',{style:'currency',currency:'MXN'}).format(v.amount_minor/100);if(done&&v.receipt_url){const u=new URL(v.receipt_url,location.origin);if(u.origin===location.origin&&u.pathname.startsWith('/comprobante/')){const a=document.getElementById('payment-return-receipt');a.href=u.href;a.hidden=false;}}}catch(e){status.textContent=e.message;}finally{busy=false;}}
  document.getElementById('payment-return-refresh').addEventListener('click',refresh);setInterval(()=>{if(!done&&!document.hidden)void refresh();},10000);void refresh();
})();
