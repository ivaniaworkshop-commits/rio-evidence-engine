(function(){
'use strict';
var destinations={cuenta:'/',caja:'/caja#cobro-codi',mercado:'/static/unificada/mercado/index.html',operaciones:'/hackaton'};
document.querySelectorAll('a[data-module]').forEach(function(link){
 var key=link.getAttribute('data-module');
 if(destinations[key]!==link.getAttribute('href'))link.removeAttribute('data-module');
});
var panel=document.getElementById('moduleSection');
var status=document.getElementById('entryStatus');
var actions=document.getElementById('entryActions');
var identity=document.getElementById('sessionLabel');
if(!panel||!status||!actions||!identity)return;
function noSession(message){
 panel.hidden=true;actions.hidden=false;status.textContent=message;
}
async function checkSession(){
 var timer;
 try{
  var controller=new AbortController();
  timer=setTimeout(function(){controller.abort()},15000);
  var response=await fetch('/v1/auth/me',{credentials:'same-origin',cache:'no-store',signal:controller.signal,headers:{'Accept':'application/json'}});
  if(response.status===401){noSession('Primero inicia sesión o crea una cuenta.');return;}
  if(!response.ok){noSession('No se pudo comprobar el acceso. Inicia sesión desde la página de cuenta.');return;}
  var data=await response.json();
  if(!data||typeof data.id!=='string'||!data.id){noSession('No se verificó una sesión válida.');return;}
  actions.hidden=true;
  panel.hidden=false;
  status.textContent='Sesión comprobada. Selecciona un módulo.';
  identity.textContent=typeof data.email==='string'?'Sesión: '+data.email:'Sesión iniciada';
 }catch(error){noSession(error.name==='AbortError'
   ?'La comprobación agotó el tiempo de espera. Intenta iniciar sesión.'
   :'No se pudo verificar la sesión. Intenta iniciar sesión.');}
 finally{clearTimeout(timer);}
}
checkSession();
})();
