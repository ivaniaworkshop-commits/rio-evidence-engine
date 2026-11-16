'use strict';
// Real FastAPI/SQLite/AccountService and Chromium. All actors/payment evidence
// are isolated synthetic fixtures. No provider, SMTP or production requests.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const net=require('node:net');
const crypto=require('node:crypto');
const {spawn}=require('node:child_process');
const {chromium}=require('playwright');

const key=crypto.randomBytes(32).toString('hex');
const directory=fs.mkdtempSync(path.join(os.tmpdir(),'mercado-production-acceptance-'));
const python=process.env.MERCADO_TEST_PYTHON||'/workspace/work/pey-venv/bin/python';
const exe=process.env.MERCADO_TEST_CHROMIUM||'/usr/bin/chromium';
const report=process.env.MERCADO_TEST_REPORT||path.join(directory,'report.json');
const password='Acceptance-Only-Password-2026';
const checks=[],errors=[],external=[];
let base,server,browser,serverLog='';
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const fixtureHeaders={'X-Production-Fixture-Key':key};

async function freePort(){return new Promise((resolve,reject)=>{const s=net.createServer();s.on('error',reject);s.listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>resolve(p));});});}
async function check(name,fn){try{await fn();checks.push({name,status:'PASS'});}catch(error){checks.push({name,status:'FAIL',error:String(error.stack||error).slice(0,2000)});throw error;}}
async function json(response,statuses=[200,201]){assert(statuses.includes(response.status()),response.status()+': '+(await response.text()).slice(0,1200));return response.json();}
async function post(actor,url,data,statuses=[200,201]){return json(await actor.context.request.post(base+url,{headers:{'X-CSRF-Token':actor.csrf},data}),statuses);}
async function bootstrap(actor){return json(await actor.context.request.get(base+'/v1/market/bootstrap'));}
async function register(name,email){
 const context=await browser.newContext({viewport:{width:390,height:844}});
 context.on('page',page=>{page.on('pageerror',error=>errors.push(error.message));page.on('request',request=>{if(/^https?:/.test(request.url())&&!request.url().startsWith(base+'/'))external.push(request.url());});});
 const signup=await json(await context.request.post(base+'/v1/auth/signup',{data:{email,password,business_name:name}}),[201]);
 const token=await json(await context.request.get(base+'/__production_test/verification-token?email='+encodeURIComponent(email),{headers:fixtureHeaders}));
 await json(await context.request.post(base+'/v1/auth/verify-email',{data:{token:token.token}}));
 const login=await json(await context.request.post(base+'/v1/auth/login',{data:{email,password}}));
 return {context,page:await context.newPage(),merchant:signup.merchant_id,csrf:login.csrf_token,email,name};
}
async function profile(actor,kind,alcaldia){
 return json(await actor.context.request.put(base+'/v1/market/profiles/'+actor.merchant,{headers:{'X-CSRF-Token':actor.csrf},data:{kind,alcaldia,colonia:'Centro',description:'Atención con registro en la plataforma',published:true}}));
}
async function openMarket(actor){await actor.page.goto(base+'/mercado-abierto');await actor.page.waitForFunction(()=>window.MercadoProduction?.ready===true);}
async function refresh(actor){await actor.page.evaluate(()=>window.MercadoProduction.refresh());}
async function view(actor,name){await actor.page.locator('#market-nav [data-view="'+name+'"]:visible').first().click();}
async function submit(form){await form.locator('button[type="submit"]').click();}
async function fit(page,label){assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),label+' horizontal overflow');}
async function transition(actor,order,action){const result=await post(actor,'/v1/market/orders/'+order+'/transition',{action});return result.order||result;}

