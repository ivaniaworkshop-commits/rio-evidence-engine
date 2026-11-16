'use strict';
(() => {
  let generation = 0, busy = false, cursor = null, txCursor = null;
  const id = () => crypto.randomUUID().replaceAll('-', '');
  const labels = {PENDING:'Pendiente', PROCESSING:'En proceso', PARTIAL:'Pago parcial', PAID:'Pago confirmado por pey', ACTIVE:'CoDi habilitado', ERROR:'Error de registro', UNCERTAIN:'Resultado incierto: consulta pey antes de repetir', SUBMITTING:'Solicitud en proceso', REJECTED:'pey rechazó la solicitud', UPDATED:'Importe actualizado', UPDATE_UNCERTAIN:'Cambio de importe sin confirmar'};
  const ctx = () => {if (!currentMerchant) throw Error('Selecciona un negocio'); return {merchant:currentMerchant,user:currentUserId,g:generation,path:'/v1/merchants/'+encodeURIComponent(currentMerchant)};};
  const valid = c => c.g===generation && c.merchant===currentMerchant && c.user===currentUserId;
  const cents = value => {if(!/^\d+(\.\d{1,2})?$/.test(value)) throw Error('Indica pesos con hasta dos decimales'); const [a,b='']=value.split('.'); const n=Number(a)*100+Number(b.padEnd(2,'0')); if(!Number.isSafeInteger(n)||n<1||n>100000000) throw Error('Importe fuera de rango'); return n;};
  const money = n => new Intl.NumberFormat('es-MX',{style:'currency',currency:'MXN'}).format(n/100);
  function button(text, handler) {const b=document.createElement('button'); b.type='button'; b.className='outline'; b.textContent=text; b.addEventListener('click',handler); return b;}
  async function work(target, action) {
    if(busy)return;
    let c; try{c=ctx();}catch(e){$(target).textContent=e.message;return;}
    busy=true;
    try{await action(c);}catch(e){if(valid(c))$(target).textContent=e.message;}
    finally{busy=false;}
  }
  function render(row,c) {
    const li=document.createElement('li');
    li.textContent=(row.kind==='BANK'?'Cuenta':row.kind==='PUSH'?'Celular':row.kind==='LINK'?'Enlace':'Cambio de importe')+' · '+(labels[row.state]||row.state)+(row.amount_minor?' · '+money(row.amount_minor):'')+' · '+(row.provider_id||row.id)+' ';
    const details=row.result||{};
    if(details.clabe_masked)li.append(document.createTextNode(' '+(details.alias||'')+' '+details.clabe_masked+' '));
    if(details.url){try{const u=new URL(details.url);if(u.protocol==='https:'&&['app.mipey.mx','app.pey.mx'].includes(u.hostname)){const a=document.createElement('a');a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';a.textContent='Abrir enlace de pago';li.append(a);}}catch{}}
    if(row.state==='PAID'&&row.intent_id)li.append(button('Ver comprobante',()=>work('pey-op-status',async snap=>{if(!valid(c))return;const r=await call('/v1/checkout/qr/'+row.intent_id+'/receipt');if(valid(snap)&&r.link){const u=new URL(r.link,location.origin);if(u.origin===location.origin)location.assign(u.href);}})));
    if(['UNCERTAIN','SUBMITTING'].includes(row.state)&&!row.provider_id&&row.kind!=='LINK_UPDATE'&&merchantRoles.get(currentMerchant)==='owner') {
      const resource=document.createElement('input');resource.setAttribute('aria-label','Identificador encontrado en pey');resource.placeholder='ID del recurso en pey';li.append(resource);
      li.append(button('Recuperar sin repetir',()=>work('pey-op-status',async snap=>{if(!valid(c))return;const r=await call(snap.path+'/pey-operations/'+row.id+'/recover?provider_id='+encodeURIComponent(resource.value.trim()),{method:'POST',write:true});if(valid(snap)){$('pey-op-status').textContent=labels[r.state]||r.state;await load(snap);}})));
    }
    if(row.provider_id&&row.kind!=='LINK_UPDATE')li.append(button('Consultar estado',()=>work(row.kind==='BANK'?'pey-bank-status':'pey-op-status',async snap=>{if(!valid(c))return;const result=await call(snap.path+'/pey-operations/'+row.id+'/refresh',{method:'POST',write:true});if(valid(snap)){(row.kind==='BANK'?$('pey-bank-status'):$('pey-op-status')).textContent=labels[result.state]||result.state;await load(snap);}})));
    if(row.kind==='BANK'&&row.state==='ACTIVE'&&!row.locally_archived)li.append(button('Usar esta cuenta',()=>{if(!valid(c))return;$('private-pey-bank').value=row.provider_id;$('private-pey-default-bank').checked=false;$('private-pey-bank').disabled=false;$('pey-bank-status').textContent='Cuenta seleccionada. Guarda y habilita la conexión de pey para usarla en Caja.';}));
    if(row.kind==='BANK'&&row.locally_archived)li.append(button('Restaurar cuenta',()=>work('pey-bank-status',async snap=>{if(!valid(c))return;await call(snap.path+'/pey-operations/'+row.id+'/restore',{method:'POST',write:true});if(valid(snap)){$('pey-bank-status').textContent='Cuenta restaurada en la lista de este negocio.';await load(snap);}})));
    if(row.kind==='BANK'&&!row.locally_archived)li.append(button('Eliminar de Mis negocios',()=>{if(!valid(c))return;if(!window.confirm('Solo se retirará de la lista de Mercado Abierto de este negocio. La cuenta seguirá registrada en pey y los movimientos anteriores se conservarán. ¿Continuar?'))return;void work('pey-bank-status',async snap=>{if(!valid(c))return;await call(snap.path+'/pey-operations/'+row.id+'/archive',{method:'POST',write:true});if(valid(snap)){$('pey-bank-status').textContent='Cuenta retirada de esta lista. La cuenta sigue en pey; puedes restaurarla abajo.';await load(snap);}});}));
    if(row.kind==='LINK'&&row.state==='PENDING') {
      const amount=document.createElement('input');amount.inputMode='decimal';amount.setAttribute('aria-label','Nuevo importe del enlace en MXN');amount.placeholder='Nuevo importe MXN';li.append(amount);
      li.append(button('Actualizar importe',()=>work('pey-op-status',async snap=>{if(!valid(c))return;const result=await call(snap.path+'/pey-operations',{method:'POST',write:true,body:{id:id(),kind:'LINK_UPDATE',parent_id:row.id,amount_minor:cents(amount.value.trim())}});if(valid(snap)){$('pey-op-status').textContent=labels[result.state]||result.state;await load(snap);}})));
    }
    $(row.kind==='BANK'?(row.locally_archived?'pey-bank-archived-list':'pey-bank-list'):'pey-op-list').append(li);
  }
  async function load(c,more=false){const data=await call(c.path+'/pey-operations'+(more&&cursor?'?before='+encodeURIComponent(cursor):''));if(!valid(c))return;if(!more){$('pey-op-list').replaceChildren();$('pey-bank-list').replaceChildren();$('pey-bank-archived-list').replaceChildren();}for(const row of data.items)render(row,c);cursor=data.next_cursor;$('pey-op-more').hidden=!cursor;}
  $('pey-op-kind').addEventListener('change',()=>{const push=$('pey-op-kind').value==='PUSH';$('pey-op-phone-label').hidden=!push;$('pey-op-tip-label').hidden=push;$('pey-op-phone').required=push;});
  $('pey-operation-form').addEventListener('submit',e=>{e.preventDefault();void work('pey-op-status',async c=>{
    if(typeof pendingOrder!=='undefined'&&pendingOrder)throw Error('Resuelve primero el cobro CoDi pendiente.');
    if(sessionStorage.getItem('mercadoabierto.cash.pending.v1:'+c.user+':'+c.merchant))throw Error('Resuelve primero el registro de efectivo pendiente.');
    const key='mercado.pey.pending.'+c.user+'.'+c.merchant;let op=sessionStorage.getItem(key);if(!op){op=id();sessionStorage.setItem(key,op);}
    const body={id:op,kind:$('pey-op-kind').value,order_id:$('sale-order').value.trim(),concept:$('sale-concept').value.trim(),numref:$('pey-op-ref').value,amount_minor:cents($('amount').value.trim()),phone:$('pey-op-kind').value==='PUSH'?$('pey-op-phone').value:'',has_tip:$('pey-op-kind').value==='LINK'&&$('pey-op-tip').checked,receipt_enabled:!$('receipt-disabled').checked,payer_email:$('payer-email').value.trim()||null};
    const result=await call(c.path+'/pey-operations',{method:'POST',write:true,body});if(!valid(c))return;$('pey-op-status').textContent=labels[result.state]||result.state;await load(c);
  });});
  $('pey-op-new').addEventListener('click',()=>{if(busy)return;try{const c=ctx();sessionStorage.removeItem('mercado.pey.pending.'+c.user+'.'+c.merchant);$('pey-operation-form').reset();$('pey-op-status').textContent='Nuevo cobro. Verifica el historial antes de repetir una venta anterior.';}catch{}});
  $('pey-bank-form').addEventListener('submit',e=>{e.preventDefault();void work('pey-bank-status',async c=>{
    const key='mercado.pey.bank.pending.'+c.user+'.'+c.merchant;let op=sessionStorage.getItem(key);if(!op){op=id();sessionStorage.setItem(key,op);}
    const result=await call(c.path+'/pey-operations',{method:'POST',write:true,body:{id:op,kind:'BANK',alias:$('pey-bank-alias').value.trim(),name:$('pey-bank-name').value.trim(),clabe:$('pey-bank-clabe').value.trim(),entity:$('pey-bank-entity').value}});if(!valid(c))return;$('pey-bank-status').textContent=labels[result.state]||result.state;if(!['SUBMITTING','UNCERTAIN'].includes(result.state)){sessionStorage.removeItem(key);$('pey-bank-form').reset();}await load(c);
  });});
  for(const element of ['pey-op-refresh','pey-bank-refresh'])$(element).addEventListener('click',()=>void work('pey-op-status',load));
  $('pey-op-more').addEventListener('click',()=>void work('pey-op-status',c=>load(c,true)));
  async function ledger(c,next=false){const q=new URLSearchParams();const account=$('pey-ledger-account').value.trim(),qr=$('pey-ledger-qr').value.trim();if(account&&qr)throw Error('Elige una cuenta bancaria o un QR, no ambos');if(account)q.set('account_id',account);if(qr)q.set('qr_id',qr);if(!next)txCursor=null;if(next&&txCursor)q.set('next_token',txCursor);const encoded=q.toString(),suffix=encoded?'?'+encoded:'';const data=await call(c.path+'/pey-transactions'+suffix);if(!valid(c))return;$('pey-ledger-list').replaceChildren();for(const tx of data.items){const li=document.createElement('li');li.append(document.createTextNode([tx.id,tx.status,tx.amount+' '+tx.currency,tx.paymentMethod].filter(Boolean).join(' · ')));li.append(document.createTextNode(' '));li.append(button('Ver detalle',()=>void work('pey-ledger-status',async snap=>{if(!valid(snap))return;const detail=await call(snap.path+'/pey-transactions/'+encodeURIComponent(tx.id));if(!valid(snap))return;const panel=document.createElement('details');const summary=document.createElement('summary');summary.textContent='Detalle de '+tx.id;const pre=document.createElement('pre');pre.textContent=JSON.stringify(detail,null,2);panel.append(summary,pre);li.append(panel);$('pey-ledger-status').textContent='Detalle consultado directamente a pey.';})));$('pey-ledger-list').append(li);}txCursor=data.next_token;$('pey-ledger-next').hidden=!txCursor;$('pey-ledger-status').textContent=data.items.length+' movimientos en esta página';}
  $('pey-existing-load').addEventListener('click',()=>void work('pey-bank-status',async c=>{const account=$('pey-existing-bank').value.trim();const data=await call(c.path+'/pey-bank-accounts/'+encodeURIComponent(account));if(valid(c)){$('pey-bank-status').textContent=[data.alias,data.name,data.clabe_masked,labels[data.codiStatus]||data.codiStatus,data.errorMessage||''].join(' · ');}}));
  $('pey-ledger-load').addEventListener('click',()=>void work('pey-ledger-status',c=>ledger(c)));
  $('pey-ledger-next').addEventListener('click',()=>void work('pey-ledger-status',c=>ledger(c,true)));
  for(const element of ['pey-ledger-account','pey-ledger-qr'])$(element).addEventListener('input',()=>{txCursor=null;$('pey-ledger-next').hidden=true;});
  function reset(){generation++;cursor=null;txCursor=null;for(const e of ['pey-op-list','pey-bank-list','pey-bank-archived-list','pey-ledger-list'])$(e).replaceChildren();for(const e of ['pey-op-status','pey-bank-status','pey-ledger-status'])$(e).textContent='';$('pey-bank-form').reset();$('pey-operation-form').reset();$('pey-ledger').hidden=merchantRoles.get(currentMerchant)!=='owner';$('pey-bank-registration').hidden=merchantRoles.get(currentMerchant)!=='owner';if(currentMerchant)void work('pey-op-status',load);}
  window.addEventListener('rio-merchant-selected',reset);
  setInterval(()=>{if(!document.hidden&&currentMerchant&&!busy)void work('pey-op-status',load);},15000);
  window.addEventListener('focus',()=>{if(currentMerchant&&!busy)void work('pey-op-status',load);});
})();
