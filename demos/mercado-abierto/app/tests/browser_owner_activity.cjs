'use strict';
const assert=require('node:assert/strict');const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
 try{
  const context=await browser.newContext({viewport:{width:390,height:844}});const page=await context.newPage();const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/v1/auth/me',async route=>{const response=await route.fetch();const data=await response.json();await route.fulfill({status:response.status(),json:response.ok()?{...data,can_invite:true}:data})});
  let deny=false,requests=0;
  await page.route('**/v1/admin/activity?**',route=>{
   requests++;if(deny)return route.fulfill({status:403,json:{detail:'Solo titular'}});
   const url=new URL(route.request().url());
   return route.fulfill({json:{events:[{id:url.searchParams.has('before')?'b':'a',event_type:url.searchParams.has('before')?'ACCOUNT_CREATED':'VERIFICATION_ACCEPTED',occurred_at:1700000000,email:'<img src=x onerror=alert(1)>@example.org',source:'LIVE_EVENT'}],next_cursor:url.searchParams.has('before')?null:'cursor-synthetic'}});
  });
  await page.goto('http://127.0.0.1:8766');await page.locator('#login input[name=email]').fill('browser@example.com');await page.locator('#login input[name=password]').fill('synthetic-password-123');await page.locator('#login-submit:not([disabled])').click();
  await page.locator('#owner-activity-open').waitFor({state:'visible'});assert.equal(requests,0);
  await page.locator('#owner-activity-open').click();
  await page.locator('#owner-activity-list li').waitFor();assert.equal(await page.locator('#owner-activity-list img').count(),0);
  assert(await page.locator('#owner-activity-list').textContent().then(t=>t.includes('aceptado por el servidor')));
  await page.locator('#owner-activity-more').click();await page.waitForFunction(()=>document.querySelectorAll('#owner-activity-list li').length===2);
  await page.selectOption('#owner-activity-category','email');await page.waitForFunction(()=>document.querySelectorAll('#owner-activity-list li').length===1);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.keyboard.press('Escape');assert(!(await page.locator('#owner-activity-dialog').isVisible()));
  assert.equal(await page.locator('#owner-activity-list li').count(),0);
  await page.locator('#owner-activity-open').click();await page.locator('#owner-activity-list li').waitFor();
  deny=true;await page.locator('#owner-activity-refresh').click();await page.locator('#owner-activity-open').waitFor({state:'hidden'});
  assert.equal(await page.locator('#owner-activity-list li').count(),0);assert.deepEqual(errors,[]);
  console.log('OWNER_ACTIVITY_DISCREET_DIALOG_PAGINATION_AUTH_DENIAL_NO_XSS_MOBILE_OK');
  await context.close();
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
