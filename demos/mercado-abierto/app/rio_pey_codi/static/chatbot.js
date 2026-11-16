(() => {
 'use strict';
 const $ = id => document.getElementById(id);
 const dialog = $('status-chatbot');
 if (!dialog) return;
 let csrf = '', timer = null, busy = false, priorFocus = null, helpCatalogPromise = null;

 function addMessage(role, text) {
  const message = document.createElement('p');
  message.className = 'chatbot-message ' + (role === 'user' ? 'from-user' : 'from-assistant');
  const label = document.createElement('strong');
  label.textContent = role === 'user' ? 'Tú' : 'Asistente';
  const body = document.createElement('span');
  body.textContent = String(text || '');
  message.append(label, body);
  $('status-chatbot-messages').append(message);
  message.scrollIntoView({block:'nearest'});
 }

 function normalize(text) { return String(text||'').normalize('NFD').replace(/\p{M}/gu,'').toLowerCase(); }

 async function helpCatalog() {
  if (!helpCatalogPromise) helpCatalogPromise = Promise.all([
   fetch('/static/rio-help-catalog.json',{credentials:'same-origin',cache:'no-store'}),
   fetch('/static/rio-help-product-overlay.json',{credentials:'same-origin',cache:'no-store'})
  ]).then(async responses => {
   if (responses.some(response=>!response.ok)) throw Error('No está disponible el catálogo de ayuda.');
   const [base,overlay]=await Promise.all(responses.map(response=>response.json()));
   if (base.preguntas?.length!==180 || !Array.isArray(overlay.preguntas) || !Array.isArray(overlay.tutoriales)) throw Error('El catálogo de ayuda está incompleto.');
   return {preguntas:[...base.preguntas,...overlay.preguntas],tutoriales:[...base.tutoriales,...overlay.tutoriales]};
  }).catch(error=>{helpCatalogPromise=null;throw error;});
  return helpCatalogPromise;
 }

 function isHelpIntent(message) {
  const value=normalize(message);
  if (/\bcomo (esta|va|sigue|se encuentra)\b/.test(value)) return false;
  return /\b(como|donde|para que|que hace|boton|tutorial|ayuda|cambiar|actualizar|configurar|eliminar|retirar|restaurar|publicar|conectar|registrar|pasos)\b/i.test(value) || /\b(whatsapp|responder mensajes|bandeja de entrada|respuesta automatica|chatbot)\b/i.test(value);
 }

 function areaLink(area) {
  const routes={mis_negocios:['#mis-negocios','Abrir Mis negocios'],caja_codi:['#cobro-codi','Abrir Caja'],caja_efectivo:['#cobro-codi','Abrir Caja'],historial:['#historial','Abrir Historial'],comprobantes:['#historial','Abrir Historial'],mercado:['/mercado-abierto#catalogo','Abrir Mercado Abierto'],whatsapp:['/mercado-abierto#whatsapp','Configurar WhatsApp público'],actividad:['#menu','Abrir el menú de la cuenta'],auth:['/login','Abrir acceso a la cuenta'],general:['#menu','Abrir el menú principal'],seguridad:['#menu','Abrir el menú principal']};
  return routes[area]||['#menu','Abrir el menú principal'];
 }

 function areaForQuery(query) {
  if (/whatsapp/.test(query)) return 'whatsapp';
  if (/pey|codi|cuenta bancaria|clabe|conectar cuenta/.test(query)) return 'mis_negocios';
  if (/efectivo|caja|cobro|qr|pago|comprobante/.test(query)) return 'caja_codi';
  if (/pedido|orden|flete|fletero|producto|mercado|mayorista/.test(query)) return 'mercado';
  if (/historial|actividad|registro/.test(query)) return 'historial';
  if (/acceso|sesion|registro|correo|contrase/.test(query)) return 'auth';
  return 'general';
 }

 async function answerHelp(message) {
  if (!isHelpIntent(message)) return false;
  let catalog;
  try { catalog=await helpCatalog(); }
  catch (_) { catalog={preguntas:[],tutoriales:[]}; }
  const needle=normalize(message), words=needle.split(/\s+/).filter(word=>word.length>=3&&!['como','donde','para','que','una','uno','los','las','del','mis','quiero','puedo','hace','cual'].includes(word));
  if (!words.length) words.push('ayuda');
  const tutorialById=new Map(catalog.tutoriales.map(tutorial=>[tutorial.id,tutorial]));
  const matches=catalog.preguntas.map(question=>{
   const tutorial=tutorialById.get(question.tutorial_id);
   const haystack=normalize([question.texto,tutorial?.titulo,...(tutorial?.pasos||[]).map(step=>step.texto)].filter(Boolean).join(' '));
   const matched=words.filter(word=>haystack.includes(word)).length;
   return {question,tutorial,matched,exact:haystack.includes(needle)};
  }).filter(item=>item.matched>0).sort((a,b)=>Number(b.exact)-Number(a.exact)||b.matched-a.matched||a.question.id.localeCompare(b.question.id));
  const whatsappAutomation=/whatsapp/.test(needle)&&/responder|mensaj|automatic|chatbot|bandeja|integrar|integracion|enviar/.test(needle);
  const exactWhatsappHelp=/whatsapp/.test(needle)?catalog.preguntas.find(question=>question.id===(whatsappAutomation?'Q183':'Q182')):null;
  const best=exactWhatsappHelp?{question:exactWhatsappHelp,tutorial:tutorialById.get(exactWhatsappHelp.tutorial_id),matched:words.length,exact:true}:matches[0];
  const hasGuide=Boolean(best&&(best.exact||best.matched>=Math.min(2,words.length)));
  const area=hasGuide?(best.tutorial?.area||best.question.area):areaForQuery(needle);
  const pendingCapability=!hasGuide&&/caseta|casetas|tag iave|caseta capufe/.test(needle);
  const messageNode=document.createElement('section');messageNode.className='chatbot-message from-assistant chatbot-instructions';
  const label=document.createElement('strong');label.textContent='Asistente';
  const title=document.createElement('p');title.textContent=hasGuide?(best.tutorial?.titulo||best.question.texto):pendingCapability?'Esta función todavía no tiene una página operativa en Mercado Abierto.':'No encuentro una guía verificada para ese cambio todavía.';
  const lead=document.createElement('p');lead.textContent=hasGuide?'No ejecutaré este cambio desde el chat. Sigue estos pasos y abre la sección indicada:':pendingCapability?'No hay un enlace de cambio válido que pueda darte. La integración sigue pendiente; no compartas códigos, tokens ni datos bancarios aquí.':'No voy a inventar botones ni a modificar datos sin una acción autorizada. Abre la sección relacionada y dime el nombre exacto del botón o la pantalla para darte pasos confirmados:';
  const list=document.createElement('ol');
  const steps=hasGuide?(best.tutorial?.pasos?.map(step=>step.texto)||best.question.respuesta_directa||[]):pendingCapability?[
   /whatsapp/.test(needle)?'El envío y la conexión de WhatsApp no están disponibles desde este asistente todavía.':'Las casetas y TAG siguen pendientes de verificar y no se pueden comprar ni operar aquí.',
   'No intentes resolverlo con un QR de prueba ni envíes credenciales por chat.',
   'Cuando exista una página autorizada, el asistente mostrará el enlace directo y las instrucciones aprobadas.'
  ]:[
   'Comprueba que estás en el negocio correcto antes de cambiar información.',
   'En esa sección busca el nombre visible de la opción relacionada; revisa el resumen y el efecto antes de confirmar.',
   'Si la opción no existe o el resultado no aparece, no repitas una operación financiera: conserva el folio y consulta el Centro de ayuda.'
  ];
  for(const text of steps){const item=document.createElement('li');item.textContent=text;list.append(item);}
  const route=pendingCapability?null:areaLink(area);const page=route?document.createElement('a'):null;if(page){page.href=route[0];page.textContent=route[1];}
  const limit=document.createElement('p');limit.textContent=hasGuide?'Límite: '+best.question.limite:pendingCapability?'Estado: pendiente de implementación/verificación.':'Este enlace abre una sección existente relacionada; no significa que el cambio solicitado ya esté implementado.';
  const links=[];
  for(const item of (hasGuide?best.tutorial?.enlaces_utiles||[]:[])){
   if(!item.url)continue;
   try{const url=new URL(item.url,location.origin);if(url.protocol==='https:'&&['rio-pey-codi-gateway.vercel.app','rio-primer-cobro-frontdesk.vercel.app','docs.pey.mx','portal.pey.mx','www.banxico.org.mx','developers.facebook.com'].includes(url.hostname)){const link=document.createElement('a');link.href=url.href;link.target='_blank';link.rel='noopener noreferrer';link.textContent=item.titulo;links.push(link);}}catch{}
  }
  messageNode.append(label,title,lead,list);if(page)messageNode.append(page);
  if(links.length){const linkList=document.createElement('p');linkList.append(document.createTextNode('Enlaces oficiales: '));links.forEach((link,index)=>{if(index)linkList.append(document.createTextNode(' · '));linkList.append(link);});messageNode.append(linkList);}
  messageNode.append(limit);$('status-chatbot-messages').append(messageNode);messageNode.scrollIntoView({block:'nearest'});return true;
 }

 async function call(path, method = 'GET', body) {
  const response = await fetch(path, {
   method, credentials:'same-origin', cache:'no-store',
   headers:{Accept:'application/json', ...(body === undefined ? {} : {'Content-Type':'application/json','X-CSRF-Token':csrf})},
   ...(body === undefined ? {} : {body:JSON.stringify(body)})
  });
  let result;
  try { result = await response.json(); } catch (_) { throw Error('El servidor no devolvió una respuesta válida.'); }
  if (response.status === 401) { location.replace('/login?next=%2F'); throw Error('Tu sesión terminó. Vuelve a iniciar sesión.'); }
  if (!response.ok) throw Error(typeof result.detail === 'string' ? result.detail : 'No pude consultar el estado ('+response.status+').');
  return result;
 }

 async function ensureCsrf() {
  if (csrf) return;
  const identity = await call('/api/auth/me');
  csrf = identity.csrf_token;
 }

 function row(label, value) {
  if (!value) return;
  const p = document.createElement('p');
  const strong = document.createElement('strong');
  strong.textContent = label + ': ';
  p.append(strong, document.createTextNode(String(value)));
  $('status-chatbot-current').append(p);
 }

 function renderStatus(data) {
  const target = $('status-chatbot-current');
  target.replaceChildren();
  row('Cuenta', data.account?.email_verified ? 'correo verificado' : 'correo pendiente de verificar');
  if (!data.businesses?.length) row('Negocios', 'sin negocios asignados');
  for (const business of (data.businesses || []).slice(0, 10)) {
   row(business.name, [business.profile_status, business.pey_credential_status,
    business.pey_last_account_observation ? 'última consulta pey: ' + business.pey_last_account_observation : ''].filter(Boolean).join(' · '));
  }
  if (data.orders?.length) {
   row('Pedidos recientes', data.orders.slice(0, 5).map(order =>
    order.listing_name + ' · ' + order.status_label + ' · ' + order.payment_label +
    (order.freight_status ? ' · flete ' + order.freight_status : '')).join(' | '));
  } else row('Pedidos', 'sin pedidos registrados');
  if (data.freights?.length) row('Fletes', data.freights.slice(0, 5).map(item => item.status_label).join(', '));
  if (data.snapshot_at) {
   const date = new Date(data.snapshot_at);
   $('status-chatbot-updated').textContent = 'Consultado ' + date.toLocaleTimeString('es-MX',{hour:'2-digit',minute:'2-digit',second:'2-digit'}) + ' · se actualiza cada 10 s mientras esta ventana está abierta.';
  }
 }

 async function refreshStatus() {
  if (busy || !dialog.open || document.visibilityState !== 'visible') return;
  try { renderStatus(await call('/v1/chatbot/status')); }
  catch (error) { $('status-chatbot-feedback').textContent = error.message; }
 }

 async function open() {
  if (dialog.open) return;
  priorFocus = document.activeElement;
  dialog.showModal();
  $('status-chatbot-feedback').textContent = '';
  $('status-chatbot-messages').replaceChildren();
  addMessage('assistant','Hola. Consulto en vivo el estado de tu cuenta, pedidos, pagos reportados por pey y fletes. ¿Qué quieres revisar?');
  $('status-chatbot-input').focus();
  try {
   await ensureCsrf();
   await refreshStatus();
   timer = setInterval(refreshStatus,10000);
  } catch (error) { $('status-chatbot-feedback').textContent = error.message; }
 }

 async function send(value) {
  const message = String(value || '').trim();
  if (!message || busy) return;
  busy = true;
  $('status-chatbot-send').disabled = true;
  $('status-chatbot-feedback').textContent = 'Consultando el estado…';
  addMessage('user',message);
  try {
   if (await answerHelp(message)) { $('status-chatbot-feedback').textContent='Guía verificada del catálogo. El enlace abre la sección correspondiente.'; return; }
   await ensureCsrf();
   const result = await call('/v1/chatbot/message','POST',{message});
   renderStatus(result);
   addMessage('assistant',result.reply);
   $('status-chatbot-feedback').textContent = '';
  } catch (error) { $('status-chatbot-feedback').textContent = error.message; }
  finally { busy = false; $('status-chatbot-send').disabled = false; }
 }

 document.addEventListener('click', event => {
  const openButton = event.target.closest('[data-open-chatbot]');
  if (openButton) { event.preventDefault(); open(); return; }
  const prompt = event.target.closest('[data-chatbot-prompt]');
  if (prompt) { $('status-chatbot-input').value = prompt.dataset.chatbotPrompt; send(prompt.dataset.chatbotPrompt); }
 });
 $('status-chatbot-close').addEventListener('click', () => dialog.close());
 $('status-chatbot-help').addEventListener('click', () => {
  dialog.close();
  document.getElementById('rio-help-open')?.click();
 });
 $('status-chatbot-form').addEventListener('submit', event => {
  event.preventDefault();
  const input = $('status-chatbot-input');
  const value = input.value; input.value = '';
  send(value);
 });
 dialog.addEventListener('close', () => {
  clearInterval(timer); timer = null; csrf = '';
  priorFocus?.isConnected && priorFocus.focus();
 });
 window.addEventListener('pagehide', () => { clearInterval(timer); timer = null; csrf = ''; });
})();
