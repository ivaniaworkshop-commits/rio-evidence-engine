// Browser E2E against an isolated loopback server with synthetic accounts and events.
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const origin = `http://127.0.0.1:${process.env.RIO_BROWSER_PORT || '8765'}`;

async function login(page) {
  await page.goto(origin);
  await page.locator('#login input[name="email"]').fill('review-browser@example.com');
  await page.locator('#login input[name="password"]').fill('synthetic-password-123');
  await page.locator('#login button').click();
  await page.locator('#dashboard').waitFor({state:'visible'});
  await page.waitForFunction(() => document.querySelectorAll('#merchant option').length === 2);
  await page.selectOption('#merchant', {label:'Principal (owner)'});
  await page.getByRole('button', {name:'Revisar browser-review-a'}).click();
  await page.locator('#review').waitFor({state:'visible'});
}

async function exercise(browser, width) {
  const context = await browser.newContext({viewport:{width,height:844}});
  const page = await context.newPage();
  try {
    await login(page);
    await page.locator('#review-clabe').fill('0'.repeat(18));
    await page.locator('#review-tracking').fill('tracking-a');
    await page.locator('#review-amount').fill('150.00');
    await page.locator('#review-reference').fill('synthetic-statement');
    await page.locator('#review-preview').click();
    await page.waitForFunction(() => document.querySelector('#review-status').textContent.includes('Coincidencia candidata'));
    await page.locator('#review-save').click();
    await page.waitForFunction(() => document.querySelector('#review-status').textContent.includes('Revisión guardada'));
    assert.equal(await page.locator('#review-clabe').inputValue(), '');
    await page.waitForFunction(() => document.querySelectorAll('#review-history li').length >= 1);
    const geometry = await page.evaluate(() => ({width:innerWidth, scroll:document.documentElement.scrollWidth}));
    assert(geometry.scroll <= geometry.width, `Unexpected horizontal overflow at ${width}px`);
    await page.locator('#review-reload').focus();
    await page.keyboard.press('Tab');
    assert(await page.evaluate(() => document.activeElement !== document.body), 'Keyboard focus was lost');
    if (width === 320 && process.env.RIO_BROWSER_SCREENSHOT) {
      await page.screenshot({path:process.env.RIO_BROWSER_SCREENSHOT,fullPage:true});
    }
    await page.reload();
    await page.locator('#dashboard').waitFor({state:'visible'});
    await page.waitForFunction(() => document.querySelectorAll('#merchant option').length === 2);
    await page.selectOption('#merchant', {label:'Principal (owner)'});
    await page.getByRole('button', {name:'Revisar browser-review-a'}).click();
    await page.locator('#review-reload').click();
    await page.waitForFunction(() => document.querySelectorAll('#review-history li').length >= 1);
    await page.locator('#review-clabe').fill('0'.repeat(18));
    await page.locator('#review-tracking').fill('tracking-a');
    await page.selectOption('#merchant', {label:'Segundo comercio (owner)'});
    await page.waitForFunction(() => document.querySelector('#review').hidden);
    assert.equal(await page.locator('#review-clabe').inputValue(), '');
    assert.equal(await page.locator('#review-tracking').inputValue(), '');
    assert.equal(await page.locator('#review-history li').count(), 0);
    const stored = await page.evaluate(() => Object.values(localStorage).join('\n'));
    assert(!stored.includes('tracking-a') && !stored.includes('0'.repeat(18)), 'Bank fields reached browser storage');
    console.log(`BROWSER_REVIEW_${width}PX_OK`);
  } finally { await context.close(); }
}

(async()=>{
  const browser = await chromium.launch({headless:true,args:['--no-sandbox']});
  try { for (const width of [320,375,1280]) await exercise(browser,width); }
  finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1});
