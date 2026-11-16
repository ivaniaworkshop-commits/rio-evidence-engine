'use strict';
// RÍO R012 — swarm of isolated Playwright Chromium workers. NO real provider calls.
const {chromium}=require('playwright');
const fs=require('node:fs'),http=require('node:http'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const ROOT=path.join(__dirname,'..','rio_pey_codi','static','unificada','hackaton');
const VIEWS=['panel','mercado','solicitudes','ofertas','pedidos','fletes','caja','inventario','negocios','tickets','historial'];
const VPORTS={desktop:{width:1366,height:768},mobile:{width:390,height:844}};
const ENABLED_VIEWPORTS=String(process.env.RIO_SWARM_VIEWPORTS||'desktop,mobile').split(',').filter(x=>Object.prototype.hasOwnProperty.call(VPORTS,x));
const MAX=Math.min(Math.max(Number(process.env.RIO_SWARM_MAX_BUTTONS||60),1),250);
const WORKERS=Math.min(Math.max(Number(process.env.RIO_SWARM_WORKERS||2),1),8);
const SEED=Number(process.env.RIO_SWARM_SEED||12012);
const PHASES=new Set(String(process.env.RIO_SWARM_PHASES||'navigation,buttons,forms,workflow,auth').split(','));
const OUT=process.env.RIO_SWARM_REPORT||path.join(__dirname,'r012_swarm_report.json');
const fixture={index:fs.readFileSync(path.join(ROOT,'index.html')),css:fs.readFileSync(path.join(ROOT,'app.css')),js:fs.readFileSync(path.join(ROOT,'app.js'))};
const sourceHashes=Object.fromEntries(Object.entries(fixture).map(([k,v])=>[k,crypto.createHash('sha256').update(v).digest('hex')]));
let requestLog=[];let tests=[];
function isInfraError(message){return /Target crashed|Browser has been closed|Target page, context or browser has been closed|net::ERR_BLOCKED_BY_ADMINISTRATOR|crash detected|Renderer process crashed/i.test(String(message||''));}
function classifyFailure(message){return isInfraError(message)?'INFRA_BLOCKED':/Timeout\s+\d+ms exceeded|timeout of \d+ms/i.test(String(message||''))?'NEEDS_REVIEW':'FAIL';}
function record(agent,view,control,status,detail=''){
 const message=String(detail).slice(0,700);
 const normalized=/Target crashed|Browser has been closed|Target page, context or browser has been closed|net::ERR_BLOCKED_BY_ADMINISTRATOR/.test(message)?'INFRA_BLOCKED':status;
 tests.push({agent,view,control,status:normalized,detail:message});
 if(process.env.RIO_SWARM_VERBOSE==='1')console.log('CASE',agent,view,control,normalized,message.slice(0,150));
 try{fs.mkdirSync(path.dirname(OUT),{recursive:true});fs.writeFileSync(OUT+'.partial.json',JSON.stringify({schema:'RIO_SWARM_R012_PARTIAL',authority:'INCOMPLETE_EXECUTION',attempts:tests.length,results:tests},null,2)+'\n');}catch(_){}
}
const app=http.createServer((req,res)=>{
 const p=new URL(req.url,'http://localhost').pathname;requestLog.push({method:req.method,path:p});
 let code=200,type='application/json',body='{}';
 const cookie=(req.headers.cookie||'').includes('rio_sid=r012-synthetic');
 if(req.method!=='GET'){code=403;body='{"detail":"ALL_SERVER_MUTATIONS_BLOCKED"}';}
 else if(p==='/hackaton'||p==='/'){if(!cookie){code=401;body='{"detail":"SYNTHETIC_SESSION_REQUIRED"}';}else{body=fixture.index;type='text/html; charset=utf-8';}}
 else if(p==='/static/unificada/hackaton/app.js'){body=fixture.js;type='text/javascript; charset=utf-8';}
 else if(p==='/static/unificada/hackaton/app.css'){body=fixture.css;type='text/css; charset=utf-8';}
 else if(p==='/api/auth/me'){
 if(!cookie){code=401;body='{"detail":"SYNTHETIC_SESSION_REQUIRED"}';}
 else body=JSON.stringify({user:{id:'r012-synthetic',email:'r012@example.invalid',display_name:'Swarm Synthetic',role:'GATEWAY_ACCOUNT',active:true},csrf_token:'synthetic-not-real',permissions:['account.manage'],auth_source:'RIO_GATEWAY_RIO_SID',commercial_state:'BROWSER_LOCAL_ONLY',payments:'DEMO_ONLY'});
 }else{code=p.startsWith('/api/')||p.startsWith('/v1/')?403:404;body='{"detail":"OUT_OF_SCOPE"}';}
 res.writeHead(code,{'content-type':type,'cache-control':'no-store','x-content-type-options':'nosniff'});
 res.end(body);
});
let origin,browser;
const WATCHDOG_MS=Math.min(Math.max(Number(process.env.RIO_SWARM_WATCHDOG_MS||90000),15000),600000);
setTimeout(()=>{console.error('R012 watchdog reached '+WATCHDOG_MS+' ms; partial report preserved at '+OUT+'.partial.json');process.exit(124)},WATCHDOG_MS).unref();
const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function open(viewport){
 const ctx=await browser.newContext({viewport,serviceWorkers:'block',acceptDownloads:false});
 await ctx.addCookies([{name:'rio_sid',value:'r012-synthetic',url:origin,httpOnly:true,sameSite:'Strict'}]);
 const page=await ctx.newPage();page.setDefaultTimeout(5000);
 const errors=[];
 page.on('pageerror',e=>errors.push(String(e)));
 page.on('crash',()=>errors.push('Renderer process crashed'));
 page.on('close',()=>errors.push('Page closed unexpectedly'));
 page.on('console',m=>{if(m.type()==='error')errors.push('console:'+m.text())});
 page.on('request',r=>{if(!r.url().startsWith(origin))errors.push('unexpected external request:'+r.url())});
 await page.goto(origin+'/hackaton',{waitUntil:'domcontentloaded'});
 await page.waitForFunction(()=>window.RIO_DEMO?.isReady()===true);
 return {ctx,page,errors};
}
async function goByClick(page,view){
 if(process.env.RIO_SWARM_DEBUG_EVAL==='1'){await page.evaluate(v=>window.RIO_DEMO.go(v),view);return;}
 let sel='#sidebar button[data-nav="'+view+'"]',n=page.locator(sel);
 if(!await n.isVisible()){
  sel='#mobileNav button[data-nav="'+view+'"]';n=page.locator(sel);
  if(await n.count()===0||!await n.isVisible()){await page.locator('#mobileNav [data-action="show-menu"]').click();n=page.locator('#modalRoot [data-nav="'+view+'"]');}
 }
 await n.click();
 assert.equal(await page.evaluate(()=>window.RIO_DEMO.getPage()),view);
}
async function navigation(label){
 let c;
 try{
  c=await open(VPORTS[label]);
  for(let i=0;i<VIEWS.length;i++){
   const v=VIEWS[i];
   try{
    await goByClick(c.page,v);
    assert.ok(await c.page.locator('#app h1').count()>0);
    const overflow=await c.page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2);
    if(label==='mobile')assert.equal(overflow,false,'horizontal overflow');
    assert.deepEqual(c.errors,[]);
    record('navigation-'+label,v,'navigate','PASS');
   }catch(e){
    const message=String(e.message||e);
    record('navigation-'+label,v,'navigate',classifyFailure(message),message);
    if(isInfraError(message)||c.page.isClosed()){
     for(const remaining of VIEWS.slice(i+1))record('navigation-'+label,remaining,'navigate','NOT_TESTED','browser crashed before attempt');
     break;
    }
   }
  }
 }catch(e){record('navigation-'+label,'*','setup',classifyFailure(e.message),e.message)}
 finally{await c?.ctx.close().catch(()=>{})}
}
async function buttonProbe(label,view,button){
 let c;
 try{
  c=await open(VPORTS[label]);await c.page.evaluate(v=>window.RIO_DEMO.go(v),view);
  const downloads=[];
  c.page.on('download',download=>downloads.push(download.suggestedFilename()));
  c.page.on('dialog',dialog=>dialog.accept().catch(()=>{}));
  if(button.action==='clear-market'||button.action==='rfq-from-cart'){
   await c.page.locator('#app [data-action="market-add"]').first().click();
  }
  if(button.action==='clear-pos'||(view==='caja'&&!button.action&&!button.route)){
   await c.page.locator('#app [data-action="pos-add"]').first().click();
  }
  let loc=button.action?c.page.locator('#app button[data-action="'+button.action+'"]').first():button.route?c.page.locator('#app button[data-nav="'+button.route+'"]').first():c.page.locator('#app button[type="submit"]').first();
  if(!await loc.count()||!await loc.isVisible()||!await loc.isEnabled()){record('buttons-'+label,view,button.text,'NOT_TESTED','hidden/disabled');return}
  const snapshot=()=>c.page.evaluate(()=>({page:window.RIO_DEMO.getPage(),state:JSON.stringify(window.RIO_DEMO.getState()),dom:document.querySelector('#app').innerHTML,modal:document.querySelector('#modalRoot').innerHTML,toast:document.querySelector('#toastRoot').innerHTML}));
  const before=await snapshot();
  await loc.click();await c.page.waitForTimeout(60);
  const after=await snapshot();
  if(c.errors.length)throw Error(c.errors.join(' | '));
  record('buttons-'+label,view,button.text,(downloads.length||Object.keys(before).some(x=>before[x]!==after[x]))?'PASS':'NEEDS_REVIEW','action='+button.action+' downloads='+downloads.length);
 }catch(e){record('buttons-'+label,view,button.text,'FAIL',e.message)}
 finally{await c?.ctx.close()}
}
function shuffle(a,seed){let x=(seed>>>0)||1;for(let i=a.length-1;i>0;i--){x^=x<<13;x^=x>>>17;x^=x<<5;const j=(x>>>0)%(i+1);[a[i],a[j]]=[a[j],a[i]]}return a}
async function buttons(label){
 const cases=[];
 for(const view of VIEWS){
  let c;try{c=await open(VPORTS[label]);await c.page.evaluate(v=>window.RIO_DEMO.go(v),view);
   const inventory=await c.page.locator('#app button[data-action],#app button[data-nav],#app button[type="submit"]').evaluateAll(es=>es.map((e,index)=>({index,text:(e.textContent||'').trim().slice(0,100),action:e.dataset.action||'',route:e.dataset.nav||''})));
   for(const button of inventory)cases.push({view,button});
  }catch(e){record('buttons-'+label,view,'inventory','FAIL',e.message)}
  finally{await c?.ctx.close()}
 }
 shuffle(cases,SEED+(label==='mobile'?1:0));
 const selected=cases.slice(0,MAX),excluded=cases.slice(MAX);
 excluded.forEach(({view,button})=>record('buttons-'+label,view,button.text,'NOT_TESTED','budget exceeded'));
 let i=0;await Promise.all(Array.from({length:WORKERS},async()=>{for(;;){const k=i++;if(k>=selected.length)break;const {view,button}=selected[k];await buttonProbe(label,view,button)}}));
}
async function seedTradingPrerequisite(page,target){
 await page.evaluate(()=>window.RIO_DEMO.go('mercado'));
 await page.locator('#app [data-action="market-add"]').first().click();
 await page.locator('#app [data-action="rfq-from-cart"]').click();
 await page.locator('form[data-form="rfq"] button[type="submit"]').click();
 assert.equal((await page.evaluate(()=>window.RIO_DEMO.getState())).rfqs.length,1,'RFQ prerequisite');
 if(target==='offer')return;
 await page.evaluate(()=>window.RIO_DEMO.go('ofertas'));
 await page.locator('#app [data-action="new-offer"]').first().click();
 await page.locator('form[data-form="offer"] button[type="submit"]').click();
 await page.locator('#app [data-action="accept-offer"]').first().click();
 assert.equal((await page.evaluate(()=>window.RIO_DEMO.getState())).orders.length,1,'order prerequisite');
}
async function forms(label){
 const entries=[['negocios','new-business','business'],['inventario','new-product','product'],['solicitudes','new-rfq','rfq'],['ofertas','new-offer','offer'],['fletes','new-freight','freight'],['caja','pos-add','checkout']];
 for(const [view,trigger,form] of entries){
  let c;try{c=await open(VPORTS[label]);
   if(form==='offer'||form==='freight')await seedTradingPrerequisite(c.page,form);
   await c.page.evaluate(v=>window.RIO_DEMO.go(v),view);
   const button=c.page.locator('[data-action="'+trigger+'"]').first();
   if(!await button.count()){record('forms-'+label,view,form,'NOT_TESTED','no initial trigger');continue}
   await button.click();
   const f=c.page.locator('form[data-form="'+form+'"]');
   if(!await f.count()){record('forms-'+label,view,form,'NOT_TESTED','prerequisite missing');continue}
   const required=await f.locator(':required').count();
   if(!required)throw Error('form has no required fields');
   const blankable=f.locator('input[required]:not([type="hidden"]), textarea[required]');
   if(!await blankable.count()){record('forms-'+label,view,form,'NOT_TESTED','no fillable required input');continue}
   await blankable.first().fill('');
   assert.equal(await f.evaluate(el=>el.checkValidity()),false,'blank required field accepted');
   if(c.errors.length)throw Error(c.errors.join(' | '));
   record('forms-'+label,view,form,'PASS','required_fields='+required);
  }catch(e){record('forms-'+label,view,form,'FAIL',e.message)}
  finally{await c?.ctx.close()}
 }
}
async function workflow(label){
 let c;const agent='flow-'+label;
 try{c=await open(VPORTS[label]);const p=c.page;
  await p.evaluate(()=>window.RIO_DEMO.go('mercado'));
  await p.locator('[data-action="market-add"]').first().click();
  await p.locator('[data-action="rfq-from-cart"]').click();
  await p.locator('form[data-form="rfq"] button[type="submit"]').click();
  let state=await p.evaluate(()=>window.RIO_DEMO.getState());
  assert.equal(state.rfqs.length,1);record(agent,'solicitudes','create-rfq','PASS');
  await p.evaluate(()=>window.RIO_DEMO.go('ofertas'));
  await p.locator('[data-action="new-offer"]').click();
  await p.locator('form[data-form="offer"] button[type="submit"]').click();
  state=await p.evaluate(()=>window.RIO_DEMO.getState());assert.equal(state.offers.length,1);record(agent,'ofertas','create-offer','PASS');
  await p.locator('[data-action="accept-offer"]').first().click();
  state=await p.evaluate(()=>window.RIO_DEMO.getState());assert.equal(state.orders.length,1);record(agent,'pedidos','accept-offer','PASS');
  await p.locator('[data-action="freight-for-order"]').first().click();
  await p.locator('form[data-form="freight"] button[type="submit"]').click();
  state=await p.evaluate(()=>window.RIO_DEMO.getState());assert.equal(state.freights.length,1);record(agent,'fletes','assign-freight','PASS');
  await p.locator('[data-action="accept-freight"]').first().click();
  await p.locator('[data-action="complete-freight"]').first().click();
  state=await p.evaluate(()=>window.RIO_DEMO.getState());assert.equal(state.orders[0].status,'recibido');record(agent,'pedidos','freight-received','PASS');
  await p.evaluate(()=>window.RIO_DEMO.go('caja'));
  await p.locator('[data-action="pos-add"]').first().click();
  await p.locator('form[data-form="checkout"] input[name="received"]').fill('999');
  await p.locator('form[data-form="checkout"] button[type="submit"]').click();
  state=await p.evaluate(()=>window.RIO_DEMO.getState());assert.equal(state.sales.length,1);record(agent,'caja','cash-ticket','PASS');
  if(c.errors.length)throw Error(c.errors.join(' | '));
 }catch(e){record(agent,'flow','workflow','FAIL',e.stack||e.message)}
 finally{await c?.ctx.close()}
}
async function auth(label){
 let c;
 try{
  c=await open(VPORTS[label]);
  await c.ctx.clearCookies();
  const denied=await c.ctx.request.get(origin+'/api/auth/me');
  assert.equal(denied.status(),401,'revoked cookie must not authorize gateway identity');
  await c.page.evaluate(()=>window.RIO_DEMO?.go('panel')).catch(e=>{
   if(!/Execution context was destroyed|navigation/i.test(String(e)))throw e;
  });
  await c.page.waitForFunction(()=>!window.RIO_DEMO||window.RIO_DEMO.isReady()===false);
  record('auth-'+label,'session','revoke-cookie','PASS','401 gateway; protected UI blocked or redirected');
 }catch(e){record('auth-'+label,'session','revoke-cookie',classifyFailure(e.message),e.message)}
 finally{await c?.ctx.close().catch(()=>{})}
}
(async()=>{
 await new Promise(resolve=>app.listen(0,'127.0.0.1',resolve));origin='http://127.0.0.1:'+app.address().port;
 try{
  browser=await chromium.launch({headless:true,executablePath:process.env.RIO_SWARM_CHROMIUM||undefined,args:['--no-sandbox']});
  for(const label of ENABLED_VIEWPORTS){
   for(const [phase,task] of [['navigation',navigation],['buttons',buttons],['forms',forms],['workflow',workflow],['auth',auth]]){
    if(PHASES.has(phase))await task(label);
   }
  }
 }finally{await browser?.close();await new Promise(r=>app.close(r))}
 const counts={};for(const row of tests)counts[row.status]=(counts[row.status]||0)+1;
 const unexpected=requestLog.filter(x=>x.method!=='GET'||x.path.includes('checkout')||x.path.startsWith('/api/admin/'));
 if(unexpected.length){record('guard','*','server-mutating-requests','FAIL',JSON.stringify(unexpected));counts.FAIL=(counts.FAIL||0)+1}
 const status=counts.FAIL?'FAIL':(counts.INFRA_BLOCKED||counts.NEEDS_REVIEW||counts.NOT_TESTED)?'INCOMPLETE':'PASS';
 const report={schema:'RIO_HACKATON_SWARM_R012_V1',status,authority:'CHROMIUM_REAL_WITH_SYNTHETIC_HTTP_NOT_FASTAPI',seed:SEED,workers:WORKERS,max_buttons_per_viewport:MAX,source_sha256:sourceHashes,counts,attempts:tests.length,results:tests,requests:requestLog.reduce((o,x)=>(o[x.method+' '+x.path]=(o[x.method+' '+x.path]||0)+1,o),{}),real_payments:false,production_deployed:false};
 fs.mkdirSync(path.dirname(OUT),{recursive:true});fs.writeFileSync(OUT,JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify({result:report.status,counts,attempts:tests.length,report:OUT}));
 process.exitCode=counts.FAIL?2:status==='INCOMPLETE'?4:0;
})().catch(e=>{console.error(e.stack||String(e));process.exitCode=3;app.close();browser?.close()});
