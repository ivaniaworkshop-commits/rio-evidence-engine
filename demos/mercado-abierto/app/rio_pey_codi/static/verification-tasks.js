(() => {
 'use strict';
 const byId=id=>document.getElementById(id);
 const button=byId('owner-verification-open'),dialog=byId('owner-verification-dialog');
 const list=byId('owner-verification-list'),status=byId('owner-verification-status');
 const filter=byId('owner-verification-filter'),domain=byId('owner-verification-domain');
 let allowed=false,rows=[],busy=false,generation=0;
 const statusNames={PENDING:'Pendiente',IN_PROGRESS:'En curso',BLOCKED:'Bloqueada',VERIFIED:'Verificada'};
 function authorize(value){allowed=value===true;button.hidden=!allowed;if(!allowed&&dialog.open)dialog.close();}
 function selectedRows(){return rows.filter(row=>(!filter.value||row.status===filter.value)&&(!domain.value||row.domain===domain.value));}
 function render(){
  list.replaceChildren();const selected=selectedRows();
  for(const row of selected){
   const card=document.createElement('article'),heading=document.createElement('div'),title=document.createElement('h3'),badge=document.createElement('span'),description=document.createElement('p'),source=document.createElement('p'),form=document.createElement('form'),stateLabel=document.createElement('label'),stateSelect=document.createElement('select'),referenceLabel=document.createElement('label'),reference=document.createElement('input'),noteLabel=document.createElement('label'),note=document.createElement('textarea'),save=document.createElement('button');
   card.className='verification-task';heading.className='verification-task-heading';title.textContent=row.title;badge.className='verification-badge';badge.textContent=statusNames[row.status]||row.status;heading.append(title,badge);description.textContent=row.description;source.className='muted';source.textContent='Fuente: '+row.source_label;
   if(row.source_url){const link=document.createElement('a');link.href=row.source_url;link.target='_blank';link.rel='noopener noreferrer';link.textContent='Abrir fuente';source.append(' · ',link);}
   stateLabel.textContent='Estado';stateSelect.name='status';for(const value of ['PENDING','IN_PROGRESS','BLOCKED','VERIFIED']){const option=document.createElement('option');option.value=value;option.textContent=statusNames[value];stateSelect.append(option);}stateSelect.value=row.status;stateLabel.append(stateSelect);
   referenceLabel.textContent='Referencia de evidencia (URL pública o folio)';reference.maxLength=160;reference.value=row.evidence_reference||'';reference.autocomplete='off';referenceLabel.append(reference);
   noteLabel.textContent='Nota de verificación';note.maxLength=500;note.value=row.note||'';noteLabel.append(note);
   save.type='submit';save.textContent='Guardar';save.className='outline';form.append(stateLabel,referenceLabel,noteLabel,save);
   form.addEventListener('submit',event=>{event.preventDefault();void update(row,{status:stateSelect.value,evidence_reference:reference.value.trim()||null,note:note.value.trim()||null});});
   card.append(heading,description,source,form);list.append(card);
  }
  const count=rows.reduce((result,row)=>(result[row.status]=(result[row.status]||0)+1,result),{});
  byId('owner-verification-counts').textContent=`${count.PENDING||0} pendientes · ${count.IN_PROGRESS||0} en curso · ${count.BLOCKED||0} bloqueadas · ${count.VERIFIED||0} verificadas`;
  status.textContent=selected.length?`${selected.length} tareas mostradas.`:'No hay tareas con estos filtros.';
 }
 async function load(){
  if(!allowed||!dialog.open||busy)return;busy=true;const version=++generation;byId('owner-verification-refresh').disabled=true;status.textContent='Consultando tareas…';
  try{const data=await call('/v1/admin/verification-tasks');if(version!==generation||!allowed||!dialog.open)return;rows=data.tasks;render();}
  catch(error){if(version===generation){if(error.status===401||error.status===403){authorize(false);return;}status.textContent='No se pudo cargar la cola. Comprueba que la base de datos esté migrada y vuelve a intentar.';}}
  finally{if(version===generation){busy=false;byId('owner-verification-refresh').disabled=false;}}
 }
 async function update(row,body){
  if(!allowed||busy)return;busy=true;status.textContent='Guardando evidencia…';
  try{const data=await call('/v1/admin/verification-tasks/'+encodeURIComponent(row.id),{method:'PATCH',body:{revision:row.revision,...body},write:true});rows=rows.map(item=>item.id===row.id?data.task:item);render();status.textContent='Tarea guardada.';}
  catch(error){status.textContent=error.status===409?'La tarea cambió en otra sesión; actualiza la cola.':error.message||'No se pudo guardar la tarea.';}
  finally{busy=false;}
 }
 byId('owner-verification-close').addEventListener('click',()=>dialog.close());
 dialog.addEventListener('close',()=>{generation++;busy=false;list.replaceChildren();status.textContent='';});
 button.addEventListener('click',()=>{if(allowed){dialog.showModal();void load();}});
 byId('owner-verification-refresh').addEventListener('click',()=>void load());filter.addEventListener('change',render);domain.addEventListener('change',render);
 byId('owner-verification-create').addEventListener('submit',async event=>{
  event.preventDefault();if(!allowed||busy)return;const form=event.currentTarget,fd=new FormData(form);
  const title=String(fd.get('title')||'').trim(),slug=title.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'_').replace(/^_|_$/g,'').slice(0,45);
  const body={task_key:'ivania_'+slug+'_'+crypto.randomUUID().slice(0,8).replace(/-/g,''),domain:String(fd.get('domain')),priority:String(fd.get('priority')),title,description:String(fd.get('description')).trim(),source_label:String(fd.get('source_label')).trim(),source_url:String(fd.get('source_url')||'').trim()||null};
  busy=true;status.textContent='Registrando tarea…';
  try{await call('/v1/admin/verification-tasks',{method:'POST',body,write:true});form.reset();busy=false;await load();status.textContent='Tarea agregada como pendiente.';}
  catch(error){status.textContent=error.message||'No se pudo agregar la tarea.';}
  finally{busy=false;}
 });
 window.RioVerificationTasks=Object.freeze({authorize});authorize(window.RioOwnerActivityAllowed===true);
})();
