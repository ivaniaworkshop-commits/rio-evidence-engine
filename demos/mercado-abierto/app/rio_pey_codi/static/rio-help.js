(() => {
  'use strict';
  const endpoint='/static/rio-help-catalog.json';
  const storageKey='rio-help-progress-v1';
  let catalog=null, active=0, stepIndex=0, marked=null;
  const pageDestinations={
    mis_negocios:['#mis-negocios','Abrir Mis negocios'],caja_codi:['#cobro-codi','Abrir Caja'],
    caja_efectivo:['#cobro-codi','Abrir Caja'],historial:['#historial','Abrir Historial'],
    comprobantes:['#historial','Abrir Historial'],mercado:['/mercado-abierto#catalogo','Abrir Mercado Abierto'],
    whatsapp:['/mercado-abierto#whatsapp','Configurar WhatsApp público'],
    actividad:['#menu','Abrir el menú principal'],auth:['/login','Abrir acceso a la cuenta'],
    general:['#menu','Abrir el menú principal'],seguridad:['#menu','Abrir el menú principal']
  };
  function node(tag, text, parent, cls) {
    const n=document.createElement(tag);
    if(text!==null && text!==undefined)n.textContent=text;
    if(cls)n.className=cls;
    if(parent)parent.appendChild(n);
    return n;
  }
  function init() {
    const anchor=document.querySelector('.workspace-user');
    if(!anchor || document.getElementById('rio-help-open'))return;
    const opener=node('button','Centro de ayuda RÍO',anchor,'outline');
    opener.id='rio-help-open';opener.type='button';
    opener.setAttribute('aria-haspopup','dialog');
    const dialog=node('dialog',null,document.body,'rio-help-dialog');
    dialog.id='rio-help-dialog';dialog.setAttribute('aria-labelledby','rio-help-title');
    const header=node('div',null,dialog,'rio-help-header');
    node('h2','Centro de ayuda RÍO',header).id='rio-help-title';
    const close=node('button','Cerrar',header,'outline');close.type='button';
    const info=node('p','Los tutoriales orientan; no conectan pey, cobran, envían correos ni comprueban liquidaciones bancarias.',dialog,'rio-help-notice');
    const field=node('label','Tutorial',dialog);
    const selection=node('select',null,field);selection.id='rio-help-select';
    const searchLabel=node('label','Buscar tema o pregunta',dialog);
    const searchInput=node('input',null,searchLabel);searchInput.type='search';searchInput.placeholder='Escribe palabras, no datos privados';searchInput.id='rio-help-search';
    const searchButton=node('button','Buscar preguntas y guías',searchLabel,'outline');searchButton.type='button';
    const progress=node('p','',dialog,'rio-help-progress');progress.setAttribute('aria-live','polite');
    const heading=node('h3','',dialog);
    const instruction=node('p','',dialog);
    const req=node('ul',null,dialog);
    const refs=node('div',null,dialog,'rio-help-references');
    const answer=node('section',null,dialog,'rio-help-answer');answer.setAttribute('aria-live','polite');
    const actions=node('div',null,dialog,'rio-help-actions');
    const prev=node('button','Anterior',actions,'outline');
    const point=node('button','Mostrar o enfocar paso',actions,'outline');
    const next=node('button','Siguiente',actions,'outline');
    const check=node('button','Comprobar elemento',actions,'outline');
    const resolve=node('button','Resolver problema relacionado',actions,'outline');
    for(const btn of [prev,point,next,check,resolve])btn.type='button';
    const status=node('p','',dialog);status.id='rio-help-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');
    function normalize(text) {
      return String(text||'').normalize('NFD').replace(/\p{M}/gu,'').toLowerCase();
    }
    function showAnswer(q) {
      answer.replaceChildren();
      node('h4',q.id+' · '+q.texto,answer);
      const list=node('ol',null,answer);
      for(const line of q.respuesta_directa)node('li',line,list);
      node('p','Límite: '+q.limite,answer);
      status.textContent='Respuesta de catálogo; no comprueba operaciones externas ni concede permisos.';
    }
    function persist() {
      try {sessionStorage.setItem(storageKey,JSON.stringify({id:catalog.tutoriales[active].id,step:stepIndex}));} catch (_) {}
    }
    function unmark() {if(marked){marked.classList.remove('rio-help-target');marked=null;}}
    function textReference(label,items) {
      const section=node('div',null,refs);
      node('strong',label,section);
      for(const item of items){
        if(item.url){
          const a=node('a',item.id+' · '+item.titulo,section);
          try {
            const safe=new URL(item.url,location.origin);
            if(safe.protocol!=='https:' || !['rio-pey-codi-gateway.vercel.app','rio-primer-cobro-frontdesk.vercel.app','docs.pey.mx','portal.pey.mx','www.banxico.org.mx','developers.facebook.com'].includes(safe.hostname)){
              a.remove();node('small',' (enlace no autorizado)',section);continue;
            }
            a.href=safe.href;a.target='_blank';a.rel='noopener noreferrer';
          } catch(_) {a.remove();node('small',' (enlace inválido)',section);continue;}
          node('small',' (enlace HTTP no comprobado)',section);
        } else node('p',item.id+' · '+item.texto,section);
      }
    }
    function render() {
      if(!catalog)return;
      const tutorial=catalog.tutoriales[active],s=tutorial.pasos[stepIndex];
      selection.value=tutorial.id;
      progress.textContent=tutorial.id+' · '+tutorial.nivel_automatizacion+' · Paso '+(stepIndex+1)+' de '+tutorial.pasos.length;
      heading.textContent=tutorial.titulo;
      instruction.textContent=s.texto;
      req.replaceChildren();refs.replaceChildren();answer.replaceChildren();
      const lead=node('li','Requisitos: '+tutorial.prerrequisitos.join('; '),req);
      lead.className='rio-help-requisite';
      textReference('Enlaces útiles: ',tutorial.enlaces_utiles);
      textReference('Consejos: ',tutorial.consejos);
      const destination=pageDestinations[tutorial.area]||['#menu','Abrir el menú principal'];
      const page=node('a',destination[1],refs);page.href=destination[0];page.className='rio-help-page-link';
      prev.disabled=stepIndex===0;next.disabled=stepIndex>=tutorial.pasos.length-1;
      point.textContent=s.accion==='enfocar'?'Enfocar campo':'Mostrar paso en pantalla';
      status.textContent='Paso informativo. La aplicación conserva sus controles de autorización.';
      persist();
    }
    function choose(i,step=0){active=i;stepIndex=Math.max(0,Math.min(step,catalog.tutoriales[i].pasos.length-1));unmark();render();}
    function locate(selector) {
      if(!selector)return null;
      try{const target=document.querySelector(selector);
        if(!target||target.closest('[hidden]')||target.hidden)return null;
        return target;
      }catch(_){return null;}
    }
    function showTarget(){
      const s=catalog.tutoriales[active].pasos[stepIndex];
      if(s.auto || !['resaltar','enfocar','prellenar','confirmar_antes'].includes(s.accion)){
        status.textContent='La acción automática está deshabilitada.';return;
      }
      const target=locate(s.selector);
      if(!target){status.textContent='Este paso no tiene un elemento visible comprobado. Realízalo manualmente según la explicación.';return;}
      unmark();dialog.close();marked=target;marked.classList.add('rio-help-target');
      target.scrollIntoView({block:'center',behavior:'auto'});
      if(s.accion==='enfocar'&&typeof target.focus==='function')target.focus({preventScroll:true});
      else if(typeof target.focus==='function'&&(target.matches('a,button,input,select,textarea')))target.focus({preventScroll:true});
    }
    async function open() {
      if(!dialog.open)dialog.showModal();
      if(!catalog){
        status.textContent='Cargando tutoriales…';
        try{
          const response=await fetch(endpoint,{credentials:'same-origin',cache:'no-store'});
          if(!response.ok)throw Error('HTTP '+response.status);
          const base=await response.json();
          if(!Array.isArray(base.preguntas)||base.preguntas.length!==180)throw Error('Índice base incompleto');
          if(!Array.isArray(base.tutoriales)||!base.tutoriales.length||base.tutoriales.some(t=>t.pasos.some(s=>s.auto)))
            throw Error('Catálogo no autorizado');
          const overlayResponse=await fetch('/static/rio-help-product-overlay.json',{credentials:'same-origin',cache:'no-store'});
          if(!overlayResponse.ok)throw Error('Extensión local de ayuda incompleta');
          const overlay=await overlayResponse.json();
          if(!Array.isArray(overlay.preguntas)||!Array.isArray(overlay.tutoriales)||overlay.tutoriales.some(t=>t.pasos.some(s=>s.auto)))
            throw Error('Extensión local no autorizada');
          const questionIds=new Set(base.preguntas.map(q=>q.id));
          if(overlay.preguntas.some(q=>questionIds.has(q.id)||!base.tutoriales.some(t=>t.id===q.tutorial_id)&&!overlay.tutoriales.some(t=>t.id===q.tutorial_id)))
            throw Error('Referencia de pregunta duplicada o inválida');
          const ids=new Set(base.tutoriales.map(t=>t.id));
          if(overlay.tutoriales.some(t=>ids.has(t.id)))throw Error('Identificador de tutorial duplicado');
          catalog={...base,preguntas:[...base.preguntas,...overlay.preguntas],tutoriales:[...base.tutoriales,...overlay.tutoriales]};
          for(const t of catalog.tutoriales){
            const option=node('option',t.id+' · '+t.titulo,selection);option.value=t.id;
          }
          searchButton.textContent='Buscar entre '+catalog.preguntas.length+' preguntas';
          let saved={};
          try{saved=JSON.parse(sessionStorage.getItem(storageKey)||'{}');}catch(_){}
          const idx=catalog.tutoriales.findIndex(t=>t.id===saved.id);
          const view=document.getElementById('dashboard')?.dataset.currentView;
          const suggestion={caja:'T004',negocios:'T003',historial:'T007'}[view];
          const contextual=catalog.tutoriales.findIndex(t=>t.id===suggestion);
          choose(idx>=0?idx:(contextual>=0?contextual:0),idx>=0?Number(saved.step)||0:0);
        }catch(_){status.textContent='No se pudo cargar el catálogo. Revisa tu conexión o informa a soporte.';return;}
      }
    }
    opener.addEventListener('click',open);
    close.addEventListener('click',()=>dialog.close());
    selection.addEventListener('change',()=>{const idx=catalog.tutoriales.findIndex(t=>t.id===selection.value);if(idx>=0)choose(idx);});
    searchButton.addEventListener('click',()=>{
      if(!catalog)return;
      const needle=normalize(searchInput.value).trim();
      if(needle.length<3){status.textContent='Escribe al menos tres caracteres, sin información privada.';return;}
      const words=needle.split(/\s+/).filter(w=>w.length>=3);
      const ranked=catalog.preguntas.map(q=>{
        const title=normalize(q.texto);
        const score=(title.includes(needle)?100:0)+words.reduce((n,w)=>n+(title.includes(w)?1:0),0);
        return {q,score};
      }).filter(x=>x.score>0).sort((a,b)=>b.score-a.score || a.q.id.localeCompare(b.q.id));
      if(!ranked.length){answer.replaceChildren();status.textContent='No hay una pregunta relacionada en este catálogo; consulta soporte sin incluir datos privados.';return;}
      const hit=ranked[0].q;
      if(hit.tutorial_id){const index=catalog.tutoriales.findIndex(t=>t.id===hit.tutorial_id);if(index>=0)choose(index);}
      showAnswer(hit);
      if(ranked.length>1)status.textContent+=' Coincidencia sugerida: revisa que corresponda a tu duda.';
    });
    searchInput.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();searchButton.click();}});
    prev.addEventListener('click',()=>{if(stepIndex>0){stepIndex--;render();}});
    next.addEventListener('click',()=>{if(stepIndex+1<catalog.tutoriales[active].pasos.length){stepIndex++;render();}});
    point.addEventListener('click',showTarget);
    check.addEventListener('click',()=>{
      const t=catalog.tutoriales[active],found=locate(t.verificacion.selector);
      status.textContent=found?'El elemento existe en pantalla. Aún debes comprobar el resultado real: '+t.verificacion.texto:
       'No se observó un elemento verificable en esta vista. '+t.verificacion.texto+' Si falla: '+t.verificacion.si_falla;
    });
    resolve.addEventListener('click',()=>{
      if(!catalog)return;
      const id=catalog.tutoriales[active].verificacion.si_falla;
      const question=catalog.preguntas.find(q=>q.id===id);
      if(question)showAnswer(question);
      else status.textContent='No hay respuesta local para ese incidente.';
    });
    dialog.addEventListener('close',persist);
    document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!dialog.open)unmark();});
    void info;
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);
  else init();
})();
