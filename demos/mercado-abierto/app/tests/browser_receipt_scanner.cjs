'use strict';
// Real Chromium + bundled QR decoding; synthetic camera stream and API only.
// The production acceptance harness separately checks the real authenticated API.
const assert=require('node:assert/strict'),http=require('node:http'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {execFileSync}=require('node:child_process');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'../rio_pey_codi/static'),merchant='a'.repeat(32),token='b'.repeat(32)+'.'+'c'.repeat(43);
(async()=>{
 let base,link,qr,calls=[],browser;
 const server=http.createServer(async(req,res)=>{
  if(req.url==='/')return res.end('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/static/receipt-scanner.css"><script defer src="/static/receipt-qr-decoder.js"></script><script defer src="/static/receipt-scanner.js"></script></head><body><select id="merchant"><option value="'+merchant+'">Synthetic Merchant</option></select><button id="receipt-scan-open">Verificar pago con QR</button><button id="logout">Salir</button></body></html>');
  if(req.url==='/qr.png'){res.setHeader('Content-Type','image/png');return res.end(qr);}
  if(req.url.startsWith('/static/')){res.setHeader('Content-Type',req.url.endsWith('.css')?'text/css; charset=utf-8':'application/javascript; charset=utf-8');return res.end(fs.readFileSync(path.join(root,req.url.slice('/static/'.length))));}
  res.setHeader('Content-Type','application/json');
  if(req.url==='/v1/auth/me')return res.end(JSON.stringify({id:'d'.repeat(32),csrf_token:'synthetic-csrf'}));
  if(req.url==='/v1/receipts/verify'){
   let raw='';for await(const chunk of req)raw+=chunk;
   const body=JSON.parse(raw);calls.push({url:req.url,body,csrf:req.headers['x-csrf-token']});
   if(body.qr_text!==link){res.statusCode=422;return res.end(JSON.stringify({detail:'Este QR no es un comprobante de Mercado Abierto.'}));}
   return res.end(JSON.stringify({verified:true,title:'Pago confirmado por pey',merchant_id:merchant,merchant_name:'Synthetic Merchant',order_id:'sale-123',amount_minor:12550,currency:'MXN',verification_source:'PEY_AUTHENTICATED_READBACK',bank_settlement_verified:false}));
  }
  res.statusCode=404;res.end('{}');
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));base='http://127.0.0.1:'+server.address().port;link=base+'/comprobante/'+token;
 const png=path.join(os.tmpdir(),'receipt-scanner-'+process.pid+'.png');
 execFileSync(process.env.RIO_SCANNER_PYTHON||'/workspace/work/pey-venv/bin/python',['-c','import qrcode,sys;qrcode.make(sys.argv[1]).save(sys.argv[2])',link,png]);qr=fs.readFileSync(png);
 try{
  browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
  const context=await browser.newContext({viewport:{width:320,height:740}}),page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{
   Object.defineProperty(window,'BarcodeDetector',{value:undefined,configurable:true});
   window.__cameraCalls=0;window.__stoppedTracks=0;window.__cameraMode='qr';
   Object.defineProperty(navigator,'mediaDevices',{value:{getUserMedia:async()=>{
    window.__cameraCalls++;if(window.__cameraMode==='denied')throw new DOMException('Synthetic denied','NotAllowedError');
    const canvas=document.createElement('canvas');canvas.width=canvas.height=640;const ctx=canvas.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,640,640);
    if(window.__cameraMode==='qr'){const image=new Image();await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=reject;image.src='/qr.png';});ctx.drawImage(image,0,0,640,640);}
    const stream=canvas.captureStream(5);window.__lastCamera=stream;for(const track of stream.getTracks()){const stop=track.stop.bind(track);track.stop=()=>{window.__stoppedTracks++;stop();};}
    if(window.__cameraMode==='pending')return await new Promise(resolve=>{window.__resolveCamera=()=>resolve(stream);});return stream;
   }},configurable:true});
  });
  await page.goto(base);await page.locator('#receipt-scan-open').click();
  assert.equal(await page.evaluate(()=>window.__cameraCalls),0,'opening scanner does not request camera permission');
  await page.locator('#receipt-scan-text').fill(link);await page.locator('#receipt-scan-submit').click();
  await page.locator('#receipt-scan-result[data-state=verified]').waitFor();assert((await page.locator('#receipt-scan-result').textContent()).includes('$125.50'));
  assert.equal(calls.at(-1).csrf,'synthetic-csrf');assert.equal(calls.at(-1).body.merchant_id,merchant);
  await page.locator('#receipt-scan-text').fill('https://foreign.invalid/comprobante/'+token);await page.locator('#receipt-scan-submit').click();
  await page.locator('#receipt-scan-result[data-state=error]').waitFor();assert(calls.every(x=>x.url==='/v1/receipts/verify'));
  await page.locator('#receipt-scan-image').setInputFiles(png);
  await page.locator('#receipt-scan-result[data-state=verified]').waitFor();assert.equal(await page.locator('#receipt-scan-text').inputValue(),link,'bundled jsQR decodes the real QR image');
  await page.locator('#receipt-scan-close').click();assert.equal(await page.locator('#receipt-scan-text').inputValue(),'');
  await page.locator('#receipt-scan-open').click();await page.locator('#receipt-scan-camera').click();
  await page.locator('#receipt-scan-result[data-state=verified]').waitFor();assert.equal(await page.evaluate(()=>window.__cameraCalls),1);assert.equal(await page.evaluate(()=>window.__stoppedTracks),1,'decoded camera stream closes before lookup');
  await page.locator('#receipt-scan-close').click();await page.locator('#receipt-scan-open').click();await page.evaluate(()=>window.__cameraMode='pending');await page.locator('#receipt-scan-camera').click();
  await page.waitForFunction(()=>typeof window.__resolveCamera==='function');await page.locator('#receipt-scan-close').click();await page.evaluate(()=>window.__resolveCamera());
  await page.waitForFunction(()=>window.__stoppedTracks===2);assert(!(await page.locator('#receipt-scanner-dialog').isVisible()),'late camera permission cannot reopen scanner');
  await page.locator('#receipt-scan-open').click();await page.evaluate(()=>window.__cameraMode='blank');await page.locator('#receipt-scan-camera').click();
  await page.waitForFunction(()=>document.getElementById('receipt-scan-video').srcObject!==null);await page.evaluate(()=>window.dispatchEvent(new Event('pagehide')));
  await page.waitForFunction(()=>window.__stoppedTracks===3);assert(!(await page.locator('#receipt-scanner-dialog').isVisible()));
  await page.locator('#receipt-scan-open').click();await page.evaluate(()=>window.__cameraMode='denied');await page.locator('#receipt-scan-camera').click();
  await page.waitForFunction(()=>document.getElementById('receipt-scan-result').dataset.state==='error');assert((await page.locator('#receipt-scan-result').textContent()).includes('No se autorizó la cámara'),await page.locator('#receipt-scan-result').textContent());assert(await page.locator('#receipt-scan-text').isEnabled());
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
  console.log(JSON.stringify({manualLookup:true,bundledQrImage:true,syntheticCameraQr:true,noAutomaticCamera:true,trackCleanup:true,pendingPermissionCleanup:true,permissionFallback:true,width:320,pageErrors:errors.length,verificationRequests:calls.length}));
  await context.close();
 }finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));fs.rmSync(png,{force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
