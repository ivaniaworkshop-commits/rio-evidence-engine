'use strict';
// R015 — one E2E process: real FastAPI+AccountService+SQLite and Chromium browsers.
// No synthetic HTTP responses; NO live payments, email delivery or production calls.
const { chromium }=require('playwright');
const { spawn }=require('node:child_process');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),net=require('node:net');
const crypto=require('node:crypto'),assert=require('node:assert/strict');

const SHARED=path.join(__dirname,'r015_fastapi_fixture.py');
const PY=process.env.RIO_R015_PYTHON||'python3';
const EXE=process.env.RIO_R015_CHROMIUM||undefined;
const SECRET=crypto.randomBytes(32).toString('hex');
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'rio-r015-'));
const report=process.env.RIO_R015_REPORT||path.join(temp,'evidence.json');
const outcomes=[],errors=[],requests=[];
let child,browser,base;
const check=(name,fn)=>async()=>{try{await fn();outcomes.push({case:name,result:'PASS'})}catch(e){outcomes.push({case:name,result:'FAIL',error:String(e.stack||e).slice(0,1200)});throw e}};
const port=()=>new Promise((resolve,reject)=>{let server=net.createServer();server.once('error',reject);server.listen(0,'127.0.0.1',()=>{let p=server.address().port;server.close(()=>resolve(p))})});
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function ready(){for(let i=0;i<130;i++){if(child.exitCode!==null)throw Error('FastAPI exited: '+child.exitCode);try{const r=await fetch(base+'/api/auth/me');if(r.status===401)return}catch(_){ }await delay(100)}throw Error('FastAPI readiness timeout')}
async function register(context,email,business){
 const api=context.request;const signup=await api.post(base+'/v1/auth/signup',{data:{email,password:'Synthetic-R015-Password-2026',business_name:business}});
 assert.equal(signup.status(),201,'signup: '+(await signup.text()).slice(0,350));
 const tok=await api.get(base+'/__rio_r015/verification-token',{headers:{'X-RIO-Fixture-Key':SECRET}});
 assert.equal(tok.status(),200);
 const token=(await tok.json()).token;
 const verify=await api.post(base+'/v1/auth/verify-email',{data:{token}});
 assert.equal(verify.status(),200,'verify: '+await verify.text());
 const login=await api.post(base+'/v1/auth/login',{data:{email,password:'Synthetic-R015-Password-2026'}});
 assert.equal(login.status(),200,'login: '+await login.text());
 const identity=await api.get(base+'/api/auth/me');
 assert.equal(identity.status(),200);
 assert.equal((await identity.json()).user.email,email);
 return {csrf:(await login.json()).csrf_token,id:(await identity.json()).user.id};
}
async function go(page,view,device){
 const side=page.locator('#sidebar button[data-nav="'+view+'"]');
 if(await side.isVisible())await side.click();
 else{
  const mobile=page.locator('#mobileNav button[data-nav="'+view+'"]');
  if(await mobile.isVisible())await mobile.click();
  else{await page.locator('#mobileNav [data-action="show-menu"]').click();await page.locator('#modalRoot [data-nav="'+view+'"]').click()}
 }
 assert.equal(await page.evaluate(()=>window.RIO_DEMO.getPage()),view,device+' view '+view);
}
const VIEWS=['panel','mercado','solicitudes','ofertas','pedidos','fletes','caja','inventario','negocios','tickets','historial'];
async function commercialReadback(context,page,tag){
 const expected=await page.evaluate(()=>{
  const s=window.RIO_DEMO.getState();
  return Object.fromEntries(['rfqs','offers','orders','freights','sales'].map(key=>[key,s[key].map(x=>x.id)]));
 });
 const deadline=Date.now()+15000;
 let last;
 do{
  const response=await context.request.get(base+'/api/hackaton/commercial-state');
  assert.equal(response.status(),200);
  last=await response.json();
  if(last.revision>0&&last.state&&Object.entries(expected).every(([key,ids])=>JSON.stringify(last.state[key].map(x=>x.id))===JSON.stringify(ids)))break;
  await delay(120);
 }while(Date.now()<deadline);
 assert(last.state,'backend did not persist '+tag);
 assert(Object.entries(expected).every(([key,ids])=>JSON.stringify(last.state[key].map(x=>x.id))===JSON.stringify(ids)),'backend mismatch '+tag);
 await page.evaluate(()=>localStorage.clear());
 await page.reload({waitUntil:'domcontentloaded'});
 await page.waitForFunction(()=>window.RIO_DEMO?.isReady()===true);
 const restored=await page.evaluate(()=>{
  const s=window.RIO_DEMO.getState();
  return Object.fromEntries(['rfqs','offers','orders','freights','sales'].map(key=>[key,s[key].map(x=>x.id)]));
 });
 assert.deepEqual(restored,expected,'backend reload mismatch '+tag);
 return last.revision;
}
async function flow(page,device){
 await go(page,'mercado',device);
 await page.locator('#app [data-action="market-add"]').first().click();
 await page.locator('#app [data-action="rfq-from-cart"]').click();
 await page.locator('form[data-form="rfq"] button[type="submit"]').click();
 assert.equal((await page.evaluate(()=>window.RIO_DEMO.getState())).rfqs.length,1);
 await go(page,'ofertas',device);
 await page.locator('#app [data-action="new-offer"]').click();
 await page.locator('form[data-form="offer"] button[type="submit"]').click();
 assert.equal((await page.evaluate(()=>window.RIO_DEMO.getState())).offers.length,1);
 await page.locator('#app [data-action="accept-offer"]').first().click();
 assert.equal((await page.evaluate(()=>window.RIO_DEMO.getState())).orders.length,1);
 await page.locator('#app [data-action="freight-for-order"]').first().click();
 await page.locator('form[data-form="freight"] button[type="submit"]').click();
 assert.equal((await page.evaluate(()=>window.RIO_DEMO.getState())).freights.length,1);
 await page.locator('#app [data-action="accept-freight"]').first().click();
 await page.locator('#app [data-action="complete-freight"]').first().click();
 assert.equal((await page.evaluate(()=>window.RIO_DEMO.getState())).orders[0].status,'recibido');
 await go(page,'caja',device);
 await page.locator('#app [data-action="pos-add"]').first().click();
 await page.locator('form[data-form="checkout"] input[name="received"]').fill('999');
 await page.locator('form[data-form="checkout"] button[type="submit"]').click();
 assert.equal((await page.evaluate(()=>window.RIO_DEMO.getState())).sales.length,1);
}
(async()=>{
 let failures=0;
 try{
  const p=await port();base='http://127.0.0.1:'+p;
  child=spawn(PY,[SHARED,'--port',String(p),'--db',path.join(temp,'r015.sqlite')],{cwd:path.join(__dirname,'..'),env:{...process.env,RIO_R015_FIXTURE_KEY:SECRET,PYTHONPATH:path.join(__dirname,'..')},stdio:['ignore','ignore','pipe']});
  let stderr='';child.stderr.on('data',x=>{stderr+=String(x).slice(-3000)});
  await ready();
  browser=await chromium.launch({headless:true,executablePath:EXE,args:['--no-sandbox']});
  const a=await browser.newContext({viewport:{width:1366,height:768},acceptDownloads:false});
  const b=await browser.newContext({viewport:{width:390,height:844},acceptDownloads:false});
  for(const c of [a,b])c.on('page',page=>{
   page.on('pageerror',e=>errors.push(String(e)));
   page.on('request',req=>requests.push({url:req.url(),method:req.method()}));
  });
  const au=await register(a,'r015-a@example.org','Synthetic Business A');
  const bu=await register(b,'r015-b@example.org','Synthetic Business B');
  assert.notEqual(au.id,bu.id);
  const pa=await a.newPage(),pb=await b.newPage();
  await pa.goto(base+'/hackaton');await pb.goto(base+'/hackaton');
  await pa.waitForFunction(()=>window.RIO_DEMO?.isReady()===true);
  await pb.waitForFunction(()=>window.RIO_DEMO?.isReady()===true);
  await check('11 desktop clicks with real authenticated gateway',async()=>{for(const v of VIEWS)await go(pa,v,'desktop')})();
  await check('11 mobile clicks with real authenticated gateway',async()=>{for(const v of VIEWS)await go(pb,v,'mobile')})();
  await check('desktop complete trading workflow via buttons',async()=>flow(pa,'desktop'))();
  await check('mobile second account has isolated local commercial state',async()=>{
    let s=await pb.evaluate(()=>window.RIO_DEMO.getState());
    assert.equal(s.rfqs.length,0);assert.equal(s.orders.length,0);assert.equal(s.sales.length,0);
  })();
  await check('mobile complete independent trading workflow',async()=>flow(pb,'mobile'))();
  await check('desktop backend commit and reload without localStorage',async()=>{assert((await commercialReadback(a,pa,'desktop'))>=1)})();
  await check('mobile backend commit and reload without localStorage',async()=>{assert((await commercialReadback(b,pb,'mobile'))>=1)})();
  await check('browser account isolation after server-backed reload',async()=>{
   const ra=await a.request.get(base+'/api/hackaton/commercial-state'),rb=await b.request.get(base+'/api/hackaton/commercial-state');
   assert.equal(ra.status(),200);assert.equal(rb.status(),200);
   const aa=await ra.json(),bb=await rb.json();
   for(const key of ['rfqs','offers','orders','freights','sales']){
    assert.equal(aa.state[key].length,1);
    assert.equal(bb.state[key].length,1);
    assert.notEqual(aa.state[key][0].id,bb.state[key][0].id);
   }
  })();
  await check('failed PUT retains local draft and explicit recovery restores server data',async()=>{
   const baseline=await (await a.request.get(base+'/api/hackaton/commercial-state')).json();
   await pa.route('**/api/hackaton/commercial-state',async route=>{
    if(route.request().method()==='PUT')await route.fulfill({status:503,contentType:'application/json',body:'{"detail":"R017_TEST_NETWORK_FAILURE"}'});
    else await route.continue();
   });
   await go(pa,'mercado','desktop');
   await pa.locator('#app [data-action="market-add"]').first().click();
   await pa.locator('#app [data-action="rfq-from-cart"]').click();
   await pa.locator('form[data-form="rfq"] button[type="submit"]').click();
   await pa.waitForFunction(()=>window.RIO_DEMO?.isReady()===false);
   const draft=await pa.evaluate(()=>{
     const key=Object.keys(localStorage).find(x=>x.startsWith('rio_hackaton_pending_r017_'));
     return key?JSON.parse(localStorage.getItem(key)):null;
   });
   assert(draft,'pending draft must survive failed server PUT');
   assert.equal(draft.baseRevision,baseline.revision);
   assert.equal(draft.state.rfqs.length,2);
   assert.equal((await (await a.request.get(base+'/api/hackaton/commercial-state')).json()).revision,baseline.revision);
   await pa.unroute('**/api/hackaton/commercial-state');
   await pa.reload({waitUntil:'domcontentloaded'});
   await pa.waitForFunction(()=>window.RIO_DEMO?.isReady()===true);
   assert.equal(await pa.locator('#modalRoot [data-action="recover-draft"]').count(),1);
   await pa.locator('#modalRoot [data-action="recover-draft"]').click();
   let current;
   for(let i=0;i<90;i++){
     current=await (await a.request.get(base+'/api/hackaton/commercial-state')).json();
     if(current.revision===baseline.revision+1&&current.state.rfqs.length===2)break;
     await delay(100);
   }
   assert.equal(current.revision,baseline.revision+1);
   assert.equal(current.state.rfqs.length,2);
   await pa.evaluate(()=>localStorage.clear());
   await pa.reload();
   await pa.waitForFunction(()=>window.RIO_DEMO?.isReady()===true);
   assert.equal((await pa.evaluate(()=>window.RIO_DEMO.getState())).rfqs.length,2);
  })();
  await check('concurrent remote change blocks draft overwrite and permits discard',async()=>{
   const baseline=await (await a.request.get(base+'/api/hackaton/commercial-state')).json();
   await pa.route('**/api/hackaton/commercial-state',async route=>{
    if(route.request().method()==='PUT')await route.fulfill({status:503,contentType:'application/json',body:'{"detail":"R017_TEST_NETWORK_FAILURE"}'});
    else await route.continue();
   });
   await go(pa,'mercado','desktop');
   await pa.locator('#app [data-action="market-add"]').first().click();
   await pa.locator('#app [data-action="rfq-from-cart"]').click();
   await pa.locator('form[data-form="rfq"] button[type="submit"]').click();
   await pa.waitForFunction(()=>window.RIO_DEMO?.isReady()===false);
   const response=await a.request.put(base+'/api/hackaton/commercial-state',
     {headers:{'X-CSRF-Token':au.csrf},data:{revision:baseline.revision,state:baseline.state}});
   assert.equal(response.status(),200);
   await pa.unroute('**/api/hackaton/commercial-state');
   await pa.reload();
   await pa.waitForFunction(()=>window.RIO_DEMO?.isReady()===true);
   assert.equal(await pa.locator('#modalRoot [data-action="recover-draft"]').count(),0);
   assert.equal(await pa.locator('#modalRoot [data-action="export-draft"]').count(),1);
   pa.once('dialog',dialog=>dialog.accept());
   await pa.locator('#modalRoot [data-action="discard-draft"]').click();
   assert.equal(await pa.locator('#modalRoot [data-action="discard-draft"]').count(),0);
   const finalState=await (await a.request.get(base+'/api/hackaton/commercial-state')).json();
   assert.equal(finalState.revision,baseline.revision+1);
   assert.equal(finalState.state.rfqs.length,2,'conflicting local draft must not mutate server');
  })();
  await check('backend distinct tenant merchants',async()=>{
   const ra=await a.request.get(base+'/v1/merchants'),rb=await b.request.get(base+'/v1/merchants');
   assert.equal(ra.status(),200);assert.equal(rb.status(),200);
   const aa=new Set((await ra.json()).merchants.map(x=>x.id));
   const bb=(await rb.json()).merchants.map(x=>x.id);
   assert(aa.size);assert(bb.length);assert(bb.every(id=>!aa.has(id)));
  })();
  await check('cross-CSRF logout rejected',async()=>{
    let res=await a.request.post(base+'/api/auth/logout',{headers:{'X-CSRF-Token':bu.csrf},data:{}});
    assert.equal(res.status(),403);
    assert.equal((await a.request.get(base+'/api/auth/me')).status(),200);
  })();
  await check('real R003 admin remains denied',async()=>{
    assert.equal((await a.request.get(base+'/api/admin/dashboard')).status(),403);
    assert.equal((await b.request.get(base+'/api/admin/dashboard')).status(),403);
  })();
  await check('independent logout revokes A but retains B',async()=>{
    let res=await a.request.post(base+'/api/auth/logout',{headers:{'X-CSRF-Token':au.csrf},data:{}});
    assert.equal(res.status(),200);
    assert.equal((await a.request.get(base+'/api/auth/me')).status(),401);
    assert.equal((await a.request.get(base+'/hackaton')).status(),401);
    assert.equal((await b.request.get(base+'/api/auth/me')).status(),200);
    assert.equal((await b.request.get(base+'/hackaton')).status(),200);
  })();
  const external=requests.filter(r=>!r.url.startsWith(base));
  const live=requests.filter(r=>/\/v1\/checkout\/|\/api\/admin\/.*(?:POST|PATCH|DELETE)/.test(r.url));
  assert.deepEqual(external,[],'browser must never call external endpoints');
  assert.deepEqual(live,[],'browser must never call checkout endpoints');
  assert.deepEqual(errors,[],'no browser JS errors');
 }catch(e){failures++;errors.push('FATAL:'+String(e.stack||e).slice(0,2400))}
 finally{
  if(browser)await browser.close().catch(()=>{});
  if(child){child.kill('SIGTERM');await Promise.race([new Promise(r=>child.once('exit',r)),delay(1000)])}
  const data={schema:'RIO_HACKATON_R017_DRAFT_RECOVERY_E2E_V1',mode:'DEMO',authority:'REAL_FASTAPI_AND_REAL_CHROMIUM_SYNTHETIC_ACCOUNTS',origin:'LOOPBACK_ONLY',results:outcomes,errors,requests:{count:requests.length,external:requests.filter(r=>!r.url.startsWith(base)).length,checkout:requests.filter(r=>r.url.includes('/v1/checkout/')).length},live_payments:false,production:false};
  fs.mkdirSync(path.dirname(report),{recursive:true});fs.writeFileSync(report,JSON.stringify(data,null,2)+'\n');
  console.log(JSON.stringify({status:errors.length||failures?'FAIL':'PASS',pass:outcomes.filter(x=>x.result==='PASS').length,fail:outcomes.filter(x=>x.result==='FAIL').length,errors:errors.slice(0,3),report}));
  if(errors.length||failures)process.exitCode=2;
  fs.rmSync(temp,{recursive:true,force:true});
 }
})().catch(e=>{console.error(e.stack||e);process.exitCode=3});
