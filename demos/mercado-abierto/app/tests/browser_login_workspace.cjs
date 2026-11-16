// Run only with the loopback DEMO fixture tests/browser_fixture_server.py.
'use strict';
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const base = 'http://127.0.0.1:' + (process.env.RIO_BROWSER_PORT || '8765');

(async () => {
  const health = await (await fetch(base + '/public-status')).json();
  assert.equal(health.application, 'rio-merchant-codi');
  assert.equal(health.environment, 'local');
  assert.equal(health.mode, 'DEMO');
  assert.equal(health.live_payments_enabled, false);
  const browser = await chromium.launch({headless:true, executablePath:process.env.CHROMIUM_EXECUTABLE_PATH || '/usr/bin/chromium', args:['--no-sandbox']});
  try {
    const context = await browser.newContext({viewport:{width:390, height:844}});
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(base);
    await page.locator('#login-submit:not([disabled])').waitFor();
    assert(await page.locator('#login').isVisible());
    assert.equal(await page.locator('#dashboard').count(), 0);
    assert.equal(await page.locator('#merchant').count(), 0);
    assert.equal(await page.locator('#signup').isVisible(), false);
    assert.equal(await page.locator('#forgot-password-form').isVisible(), false);
    await page.screenshot({path:'/workspace/work/pey-login-only.png', fullPage:true});

    await page.locator('[data-auth-open="signup"]').click();
    await page.locator('#signup input[name="business_name"]').fill('Comercio UI local');
    await page.locator('#signup-email').fill('ui-local-signup-' + Date.now() + '@example.com');
    await page.locator('#signup input[name="password"]').fill('Synthetic-workspace-123');
    await page.locator('#signup-submit').click();
    await page.getByText('Cuenta creada. Revisa tu correo y verifica la cuenta antes de iniciar sesión.').waitFor();
    assert.equal(await page.locator('#dashboard').count(), 0);
    await page.locator('[data-auth-view="verify"] [data-auth-open="login"]').click();
    await page.locator('[data-auth-view="login"] [data-auth-open="forgot"]').click();
    await page.locator('#forgot-email').fill('browser@example.com');
    await page.locator('#reset-request').click();
    await page.locator('#forgot-password-status').filter({hasText:'Si existe una cuenta'}).waitFor();
    await page.locator('[data-auth-view="forgot"] [data-auth-open="login"]').click();

    // Exercise the extracted public token screens with synthetic API responses.
    const tokenPage = await context.newPage();
    tokenPage.on('pageerror', error => errors.push(error.message));
    await tokenPage.route('**/v1/auth/verify-email', async route => {
      assert.deepEqual(route.request().postDataJSON(), {token:'synthetic-verify-token'});
      await route.fulfill({status:400,json:{detail:'Este enlace ya se utilizó. Inicia sesión con tu correo y contraseña.'}});
    });
    await tokenPage.goto(base + '/verify-email#token=synthetic-verify-token');
    await tokenPage.getByText('Este enlace ya se utilizó. Inicia sesión con tu correo y contraseña.').waitFor();
    assert(!tokenPage.url().includes('token'));
    assert.equal(await tokenPage.locator('#dashboard').count(), 0);
    await tokenPage.route('**/v1/auth/reset-confirm', async route => {
      assert.deepEqual(route.request().postDataJSON(), {token:'synthetic-reset-token',password:'Changed-synthetic-123'});
      await route.fulfill({status:200,json:{status:'RESET'}});
    });
    await tokenPage.goto(base + '/reset-password#token=synthetic-reset-token');
    await tokenPage.locator('#rio-reset-password').fill('Changed-synthetic-123');
    await tokenPage.locator('#rio-reset-confirmation').fill('Changed-synthetic-123');
    await tokenPage.locator('#rio-reset-submit').click();
    await tokenPage.getByText('Contraseña actualizada. Ya puedes iniciar sesión.').waitFor();
    assert(!tokenPage.url().includes('token'));
    await tokenPage.close();

    await page.locator('#login input[name="email"]').fill('browser@example.com');
    await page.locator('#login input[name="password"]').fill('synthetic-password-123');
    await page.locator('#login-submit').click();
    await page.locator('#dashboard').waitFor({state:'visible'});
    await page.waitForFunction(() => document.documentElement.dataset.sessionReady === 'true');
    assert.equal(await page.locator('#login').count(), 0);
    assert.equal(await page.locator('[data-workspace-panel]:visible').count(), 1);
    assert(await page.locator('[data-workspace-panel="menu"]').isVisible());
    for (const view of ['caja', 'historial', 'negocios', 'menu']) {
      await page.locator('[data-workspace-view="' + view + '"]:visible').first().click();
      assert.equal(await page.locator('[data-workspace-panel]:visible').count(), 1);
      assert(await page.locator('[data-workspace-panel="' + view + '"]').isVisible());
    }
    await page.locator('[data-workspace-view="caja"]:visible').first().click();
    const ids = await page.locator('[id]').evaluateAll(nodes => nodes.map(node => node.id));
    assert.equal(ids.length, new Set(ids).size, 'Each operation has only one DOM location');
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({path:'/workspace/work/pey-workspace-caja.png', fullPage:true});

    const second = await context.newPage();
    second.on('pageerror', error => errors.push(error.message));
    assert.equal((await context.request.get(base + '/static/unificada/mercado/index.html')).status(), 403);
    assert.equal(await page.locator('[data-owner-area="market"]:visible').count(), 0);
    await second.goto(base + '/mercado-abierto');
    await second.waitForFunction(() => document.documentElement.dataset.sessionReady === 'true');
    assert(!second.url().includes('/login'));
    await page.evaluate(async () => {
      const cache = await caches.open('rio-unificada-legacy-login-test');
      await cache.put('/static/unificada/caja/index.html', new Response('<h1>old private page</h1>'));
    });
    // Keep a private entry in browser history, then verify Back after logout.
    await page.goto(base + '/caja');
    await page.locator('#dashboard').waitFor({state:'visible'});
    await page.locator('#logout').click();
    await page.locator('#login-submit:not([disabled])').waitFor();
    await second.waitForURL('**/login?next=**');
    assert.equal(await second.locator('#app').count(), 0);
    await page.waitForFunction(async () => !(await caches.keys()).includes('rio-unificada-legacy-login-test'));
    for (const path of ['/caja', '/hackaton', '/mercado-abierto', '/static/index.html', '/static/unificada/index.html',
                        '/static/unificada/caja/index.html', '/static/unificada/mercado/index.html',
                        '/static/unificada/hackaton/index.html']) {
      const response = await context.request.get(base + path, {maxRedirects:0});
      assert.equal(response.status(), 303, path);
    }
    await page.goBack();
    await page.locator('#login-submit').waitFor({state:'visible'});
    assert.equal(await page.locator('#dashboard').count(), 0);
    assert.deepEqual(errors, []);
    console.log('LOGIN_FIRST_WORKSPACE_AND_LOGOUT_OK');
    console.log(JSON.stringify({authOnly:true,views:4,directLinksProtected:8,ownerMarketRestricted:true,logoutAcrossTabs:true,oldHtmlCacheRemoved:true,pageErrors:errors.length}));
    await context.close();
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
