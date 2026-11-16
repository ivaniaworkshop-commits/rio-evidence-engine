'use strict';
// Loopback-only real API/browser test. No production payments or mail.
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const base='http://127.0.0.1:'+(process.env.RIO_BROWSER_PORT||'8833');
(async()=>{
 const status=await(await fetch(base+'/public-status')).json();assert.equal(status.environment,'local');
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
 try{
  const errors=[],posts=[];let codi=0;
  const a=await browser.newContext({viewport:{width:390,height:844}}),b=await browser.newContext({viewport:{width:320,height:800}});
  async function login(context){const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));page.on('request',req=>{const url=new URL(req.url());if(req.method()==='POST'&&url.pathname.endsWith('/cash-sales'))posts.push(req.postDataJSON().id);if(req.method()==='POST'&&url.pathname==='/v1/checkout/qr')codi++});await page.goto(base+'/');await page.locator('#login input[name=email]').fill('browser@example.com');await page.locator('#login input[name=password]').fill('synthetic-password-123');await page.locator('#login-submit:not([disabled])').click();await page.locator('#main-area-menu').waitFor({state:'visible'});await page.locator('#main-area-menu [data-workspace-view="caja"]').click();await page.locator('#payment-method').selectOption('cash');await page.locator('#cash-record:not([disabled])').waitFor();await page.locator('#cash-tools details > summary').click();return page}
  const pa=await login(a),pb=await login(b);
  async function details(page,folio,amount,received){await page.locator('#sale-order').fill(folio);await page.locator('#sale-concept').fill('Venta real declarada por la persona');await page.locator('#amount').fill(amount);await page.locator('#cash-received').fill(received)}
  async function save(page){await page.locator('#cash-record').click();await page.waitForFunction(()=>document.getElementById('cash-status').textContent.includes('Efectivo recibido y registrado en el servidor.'))}
  await details(pa,'BROWSER-A','3.13','5');await save(pa);assert((await pa.locator('#cash-change').innerText()).includes('1.87'));
  await pb.locator('#cash-refresh').click();await pb.waitForFunction(()=>document.getElementById('cash-history').children.length===1);
  await details(pb,'BROWSER-B','6.26','10');await save(pb);
  const merchant=await pa.locator('#merchant').inputValue(),path='/v1/merchants/'+merchant+'/cash-sales';
  assert.equal((await(await a.request.get(base+path)).json()).sales.length,2);
  await pa.evaluate(()=>localStorage.clear());await pa.reload();await pa.locator('#payment-method').selectOption('cash');await pa.locator('#cash-record:not([disabled])').waitFor();assert.equal(await pa.locator('#cash-history > li').count(),2);
  // Offline save cannot claim success. Its pending ID survives reload for an idempotent retry.
  await pa.locator('#cash-new-sale').click();await details(pa,'BROWSER-OFFLINE','10','20');
  await pa.route('**/cash-sales',route=>route.request().method()==='POST'?route.abort('failed'):route.continue());
  await pa.route('**/cash-sales/CASH-*',route=>route.abort('failed'));
  await pa.locator('#cash-record').click();await pa.waitForFunction(()=>document.getElementById('cash-status').textContent.includes('No se mostrará como guardada'));
  const pending=await pa.evaluate(()=>Object.keys(sessionStorage).filter(k=>k.startsWith('mercadoabierto.cash.pending.v1:')).map(k=>JSON.parse(sessionStorage.getItem(k)))[0]);assert(pending?.item?.id);
  assert.equal((await(await b.request.get(base+path)).json()).sales.length,2);
  await pa.reload();await pa.locator('#payment-method').selectOption('cash');await pa.locator('#cash-record:not([disabled])').waitFor();assert.equal(await pa.locator('#sale-order').inputValue(),'BROWSER-OFFLINE');assert.equal(await pa.locator('#amount').inputValue(),'10.00');
  await pa.locator('#payment-method').selectOption('codi');assert.equal(await pa.locator('#payment-method').inputValue(),'cash');
  await pa.unroute('**/cash-sales');await pa.unroute('**/cash-sales/CASH-*');await save(pa);
  let rows=(await(await b.request.get(base+path)).json()).sales;assert.equal(rows.length,3);assert(rows.some(row=>row.id===pending.item.id));
  // Commit then drop the response and readback: another browser sees it, retry never duplicates it.
  await pa.locator('#cash-new-sale').click();await details(pa,'BROWSER-UNCERTAIN','12','20');
  await pa.route('**/cash-sales',async route=>{if(route.request().method()==='POST'){await route.fetch();await route.abort('failed')}else await route.continue()});
  await pa.route('**/cash-sales/CASH-*',route=>route.abort('failed'));
  await pa.locator('#cash-record').click();await pa.waitForFunction(()=>document.getElementById('cash-status').textContent.includes('No se mostrará como guardada'));
  assert.equal((await(await b.request.get(base+path)).json()).sales.length,4);
  await pa.unroute('**/cash-sales');await pa.unroute('**/cash-sales/CASH-*');await save(pa);
  rows=(await(await b.request.get(base+path)).json()).sales;assert.equal(rows.length,4);assert(rows.every(row=>row.persisted&&row.bankPaymentConfirmed===false));
  await pb.locator('#cash-refresh').click();await pb.waitForFunction(()=>document.getElementById('cash-history').children.length===4);
  assert.equal(codi,0);assert.deepEqual(errors,[]);assert(posts.filter(id=>id===pending.item.id).length>=2);
  for(const page of [pa,pb])assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  console.log(JSON.stringify({cashBrowser:'PASS',crossBrowserServerRecords:4,offlineNotSaved:true,pendingReload:true,uncertainRetryIdempotent:true,codiPosts:codi,pageErrors:errors.length}));
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
