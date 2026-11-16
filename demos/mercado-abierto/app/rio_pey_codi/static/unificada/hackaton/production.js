(() => {
 'use strict';
 const $ = id => document.getElementById(id);
 const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const money = minor => new Intl.NumberFormat('es-MX',{style:'currency',currency:'MXN'}).format(Number(minor || 0) / 100);
 const units = {piece:'pieza',kg:'kg',meter:'metro',service:'servicio'};
 const kinds = {merchant:'Comerciante',freighter:'Fletero',both:'Comerciante y fletero'};
 const statuses = {REQUESTED:'Solicitado',QUOTED:'Cotizado',ACCEPTED:'Aceptado',PREPARED:'Preparado',SHIPPED:'Enviado',RECEIVED:'Recibido',REJECTED:'Rechazado',CANCELLED:'Cancelado',PROPOSED:'Propuesto',DELIVERED:'Entrega declarada'};
 const names = {catalogo:'Ofertas de la comunidad',carrito:'Carrito de compra',direcciones:'Direcciones de entrega',publicar:'Mis publicaciones',directorio:'Negocios y fleteros',pedidos:'Cotizaciones y pedidos',fletes:'Fletes'};
 let user = null, csrf = '', data = null, view = 'catalogo', busy = false, generation = 0, ready = false;
 let editListing = null, selectedBusiness = '', catalogSearch = '', catalogAlcaldia = '', directoryAlcaldia = '', directoryKind = '';
 let cartData = null, deliveryAddresses = [], editAddressId = null, deepLinkHandled = false;
 let lastDialogTrigger = null, lastRefresh = 0, catalogCursor = null, catalogBusy = false, catalogGeneration = 0, searchTimer = null;
 const requestKeys = new Map();
 const ownBusiness = id => data?.my_businesses?.find(b => b.id === id);
 const canManage = id => ['owner','admin'].includes(ownBusiness(id)?.role);
 const canCharge = id => ['owner','admin','cashier'].includes(ownBusiness(id)?.role);
  const editableBusinesses = () => (data?.my_businesses || []).filter(b => canManage(b.id));
 const quantityText = milli => new Intl.NumberFormat('es-MX',{maximumFractionDigits:3}).format(Number(milli || 0) / 1000);
 const decimalText = (integer, places) => (Number(integer || 0) / 10 ** places).toFixed(places).replace(/\.?0+$/,'') || '0';
 function announce(text, error = false) { const target = $('market-status'); if (target) { target.textContent = text; target.classList.toggle('error', error); } }
 function detail(error) { return error?.message || 'No se pudo completar la operación. Intenta de nuevo.'; }
 function amount(value, places, zero = false) {
  const raw = String(value).trim();
  const match = new RegExp('^(0|[1-9][0-9]{0,8})(?:[.,]([0-9]{1,'+places+'}))?$').exec(raw);
  if (!match) throw Error(places === 2 ? 'Indica un importe con hasta dos decimales.' : 'Indica una cantidad con hasta tres decimales.');
  const parsed = Number(match[1]) * 10 ** places + Number((match[2] || '').padEnd(places,'0'));
  if (!Number.isSafeInteger(parsed) || parsed > (places===2?100000000:1000000000) || (zero ? parsed < 0 : parsed <= 0)) throw Error('La cantidad está fuera del límite permitido.');
  return parsed;
 }
 function updateListingFeePreview() {
  const form=$('listing-form'), target=$('listing-fee-preview'); if(!form||!target)return;
  try {
   const base=amount(form.elements.price.value,2), discountBps=amount(form.elements.discount.value || '0',2,true);
   if(discountBps>9900)throw Error('El descuento mayorista no puede superar 99%.');
   const discounted=Math.floor((base*(10000-discountBps)+5000)/10000), fee=Math.floor((discounted*5+50)/100);
   target.textContent='Desglose del vendedor · base con descuento '+money(discounted)+' · recargo de producto 5% '+money(fee)+' · precio al comprador '+money(discounted+fee)+'. El flete se calcula aparte.';
  } catch (_) { target.textContent='Desglose del vendedor: completa un precio válido y un descuento de hasta 99%.'; }
 }
 function readImageFile(file) {
  return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onerror=()=>reject(Error('No se pudo leer la foto seleccionada.'));reader.onload=()=>{const value=String(reader.result||'');const comma=value.indexOf(',');if(comma<0)reject(Error('La foto no pudo codificarse.'));else resolve({mime_type:file.type,data_base64:value.slice(comma+1)})};reader.readAsDataURL(file)});
 }
 function quantity(value, unit) { const n = amount(value,3); if (['piece','service'].includes(unit) && n % 1000) throw Error('Las piezas y servicios se solicitan en cantidades enteras.'); return n; }
 function key(fingerprint) { if (!requestKeys.has(fingerprint)) requestKeys.set(fingerprint,crypto.randomUUID().replace(/-/g,'')); return requestKeys.get(fingerprint); }
 function locality(code) { return data?.localities?.find(l => l.code === code)?.name || code || 'Localidad por completar'; }
 function locationText(item) { return [item.colonia,locality(item.alcaldia),'Ciudad de México'].filter(Boolean).join(' · '); }
 function publicationStatus(item) { const profile = ownBusiness(item.merchant_id)?.profile; return !item.published?'Sin publicar':profile?.published && ['merchant','both'].includes(profile.kind)?'Publicada':'Pendiente de perfil público'; }
 function historyNotice() { return data.history_truncated?'<p class="notice">Esta vista muestra hasta 500 registros recientes por tipo de operación. El historial anterior se conserva en el servidor.</p>':''; }
 function options(items, selected = '', placeholder = null) { return (placeholder === null ? '' : '<option value="">'+esc(placeholder)+'</option>') + items.map(item => '<option value="'+esc(item[0])+'"'+(String(item[0])===String(selected)?' selected':'')+'>'+esc(item[1])+'</option>').join(''); }
 function localityOptions(selected = '', placeholder = 'Todas las alcaldías') { return options((data?.localities || []).map(l => [l.code,l.name]),selected,placeholder); }
 function businessOptions(selected = '', manageable = false) { return options((manageable?editableBusinesses():data?.my_businesses || []).map(b => [b.id,b.name]),selected,'Selecciona tu negocio'); }
 function field(name,label,value = '',extra = '') { return '<label class="field">'+label+'<input name="'+esc(name)+'" value="'+esc(value)+'" '+extra+'></label>'; }
 function button(label,action,id = '',extra = '',secondary = true) { return '<button type="button" class="button'+(secondary?' secondary':'')+'" data-action="'+esc(action)+'" data-id="'+esc(id)+'" '+extra+(busy?' disabled':'')+'>'+label+'</button>'; }
 function whatsappLink(phone,name,context,label=null) {
  const digits = String(phone || '').replace(/\D/g,'');
  if (digits.length < 8 || digits.length > 15) return '';
  const message = 'Hola, te contacto por '+String(context || 'Mercado Abierto')+'.';
  const href = 'https://wa.me/'+digits+'?text='+encodeURIComponent(message);
  return '<a class="button secondary whatsapp-contact" href="'+esc(href)+'" target="_blank" rel="noopener noreferrer">'+esc(label || ('WhatsApp · '+(name || 'contactar')))+'</a>';
 }
 function contactSellerButton(p) { return whatsappLink(p.whatsapp_phone,p.merchant_name,'la oferta '+p.name,'Contactar vendedor') || button('Contactar vendedor','quote',p.id); }
 function discountPercent(bps) { return (Number(bps || 0) / 100).toLocaleString('es-MX',{maximumFractionDigits:2}); }
 function offeredPrice(p) { return Number(p.wholesale_discount_bps || 0) > 0 ? '<p class="regular-price"><s>'+money(p.regular_price_minor)+'</s> <small>Precio regular</small></p><p class="wholesale-price">Mayoreo · '+discountPercent(p.wholesale_discount_bps)+'% de descuento<br><strong>'+money(p.price_minor)+'</strong></p>' : '<p class="price">'+money(p.price_minor)+' <small>/ '+esc(units[p.unit] || p.unit)+'</small></p>'; }
 function productImage(p) { return p.image_url ? '<img class="product-image" src="'+esc(p.image_url)+'" alt="Foto de '+esc(p.name)+'" loading="lazy">' : ''; }
 function badge(status) { return '<span class="badge '+(['RECEIVED','DELIVERED','ACCEPTED'].includes(status)?'good':['REJECTED','CANCELLED'].includes(status)?'closed':'pending')+'">'+esc(statuses[status] || status)+'</span>'; }
 function heading(title,description) { return '<header class="page-heading"><div><p class="eyebrow">Ciudad de México</p><h1 tabindex="-1">'+title+'</h1><p class="muted">'+description+'</p></div></header>'; }
 function empty(title,description,action = '') { return '<section class="empty"><h2>'+title+'</h2><p>'+description+'</p>'+action+'</section>'; }
 async function api(path, method = 'GET', body) {
  const controller = new AbortController(), timer = setTimeout(() => controller.abort(),20000);
  try {
   const response = await fetch(path,{method,credentials:'same-origin',cache:'no-store',signal:controller.signal,headers:{Accept:'application/json',...(method==='GET'?{}:{'Content-Type':'application/json','X-CSRF-Token':csrf})},...(body===undefined?{}:{body:JSON.stringify(body)})});
   let result; try { result = await response.json(); } catch (_) { throw Error('El servidor no devolvió una respuesta válida.'); }
   if (!response.ok) {
    if (response.status === 401) { window.RioSession?.lock(); location.replace('/login?next=%2Fmercado-abierto'); }
    const message = typeof result.detail === 'string' ? result.detail : response.status === 422 ? 'Revisa los campos y vuelve a intentar.' : 'No se pudo completar la operación ('+response.status+').';
    throw Error(message);
   }
   return result;
  } catch (error) { if (error.name === 'AbortError') throw Error(method === 'GET' ? 'La consulta tardó demasiado. Pulsa Actualizar para intentar de nuevo.' : 'No se pudo confirmar el guardado. Revisa la lista antes de volver a enviar.'); throw error; }
  finally { clearTimeout(timer); }
 }
 async function refresh({silent = false} = {}) {
  if (busy) return false;
  const current = ++generation;
  try {
   const identity = await api('/api/auth/me');
   if (current !== generation) return false;
   if (!$('market-app')) { ready = false; return false; }
   if (user && user.id !== identity.user.id) { data = null; requestKeys.clear(); editListing = null; selectedBusiness = ''; closeDialog(); $('market-app').replaceChildren(); }
   user = identity.user; csrf = identity.csrf_token;
   const received = await api('/v1/market/bootstrap');
   if (current !== generation) return false;
   data = received; catalogGeneration++; catalogCursor = received.next_cursor || null; catalogBusy = false;
   ready = true; lastRefresh = Date.now(); $('market-identity').textContent = user.email || '';
   const requestedBusiness = new URLSearchParams(location.search).get('merchant');
   if (!selectedBusiness || !editableBusinesses().some(b => b.id === selectedBusiness)) selectedBusiness = editableBusinesses().find(b => b.id === requestedBusiness)?.id || editableBusinesses()[0]?.id || '';
   cartData = null; deliveryAddresses = [];
   if (selectedBusiness) await Promise.all([loadCart(selectedBusiness),loadDeliveryAddresses(selectedBusiness)]);
   render();
   if (!deepLinkHandled) await handleDeepLink();
   if (view === 'catalogo' && (catalogSearch || catalogAlcaldia)) await loadCatalog(true);
   if (location.hash === '#perfil') $('profile-form')?.querySelector('[name=alcaldia]')?.focus({preventScroll:true});
   if (location.hash === '#whatsapp') focusWhatsappSettings();
   if (!silent) announce('Información actualizada desde el servidor.'); return true;
  } catch (error) {
   if (current !== generation) return false;
   announce(detail(error),true);
   if (!data) $('market-app').innerHTML = heading('Mercado Abierto','Tus ofertas y operaciones se consultan en el servidor.')+empty('No se pudo cargar la información','Comprueba tu conexión y vuelve a intentar.',button('Volver a consultar','refresh'));
   return false;
  }
 }
 function navigate(next, focus = true) {
  if (next === 'perfil') next = 'publicar';
  const whatsappSettings = next === 'whatsapp';
  if (whatsappSettings) next = 'publicar';
  if (!Object.hasOwn(names,next)) next = 'catalogo';
  if (busy) return;
  view = next; history.replaceState(null,'','#'+(whatsappSettings?'whatsapp':view)); render();
  if (focus) { const title = $('market-app').querySelector('h1'); title?.focus({preventScroll:true}); title?.scrollIntoView({block:'start'}); }
  if (whatsappSettings) focusWhatsappSettings();
 }
 function focusWhatsappSettings() {
  const input = $('market-whatsapp-phone');
  if (!input) return;
  input.focus({preventScroll:true});
  input.closest('.panel')?.scrollIntoView({block:'start',behavior:'smooth'});
 }
 function render() {
  if (!data || !$('market-app')) return;
  $('market-nav').querySelectorAll('[data-view]').forEach(b => b.setAttribute('aria-current',b.dataset.view===view?'page':'false'));
  const pages = {catalogo:renderCatalog,carrito:renderCart,direcciones:renderAddresses,publicar:renderPublish,directorio:renderDirectory,pedidos:renderOrders,fletes:renderFreights};
  $('market-app').innerHTML = pages[view]();
  if (view === 'catalogo') renderCatalogResults();
  if (view === 'directorio') renderDirectoryResults();
  if (view === 'publicar') { fillProfile(selectedBusiness); updateListingFeePreview(); }
 }
 function renderCatalog() {
  return heading('Ofertas de la comunidad','Productos y servicios publicados por los negocios de Ciudad de México. Consulta precios y solicita una cotización o un pedido.')+'<form class="toolbar" id="catalog-filter" role="search"><label class="field">Buscar producto o negocio<input id="catalog-search" type="search" maxlength="120" value="'+esc(catalogSearch)+'" placeholder="¿Qué necesitas?"></label><label class="field">Alcaldía<select id="catalog-alcaldia">'+localityOptions(catalogAlcaldia)+'</select></label><button type="submit" class="button secondary">Buscar</button></form><p id="catalog-count" class="muted small" role="status"></p><div class="cards" id="catalog-list"></div><div class="actions"><button type="button" id="catalog-more" class="button secondary" data-action="catalog-more" hidden>Cargar más ofertas</button></div>';
 }
 function renderCatalogResults() {
  const words = catalogSearch.toLocaleLowerCase('es-MX').trim();
  const listings = (data.listings || []).filter(p => p.published && (!catalogAlcaldia || p.alcaldia === catalogAlcaldia) && (!words || [p.name,p.description,p.category,p.merchant_name].join(' ').toLocaleLowerCase('es-MX').includes(words)));
  $('catalog-count').textContent = (catalogBusy?'Consultando… · ':'')+listings.length+' '+(listings.length===1?'oferta cargada':'ofertas cargadas')+(catalogCursor?' · Hay más ofertas disponibles.':'');
  $('catalog-list').innerHTML = listings.length ? listings.map(p => '<article class="card" data-listing-id="'+esc(p.id)+'"><span class="badge">'+esc(p.category || 'Productos y servicios')+'</span>'+productImage(p)+'<h2>'+esc(p.name)+'</h2><p>'+esc(p.description)+'</p><p class="muted">'+esc(p.merchant_name)+'</p><p class="location">'+esc(locationText(p))+'</p>'+offeredPrice(p)+'<p class="small muted">Disponible: '+quantityText(p.stock_milli)+' '+esc(units[p.unit] || p.unit)+'</p><div class="actions">'+(canManage(p.merchant_id)?button('Editar publicación','edit-listing',p.id):button('Agregar al carrito','cart-add',p.id,'',false)+button('Solicitar pedido','order',p.id))+contactSellerButton(p)+button('Ver ficha y QR','product-qr',p.id)+'</div></article>').join('') : empty(catalogBusy?'Consultando las ofertas…':'Todavía no hay ofertas con estos filtros','Las publicaciones de todos los negocios aparecerán aquí cuando sus titulares las den de alta.',button('Publicar mis productos','view-publicar'));
  $('catalog-more').hidden = !catalogCursor; $('catalog-more').disabled = catalogBusy || busy;
 }
 async function loadCatalog(reset = true) {
  if (!data || busy || !reset && (!catalogCursor || catalogBusy)) return;
  const current = ++catalogGeneration, contextUser = user?.id;
  const params = new URLSearchParams(); if (catalogSearch.trim()) params.set('q',catalogSearch.trim()); if (catalogAlcaldia) params.set('alcaldia',catalogAlcaldia); if (!reset && catalogCursor) params.set('cursor',catalogCursor);
  catalogBusy = true; if (view === 'catalogo') renderCatalogResults();
  try {
   const result = await api('/v1/market/listings?'+params);
   if (current !== catalogGeneration || user?.id !== contextUser) return;
   data.listings = reset ? result.listings : [...new Map([...data.listings,...result.listings].map(p => [p.id,p])).values()]; catalogCursor = result.next_cursor || null;
  } catch (error) { if (current === catalogGeneration) announce(detail(error),true); }
  finally { if (current === catalogGeneration) { catalogBusy = false; if (view === 'catalogo') renderCatalogResults(); } }
 }
 async function loadCart(merchantId = selectedBusiness) {
  if (!merchantId || !canManage(merchantId)) { cartData = null; return null; }
  const result = await api('/v1/market/cart?buyer_merchant_id='+encodeURIComponent(merchantId));
  if (selectedBusiness === merchantId || view === 'carrito') cartData = result;
  return result;
 }
 async function loadDeliveryAddresses(merchantId = selectedBusiness) {
  if (!merchantId || !canManage(merchantId)) { deliveryAddresses = []; return []; }
  const result = await api('/v1/market/delivery-addresses?merchant_id='+encodeURIComponent(merchantId));
  if (selectedBusiness === merchantId || view === 'direcciones') deliveryAddresses = result.addresses || [];
  return deliveryAddresses;
 }
 function renderCart() {
  const businesses = editableBusinesses();
  if (!businesses.length) return heading('Carrito de compra','Cada negocio administra su carrito y sus direcciones de entrega.')+empty('Necesitas administrar un negocio','Agrega un negocio o pide acceso de administración para comprar.','<a class="button" href="/#mis-negocios">Abrir Mis negocios</a>');
  const items = cartData?.items || [];
  const rows = items.map(item => '<article class="cart-row">'+productImage(item.listing)+'<div><h3>'+esc(item.listing.name)+'</h3><p>'+quantityText(item.quantity_milli)+' '+esc(units[item.listing.unit] || item.listing.unit)+' · '+money(item.line_total_minor)+'</p><p class="small muted">Vendedor: '+esc(item.listing.merchant_name)+'</p></div><button class="button secondary" type="button" data-action="cart-remove" data-id="'+esc(item.listing.id)+'">Quitar</button></article>').join('');
  const addresses = deliveryAddresses.map(a=>[a.id,a.label+' · '+a.colonia+', '+locality(a.alcaldia)]);
  const sellerIds = [...new Set(items.map(i=>i.listing.merchant_id))];
  const mixedSellers = sellerIds.length > 1;
  return heading('Carrito de compra','Revisa los productos y elige la dirección donde se entregarán. Un QR unificado reúne todos los productos de un mismo vendedor.')+(mixedSellers?'<p class="notice">El carrito tiene varios vendedores. pey liquida cada QR CoDi a una sola cuenta receptora; para pagar en una sola operación, todos los productos deben pertenecer al mismo vendedor. Retira artículos de otros vendedores y compra esos pedidos por separado.</p>':'')+'<label class="field">Cuenta compradora<select id="cart-business">'+businessOptions(selectedBusiness,true)+'</select></label><div class="list">'+(rows || empty('Tu carrito está vacío','Agrega productos desde Ofertas o desde los perfiles de los mayoristas.',button('Ver ofertas','view-catalogo')))+'</div>'+(items.length?'<section class="panel"><h2>Confirmar compra</h2><p class="price">Total de productos: '+money(cartData.total_minor)+'</p><form id="cart-checkout" class="form-grid"><input type="hidden" name="buyer_merchant_id" value="'+esc(selectedBusiness)+'"><label class="field full">Dirección de entrega<select name="address_id" required>'+options(addresses,'','Selecciona una dirección')+'</select></label>'+((!addresses.length)?'<p class="notice full">Registra primero una dirección para esta cuenta.</p>':'')+'<p class="small muted full">El QR unificado conserva las referencias de todos los productos del pedido. Tras la aceptación del vendedor, Caja genera un solo QR CoDi por el total del pedido; la dirección elegida queda guardada en su historial.</p><button class="button full" type="submit"'+((mixedSellers||!addresses.length)?' disabled':'')+'>Confirmar compra y generar QR unificado</button></form></section>':'')+'<div class="actions">'+button('Administrar direcciones','view-direcciones')+button('Historial de pedidos','view-pedidos')+'</div>';
 }
 function renderAddresses() {
  if (!editableBusinesses().length) return heading('Direcciones de entrega','Guarda las direcciones que cada negocio puede usar en sus compras.')+empty('Necesitas administrar un negocio','Las direcciones se guardan de forma privada por cuenta.','<a class="button" href="/#mis-negocios">Abrir Mis negocios</a>');
  const editing = editAddressId && deliveryAddresses.find(a=>a.id===editAddressId);
  const form = '<section class="panel"><h2>'+(editing?'Editar dirección':'Agregar dirección')+'</h2><form id="address-form" class="form-grid"><label class="field full">Negocio<select id="address-business" name="merchant_id" required>'+businessOptions(selectedBusiness,true)+'</select></label>'+field('label','Nombre de la dirección',editing?.label || '','required maxlength="80"')+field('recipient','Persona que recibe',editing?.recipient || '','required maxlength="120"')+field('phone','Teléfono de contacto',editing?.phone || '','required type="tel" inputmode="tel" placeholder="+525512345678"')+field('street','Calle',editing?.street || '','required maxlength="160"')+field('exterior_number','Número exterior',editing?.exterior_number || '','required maxlength="20"')+field('interior_number','Número interior',editing?.interior_number || '','maxlength="20"')+field('colonia','Colonia',editing?.colonia || '','required maxlength="100"')+'<label class="field">Alcaldía<select name="alcaldia" required>'+localityOptions(editing?.alcaldia || '','Selecciona una alcaldía')+'</select></label>'+field('postal_code','Código postal',editing?.postal_code || '','required inputmode="numeric" pattern="[0-9]{5}" maxlength="5"')+'<label class="field full">Referencias<textarea name="reference_notes" maxlength="240">'+esc(editing?.reference_notes || '')+'</textarea></label><button class="button full" type="submit">'+(editing?'Guardar dirección':'Agregar dirección')+'</button>'+(editing?button('Cancelar edición','cancel-address-edit'):'')+'</form></section>';
  const cards = deliveryAddresses.length ? '<div class="cards">'+deliveryAddresses.map(a=>'<article class="card"><span class="badge">'+esc(a.label)+'</span><h3>'+esc(a.recipient)+'</h3><p>'+esc(a.street)+' '+esc(a.exterior_number)+(a.interior_number?' int. '+esc(a.interior_number):'')+'</p><p>'+esc(a.colonia)+' · '+esc(locality(a.alcaldia))+' · CP '+esc(a.postal_code)+'</p><p>'+esc(a.phone)+'</p>'+(a.reference_notes?'<p>'+esc(a.reference_notes)+'</p>':'')+'<div class="actions">'+button('Editar','edit-address',a.id)+button('Eliminar','delete-address',a.id)+'</div></article>').join('')+'</div>' : empty('Todavía no hay direcciones','Agrega al menos una dirección para poder confirmar compras.');
  return heading('Direcciones de entrega','Administra las direcciones privadas de '+esc(ownBusiness(selectedBusiness)?.name || 'tu negocio')+'. Al comprar, eliges una y se guarda como copia en el historial del pedido.')+form+'<h2 class="section-heading">Direcciones guardadas</h2>'+cards;
 }
 function renderPublish() {
  const owned = editableBusinesses();
  if (!owned.length) return heading('Mis publicaciones','Administra los datos públicos y los productos de tus negocios.')+empty('Necesitas un negocio con permiso de administración','Puedes dar de alta otro negocio desde tu perfil.','<a class="button" href="/#mis-negocios">Abrir Mis negocios</a>');
  const listing = editListing && (data.my_listings || []).find(p => p.id === editListing);
  const merchant = listing?.merchant_id || selectedBusiness;
  const ownListings = data.my_listings || [];
  const profileForm = '<section class="panel"><h2>Localidad, perfil y contacto por WhatsApp</h2><p class="muted">El botón público permite que un cliente abra WhatsApp y te contacte. No incluye una bandeja de mensajes ni respuestas automáticas dentro de Mercado Abierto.</p><form id="profile-form" class="form-grid"><label class="field full">Negocio<select name="merchant_id" required>'+businessOptions(selectedBusiness,true)+'</select></label><label class="field">Actividad<select name="kind">'+options(Object.entries(kinds),'merchant')+'</select></label><label class="field">Alcaldía<select name="alcaldia" required>'+localityOptions('','Selecciona una alcaldía')+'</select></label>'+field('colonia','Colonia','','required minlength="2" maxlength="100"')+'<label class="field full">Descripción pública<textarea name="description" maxlength="1000"></textarea></label><label class="field full" for="market-whatsapp-phone">WhatsApp público (opcional)<input id="market-whatsapp-phone" name="whatsapp_phone" type="tel" inputmode="tel" autocomplete="tel" placeholder="+525512345678" maxlength="20"></label><p class="required-note full">Incluye el código de país, por ejemplo +52. El número solo se muestra en los botones de contacto si publicas este perfil. Los botones abren WhatsApp con un mensaje inicial para que el cliente lo revise y lo envíe; Mercado Abierto no recibe ni registra esos mensajes.</p><label class="check full"><input name="published" type="checkbox"> Publicar este perfil en el directorio de Ciudad de México.</label><button class="button full" type="submit">Guardar perfil</button></form><p class="required-note">Se comparte el nombre comercial, actividad, alcaldía, colonia y descripción. Las claves de pey y los correos de la cuenta permanecen privados.</p></section>';
  const imagePreview = listing?.image_url ? '<img class="product-image preview-image" src="'+esc(listing.image_url)+'" alt="Foto actual de '+esc(listing.name)+'">' : '';
  const listingForm = '<section class="panel"><h2>'+(listing?'Editar producto o servicio':'Publicar producto o servicio')+'</h2><form id="listing-form" class="form-grid"><label class="field full">Negocio que ofrece<select name="merchant_id" required'+(listing?' disabled':'')+'>'+businessOptions(merchant,true)+'</select></label>'+field('name','Nombre',listing?.name || '','required minlength="2" maxlength="120"')+field('category','Categoría',listing?.category || '','required maxlength="80"')+'<label class="field full">Descripción<textarea name="description" maxlength="1000">'+esc(listing?.description || '')+'</textarea></label><label class="field">Unidad<select name="unit"'+(listing?' disabled':'')+'>'+options(Object.entries(units),listing?.unit || 'piece')+'</select></label>'+field('price','Precio regular por unidad (MXN)',listing?decimalText(listing.seller_price_minor,2):'','required inputmode="decimal" placeholder="0.00"')+field('discount','Descuento por mayoreo (%)',listing?discountPercent(listing.wholesale_discount_bps):'0','inputmode="decimal" min="0" max="99" step="0.01"')+field('stock','Cantidad disponible',listing?decimalText(listing.stock_milli,3):'','required inputmode="decimal" placeholder="0"')+'<label class="field full">Foto del producto (JPEG, PNG o WebP · máximo 1.5 MB)<input name="image" type="file" accept="image/jpeg,image/png,image/webp"></label>'+imagePreview+'<p class="small muted full">El precio regular se tacha en la ficha y el precio de mayoreo aparece resaltado. Al importe de venta se suma el 5% de producto y, cuando aplique, el 5% del flete.</p><p id="listing-fee-preview" class="seller-fee-preview full">Desglose del vendedor: se calcula al escribir el precio.</p><label class="check full"><input name="published" type="checkbox"'+(listing?.published!==false?' checked':'')+'> Publicar esta oferta para todos los clientes.</label><button class="button full" type="submit">'+(listing?'Guardar cambios':'Publicar producto o servicio')+'</button>'+(listing?button('Cancelar edición','cancel-edit'):'')+'</form><p class="required-note">El desglose de los recargos solo se muestra al vendedor. El pago CoDi se acredita a la cuenta receptora del negocio; esta versión aún no separa automáticamente esos recargos para liquidarlos a la plataforma.</p></section>';
  return heading('Mis publicaciones','Completa tu localidad, publica tu negocio y ofrece tus productos.')+'<section class="panel"><h2>Cuenta receptora de pey</h2><p>Registra la CLABE de este negocio, consulta su estado y elige una cuenta activa como receptora de CoDi. Solo una cuenta ACTIVE puede recibir pagos CoDi.</p><p class="required-note">La CLABE y la llave de pey se capturan de forma privada en Mis negocios.</p><a class="button" href="/#mis-negocios">Administrar cuentas bancarias y conexión pey</a></section><div class="form-layout">'+profileForm+listingForm+'</div><h2 class="section-heading">Publicaciones de mis negocios</h2><div class="cards">'+(ownListings.length ? ownListings.map(p => '<article class="card"><span class="badge '+(publicationStatus(p)==='Publicada'?'good':'closed')+'">'+esc(publicationStatus(p))+'</span>'+productImage(p)+'<h3>'+esc(p.name)+'</h3><p class="muted">'+esc(p.merchant_name)+'</p>'+offeredPrice(p)+'<p class="seller-fee-preview">Precio base vendedor: '+money(p.discounted_seller_price_minor || p.seller_price_minor)+' · Recargo de producto 5%: '+money(p.platform_fee_minor)+'</p><p>Disponible: '+quantityText(p.stock_milli)+'</p><div class="actions">'+button('Editar','edit-listing',p.id)+(p.qr_sha256?button('Ver QR','product-qr',p.id):'')+'</div></article>').join('') : empty('Aún no has publicado productos','Completa el formulario para agregar tu primera oferta.'))+'</div>';
 }
 function fillProfile(id) {
  const form = $('profile-form'); if (!form) return;
  const business = ownBusiness(id), profile = business?.profile;
  form.elements.merchant_id.value = id || '';
  form.elements.kind.value = profile?.kind || 'merchant'; form.elements.alcaldia.value = profile?.alcaldia || '';
  form.elements.colonia.value = profile?.colonia || ''; form.elements.description.value = profile?.description || '';
  form.elements.whatsapp_phone.value = profile?.whatsapp_phone || ''; form.elements.published.checked = profile?.published === true;
 }
 function renderDirectory() { return heading('Negocios y fleteros','Encuentra comerciantes y transportistas por alcaldía y colonia. Cada perfil es publicado por el negocio responsable.')+'<div class="toolbar"><label class="field">Alcaldía<select id="directory-alcaldia">'+localityOptions(directoryAlcaldia)+'</select></label><label class="field">Actividad<select id="directory-kind">'+options([['merchant','Comerciantes'],['freighter','Fleteros']],directoryKind,'Todas las actividades')+'</select></label></div><div id="directory-list"></div>'; }
 function renderDirectoryResults() {
  const profiles = (data.profiles || []).filter(p => p.published && (!directoryAlcaldia || p.alcaldia === directoryAlcaldia) && (!directoryKind || p.kind === directoryKind || p.kind === 'both'));
  const groups = new Map(); for (const profile of profiles) { if (!groups.has(profile.alcaldia)) groups.set(profile.alcaldia,[]); groups.get(profile.alcaldia).push(profile); }
  $('directory-list').innerHTML = profiles.length ? [...groups].map(([code,rows]) => '<section class="locality-group"><h2>'+esc(locality(code))+'</h2><div class="cards">'+rows.map(p => {
   const products = (data.listings || []).filter(item => item.merchant_id === p.merchant_id && item.published);
   return '<article class="card" data-profile-id="'+esc(p.merchant_id)+'"><span class="badge">'+esc(kinds[p.kind])+'</span><h3>'+esc(p.name)+'</h3><p class="location">'+esc(locationText(p))+'</p><p>'+esc(p.description)+'</p><div class="actions">'+whatsappLink(canManage(p.merchant_id)?null:p.whatsapp_phone,p.name,'tu perfil en Mercado Abierto','Contactar vendedor')+(canManage(p.merchant_id)?button('Editar perfil','edit-profile',p.merchant_id):'')+'</div>'+(products.length?'<h4>Productos publicados</h4><div class="profile-products">'+products.map(item=>'<article>'+productImage(item)+'<strong>'+esc(item.name)+'</strong>'+offeredPrice(item)+'<div class="actions">'+button('Agregar al carrito','cart-add',item.id)+button('Ver QR','product-qr',item.id)+'</div></article>').join('')+'</div>':'<p class="small muted">Aún no hay productos publicados.</p>')+'</article>';
  }).join('')+'</div></section>').join('') : empty('No hay perfiles con estos filtros','Los comerciantes y fleteros aparecerán agrupados por su alcaldía cuando publiquen su perfil.',button('Completar mi perfil','view-publicar'));
 }
 function paymentInfo(order) { const paid = order.payment?.status === 'PEY_CONFIRMED'; return '<div class="payment-evidence"><span class="badge '+(paid?'good':'pending')+'">'+(paid?'Pago confirmado por pey':'Pago sin verificar')+'</span><p class="small muted">La entrega y el pago se registran por separado. La acreditación bancaria independiente sigue sin verificarse.</p></div>'; }
 function renderOrders() {
  const quotes = data.quotes || [], orders = data.orders || [];
  return heading('Cotizaciones y pedidos','Consulta las operaciones de tus negocios. El vendedor responde las cotizaciones y confirma los pedidos; el comprador confirma la recepción.')+historyNotice()+'<h2>Cotizaciones</h2><div class="list">'+(quotes.length ? quotes.map(quoteCard).join('') : empty('Sin cotizaciones todavía','Solicita una cotización desde una oferta de la comunidad.'))+'</div><h2 class="section-heading">Pedidos</h2><div class="list">'+(orders.length ? orders.map(orderCard).join('') : empty('Sin pedidos todavía','Solicita un pedido o acepta una cotización para iniciar una compra.'))+'</div>';
 }
 function quoteCard(q) {
  const buyer = canManage(q.buyer_merchant_id), seller = canManage(q.seller_merchant_id);
  let actions = '';
  if (seller && q.status === 'REQUESTED') actions += button('Responder cotización','respond-quote',q.id,'',false);
  if (buyer && q.status === 'QUOTED') actions += button('Aceptar cotización','accept-quote',q.id,'',false);
  const contact = buyer ? whatsappLink(q.seller_whatsapp_phone,q.seller_name,'la cotización de '+q.listing_name) : seller ? whatsappLink(q.buyer_whatsapp_phone,q.buyer_name,'la cotización de '+q.listing_name) : '';
  const fee=seller && Number.isInteger(q.platform_fee_minor)?'<p class="seller-fee-preview">Solo vendedor · Recargo producto 5%: '+money(q.platform_fee_minor)+' · Recargo flete 5%: '+money(q.freight_platform_fee_minor)+'</p>':'';
  return '<article class="panel record" data-quote-id="'+esc(q.id)+'"><div>'+badge(q.status)+'<h3>'+esc(q.listing_name)+'</h3><p class="muted">'+esc(q.buyer_name || 'Comprador')+' → '+esc(q.seller_name || 'Vendedor')+'</p><p>'+quantityText(q.quantity_milli)+' '+esc(units[q.unit] || q.unit)+(q.total_minor==null?'':' · <strong>'+money(q.total_minor)+'</strong>')+'</p>'+fee+'<p>'+esc(q.message || '')+'</p>'+(q.seller_message?'<p>Respuesta: '+esc(q.seller_message)+'</p>':'')+(q.order_id?'<p class="small muted">Pedido creado: '+esc(q.order_id)+'</p>':'')+'</div><div class="actions">'+actions+contact+'</div></article>';
 }
 function orderCard(o) {
  const seller = canManage(o.seller_merchant_id), buyer = canManage(o.buyer_merchant_id), closed = ['CANCELLED','REJECTED'].includes(o.status);
  let actions = '';
  const transition = (label,action,primary = false) => button(label,'order-transition',o.id,'data-transition="'+action+'"',!primary);
  if (seller && o.status === 'REQUESTED') actions += transition('Aceptar pedido','accept',true)+transition('Rechazar','reject');
  if (seller && o.status === 'ACCEPTED') actions += transition('Marcar preparado','prepare',true);
  if (seller && o.status === 'PREPARED') actions += transition('Generar QR de tránsito','ship',true);
  if (buyer && o.status === 'SHIPPED' && o.progress?.qr?.receipt) actions += button('Escanear recepción','stage-qr',o.id,'data-kind="receipt"',false);
  if (buyer && o.status === 'REQUESTED') actions += transition('Cancelar solicitud','cancel');
  if (seller && ['ACCEPTED','PREPARED'].includes(o.status) && !o.freight_id) actions += button('Solicitar flete','assign-freight',o.id);
  if (canCharge(o.seller_merchant_id) && !closed && o.status !== 'REQUESTED' && o.payment?.status !== 'PEY_CONFIRMED') actions += '<a class="button secondary" href="/caja?market_order='+encodeURIComponent(o.id)+'#cobro-codi">Cobrar con CoDi</a>';
  const contact = buyer ? whatsappLink(o.seller_whatsapp_phone,o.seller_name,'el pedido de '+o.listing_name) : seller ? whatsappLink(o.buyer_whatsapp_phone,o.buyer_name,'el pedido de '+o.listing_name) : '';
  const fees=seller && Number.isInteger(o.platform_fee_minor)?'<p class="seller-fee-preview">Solo vendedor · Precio base: '+money(o.seller_unit_price_minor)+' · Recargo producto 5%: '+money(o.platform_fee_minor)+' · Base flete: '+money(o.seller_delivery_fee_minor)+' · Recargo flete 5%: '+money(o.freight_platform_fee_minor)+'</p>':'';
  const itemList=(o.items || []).length?'<ul class="order-items">'+o.items.map(i=>'<li>'+esc(i.listing_name)+' · '+quantityText(i.quantity_milli)+' '+esc(units[i.unit] || i.unit)+' · '+money(i.total_minor)+'</li>').join('')+'</ul>':'';
  const address=o.delivery_address?'<div class="delivery-address"><strong>Entrega:</strong> '+esc(o.delivery_address.recipient)+' · '+esc(o.delivery_address.street)+' '+esc(o.delivery_address.exterior_number)+(o.delivery_address.interior_number?' int. '+esc(o.delivery_address.interior_number):'')+', '+esc(o.delivery_address.colonia)+', '+esc(locality(o.delivery_address.alcaldia))+' CP '+esc(o.delivery_address.postal_code)+' · '+esc(o.delivery_address.phone)+'</div>':'';
  const qrs=o.progress?.qr || {};
  const workflow='<div class="order-workflow"><p><strong>Etapa:</strong> '+esc(o.progress?.stage || o.status)+' · <strong>Acreditación bancaria:</strong> '+(o.progress?.bank_credit_status==='CONFIRMED'?'confirmada':'pendiente de integración')+'</p>'+['payment','bank_credit','transit','receipt'].filter(k=>qrs[k]).map(k=>'<div class="stage-qr"><span>'+esc(k==='payment'&&o.unified_qr?'QR unificado del pedido':{payment:'QR de seguimiento del pedido',bank_credit:'QR de consulta bancaria',transit:'QR de tránsito',receipt:'QR de recepción'}[k])+'</span><img src="'+esc(qrs[k].image_url)+'" alt="QR '+esc(k)+'"><code>'+esc(qrs[k].sha256)+'</code>'+button('Abrir etapa','stage-qr',o.id,'data-kind="'+k+'"')+'</div>').join('')+'<ol class="order-history">'+(o.progress?.history || []).map(e=>'<li>'+esc(e.stage)+' · '+esc(new Date(e.created_at*1000).toLocaleString('es-MX'))+'</li>').join('')+'</ol></div>';
  return '<article class="panel record" data-order-id="'+esc(o.id)+'"><div>'+badge(o.status)+'<h3>'+esc(o.listing_name)+'</h3><p class="muted">'+esc(o.buyer_name || 'Comprador')+' → '+esc(o.seller_name || 'Vendedor')+'</p><p>'+quantityText(o.quantity_milli)+' '+esc(units[o.unit] || o.unit)+' · <strong>'+money(o.total_minor)+'</strong></p><p class="small">Folio: '+esc(o.checkout_order_id || 'market-'+o.id)+'</p>'+itemList+address+fees+(o.notes?'<p>'+esc(o.notes)+'</p>':'')+paymentInfo(o)+workflow+'</div><div class="actions">'+actions+contact+'</div></article>';
 }
 function renderFreights() {
  return heading('Fletes','Los negocios asignan un transportista de Ciudad de México a un pedido. El fletero acepta la asignación y declara la entrega.')+historyNotice()+'<p class="notice">Las confirmaciones de logística las realiza cada participante desde su cuenta. Para comprobar un pago consulta su comprobante en Caja.</p><div class="list">'+((data.freights || []).length ? data.freights.map(f => { const contact = canManage(f.carrier_merchant_id) ? whatsappLink(f.seller_whatsapp_phone,f.seller_name,'el flete del pedido '+f.order_id) : whatsappLink(f.carrier_whatsapp_phone,f.carrier_name,'la asignación de flete del pedido '+f.order_id); return '<article class="panel record" data-freight-id="'+esc(f.id)+'"><div>'+badge(f.status)+'<h3>'+esc(f.carrier_name || 'Transportista')+'</h3><p>Pedido: '+esc(f.order_id)+'</p><p class="price">'+money(f.fee_minor)+'</p><p>'+esc(f.notes || '')+'</p></div><div class="actions">'+(canManage(f.carrier_merchant_id) && f.status === 'PROPOSED'?button('Aceptar flete','freight-transition',f.id,'data-transition="accept"',false):'')+(canManage(f.carrier_merchant_id) && f.status === 'ACCEPTED'?button('Declarar entrega realizada','freight-transition',f.id,'data-transition="deliver"',false):'')+contact+'</div></article>';}).join('') : empty('No hay fletes asignados','Desde un pedido puedes elegir un fletero publicado en el directorio.',button('Ver pedidos','view-pedidos')))+'</div>';
 }
 function openDialog(title,html) { if (busy) return; lastDialogTrigger = document.activeElement; $('market-dialog-title').textContent = title; $('market-dialog-content').innerHTML = html; $('market-dialog-status').textContent = ''; $('market-dialog').showModal(); }
 function closeDialog() { if ($('market-dialog').open) $('market-dialog').close(); $('market-dialog-content').replaceChildren(); $('market-dialog-status').textContent = ''; lastDialogTrigger?.isConnected && lastDialogTrigger.focus(); }
 function productQrDialog(p) {
  if (!p || !p.qr_sha256 || !p.qr_url) throw Error('Esta oferta no tiene un QR vigente.');
  const discounted = Number(p.wholesale_discount_bps || 0) > 0;
  openDialog('Ficha de compra · '+p.name,'<div class="product-sheet">'+productImage(p)+'<div><p class="muted">'+esc(p.merchant_name)+' · '+esc(locationText(p))+'</p>'+(discounted?'<p class="regular-price"><s>'+money(p.regular_price_minor)+'</s> Precio regular</p><p class="wholesale-price">Mayoreo · '+discountPercent(p.wholesale_discount_bps)+'%<br><strong>'+money(p.price_minor)+' / '+esc(units[p.unit] || p.unit)+'</strong></p>':'<p class="price">'+money(p.price_minor)+' / '+esc(units[p.unit] || p.unit)+'</p>')+'<p>'+esc(p.description || '')+'</p><img class="purchase-qr" src="'+esc(p.qr_url)+'" alt="QR válido de compra para '+esc(p.name)+'"><p class="small">SHA-256 del QR</p><code class="qr-sha">'+esc(p.qr_sha256)+'</code><p class="small muted">El QR identifica y valida esta oferta en Mercado Abierto; no es el QR bancario CoDi. El QR CoDi se crea al cobrar el pedido.</p><div class="actions">'+contactSellerButton(p)+button('Agregar al carrito','cart-add',p.id,'',false)+button('Solicitar cotización','quote',p.id)+'</div></div></div>');
 }
 function addCartDialog(id) {
  const p=(data.listings || []).find(item=>item.id===id) || (data.my_listings || []).find(item=>item.id===id);
  if(!p)throw Error('Actualiza las ofertas para agregar este producto al carrito.');
  if(!editableBusinesses().length){announce('Necesitas administrar un negocio para crear un carrito. Abre Mis negocios.',true);return}
  openDialog('Agregar al carrito','<p><strong>'+esc(p.name)+'</strong> · '+money(p.price_minor)+' / '+esc(units[p.unit] || p.unit)+'</p><form id="cart-add-form" class="form-grid"><input type="hidden" name="listing_id" value="'+esc(p.id)+'"><label class="field full">Cuenta compradora<select name="buyer_merchant_id" required>'+businessOptions(selectedBusiness,true)+'</select></label>'+field('quantity','Cantidad ('+esc(units[p.unit] || p.unit)+')','1','required inputmode="decimal"')+'<button class="button full" type="submit">Agregar al carrito</button></form>');
 }
 function orderStageDialog(order, kind, scanResult=null) {
  const qr=order.progress?.qr?.[kind];
  const stageNames={payment:order.unified_qr?'QR unificado del pedido':'Seguimiento del pedido',bank_credit:'Acreditación bancaria',transit:'Salida a tránsito',receipt:'Recepción del producto'};
  const scanButton=['transit','receipt'].includes(kind)?button('Escanear QR con cámara','scan-market-qr','','',false):'';
  const components=order.unified_qr&&kind==='payment'?'<section class="unified-qr-info"><strong>'+esc(String(order.unified_qr.item_count))+' productos consolidados</strong><ul class="order-items">'+(order.items||[]).map(item=>'<li>'+esc(item.listing_name)+' · '+quantityText(item.quantity_milli)+' '+esc(units[item.unit]||item.unit)+(item.product_qr_sha256?'<br><code>'+esc(item.product_qr_sha256)+'</code>':'')+'</li>').join('')+'</ul></section>':'';
  const paymentNote=order.unified_qr&&kind==='payment'?'Este QR reúne las referencias de los productos y abre el pedido consolidado; no es un QR bancario. Después de que el vendedor acepte el pedido, una persona autorizada generará en Caja un solo QR CoDi por el total.':'Un QR solo consulta o identifica esta etapa; no acredita por sí mismo el depósito.';
  const cashierAction=kind==='payment'&&canCharge(order.seller_merchant_id)&&['ACCEPTED','PREPARED'].includes(order.status)&&order.payment?.status!=='PEY_CONFIRMED'?'<a class="button secondary" href="/caja?market_order='+encodeURIComponent(order.id)+'#cobro-codi">Abrir Caja para crear el QR CoDi</a>':'';
  openDialog(stageNames[kind] || 'Etapa del pedido','<p><strong>'+esc(order.listing_name)+'</strong> · '+money(order.total_minor)+'</p><p>'+esc(order.progress?.stage || order.status)+'</p><p class="notice">'+paymentNote+' Estado de acreditación bancaria: '+(order.progress?.bank_credit_status==='CONFIRMED'?'confirmada por integración bancaria':'pendiente de una integración bancaria verificable')+'.</p>'+(qr?'<img class="purchase-qr" src="'+esc(qr.image_url)+'" alt="'+esc(stageNames[kind] || kind)+'"><p class="small">SHA-256</p><code class="qr-sha">'+esc(qr.sha256)+'</code>':'<p>El QR de esta etapa todavía no está disponible.</p>')+components+'<p id="stage-scan-result" class="small" role="status">'+esc(scanResult || '')+'</p><div class="actions">'+cashierAction+scanButton+button('Ver historial del pedido','view-pedidos')+'</div>');
 }
 async function handleDeepLink() {
  const params=new URLSearchParams(location.search);
  const productIds=params.getAll('producto'), hashes=params.getAll('sha256'), orderIds=params.getAll('pedido'), stages=params.getAll('etapa');
  if(!productIds.length && !orderIds.length){deepLinkHandled=true;return}
  deepLinkHandled=true;
  if(productIds.length===1 && hashes.length===1 && orderIds.length===0 && /^[0-9a-f]{32}$/.test(productIds[0]) && /^[0-9a-f]{64}$/.test(hashes[0])){
   const product=await api('/v1/market/listings/'+productIds[0]+'?sha256='+hashes[0]);
   if(!(data.listings || []).some(p=>p.id===product.id))data.listings.unshift(product);
   productQrDialog(product);
   history.replaceState(null,'','#'+view);
   return;
  }
  if(orderIds.length===1 && stages.length===1 && hashes.length===1 && /^[0-9a-f]{32}$/.test(orderIds[0]) && /^[0-9a-f]{64}$/.test(hashes[0])){
   const kind=stages[0];
   if(!['payment','bank_credit','transit','receipt'].includes(kind))throw Error('La etapa del QR no es válida.');
   const response=await api('/v1/market/orders/'+orderIds[0]);
   const qr=response.order?.progress?.qr?.[kind];
   if(!qr || qr.sha256!==hashes[0])throw Error('El QR no coincide con un pedido vigente.');
   let message='QR leído. Consultando el estado del pedido.';
   try { const scan=await api('/v1/market/order-qr/scan','POST',{order_id:orderIds[0],kind:kind.toUpperCase(),sha256:hashes[0]}); message=scan.stage_advanced?'Etapa actualizada desde el escaneo.':'QR validado; se muestra el estado guardado.'; await refresh({silent:true}); }
   catch(error){message=detail(error)}
   const refreshed=await api('/v1/market/orders/'+orderIds[0]);
   orderStageDialog(refreshed.order,kind,message);
   history.replaceState(null,'','#pedidos');
   return;
  }
  throw Error('El enlace QR tiene parámetros inválidos.');
 }
 async function scanMarketQR() {
  if(!navigator.mediaDevices?.getUserMedia || !window.jsQR){announce('La cámara QR no está disponible en este navegador.',true);return}
  openDialog('Escanear QR de Mercado Abierto','<p>Apunta la cámara al QR de oferta, pago o entrega. La imagen se procesa en este dispositivo.</p><video id="market-qr-video" class="scanner-video" autoplay muted playsinline></video><button type="button" class="button secondary" data-action="stop-market-qr">Detener cámara</button><p id="market-qr-status" role="status">Solicitando permiso de cámara…</p>');
  const video=$('market-qr-video'), status=$('market-qr-status');
  try {
   const stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'}},audio:false});
   video.srcObject=stream; await video.play();
   const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d',{willReadFrequently:true});
   const scan=()=>{ if(!video.isConnected||!stream.active)return; if(video.readyState>=2){canvas.width=video.videoWidth;canvas.height=video.videoHeight;ctx.drawImage(video,0,0,canvas.width,canvas.height);const found=window.jsQR(ctx.getImageData(0,0,canvas.width,canvas.height).data,canvas.width,canvas.height);if(found?.data){stream.getTracks().forEach(t=>t.stop());video.srcObject=null;void handleScannedQr(found.data);return}} requestAnimationFrame(scan); };
   $('market-dialog').addEventListener('close',()=>stream.getTracks().forEach(t=>t.stop()),{once:true});
   requestAnimationFrame(scan); status.textContent='Cámara activa. Mantén el QR dentro del recuadro.';
  }catch(error){status.textContent='No se pudo abrir la cámara: '+detail(error)}
 }
 async function handleScannedQr(raw) {
  try {const url=new URL(raw,location.origin);if(url.origin!==location.origin||url.pathname!=='/mercado-abierto')throw Error('El QR no pertenece a Mercado Abierto.');history.replaceState(null,'',url.pathname+url.search);await handleDeepLink();}
  catch(error){announce(detail(error),true)}
 }
 function requestDialog(id,mode) {
  const listing = (data.listings || []).find(p => p.id === id); if (!listing) throw Error('Esta publicación ya no está disponible. Actualiza el catálogo.');
  if (!editableBusinesses().length) { announce('Necesitas administrar un negocio para enviar solicitudes. Abre Mis negocios.',true); return; }
  openDialog(mode === 'quote'?'Solicitar cotización':'Solicitar pedido','<p><strong>'+esc(listing.name)+'</strong> · '+money(listing.price_minor)+' / '+esc(units[listing.unit])+'</p><p class="location">'+esc(locationText(listing))+'</p><form id="request-form" class="form-grid"><input type="hidden" name="listing_id" value="'+esc(id)+'"><input type="hidden" name="mode" value="'+mode+'"><label class="field full">Negocio comprador<select name="buyer_merchant_id" required>'+businessOptions('',true)+'</select></label>'+field('quantity','Cantidad ('+esc(units[listing.unit])+')','1','required inputmode="decimal"')+'<label class="field full">Indicaciones<textarea name="message" maxlength="1000"></textarea></label><p class="small muted full">Tu negocio debe tener alcaldía y colonia guardadas. El vendedor revisará la solicitud; enviarla no confirma ningún pago.</p><button class="button full" type="submit">Enviar solicitud</button></form>');
 }
 function quoteResponseDialog(id) { const q = data.quotes.find(q => q.id === id); if (!q) return; openDialog('Responder cotización','<p>'+esc(q.listing_name)+' · '+quantityText(q.quantity_milli)+' '+esc(units[q.unit])+'</p><form id="quote-response-form" class="form-grid"><input type="hidden" name="quote_id" value="'+esc(id)+'">'+field('price','Precio unitario (MXN)','','required inputmode="decimal"')+field('delivery_fee','Entrega (MXN)','0','required inputmode="decimal"')+'<label class="field full">Mensaje<textarea name="message" maxlength="1000"></textarea></label><button class="button full" type="submit">Enviar cotización</button></form>'); }
 function freightDialog(id) { const carriers = (data.profiles || []).filter(p => p.published && ['freighter','both'].includes(p.kind)); if (!carriers.length) { announce('Todavía no hay fleteros publicados. Consulta el directorio o publica tu perfil de transporte.',true); return; } openDialog('Solicitar flete','<form id="freight-form" class="form-grid"><input type="hidden" name="order_id" value="'+esc(id)+'"><label class="field full">Fletero y localidad<select name="carrier_merchant_id" required>'+options(carriers.map(p => [p.merchant_id,p.name+' · '+locality(p.alcaldia)]),'','Selecciona un fletero')+'</select></label>'+field('fee','Costo acordado (MXN)','','required inputmode="decimal"')+'<label class="field full">Indicaciones<textarea name="notes" maxlength="1000"></textarea></label><p class="small muted full">El transportista deberá aceptar desde su cuenta. Este registro no efectúa un pago.</p><button class="button full" type="submit">Guardar asignación</button></form>'); }
 async function mutate(work,success,form = null) {
  if (busy) return;
  busy = true; const controls = [...document.querySelectorAll('button,input,select,textarea')], disabled = new Map(controls.map(c => [c,c.disabled])); controls.forEach(c => c.disabled = true);
  $('market-dialog-status').textContent = '';
  try { await work(); busy = false; if (form && $('market-dialog').contains(form)) closeDialog(); const updated = await refresh({silent:true}); const message=typeof success==='function'?success():success; announce(updated?message:message+' No se pudo actualizar la lista; pulsa Actualizar para consultarla.',!updated); }
  catch (error) { const text = detail(error); if (form && $('market-dialog').contains(form)) $('market-dialog-status').textContent = text; announce(text,true); }
  finally { busy = false; controls.forEach(c => { if (c.isConnected) c.disabled = disabled.get(c); }); }
 }
 document.addEventListener('submit',event => {
  const form = event.target;
  if (!['catalog-filter','profile-form','listing-form','request-form','quote-response-form','freight-form','cart-add-form','cart-checkout','address-form'].includes(form.id)) return;
  event.preventDefault(); if (busy) return;
  if (form.id === 'catalog-filter') { clearTimeout(searchTimer); catalogSearch = $('catalog-search').value; catalogAlcaldia = $('catalog-alcaldia').value; loadCatalog(true); return; }
  const value = new FormData(form), text = name => String(value.get(name) || '').trim();
  try {
   if (form.id === 'profile-form') {
    const id = text('merchant_id'); selectedBusiness = id;
    const profile = ownBusiness(id)?.profile, payload = {kind:text('kind'),alcaldia:text('alcaldia'),colonia:text('colonia'),description:text('description'),whatsapp_phone:text('whatsapp_phone') || null,published:value.has('published')}; if (Number.isInteger(profile?.revision)) payload.revision = profile.revision;
    return mutate(() => api('/v1/market/profiles/'+encodeURIComponent(id),'PUT',payload),'Perfil guardado en el servidor.',form);
   }
   if (form.id === 'listing-form') {
    const prior = editListing && (data.my_listings || []).find(p => p.id === editListing);
    const discountBps=amount(text('discount') || '0',2,true);
    if(discountBps>9900)throw Error('El descuento por mayoreo debe ser de 0% a 99%.');
    const payload = {name:text('name'),description:text('description'),category:text('category'),unit:prior?.unit || text('unit'),price_minor:amount(text('price'),2),wholesale_discount_bps:discountBps,stock_milli:amount(text('stock'),3,true),published:value.has('published')};
    if (['piece','service'].includes(payload.unit) && payload.stock_milli % 1000) throw Error('Las existencias de piezas y servicios deben ser cantidades enteras.');
    if (!prior) payload.merchant_id = text('merchant_id'); else if (Number.isInteger(prior.revision)) payload.revision = prior.revision;
    const path = '/v1/market/listings'+(prior?'/'+encodeURIComponent(prior.id):'');
    const image=form.elements.image.files?.[0]; let imageWarning='';
    if(image && (image.size>1500000 || !['image/jpeg','image/png','image/webp'].includes(image.type)))throw Error('Elige una foto JPEG, PNG o WebP de hasta 1.5 MB.');
    return mutate(async() => { const saved=await api(path,prior?'PATCH':'POST',payload); if(image){try{await api('/v1/market/listings/'+encodeURIComponent(saved.id || prior?.id)+'/image','PUT',await readImageFile(image));}catch(error){imageWarning=' La publicación sí se guardó, pero la foto no: '+detail(error)+'. Puedes volver a intentarlo al editar.'}} editListing = null; },()=>imageWarning?'Publicación guardada.'+imageWarning:'Publicación guardada con su precio mayorista y desglose privado para el vendedor.',form);
   }
   if (form.id === 'request-form') {
    const listing = (data.listings || []).find(p => p.id === text('listing_id')); if (!listing) throw Error('Actualiza el catálogo antes de enviar la solicitud.');
    const payload = {listing_id:listing.id,buyer_merchant_id:text('buyer_merchant_id'),quantity_milli:quantity(text('quantity'),listing.unit)};
    const quoting = text('mode') === 'quote'; if (quoting) payload.message = text('message'); else { payload.notes = text('message'); payload.request_key = key(JSON.stringify(payload)); }
    return mutate(async() => { await api('/v1/market/'+(quoting?'quotes':'orders'),'POST',payload); view = 'pedidos'; history.replaceState(null,'','#pedidos'); },'Solicitud guardada. Puedes seguirla en Cotizaciones y pedidos.',form);
   }
   if (form.id === 'cart-add-form') {
    const listing=(data.listings || []).find(p=>p.id===text('listing_id')) || (data.my_listings || []).find(p=>p.id===text('listing_id'));
    if(!listing)throw Error('Actualiza el catálogo antes de agregar el producto.');
    const buyer=text('buyer_merchant_id'), payload={buyer_merchant_id:buyer,listing_id:listing.id,quantity_milli:quantity(text('quantity'),listing.unit)};
    return mutate(async()=>{selectedBusiness=buyer;await api('/v1/market/cart/items','POST',payload);view='carrito';history.replaceState(null,'','#carrito');},'Producto agregado al carrito de la cuenta.',form);
   }
   if (form.id === 'cart-checkout') {
    const buyer=text('buyer_merchant_id'), address=text('address_id');
    const payload={buyer_merchant_id:buyer,address_id:address,request_key:key('cart-checkout:'+buyer+':'+(cartData?.revision || 0)+':'+address)};
    let createdOrder=null;
    return mutate(async()=>{const result=await api('/v1/market/cart/checkout','POST',payload);createdOrder=result.order;selectedBusiness=buyer;view='pedidos';history.replaceState(null,'','#pedidos');},()=>{if(createdOrder)orderStageDialog(createdOrder,'payment');return 'Pedido consolidado creado. El vendedor debe aceptarlo antes de emitir un QR CoDi único en Caja.';},form);
   }
   if (form.id === 'address-form') {
    const id=text('merchant_id'), payload={merchant_id:id,label:text('label'),recipient:text('recipient'),phone:text('phone'),street:text('street'),exterior_number:text('exterior_number'),interior_number:text('interior_number'),colonia:text('colonia'),alcaldia:text('alcaldia'),postal_code:text('postal_code'),reference_notes:text('reference_notes')};
    if(!/^\d{5}$/.test(payload.postal_code))throw Error('El código postal debe tener cinco dígitos.');
    const path='/v1/market/delivery-addresses'+(editAddressId?'/'+encodeURIComponent(editAddressId):'');
    return mutate(async()=>{selectedBusiness=id;await api(path,editAddressId?'PUT':'POST',payload);editAddressId=null;},'Dirección guardada en esta cuenta.',form);
   }
   if (form.id === 'quote-response-form') return mutate(() => api('/v1/market/quotes/'+encodeURIComponent(text('quote_id'))+'/respond','POST',{unit_price_minor:amount(text('price'),2),delivery_fee_minor:amount(text('delivery_fee'),2,true),message:text('message')}),'Cotización enviada al negocio comprador.',form);
   if (form.id === 'freight-form') return mutate(async() => { await api('/v1/market/freights','POST',{order_id:text('order_id'),carrier_merchant_id:text('carrier_merchant_id'),fee_minor:amount(text('fee'),2,true),notes:text('notes')}); view = 'fletes'; history.replaceState(null,'','#fletes'); },'Flete guardado, pendiente de aceptación del transportista.',form);
  } catch (error) { if ($('market-dialog').contains(form)) $('market-dialog-status').textContent = detail(error); announce(detail(error),true); }
 });
 document.addEventListener('click',async event => {
  const nav = event.target.closest('[data-view]'); if (nav) { navigate(nav.dataset.view); return; }
  const target = event.target.closest('[data-action]'); if (!target || busy) return;
  const {action,id,transition} = target.dataset;
  try {
   if (action === 'open-whatsapp-settings') { navigate('whatsapp'); return; }
   if (action.startsWith('view-')) return navigate(action.slice(5));
   if (action === 'refresh') return refresh();
   if (action === 'catalog-more') return loadCatalog(false);
   if (action === 'quote' || action === 'order') return requestDialog(id,action);
   if (action === 'product-qr') { const product=(data.listings || []).find(p=>p.id===id) || (data.my_listings || []).find(p=>p.id===id); return productQrDialog(product); }
   if (action === 'cart-add') return addCartDialog(id);
   if (action === 'cart-remove') return mutate(()=>api('/v1/market/cart/items/'+encodeURIComponent(id)+'?buyer_merchant_id='+encodeURIComponent(selectedBusiness),'DELETE'),'Producto retirado del carrito.');
   if (action === 'edit-address') { editAddressId=id; navigate('direcciones'); return; }
   if (action === 'cancel-address-edit') { editAddressId=null; render(); return; }
   if (action === 'delete-address') { const address=deliveryAddresses.find(a=>a.id===id); if(!address)return; if(!window.confirm('¿Eliminar la dirección “'+address.label+'” de esta cuenta? Los pedidos anteriores conservarán su copia.'))return; return mutate(()=>api('/v1/market/delivery-addresses/'+encodeURIComponent(id)+'?merchant_id='+encodeURIComponent(selectedBusiness),'DELETE'),'Dirección eliminada. Los pedidos anteriores se conservaron.'); }
   if (action === 'stage-qr') { const order=await api('/v1/market/orders/'+encodeURIComponent(id)); return orderStageDialog(order.order,target.dataset.kind); }
   if (action === 'scan-market-qr') return scanMarketQR();
   if (action === 'stop-market-qr') { document.querySelector('#market-qr-video')?.srcObject?.getTracks().forEach(t=>t.stop()); return closeDialog(); }
   if (action === 'respond-quote') return quoteResponseDialog(id);
   if (action === 'assign-freight') return freightDialog(id);
   if (action === 'cancel-edit') { editListing = null; return render(); }
   if (action === 'edit-listing') { const listing = (data.my_listings || []).find(p => p.id === id); if (!listing || !canManage(listing.merchant_id)) throw Error('No tienes permiso para editar esta publicación.'); editListing = id; navigate('publicar'); $('listing-form')?.querySelector('[name=name]')?.focus(); return; }
   if (action === 'edit-profile') { selectedBusiness = id; navigate('publicar'); fillProfile(id); $('profile-form')?.querySelector('[name=alcaldia]')?.focus(); return; }
   if (action === 'accept-quote') return mutate(() => api('/v1/market/quotes/'+encodeURIComponent(id)+'/accept','POST',{request_key:key('quote:'+id)}),'Cotización aceptada. El vendedor debe confirmar el pedido.');
   if (action === 'order-transition') return mutate(() => api('/v1/market/orders/'+encodeURIComponent(id)+'/transition','POST',{action:transition}),'Estado del pedido actualizado.');
   if (action === 'freight-transition') return mutate(() => api('/v1/market/freights/'+encodeURIComponent(id)+'/transition','POST',{action:transition}),'Estado del flete actualizado.');
  } catch (error) { announce(detail(error),true); }
 });
 document.addEventListener('input',event => { if (event.target.id === 'catalog-search') { catalogSearch = event.target.value; renderCatalogResults(); clearTimeout(searchTimer); searchTimer = setTimeout(() => loadCatalog(true),300); } if (event.target.form?.id==='listing-form' && ['price','discount'].includes(event.target.name)) updateListingFeePreview(); });
 document.addEventListener('change',async event => {
  if (event.target.id === 'catalog-alcaldia') { catalogAlcaldia = event.target.value; loadCatalog(true); }
  if (event.target.id === 'directory-alcaldia' || event.target.id === 'directory-kind') { directoryAlcaldia = $('directory-alcaldia').value; directoryKind = $('directory-kind').value; renderDirectoryResults(); }
  if (event.target.form?.id === 'profile-form' && event.target.name === 'merchant_id') { selectedBusiness = event.target.value; fillProfile(selectedBusiness); }
  if (['cart-business','address-business'].includes(event.target.id)) { selectedBusiness=event.target.value;editAddressId=null;try{await Promise.all([loadCart(selectedBusiness),loadDeliveryAddresses(selectedBusiness)]);render();}catch(error){announce(detail(error),true)} }
 });
 $('market-dialog-close').addEventListener('click',() => { if (!busy) closeDialog(); });
 $('market-dialog').addEventListener('cancel',event => { if (busy) event.preventDefault(); });
 $('market-dialog').addEventListener('close',() => { $('market-dialog-content').replaceChildren(); $('market-dialog-status').textContent = ''; });
 $('market-refresh').addEventListener('click',() => { if ($('market-dialog').open || document.activeElement?.closest('form') && view==='publicar') return announce('Termina de editar antes de actualizar para conservar tus campos.',true); refresh(); });
 window.addEventListener('hashchange',() => navigate(location.hash.slice(1),false));
 window.addEventListener('focus',() => { if (ready && !busy && !$('market-dialog').open && !document.activeElement?.closest('form') && Date.now()-lastRefresh>15000) refresh({silent:true}); });
 window.addEventListener('pagehide',() => { generation++; user = null; csrf = ''; data = null; ready = false; closeDialog(); });
 window.MercadoProduction = Object.freeze({get ready(){return ready;},refresh:() => refresh({silent:true}),get view(){return view;}});
 view = ['#perfil','#whatsapp'].includes(location.hash)?'publicar':Object.hasOwn(names,location.hash.slice(1))?location.hash.slice(1):'catalogo';
 refresh({silent:true});
})();