(async()=>{
 const port=await freePort();base='http://127.0.0.1:'+port;
 server=spawn(python,[path.join(__dirname,'production_acceptance_fixture.py'),'--port',String(port),'--db',path.join(directory,'data.sqlite')],{cwd:path.resolve(__dirname,'..'),env:{...process.env,PRODUCTION_ACCEPTANCE_KEY:key},stdio:['ignore','pipe','pipe']});
 server.stdout.on('data',chunk=>serverLog+=chunk);server.stderr.on('data',chunk=>serverLog+=chunk);
 for(let attempt=0;attempt<200;attempt++){
  if(server.exitCode!==null)throw Error('Acceptance server exited: '+serverLog);
  try{const response=await fetch(base+'/v1/auth/me');if(response.status===401)break;}catch(_){ }
  if(attempt===199)throw Error('Acceptance server unavailable: '+serverLog);
  await delay(100);
 }
 browser=await chromium.launch({executablePath:exe,headless:true,args:['--no-sandbox']});
 const seller=await register('Verduras del Centro','seller-production@example.org');
 const buyer=await register('Abarrotes del Sur','buyer-production@example.org');
 const carrier=await register('Fletes CDMX','carrier-production@example.org');
 let listing,order,receipt;

 await check('Empty production catalog and sixteen CDMX alcaldias, no seeded offers',async()=>{
  const state=await bootstrap(buyer);assert.equal(state.localities.length,16);assert.equal(state.listings.length,0);assert.equal(state.profiles.length,0);
  const noKey=await buyer.context.request.get(base+'/__production_test/metrics');assert.equal(noKey.status(),403);
 });
 await profile(seller,'merchant','coyoacan');await profile(buyer,'merchant','iztapalapa');await profile(carrier,'freighter','coyoacan');
 await check('Seller publishes an actual database listing from the production form',async()=>{
  await openMarket(seller);await view(seller,'publicar');
  const form=seller.page.locator('#listing-form');
  await form.locator('[name="merchant_id"]').selectOption(seller.merchant);
  await form.locator('[name="name"]').fill('Salsa de temporada');
  await form.locator('[name="description"]').fill('Frasco elaborado por el comercio');await form.locator('[name="category"]').fill('Alimentos');
  await form.locator('[name="unit"]').selectOption('kg');
  await form.locator('[name="price"]').fill('12.50');await form.locator('[name="stock"]').fill('20');
  await form.locator('[name="published"]').check();
  const saved=seller.page.waitForResponse(r=>r.url()===base+'/v1/market/listings'&&r.request().method()==='POST');
  await submit(form);await json(await saved);
  const mine=await bootstrap(seller);listing=mine.my_listings.find(item=>item.name==='Salsa de temporada');
  assert(listing);assert.equal(listing.price_minor,1250);assert.equal(listing.stock_milli,20000);
 });
 await check('Another client sees the shared offer and can filter CDMX locality',async()=>{
  await openMarket(buyer);const page=buyer.page;
  await page.locator('#catalog-search').fill('Salsa de temporada');
  await page.locator('#catalog-alcaldia').selectOption('coyoacan');
  await page.locator('[data-listing-id="'+listing.id+'"]').waitFor({state:'visible'});
  await page.locator('#catalog-alcaldia').selectOption('iztapalapa');
  await page.waitForFunction(id=>!document.querySelector('[data-listing-id="'+id+'"]'),listing.id);
  await page.locator('#catalog-alcaldia').selectOption('coyoacan');await page.locator('[data-listing-id="'+listing.id+'"]').waitFor({state:'visible'});
  const forbidden=await buyer.context.request.patch(base+'/v1/market/listings/'+listing.id,{headers:{'X-CSRF-Token':buyer.csrf},data:{price_minor:1}});assert([403,404].includes(forbidden.status()));
  assert(!/demo|práctica|simulad/i.test(await page.locator('body').innerText()),'Active market contains practice/demo text');
  await fit(page,'390px shared catalog');
 });
 await check('Buyer requests a real order through shared listing controls',async()=>{
  const page=buyer.page;await page.locator('[data-listing-id="'+listing.id+'"] [data-action="order"]').click();
  const form=page.locator('#request-form');await form.locator('[name="buyer_merchant_id"]').selectOption(buyer.merchant);await form.locator('[name="quantity"]').fill('1.5');
  const saved=page.waitForResponse(r=>r.url()===base+'/v1/market/orders'&&r.request().method()==='POST');await submit(form);await json(await saved);
  const state=await bootstrap(buyer);order=state.orders.find(row=>row.listing_id===listing.id);assert(order);assert.equal(order.status,'REQUESTED');
  const wrongActor=await buyer.context.request.post(base+'/v1/market/orders/'+order.id+'/transition',{headers:{'X-CSRF-Token':buyer.csrf},data:{action:'accept'}});assert([403,404].includes(wrongActor.status()));
 });
 await check('Seller, assigned carrier and buyer complete the actor-scoped delivery workflow',async()=>{
  await refresh(seller);await view(seller,'pedidos');
  const accepted=seller.page.waitForResponse(r=>r.url().endsWith('/orders/'+order.id+'/transition'));
  await seller.page.locator('[data-action="order-transition"][data-id="'+order.id+'"][data-transition="accept"]').click();await json(await accepted);
  await transition(seller,order.id,'prepare');
  const freightData=await post(seller,'/v1/market/freights',{order_id:order.id,carrier_merchant_id:carrier.merchant,fee_minor:2500,notes:'Entrega coordinada en Ciudad de México'});
  const freight=freightData.freight||freightData;
  assert(freight.id);await post(carrier,'/v1/market/freights/'+freight.id+'/transition',{action:'accept'});
  await transition(seller,order.id,'ship');await post(carrier,'/v1/market/freights/'+freight.id+'/transition',{action:'deliver'});
  await transition(buyer,order.id,'receive');
  const current=(await bootstrap(buyer)).orders.find(row=>row.id===order.id);assert.equal(current.status,'RECEIVED');
  assert.equal(current.payment.status,'UNVERIFIED');assert.equal(current.payment.bank_payment_confirmed,false);
 });
 await check('Server cash survives a separate browser context and never creates a CoDi request',async()=>{
  const page=seller.page;await page.goto(base+'/#cobro-codi');await page.locator('#merchant').waitFor();await page.locator('#payment-method').selectOption('cash');
  await page.locator('#sale-concept').fill('Venta de mostrador');await page.locator('#amount').fill('3.13');await page.locator('#cash-received').fill('5.00');
  const save=page.waitForResponse(r=>r.url().includes('/cash-sales')&&r.request().method()==='POST');await page.locator('#cash-record').click();const stored=await json(await save);
  assert.equal(stored.persisted,true);assert.equal(stored.sale.changeMinor,187);
  const other=await browser.newContext({viewport:{width:320,height:740}});const login=await json(await other.request.post(base+'/v1/auth/login',{data:{email:seller.email,password}}));assert(login.csrf_token);
  const fresh=await other.newPage();fresh.on('pageerror',error=>errors.push(error.message));await fresh.goto(base+'/#cobro-codi');await fresh.locator('#payment-method').selectOption('cash');await fresh.locator('#cash-tools details summary').click();await fresh.locator('#cash-history').getByText(/Venta de mostrador/).waitFor();
  assert.equal((await json(await other.request.get(base+'/v1/merchants/'+seller.merchant+'/cash-sales'))).sales.length,1);await fit(fresh,'320px server cash');await other.close();
 });
 await check('Scanner checks the signed QR against the database and rejects unrelated payment receipts',async()=>{
  receipt=await json(await seller.context.request.post(base+'/__production_test/receipt/'+seller.merchant,{headers:{...fixtureHeaders,'X-CSRF-Token':seller.csrf},data:{}}));
  const page=seller.page;await page.locator('#receipt-scan-open').click();await page.locator('#receipt-scan-text').fill(receipt.link);await submit(page.locator('#receipt-scan-form'));await page.locator('#receipt-scan-result[data-state="verified"]').waitFor();
  assert((await page.locator('#receipt-scan-result').innerText()).includes('Pago confirmado por pey'));
  const foreign=await buyer.context.request.post(base+'/v1/receipts/verify',{headers:{'X-CSRF-Token':buyer.csrf},data:{qr_text:receipt.link,merchant_id:buyer.merchant}});assert([403,404].includes(foreign.status()));
  await page.locator('#receipt-scan-text').fill('https://example.org/comprobante/'+receipt.link.split('/').at(-1));await submit(page.locator('#receipt-scan-form'));await page.locator('#receipt-scan-result[data-state="error"]').waitFor();
  const png=await seller.context.request.get(receipt.link+'/qr.png');assert.equal(png.status(),200);await page.locator('#receipt-scan-image').setInputFiles({name:'comprobante.png',mimeType:'image/png',buffer:await png.body()});await page.locator('#receipt-scan-result[data-state="verified"]').waitFor();
  await page.locator('#receipt-scan-close').click();assert(!(await page.locator('#receipt-scanner-dialog').isVisible()));
 });
 await check('Production locality forms and catalog fit a 320px mobile viewport',async()=>{
  await openMarket(buyer);await buyer.page.setViewportSize({width:320,height:740});
  for(const name of ['catalogo','publicar','directorio','pedidos','fletes']){await view(buyer,name);await fit(buyer.page,'320px '+name);}
  await buyer.page.screenshot({path:path.join(directory,'market-320.png'),fullPage:true});
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
  const metrics=await json(await seller.context.request.get(base+'/__production_test/metrics',{headers:fixtureHeaders}));assert.equal(metrics.provider_calls,0);assert(metrics.mail_kinds.every(kind=>kind==='verify'));
 });
 await Promise.all([seller.context.close(),buyer.context.close(),carrier.context.close()]);
 console.log(JSON.stringify({checks:checks.length,passed:checks.filter(item=>item.status==='PASS').length,pageErrors:errors.length,externalRequests:external.length,report}));
})().catch(error=>{console.error(error.stack||error);process.exitCode=1;}).finally(async()=>{
 fs.writeFileSync(report,JSON.stringify({checks,errors,external,artifacts:directory,serverLog:serverLog.slice(-6000)},null,2));
 if(browser)await browser.close();if(server&&server.exitCode===null)server.kill('SIGTERM');
});
