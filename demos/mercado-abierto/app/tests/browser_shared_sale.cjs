// Real browser contexts, synthetic accounts and a loopback-only timeout provider.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {chromium} = require('playwright');
const base = `http://127.0.0.1:${process.env.RIO_BROWSER_PORT || '8765'}`;
const counter = process.env.RIO_BROWSER_COUNTER;
const attempts = () => fs.existsSync(counter) ? fs.readFileSync(counter,'utf8').trim().split('\n').filter(Boolean).length : 0;

async function login(context,email){
  const page=await context.newPage();
  await page.goto(base);
  await page.locator('#login input[name="email"]').fill(email);
  await page.locator('#login input[name="password"]').fill('synthetic-password-123');
  await page.locator('#login button').click();
  await page.locator('#dashboard').waitFor({state:'visible'});
  await page.waitForFunction(()=>Array.from(document.querySelectorAll('#merchant option'))
    .some(option=>option.textContent.startsWith('Principal')));
  const labels=await page.locator('#merchant option').allTextContents();
  await page.selectOption('#merchant',{label:labels.find(label=>label.startsWith('Principal'))});
  await page.locator('#charge input[name="order_id"]').fill('sale-123');
  await page.locator('#charge input[name="concept"]').fill('Pedido compartido');
  await page.locator('#charge input[name="amount"]').fill('150.00');
  return page;
}

(async()=>{
  const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
  try {
    const firstContext=await browser.newContext({viewport:{width:390,height:844}});
    const secondContext=await browser.newContext({viewport:{width:390,height:844}});
    for(const [context,seed] of [[firstContext,101],[secondContext,202]]){
      await context.addInitScript(value=>{
        const original=crypto.getRandomValues.bind(crypto);
        crypto.getRandomValues=values=>values instanceof Uint32Array && values.length===1 ?
          (values[0]=value,values) : original(values);
      },seed);
    }
    let lookups=0; const waiting=[];
    async function forceConcurrentPreflight(route){
      if(lookups++<2){
        waiting.push(route);
        if(waiting.length===2) await Promise.all(waiting.map(r=>r.fulfill({status:404,
          contentType:'application/json',body:JSON.stringify({detail:'Payment intent not found',code:'ORDER_NOT_FOUND'})})));
      } else await route.continue();
    }
    await firstContext.route('**/checkout-orders/sale-123',forceConcurrentPreflight);
    await secondContext.route('**/checkout-orders/sale-123',forceConcurrentPreflight);
    const first=await login(firstContext,'browser@example.com');
    const second=await login(secondContext,'cashier@example.com');
    await Promise.all([first.locator('#charge button').click(),second.locator('#charge button').click()]);
    for(let i=0;i<100&&attempts()<1;i++)await new Promise(resolve=>setTimeout(resolve,50));
    assert.equal(attempts(),1);
    await Promise.race([
      first.waitForFunction(()=>document.querySelector('#folio').textContent==='sale-123'),
      second.waitForFunction(()=>document.querySelector('#folio').textContent==='sale-123'),
    ]);
    await first.waitForFunction(()=>!document.querySelector('#charge button').disabled);
    await second.waitForFunction(()=>!document.querySelector('#charge button').disabled);
    assert.equal(attempts(),1);
    const saved=async page=>page.evaluate(()=>Object.values(localStorage).map(JSON.parse)[0]);
    const [saved1,saved2]=await Promise.all([saved(first),saved(second)]);
    assert.equal(saved1.id,'sale-123'); assert.equal(saved2.id,'sale-123');
    assert.equal(saved1.reference,saved2.reference);
    assert(await first.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));

    const thirdContext=await browser.newContext({viewport:{width:390,height:844}});
    const third=await login(thirdContext,'browser@example.com');
    await third.locator('#charge button').click();
    await third.waitForFunction(()=>document.querySelector('#folio').textContent==='sale-123');
    assert.equal(attempts(),1);
    const fourthContext=await browser.newContext({viewport:{width:390,height:844}});
    const fourth=await login(fourthContext,'cashier@example.com');
    await fourth.locator('#charge input[name="amount"]').fill('151.00');
    await fourth.locator('#charge button').click();
    await fourth.waitForFunction(()=>document.querySelector('#notice').textContent.includes('otros datos'));
    assert.equal(attempts(),1);
    console.log('BROWSER_SHARED_SALE_TWO_USERS_RACE_OK');
    console.log('BROWSER_SHARED_SALE_EXISTING_AND_MISMATCH_OK');
    await firstContext.close(); await secondContext.close(); await thirdContext.close(); await fourthContext.close();
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1});
