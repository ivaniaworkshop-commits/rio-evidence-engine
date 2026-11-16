// Validate the native constraint against the served HTML in Chromium.
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const base=`http://127.0.0.1:${process.env.RIO_BROWSER_PORT||'8765'}`;
(async()=>{
  const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
  try {
    const page=await browser.newPage();
    await page.goto(base);
    const check=value=>page.locator('#sale-order').evaluate((element,value)=>{
      element.value=value;
      return {mismatch:element.validity.patternMismatch, valid:element.validity.valid};
    },value);
    for(const value of ['', 'A', 'sale-123', 'X.y_z', 'a'.repeat(70)]){
      const state=await check(value);
      assert.equal(state.valid,true,`expected valid: ${value}`);
    }
    for(const value of ['-bad','a b','a@b','a'.repeat(71),'á']){
      const state=await check(value);
      assert.equal(state.mismatch,true,`expected pattern mismatch: ${value}`);
    }
    console.log('BROWSER_SHARED_SALE_NATIVE_VALIDITY_OK');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1});
