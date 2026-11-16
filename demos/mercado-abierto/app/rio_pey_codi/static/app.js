'use strict';
let csrf = '', currentIntent = '', currentMerchant = '', currentUserId = '', pendingOrder;
let limitedLaunch = false;
let paymentRequestsEnabled = false, livePaymentsEnabled = false;
let currentIntentMode = '';
let unresolvedCursor = null, unresolvedGeneration = 0, unresolvedBusy = false;
let selectionGeneration = 0, historyGeneration = 0;
let selectionBusy = false, checkoutBusy = false;
let merchantRoles = new Map(), reviewGeneration = 0, reviewAttempt = null, reviewBusy = false;
let beneficiaryGeneration = 0, beneficiaryPending = null, beneficiaryBusy = false;
let providerCheckPending = null;
const $ = id => document.getElementById(id);
function notice(t) { const target=$('notice');if(target)target.textContent=t; }
function updateChargeControls() {
  const cashMode = $('payment-method')?.value === 'cash';
  const busy = selectionBusy || checkoutBusy || (!cashMode && !paymentRequestsEnabled) || !currentMerchant
    || !['owner','admin','cashier'].includes(merchantRoles.get(currentMerchant));
  $('charge').querySelector('button').disabled = busy;
  for (const id of ['sale-order', 'sale-concept', 'amount']) $(id).disabled = busy;
  $('merchant').disabled = checkoutBusy;
  if($('payment-method')){
    $('charge-submit').hidden=cashMode; $('cash-tools').hidden=!cashMode; $('charge-mode-note').hidden=cashMode;
    $('receipt-options').hidden=cashMode || !livePaymentsEnabled;
    $('payer-email').required=!cashMode && livePaymentsEnabled && !$('receipt-disabled').checked;
    $('payer-email').disabled=cashMode || $('receipt-disabled').checked;
    $('payment-method').disabled=checkoutBusy || selectionBusy;
    $('payment-method-note').textContent=cashMode?'Efectivo: registra lo recibido y calcula el cambio.':'CoDi: genera el QR de cobro con la cuenta de pey del negocio.';
    window.MercadoCash?.refreshControls();
  }
  $('charge-merchant').textContent = currentMerchant ? 'Comercio: ' + ($('merchant').selectedOptions[0]?.textContent || '') : '';
}
async function call(path,{method='GET',body,write=false,signal,extraHeaders={}}={}){
  const opts={method,headers:{'Accept':'application/json'}};
  Object.assign(opts.headers,extraHeaders);
  if(body!==undefined){opts.body=JSON.stringify(body);opts.headers['Content-Type']='application/json'}
  if(write)opts.headers['X-CSRF-Token']=csrf;
  // Checkout and recovery callers keep their own deadlines and cancellation signal.
  const controller=signal?null:new AbortController();
  opts.signal=signal||controller.signal;
  let timedOut=false;
  const timer=controller?setTimeout(()=>{timedOut=true;controller.abort()},15000):null;
  try{
    const res=await fetch(path,opts);
    let data;try{data=await res.json()}catch(error){
      if(opts.signal.aborted)throw error;
      throw Error('Respuesta inválida del servidor');
    }
    if(!res.ok){if(res.status===401&&typeof window!=='undefined'&&window.RioSession){window.RioSession.lock();location.replace('/login?next='+encodeURIComponent(location.pathname))}const error=Error(typeof data.detail==='string'?data.detail:`HTTP ${res.status}`);error.code=data.code;error.status=res.status;throw error}
    return data;
  }catch(error){
    if(timedOut){
      const timeout=Error(['GET','HEAD'].includes(method.toUpperCase())
        ?'El servidor tardó demasiado en responder. Intenta consultar de nuevo.'
        :'No se pudo confirmar el resultado a tiempo. Consulta el estado antes de repetir la operación.');
      timeout.name='AbortError';timeout.code='REQUEST_TIMEOUT';throw timeout;
    }
    throw error;
  }finally{if(timer!==null)clearTimeout(timer)}
}
function form(f){return Object.fromEntries(new FormData(f).entries())}
function newReference() {
  const value = new Uint32Array(1);
  const range = 9000000;
  const limit = Math.floor(2 ** 32 / range) * range;
  do { crypto.getRandomValues(value); } while (value[0] >= limit);
  return String(1000000 + value[0] % range);
}
function storageKey(user, merchant) { return `rio.checkout.v1:${user}:${merchant}`; }
function readPending(user, merchant) {
  try {
    const raw = localStorage.getItem(storageKey(user, merchant));
    if (raw === null) return null;
    const value = JSON.parse(raw);
    const identifier = /^[A-Za-z0-9][A-Za-z0-9._-]{0,69}$/;
    if (!value || value.version !== 1 || value.user !== user || value.merchant !== merchant ||
        typeof value.id !== 'string' || !identifier.test(value.id) ||
        typeof value.reference !== 'string' || value.reference.length > 40 || !identifier.test(value.reference) ||
        !Number.isInteger(value.expiration) || value.expiration < 60 || value.expiration > 3600 ||
        typeof value.fingerprint !== 'string' || !/^[a-f0-9]{64}$/.test(value.fingerprint) ||
        (value.shared !== undefined && typeof value.shared !== 'boolean')) {
      throw Error('Invalid pending order');
    }
    return value;
  } catch (_) {
    throw Error('No se pudo recuperar la solicitud guardada. Consulta el historial antes de continuar.');
  }
}
function savePending(order) {
  try {
    const key = storageKey(order.user, order.merchant);
    const value = JSON.stringify(order);
    localStorage.setItem(key, value);
    if (localStorage.getItem(key) !== value) throw Error('Storage readback failed');
  } catch (_) {
    throw Error('No se pudo guardar la solicitud. Consulta el historial antes de continuar.');
  }
}
async function orderFingerprint(user, merchant, concept, amount, expiration) {
  const bytes = new TextEncoder().encode(JSON.stringify([user, merchant, concept, amount, expiration]));
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
}
async function withOrderLock(user, merchant, action) {
  if (!navigator.locks || typeof navigator.locks.request !== 'function') {
    throw Error('Este navegador no puede coordinar la caja entre pestañas.');
  }
  return navigator.locks.request(`rio.checkout:${user}:${merchant}`, {mode:'exclusive', ifAvailable:true}, async lock => {
    if (!lock) throw Error('Otra pestaña está procesando una solicitud para este comercio.');
    return action();
  });
}
function showIntent(intent) {
  if (currentIntent !== intent.id) resetReview();
  currentIntent = intent.id;
  currentIntentMode = intent.mode;
  $('result').hidden = false;
  const qr = $('qrcode');
  const live = intent.mode === 'LIVE';
  const paid = intent.status === 'PROVIDER_REPORTED';
  qr.textContent = paid ? (live ? 'Pey reportó el pago.' : 'Aviso de práctica recibido.')
    : intent.expired ? 'Solicitud caducada' : (intent.qr_display || 'Sin QR confirmado');
  if (live && !paid && !intent.expired && intent.qr_image_url === '/v1/checkout/qr/' + intent.id + '/image') {
    const image = document.createElement('img');
    image.alt = 'Código QR CoDi para pagar';
    image.src = intent.qr_image_url;
    image.addEventListener('error', () => {
      if (currentIntent === intent.id && qr.contains(image)) qr.textContent = 'No se pudo cargar el QR. Actualiza el estado.';
    });
    qr.replaceChildren(image);
  }
  $('folio').textContent = intent.order_id;
  $('qr-amount').textContent = new Intl.NumberFormat('es-MX', {style:'currency', currency:'MXN'}).format(intent.amount_minor / 100);
  $('qr-provider-id').textContent = intent.provider_qr_id || '—';
  $('qr-provider-tx').textContent = intent.provider_transaction_id || '—';
  $('qrstate').textContent = ({
    QR_REQUESTING:'Solicitando QR a pey',
    QR_ISSUED:intent.expired ? 'Solicitud caducada' : 'QR emitido · pago pendiente',
    PROVIDER_UNCERTAIN:'Resultado incierto · conserva el folio',
    PROVIDER_REJECTED:'Pey rechazó la solicitud',
    PROVIDER_REPORTED:live ? 'Pago reportado por pey' : 'Aviso de práctica',
  })[intent.status] || intent.status;
  $('refresh-pey').hidden = !live || intent.status==='PROVIDER_REJECTED';
  $('new-order').textContent = ['PROVIDER_UNCERTAIN','QR_REQUESTING'].includes(intent.status)
    ? 'Preparar otra venta' : 'Nueva orden';
  $('ticket').hidden = live;
  if (typeof loadReceipt === 'function') void loadReceipt(intent, live);
  $('review').hidden = !['owner', 'admin'].includes(merchantRoles.get(currentMerchant));
}
async function orderById(merchant, orderId) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await call(`/v1/merchants/${encodeURIComponent(merchant)}/checkout-orders/${encodeURIComponent(orderId)}`,
                                {signal:controller.signal});
    if (!response.intent || typeof response.intent !== 'object' || Array.isArray(response.intent)) {
      throw Error('La consulta de la orden devolvió una respuesta inválida.');
    }
    return response.intent;
  } finally { clearTimeout(timer); }
}
async function restorePending(order) {
  let intent;
  try {
    intent = await orderById(order.merchant, order.id);
  } catch (error) {
    if (error.status === 404) {
      notice('Solicitud guardada, aún no localizada. Conserva los mismos datos si la reintentas.');
      return;
    }
    throw error;
  }
  await applyRecovered(order, intent);
}
async function applyRecovered(order, intent) {
  if (currentUserId !== order.user || currentMerchant !== order.merchant) return;
  const fingerprint = await orderFingerprint(order.user, order.merchant, intent.concept, intent.amount_minor, intent.expiration_s);
  if (currentUserId !== order.user || currentMerchant !== order.merchant) return;
  if (intent.order_id !== order.id || intent.merchant_id !== order.merchant ||
      intent.numref !== order.reference || intent.expiration_s !== order.expiration || fingerprint !== order.fingerprint) {
    throw Error('La solicitud guardada difiere del servidor. Revisa el historial antes de continuar.');
  }
  const charge = $('charge');
  charge.elements.namedItem('concept').value = intent.concept;
  charge.elements.namedItem('amount').value = `${Math.floor(intent.amount_minor / 100)}.${String(intent.amount_minor % 100).padStart(2, '0')}`;
  $('sale-order').value = order.id;
  showIntent(intent);
  notice('Solicitud recuperada. La liquidación bancaria sigue sin verificarse.');
}
async function merchants(preferred=null){
 const previous=currentMerchant;
 const [x,archived]=await Promise.all([call('/v1/merchants'),call('/v1/merchants/archived')]);merchantRoles=new Map(x.merchants.map(m=>[m.id,m.role]));
 $('merchant').replaceChildren();for(const m of x.merchants)$('merchant').add(new Option(`${m.name} (${m.role})`,m.id));
 let restored=null;
 try{const receipt=JSON.parse(sessionStorage.getItem('rio.pey.activation')||'null');
  if(receipt&&receipt.user===currentUserId&&Date.now()-receipt.time<120000&&merchantRoles.has(receipt.merchant)){restored=receipt.merchant;notice('CoDi habilitado. La conexión de tu negocio quedó guardada.');}
  sessionStorage.removeItem('rio.pey.activation');
 }catch(_){}
 const target=preferred||restored||previous;
 if(target&&merchantRoles.has(target))$('merchant').value=target;
 const list=$('business-list');
 if(list){list.replaceChildren();for(const m of x.merchants){
  const row=document.createElement('div');row.className='business-card';row.setAttribute('role','listitem');row.dataset.merchantId=m.id;
  const text=document.createElement('div'),name=document.createElement('strong'),role=document.createElement('small'),button=document.createElement('button');
  name.textContent=m.name;role.textContent=m.role==='owner'?'Titular · cuenta de pey independiente':'Acceso autorizado';text.append(name,role);
  button.type='button';button.className='outline';button.textContent='Seleccionar';button.addEventListener('click',async()=>{if(checkoutBusy){notice('Espera a que termine la solicitud de cobro antes de cambiar de negocio.');return}try{$('merchant').value=m.id;await selectMerchant();window.RioWorkspace?.open('negocios');}catch(error){notice(error.message)}});
  row.append(text,button);
  if(m.role==='owner'){
   const remove=document.createElement('button');remove.type='button';remove.className='outline business-remove';remove.textContent='Quitar del perfil';
   remove.addEventListener('click',async()=>{
    if(checkoutBusy){notice('Espera a que termine la solicitud de cobro antes de retirar el negocio.');return}
    if(!window.confirm('Se retirará '+m.name+' de la lista de negocios activos. Se conservarán sus cobros, historial y datos; no se borrará ni desactivará su cuenta pey.'))return;
    const typed=window.prompt('Para confirmar, escribe exactamente el nombre del negocio: '+m.name);
    if(typed!==m.name){notice('No se retiró el negocio: el nombre no coincide.');return}
    remove.disabled=true;
    try{await call('/v1/merchants/'+encodeURIComponent(m.id)+'/archive',{method:'POST',body:{confirm_name:typed},write:true});await merchants();notice('Negocio retirado del perfil. Sus registros se conservaron y puedes restaurarlo desde “Negocios retirados del perfil”.');}
    catch(error){notice(error.message);remove.disabled=false}
   });
   row.append(remove);
  }
  list.append(row);
 }}
 const archivedList=$('archived-business-list');
 if(archivedList){archivedList.replaceChildren();for(const m of archived.merchants){
  const row=document.createElement('div');row.className='business-card';row.setAttribute('role','listitem');
  const text=document.createElement('div'),name=document.createElement('strong'),role=document.createElement('small'),restore=document.createElement('button');
  name.textContent=m.name;role.textContent='Retirado del perfil · historial conservado';text.append(name,role);
  restore.type='button';restore.className='outline';restore.textContent='Restaurar negocio';
  restore.addEventListener('click',async()=>{if(checkoutBusy){notice('Espera a que termine la solicitud de cobro.');return}restore.disabled=true;try{await call('/v1/merchants/'+encodeURIComponent(m.id)+'/restore',{method:'POST',write:true});await merchants(m.id);notice('Negocio restaurado en tu perfil.');}catch(error){notice(error.message);restore.disabled=false}});
  row.append(text,restore);archivedList.append(row);
 }}
 await selectMerchant();
}
async function selectMerchant() {
  const selection = ++selectionGeneration;
  selectionBusy = true;
  updateChargeControls();
  try {
    const previousMerchant = currentMerchant;
    currentMerchant = $('merchant').value;
    (document.querySelectorAll?.('#business-list [data-merchant-id]')||[]).forEach(row=>row.setAttribute('aria-current',String(row.dataset.merchantId===currentMerchant)));
    window.dispatchEvent(new Event('rio-merchant-selected'));
    resetReview();
    resetBeneficiary();
    if (previousMerchant !== currentMerchant) $('sale-order').value = '';
    currentIntent = '';
    currentIntentMode = '';
    pendingOrder = undefined;
    $('result').hidden = true;
    $('qrstate').textContent = '';
    $('folio').textContent = '';
    $('qrcode').textContent = '';
    const merchant = currentMerchant;
    const user = currentUserId;
    if (merchantRoles.get(merchant) === 'owner') {
      $('beneficiary-panel').hidden = false;
      try { await loadBeneficiary(); }
      catch (_) { if (selection === selectionGeneration) $('beneficiary-status').textContent = 'No se pudo consultar el registro del beneficiario.'; }
      if (selection !== selectionGeneration || merchant !== currentMerchant || user !== currentUserId) return;
      try { await loadProviderReadiness(); }
      catch (_) { if (selection === selectionGeneration) $('provider-readiness').textContent = 'No se pudo consultar el estado de preparación.'; }
      if (selection !== selectionGeneration || merchant !== currentMerchant || user !== currentUserId) return;
    }
    try { pendingOrder = readPending(currentUserId, merchant); }
    catch (error) { notice(error.message); }
    if (pendingOrder) $('sale-order').value = pendingOrder.id;
    await loadHistory();
    if (selection !== selectionGeneration || merchant !== currentMerchant || user !== currentUserId) return;
    await loadUnresolved();
    if (selection === selectionGeneration && merchant === currentMerchant && user === currentUserId && pendingOrder) {
      await restorePending(pendingOrder);
    }
  } finally {
    if (selection === selectionGeneration) {
      selectionBusy = false;
      updateChargeControls();
    }
  }
}
async function loadHistory() {
  const merchant = currentMerchant, user = currentUserId, generation = ++historyGeneration;
  $('history').replaceChildren();
  if (!merchant) return;
  const {intents} = await call(`/v1/merchants/${encodeURIComponent(merchant)}/checkout-history`);
  if (generation !== historyGeneration || merchant !== currentMerchant || user !== currentUserId) return;
  for (const intent of intents) {
    const item = document.createElement('li');
    item.textContent = `${intent.order_id} · MXN ${(intent.amount_minor / 100).toFixed(2)} · ${intent.status}`;
    if (intent.mode === 'LIVE' || intent.status === 'QR_REQUESTING' || intent.status === 'PROVIDER_UNCERTAIN') {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = 'Recuperar';
      button.addEventListener('click', () => recoverFromHistory(merchant, intent.order_id).catch(e => notice(e.message)));
      item.append(button);
    }
    if (['owner', 'admin'].includes(merchantRoles.get(merchant)) && /^[0-9a-f]{32}$/.test(intent.id)) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = `Revisar ${intent.order_id}`;
      button.addEventListener('click', () => inspectReviewIntent(merchant, intent.id).catch(e => notice(e.message)));
      item.append(button);
    }
    $('history').append(item);
  }
}
async function loadUnresolved(append = false) {
  const merchant = currentMerchant, user = currentUserId;
  if (append && (unresolvedBusy || !unresolvedCursor)) return;
  const generation = append ? unresolvedGeneration : ++unresolvedGeneration;
  if (!append) {
    unresolvedCursor = null;
    $('unresolved').replaceChildren();
    $('unresolved-status').textContent = 'Consultando solicitudes…';
    $('unresolved-more').hidden = true;
  }
  if (!merchant || !user) return;
  const params = new URLSearchParams({limit:'25'});
  if (append) {
    params.set('after_created_at', String(unresolvedCursor.created_at));
    params.set('after_id', unresolvedCursor.id);
  }
  unresolvedBusy = true;
  $('unresolved-more').disabled = true;
  try {
    const response = await call(`/v1/merchants/${encodeURIComponent(merchant)}/checkout-unresolved?${params}`);
    if (generation !== unresolvedGeneration || merchant !== currentMerchant || user !== currentUserId) return;
    if (!Array.isArray(response.intents) || response.intents.some(intent => !intent ||
        intent.merchant_id !== merchant || !['QR_REQUESTING', 'PROVIDER_UNCERTAIN'].includes(intent.status) ||
        typeof intent.order_id !== 'string' || typeof intent.concept !== 'string' ||
        !Number.isSafeInteger(intent.amount_minor) || intent.amount_minor <= 0) ||
        (response.next_cursor !== null &&
        (!response.next_cursor || !Number.isInteger(response.next_cursor.created_at) ||
         !/^[0-9a-f]{32}$/.test(response.next_cursor.id)))) throw Error('Invalid queue response');
    for (const intent of response.intents) {
      const item = document.createElement('li');
      item.textContent = `${intent.order_id} · ${intent.concept} · MXN ${(intent.amount_minor / 100).toFixed(2)} · ${intent.status}`;
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = 'Recuperar';
      button.addEventListener('click', () => recoverFromHistory(merchant, intent.order_id).catch(e => notice(e.message)));
      item.append(button);
      $('unresolved').append(item);
    }
    unresolvedCursor = response.next_cursor;
    $('unresolved-more').hidden = !unresolvedCursor;
    $('unresolved-status').textContent = $('unresolved').children.length ?
      'Consulta las solicitudes antes de repetirlas.' : 'No hay solicitudes sin resolver en esta consulta.';
  } catch (_) {
    if (generation === unresolvedGeneration && merchant === currentMerchant && user === currentUserId) {
      unresolvedCursor = null;
      $('unresolved-more').hidden = true;
      $('unresolved-status').textContent = 'No se pudo consultar la lista. Actualízala antes de repetir una solicitud.';
    }
  } finally {
    if (generation === unresolvedGeneration) {
      unresolvedBusy = false;
      $('unresolved-more').disabled = false;
    }
  }
}
async function recoverFromHistory(merchant, orderId) {
  const user = currentUserId;
  await withOrderLock(user, merchant, async () => {
    if (user !== currentUserId || merchant !== currentMerchant) return;
    const saved = readPending(user, merchant);
    if (saved && saved.id !== orderId) throw Error('Ya tienes otra solicitud guardada en este comercio.');
    const intent = await orderById(merchant, orderId);
    if (intent.merchant_id !== merchant || intent.order_id !== orderId) throw Error('La orden no coincide con el comercio.');
    const fingerprint = await orderFingerprint(user, merchant, intent.concept, intent.amount_minor, intent.expiration_s);
    if (saved && (saved.reference !== intent.numref || saved.expiration !== intent.expiration_s || saved.fingerprint !== fingerprint)) {
      throw Error('La solicitud guardada difiere del servidor. Revisa el historial antes de continuar.');
    }
    const order = saved || {version:1, user, merchant, id:orderId, reference:intent.numref,
                            expiration:intent.expiration_s, fingerprint};
    savePending(order);
    pendingOrder = order;
    await applyRecovered(order, intent);
    window.RioWorkspace?.open('caja');
  });
}
async function adoptSharedOrder(user, merchant, id, intent, concept, amount, expectedExpiration) {
  if (!intent || intent.merchant_id !== merchant || intent.order_id !== id ||
      intent.concept !== concept || intent.amount_minor !== amount ||
      !Number.isInteger(intent.expiration_s) || intent.expiration_s < 60 || intent.expiration_s > 3600 ||
      (expectedExpiration !== undefined && intent.expiration_s !== expectedExpiration) ||
      typeof intent.numref !== 'string' || intent.numref.length > 40 ||
      !/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(intent.numref)) {
    throw Error('El folio ya existe con otros datos. Revisa la venta antes de continuar.');
  }
  if (user !== currentUserId || merchant !== currentMerchant) return;
  const fingerprint = await orderFingerprint(user, merchant, concept, amount, intent.expiration_s);
  if (user !== currentUserId || merchant !== currentMerchant) return;
  const order = {version:1, user, merchant, id, reference:intent.numref,
                 expiration:intent.expiration_s, fingerprint, shared:true};
  savePending(order);
  pendingOrder = order;
  await applyRecovered(order, intent);
}
async function enter(user) {
  currentUserId = user.id;
  $('welcome').textContent = user.email;
  window.RioOwnerActivityAllowed = user.can_invite === true;
  $('dashboard').dataset.owner=String(window.RioOwnerActivityAllowed);
  document.querySelectorAll('[data-owner-area]').forEach(element=>element.hidden=!window.RioOwnerActivityAllowed);
  window.RioActivity?.authorize(window.RioOwnerActivityAllowed);
  window.RioVerificationTasks?.authorize(window.RioOwnerActivityAllowed);
  $('invite-panel').hidden = user.can_invite !== true;
  $('rio-admin-recovery').hidden = user.can_invite !== true;
  window.RioWorkspace?.activate();
  await merchants();
}
async function boot() {
  try {
    const user = await call('/v1/auth/me');
    csrf = user.csrf_token;
    const h = await call('/public-status');
    if (h.access_enabled !== true) throw Error('El acceso no está disponible en este momento.');
    paymentRequestsEnabled = h.payment_requests_enabled === true;
    livePaymentsEnabled = h.mode === 'LIVE' && h.live_payments_enabled === true;
    $('receipt-options').hidden = !livePaymentsEnabled;
    $('payer-email').required = livePaymentsEnabled && !$('receipt-disabled').checked;
    limitedLaunch = h.launch_mode === 'LIMITED';
    if (h.mode === 'LIVE' && $('sale-concept').value === 'Venta de ejemplo') $('sale-concept').value = '';
    $('environment').textContent = livePaymentsEnabled ? 'COBROS CODI · PRODUCCIÓN' : h.mode === 'DEMO' ? 'DEMOSTRACIÓN' : 'COBROS EN PAUSA';
    $('charge-submit').textContent = livePaymentsEnabled ? 'Generar QR CoDi' : 'Generar solicitud';
    $('charge-mode-note').textContent = livePaymentsEnabled ? 'Selecciona el comercio receptor y verifica el importe antes de generar el QR.' : paymentRequestsEnabled ? 'Solicitud de práctica.' : 'La emisión de solicitudes está en pausa.';
    await enter(user);
    window.MercadoMarketCheckout?.prepare();
  } catch (error) {
    if (error.status === 401 || error.status === 403) {
      window.RioSession?.lock();
      location.replace('/login?next=' + encodeURIComponent(location.pathname));
    } else notice(error.message);
  }
}
$('logout').addEventListener('click',async()=>{try{await call('/v1/auth/logout',{method:'POST',write:true});window.RioSession?.logout();location.replace('/login')}catch(e){notice(e.message)}});
$('rio-admin-reset-form').addEventListener('submit',async e=>{
 e.preventDefault();
 const button=$('rio-admin-reset-submit'),status=$('rio-admin-reset-status');
 const link=$('rio-admin-reset-link'),label=$('rio-admin-reset-link-label');
 if(button.disabled)return;
 button.disabled=true;link.hidden=true;label.hidden=true;link.value='';
 status.textContent='Verificando cuenta y autorización…';
 try{
  const result=await call('/v1/admin/reset-links',{method:'POST',write:true,body:form(e.target)});
  const url=new URL(result.reset_url);
  const token=new URLSearchParams(url.hash.slice(1)).get('token');
  if(result.status!=='ADMIN_RESET_LINK_CREATED'||result.expires_in!==900||
     url.origin!==location.origin||url.pathname!=='/reset-password'||
     !/^[A-Za-z0-9_-]{40,64}$/.test(token||'')){
      throw Error('Enlace de recuperación inválido');
  }
  link.value=url.href;link.hidden=false;label.hidden=false;
  status.textContent='Enlace creado. Compártelo de forma privada con el titular; vence en 15 minutos.';
 }catch(error){
  status.textContent=error.status===403?'Acceso de titular no autorizado.':error.status===404?
    'La cuenta no existe o no es posterior a la cuenta propietaria.':
    'No se pudo generar el enlace. '+error.message;
 }finally{button.disabled=false;}
});
$('invite-form').addEventListener('submit',async e=>{
  e.preventDefault();
  const button=$('invite-create'), status=$('invite-status'), link=$('invite-link');
  if(button.disabled)return;
  button.disabled=true;link.value='';$('invite-link-label').hidden=true;
  status.textContent='Generando invitación…';
  try{
    const result=await call('/v1/admin/invitations',{method:'POST',write:true,body:form(e.target)});
    const url=new URL(result.invitation_url);
    const secret=new URLSearchParams(url.hash.slice(1)).get('owner_invite');
    if(result.status!=='INVITATION_CREATED'||result.email_verified!==false||url.origin!==location.origin||
       url.pathname!=='/'||!/^[A-Za-z0-9_-]{43}$/.test(secret||''))throw Error('Respuesta inválida');
    link.value=url.href;$('invite-link-label').hidden=false;
    status.textContent='Invitación generada. Cópiala y compártela en privado; no se envía automáticamente.';
  }catch(error){
    status.textContent=error.status===409?error.message:
      'No se pudo mostrar la invitación. Puedes generar otra para el mismo correo si la cuenta aún no se activó.';
  }finally{button.disabled=false}
});
$('add-merchant').addEventListener('submit',async e=>{e.preventDefault();if(checkoutBusy){notice('Espera a que termine la solicitud de cobro antes de agregar otro negocio.');return}const button=e.target.querySelector('button');if(button.disabled)return;button.disabled=true;try{const created=await call('/v1/merchants',{method:'POST',write:true,body:form(e.target)});await merchants(created.id);e.target.reset();window.RioWorkspace?.open('negocios');notice('Negocio agregado. Configura aquí su propia cuenta de pey.')}catch(err){notice(err.message)}finally{button.disabled=false}});
$('merchant').addEventListener('change', () => selectMerchant().catch(e => notice(e.message)));
function resetBeneficiary() {
  beneficiaryGeneration++;
  beneficiaryPending = null;
  providerCheckPending = null;
  beneficiaryBusy = false;
  $('beneficiary-panel').hidden = true;
  $('beneficiary-account').value = '';
  $('beneficiary-account').disabled = false;
  $('beneficiary-save').disabled = false;
  $('beneficiary-withdraw').disabled = false;
  $('provider-account-check').hidden = true;
  $('provider-account-check').disabled = false;
  $('own-pey-key').value = '';
  $('own-pey-key').disabled = false;
  $('own-pey-check').disabled = false;
  $('own-pey-status').textContent = '';
  $('provider-readiness').textContent = '';
  $('beneficiary-status').textContent = '';
  $('beneficiary-history').replaceChildren();
}
function sameBeneficiary(snapshot) {
  return snapshot.generation === beneficiaryGeneration && snapshot.merchant === currentMerchant && snapshot.user === currentUserId;
}
function beneficiarySnapshot() {
  return {generation:beneficiaryGeneration, merchant:currentMerchant, user:currentUserId};
}
function beneficiaryPath(merchant) {
  return `/v1/merchants/${encodeURIComponent(merchant)}/beneficiary-claims`;
}
async function beneficiaryCall(path, options={}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try { return await call(path, {...options, signal:controller.signal}); }
  finally { clearTimeout(timer); }
}
function beneficiaryControls(disabled) {
  beneficiaryBusy = disabled;
  $('beneficiary-account').disabled = disabled;
  $('beneficiary-save').disabled = disabled;
  $('beneficiary-withdraw').disabled = disabled;
  $('provider-account-check').disabled = disabled;
  $('own-pey-key').disabled = disabled;
  $('own-pey-check').disabled = disabled;
}
async function loadProviderReadiness() {
  const snapshot = beneficiarySnapshot();
  const state = await beneficiaryCall(`/v1/merchants/${encodeURIComponent(snapshot.merchant)}/production-readiness`);
  if (!sameBeneficiary(snapshot)) return;
  if (state.production !== 'BLOCKED' || state.live_payments_enabled !== false ||
      state.merchant_ownership_verified !== false || state.independent_bank_source_verified !== false ||
      state.bank_payment_confirmed !== false || typeof state.account_lookup_configured !== 'boolean') {
    throw Error('Respuesta de preparación inválida.');
  }
  $('provider-account-check').hidden = !state.account_lookup_configured;
  const item = state.provider_observation;
  const labels = {ACTIVE:'activa', PENDING:'pendiente', PROCESSING:'en trámite', ERROR:'con error',
                  NOT_FOUND:'no encontrada con la credencial consultada'};
  if (item && (item.source !== 'SERVER_PEY_HTTPS_READ_ONLY' || !Object.hasOwn(labels, item.status) ||
               !Number.isInteger(item.checked_at))) throw Error('Observación de pey inválida.');
  const observed = item ? `Última consulta a pey: ${labels[item.status]} (${new Date(item.checked_at*1000).toLocaleString('es-MX')}).` :
                          'Aún no hay una consulta a pey.';
  const historical = item && !state.provider_observation_matches_current_declaration ? ' Corresponde a una declaración anterior.' : '';
  const configured = state.account_lookup_configured ? '' : ' Puedes consultar con tu propia clave.';
  $('provider-readiness').textContent = `${observed}${historical}${configured} No acredita titularidad ni abono; cobros reales bloqueados.`;
}
async function checkProviderAccount() {
  if (beneficiaryBusy || merchantRoles.get(currentMerchant) !== 'owner') return;
  const snapshot = beneficiarySnapshot();
  if (!providerCheckPending) providerCheckPending = crypto.randomUUID().replaceAll('-', '');
  beneficiaryControls(true);
  try {
    const result = await beneficiaryCall(`/v1/merchants/${encodeURIComponent(snapshot.merchant)}/provider-account-checks`, {
      method:'POST', write:true, extraHeaders:{'Idempotency-Key':providerCheckPending}});
    if (!sameBeneficiary(snapshot)) return;
    const obs = result.observation;
    if (!obs || obs.source !== 'SERVER_PEY_HTTPS_READ_ONLY' || obs.merchant_ownership_verified !== false ||
        obs.bank_payment_confirmed !== false || obs.live_payments_enabled !== false) throw Error('Respuesta de pey inválida.');
    providerCheckPending = null;
    await loadProviderReadiness();
  } catch (error) {
    if (sameBeneficiary(snapshot)) {
      if (error.status === 409) {
        providerCheckPending = null;
        try { await loadProviderReadiness(); } catch (_) { /* No prior result can be inferred. */ }
        if (sameBeneficiary(snapshot)) $('provider-readiness').textContent +=
          ' La declaración cambió o la consulta ya se registró; revisa el último resultado antes de volver a consultar.';
      } else {
        $('provider-readiness').textContent = 'No se pudo completar la consulta. Si su resultado es incierto, vuelve a intentar.';
      }
    }
  } finally { if (sameBeneficiary(snapshot)) beneficiaryControls(false); }
}
$('provider-account-check').addEventListener('click', () => checkProviderAccount());
$('own-pey-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (beneficiaryBusy || merchantRoles.get(currentMerchant) !== 'owner') return;
  const snapshot=beneficiarySnapshot(), field=$('own-pey-key'), key=field.value;
  field.value='';
  if (!/^[A-Za-z0-9._~+\/\-]+={0,2}$/.test(key) || key.length>512) {
    $('own-pey-status').textContent='Revisa la clave de API de tu cuenta de pey.';return;
  }
  beneficiaryControls(true);$('own-pey-status').textContent='Consultando pey…';
  try {
    const result=await beneficiaryCall(`/v1/merchants/${encodeURIComponent(snapshot.merchant)}/own-pey-account-checks`,
      {method:'POST',write:true,body:{api_key:key},extraHeaders:{'Idempotency-Key':crypto.randomUUID().replaceAll('-', '')}});
    if (!sameBeneficiary(snapshot)) return;
    const obs=result.observation;
    const labels={ACTIVE:'activa',PENDING:'pendiente',PROCESSING:'en trámite',ERROR:'con error',NOT_FOUND:'no encontrada con esa clave'};
    if(result.key_saved!==false||!obs||obs.source!=='SERVER_PEY_HTTPS_READ_ONLY'||!Object.hasOwn(labels,obs.status)||
       obs.merchant_ownership_verified!==false||obs.live_payments_enabled!==false) throw Error('Invalid response');
    $('own-pey-status').textContent=`pey reportó la cuenta ${labels[obs.status]}. La clave no se guardó; la consulta no activa cobros ni confirma titularidad.`;
  } catch (error) {
    if(sameBeneficiary(snapshot))$('own-pey-status').textContent=error.status===409?'Primero guarda el ID de tu cuenta de pey arriba.':
      'No se pudo confirmar la consulta. Revisa el ID y tu clave y vuelve a intentar.';
  } finally {if(sameBeneficiary(snapshot))beneficiaryControls(false)}
});
async function loadBeneficiary() {
  const snapshot = beneficiarySnapshot();
  const response = await beneficiaryCall(beneficiaryPath(snapshot.merchant));
  if (!sameBeneficiary(snapshot)) return;
  if (!Array.isArray(response.claims) || response.provider_status_verified !== false || response.live_payments_enabled !== false) {
    throw Error('Respuesta del registro inválida.');
  }
  $('beneficiary-history').replaceChildren();
  for (const row of response.claims) {
    const item = document.createElement('li');
    const label = row.claim === 'OWNER_REPORTED_VERIFIED' ? 'El titular reportó que verificó al beneficiario' :
                  row.claim === 'OWNER_WITHDREW_REPORT' ? 'El titular retiró su confirmación' : 'Registro no reconocido';
    item.textContent = `${new Date(row.created_at * 1000).toLocaleString('es-MX')} · ${label}${row.provider_account_id ? ' · ID ' + row.provider_account_id : ''}`;
    $('beneficiary-history').append(item);
  }
  $('beneficiary-status').textContent = response.claims.length ? 'Historial consultado. Estado de pey aún no comprobado por Mercado Abierto.' : 'Sin confirmación registrada para este comercio.';
}
async function submitBeneficiary(claim) {
  if (beneficiaryBusy || merchantRoles.get(currentMerchant) !== 'owner') return;
  const snapshot = beneficiarySnapshot();
  const account = claim === 'OWNER_REPORTED_VERIFIED' ? $('beneficiary-account').value : '';
  if (account && !/^[0-7][0-9A-HJKMNP-TV-Z]{25}$/.test(account)) {
    $('beneficiary-status').textContent = 'El ID de cuenta debe tener el formato de pey.';
    return;
  }
  const body = {claim, provider_account_id:account || null};
  const signature = JSON.stringify(body);
  if (beneficiaryPending && beneficiaryPending.signature !== signature) {
    $('beneficiary-status').textContent = 'Hay una solicitud sin confirmar. Reintenta con los mismos datos.';
    return;
  }
  if (!beneficiaryPending) beneficiaryPending = {signature, key:crypto.randomUUID().replaceAll('-', '')};
  beneficiaryControls(true);
  try {
    const result = await beneficiaryCall(beneficiaryPath(snapshot.merchant), {method:'POST', write:true, body,
      extraHeaders:{'Idempotency-Key':beneficiaryPending.key}});
    if (!sameBeneficiary(snapshot)) return;
    if (!result.claim || result.claim.merchant_id !== snapshot.merchant || result.claim.claim !== body.claim ||
        result.claim.provider_account_id !== body.provider_account_id || result.provider_status_verified !== false ||
        result.live_payments_enabled !== false) throw Error('No se pudo verificar el registro guardado.');
    beneficiaryPending = null;
    $('beneficiary-account').value = '';
    try { await loadBeneficiary(); }
    catch (_) {
      if (sameBeneficiary(snapshot)) $('beneficiary-status').textContent = 'Confirmación guardada. No se pudo actualizar el historial.';
      return;
    }
    if (sameBeneficiary(snapshot)) $('beneficiary-status').textContent = 'Confirmación guardada. Estado de pey aún no comprobado por Mercado Abierto.';
    try { await loadProviderReadiness(); } catch (_) { /* Keep the recorded owner declaration. */ }
  } catch (error) {
    if (sameBeneficiary(snapshot)) $('beneficiary-status').textContent = `${error.message} Si no sabes si se guardó, reintenta con los mismos datos.`;
  } finally {
    if (sameBeneficiary(snapshot)) beneficiaryControls(false);
  }
}
$('beneficiary-form').addEventListener('submit', event => { event.preventDefault(); submitBeneficiary('OWNER_REPORTED_VERIFIED'); });
$('beneficiary-withdraw').addEventListener('click', () => submitBeneficiary('OWNER_WITHDREW_REPORT'));
$('unresolved-refresh').addEventListener('click', () => loadUnresolved());
$('unresolved-more').addEventListener('click', () => loadUnresolved(true));
$('receipt-disabled')?.addEventListener('change', () => { $('payer-email').required = livePaymentsEnabled && !$('receipt-disabled').checked; $('payer-email').disabled = $('receipt-disabled').checked; });
$('charge').addEventListener('submit', async e => {
  e.preventDefault();
  const formElement = e.currentTarget;
  const data = form(formElement);
  if (!/^\d{1,7}(\.\d{1,2})?$/.test(data.amount)) return notice('Importe inválido');
  const [pesos, cents = ''] = data.amount.split('.');
  const amount = Number(pesos) * 100 + Number(cents.padEnd(2, '0'));
  if (amount <= 0 || amount > 100000000) return notice('Importe inválido');
  const requestedOrder = typeof data.order_id === 'string' ? data.order_id : '';
  if (requestedOrder && !/^[A-Za-z0-9][A-Za-z0-9._-]{0,69}$/.test(requestedOrder)) return notice('Folio de venta inválido');
  const button = formElement.querySelector('button');
  if (button.disabled) return;
  checkoutBusy = true;
  updateChargeControls();
  const merchant = currentMerchant;
  const user = currentUserId;
  try {
    if (!user || !merchant) throw Error('Selecciona un comercio con sesión activa.');
    await withOrderLock(user, merchant, async () => {
      if (user !== currentUserId || merchant !== currentMerchant) return;
      let order = readPending(user, merchant);
      if (order && data.order_id !== undefined && requestedOrder !== order.id) {
        throw Error('No cambies el folio de una solicitud pendiente. Recupérala primero.');
      }
      const expiration = order ? order.expiration : 600;
      const fingerprint = await orderFingerprint(user, merchant, data.concept, amount, expiration);
      if (order && order.fingerprint !== fingerprint) {
        throw Error('Hay una solicitud pendiente con otros datos. Recupérala antes de modificarlos.');
      }
      if (!order) {
        if (requestedOrder) {
          let existing;
          try { existing = await orderById(merchant, requestedOrder); }
          catch (error) { if (error.status !== 404 || error.code !== 'ORDER_NOT_FOUND') throw error; }
          if (existing) {
            await adoptSharedOrder(user, merchant, requestedOrder, existing, data.concept, amount);
            return;
          }
        }
        if (user !== currentUserId || merchant !== currentMerchant) return;
        order = {version:1, user, merchant, id:requestedOrder || crypto.randomUUID().replaceAll('-', ''),
                 reference:newReference(), expiration, fingerprint, shared:!!requestedOrder};
        savePending(order);
      }
      pendingOrder = order;
      $('sale-order').value = order.id;
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 24000);
      let response;
      try {
        response = await call('/v1/checkout/qr', {method:'POST', write:true, signal:controller.signal, body:{
          merchant_id:merchant, order_id:order.id, numref:order.reference, concept:data.concept,
          amount_minor:amount, expiration_s:order.expiration,
          ...(livePaymentsEnabled ? {receipt_enabled:!$('receipt-disabled').checked, payer_email:$('receipt-disabled').checked ? null : data.payer_email} : {})
        }});
      } catch (error) {
        if (error.code==='MERCHANT_PEY_UNAVAILABLE') {
          if (user===currentUserId && merchant===currentMerchant) {
            localStorage.removeItem(storageKey(user,merchant));
            pendingOrder=undefined;
            $('sale-order').value=requestedOrder;
          }
          throw error;
        }
        if (error.status === 409 && error.code === 'REFERENCE_TAKEN') {
          order.reference = newReference();
          savePending(order);
          notice('La referencia estaba ocupada. Vuelve a generar la solicitud.');
          return;
        }
        if (error.status === 409 && order.shared === true) {
          const existing = await orderById(merchant, order.id);
          await adoptSharedOrder(user, merchant, order.id, existing, data.concept, amount, order.expiration);
          return;
        }
        if (error.status===502 || error.name==='AbortError' || error instanceof TypeError) {
          try { await restorePending(order); }
          catch (_) { /* The saved folio remains available for later recovery. */ }
        }
        throw error;
      } finally {
        clearTimeout(timer);
      }
      const intent = response.intent;
      if (!intent || intent.order_id !== order.id || intent.merchant_id !== merchant || intent.numref !== order.reference ||
          intent.expiration_s !== order.expiration ||
          await orderFingerprint(user, merchant, intent.concept, intent.amount_minor, intent.expiration_s) !== order.fingerprint) {
        throw Error('La respuesta no coincide con la solicitud. Consulta el historial.');
      }
      if (user !== currentUserId || merchant !== currentMerchant) return;
      showIntent(intent);
      $('result').scrollIntoView({block:'start'});
      if (intent.status==='PROVIDER_REJECTED') {
        notice('Pey rechazó la solicitud. Revisa la cuenta CoDi y el importe antes de preparar un folio nuevo.');
      } else {
        notice(intent.mode === 'LIVE' ? 'Solicitud registrada. Consulta su estado después del pago.' : 'Solicitud de práctica.');
      }
      await loadHistory();
    });
  } catch (err) {
    notice(err.name === 'AbortError' ? 'Resultado incierto. Conserva los datos y consulta el estado.' : err.message);
  } finally {
    checkoutBusy = false;
    updateChargeControls();
    if (merchant === currentMerchant && user === currentUserId) void loadUnresolved();
  }
});
$('new-order').addEventListener('click', async () => {
  const user = currentUserId, merchant = currentMerchant;
  try {
    if (!user || !merchant) throw Error('Selecciona un comercio con sesión activa.');
    await withOrderLock(user, merchant, async () => {
      if (user !== currentUserId || merchant !== currentMerchant) return;
      const saved = readPending(user, merchant);
      if (!saved) {
        if (pendingOrder) throw Error('Falta la solicitud guardada. Consulta el historial.');
        return;
      }
      const intent = await orderById(merchant, saved.id);
      if (user !== currentUserId || merchant !== currentMerchant) return;
      const fingerprint = await orderFingerprint(user, merchant, intent.concept, intent.amount_minor, intent.expiration_s);
      if (intent.merchant_id !== merchant || intent.order_id !== saved.id ||
          intent.numref !== saved.reference || intent.expiration_s !== saved.expiration || fingerprint !== saved.fingerprint) {
        throw Error('El folio no coincide. Consulta el historial.');
      }
      if (['PROVIDER_UNCERTAIN','QR_REQUESTING'].includes(intent.status)) {
        if (!window.confirm('El folio anterior sigue pendiente en el historial. ¿Abrir un folio para una venta distinta?')) return;
      } else if (!['QR_ISSUED','PROVIDER_REPORTED','PROVIDER_REJECTED'].includes(intent.status)) {
        throw Error('Consulta el estado de la solicitud anterior.');
      }
      const key = storageKey(user, merchant);
      localStorage.removeItem(key);
      if (localStorage.getItem(key) !== null) throw Error('No se pudo actualizar la solicitud guardada.');
      pendingOrder = undefined;
      currentIntent = '';
      resetReview();
      $('sale-order').value = '';
      $('result').hidden = true;
      $('amount').focus();
    });
  } catch (err) { notice(err.message); }
});
$('ticket').addEventListener('click', async () => {
  try {
    const ticket = await call(`/v1/checkout/qr/${encodeURIComponent(currentIntent)}/practice-ticket`);
    const text = `Ticket de práctica (sin validez fiscal)\nFolio: ${ticket.order_id}\nImporte MXN: ${(ticket.amount_minor / 100).toFixed(2)}\nLiquidación: sin verificar\n`;
    const url = URL.createObjectURL(new Blob([text], {type:'text/plain;charset=utf-8'}));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'ticket-practica.txt';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (err) { notice(err.message); }
});
$('refresh').addEventListener('click',async()=>{
  const intent=currentIntent, merchant=currentMerchant, user=currentUserId;
  try {
    const result=await call('/v1/checkout/qr/'+encodeURIComponent(intent));
    if (intent===currentIntent && merchant===currentMerchant && user===currentUserId) showIntent(result.intent);
  } catch(err) { notice(err.message); }
});
$('refresh-pey').addEventListener('click',async()=>{
  const button=$('refresh-pey'), intent=currentIntent, merchant=currentMerchant, user=currentUserId;
  if (currentIntentMode!=='LIVE') return;
  button.disabled=true;
  try {
    const result=await call('/v1/checkout/qr/'+encodeURIComponent(intent)+'/provider-status',{method:'POST',write:true});
    if (intent!==currentIntent || merchant!==currentMerchant || user!==currentUserId) return;
    showIntent(result.intent);
    notice(({
      PAYMENT_OBSERVED:'Pey reportó el pago de este QR.',
      NO_PAID_TRANSACTION_OBSERVED:'Pey todavía no reporta un pago para este QR.',
      QR_NOT_IDENTIFIED:'El QR sigue sin identificarse. Conserva el folio para revisarlo.',
    })[result.provider_lookup]);
  } catch(err) {
    if (intent===currentIntent && merchant===currentMerchant && user===currentUserId) notice(err.message);
  } finally {button.disabled=false;}
});

const reviewLabels = {
  MATCH_CANDIDATE_UNVERIFIED:'Coincidencia candidata; el abono no está verificado.',
  NO_BANK_RECORD:'No se encontró un registro bancario coincidente en los datos capturados.',
  DISCREPANCY_REVIEW_REQUIRED:'Hay una diferencia que requiere revisión.',
  REVERSAL_REVIEW_REQUIRED:'Hay un reverso que requiere revisión.',
  AMBIGUOUS_BANK_RECORDS:'Hay más de un registro candidato.',
  NO_PROVIDER_REPORT:'Todavía no hay una notificación del proveedor para esta solicitud.',
  PROVIDER_FIELDS_MISSING:'La notificación no contiene todos los datos para comparar.',
  PROVIDER_EVIDENCE_INVALID:'La evidencia guardada no pudo validarse.',
  PROVIDER_EVIDENCE_CONFLICT:'Hay notificaciones contradictorias que requieren revisión.',
  PROVIDER_EVENT_MISSING:'Falta la notificación guardada.',
  PROVIDER_EVIDENCE_MISSING:'Faltan datos de la notificación guardada.',
  PROVIDER_EVIDENCE_LIMIT_EXCEEDED:'Hay demasiadas notificaciones para esta revisión.',
  PROVIDER_SIGNATURE_NOT_RECORDED:'La notificación es anterior al registro de firma o no lo conserva.',
  PROVIDER_SIGNATURE_KEY_UNAVAILABLE:'No está disponible la versión de clave necesaria para verificar la firma.',
  PROVIDER_SIGNATURE_INVALID:'La firma no coincide con los datos o con la clave configurada.',
  OWNER_ACCOUNT_MISMATCH:'La cuenta del webhook difiere de la declarada por el titular.'
};
function reviewLabel(value) { return typeof reviewLabels[value]==='string' ? reviewLabels[value] : 'Resultado pendiente de revisión.'; }
function accountLabel(value) {
  const labels = {
    SIGNATURE_NOT_VERIFIED:'Cuenta sin comparar: no se verificó la firma.',
    PROVIDER_EVENT_UNAVAILABLE:'Cuenta sin comparar: no hay un evento válido.',
    NO_OWNER_REPORT:'No hay una cuenta declarada por el titular.',
    OWNER_REPORT_WITHDRAWN:'El titular retiró su confirmación.',
    OWNER_REPORT_NO_ACCOUNT_ID:'La confirmación no incluye un ID de cuenta.',
    WEBHOOK_ACCOUNT_ID_ABSENT:'El webhook no incluye un ID de cuenta para comparar.',
    MISMATCH_OWNER_REPORT:'El ID de cuenta difiere del declarado; revisa la cuenta y su historial.',
    PARTIAL_MATCH_UNVERIFIED:'El ID coincide con lo declarado, pero falta en algunos eventos; vínculo sin verificar.',
    MATCH_OWNER_REPORT_UNVERIFIED:'El ID coincide con lo declarado por el titular; vínculo con el proveedor sin verificar.'
  };
  return labels[value] || 'Comparación de cuenta no registrada.';
}
function signatureLabel(value) {
  if (value === 'VERIFIED') return 'Firma comprobada con la clave configurada; el abono sigue sin verificarse.';
  if (value === 'KEY_UNAVAILABLE') return 'No está disponible la clave histórica para comprobar la firma.';
  if (value === 'INVALID') return 'La firma no coincide con los datos o con la clave configurada.';
  return 'La firma no pudo comprobarse con la evidencia disponible.';
}
function clearReviewFields() {
  for (const id of ['review-clabe','review-tracking','review-amount','review-reference']) $(id).value='';
  $('review-direction').value='credit';
}
function resetReview() {
  reviewGeneration++;
  reviewAttempt=null;
  reviewBusy=false;
  $('review').hidden=true;
  $('review-fields').disabled=false;
  $('review-preview').disabled=false;
  $('review-save').disabled=false;
  $('review-status').textContent='';
  $('review-history').replaceChildren();
  clearReviewFields();
}
function reviewSnapshot() {
  if (!currentUserId || !currentMerchant || !currentIntent ||
      !['owner','admin'].includes(merchantRoles.get(currentMerchant))) {
    throw Error('Selecciona una solicitud de un comercio que puedas administrar.');
  }
  return {user:currentUserId, merchant:currentMerchant, intent:currentIntent, generation:reviewGeneration};
}
function sameReview(s) {
  return s.user===currentUserId && s.merchant===currentMerchant && s.intent===currentIntent && s.generation===reviewGeneration;
}
function reviewRecord() {
  const beneficiary=$('review-clabe').value, tracking=$('review-tracking').value;
  const reference=$('review-reference').value, amount=$('review-amount').value, direction=$('review-direction').value;
  if (!/^[0-9]{18}$/.test(beneficiary)) throw Error('Ingresa una CLABE de 18 dígitos.');
  if (!tracking || tracking!==tracking.trim() || tracking.length>256 || /[\u0000-\u001f\u007f-\u009f]/.test(tracking)) throw Error('Revisa la clave de rastreo.');
  if (!reference || reference!==reference.trim() || reference.length>100 || /[\u0000-\u001f\u007f-\u009f]/.test(reference)) throw Error('Revisa la referencia de tu evidencia.');
  if (!/^\d{1,7}(\.\d{1,2})?$/.test(amount)) throw Error('Revisa el importe.');
  const [pesos,cents='']=amount.split('.');
  const minor=Number(pesos)*100+Number(cents.padEnd(2,'0'));
  if (minor<=0 || minor>100000000 || !['credit','reversal'].includes(direction)) throw Error('Revisa el importe y el movimiento.');
  return {beneficiary,tracking_key:tracking,amount_minor:minor,direction,evidence_reference:reference,currency:'MXN'};
}
function setReviewBusy(value) {
  reviewBusy=value;
  $('review-fields').disabled=value;
  $('review-preview').disabled=value;
  $('review-save').disabled=value;
}
function reviewBase(intent) { return `/v1/checkout/qr/${encodeURIComponent(intent)}/reconciliation-reviews`; }
async function reviewCall(path,options={}) {
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),15000);
  try { return await call(path,{...options,signal:controller.signal}); }
  finally { clearTimeout(timer); }
}
function validSavedReview(response,snapshot) {
  const item=response && response.review;
  return item && /^[0-9a-f]{32}$/.test(item.id) && item.intent_id===snapshot.intent &&
    item.source==='USER_REPORTED_UNVERIFIED' && typeof item.classification==='string' &&
    typeof item.account_assessment_at_review==='string' &&
    response.bank_payment_confirmed===false && response.independent_bank_source_verified===false &&
    typeof response.provider_signature_reverified==='boolean' &&
    (!response.provider_signature_reverified || item.signature_assessment_at_review==='VERIFIED') &&
    response.beneficiary_binding_verified===false &&
    response.bank_records_persisted===false;
}
async function inspectReviewIntent(merchant,intentId) {
  const user=currentUserId, generation=selectionGeneration;
  const response=await reviewCall(`/v1/checkout/qr/${encodeURIComponent(intentId)}`);
  if (user!==currentUserId || merchant!==currentMerchant || generation!==selectionGeneration) return;
  if (!response.intent || response.intent.id!==intentId || response.intent.merchant_id!==merchant) throw Error('La solicitud no corresponde al comercio seleccionado.');
  showIntent(response.intent);
  window.RioWorkspace?.open('historial');
  $('review').scrollIntoView?.({behavior:'smooth',block:'start'});
}
async function loadReviewHistory() {
  const snapshot=reviewSnapshot();
  const data=await reviewCall(reviewBase(snapshot.intent));
  if (!sameReview(snapshot)) return;
  if (!Array.isArray(data.reviews) || data.reviews.some(item=>!item || item.intent_id!==snapshot.intent ||
      item.source!=='USER_REPORTED_UNVERIFIED' || !Number.isInteger(item.created_at) || typeof item.classification!=='string')) {
    throw Error('No se pudo interpretar el historial de revisiones.');
  }
  $('review-history').replaceChildren();
  for (const item of data.reviews) {
    const li=document.createElement('li');
    li.textContent=`${new Date(item.created_at*1000).toLocaleString('es-MX')} · ${reviewLabel(item.classification)} Firma al guardar: ${signatureLabel(item.signature_assessment_at_review)} Cuenta al guardar: ${accountLabel(item.account_assessment_at_review)}`;
    $('review-history').append(li);
  }
  if (data.truncated) $('review-status').textContent='Se muestran las 50 revisiones más recientes.';
}
$('review-preview').addEventListener('click',async()=>{
  if (reviewBusy) return;
  let snapshot;
  try {
    snapshot=reviewSnapshot();
    const record=reviewRecord();
    setReviewBusy(true);
    const response=await reviewCall(`/v1/checkout/qr/${encodeURIComponent(snapshot.intent)}/reconciliation-preview`,
                                    {method:'POST',write:true,body:{bank_records:[record]}});
    if (!sameReview(snapshot)) return;
    if (response.bank_payment_confirmed!==false || typeof response.classification!=='string' ||
        typeof response.provider_signature_reverified!=='boolean' || typeof response.account_assessment!=='string' ||
        (response.provider_signature_reverified !== (response.signature_assessment==='VERIFIED'))) throw Error('Respuesta de revisión inválida.');
    $('review-status').textContent=`Vista previa: ${reviewLabel(response.classification)} ${signatureLabel(response.signature_assessment)} ${accountLabel(response.account_assessment)}`;
  } catch (error) {
    if (!snapshot || sameReview(snapshot)) $('review-status').textContent=error.status===409 ?
      'La información del cobro cambió durante la revisión. Vuelve a generar la vista previa.' : error.message;
  }
  finally { if (snapshot && sameReview(snapshot)) setReviewBusy(false); }
});
$('review-form').addEventListener('submit',async event=>{
  event.preventDefault();
  if (reviewBusy) return;
  let snapshot;
  try {
    snapshot=reviewSnapshot();
    const record=reviewRecord(), signature=JSON.stringify([record]);
    if (reviewAttempt && reviewAttempt.signature!==signature) throw Error('Hay un resultado anterior sin confirmar. Recupera esa revisión antes de cambiar los datos.');
    if (!reviewAttempt) reviewAttempt={key:crypto.randomUUID().replaceAll('-',''),signature};
    const key=reviewAttempt.key, base=reviewBase(snapshot.intent);
    setReviewBusy(true);
    let response, recovered=false;
    try {
      response=await reviewCall(base,{method:'POST',write:true,extraHeaders:{'Idempotency-Key':key},body:{bank_records:[record]}});
    } catch (error) {
      if (error.status!==409 || error.code!=='REVIEW_REQUEST_ALREADY_USED') throw error;
      response=await reviewCall(`${base}/by-request/${encodeURIComponent(key)}`);
      recovered=true;
    }
    if (!sameReview(snapshot)) return;
    if (!validSavedReview(response,snapshot)) throw Error('No se pudo verificar la revisión guardada. Consulta el historial.');
    reviewAttempt=null;
    clearReviewFields();
    $('review-status').textContent=recovered ?
      `Se recuperó una revisión anterior. El sistema no conservó los datos bancarios para comprobar que sean los mismos. ${reviewLabel(response.review.classification)} ${accountLabel(response.review.account_assessment_at_review)}` :
      `Revisión guardada. ${reviewLabel(response.review.classification)} ${accountLabel(response.review.account_assessment_at_review)}`;
    try { await loadReviewHistory(); } catch (_) { if (sameReview(snapshot)) notice('Revisión guardada; no se pudo actualizar el historial.'); }
  } catch (error) {
    if (snapshot && sameReview(snapshot) && error.status===422) {
      reviewAttempt=null;
      $('review-status').textContent='Revisa los datos capturados y vuelve a intentar.';
    } else if (!snapshot || sameReview(snapshot)) {
      $('review-status').textContent=`${error.name==='AbortError' ? 'La respuesta tardó demasiado.' : error.message} Si el resultado es incierto, vuelve a intentar con los mismos datos.`;
    }
  } finally { if (snapshot && sameReview(snapshot)) setReviewBusy(false); }
});
$('review-reload').addEventListener('click',async()=>{
  let snapshot;
  try { snapshot=reviewSnapshot(); await loadReviewHistory(); }
  catch(error) { if (!snapshot || sameReview(snapshot)) $('review-status').textContent=error.message; }
});
async function loadReceipt(intent, live, attempt=0) {
  if (currentIntent !== intent.id) return;
  const status=$('receipt-status'),link=$('receipt-link');
  if(!status || !link)return;
  status.textContent='';link.hidden=true;link.removeAttribute('href');
  if(!live)return;
  const merchant=currentMerchant,user=currentUserId;
  try {
    const result=await call('/v1/checkout/qr/'+encodeURIComponent(intent.id)+'/receipt');
    if(currentIntent!==intent.id || merchant!==currentMerchant || user!==currentUserId)return;
    if(attempt<5 && intent.status==='PROVIDER_REPORTED' && (!result.issued || Object.values(result.deliveries||{}).some(value=>['PENDING','SENDING'].includes(value)))) {
      setTimeout(()=>{if(currentIntent===intent.id && merchant===currentMerchant && user===currentUserId)void loadReceipt(intent,live,attempt+1);},5000);
    }
    if(!result.issued){status.textContent=(result.enabled?'':'Envío de correos desactivado. ')+'El comprobante se emitirá cuando pey confirme el pago.';return;}
    if(typeof result.link==='string') {
      const url=new URL(result.link,location.origin);
      if(url.origin===location.origin && url.pathname.startsWith('/comprobante/')){link.href=url.href;link.hidden=false;}
    }
    const names={SENT:'aceptado por el servidor de correo',PENDING:'pendiente',SENDING:'enviando',UNCERTAIN:'entrega incierta; requiere revisión',CANCELLED:'cancelado',UNVERIFIED:'correo receptor sin verificar'};
    status.textContent='Pago confirmado por pey. '+(result.enabled?'':'Envío de correos desactivado. ')+Object.entries(result.deliveries).map(([role,value])=>(role==='payer'?'Pagador':'Receptor')+': '+(names[value]||'pendiente')).join(' · ');
  }catch(_){if(currentIntent===intent.id)status.textContent='No se pudo consultar el comprobante. Actualiza el estado.';}
}


$('payment-method')?.addEventListener('change',updateChargeControls);
$('shared-new-sale')?.addEventListener('click',()=>{if($('payment-method').value==='cash' && !pendingOrder)$('cash-new-sale').click();else $('new-order').click();});

boot();
