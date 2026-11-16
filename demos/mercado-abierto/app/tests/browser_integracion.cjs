'use strict';
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { randomBytes } = require('node:crypto');
const path = require('node:path');
const { chromium } = require('playwright');
const port=Number(process.env.RIO_DEMO_PORT || 18830), origin=`http://127.0.0.1:${port}`;
const python=process.env.RIO_DEMO_PYTHON || 'python3';
const launcher=process.env.RIO_DEMO_LAUNCHER || path.join(__dirname,'..','..','iniciar_unificada.py');
const marker=randomBytes(16).toString('hex');
const server=spawn(python,[launcher,'--port',String(port),'--test-marker',marker],{stdio:'ignore'});
let serverError;
server.on('error',error=>{serverError=error});
let browser, phase='iniciar';
const text = async(page,selector)=> (await page.locator(selector).innerText()).trim();
(async()=>{
  try {
    let ready=false;
    for(let i=0;i<100;i++) {
      if(serverError)throw serverError;
      if(server.exitCode!==null || server.signalCode!==null)throw Error('El servidor de prueba terminó antes de estar disponible.');
      try {
        const response=await fetch(origin+'/__rio_test_'+marker);
        if(response.ok && (await response.json()).marker===marker){ready=true;break;}
      } catch(_){}
      await new Promise(r=>setTimeout(r,100));
    }
    if(!ready)throw Error('No se identificó el servidor de prueba; comprueba que el puerto esté libre.');
    const publicStatus=await (await fetch(origin+'/public-status')).json();
    assert.equal(publicStatus.mode,'DEMO');
    assert.equal(publicStatus.live_payments_enabled,false);
    browser=await chromium.launch({headless:true,args:['--no-sandbox']});
    const context=await browser.newContext({viewport:{width:390,height:844},serviceWorkers:'allow'});
    const page=await context.newPage();
    page.setDefaultTimeout(12000);
    const checkoutRequests=[];
    page.on('request',req=>{if(req.method()==='POST'&&req.url().includes('/v1/checkout/qr'))checkoutRequests.push(req.url())});
    phase='inicio de sesión ficticio';
    await page.goto(origin+'/',{waitUntil:'networkidle'});
    await page.locator('#login-submit').waitFor({state:'visible'});
    await page.waitForFunction(()=>!document.querySelector('#login-submit').disabled);
    await page.locator('#login input[name=email]').fill('evaluacion@example.org');
    await page.locator('#login input[name=password]').fill('RioDemo-2026-Local');
    await page.locator('#login-submit').click();
    await page.locator('#dashboard').waitFor({state:'visible'});
    await page.waitForFunction(()=>document.querySelector('#merchant').value && !document.querySelector('#charge button').disabled);
    phase='traslado de la cesta ficticia';
    await page.locator('a[href="/static/unificada/mercado/index.html"]').click();
    await page.locator('#rio-basket-to-cash').click();
    await page.locator('#rio-basket-panel').waitFor({state:'visible'});
    await page.locator('#rio-import-basket').click();
    assert.match(await text(page,'#cart-count'),/10/);
    assert.match(await text(page,'#total'),/1,500\.00/);
    phase='venta QR y traslado a cuenta';
    await page.locator('input[name=method][value=qr]').check();
    await page.locator('#start-sale').click();
    const sale=await page.evaluate(()=>window.RioApp.readState().sale);
    assert.equal(sale.method,'qr'); assert.equal(sale.totalCents,150000); assert.equal(sale.realPaymentConfirmed,false);
    await page.locator('#rio-sale-to-gateway').click();
    await page.locator('#dashboard').waitFor({state:'visible'});
    await page.waitForFunction(()=>document.querySelector('#merchant').value && !document.querySelector('#charge button').disabled);
    await page.locator('#rio-gateway-panel').waitFor({state:'visible'});
    assert.match(await text(page,'#rio-gateway-transfer-status'),new RegExp(sale.saleId));
    await page.locator('#rio-gateway-import').click();
    await page.waitForFunction(()=>document.querySelector('#amount').value==='1500.00');
    assert.equal(await page.locator('#sale-order').inputValue(),sale.saleId);
    assert.equal(checkoutRequests.length,0,'el traslado no debe crear una solicitud');
    phase='solicitud local de práctica';
    await page.locator('#charge button').click();
    await page.locator('#result').waitFor({state:'visible'});
    assert.equal(checkoutRequests.length,1);
    assert.ok((await text(page,'#qrstate')).length>0);
    assert.match(await text(page,'#notice'),/práctica|verificar/i);
    phase='preparación de caché y desconexión';
    await page.locator('a[href="/static/unificada/caja/index.html"]').first().click();
    await page.waitForFunction(()=>document.querySelector('#rio-offline-status').textContent.includes('preparados sin conexión'),null,{timeout:20000});
    await context.setOffline(true);
    await page.reload({waitUntil:'load'});
    assert.equal(await page.locator('input[name=method][value=qr]').isChecked(),true);
    const restored=await page.evaluate(()=>window.RioApp.readState().sale);
    assert.equal(restored.saleId,sale.saleId);assert.equal(restored.totalCents,150000);
    assert.match(await text(page,'#cart-storage-status'),/guardad|recuperad/i);
    const apiUnavailable=await page.evaluate(async()=>{try{await fetch('/public-status',{cache:'no-store'});return false}catch(_){return true}});
    assert.equal(apiUnavailable,true,'la API debe requerir red y no estar en caché');
    phase='mercado sin red';
    await page.locator('a[href="/static/unificada/mercado/index.html"]').click();
    await page.locator('#rio-basket-to-cash').waitFor({state:'visible'});
    await page.waitForFunction(()=>document.querySelector('#rio-offline-status').textContent.includes('preparados sin conexión'));
    assert.match(await text(page,'#rio-offline-status'),/preparados sin conexión/i);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,'la página no debe desbordar horizontalmente en móvil');
    await page.locator('a[href="/static/unificada/caja/index.html"]').first().click();
    await page.waitForFunction(()=>window.RioApp && window.RioApp.readState);
    assert.equal((await page.evaluate(()=>window.RioApp.readState().sale)).saleId,sale.saleId);
    console.log(JSON.stringify({result:'PASS',scenario:'authenticated-synthetic-browser-offline',browser:browser.version(),viewport:'390x844',offline:true,apiOffline:true,items:10,amountCents:150000,checkoutRequestsBeforeExplicitClick:0,checkoutRequestsAfterExplicitClick:1,storageRestored:true}));
    await context.close();
  } catch(e){ console.error('FAIL at '+phase+'\n'+(e.stack||e));process.exitCode=1; }
  finally { if(browser)await browser.close(); server.kill('SIGTERM'); }
})();
