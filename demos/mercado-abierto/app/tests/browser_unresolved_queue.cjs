// Two isolated browser contexts against the loopback-only synthetic fixture.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {chromium} = require('playwright');
const base = `http://127.0.0.1:${process.env.RIO_BROWSER_PORT || '8765'}`;
const counter = process.env.RIO_BROWSER_COUNTER;
const attempts = () => fs.existsSync(counter) ? fs.readFileSync(counter,'utf8').trim().split('\n').filter(Boolean).length : 0;

async function login(context) {
  const page = await context.newPage();
  await page.goto(base);
  await page.locator('#login input[name="email"]').fill('browser@example.com');
  await page.locator('#login input[name="password"]').fill('synthetic-password-123');
  await page.locator('#login button').click();
  await page.locator('#dashboard').waitFor({state:'visible'});
  await page.waitForFunction(() => document.querySelectorAll('#merchant option').length === 2);
  const labels = await page.locator('#merchant option').allTextContents();
  await page.selectOption('#merchant', {label:labels.find(label => label.startsWith('Principal'))});
  await page.locator('#unresolved li').filter({hasText:'old-queue-order'}).waitFor();
  return page;
}

(async()=>{
  const browser = await chromium.launch({headless:true,args:['--no-sandbox']});
  try {
    const firstContext = await browser.newContext({viewport:{width:390,height:844}});
    const secondContext = await browser.newContext({viewport:{width:390,height:844}});
    const first = await login(firstContext);
    assert.equal(await first.locator('#history li').filter({hasText:'old-queue-order'}).count(),0);
    await first.locator('#unresolved li').filter({hasText:'old-queue-order'}).getByRole('button',{name:'Recuperar'}).click();
    await first.waitForFunction(() => document.querySelector('#folio').textContent === 'old-queue-order');

    const second = await login(secondContext);
    assert.equal(await second.evaluate(() => Object.keys(localStorage).length),0);
    await second.locator('#unresolved li').filter({hasText:'old-queue-order'}).getByRole('button',{name:'Recuperar'}).click();
    await second.waitForFunction(() => document.querySelector('#folio').textContent === 'old-queue-order');
    assert.equal(await second.locator('#charge input[name="amount"]').inputValue(),'150.00');
    assert.equal(await second.locator('#charge input[name="concept"]').inputValue(),'Pedido anterior');
    await second.locator('#charge button').click();
    await second.waitForFunction(() => document.querySelector('#notice').textContent.includes('Solicitud de práctica'));
    assert.equal(attempts(),0,'replay of the recovered order must not call the provider');
    assert(await second.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    console.log('BROWSER_OLD_QUEUE_SEPARATE_CONTEXTS_OK');
    console.log('BROWSER_QUEUE_NO_PROVIDER_RETRY_OK');
    await firstContext.close(); await secondContext.close();
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1});
