/** R019 public checkout E2E. Real mouse events in isolated Chrome; no bank operations. */
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdtemp,readFile,readdir,mkdir,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
const configuredBase=process.env.RIO_TEST_BASE_URL||'https://rio-primer-cobro-frontdesk.vercel.app/';
const parsedBase=new URL(configuredBase);
const hostOK=parsedBase.hostname==='rio-primer-cobro-frontdesk.vercel.app'||/^rio-primer-cobro-frontdesk-[a-z0-9]+-ivaniaworkshop-6855\.vercel\.app$/.test(parsedBase.hostname);
if(parsedBase.protocol!=='https:'||!hostOK||parsedBase.username||parsedBase.password||parsedBase.pathname!=='/'||parsedBase.search||parsedBase.hash||parsedBase.port)throw Error('UNAPPROVED_RIO_TEST_BASE_URL');
const base=parsedBase.origin+'/';
const chrome=process.env.CHROME_BIN||'google-chrome';
const directory=await mkdtemp(join(tmpdir(),'rio-r019-public-'));
const downloads=join(directory,'downloads');
let child,ws,idx=0;
const pending=new Map(),checks=[];
const check=(title,ok)=>{checks.push({name:title,pass:Boolean(ok)});if(!ok)throw Error('CHECK_FAILED: '+title)};
async function poll(fn,limit=100){let err;for(let i=0;i<limit;i++){try{let r=await fn();if(r)return r}catch(e){err=e}await delay(150)}throw err||Error('TIMEOUT_WAITING_BROWSER')}
async function call(method,params={}){let id=++idx;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP_TIMEOUT '+method))},18000);pending.set(id,{resolve:(x)=>{clearTimeout(timer);resolve(x)},reject:(e)=>{clearTimeout(timer);reject(e)}});ws.send(JSON.stringify({id,method,params}))})}
async function js(code){let r=await call('Runtime.evaluate',{expression:code,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error('BROWSER_JS_EXCEPTION '+JSON.stringify(r.exceptionDetails));return r.result?.value}
async function loaded(){return poll(()=>js('document.readyState==="complete" && Boolean(window.RioApp && window.RioQR)'))}
async function click(selector){const r=await js('(()=>{let e=document.querySelector('+JSON.stringify(selector)+');if(!e)return {error:"missing"};e.scrollIntoView({block:"center",inline:"nearest"});const b=e.getBoundingClientRect();return {x:b.x+b.width/2,y:b.y+b.height/2,w:b.width,h:b.height,disabled:e.disabled}})()');if(r.error||r.disabled||r.w<1||r.h<1)throw Error('NOT_CLICKABLE '+selector+' '+JSON.stringify(r));await call('Input.dispatchMouseEvent',{type:'mouseMoved',x:r.x,y:r.y});await call('Input.dispatchMouseEvent',{type:'mousePressed',x:r.x,y:r.y,button:'left',clickCount:1});await call('Input.dispatchMouseEvent',{type:'mouseReleased',x:r.x,y:r.y,button:'left',clickCount:1});await delay(170)}
async function state(){return js('window.RioApp.readState()')}
async function navigate(url){await call('Page.navigate',{url});await poll(()=>js('document.readyState==="complete"'))}
try{
 await mkdir(downloads,{recursive:true});
 child=spawn(chrome,['--headless=new','--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--no-first-run','--remote-debugging-port=0','--window-size=393,852', '--user-data-dir='+directory,'about:blank'],{stdio:'ignore'});
 const port=await poll(async()=>Number((await readFile(join(directory,'DevToolsActivePort'),'utf8')).split('\n')[0]));
 const target=await poll(async()=>{const l=await (await fetch('http://127.0.0.1:'+port+'/json/list')).json();return l.find(x=>x.type==='page'&&x.webSocketDebuggerUrl)});
 ws=new WebSocket(target.webSocketDebuggerUrl);
 ws.onmessage=(e)=>{let m=JSON.parse(e.data);if(!m.id)return;let cb=pending.get(m.id);if(!cb)return;pending.delete(m.id);m.error?cb.reject(Error(JSON.stringify(m.error))):cb.resolve(m.result||{})};
 await new Promise((ok,no)=>{ws.onopen=ok;ws.onerror=no;setTimeout(()=>no(Error('WS_TIMEOUT')),15000)});
 await call('Page.enable');await call('Runtime.enable');
 await call('Emulation.setDeviceMetricsOverride',{width:393,height:852,deviceScaleFactor:1,mobile:true});
 await call('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:downloads,eventsEnabled:true});
 await navigate(base);
 check('public front desk HTML',await js('document.title.includes("RÍO Primer Cobro")'));
 check('public GitHub repository linked',await js('Boolean([...document.querySelectorAll("a")].some(a=>a.href.includes("github.com")))'));
 await click('#abrir');await loaded();
 check('front desk link opens app',await js('location.pathname.endsWith("/app.html")'));
 check('cart starts empty',(await state()).lines.length===0);
 await click('#example-product');await click('#add');
 let s=await state();check('add product clicked and item present',s.lines.length===1);
 check('cent-exact cart amount',s.lines[0].amountCents===2500);
 await click('input[name="method"][value="qr"]');
 check('QR payment mode selected',await js('document.querySelector("input[name=method]:checked").value==="qr"'));
 await click('#start-sale');s=await state();
 check('QR sale created',s.sale?.method==='qr'&&s.sale.totalCents===2500);
 check('not a bank-confirmed payment',s.sale?.realPaymentConfirmed===false);
 check('ticket generated',await js('document.querySelector("#ticket-preview").textContent.includes("25.00")'));
 await click('#generate-qr');s=await state();
 check('QR SVG visible',await js('Boolean(document.querySelector("#qr-code svg"))'));
 check('QR binds sale reference',s.qrPayload?.includes(s.sale.saleId));
 check('QR binds exact cents',s.qrPayload?.includes('MXN-CENTAVOS=2500'));
 check('QR clearly nonpayable',s.qrPayload?.includes('NO-PAGABLE'));
 const folio=s.sale.saleId,ticket=await js('document.querySelector("#ticket-preview").textContent');
 await call('Page.reload',{ignoreCache:true});await loaded();s=await state();
 check('sale restored by real browser reload',s.sale?.saleId===folio);
 check('ticket unchanged after reload',await js('document.querySelector("#ticket-preview").textContent')===ticket);
 check('restored sale not bank-confirmed',s.sale?.realPaymentConfirmed===false);
 await click('#generate-qr');s=await state();
 check('QR regenerable after reload',s.qrPayload?.includes(folio));
 await click('#ticket-download');
 const files=await poll(async()=>{let f=await readdir(downloads);return f.some(x=>x.endsWith('.txt'))?f:null},40);
 check('ticket downloaded to isolated browser directory',files.some(x=>x.endsWith('.txt')));
 await click('#new-sale');s=await state();
 check('new-sale clears cart and active sale',s.lines.length===0&&!s.sale);
 check('previous sale stored in history',s.history.some(x=>x.sale.saleId===folio));
 await click('#history-list button');s=await state();
 check('ticket restored from local history',s.sale?.saleId===folio&&s.sale.totalCents===2500);
 // Separate cash example: manual declaration is not a bank transaction.
 await click('#new-sale');
 await click('#example-product');await click('#add');
 await click('input[name="method"][value="cash"]');
 await click('#start-sale');s=await state();
 check('cash method selected',s.sale?.method==='cash'&&s.sale.totalCents===2500);
 check('cash receipt entry visible',await js('Boolean(document.querySelector("#cash-received"))'));
 const receiptEntry=await js('(()=>{let x=document.querySelector("#cash-received");x.value="50.00";x.dispatchEvent(new Event("input",{bubbles:true}));return x.value})()');
 check('cash amount entered in browser',receiptEntry==='50.00');
 check('change calculated before confirmation',await js('document.querySelector("#cash-change").textContent.includes("25.00")'));
 await click('#register-cash');s=await state();
 check('manual cash registration recorded',s.sale?.cashReceivedCents===5000);
 check('exact change persisted',s.sale?.changeCents===2500);
 check('cash payment never bank-confirmed',s.sale?.realPaymentConfirmed===false);
 check('cash ticket visible',await js('document.querySelector("#ticket-card").hidden===false && document.querySelector("#ticket-preview").textContent.includes("50.00")'));
 // Report must run internal tests and deliver actual JSON to isolated browser download directory.
 await click('#tab-informe');await click('#generate');
 const reportFiles=await poll(async()=>{let f=await readdir(downloads);return f.some(x=>x.endsWith('.json'))?f:null},50);
 const reportName=reportFiles.find(x=>x.endsWith('.json'));
 const json=JSON.parse(await readFile(join(downloads,reportName),'utf8'));
 check('report generated on user click',json.tests?.executed_on_click===true);
 check('report internal regressions executed',json.tests?.failed===0&&json.tests?.passed>0);
 check('report never claims actual digital payment',json.real_payment==='NO'&&json.payment_provider==='NONE');
 console.log(JSON.stringify({schema:'RIO_PUBLIC_CHECKOUT_E2E_R019',status:'PASS',browser:'GITHUB_RUNNER_CHROME_HEADLESS',viewport:'393x852',site:base,authentication:'FRESH_PROFILE_NONE',real_bank_payment:false,android_physical:'NOT_OBSERVED',checks_passed:checks.length,checks_total:checks.length,checks},null,2));
}catch(error){let debug={};try{debug=await js('({url:location.href,title:document.title,ready:document.readyState,notification:document.getElementById("app-notice")?.textContent,html:document.body?.textContent.slice(0,400)})')}catch{}
 console.error(JSON.stringify({schema:'RIO_PUBLIC_CHECKOUT_E2E_R019',status:'FAIL',error:String(error?.stack||error),checks,debug}));process.exitCode=2;
}finally{try{ws?.close()}catch{}try{child?.kill('SIGKILL')}catch{}await delay(150);await rm(directory,{recursive:true,force:true}).catch(()=>{})}
