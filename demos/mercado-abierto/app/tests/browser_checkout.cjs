// Run only against tests/browser_fixture_server.py in an isolated environment.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {chromium} = require('playwright');

const base = `http://127.0.0.1:${process.env.RIO_BROWSER_PORT || '8765'}`;
const counter = process.env.RIO_BROWSER_COUNTER;
const attempts = () => fs.existsSync(counter) ? fs.readFileSync(counter, 'utf8').trim().split('\n').filter(Boolean).length : 0;
const amount = page => page.locator('#charge input[name="amount"]');
const concept = page => page.locator('#charge input[name="concept"]');
const submit = page => page.locator('#charge button');
const openWorkspace = (page, view) => page.locator('[data-workspace-view="' + view + '"]:visible').first().click();

async function choose(page, name) {
  await page.waitForFunction(() => document.querySelectorAll('#merchant option').length === 2);
  const labels = await page.locator('#merchant option').allTextContents();
  await page.selectOption('#merchant', {label:labels.find(label => label.startsWith(name))});
}

(async () => {
  const browser = await chromium.launch({headless:true, args:['--no-sandbox'],
    ...(process.env.CHROMIUM_EXECUTABLE_PATH ? {executablePath:process.env.CHROMIUM_EXECUTABLE_PATH} : {})});
  try {
    const context = await browser.newContext({viewport:{width:390, height:844}, colorScheme:'light'});
    const first = await context.newPage();
    await first.goto(base);
    await first.locator('#login input[name="email"]').fill('browser@example.com');
    await first.locator('#login input[name="password"]').fill('synthetic-password-123');
    await first.locator('#login-submit:not([disabled])').click();
    await first.locator('#dashboard').waitFor({state:'visible'});
    await openWorkspace(first, 'negocios');
    await first.waitForFunction(() => {
      const img = document.querySelector('.provider-mark img');
      return img.naturalWidth > 0 && img.currentSrc.endsWith('pey_codi_light.svg');
    });
    await first.emulateMedia({colorScheme:'dark'});
    await first.waitForFunction(() => {
      const img = document.querySelector('.provider-mark img');
      return img.naturalWidth > 0 && img.currentSrc.endsWith('pey_codi_dark.svg');
    });
    assert(await first.evaluate(() => document.documentElement.scrollWidth <= innerWidth));

    await openWorkspace(first, 'caja');
    await choose(first, 'Principal');
    await concept(first).fill('Pedido privado');
    await amount(first).fill('150.00');
    await submit(first).click();
    await first.waitForFunction(() => document.querySelector('#notice').textContent.includes('incierto'));
    assert.equal(attempts(), 1);
    const stored = await first.evaluate(() => JSON.stringify(localStorage));
    assert(!stored.includes('Pedido privado'));
    assert(!stored.includes('150.00'));

    await first.reload();
    await first.locator('#dashboard').waitFor({state:'visible'});
    await openWorkspace(first, 'caja');
    await choose(first, 'Principal');
    await first.waitForFunction(() => document.querySelector('#qrstate').textContent.includes('Resultado incierto'));
    assert.equal(await amount(first).inputValue(), '150.00');
    assert.equal(await concept(first).inputValue(), 'Pedido privado');
    await amount(first).fill('151.00');
    await submit(first).click();
    await first.waitForFunction(() => document.querySelector('#notice').textContent.includes('otros datos'));
    assert.equal(attempts(), 1);
    await amount(first).fill('150');
    await submit(first).click();
    await first.waitForFunction(() => document.querySelector('#notice').textContent.includes('Solicitud de práctica'));
    assert.equal(attempts(), 1);
    first.once('dialog', dialog => dialog.dismiss());
    await first.locator('#new-order').click();
    assert(await first.locator('#result').isVisible());
    assert.equal(attempts(), 1, 'Declining another sale preserves the unresolved order');

    const second = await context.newPage();
    await second.goto(base);
    await second.locator('#dashboard').waitFor({state:'visible'});
    await openWorkspace(second, 'caja');
    await choose(first, 'Segundo comercio');
    await choose(second, 'Segundo comercio');
    for (const page of [first, second]) {
      await concept(page).fill('Segundo pedido');
      await amount(page).fill('200.00');
    }
    await submit(first).click();
    for (let i = 0; i < 50 && attempts() < 2; i++) await new Promise(resolve => setTimeout(resolve, 50));
    assert.equal(attempts(), 2);
    await submit(second).click();
    await second.waitForFunction(() => document.querySelector('#notice').textContent.includes('Otra pestaña'));
    await first.waitForFunction(() => document.querySelector('#notice').textContent.includes('incierto'));
    assert.equal(attempts(), 2);
    console.log('BROWSER_RECOVERY_AND_TWO_TABS_OK');
    console.log('BROWSER_LOGOS_LIGHT_DARK_390PX_OK');
    await context.close();
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
