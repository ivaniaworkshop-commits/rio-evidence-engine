"""R014 Chromium in-memory UI and same-page mock storage continuity.
Not a real browser restart nor physical Android test.
"""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
HTML=(ROOT/'RIO_PRIMER_COBRO_R014_OFFLINE.html').read_text(encoding='utf-8')
results=[]
def ck(name,ok):
 results.append({'name':name,'pass':bool(ok)})
 if not ok: raise AssertionError(name)

MOCK='''() => {window.__store={};Object.defineProperty(window,'localStorage',{configurable:true,get(){return {getItem(k){return Object.prototype.hasOwnProperty.call(window.__store,k)?window.__store[k]:null},setItem(k,v){window.__store[k]=String(v)},removeItem(k){delete window.__store[k]}}}});window.confirm=()=>true;}'''
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
 for width,height,label in [(390,844,'mobile'),(1280,900,'desktop')]:
  context=browser.new_context(viewport={'width':width,'height':height},accept_downloads=True)
  page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.evaluate(MOCK);page.set_content(HTML,wait_until='load')
  ck(label+' app loaded',page.locator('#export-backup').is_visible())
  ck(label+' no horizontal overflow',page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1'))
  page.locator('#example-product').click();page.locator('#add').click()
  ck(label+' cart sum','$25.00' in page.locator('#total').inner_text())
  page.locator('#start-sale').click()
  saleid=page.evaluate('window.RioApp.readState().sale.saleId')
  ck(label+' sale persisted',page.evaluate('!!localStorage.getItem("RIO_PRIMER_COBRO_R014_SESSION_V1")'))
  page.locator('#cash-received').fill('30.00');page.locator('#register-cash').click()
  ck(label+' cash ticket change', 'Cambio calculado: $5.00' in page.locator('#ticket-preview').inner_text())
  ck(label+' paid cash only manually',page.evaluate('window.RioApp.readState().sale.state')=='CASH_REPORTED_RECEIVED')
  page.set_content(HTML,wait_until='load')
  ck(label+' recover same sale id',page.evaluate('window.RioApp.readState().sale.saleId')==saleid)
  ck(label+' recovered cash change', 'Cambio calculado: $5.00' in page.locator('#ticket-preview').inner_text())
  ck(label+' history status recovered',page.evaluate('window.RioApp.readState().persistenceStatus')=='RECOVERED_LOCAL')
  page.locator('#new-sale').click()
  ck(label+' active archived',len(page.evaluate('window.RioApp.readState().history'))==1)
  ck(label+' old ticket in list',saleid in page.locator('#history-list').inner_text())
  page.set_content(HTML,wait_until='load')
  ck(label+' history survived reload',saleid in page.locator('#history-list').inner_text())
  page.locator('#history-list button').first.click()
  ck(label+' restore archived sale',page.evaluate('window.RioApp.readState().sale.saleId')==saleid)
  ck(label+' reprinted receipt', 'Cambio calculado: $5.00' in page.locator('#ticket-preview').inner_text())
  ck(label+' share remains optional',page.locator('#ticket-email').get_attribute('href').startswith('mailto:') and page.locator('#ticket-whatsapp').get_attribute('href').startswith('https://wa.me/'))
  with page.expect_download() as dl:page.locator('#export-backup').click()
  raw=Path(dl.value.path()).read_text()
  backup=json.loads(raw)
  ck(label+' backup contains active',backup['active']['sale']['saleId']==saleid)
  ck(label+' backup no real payment',backup['active']['sale']['realPaymentConfirmed'] is False)
  # test new QR flow and recovering QR state
  page.locator('#new-sale').click();page.locator('#example-product').click();page.locator('#add').click();page.locator('input[name="method"][value="qr"]').check();page.locator('#start-sale').click();page.locator('#generate-qr').click()
  ck(label+' QR generated',page.locator('#qr-code svg').count()==1)
  ck(label+' demo not bank', 'NO-PAGABLE' in page.locator('#qr-payload').inner_text())
  qrid=page.evaluate('window.RioApp.readState().sale.saleId')
  page.set_content(HTML,wait_until='load')
  ck(label+' QR sale recover',page.evaluate('window.RioApp.readState().sale.saleId')==qrid)
  ck(label+' QR regenerated on demand',page.locator('#generate-qr').count()==1)
  page.locator('#generate-qr').click()
  ck(label+' QR regenerated same sale',qrid in page.locator('#qr-payload').inner_text())
  page.locator('#tab-informe').click()
  with page.expect_download() as dl:page.locator('#generate').click()
  report=json.loads(Path(dl.value.path()).read_text())
  ck(label+' report runs tests on click',report['tests']['executed_on_click'])
  ck(label+' report internal all pass',report['tests']['failed']==0)
  ck(label+' report marks no real payment',report['real_payment']=='NO')
  ck(label+' report includes persisted sale',report['persistence']['status'] in ('SAVED_LOCAL','RECOVERED_LOCAL'))
  (ROOT/'reports'/f'R014_report_{label}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
  page.locator('#tab-vender').click();page.screenshot(path=str(ROOT/'reports'/f'R014_{label}.png'),full_page=True)
  # Import backed-up sale from prior cash ticket.
  page.locator('#import-backup').set_input_files({'name':'backup.json','mimeType':'application/json','buffer':raw.encode('utf-8')})
  ck(label+' user imported original sale',page.evaluate('window.RioApp.readState().sale.saleId')==saleid)
  # Corrupted backup must be rejected without replacing current sale
  page.locator('#import-backup').set_input_files({'name':'bad.json','mimeType':'application/json','buffer':b'{not json'})
  ck(label+' bad import rejected',page.evaluate('window.RioApp.readState().sale.saleId')==saleid)
  ck(label+' no page errors',not errors)
  print(label,'checks',sum(x['name'].startswith(label) for x in results),'internal',report['tests']['passed'],'/',report['tests']['total'],'errors',errors)
  context.close()
 # fault state: preserve raw bad source
 context=browser.new_context();page=context.new_page();page.evaluate(MOCK)
 page.evaluate('localStorage.setItem("RIO_PRIMER_COBRO_R014_SESSION_V1", "{bad stored")')
 page.set_content(HTML,wait_until='load')
 ck('corruption is locked',page.evaluate('window.RioApp.readState().persistenceStatus')=='CORRUPT_PRESERVED')
 ck('corruption raw bytes preserved',page.evaluate('localStorage.getItem("RIO_PRIMER_COBRO_R014_SESSION_V1")')=='{bad stored')
 page.locator('#example-product').click();page.locator('#add').click();page.locator('#start-sale').click()
 ck('corrupt backup not silently overwritten',page.evaluate('localStorage.getItem("RIO_PRIMER_COBRO_R014_SESSION_V1")')=='{bad stored')
 context.close();browser.close()
(ROOT/'reports'/'R014_E2E.json').write_text(json.dumps({'tests':len(results),'passed':sum(r['pass'] for r in results),'failed':sum(not r['pass'] for r in results),'scope':'CHROMIUM_IN_MEMORY_LOCALSTORAGE_MOCK_NOT_PHYSICAL_RESTART','cases':results},ensure_ascii=False,indent=2))
print('R014 ALL',len(results),'PASS')
