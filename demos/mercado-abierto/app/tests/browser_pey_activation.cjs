'use strict';
// Loopback-only fixture. Provider responses are synthetic; no live calls.
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const base='http://127.0.0.1:'+(process.env.RIO_BROWSER_PORT||'8765');
(async()=>{
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
 try{
 const ctx=await browser.newContext();const page=await ctx.newPage();const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 let saved=false,active=false,failSave=true,failActivation=true,gets=0;
 await ctx.route('**/public-status',async route=>{const response=await route.fetch();const data=await response.json();await route.fulfill({json:{...data,mode:'LIVE',live_payments_enabled:true,payment_requests_enabled:true}})});
 await ctx.route('**/v1/merchants/*/pey-status',route=>route.fulfill({json:{payment_active:active}}));
 await ctx.route('**/v1/merchants/*/pey-settings',async route=>{
  if(route.request().method()==='PUT'){
   if(failSave)return route.fulfill({status:503,json:{detail:'Error sintético al guardar'}});
   assert.equal(route.request().postDataJSON().api_key,'sk_synthetic_browser');saved=true;
   return route.fulfill({json:{saved:true,payment_active:false}});
  }
  gets++;return route.fulfill({json:{api_key_configured:saved,webhook_secret_configured:saved,configuration_available:true,payment_active:active,webhook_url:'http://127.0.0.1/webhook'}});
 });
 await ctx.route('**/pey-settings/activate',route=>{
  if(failActivation)return route.fulfill({status:502,json:{detail:'Error sintético al verificar'}});
  active=true;return route.fulfill({json:{payment_active:true}});
 });
 await page.goto(base);
 await page.locator('#login input[name=email]').fill('browser@example.com');
 await page.locator('#login input[name=password]').fill('synthetic-password-123');
 await page.locator('#login-submit:not([disabled])').click();
 await page.locator('#dashboard').waitFor({state:'visible'});
 await page.locator('#main-area-menu [data-workspace-view="negocios"]').click();
 await page.waitForFunction(()=>document.querySelectorAll('#merchant option').length===2);
 const selected=await page.locator('#merchant option').last().getAttribute('value');
 await page.selectOption('#merchant',selected);
 await page.locator('#private-pey-form button[type=submit]:not([disabled])').waitFor();
 await page.locator('#private-pey-key').fill('sk_synthetic_browser');
 await page.locator('#private-pey-webhook').fill('synthetic-webhook');
 await page.locator('#private-pey-form button[type=submit]').click();
 await page.getByText('Error sintético al guardar',{exact:true}).waitFor();
 assert.equal(await page.locator('#private-pey-key').inputValue(),'sk_synthetic_browser');
 failSave=false;await page.locator('#private-pey-form button[type=submit]').click();
 await page.locator('#private-pey-state').filter({hasText:'Llave guardada · Webhook guardado'}).waitFor();
 assert.equal(await page.locator('#private-pey-key').inputValue(),'');
 const second=await ctx.newPage();
 await second.goto(base);
 await second.locator('#main-area-menu [data-workspace-view="negocios"]').click();
 await second.waitForFunction(()=>document.querySelectorAll('#merchant option').length===2);
 await second.selectOption('#merchant',selected);
 await second.locator('#pey-connection-status').filter({hasText:'pendiente'}).waitFor();
 await page.bringToFront();
 await page.locator('#private-pey-confirm').check();
 await page.locator('#private-pey-activate').click();
 await page.getByText('Error sintético al verificar',{exact:true}).waitFor();
 assert(!active);
 failActivation=false;
 await Promise.all([page.waitForEvent('load'),page.locator('#private-pey-activate').click()]);
 await page.locator('#private-pey-state').filter({hasText:'CoDi habilitado'}).waitFor();
 await page.locator('#notice').filter({hasText:'quedó guardada'}).waitFor();
 await second.locator('#pey-connection-status').filter({hasText:'CoDi habilitado'}).waitFor();
 assert.equal(await page.locator('#private-pey-activate').isDisabled(),true);
 assert.equal(await page.locator('#merchant').inputValue(),selected);
 assert(gets>=4);assert.deepEqual(errors,[]);
 console.log('PEY_SAVE_FAILURE_PRESERVES_FIELDS_STATUS_REFRESH_AND_ACTIVATION_RELOAD_OK');
 await ctx.close();
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
