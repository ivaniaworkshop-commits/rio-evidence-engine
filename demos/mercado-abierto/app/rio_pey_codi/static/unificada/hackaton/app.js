
(()=>{'use strict';
const DRAFT_PREFIX='rio_hackaton_pending_r017_';const STORAGE_PREFIX='rio_hackaton_r010_gateway_user_';let storageKey=null;const STORAGE_LEGACY='rio_hackaton_unificada_r001_v1';
const MENU=[['centro','🧩','Guía de áreas'],['panel','▦','Resumen'],['mercado','🛍','Mercado'],['solicitudes','📨','RFQ'],['ofertas','💬','Ofertas'],['pedidos','📦','Pedidos'],['fletes','🚚','Fletes'],['caja','🧾','Caja'],['inventario','🏷','Inventario'],['negocios','🏪','Negocios'],['tickets','🎫','Tickets'],['historial','🕒','Historial'],['admin','🛡','Centro de control'],['cuenta','⚙','Mi cuenta']];
const CAT=['Abarrotes','Frutas y verduras','Juguetes','Ferretería','Tecnología','Otros'];
const money=n=>new Intl.NumberFormat('es-MX',{style:'currency',currency:'MXN'}).format(Number(n)||0);
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const now=()=>new Date().toISOString();const uid=p=>p+'-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,7);
const date=x=>x?new Date(x).toLocaleString('es-MX',{dateStyle:'short',timeStyle:'short'}):'—';
const seed=()=>({schema:'RIO_MERCADO_DEMO_R001',version:1,createdAt:now(),businesses:[{id:'NEG-001',name:'Abarrotes La Esquina',type:'minorista',zone:'Iztapalapa, CDMX',contact:'',active:true},{id:'NEG-002',name:'Central de Frutas del Sur',type:'mayorista',zone:'Coyoacán, CDMX',contact:'',active:true},{id:'NEG-003',name:'Fletes del Barrio',type:'fletero',zone:'Ciudad de México',contact:'',active:true}],products:[{id:'SKU-001',name:'Jitomate',category:'Frutas y verduras',unit:'kg',price:40,stock:60,owner:'NEG-002',active:true},{id:'SKU-002',name:'Arroz',category:'Abarrotes',unit:'pieza',price:27,stock:45,owner:'NEG-001',active:true},{id:'SKU-003',name:'Agua embotellada',category:'Abarrotes',unit:'pieza',price:15,stock:80,owner:'NEG-001',active:true},{id:'SKU-004',name:'Cable de red',category:'Tecnología',unit:'metro',price:12,stock:100,owner:'NEG-002',active:true}],rfqs:[],offers:[],orders:[],freights:[],sales:[],events:[]});
const validate=s=>s&&s.schema==='RIO_MERCADO_DEMO_R001'&&['businesses','products','rfqs','offers','orders','freights','sales','events'].every(k=>Array.isArray(s[k]));
let state=seed(),appReady=false;
let remoteRevision=0,remoteSaveQueue=Promise.resolve(),remoteBlocked=false,remoteStatus='SIN_VERIFICAR',sessionEpoch=0,pendingDraft=null,draftSequence=0;
async function loadCommercialStateForUser(id){
 const epoch=++sessionEpoch;
 storageKey=STORAGE_PREFIX+String(id);
 pendingDraft=null;
 try{const d=JSON.parse(localStorage.getItem(DRAFT_PREFIX+String(id))||'null');
  if(d&&d.userId===String(id)&&validate(d.state)&&Number.isSafeInteger(d.baseRevision)&&d.baseRevision>=0)pendingDraft=d;
 }catch(e){}
 let cached=null;
 try{const raw=localStorage.getItem(storageKey);if(raw){const data=JSON.parse(raw);if(validate(data))cached=data}}catch(e){}
 const remote=await adminAPI('/hackaton/commercial-state');
 if(epoch!==sessionEpoch)throw Error('La sesión cambió durante la carga comercial');
 if(!remote||!Number.isSafeInteger(remote.revision)||remote.revision<0)throw Error('Revisión comercial inválida');
 remoteRevision=remote.revision;remoteBlocked=false;remoteSaveQueue=Promise.resolve();
 if(remote.state!==null){
  if(!validate(remote.state))throw Error('El servidor devolvió datos comerciales inválidos');
  state=remote.state;remoteStatus='SINCRONIZADO';
  try{localStorage.setItem(storageKey,JSON.stringify(state))}catch(e){}
 }else if(cached&&!pendingDraft){
  state=cached;
  const saved=await adminAPI('/hackaton/commercial-state',{method:'PUT',body:JSON.stringify({revision:0,state})});
  if(epoch!==sessionEpoch)throw Error('La sesión cambió durante la migración');
  if(!Number.isSafeInteger(saved.revision)||saved.revision!==1)throw Error('La migración comercial no fue confirmada');
  remoteRevision=saved.revision;remoteStatus='MIGRADO';
 }else{state=seed();remoteStatus='SIN_MOVIMIENTOS'}
 if(pendingDraft)remoteStatus=pendingDraft.baseRevision===remoteRevision?'BORRADOR_RECUPERABLE':'BORRADOR_EN_CONFLICTO';
 marketCart={};posCart={};
}
function queueRemoteState(){
 if(!appReady||remoteBlocked)return;
 const epoch=sessionEpoch,owner=storageKey,snapshot=JSON.stringify(state);
 const draftKey=DRAFT_PREFIX+String(adminState.user?.id||''),nonce=String(++draftSequence)+':'+uid('DRAFT');
 const draft={userId:String(adminState.user?.id||''),baseRevision:remoteRevision,state:JSON.parse(snapshot),createdAt:now(),nonce};
 try{localStorage.setItem(draftKey,JSON.stringify(draft));}catch(e){
  remoteBlocked=true;remoteStatus='BORRADOR_NO_GUARDADO';
  toast('Sin espacio para conservar el borrador. Exporta el respaldo antes de salir.',true);return;
 }
 remoteStatus='PENDIENTE';
 remoteSaveQueue=remoteSaveQueue.then(async()=>{
  if(epoch!==sessionEpoch||owner!==storageKey||remoteBlocked)return;
  const saved=await adminAPI('/hackaton/commercial-state',{method:'PUT',body:JSON.stringify({revision:remoteRevision,state:JSON.parse(snapshot)})});
  if(epoch!==sessionEpoch||owner!==storageKey)return;
  if(!Number.isSafeInteger(saved.revision)||saved.revision!==remoteRevision+1)throw Error('El servidor no confirmó la revisión comercial');
  remoteRevision=saved.revision;
  try{const current=JSON.parse(localStorage.getItem(draftKey)||'null');
   if(current?.nonce===nonce)localStorage.removeItem(draftKey);
  }catch(e){}
  remoteStatus=localStorage.getItem(draftKey)?'PENDIENTE':'SINCRONIZADO';
 }).catch(e=>{
  if(epoch!==sessionEpoch)return;
  remoteBlocked=true;remoteStatus='ERROR';
  invalidateSession('La sincronización comercial falló: '+String(e.message||e)+'. Se conservó una copia local de recuperación.');
  render();
 });
}
let page='panel';let query='';let category='Todas';let marketCart={};let posCart={};let previewTicket=null;let modalReturnFocus=null;
function invalidateSession(reason='Sesión no disponible'){sessionEpoch++;remoteBlocked=true;remoteStatus='BLOQUEADO';appReady=false;storageKey=null;state=seed();marketCart={};posCart={};previewTicket=null;adminState.user=null;adminState.csrf='';adminState.permissions=[];adminState.phase='offline';adminState.error=reason;const root=document.getElementById('modalRoot');if(root)root.replaceChildren();}

const find=(kind,id)=>state[kind].find(x=>x.id===id);
const bname=id=>find('businesses',id)?.name||'Negocio sin identificar';
const pname=id=>find('products',id)?.name||'Artículo retirado';
const capture=(type,detail)=>state.events.unshift({id:uid('EV'),at:now(),type,detail:String(detail).slice(0,300)});
const persist=()=>{if(!storageKey)return false;try{localStorage.setItem(storageKey,JSON.stringify(state));return true}catch(e){toast('No se pudo guardar en este navegador',true);return false}};
const commit=(type,detail)=>{capture(type,detail);persist();queueRemoteState();render();toast(detail)};
function toast(t,bad=false){const e=document.getElementById('toastRoot');e.innerHTML=`<div class="toast ${bad?'bad':''}">${esc(t)}</div>`;window.clearTimeout(toast.timeout);toast.timeout=window.setTimeout(()=>e.innerHTML='',3200)}
const btn=(text,action,id='',kind='secondary',extra='')=>`<button class="btn ${kind} ${extra}" data-action="${esc(action)}" ${id?'data-id="'+esc(id)+'"':''}>${text}</button>`;
const chip=(status)=>{const s=String(status||'');const hue=/entregado|pagado|activo|aceptado|finalizad|recibid/.test(s)?'green':/rechaz|cancel/.test(s)?'red':'amber';return `<span class="chip ${hue}">${esc(s.replaceAll('_',' '))}</span>`};
const empty=(s)=>`<div class="empty">${esc(s)}</div>`;
const opts=(items,selected='')=>items.map(([v,l])=>`<option value="${esc(v)}" ${v===selected?'selected':''}>${esc(l)}</option>`).join('');
const busOptions=(type,selected='')=>opts(state.businesses.filter(b=>b.active&&(!type||b.type===type)).map(b=>[b.id,b.name]),selected);
const productOptions=()=>opts(state.products.filter(p=>p.active).map(p=>[p.id,p.name+' · '+money(p.price)+'/'+p.unit]));
const field=(name,label,value='',type='text',extra='')=>`<label class="field">${label}<input name="${name}" type="${type}" value="${esc(value)}" ${extra}></label>`;
const title=(name,sub,actions='')=>`<div class="pagehead"><div><div class="eyebrow">Mercado Abierto · Comercio</div><h1>${name}</h1><p class="muted">${sub}</p></div><div class="row">${actions}</div></div>`;
function marketAllowed(){return adminState.user?.can_access_market===true}
function routeAllowed(p){return (p!=='mercado'||marketAllowed())&&(p!=='admin'||adminAllowed('dashboard'))}
function navigation(){
 document.getElementById('sidebar').innerHTML=`<a class="brand" href="/" aria-label="Mercado Abierto · Menú principal"><span class="brand-mark" aria-hidden="true">M</span>Mercado<br>Abierto</a><div class="small muted" data-rio-style="r010-style-8">Tu espacio de comercio</div>${MENU.filter(([p])=>routeAllowed(p)).map(([p,ico,n])=>`<button class="navitem ${page===p?'active':''}" data-nav="${p}" aria-current="${page===p?'page':'false'}"><i aria-hidden="true">${ico}</i> ${n}</button>`).join('')}<div class="asidefoot"><div class="eyebrow">Datos de práctica</div><div class="small muted">Cotizaciones, pedidos y entregas de demostración guardados por cuenta.</div><a class="btn secondary" href="/">Menú principal</a></div>`;
 const mobile=['panel','solicitudes','pedidos','caja','cuenta'];
 document.getElementById('mobileNav').innerHTML=mobile.filter(routeAllowed).map(p=>{let m=MENU.find(x=>x[0]===p);return `<button class="navitem ${page===p?'active':''}" data-nav="${p}" aria-current="${page===p?'page':'false'}" title="${m[2]}"><i aria-hidden="true">${m[1]}</i><span class="short">${m[2]}</span></button>`}).join('')+`<button class="navitem" data-action="show-menu" aria-label="Ver todas las áreas de comercio"><i aria-hidden="true">☰</i><span class="short">Más</span></button>`;
}
function centro(){
 const total=state.sales.reduce((sum,sale)=>sum+Number(sale.total||0),0);
 const links=MENU.filter(([p])=>!['centro','admin','cuenta'].includes(p)&&routeAllowed(p));
 const jump=(route,name,cls='secondary')=>`<button class="btn ${cls}" type="button" data-nav="${route}">${name}</button>`;
 return `${title('Guía de áreas','Todo lo que puedes hacer en el espacio comercial de Mercado Abierto.')}
 <section class="panel"><h2>Tu negocio conectado</h2><p class="muted">Administra tus cuentas pey y realiza cobros desde las áreas principales.</p><div class="toolbar"><a class="btn primary" href="/#mis-negocios">Mis negocios</a><a class="btn secondary" href="/#cobro-codi">Caja</a><a class="btn secondary" href="/">Menú principal</a></div></section>
 <p class="small muted" role="status">Datos de práctica: ${esc(remoteStatus)} · revisión ${remoteRevision}</p><div class="notice" role="status"><strong>Espacio de demostración</strong> · Las cotizaciones, los pedidos, los fletes y los tickets de esta área son registros de práctica. Para recibir pagos abre Caja desde el menú principal.</div>
 <div class="grid three" data-rio-style="r010-style-5">
  <section class="panel"><div class="eyebrow">01 · Cotizaciones</div><h2>Comprar y entregar</h2><p class="muted">Solicitud → oferta → pedido → flete → recepción.</p><div class="toolbar">${marketAllowed()?jump('mercado','Explorar productos','primary'):''}${jump('solicitudes','Abrir RFQ')}${jump('ofertas','Ofertas')}${jump('pedidos','Pedidos')}${jump('fletes','Fletes')}</div><div class="small muted">${state.rfqs.length} solicitudes · ${state.orders.length} pedidos</div></section>
  <section class="panel"><div class="eyebrow">02 · Ventas de práctica</div><h2>Simulador de caja</h2><p class="muted">Prepara una venta, calcula el cambio y emite un ticket de demostración.</p><div class="toolbar">${jump('caja','Abrir simulador','primary')}${jump('tickets','Ver tickets')}</div><div class="small muted">${state.sales.length} tickets · ${money(total)} en ventas de práctica</div></section>
  <section class="panel"><div class="eyebrow">03 · Cobros</div><h2>Caja y CoDi</h2><p class="muted">Abre tu caja para crear cobros y consultar las confirmaciones de pey.</p><div class="toolbar"><a class="btn primary" href="/#cobro-codi">Abrir Caja</a><a class="btn secondary" href="/#mis-negocios">Configurar mis negocios</a></div></section>
 </div>
 <section class="panel" data-rio-style="r010-style-5"><h2>Áreas comerciales</h2><p class="muted">Elige la tarea que quieres realizar.</p><div class="toolbar">${links.map(([p,i,n])=>jump(p,i+' '+n)).join('')}</div></section>
 <section class="panel" data-rio-style="r010-style-5"><h2>Cuenta y administración</h2><div class="toolbar">${jump('cuenta','⚙ Mi cuenta')}${adminAllowed('dashboard')?jump('admin','🛡 Centro de control','primary'):''}</div></section>`;
}

function panel(){let pending=state.rfqs.filter(r=>r.status==='abierta').length,active=state.orders.filter(o=>o.status!=='recibido').length,earn=state.sales.reduce((a,s)=>a+s.total,0);return `${title('Mercado Abierto','Organiza tus productos, cotizaciones, pedidos y entregas.',btn('Crear solicitud','new-rfq','','primary'))}<section class="hero"><div class="eyebrow">Comercio popular</div><h2>Negocios, productos, cotizaciones y entregas en un mismo lugar.</h2><p>Del catálogo al pedido y del pedido a la recepción, con caja educativa independiente.</p><div class="toolbar">${marketAllowed()?btn('Explorar productos','go-mercado','','primary'):''}${btn('Abrir caja','go-caja')}${btn('Registrar negocio','new-business')}</div><div class="small muted">⚠ Demo local. No envía correos, no solicita pagos y no conecta fleteros reales.</div></section><div class="grid four"><div class="stat"><strong>${state.businesses.filter(b=>b.active).length}</strong><span>Negocios registrados</span></div><div class="stat"><strong>${state.products.filter(p=>p.active).length}</strong><span>Productos publicados</span></div><div class="stat"><strong>${pending}</strong><span>RFQ abiertas</span></div><div class="stat"><strong>${active}</strong><span>Pedidos en curso</span></div></div><div class="grid two" data-rio-style="r010-style-5"><article class="panel"><h2>Recorrido comercial completo</h2><p class="muted">Mercado → Cotización RFQ → Oferta mayorista → Pedido → Flete → Recepción.</p>${marketAllowed()?btn('Explorar productos','go-mercado','','primary'):btn('Crear solicitud','new-rfq','','primary')}</article><article class="panel"><h2>Caja y tickets</h2><p class="muted">Registra una venta de práctica, calcula cambio y genera ticket local.</p><div class="stat"><strong>${money(earn)}</strong><span>Ventas de práctica guardadas por cuenta</span></div><div data-rio-style="r010-style-2">${btn('Ir a caja','go-caja','','primary')}</div></article></div><section class="panel" data-rio-style="r010-style-5"><h3>Actividad reciente</h3>${eventTable(state.events.slice(0,5))}</section>`}
const emojiCat=c=>({'Abarrotes':'🥫','Frutas y verduras':'🥬','Juguetes':'🧸','Ferretería':'🔩','Tecnología':'💻','Otros':'📦'}[c]||'📦');
function mercado(){const arr=state.products.filter(p=>p.active&&(!query||(p.name+' '+p.category).toLowerCase().includes(query.toLowerCase()))&&(category==='Todas'||category===p.category));const total=Object.entries(marketCart).reduce((a,[id,n])=>a+(find('products',id)?.price||0)*n,0);return `${title('Mercado','Explora el catálogo y prepara una solicitud de cotización RFQ.',btn('Agregar producto','new-product','','primary'))}<div class="toolbar"><label class="field grow" data-rio-style="r010-style-7">Buscar producto<input id="searchProducts" placeholder="Nombre o categoría" value="${esc(query)}" autocomplete="off"></label><label class="field">Categoría<select id="filterCategory">${opts(['Todas',...CAT].map(x=>[x,x]),category)}</select></label></div><div class="cards">${arr.map(p=>`<article class="panel product"><div class="symbol" aria-hidden="true">${emojiCat(p.category)}</div><div class="row between"><strong>${esc(p.name)}</strong>${chip('disponible')}</div><div class="muted small">${esc(p.category)} · ${esc(bname(p.owner))}</div><div class="muted small">Existencias referenciales: ${p.stock} ${esc(p.unit)}</div><div class="productfooter"><span class="price">${money(p.price)}<span class="tiny muted">/${esc(p.unit)}</span></span>${btn('+ Añadir','market-add',p.id,'primary','sm')}</div></article>`).join('')||empty('No hay productos para este filtro.')}</div><section class="panel" data-rio-style="r010-style-3"><div class="row between"><h3>🛒 Canasta para cotizar</h3><strong>${money(total)}</strong></div>${cartTable(marketCart,'market')}<div class="toolbar" data-rio-style="r010-style-2">${btn('Crear RFQ con canasta','rfq-from-cart','','primary')}${btn('Vaciar canasta','clear-market')}</div><div class="hint">Los precios son de referencia; la oferta del proveedor se registra por separado.</div></section>`}
function cartTable(cart,prefix){const entries=Object.entries(cart).filter(([id,n])=>n>0&&find('products',id));return entries.length?`<div class="tablewrap"><table><thead><tr><th>Producto</th><th>Unidades</th><th>Subtotal</th><th>Acciones</th></tr></thead><tbody>${entries.map(([id,n])=>{const p=find('products',id);return `<tr><td>${esc(p.name)}</td><td>${n} ${esc(p.unit)}</td><td>${money(n*p.price)}</td><td><div class="row">${btn('−',prefix+'-minus',id,'secondary','sm')}${btn('+',prefix+'-add',id,'secondary','sm')}</div></td></tr>`}).join('')}</tbody></table></div>`:empty('Canasta vacía. Añade productos para continuar.')}
function solicitudes(){return `${title('Solicitudes de cotización','Las RFQ guardan qué necesita el minorista y permiten recibir ofertas.',btn('Nueva RFQ','new-rfq','','primary'))}${state.rfqs.length?`<div class="order-list">${state.rfqs.map(r=>`<article class="panel order"><div><div class="row"><strong>${esc(r.id)}</strong>${chip(r.status)}</div><div class="muted small">Minorista: ${esc(bname(r.buyer))} · ${date(r.createdAt)}</div><p>${r.items.map(i=>`${esc(pname(i.productId))} × ${i.qty}`).join(' · ')}</p><div class="small muted">Destino: ${esc(r.destination)} · ${esc(r.notes||'Sin indicaciones')}</div></div><div class="row">${btn('Ver ofertas','rfq-offers',r.id)}${r.status==='abierta'?btn('Ofertar','offer-for-rfq',r.id,'primary'):''}</div></article>`).join('')}</div>`:empty('Aún no hay RFQ. Crea una solicitud desde el mercado o aquí.')}`}
function ofertas(){return `${title('Ofertas de proveedores','Compara propuestas y acepta una para convertirla en pedido.',btn('Nueva oferta','new-offer','','primary'))}${state.offers.length?`<div class="order-list">${state.offers.map(o=>{const r=find('rfqs',o.rfqId),total=offerTotal(o,r);return `<article class="panel order"><div><div class="row"><strong>${esc(o.id)}</strong>${chip(o.status)}</div><div class="muted small">RFQ ${esc(o.rfqId)} · Mayorista ${esc(bname(o.supplier))}</div><p>${r?.items.map(i=>`${esc(pname(i.productId))} × ${i.qty} (${money(o.prices[i.productId])}/${esc(find('products',i.productId)?.unit||'u')})`).join(' · ')||'RFQ no disponible'}</p><div>Productos: ${money(total-o.deliveryFee)} · Entrega: ${money(o.deliveryFee)} · <strong>Total: ${money(total)}</strong></div><div class="muted small">${esc(o.notes||'Sin comentarios')}</div></div><div class="row">${o.status==='enviada'&&r?.status==='abierta'?btn('Aceptar y crear pedido','accept-offer',o.id,'primary'):''}</div></article>`}).join('')}</div>`:empty('No existen ofertas. Abre una RFQ y registra la propuesta del mayorista.')}`}
function offerTotal(o,r){return Number(o.deliveryFee||0)+(r?.items.reduce((a,i)=>a+i.qty*Number(o.prices?.[i.productId]||0),0)||0)}
function pedidos(){return `${title('Pedidos','Gestiona la cadena posterior a la aceptación de una oferta.',btn('Ver ofertas','go-ofertas','','primary'))}${state.orders.length?`<div class="order-list">${state.orders.map(o=>`<article class="panel order"><div><div class="row"><strong>${esc(o.id)}</strong>${chip(o.status)}</div><div class="muted small">${esc(bname(o.buyer))} ← ${esc(bname(o.supplier))} · ${date(o.createdAt)}</div><p>${o.items.map(i=>`${esc(pname(i.productId))} × ${i.qty}`).join(' · ')}</p><strong>Total cotizado: ${money(o.total)}</strong><div class="small muted">Destino: ${esc(o.destination)}</div></div><div class="row">${o.status==='confirmado'?btn('Marcar preparado','prepare-order',o.id):''}${o.status==='preparado'?btn('Marcar enviado','ship-order',o.id):''}${!['recibido'].includes(o.status)?btn('Crear flete','freight-for-order',o.id,'primary'):''}${['confirmado','preparado','enviado'].includes(o.status)?btn('Confirmar recepción','receive-order',o.id):''}${o.status==='recibido'?btn('Ver historial','go-historial'):''}</div></article>`).join('')}</div>`:empty('Todavía no hay pedidos. Acepta una oferta para crear el primero.')}`}
function fletes(){return `${title('Fletes','Asignación y seguimiento de entregas simuladas, guardadas por cuenta.',btn('Asignar flete','new-freight','','primary'))}${state.freights.length?`<div class="order-list">${state.freights.map(f=>`<article class="panel order"><div><div class="row"><strong>${esc(f.id)}</strong>${chip(f.status)}</div><div class="muted small">Pedido ${esc(f.orderId)} · ${esc(bname(f.carrier))}</div><p>Destino: ${esc(f.destination)} · Costo estimado: <strong>${money(f.cost)}</strong></p></div><div class="row">${f.status==='propuesto'?btn('Aceptar asignación','accept-freight',f.id,'primary'):''}${f.status==='asignado'?btn('Confirmar entrega','complete-freight',f.id,'primary'):''}</div></article>`).join('')}</div>`:empty('No hay fletes. Genera un pedido y asígnale uno.')}<p class="hint">Asignaciones y confirmaciones de esta pantalla son de práctica; no notifican a transportistas reales.</p>`}
function caja(){let sub=Object.entries(posCart).reduce((a,[id,n])=>a+(find('products',id)?.price||0)*n,0);return `${title('Caja educativa','Prepara una venta, calcula cambio y emite un ticket de práctica.',btn('Ver tickets','go-tickets','','secondary'))}<div class="poslayout"><section class="panel"><h2>Productos</h2><div class="cards">${state.products.filter(p=>p.active).map(p=>`<article class="stat"><div class="row between"><span>${emojiCat(p.category)} <strong>${esc(p.name)}</strong></span><span>${money(p.price)}</span></div><p class="small muted">Unidad: ${esc(p.unit)} · Existencias: ${p.stock}</p>${btn('+ Agregar','pos-add',p.id,'primary','sm')}</article>`).join('')}</div></section><section class="panel"><h2>Venta actual</h2>${cartTable(posCart,'pos')}<div class="row between" data-rio-style="r010-style-4"><strong>Total</strong><strong class="price">${money(sub)}</strong></div><form data-form="checkout" class="stack" data-rio-style="r010-style-5"><label class="field">Forma de cobro<select name="payment" id="paymentMode"><option value="efectivo">Efectivo</option><option value="digital_simulado">QR de práctica (no pagable)</option></select></label><label class="field" id="receivedField">Dinero recibido (MXN)<input name="received" id="receivedAmount" type="number" min="0" step="0.01" value="${sub.toFixed(2)}" required></label><div id="cashChange" class="muted small">Cambio estimado: ${money(0)}</div><div id="paymentNote" class="notice" data-rio-style="r010-style-1">QR digital de demostración: no pagable y sin confirmación bancaria.</div><button type="submit" class="btn primary" ${sub<=0?'disabled':''}>Cerrar venta y generar ticket</button>${btn('Vaciar venta','clear-pos')}</form></section></div>`}
function inventario(){return `${title('Inventario y catálogo','Alta, edición y desactivación de productos publicados.',btn('Nuevo producto','new-product','','primary'))}<div class="tablewrap"><table><thead><tr><th>SKU</th><th>Producto</th><th>Responsable</th><th>Precio</th><th>Stock</th><th>Estado</th><th>Acciones</th></tr></thead><tbody>${state.products.map(p=>`<tr><td>${esc(p.id)}</td><td><strong>${esc(p.name)}</strong><div class="small muted">${esc(p.category)} · ${esc(p.unit)}</div></td><td>${esc(bname(p.owner))}</td><td>${money(p.price)}</td><td>${p.stock}</td><td>${chip(p.active?'activo':'inactivo')}</td><td><div class="row">${btn('Editar','edit-product',p.id,'secondary','sm')}${btn(p.active?'Desactivar':'Activar','toggle-product',p.id,'secondary','sm')}</div></td></tr>`).join('')}</tbody></table></div>`}
function negocios(){return `${title('Directorio de negocios','Perfiles de demostración para minoristas, mayoristas y fleteros.',btn('Nuevo negocio','new-business','','primary'))}<div class="cards">${state.businesses.map(b=>`<article class="panel"><div class="row between"><h3>🏪 ${esc(b.name)}</h3>${chip(b.active?'activo':'inactivo')}</div><p class="muted">${esc(b.type)} · ${esc(b.zone)}</p><p class="small">Contacto: ${esc(b.contact||'No registrado')}</p><div class="row">${btn('Editar','edit-business',b.id)}${btn(b.active?'Desactivar':'Activar','toggle-business',b.id,'secondary','sm')}</div></article>`).join('')}</div>`}
function ticketHtml(s){return `<article class="ticket"><h3>MERCADO ABIERTO · TICKET DE PRÁCTICA</h3><p data-rio-style="r010-style-9">NO FISCAL · NO BANCARIO</p><div>Folio: ${esc(s.id)}</div><div>Fecha: ${date(s.createdAt)}</div><hr class="divider">${s.items.map(i=>`<div class="ticketline"><span>${esc(i.name)} × ${i.qty}</span><span>${money(i.price*i.qty)}</span></div>`).join('')}<hr class="divider"><div class="ticketline"><strong>TOTAL</strong><strong>${money(s.total)}</strong></div><div class="ticketline"><span>Método</span><span>${s.payment==='efectivo'?'Efectivo':'Digital simulado'}</span></div>${s.payment==='efectivo'?`<div class="ticketline"><span>Recibido</span><span>${money(s.received)}</span></div><div class="ticketline"><span>Cambio</span><span>${money(s.change)}</span></div>`:''}<hr class="divider"><p data-rio-style="r010-style-9">Demostración local. No acredita pago real ni constituye CFDI.</p></article>`}
function tickets(){return `${title('Tickets de práctica','Visualiza, copia e imprime tickets de práctica vinculados a tu cuenta.',btn('Abrir caja','go-caja','','primary'))}${state.sales.length?`<div class="order-list">${state.sales.map(s=>`<article class="panel order"><div><strong>${esc(s.id)}</strong><div class="muted small">${date(s.createdAt)} · ${esc(s.payment==='efectivo'?'Efectivo':'Digital simulado')} · ${s.items.length} conceptos</div><div class="price">${money(s.total)}</div></div><div class="row">${btn('Ver ticket','view-ticket',s.id,'primary')}${btn('Copiar','copy-ticket',s.id)}</div></article>`).join('')}</div>`:empty('No se han cerrado ventas en la caja.')}`}
function eventTable(events){return events.length?`<div class="tablewrap"><table><thead><tr><th>Fecha</th><th>Evento</th><th>Descripción</th></tr></thead><tbody>${events.map(e=>`<tr><td>${date(e.at)}</td><td>${esc(e.type)}</td><td>${esc(e.detail)}</td></tr>`).join('')}</tbody></table></div>`:empty('Sin movimientos aún.')}
function historial(){return `${title('Historial y datos','Eventos de práctica y exportación de un respaldo local del estado sincronizado.',btn('Exportar JSON','export-data','','primary'))}<div class="grid two"><div class="panel"><h3>Gestión de datos locales</h3><p class="muted">Descarga el estado completo o restaura una copia JSON generada por esta aplicación.</p><div class="toolbar">${btn('Exportar respaldo','export-data','','primary')}<label class="btn">Importar respaldo<input type="file" id="importFile" accept=".json,application/json" data-rio-style="r010-style-1"></label>${btn('Restaurar demo inicial','reset-demo','','warn')}</div><div class="notice small">Estos datos permanecen en este navegador. Ningún respaldo se envía a servidores.</div></div><div class="panel"><h3>Resumen</h3><div class="grid two"><div class="stat"><strong>${state.rfqs.length}</strong><span>RFQ</span></div><div class="stat"><strong>${state.offers.length}</strong><span>Ofertas</span></div><div class="stat"><strong>${state.orders.length}</strong><span>Pedidos</span></div><div class="stat"><strong>${state.sales.length}</strong><span>Ventas</span></div></div></div></div><section class="panel" data-rio-style="r010-style-4"><h3>Registro de actividad</h3>${eventTable(state.events)}</section>`}
/* RÍO Admin R002: integrated role-aware administration, no unauthenticated app screens. */
const adminState={phase:'probing',csrf:'',user:null,permissions:[],server:'unknown',error:'',dashboard:null,users:[],roles:[],events:[],busy:false};
let adminSection='dashboard';
const ADMIN_SECTIONS=[['dashboard','▦','Panel'],['users','👥','Usuarios'],['roles','🗝','Roles'],['audit','📜','Auditoría'],['account','⚙','Mi cuenta']];
const adminAllowed=s=>s==='account'||(s==='dashboard'&&adminState.permissions.includes('admin.dashboard.read'))||
 (s==='users'&&adminState.permissions.includes('admin.users.read'))||
 (s==='roles'&&adminState.permissions.includes('admin.roles.read'))||
 (s==='audit'&&adminState.permissions.includes('admin.audit.read'));
const adminButton=(label,action,id='',kind='secondary')=>`<button type="button" class="btn ${kind}" data-admin-action="${esc(action)}" ${id?'data-admin-id="'+esc(id)+'"':''}>${label}</button>`;
const adminLink=(s,label)=>`<button type="button" class="btn ${s===adminSection?'primary':'secondary'}" data-admin-page="${s}">${esc(label)}</button>`;
const adminStat=(name,value)=>`<div class="panel"><div class="small muted">${esc(name)}</div><div class="admin-number">${esc(value)}</div></div>`;
const fmtAuditDate=x=>date(x?new Date(x*1000).toISOString():null);
function admin(){
 let intro=title('Centro de control','Gestiona accesos y actividad según los permisos de tu cuenta.');
 if(adminState.phase==='probing')return intro+'<div class="panel">Verificando disponibilidad del servidor y la sesión…</div>';
 if(adminState.phase==='offline')return intro+'<section class="panel"><h3>Conexión pendiente</h3><p>No se puede acceder a funciones administrativas sin el servidor.</p>'+adminButton('Reintentar','retry','','primary')+'</section>';
 if(!adminState.user)return intro+'<div class="panel">Sesión no verificada. Inicia sesión desde la portada.</div>';
 let sections=ADMIN_SECTIONS.filter(([key])=>adminAllowed(key));
 let menu=`<div class="admin-hero"><div><div class="eyebrow">Cuenta autenticada</div><strong>${esc(adminState.user.display_name)}</strong><p>${esc(adminState.user.email)} · ${esc(adminState.user.role)}</p></div><div class="row">${adminButton('Cerrar sesión','logout','','secondary')}</div></div>`;
 let rail=`<nav class="admin-rail" aria-label="Herramientas administrativas">${sections.map(([s,ic,name])=>adminLink(s,ic+' '+name)).join('')}</nav>`;
 let body='';
 if(adminSection==='dashboard'){
  let d=adminState.dashboard;
  body=d?`<div class="grid four">${adminStat('Usuarios totales',d.users_total)}${adminStat('Usuarios activos',d.users_active)}${adminStat('Roles disponibles',d.roles_total)}${adminStat('Eventos (30 días)',d.events_last30)}</div><div class="panel"><div class="row"><h3>Actividad administrativa reciente</h3>${adminButton('Actualizar','reload','','primary')}${adminAllowed('audit')?adminLink('audit','Ver auditoría'):''}</div>${d.recent_events.length?`<div class="tablewrap"><table><thead><tr><th>Fecha</th><th>Actor</th><th>Acción</th></tr></thead><tbody>${d.recent_events.map(e=>`<tr><td>${fmtAuditDate(e.created_at)}</td><td>${esc(e.actor_email)}</td><td>${esc(e.action)}</td></tr>`).join('')}</tbody></table></div>`:empty('Sin eventos todavía')}</div>`:'<div class="panel">Cargando indicadores del servidor…</div>';
  body+=`<div class="panel muted">Los indicadores anteriores proceden de usuarios y eventos del servidor. Las ventas, RFQ y fletes de práctica se sincronizan por cuenta en el servidor; no son operaciones bancarias ni comprobantes fiscales.</div>`;
  body+=`<div class="panel"><h3>Otros 14 módulos previstos</h3><p class="muted">Negocios, catálogo, RFQ, ofertas, pedidos, fletes, caja, cobros, planes, territorio, asesores, comunicaciones, soporte e informes: pendientes de integración por etapas. No se presentan como botones operativos.</p></div>`;
 }else if(adminSection==='users'){
  body=`<section class="panel"><div class="row"><h3>Usuarios del servidor</h3>${adminButton('Nuevo usuario','user-new','','primary')}${adminButton('Actualizar','reload')}</div><p class="small muted">Crear una cuenta NO envía correo de invitación. La contraseña inicial se entrega por un canal privado administrado externamente.</p><label class="field">Buscar en la lista<input type="search" id="adminUserSearch" placeholder="Nombre o correo" autocomplete="off"></label><div class="tablewrap"><table><thead><tr><th>Correo</th><th>Nombre</th><th>Rol</th><th>Estado</th><th>Acciones</th></tr></thead><tbody>${adminState.users.map(u=>`<tr data-user-row="${esc((u.email+' '+u.display_name).toLowerCase())}"><td>${esc(u.email)}${u.is_owner?' <span class="chip green">Propietario</span>':''}</td><td>${esc(u.display_name)}</td><td>${esc(u.role)}</td><td>${u.active?'<span class="chip green">activo</span>':'<span class="chip red">inactivo</span>'}</td><td>${!u.is_owner?`<div class="row">${adminButton('Editar','user-edit',u.id)}${adminButton(u.active?'Desactivar':'Reactivar','user-toggle',u.id,u.active?'danger':'secondary')}</div>`:'<span class="muted small">Protegido</span>'}</td></tr>`).join('')}</tbody></table></div></section>`;
 }else if(adminSection==='roles'){
  body=`<section class="panel"><div class="row"><h3>Matriz de roles</h3>${adminButton('Actualizar','reload','','primary')}</div><p class="muted">Los permisos indicados los impone el servidor. La edición de esta matriz queda reservada para otra ronda y no se ofrece un botón ficticio.</p><div class="tablewrap"><table><thead><tr><th>Rol</th><th>Permisos autorizados actualmente</th></tr></thead><tbody>${adminState.roles.map(r=>`<tr><td><strong>${esc(r.role)}</strong></td><td>${r.permissions.map(p=>`<code>${esc(p)}</code>`).join(' · ')||'Sin permisos administrativos'}</td></tr>`).join('')}</tbody></table></div></section>`;
 }else if(adminSection==='audit'){
  body=`<section class="panel"><div class="row"><h3>Registro de auditoría del servidor</h3>${adminButton('Actualizar','reload','','primary')}</div><p class="muted small">Eventos guardados en SQLite. No se guardan contraseñas en el registro.</p><div class="tablewrap"><table><thead><tr><th>Fecha</th><th>Actor</th><th>Evento</th><th>Objeto</th><th>Detalle</th></tr></thead><tbody>${adminState.events.map(e=>`<tr><td>${fmtAuditDate(e.created_at)}</td><td>${esc(e.actor_email)}</td><td>${esc(e.action)}</td><td>${esc(e.subject)}</td><td><code>${esc(e.detail)}</code></td></tr>`).join('')}</tbody></table></div></section>`;
 }else if(adminSection==='account'){
  body=`<div class="grid two"><section class="panel"><h3>Mi perfil</h3><p class="small muted">${esc(adminState.user.email)} · ${esc(adminState.user.role)}</p><form data-admin-form="profile" class="formgrid"><label class="field span2">Nombre visible<input name="display_name" required maxlength="120" value="${esc(adminState.user.display_name)}"></label><button type="submit" class="btn primary">Guardar nombre</button></form></section><section class="panel"><h3>Cambiar contraseña</h3><form data-admin-form="password" class="formgrid"><label class="field span2">Contraseña actual<input type="password" name="current_password" required></label><label class="field span2">Contraseña nueva (14+ caracteres)<input type="password" name="new_password" minlength="14" required></label><button class="btn primary" type="submit">Cambiar contraseña</button></form></section></div><div class="panel"><h3>Sesiones</h3><p class="muted">Revoca las sesiones de esta cuenta, incluida la actual.</p>${adminButton('Cerrar todas mis sesiones','logout-all','','danger')}</div>`;
 }
 return intro+menu+`<div class="admin-workspace">${rail}<div class="admin-body">`+(adminState.error?`<p class="chip red" role="alert">${esc(adminState.error)}</p>`:'')+body+`</div></div>`;
}
function cuenta(){
 if(!adminState.user)return '<section class="panel">Sesión no validada.</section>';
 return `${title('Mi cuenta','Tu sesión y tus permisos en Mercado Abierto.')}
 <section class="panel"><h3>Identidad comprobada</h3>
 <p><strong>${esc(adminState.user.email)}</strong></p>
 <p class="muted">Administra tu perfil y tus negocios desde el menú principal.</p>
 <div class="row"><a class="btn secondary" href="/">Menú principal</a><a class="btn secondary" href="/#mis-negocios">Mis negocios</a>${adminButton('Cerrar sesión','logout','','danger')}</div>
 </section><div class="panel"><h3>Datos de práctica</h3><p>Las 11 vistas comerciales guardan datos de demostración por cuenta en el servidor y mantienen una copia auxiliar en este navegador. Ningún registro acredita pagos bancarios.</p>${btn('Exportar respaldo JSON','export-data','','secondary')}</div>`;
}
async function adminAPI(endpoint, options={}){
 const config={credentials:'same-origin',...options,headers:{...(options.body?{'Content-Type':'application/json'}:{}),...(options.headers||{})}};
 if(options.method && options.method!=='GET' && adminState.csrf)config.headers['X-CSRF-Token']=adminState.csrf;
 let response=await fetch('/api'+endpoint, config),data;
 try{data=await response.json()}catch(e){let err=new Error('El servidor no devolvió JSON válido');err.status=response.status;throw err}
 if(!response.ok){let message=typeof data.detail==='string'?data.detail:'Error HTTP '+response.status;let err=new Error(message);err.status=response.status;throw err}
 return data;
}
async function loadAdminSession(){
 try{
  const data=await adminAPI('/auth/me');
  adminState.phase='active';adminState.user=data.user;adminState.csrf=data.csrf_token;adminState.permissions=data.permissions||[];adminState.server='ready';adminState.error='';
  await loadCommercialStateForUser(data.user.id);
  appReady=true;
  document.getElementById('sessionIdentity').textContent=data.user.email;
  let hash=location.hash;
  if(hash.startsWith('#/admin/')&&adminAllowed('dashboard')){
   page='admin';const candidate=hash.split('/')[2];adminSection=ADMIN_SECTIONS.some(x=>x[0]===candidate)?candidate:'dashboard';
  }else{page='panel';adminSection='dashboard';}
  render();if(page==='admin')await refreshAdmin();
 }catch(e){
  invalidateSession(e.message);
  adminState.phase=e.status===401?'loggedout':'offline';
  render();if(e.status===401&&location.protocol!=='about:')location.replace('/');
 }
}
async function verifySessionNow(){
 if(!appReady)return;
 try{
  const data=await adminAPI('/auth/me');
  if(!data||!data.user||data.user.id!==adminState.user?.id)throw Error('La identidad de la sesión cambió');
  const accessChanged=marketAllowed()!==(data.user.can_access_market===true)||JSON.stringify(adminState.permissions)!==JSON.stringify(data.permissions||[]);
  adminState.user=data.user;adminState.permissions=data.permissions||[];adminState.csrf=data.csrf_token||adminState.csrf;
  if(accessChanged){if(!routeAllowed(page))page='panel';closeModal();render();}
 }
 catch(e){invalidateSession(e.status===401?'Sesión terminada':'No se pudo revalidar la sesión; interfaz bloqueada');adminState.phase=e.status===401?'loggedout':'offline';render();if(e.status===401&&location.protocol!=='about:')location.replace('/');}
}
async function refreshAdmin(){
 if(!adminState.user)return;
 try{
  if(adminSection==='dashboard')adminState.dashboard=await adminAPI('/admin/dashboard');
  else if(adminSection==='users')adminState.users=(await adminAPI('/admin/users')).users;
  else if(adminSection==='roles')adminState.roles=(await adminAPI('/admin/roles')).roles;
  else if(adminSection==='audit')adminState.events=(await adminAPI('/admin/audit')).events;
  adminState.error='';
 }catch(e){adminState.error='No se pudo cargar: '+e.message;if(e.status===401){invalidateSession('Sesión terminada');adminState.phase='loggedout';if(location.protocol!=='about:')location.replace('/');}}
 if(page==='admin')render();
}
async function adminGo(s){if(!adminAllowed(s)){toast('No tienes permiso para abrir esa sección',true);return}adminSection=s;page='admin';location.hash='/admin/'+s;render();await refreshAdmin()}
function adminUserForm(id){
 const user=adminState.users.find(x=>String(x.id)===String(id)),edit=!!user;
 const roles=['ADMIN_OPERACIONES','SOPORTE','ASESOR','MAYORISTA','MINORISTA','FLETERO'];
 if(edit&&user.is_owner){toast('La cuenta propietaria está protegida',true);return}
 const roleSelect=`<label class="field">Rol<select name="role" required>${opts(roles.map(r=>[r,r]),user?.role||'MINORISTA')}</select></label>`;
 const contents=`<form data-admin-form="${edit?'user-edit':'user-new'}" class="formgrid"><input type="hidden" name="id" value="${esc(id||'')}">${edit?`<p class="span2 muted">${esc(user.email)}</p>`:`<label class="field">Correo electrónico<input type="email" name="email" required maxlength="254" autocomplete="off"></label>`}<label class="field">Nombre visible<input name="display_name" value="${esc(user?.display_name||'')}" required maxlength="120"></label>${roleSelect}${edit?`<label class="field">Estado<select name="active"><option value="true" ${user.active?'selected':''}>Activo</option><option value="false" ${!user.active?'selected':''}>Desactivado</option></select></label>`:`<label class="field span2">Contraseña inicial (mínimo 14 caracteres)<input type="password" minlength="14" name="password" required autocomplete="new-password"></label>`}<div class="span2 row"><button class="btn primary" type="submit">${edit?'Guardar cambios':'Crear usuario'}</button>${btn('Cancelar','close-modal')}</div></form>`;
 modal(edit?'Editar usuario':'Crear usuario',contents);
}
async function adminAction(action,id){
 try{
  if(action==='retry'){adminState.phase='probing';render();await loadAdminSession();return}
  if(action==='user-new'){adminUserForm('');return}
  if(action==='user-edit'){adminUserForm(id);return}
  if(action==='reload'){await refreshAdmin();return}
  if(action==='user-toggle'){
   const u=adminState.users.find(x=>String(x.id)===String(id));if(!u)return;
   if(!confirm((u.active?'¿Desactivar':'¿Reactivar')+' a '+u.email+'?'))return;
   await adminAPI('/admin/users/'+id,{method:'PATCH',body:JSON.stringify({active:!u.active})});await refreshAdmin();toast('Estado de usuario actualizado');return;
  }
  if(action==='logout' || action==='logout-all'){
   if(action==='logout-all' && !confirm('¿Revocar todas las sesiones de esta cuenta?'))return;
   await adminAPI(action==='logout'?'/auth/logout':'/auth/logout-all',{method:'POST',body:'{}'});
   invalidateSession('Sesión cerrada');adminState.phase='loggedout';render();if(location.protocol!=='about:')location.assign('/');return;
  }
 }catch(e){adminState.error=e.message;render()}
}
async function adminForm(form){
 const fd=new FormData(form),val=k=>String(fd.get(k)||'').trim(),type=form.dataset.adminForm;
 try{
  if(type==='user-new'){
   await adminAPI('/admin/users',{method:'POST',body:JSON.stringify({email:val('email'),display_name:val('display_name'),password:String(fd.get('password')||''),role:val('role')})});
   closeModal();await refreshAdmin();toast('Usuario creado en el servidor');return;
  }
  if(type==='user-edit'){
   await adminAPI('/admin/users/'+encodeURIComponent(val('id')),{method:'PATCH',body:JSON.stringify({display_name:val('display_name'),role:val('role'),active:val('active')==='true'})});
   closeModal();await refreshAdmin();toast('Usuario actualizado');return;
  }
  if(type==='profile'){
   await adminAPI('/auth/profile',{method:'PATCH',body:JSON.stringify({display_name:val('display_name')})});
   await loadAdminSession();toast('Nombre actualizado');return;
  }
  if(type==='password'){
   await adminAPI('/auth/password',{method:'PATCH',body:JSON.stringify({current_password:String(fd.get('current_password')||''),new_password:String(fd.get('new_password')||'')})});
   form.reset();toast('Contraseña actualizada y demás sesiones revocadas');return;
  }
 }catch(e){adminState.error=e.message;render();toast('Operación no completada: '+e.message,true)}
}
document.addEventListener('click', e=>{
 const tab=e.target.closest('[data-admin-page]');if(tab){adminGo(tab.dataset.adminPage);return}
 const action=e.target.closest('[data-admin-action]');if(action){adminAction(action.dataset.adminAction,action.dataset.adminId||'');return}
});
document.addEventListener('submit',e=>{
 const form=e.target.closest('form[data-admin-form]');if(!form)return;e.preventDefault();adminForm(form);
});
document.addEventListener('input',e=>{
 if(e.target.id==='adminUserSearch'){
  let s=e.target.value.toLowerCase().trim();document.querySelectorAll('[data-user-row]').forEach(r=>{r.hidden=!r.dataset.userRow.includes(s)});
 }
});

const PAGES={panel,centro,mercado,solicitudes,ofertas,pedidos,fletes,caja,inventario,negocios,tickets,historial,admin,cuenta};
function render(){
 const top=document.querySelector('.topbar');
 if(!appReady){top.style.display='none';document.getElementById('sidebar').innerHTML='';document.getElementById('mobileNav').innerHTML='';
  document.getElementById('app').innerHTML='<section class="panel admin-access"><h2>Validando tu sesión…</h2><p class="muted">La plataforma requiere una cuenta activa y conexión con el servidor.</p>'+ (adminState.phase==='offline'?adminButton('Reintentar conexión','retry','','primary'):'')+'</section>';return;
 }
 if(!routeAllowed(page))page='panel';
 top.style.display='';navigation();document.getElementById('app').innerHTML=PAGES[page]();bindCashPreview();
 if(pendingDraft){
  const conflict=pendingDraft.baseRevision!==remoteRevision;
  document.getElementById('modalRoot').innerHTML=
   '<div class="dialog-backdrop"><section class="dialog" role="dialog" aria-modal="true" aria-labelledby="draftTitle">'+
   '<h2 id="draftTitle">Borrador comercial pendiente</h2>'+
   '<p>'+ (conflict?'El servidor avanzó a otra revisión. No se sobrescribirá automáticamente. Exporta para conciliar antes de descartar.':'Se encontró un borrador que no obtuvo confirmación del servidor. Puedes recuperar su contenido y reintentar el guardado.')+'</p>'+
   '<p class="small muted">Revisión del borrador: '+pendingDraft.baseRevision+' · Revisión del servidor: '+remoteRevision+'</p>'+
   '<div class="row">'+(conflict?'':btn('Recuperar y guardar','recover-draft','','primary'))+
   btn('Exportar borrador','export-draft')+btn('Descartar borrador','discard-draft','','secondary')+'</div></section></div>';
 }
}
function navigate(p){if(!appReady||!PAGES[p])return;
 if(p==='mercado'&&!marketAllowed()){toast('Mercado está disponible solo en la cuenta de Ivania',true);return}
 if(p==='admin'&&!adminAllowed('dashboard')){toast('Se requiere un rol administrativo',true);return}
 page=p;query=page==='mercado'?query:'';
 if(p==='admin'){adminSection='dashboard';location.hash='/admin/dashboard';}else if(location.hash.startsWith('#/admin/'))location.hash='';
 render();if(p==='admin')refreshAdmin();verifySessionNow();window.scrollTo({top:0,behavior:'instant'});document.getElementById('app').focus({preventScroll:true});
}
const modal=(heading,body)=>{modalReturnFocus=document.activeElement;document.getElementById('modalRoot').innerHTML=`<div class="dialog-backdrop" id="backdrop"><section class="dialog" role="dialog" aria-modal="true" aria-labelledby="modalTitle"><div class="dialoghead"><h2 id="modalTitle">${heading}</h2><button class="close" data-action="close-modal" aria-label="Cerrar ventana">✕</button></div>${body}</section></div>`;document.querySelector('.dialog input:not([type=hidden]),.dialog select')?.focus()};
const closeModal=()=>{document.getElementById('modalRoot').innerHTML='';if(modalReturnFocus?.isConnected)modalReturnFocus.focus();modalReturnFocus=null};
const foot=(label='Guardar')=>`<div class="row" data-rio-style="r010-style-6"><button class="btn primary" type="submit">${label}</button>${btn('Cancelar','close-modal')}</div>`;
function businessForm(id){let b=find('businesses',id)||{};modal(id?'Editar negocio':'Nuevo negocio',`<form class="formgrid" data-form="business"><input type="hidden" name="id" value="${esc(id||'')}">${field('name','Nombre del negocio',b.name||'','text','required maxlength="80"')}<label class="field">Tipo<select name="type" required>${opts([['minorista','Minorista'],['mayorista','Mayorista'],['fletero','Transportista / Fletero']],b.type||'minorista')}</select></label>${field('zone','Zona o localidad',b.zone||'','text','required maxlength="100"')}${field('contact','Medio de contacto (opcional)',b.contact||'','text','maxlength="100"')}<div class="span2">${foot()}</div></form>`)}
function productForm(id){let p=find('products',id)||{};modal(id?'Editar producto':'Nuevo producto',`<form class="formgrid" data-form="product"><input type="hidden" name="id" value="${esc(id||'')}">${field('name','Nombre del producto',p.name||'','text','required maxlength="90"')}<label class="field">Categoría<select name="category">${opts(CAT.map(x=>[x,x]),p.category||'Abarrotes')}</select></label><label class="field">Unidad<select name="unit">${opts([['pieza','Pieza'],['kg','Kilogramo'],['metro','Metro'],['caja','Caja']],p.unit||'pieza')}</select></label>${field('price','Precio de referencia MXN',p.price??0,'number','min="0" step="0.01" required')}${field('stock','Stock de referencia',p.stock??0,'number','min="0" step="0.001" required')}<label class="field">Negocio responsable<select name="owner" required>${busOptions(null,p.owner||'')}</select></label><div class="span2">${foot()}</div></form>`)}
function rfqForm(fromCart=false){let cart=Object.entries(marketCart).filter(([id,n])=>n>0&&find('products',id));let itemFields=fromCart&&cart.length?`<div class="span2"><strong>Productos de la canasta</strong>${cart.map(([id,n])=>`<p class="small">${esc(pname(id))}: ${n} ${esc(find('products',id).unit)}</p>`).join('')}</div>`:`<label class="field">Producto<select name="productId" required>${productOptions()}</select></label>${field('qty','Cantidad solicitada',1,'number','min="0.001" step="0.001" required')}`;modal('Crear solicitud RFQ',`<form class="formgrid" data-form="rfq"><input type="hidden" name="fromCart" value="${fromCart?'1':'0'}"><label class="field">Negocio solicitante<select name="buyer" required>${busOptions('minorista')}</select></label>${field('destination','Entrega solicitada','Ciudad de México','text','required maxlength="130"')}${itemFields}<label class="field span2">Notas opcionales<textarea name="notes" maxlength="400" placeholder="Por ejemplo, horario, presentación o volumen"></textarea></label><div class="span2">${foot('Publicar solicitud local')}</div></form>`)}
function offerForm(rfqId){let choices=state.rfqs.filter(r=>r.status==='abierta');let r=find('rfqs',rfqId)||choices[0];if(!r){toast('Primero crea una RFQ abierta.',true);return}modal('Oferta mayorista',`<form class="formgrid" data-form="offer"><input type="hidden" name="rfqId" value="${esc(r.id)}"><p class="span2">Cotización para <strong>${esc(r.id)}</strong> · ${esc(bname(r.buyer))}</p><label class="field">Mayorista<select name="supplier" required>${busOptions('mayorista')}</select></label>${field('deliveryFee','Cargo de entrega MXN',0,'number','min="0" step="0.01" required')}<div class="span2"><h3>Precios por producto</h3></div>${r.items.map(i=>{let p=find('products',i.productId);return `<label class="field span2">${esc(p?.name||i.productId)} × ${i.qty} ${esc(p?.unit||'unidades')} (precio unitario MXN)<input type="number" name="unit_${esc(i.productId)}" value="${Number(p?.price||0).toFixed(2)}" min="0" step="0.01" required></label>`}).join('')}<label class="field span2">Condiciones<textarea name="notes" maxlength="400" placeholder="Plazo de entrega y condiciones"></textarea></label><div class="span2">${foot('Enviar oferta local')}</div></form>`)}
function freightForm(orderId){let available=state.orders.filter(o=>o.status!=='recibido');let o=find('orders',orderId)||available[0];if(!o){toast('No hay pedidos abiertos para un flete.',true);return}modal('Asignar transporte',`<form data-form="freight" class="formgrid"><label class="field">Pedido<select name="orderId" required>${opts(available.map(x=>[x.id,x.id+' · '+bname(x.buyer)]),o.id)}</select></label><label class="field">Fletero<select name="carrier" required>${busOptions('fletero')}</select></label>${field('cost','Costo acordado MXN',80,'number','min="0" step="0.01" required')}<div class="span2">${foot('Proponer flete')}</div></form>`)}
function viewTicket(id){const s=find('sales',id);if(!s)return;previewTicket=s;modal('Ticket de práctica',`${ticketHtml(s)}<div class="row">${btn('Imprimir','print-ticket','','primary')}${btn('Copiar texto','copy-ticket',id)}${btn('Cerrar','close-modal')}</div>`)}
function copyTicket(s){const txt=`MERCADO ABIERTO TICKET DE PRÁCTICA\nNO FISCAL / NO BANCARIO\nFolio: ${s.id}\n${date(s.createdAt)}\n`+s.items.map(i=>`${i.name} x${i.qty} = ${money(i.price*i.qty)}`).join('\n')+`\nTOTAL ${money(s.total)}\nMétodo: ${s.payment}\nPago real NO VERIFICADO`;if(navigator.clipboard?.writeText){navigator.clipboard.writeText(txt).then(()=>toast('Ticket copiado')).catch(()=>fallbackCopy(txt))}else fallbackCopy(txt)}
function fallbackCopy(t){const el=document.createElement('textarea');el.value=t;document.body.append(el);el.select();try{document.execCommand('copy');toast('Texto copiado')}catch(e){toast('No se pudo copiar automáticamente',true)}el.remove()}
function download(name,text,type){const blob=new Blob([text],{type});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1500)}
function bindCashPreview(){const mode=document.getElementById('paymentMode');if(!mode)return;const received=document.getElementById('receivedAmount');let sum=Object.entries(posCart).reduce((a,[id,n])=>a+(find('products',id)?.price||0)*n,0);function update(){const digital=mode.value!=='efectivo';document.getElementById('receivedField').style.display=digital?'none':'';received.required=!digital;document.getElementById('paymentNote').style.display=digital?'block':'none';document.getElementById('cashChange').textContent=digital?'Se emitirá un ticket digital SIMULADO sin cobro real.':Number(received.value)>=sum?'Cambio estimado: '+money(Number(received.value)-sum):'Faltan '+money(sum-Number(received.value))}mode.addEventListener('change',update);received.addEventListener('input',update);update()}
function changeQty(obj,id,delta){const n=(obj[id]||0)+delta;if(n<=0)delete obj[id];else obj[id]=Math.min(n,9999);render()}
function withNumber(x){const n=Number(x);return Number.isFinite(n)&&n>=0?n:NaN}
function requireSelection(v,label){if(!v)throw Error('Selecciona '+label);return v}
function onAction(action,id){
 if(['market-add','market-minus','clear-market','rfq-from-cart'].includes(action)&&!marketAllowed()){toast('Mercado está disponible solo en la cuenta de Ivania',true);return}
 switch(action){
 case 'recover-draft':{
  if(!pendingDraft||pendingDraft.baseRevision!==remoteRevision){toast('La revisión cambió: exporta y concilia el borrador antes de continuar.',true);break}
  state=pendingDraft.state;pendingDraft=null;document.getElementById('modalRoot').replaceChildren();persist();queueRemoteState();render();toast('Guardando borrador recuperado');break}
 case 'export-draft':{
  if(pendingDraft)download('RIO_BORRADOR_PENDIENTE_R017.json',JSON.stringify(pendingDraft,null,2),'application/json');break}
 case 'discard-draft':{
  if(!pendingDraft||!confirm('¿Descartar definitivamente el borrador local no sincronizado? Exporta antes si quieres conservarlo.'))break;
  localStorage.removeItem(DRAFT_PREFIX+String(adminState.user?.id||''));pendingDraft=null;document.getElementById('modalRoot').replaceChildren();persist();remoteStatus='SINCRONIZADO';render();break}
 case 'show-menu':modal('Navegación',`<div class="grid two">${MENU.filter(([p])=>routeAllowed(p)).map(([p,i,n])=>`<button class="btn secondary" data-nav="${p}">${i} ${n}</button>`).join('')}</div>`);break;case 'close-modal':closeModal();break;case 'new-business':businessForm();break;case 'edit-business':businessForm(id);break;case 'toggle-business':{let b=find('businesses',id);if(b){b.active=!b.active;commit('NEGOCIO',`${b.name}: ${b.active?'activo':'inactivo'}`)}break}case 'new-product':productForm();break;case 'edit-product':productForm(id);break;case 'toggle-product':{let p=find('products',id);if(p){p.active=!p.active;commit('PRODUCTO',`${p.name}: ${p.active?'activo':'inactivo'}`)}break}case 'market-add':changeQty(marketCart,id,1);break;case 'market-minus':changeQty(marketCart,id,-1);break;case 'pos-add':changeQty(posCart,id,1);break;case 'pos-minus':changeQty(posCart,id,-1);break;case 'clear-market':marketCart={};render();break;case 'clear-pos':posCart={};render();break;case 'rfq-from-cart':if(!Object.keys(marketCart).length){toast('Agrega al menos un producto.',true);return}rfqForm(true);break;case 'new-rfq':rfqForm();break;case 'new-offer':offerForm();break;case 'offer-for-rfq':offerForm(id);break;case 'rfq-offers':navigate('ofertas');break;case 'accept-offer':{let o=find('offers',id),r=o&&find('rfqs',o.rfqId);if(!o||!r||r.status!=='abierta'||o.status!=='enviada')return;const order={id:uid('PED'),createdAt:now(),buyer:r.buyer,supplier:o.supplier,rfqId:r.id,offerId:o.id,destination:r.destination,items:r.items.map(i=>({...i,price:Number(o.prices[i.productId]||0)})),total:offerTotal(o,r),status:'confirmado'};r.status='adjudicada';o.status='aceptada';state.offers.filter(x=>x.rfqId===r.id&&x.id!==o.id).forEach(x=>x.status='no_seleccionada');state.orders.unshift(order);page='pedidos';commit('PEDIDO',`Pedido ${order.id} creado desde ${r.id}`);break}case 'prepare-order':case 'ship-order':case 'receive-order':{let o=find('orders',id);if(!o)return;o.status=action==='prepare-order'?'preparado':action==='ship-order'?'enviado':'recibido';commit('PEDIDO',`${o.id}: ${o.status}`);break}case 'new-freight':freightForm();break;case 'freight-for-order':freightForm(id);break;case 'accept-freight':case 'complete-freight':{let f=find('freights',id);if(!f)return;f.status=action==='accept-freight'?'asignado':'entregado';if(f.status==='entregado'){let o=find('orders',f.orderId);if(o)o.status='recibido'}commit('FLETE',`${f.id}: ${f.status}`);break}case 'view-ticket':viewTicket(id);break;case 'copy-ticket':{let s=find('sales',id);if(s)copyTicket(s);break}case 'print-ticket':if(previewTicket){document.getElementById('printArea').innerHTML=ticketHtml(previewTicket);window.print()}break;case 'export-data':download('RIO_MERCADO_ABIERTO_RESPALDO_R001.json',JSON.stringify(state,null,2),'application/json');toast('Respaldo JSON descargado');break;case 'reset-demo':if(confirm('¿Restaurar datos de muestra? Se reemplazarán los datos locales. Exporta antes si deseas conservarlos.')){state=seed();marketCart={};posCart={};commit('DEMO','Datos iniciales restaurados')}break;default:if(action.startsWith('go-'))navigate(action.slice(3));}}
function onForm(form){const fd=new FormData(form);const val=k=>String(fd.get(k)||'').trim();try{switch(form.dataset.form){case 'business':{let id=val('id'),b=id&&find('businesses',id);let data={name:requireSelection(val('name'),'nombre'),type:val('type'),zone:requireSelection(val('zone'),'zona'),contact:val('contact')};if(b)Object.assign(b,data);else state.businesses.push({id:uid('NEG'),...data,active:true});closeModal();commit('NEGOCIO',`Negocio ${data.name} ${b?'actualizado':'registrado'}`);break}case 'product':{let id=val('id'),p=id&&find('products',id);let price=withNumber(val('price')),stock=withNumber(val('stock'));if(!Number.isFinite(price)||!Number.isFinite(stock))throw Error('Precio o inventario inválido');const owner=requireSelection(val('owner'),'negocio');if(!find('businesses',owner))throw Error('El negocio no existe');const data={name:requireSelection(val('name'),'producto'),category:val('category'),unit:val('unit'),price,stock,owner};if(p)Object.assign(p,data);else state.products.push({id:uid('SKU'),...data,active:true});closeModal();commit('PRODUCTO',`Producto ${data.name} ${p?'actualizado':'creado'}`);break}case 'rfq':{let from=val('fromCart')==='1',items=from?Object.entries(marketCart).map(([productId,qty])=>({productId,qty:Number(qty)})): [{productId:val('productId'),qty:withNumber(val('qty'))}];items=items.filter(i=>find('products',i.productId)&&i.qty>0);if(!items.length)throw Error('Se necesita un producto y una cantidad válida');const buyer=requireSelection(val('buyer'),'minorista');if(!find('businesses',buyer))throw Error('Minorista no registrado');const r={id:uid('RFQ'),createdAt:now(),buyer,destination:requireSelection(val('destination'),'destino'),notes:val('notes'),items,status:'abierta'};state.rfqs.unshift(r);if(from)marketCart={};closeModal();page='solicitudes';commit('RFQ',`Solicitud ${r.id} creada`);break}case 'offer':{let r=find('rfqs',val('rfqId'));if(!r||r.status!=='abierta')throw Error('La RFQ ya no está abierta');let supplier=requireSelection(val('supplier'),'mayorista'),deliveryFee=withNumber(val('deliveryFee'));if(!find('businesses',supplier)||!Number.isFinite(deliveryFee))throw Error('Mayorista o entrega inválidos');let prices={};for(const i of r.items){let num=withNumber(val('unit_'+i.productId));if(!Number.isFinite(num))throw Error('Precio unitario inválido');prices[i.productId]=num}let o={id:uid('OFR'),createdAt:now(),rfqId:r.id,supplier,prices,deliveryFee,notes:val('notes'),status:'enviada'};state.offers.unshift(o);closeModal();page='ofertas';commit('OFERTA',`Oferta ${o.id} registrada`);break}case 'freight':{let orderId=val('orderId'),o=find('orders',orderId),carrier=val('carrier'),cost=withNumber(val('cost'));if(!o||o.status==='recibido'||!find('businesses',carrier)||!Number.isFinite(cost))throw Error('Pedido, fletero o costo inválidos');let f={id:uid('FLT'),createdAt:now(),orderId,carrier,cost,destination:o.destination,status:'propuesto'};state.freights.unshift(f);closeModal();page='fletes';commit('FLETE',`Flete ${f.id} propuesto`);break}case 'checkout':{let items=Object.entries(posCart).filter(([id,n])=>n>0&&find('products',id)).map(([id,qty])=>{let p=find('products',id);return {productId:id,name:p.name,qty,price:p.price}});if(!items.length)throw Error('La venta está vacía');let total=items.reduce((a,i)=>a+i.qty*i.price,0);let payment=val('payment'),received=payment==='efectivo'?withNumber(val('received')):0;if(payment==='efectivo'&&(!Number.isFinite(received)||received+1e-9<total))throw Error('Efectivo recibido insuficiente');if(!['efectivo','digital_simulado'].includes(payment))throw Error('Método desconocido');const s={id:uid('TKT'),createdAt:now(),items,total,payment,received,change:payment==='efectivo'?Math.round((received-total)*100)/100:0,mode:'SIMULACION_LOCAL'};state.sales.unshift(s);posCart={};page='tickets';commit('CAJA',`Ticket ${s.id} registrado`);viewTicket(s.id);break}default:return} }catch(e){toast(e.message||'No se pudo guardar',true)}}
document.addEventListener('click',e=>{const n=e.target.closest('[data-nav]');if(n){closeModal();navigate(n.dataset.nav);return}const a=e.target.closest('[data-action]');if(a){try{onAction(a.dataset.action,a.dataset.id||'')}catch(err){toast('Acción no completada: '+err.message,true)}return}if(e.target?.id==='backdrop')closeModal()});
document.addEventListener('submit',e=>{const f=e.target.closest('form[data-form]');if(!f)return;e.preventDefault();onForm(f)});
document.addEventListener('input',e=>{if(e.target.id==='searchProducts'){const el=e.target;const caret=el.selectionStart;query=el.value;render();const next=document.getElementById('searchProducts');next?.focus();next?.setSelectionRange(caret,caret)}});
document.addEventListener('change',async e=>{if(e.target.id==='filterCategory'){category=e.target.value;render()}if(e.target.id==='importFile'&&e.target.files?.[0]){try{let raw=await e.target.files[0].text();if(raw.length>3_000_000)throw Error('Archivo demasiado grande');let obj=JSON.parse(raw);if(!validate(obj))throw Error('Formato de respaldo no reconocido');if(!confirm('¿Reemplazar los datos locales con el respaldo seleccionado?'))return;state=obj;marketCart={};posCart={};page='panel';commit('RESPALDO','Respaldo local importado')}catch(err){toast('No se pudo importar: '+err.message,true)}}});
document.addEventListener('keydown',e=>{const dialog=document.querySelector('#modalRoot [role="dialog"]');if(e.key==='Escape'&&dialog){e.preventDefault();closeModal();return;}if(e.key!=='Tab'||!dialog)return;const nodes=[...dialog.querySelectorAll('button:not([disabled]),input:not([disabled]):not([type="hidden"]),select:not([disabled]),textarea:not([disabled]),a[href]')].filter(n=>n.getClientRects().length);if(!nodes.length){e.preventDefault();dialog.focus();return;}const first=nodes[0],last=nodes[nodes.length-1];if(e.shiftKey&&(document.activeElement===first||!dialog.contains(document.activeElement))){e.preventDefault();last.focus();}else if(!e.shiftKey&&(document.activeElement===last||!dialog.contains(document.activeElement))){e.preventDefault();first.focus();}});
render();
loadAdminSession();
setInterval(()=>{if(appReady)verifySessionNow()},60000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&appReady)verifySessionNow()});
window.RIO_DEMO={getState:()=>JSON.parse(JSON.stringify(state)),getPage:()=>page,go:navigate,version:'R010_GATEWAY_AUTH_R008_VIEWS',isReady:()=>appReady,getUiRoutes:()=>MENU.filter(([p])=>routeAllowed(p)).map(row=>row[0])};
})();