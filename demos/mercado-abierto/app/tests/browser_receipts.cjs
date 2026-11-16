'use strict';
// Only loopback fixture and synthetic provider responses.
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
 try {
  const ctx=await browser.newContext({viewport:{width:390,height:844}});const page=await ctx.newPage();const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/public-status',async route=>{const response=await route.fetch();await route.fulfill({json:{...await response.json(),mode:'LIVE',live_payments_enabled:true,payment_requests_enabled:true}})});
  let lastIntent;
  await page.route('**/v1/merchants/*/checkout-orders/*',route=>route.fulfill({json:{intent:lastIntent}}));
  let captured,ident='a'.repeat(32);
  await page.route('**/v1/checkout/qr',route=>{
   captured=route.request().postDataJSON();
   lastIntent={...captured,id:ident,mode:'LIVE',status:'PROVIDER_REPORTED',provider_transaction_id:'tx-synthetic',expired:false};
   return route.fulfill({status:201,json:{status:'CREATED',mode:'LIVE',intent:lastIntent}});
  });
  await page.route('**/v1/checkout/qr/*/receipt',route=>route.fulfill({json:{enabled:captured.receipt_enabled,issued:true,link:'http://127.0.0.1:8765/comprobante/synthetic',deliveries:captured.receipt_enabled?{payer:'SENT',receiver:'SENT'}:{}}}));
  await page.goto('http://127.0.0.1:8765');
  await page.locator('#login input[name=email]').fill('browser@example.com');
  await page.locator('#login input[name=password]').fill('synthetic-password-123');
  await page.locator('#login-submit:not([disabled])').click();
  await page.locator('#dashboard').waitFor({state:'visible'});
  await page.locator('#charge-submit:not([disabled])').waitFor();
  assert(await page.locator('#receipt-options').isVisible());
  assert(await page.locator('#payer-email').evaluate(n=>n.required));
  await page.locator('#sale-concept').fill('Prueba sintética');
  await page.locator('#amount').fill('10.00');
  await page.locator('#payer-email').fill('payer@example.com');
  await page.locator('#charge-submit').click();
  await page.locator('#receipt-status').filter({hasText:'Pago confirmado por pey'}).waitFor();
  assert.equal(captured.payer_email,'payer@example.com');assert.equal(captured.receipt_enabled,true);
  assert(await page.locator('#receipt-link').isVisible());
  assert(!(await page.evaluate(()=>JSON.stringify(localStorage))).includes('payer@example.com'));
  await page.locator('#new-order').click();
  await page.locator('#receipt-disabled').check();
  assert(!(await page.locator('#payer-email').evaluate(n=>n.required)));
  assert(await page.locator('#payer-email').isDisabled());
  await page.locator('#sale-concept').fill('Segunda prueba');await page.locator('#amount').fill('11.00');
  await page.locator('#charge-submit').click();
  await page.locator('#receipt-status').filter({hasText:'Envío de correos desactivado'}).waitFor();
  assert.equal(captured.receipt_enabled,false);assert.equal(captured.payer_email,null);
  assert(await page.locator('#receipt-link').isVisible());
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.deepEqual(errors,[]);console.log('RECEIPT_EMAIL_OPT_OUT_AND_VERIFICATION_LINK_MOBILE_OK');
  await ctx.close();
 } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
