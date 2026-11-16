'use strict';
(() => {
  const panel = $('configuracion-pey');
  const form = $('private-pey-form');
  const state = $('private-pey-state');
  const label = $('private-pey-merchant');
  const confirm = $('private-pey-confirm');
  const url = $('private-pey-url');
  const activate = $('private-pey-activate');
  const remove = $('private-pey-delete');
  const bank = $('private-pey-bank');
  const defaultBank = $('private-pey-default-bank');
  const submit = form.querySelector('button[type=submit]');
  let pending = false;
  let generation = 0;
  let configured = false;
  let active = false;
  let available = false;
  let saved = false;
  let lastError = false;
  let syncing = false;
  let channel;
  try { channel = new BroadcastChannel('rio-pey-configuration'); } catch (_) {}
  function changed() { channel?.postMessage('changed'); }
  async function synchronize() {
    if (pending || syncing || !currentUserId || !currentMerchant || document.hidden) return;
    const merchant = currentMerchant, user = currentUserId, version = generation;
    syncing = true;
    try {
      const result = await call('/v1/merchants/'+encodeURIComponent(merchant)+'/pey-status');
      if (merchant !== currentMerchant || user !== currentUserId || version !== generation) return;
      $('pey-connection-status').textContent = result.payment_active ? 'CoDi habilitado' : 'CoDi pendiente de activación';
      if (!panel.hidden) await refresh(scope());
    } catch (_) {
      if (merchant === currentMerchant && user === currentUserId)
        $('pey-connection-status').textContent = 'No pudimos actualizar la conexión. Reintentando…';
    } finally {
      syncing = false;
      if (merchant !== currentMerchant || user !== currentUserId) void synchronize();
    }
  }
  channel?.addEventListener('message', () => { void synchronize(); });
  window.addEventListener('focus', () => { void synchronize(); });
  document.addEventListener('visibilitychange', () => { void synchronize(); });
  setInterval(() => { void synchronize(); }, 15000);

  function controls() {
    submit.disabled = pending || !available;
    remove.disabled = pending || !saved;
    activate.disabled = pending || !available || !configured || active || !confirm.checked || !livePaymentsEnabled;
  }

  function scope() {
    if (!currentUserId || !currentMerchant || merchantRoles.get(currentMerchant) !== 'owner') {
      throw Error('Selecciona un comercio del que seas titular.');
    }
    const merchant = currentMerchant;
    return {merchant, user:currentUserId, generation, path:'/v1/merchants/'+encodeURIComponent(merchant)+'/pey-settings'};
  }

  function isCurrent(snapshot) {
    return snapshot.generation===generation && snapshot.merchant===currentMerchant && snapshot.user===currentUserId;
  }

  async function refresh(snapshot) {
    const result = await call(snapshot.path);
    if (!isCurrent(snapshot)) return;
    configured = result.api_key_configured && result.webhook_secret_configured;
    active = result.payment_active === true;
    saved = result.configuration_saved === true || result.api_key_configured === true || result.webhook_secret_configured === true || result.bank_account_id_configured === true;
    $('private-pey-account-status').textContent = active ? 'CoDi habilitado' : saved ? (result.configuration_available ? 'Conexión guardada · CoDi sin habilitar' : 'Conexión guardada · No disponible') : 'Sin conexión guardada';
    $('private-pey-empty').hidden = saved;
    $('private-pey-saved-account').textContent = result.bank_account_id || (result.bank_account_id_configured ? 'ID guardado · No disponible' : result.api_key_configured ? 'Cuenta CoDi vinculada a la llave de pey' : 'Sin cuenta vinculada');
    $('private-pey-saved-key-id').textContent = result.api_key_id || (result.api_key_configured ? 'Llave guardada · ID no indicado' : 'Sin llave guardada');
    const date = value => Number.isSafeInteger(value) && value > 0 ? new Date(value*1000).toLocaleString('es-MX') : 'Sin registro';
    $('private-pey-updated').textContent = date(result.updated_at);
    $('private-pey-verified').textContent = date(result.verified_at);
    url.value = result.webhook_url || '';
    $('private-pey-url-group').hidden = !url.value;
    available = result.configuration_available === true;
    label.textContent = $('merchant').selectedOptions[0]?.textContent || 'Comercio seleccionado';
    if (!lastError) state.textContent = (active ? 'CoDi habilitado. ' : '') +
      'Llave '+(result.api_key_configured?'guardada':'pendiente')+' · Webhook '+
      (result.webhook_secret_configured?'guardado':'pendiente')+' · Cuenta '+
      (result.bank_account_id_configured?'por ID':result.api_key_configured?'vinculada a la llave':'pendiente');
    $('pey-connection-status').textContent = active ? 'CoDi habilitado' : 'CoDi pendiente de activación';
    controls();
    return result;
  }

  async function run(action, after) {
    if (pending) return;
    let snapshot;
    generation += 1;
    try { snapshot = scope(); }
    catch (error) { state.textContent = error.message; return; }
    pending = true;
    lastError = false;
    controls();
    try {
      const result = await action(snapshot);
      if (isCurrent(snapshot)) {
        await refresh(snapshot);
        if (after && isCurrent(snapshot)) after(result, snapshot);
        changed();
      }
    } catch (error) {
      if (isCurrent(snapshot)) { lastError = true; state.textContent = error.message; }
    } finally {
      if (isCurrent(snapshot)) {
        pending = false;
        controls();
      }
    }
  }

  function reset() {
    generation += 1;
    form.reset();
    confirm.checked = false;
    bank.disabled = false;
    pending = false;
    configured = false;
    active = false;
    saved = false;
    lastError = false;
    available = false;
    $('private-pey-account-status').textContent = 'Consultando tu cuenta…';
    $('private-pey-empty').hidden = true;
    for (const id of ['private-pey-saved-account','private-pey-saved-key-id','private-pey-updated','private-pey-verified']) $(id).textContent = '—';
    url.value = '';
    $('private-pey-url-group').hidden = true;
    panel.hidden = !currentMerchant || merchantRoles.get(currentMerchant)!=='owner';
    state.textContent = 'Consultando configuración del comercio…';
    controls();
    $('pey-connection-status').textContent = 'Consultando conexión de pey…';
    void synchronize();
  }

  window.addEventListener('rio-merchant-selected', reset);
  $('private-pey-check').addEventListener('click', () => run(async () => {}));
  confirm.addEventListener('change', controls);
  defaultBank.addEventListener('change', () => { bank.disabled = defaultBank.checked; });
  $('private-pey-copy').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(url.value); }
    catch (_) { url.select(); }
  });
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (submit.disabled) return;
    const body = {};
    for (const [id,key] of [['private-pey-key','api_key'],['private-pey-webhook','webhook_secret'],
                            ['private-pey-key-id','api_key_id'],['private-pey-bank','bank_account_id']]) {
      const value = $(id).value.trim();
      if (value) body[key]=value;
    }
    if (defaultBank.checked) body.bank_account_id = null;
    if (!Object.keys(body).length) { state.textContent='Agrega un dato para guardar.'; return; }
    void run(async snapshot => {
      const result = await call(snapshot.path,{method:'PUT',write:true,body});
      if (result.saved !== true) throw Error('El servidor no confirmó el guardado.');
      if (isCurrent(snapshot)) { form.reset(); bank.disabled = false; confirm.checked = false; }
      return result;
    });
  });
  activate.addEventListener('click', () => {
    if (activate.disabled) return;
    void run(snapshot => call(snapshot.path+'/activate',{
      method:'POST',write:true,extraHeaders:{'X-Pey-Beneficiary-Confirmed':'true'},
    }), (result, snapshot) => {
      if (result.payment_active !== true || !active) throw Error('No se confirmó la activación. Consulta el estado antes de continuar.');
      state.textContent = 'CoDi habilitado. Conexión guardada. Actualizando la página…';
      try { sessionStorage.setItem('rio.pey.activation', JSON.stringify({user:snapshot.user,merchant:snapshot.merchant,time:Date.now()})); } catch (_) {}
      location.hash = '#configuracion-pey';
      location.reload();
    });
  });
  remove.addEventListener('click', () => {
    if (remove.disabled || !window.confirm('¿Eliminar la conexión de pey de este comercio? Se desactivarán los nuevos cobros. La cuenta en pey y el historial se conservan.')) return;
    confirm.checked = false;
    void run(snapshot => call(snapshot.path,{method:'DELETE',write:true}), () => { state.textContent='Conexión eliminada de este comercio. CoDi desactivado.'; });
  });
  // The merchant may have loaded before this deferred script finished downloading.
  if (currentUserId && currentMerchant) reset();
})();
