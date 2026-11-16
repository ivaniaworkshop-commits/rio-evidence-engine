'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'../rio_pey_codi/static');
const landing=fs.readFileSync(path.join(root,'unificada/index.html'),'utf8');
const account=fs.readFileSync(path.join(root,'index.html'),'utf8');
const landingJs=fs.readFileSync(path.join(root,'unificada/shell.js'),'utf8');
const landingCss=fs.readFileSync(path.join(root,'unificada/shell.css'),'utf8');
const accountCss=fs.readFileSync(path.join(root,'unificada/unificada.css'),'utf8');
const reports=[];
async function check(name,fn){await fn();reports.push({case:name,result:'PASS'});console.log('PASS',name)}
function element(attributes={}){return{hidden:false,textContent:'',attributes,getAttribute(k){return this.attributes[k]},removeAttribute(k){delete this.attributes[k]}}}
async function boot(response,expected){
 const panel=element(),status=element(),actions=element(),identity=element();
 panel.hidden=true;
 const links=[
   element({'data-module':'cuenta',href:'/'}),
   element({'data-module':'caja',href:'/static/unificada/caja/index.html'}),
   element({'data-module':'mercado',href:'/static/unificada/mercado/index.html'}),
   element({'data-module':'operaciones',href:'/hackaton'}),
   element({'data-module':'bad',href:'https://example.invalid'})
 ];
 const ids={moduleSection:panel,entryStatus:status,entryActions:actions,sessionLabel:identity};
 const calls=[];
 const fetch=async(url,options)=>{calls.push({url,options});if(response instanceof Error)throw response;return response};
 vm.runInNewContext(landingJs,{document:{querySelectorAll:()=>links,getElementById:id=>ids[id]||null},fetch,AbortController:global.AbortController,setTimeout,clearTimeout,console});
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(calls.length,1);
 assert.equal(calls[0].url,'/v1/auth/me');
 assert.equal(calls[0].options.credentials,'same-origin');
 assert.equal(calls[0].options.cache,'no-store');
 assert.equal(links[4].attributes['data-module'],undefined);
 assert.equal(panel.hidden,expected);
 return {panel,status,actions,identity};
}
(async()=>{
 await check('landing shows login before module panel',()=>{
  assert(landing.indexOf('id="entryActions"')<landing.indexOf('id="moduleSection"'));
  assert(landing.includes('id="moduleSection"')&&landing.includes('hidden'));
  assert.equal((landing.match(/class="module module-/g)||[]).length,4);
 });
 await check('all four module destinations are distinct and accessible',()=>{
  const links=[...landing.matchAll(/<a class="module module-[^"]+" href="([^"]+)" data-module="([^"]+)">/g)];
  assert.equal(links.length,4);
  assert.equal(new Set(links.map(x=>x[1])).size,4);
  assert.deepEqual(links.map(x=>x[2]),['cuenta','caja','mercado','operaciones']);
  assert(landing.includes('aria-label="Elegir módulo comercial"'));
  assert(landing.includes('href="#contenido"'));
 });
 await check('account login precedes account setup',()=>{
  assert(account.indexOf('id="access"')<account.indexOf('id="pey-setup"'));
  assert(account.indexOf('id="access"')<account.indexOf('id="local-cash-title"'));
  assert(account.indexOf('id="dashboard" hidden')<account.indexOf('class="rio-module-section"'));
  assert.equal((account.match(/class="rio-module-button rio-module-/g)||[]).length,4);
  assert(account.includes('id="login"')&&account.includes('id="signup"'));
  assert(account.includes('id="charge"')&&account.includes('id="merchant"'));
 });
 await check('interactive targets, focus visibility and responsive layout',()=>{
  assert(landingCss.includes('#moduleSection .module:')===false || landingCss.includes('.module:focus-visible'));
  assert(landingCss.includes('.entry-actions a:focus-visible,.module:focus-visible'));
  assert(landingCss.includes('[hidden]{display:none!important}'));
  assert(landingCss.includes('grid-template-columns:1fr'));
  assert(accountCss.includes('.rio-module-button:focus-visible'));
  assert(accountCss.includes('min-height:116px'));
 });
 await check('401 keeps modules hidden and shows login',async()=>{
  const {panel,actions}=await boot({status:401,ok:false},true);
  assert.equal(panel.hidden,true);assert.equal(actions.hidden,false);
 });
 await check('5xx keeps modules hidden and shows login',async()=>{
  const {panel,actions}=await boot({status:503,ok:false},true);
  assert.equal(panel.hidden,true);assert.equal(actions.hidden,false);
 });
 await check('network failure keeps modules hidden',async()=>{
  const {panel,actions}=await boot(new Error('network'),true);
  assert.equal(panel.hidden,true);assert.equal(actions.hidden,false);
 });
 await check('200 without account id does not authorize modules',async()=>{
  const {panel,actions}=await boot({status:200,ok:true,json:async()=>({})},true);
  assert.equal(panel.hidden,true);assert.equal(actions.hidden,false);
 });
 await check('valid session exposes four module links',async()=>{
  const {panel,actions,identity}=await boot({status:200,ok:true,json:async()=>({id:'u_valid',email:'merchant@example.test'})},false);
  assert.equal(panel.hidden,false);assert.equal(actions.hidden,true);
  assert(identity.textContent.includes('merchant@example.test'));
 });
 console.log(JSON.stringify({schema:'RIO_R023_UI_NAVIGATION_TEST',passed:reports.length,failed:0,results:reports}));
})().catch(error=>{console.error(error.stack);process.exit(1)});
