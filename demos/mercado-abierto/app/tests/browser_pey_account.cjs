'use strict';
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const base='http://127.0.0.1:'+(process.env.RIO_BROWSER_PORT||'8765');
(async()=>{
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
 try{
  const context=await browser.newContext({viewport:{width:390,height:844}});
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base);
  await page.locator('#login input[name=email]').fill('browser@example.com');
  await page.locator('#login input[name=password]').fill('synthetic-password-123');
  await page.locator('#login-submit:not([disabled])').click();
  await page.locator('#dashboard').waitFor({state:'visible'});
  let saved=false, active=false;
  const account='01JBAVWE4NS5TGXHWGMX3KH23Q';
  await page.route('**/v1/merchants/*/pey-status',route=>route.fulfill({json:{payment_active:active}}));
  await page.route('**/v1/merchants/*/pey-settings',async route=>{
   const method=route.request().method();
   if(method==='PUT'){saved=true;return route.fulfill({json:{saved:true}})}
   if(method==='DELETE'){saved=false;active=false;return route.fulfill({json:{deleted:true}})}
   return route.fulfill({json:{configuration_available:true,configuration_saved:saved,api_key_configured:saved,
    webhook_secret_configured:saved,bank_account_id_configured:saved,bank_account_id:saved?account:null,
    api_key_id:saved?'01M3QMMR6X9CBVDY1SF3G8QWNW':null,payment_active:active,updated_at:saved?1700000000:null,
    verified_at:active?1700000001:null}});
  });
  await page.addInitScript(()=>window.addEventListener('rio-merchant-selected',()=>{window.__merchantLoaded=true}));
  await page.route('**/static/pey-private.js',async route=>{
    // Force initial selection to occur before the deferred connection script loads.
    await page.waitForFunction(()=>window.__merchantLoaded===true);
    await route.continue();
  });
  await page.reload();
  await page.locator('[data-workspace-view="negocios"]:visible').first().click();
  await page.locator('#private-pey-account-status').filter({hasText:'Sin conexión guardada'}).waitFor();
  assert(await page.locator('#private-pey-empty').isVisible());
  assert(await page.locator('#private-pey-delete').isDisabled());
  await page.locator('#private-pey-bank').fill('012345678901234567');
  assert(await page.locator('#private-pey-bank').evaluate(node=>node.validity.patternMismatch));
  await page.locator('#private-pey-bank').fill(account);
  await page.locator('#private-pey-key').fill('sk_synthetic_summary');
  await page.locator('#private-pey-form button[type=submit]').click();
  await page.locator('#private-pey-saved-account').filter({hasText:account}).waitFor();
  assert(await page.locator('#private-pey-delete').isEnabled());
  assert.equal(await page.locator('#private-pey-updated').textContent()==='Sin registro',false);
  active=true;await page.locator('#private-pey-check').click();
  await page.locator('#private-pey-account-status').filter({hasText:'CoDi habilitado'}).waitFor();
  page.once('dialog',dialog=>dialog.accept());
  await page.locator('#private-pey-delete').click();
  await page.locator('#private-pey-account-status').filter({hasText:'Sin conexión guardada'}).waitFor();
  assert(await page.locator('#private-pey-delete').isDisabled());
  assert.equal(await page.locator('#private-pey-saved-account').textContent(),'Sin cuenta vinculada');
  await page.locator('[data-workspace-view="menu"]:visible').first().click();
  await page.locator('#main-area-menu [data-workspace-view="negocios"]').click();
  assert.equal(await page.locator('[data-workspace-panel]:visible').count(),1);
  assert(await page.locator('#add-merchant').isVisible());
  assert(await page.locator('#private-pey-summary').isVisible());
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.deepEqual(errors,[]);
  console.log('PEY_ACCOUNT_LATE_SCRIPT_DETAILS_STATUS_DELETE_MOBILE_OK');
  await context.close();
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
