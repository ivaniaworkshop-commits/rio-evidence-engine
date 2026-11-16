(() => {
 'use strict';
 const byId=id=>document.getElementById(id);
 const button=byId('owner-activity-open'),dialog=byId('owner-activity-dialog');
 const list=byId('owner-activity-list'),status=byId('owner-activity-status');
 const more=byId('owner-activity-more'),refresh=byId('owner-activity-refresh'),filter=byId('owner-activity-category');
 let allowed=false,cursor=null,busy=false,generation=0;
 const labels={ACCOUNT_CREATED:'Cuenta registrada',ACCOUNT_EXISTS:'Registro repetido: la cuenta ya existe',VERIFICATION_REQUESTED:'Verificación solicitada',VERIFICATION_ACCEPTED:'Verificación: correo aceptado por el servidor',VERIFICATION_FAILED:'Falló el envío de verificación',EMAIL_VERIFIED:'Correo verificado',VERIFY_LINK_INVALID:'Enlace de verificación rechazado',LOGIN_ACCEPTED:'Inicio de sesión correcto',LOGIN_REJECTED:'Inicio de sesión rechazado',LOGIN_PENDING:'Acceso pendiente de verificar correo',LOGOUT:'Sesión cerrada',RESET_REQUESTED:'Recuperación solicitada',RESET_ACCEPTED:'Recuperación: correo aceptado por el servidor',RESET_FAILED:'Falló el envío de recuperación',PASSWORD_RESET:'Contraseña restablecida',PEY_SAVED:'Conexión de pey guardada',PEY_ACTIVATED:'CoDi habilitado',PEY_REMOVED:'Conexión de pey eliminada',RECEIPT_ACCEPTED:'Comprobante: correo aceptado por el servidor',RECEIPT_UNCERTAIN:'Comprobante: entrega de correo incierta'};
 function clear(){generation++;cursor=null;list.replaceChildren();more.hidden=true;status.textContent='';busy=false;refresh.disabled=false;filter.disabled=false;}
 function authorize(value){allowed=value===true;button.hidden=!allowed;if(!allowed){if(dialog.open)dialog.close();clear();}}
 async function load(append=false){
  if(!allowed||!dialog.open||busy)return;
  const version=++generation;busy=true;refresh.disabled=true;more.disabled=true;filter.disabled=true;
  if(!append){cursor=null;list.replaceChildren();}
  status.textContent='Consultando actividad…';
  const params=new URLSearchParams({limit:'30'});
  if(filter.value)params.set('category',filter.value);
  if(append&&cursor)params.set('before',cursor);
  try{
   const data=await call('/v1/admin/activity?'+params);
   if(version!==generation||!allowed||!dialog.open)return;
   for(const event of data.events){
    const item=document.createElement('li'),title=document.createElement('strong'),date=document.createElement('time');
    title.textContent=labels[event.event_type]||'Evento de actividad';date.textContent=new Date(event.occurred_at*1000).toLocaleString('es-MX',{timeZone:'America/Mexico_City'});
    item.append(title,date);
    if(event.email){const email=document.createElement('span');email.textContent=event.email;item.append(email);}
    if(event.detail_code){const code=document.createElement('small');code.textContent='Resultado: '+event.detail_code;item.append(code);}
    if(event.source!=='LIVE_EVENT'){const note=document.createElement('small');note.textContent=event.source==='HISTORICAL_SENT'?'Envío anterior comprobado en el remitente':'Recuperado del estado anterior de la cuenta';item.append(note);}
    list.append(item);
   }
   cursor=data.next_cursor||null;more.hidden=!cursor;
   status.textContent=list.children.length?list.children.length+' eventos mostrados.':'No hay eventos en esta categoría.';
  }catch(error){if(version===generation){if(error.status===401||error.status===403){authorize(false);return;}status.textContent='No se pudo cargar la actividad. Vuelve a intentar.';}}
  finally{if(version===generation){busy=false;refresh.disabled=false;more.disabled=false;filter.disabled=false;}}
 }
 button.addEventListener('click',()=>{if(allowed){clear();dialog.showModal();void load();}});
 byId('owner-activity-close').addEventListener('click',()=>{clear();dialog.close();});
 dialog.addEventListener('close',clear);
 dialog.addEventListener('cancel',clear);
 refresh.addEventListener('click',()=>{void load();});filter.addEventListener('change',()=>{void load();});more.addEventListener('click',()=>{void load(true);});
 window.RioActivity=Object.freeze({authorize});
 authorize(window.RioOwnerActivityAllowed===true);
})();
