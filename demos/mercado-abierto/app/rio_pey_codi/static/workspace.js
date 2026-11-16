(() => {
 'use strict';
 const dashboard=document.getElementById('dashboard'),context=document.getElementById('commerce-context');
 const links=[...document.querySelectorAll('[data-workspace-view]')],panels=[...document.querySelectorAll('[data-workspace-panel]')];
 const nav=document.querySelector('.workspace-nav');
 const hashes={'#menu':'menu','#cobro-codi':'caja','#historial':'historial','#mis-negocios':'negocios','#configuracion-pey':'negocios','#negocio':'negocios','#rio-merchant-details':'negocios','#modulos':'menu'};
 let authenticated=false;
 function open(view,update=true){
  if(view==='pey'||view==='negocio')view='negocios';if(view==='modulos')view='menu';
  if(!authenticated||!panels.some(p=>p.dataset.workspacePanel===view))return;
  panels.forEach(p=>p.hidden=p.dataset.workspacePanel!==view);
  context.hidden=view==='menu';nav.hidden=view==='menu';
  dashboard.dataset.currentView=view;
  links.forEach(link=>{if(link.dataset.workspaceView===view)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current')});
  const link=links.find(link=>link.dataset.workspaceView===view);
  if(update&&link)history.replaceState(null,'',location.pathname+location.search+link.hash);
 }
 links.forEach(link=>link.addEventListener('click',event=>{
  event.preventDefault();open(link.dataset.workspaceView);
  const panel=panels.find(p=>p.dataset.workspacePanel===link.dataset.workspaceView);
  const target=panel?.querySelector('h1')||panel?.querySelector('a,button');
  if(target){if(target.tagName==='H1')target.tabIndex=-1;target.focus({preventScroll:true});target.scrollIntoView({block:'nearest'});}
 }));
 window.addEventListener('hashchange',()=>open(hashes[location.hash]||'menu',false));
 document.querySelectorAll('[data-open-activity]').forEach(button=>button.addEventListener('click',()=>document.getElementById('owner-activity-open').click()));
 window.RioWorkspace=Object.freeze({activate(){authenticated=true;dashboard.hidden=false;open(hashes[location.hash]||(location.pathname==='/caja'?'caja':'menu'),false)},open,lock(){authenticated=false;dashboard.hidden=true}});
})();
