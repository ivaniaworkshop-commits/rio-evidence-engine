'use strict';
// Local fixture only; auth responses below are synthetic. No external mail.
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const base = 'http://127.0.0.1:' + (process.env.RIO_BROWSER_PORT || '8765');
(async () => {
  const status = await (await fetch(base + '/public-status')).json();
  assert.equal(status.environment, 'local'); assert.equal(status.mode, 'DEMO');
  const browser = await chromium.launch({headless:true, executablePath:'/usr/bin/chromium', args:['--no-sandbox']});
  try {
    const context = await browser.newContext({viewport:{width:390,height:844}});
    const page = await context.newPage();
    const errors=[]; page.on('pageerror', error => errors.push(error.message));
    let signupMode='exists', loginMode='pending', resendMode='fail', resendCalls=0, release;
    await page.route('**/v1/auth/signup', async route => {
      if (signupMode==='exists') return route.fulfill({status:409,json:{detail:'Account already exists; use account recovery',code:'ACCOUNT_EXISTS'}});
      if (signupMode==='mail-fail') return route.fulfill({status:503,json:{detail:'Correo no disponible',code:'VERIFICATION_DELIVERY_UNAVAILABLE',account_created:true}});
      return route.fulfill({status:201,json:{status:'VERIFICATION_REQUIRED'}});
    });
    await page.route('**/v1/auth/login', async route => {
      if (loginMode==='mail-fail') return route.fulfill({status:503,json:{detail:'Correo no disponible',code:'EMAIL_DELIVERY_UNAVAILABLE'}});
      if (loginMode==='invalid') return route.fulfill({status:401,json:{detail:'Invalid credentials'}});
      return route.fulfill({status:403,json:{detail:'Verifica tu correo',code:'ACCOUNT_ACTIVATION_REQUIRED',verification_requested:true}});
    });
    await page.route('**/v1/auth/resend-verification', async route => {
      resendCalls++;
      assert.equal(route.request().postDataJSON().email,'new-business@example.com');
      if (resendMode==='hold') await new Promise(resolve => {release=resolve});
      if (resendMode==='fail') return route.fulfill({status:503,json:{detail:'Correo no disponible',code:'EMAIL_DELIVERY_UNAVAILABLE'}});
      return route.fulfill({status:200,json:{status:'IF_ELIGIBLE_EMAIL_SENT'}});
    });
    await page.goto(base);
    await page.locator('#login-submit:not([disabled])').waitFor();
    await page.locator('[data-auth-view="login"] [data-auth-open="signup"]').click();
    await page.locator('#signup input[name=business_name]').fill('Nuevo negocio');
    await page.locator('#signup-email').fill('new-business@example.com');
    await page.locator('#signup input[name=password]').fill('Synthetic-password-123');
    await page.locator('#signup-submit').click();
    await page.locator('#verification-status').filter({hasText:'Este correo ya tiene una cuenta'}).waitFor();
    assert.equal(await page.locator('#verification-email').inputValue(),'new-business@example.com');
    assert.equal(resendCalls,0,'Duplicate signup must not send another email automatically');
    assert(!(await page.locator('body').innerText()).includes('Account already exists'));
    assert.equal(await page.locator('#dashboard').count(),0);

    await page.locator('#verification-resend').click();
    await page.locator('#verification-status').filter({hasText:'No se pudo completar'}).waitFor();
    assert.equal(await page.locator('#verification-email').inputValue(),'new-business@example.com');
    assert(!/Solicitud aceptada|recibirás un enlace/.test(await page.locator('#verification-status').textContent()));
    resendMode='hold';
    await page.locator('#verification-resend').click();
    await page.waitForFunction(() => document.querySelector('#verification-resend').disabled);
    assert(await page.locator('#verification-resend').isDisabled());
    await page.locator('#verification-form').evaluate(form=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
    for(let attempt=0;attempt<100&&!release;attempt++)await new Promise(resolve=>setTimeout(resolve,5));
    assert(release); assert.equal(resendCalls,2);
    resendMode='success'; release();
    await page.locator('#verification-status').filter({hasText:'Solicitud aceptada'}).waitFor();
    assert.equal(resendCalls,2);

    await page.locator('[data-auth-view="verify"] [data-auth-open="forgot"]').click();
    assert.equal(await page.locator('#forgot-email').inputValue(),'new-business@example.com');
    await page.locator('[data-auth-view="forgot"] [data-auth-open="login"]').click();
    assert.equal(await page.locator('#login input[name=email]').inputValue(),'new-business@example.com');
    await page.locator('#login input[name=password]').fill('Synthetic-password-123');
    await page.locator('#login-submit').click();
    await page.locator('#verification-status').filter({hasText:'Solicitamos un nuevo correo'}).waitFor();
    assert.equal(await page.locator('#dashboard').count(),0);

    loginMode='mail-fail';
    await page.locator('[data-auth-view="verify"] [data-auth-open="login"]').click();
    await page.locator('#login input[name=password]').fill('Synthetic-password-123');
    await page.locator('#login-submit').click();
    await page.locator('#verification-status').filter({hasText:'servicio de correo no pudo completar'}).waitFor();
    assert.equal(await page.locator('#verification-email').inputValue(),'new-business@example.com');

    await page.locator('[data-auth-view="verify"] [data-auth-open="login"]').click();
    await page.locator('[data-auth-view="login"] [data-auth-open="signup"]').click();
    signupMode='mail-fail';
    await page.locator('#signup input[name=password]').fill('Synthetic-password-123');
    await page.locator('#signup-submit').click();
    await page.locator('#verification-status').filter({hasText:'La cuenta quedó creada'}).waitFor();
    assert.equal(await page.locator('#verification-email').inputValue(),'new-business@example.com');
    assert.equal(await page.locator('#dashboard').count(),0);
    assert(!(await page.evaluate(()=>JSON.stringify(localStorage))).includes('new-business@example.com'));
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    assert.deepEqual(errors,[]);
    console.log('REGISTRATION_EXISTS_VERIFY_RETRY_FAILURE_DUPLICATE_REQUESTS_NO_AUTH_BYPASS_OK');
    await context.close();
  } finally {await browser.close()}
})().catch(error => {console.error(error);process.exitCode=1});
