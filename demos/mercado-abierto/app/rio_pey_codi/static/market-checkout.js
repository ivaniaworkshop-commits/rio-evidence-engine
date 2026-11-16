/* Prepare a real marketplace order for the seller's existing CoDi checkout. */
(()=>{
 'use strict';
 let attempted=false;
 const idPattern=/^[0-9a-f]{32}$/;
 const editable=()=>!checkoutBusy&&!selectionBusy&&!pendingOrder&&
   !document.getElementById('sale-order').value&&!document.getElementById('amount').value&&
   !document.getElementById('sale-concept').value.trim();
 async function prepare(){
  if(attempted)return;
  const values=new URLSearchParams(location.search).getAll('market_order');
  if(!values.length)return;
  attempted=true;
  try{
   if(values.length!==1||!idPattern.test(values[0]))throw Error('El enlace del pedido no es válido.');
   if(!editable())throw Error('Conserva la venta actual. Prepara una caja vacía antes de abrir otro pedido.');
   const user=currentUserId,merchant=currentMerchant,generation=selectionGeneration,id=values[0];
   const response=await call('/v1/market/orders/'+encodeURIComponent(id));
   const order=response.order;
   if(!order||order.id!==id||!idPattern.test(order.seller_merchant_id)||
      order.checkout_order_id!=='market-'+id||!Number.isSafeInteger(order.total_minor)||
      order.total_minor<=0||order.total_minor>100000000)
    throw Error('No se pudo validar el pedido guardado.');
   if(!['ACCEPTED','PREPARED','SHIPPED','RECEIVED'].includes(order.status))
    throw Error('El vendedor debe aceptar el pedido antes de preparar el cobro.');
   if(order.payment?.status==='PEY_CONFIRMED')throw Error('Este pedido ya tiene un pago confirmado por pey. Consulta su comprobante.');
   if(!['owner','admin','cashier'].includes(merchantRoles.get(order.seller_merchant_id)))
    throw Error('La caja del negocio vendedor debe generar la solicitud de este pedido.');
   if(user!==currentUserId||merchant!==currentMerchant||generation!==selectionGeneration||!editable())
    throw Error('La caja cambió durante la consulta. Revisa la venta actual.');
   if(currentMerchant!==order.seller_merchant_id){
    document.getElementById('merchant').value=order.seller_merchant_id;
    await selectMerchant();
   }
   if(user!==currentUserId||currentMerchant!==order.seller_merchant_id||!editable())
    throw Error('Hay una solicitud guardada en esta caja. Revisa su estado antes de preparar el pedido.');
   document.getElementById('sale-order').value=order.checkout_order_id;
   document.getElementById('sale-concept').value=('Pedido · '+(order.listing_name||id)).slice(0,140);
   document.getElementById('amount').value=(order.total_minor/100).toFixed(2);
   const method=document.getElementById('payment-method');method.value='codi';
   method.dispatchEvent(new Event('change'));
   window.RioWorkspace?.open('caja');
   notice('Pedido consolidado consultado. Este cobro incluye todos sus productos. Revisa el total y pulsa Generar QR CoDi para emitir un único QR de pago.');
  }catch(error){notice(error.message);}
 }
 window.MercadoMarketCheckout=Object.freeze({prepare});
 if(typeof currentUserId==='string'&&currentUserId&&typeof selectionBusy==='boolean'&&!selectionBusy)void prepare();
})();
