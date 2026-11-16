"""R012 regression tests; real HTML singlefile loaded in headless Chromium memory.
Browser-level regression incl. validation, cart update/remove/clear and checkout.
All financial operations are local simulations; external links intercepted.
"""
from playwright.sync_api import sync_playwright
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
html=(ROOT/'RIO_PRIMER_COBRO_R013_OFFLINE.html').read_text('utf8')
results=[]
def test(name,fn):
    try: assert fn(), name
    except Exception as e:
        results.append({'name':name,'pass':False,'error':str(e)})
        raise
    else: results.append({'name':name,'pass':True})
def boot(browser,width=390):
    ctx=browser.new_context(viewport={'width':width,'height':844},accept_downloads=True)
    p=ctx.new_page();errors=[]
    p.on('pageerror',lambda err: errors.append(str(err)))
    p.set_content(html)
    p.evaluate('''() => {window._out=[];window.print=()=>window._out.push('print');for(const id of ['ticket-email','ticket-whatsapp'])document.getElementById(id).addEventListener('click',e=>{e.preventDefault();window._out.push(e.currentTarget.href)},true)}''')
    return ctx,p,errors
def add(p,name,qty,price,kind='piece'):
    p.locator('#kind').select_option(kind)
    p.locator('#description').fill(name);p.locator('#qty').fill(str(qty));p.locator('#price').fill(price);p.locator('#add').click()
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True, executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    for size in (390,1280):
        ctx,p,errors=boot(browser,size);prefix=str(size)+'px '
        test(prefix+'script active',lambda:p.evaluate('typeof RioApp')=='object')
        p.locator('#add').click()
        test(prefix+'empty add click gives visible error',lambda:'Escribe el nombre' in p.locator('#line-feedback').inner_text())
        p.locator('#description').fill('Arroz');p.locator('#add').click()
        test(prefix+'missing price gives specific error',lambda:'Indica el precio' in p.locator('#line-feedback').inner_text())
        p.locator('#example-product').click()
        test(prefix+'example prepares form',lambda:p.locator('#price').input_value()=='12.50')
        p.locator('#add').click()
        test(prefix+'example adds to cart',lambda:p.locator('#total').inner_text()=='$25.00 MXN')
        test(prefix+'cart counter',lambda:'1 producto' in p.locator('#cart-count').inner_text())
        add(p,'Jitomate',250,'24.00','weight')
        test(prefix+'mixed cart adds exact',lambda:p.locator('#total').inner_text()=='$31.00 MXN')
        p.locator('#line-qty-0').fill('4')
        p.locator('#lines button:has-text("Actualizar")').first.click()
        test(prefix+'edit qty modifies totals',lambda:p.locator('#total').inner_text()=='$56.00 MXN')
        p.locator('#line-qty-0').fill('x')
        p.locator('#lines button:has-text("Actualizar")').first.click()
        test(prefix+'invalid qty does not mutate total',lambda:p.locator('#total').inner_text()=='$56.00 MXN' and p.locator('#app-notice').get_attribute('data-notification-error')=='true')
        p.locator('#lines button:has-text("Quitar")').last.click()
        test(prefix+'remove changes exact total',lambda:p.locator('#total').inner_text()=='$50.00 MXN')
        add(p,'Pan',1,'10.00')
        test(prefix+'two lines total',lambda:p.locator('#total').inner_text()=='$60.00 MXN')
        p.screenshot(path=str(ROOT/'reports'/('R012_cart_mobile.png' if size==390 else 'R012_cart_desktop.png')),full_page=True)
        p.locator('#start-sale').click()
        test(prefix+'lock cart after checkout',lambda:p.locator('#add').is_disabled() and p.locator('#clear-cart').is_disabled())
        test(prefix+'sale mirrors exact cart',lambda:p.evaluate('RioApp.readState().sale.totalCents')==6000)
        p.locator('#cash-received').fill('100');p.locator('#register-cash').click()
        test(prefix+'cash change',lambda:p.evaluate('RioApp.readState().sale.changeCents')==4000)
        test(prefix+'ticket has cart lines',lambda:all(x in p.locator('#ticket-preview').inner_text() for x in ['Manzana (ejemplo)','Pan','$60.00 MXN']))
        with p.expect_download() as d:p.locator('#ticket-download').click()
        txt=d.value.path().read_text('utf8')
        test(prefix+'ticket downloaded',lambda:'Cambio calculado: $40.00 MXN' in txt)
        p.locator('#ticket-email').click();p.locator('#ticket-whatsapp').click()
        test(prefix+'share links prepared no sends',lambda:p.evaluate('window._out.length')==2)
        p.locator('#tab-informe').click()
        with p.expect_download() as dr:p.locator('#generate').click()
        report=json.loads(dr.value.path().read_text('utf8'))
        test(prefix+'report tests rerun',lambda:report['tests']['failed']==0 and report['tests']['executed_on_click'])
        test(prefix+'report documents cart',lambda:report['cart']['items']==2 and report['cart']['totalCents']==6000)
        test(prefix+'no real payment',lambda:report['real_payment']=='NO')
        p.locator('#tab-vender').click();p.locator('#new-sale').click()
        test(prefix+'reset empties cart',lambda:p.locator('#total').inner_text()=='$0.00 MXN')
        add(p,'Café',1,'20.00')
        p.locator('#clear-cart').click()
        test(prefix+'clear cart works',lambda:p.locator('#cart-count').inner_text()=='0 productos')
        test(prefix+'no page errors',lambda:len(errors)==0)
        test(prefix+'no viewport overflow',lambda:p.evaluate('document.documentElement.scrollWidth <= innerWidth+2'))
        p.screenshot(path=str(ROOT/'reports'/('R012_mobile.png' if size==390 else 'R012_desktop.png')),full_page=True)
        ctx.close()
    browser.close()
(ROOT/'reports'/'R012_CART_AUDIT.json').write_text(json.dumps({'checks':len(results),'passed':sum(x['pass'] for x in results),'failed':sum(not x['pass'] for x in results),'results':results,'browser':'Chromium memory-injected HTML','android_physical':'NOT_OBSERVED','payment_provider':'NONE'},ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps({'checks':len(results),'passed':sum(x['pass'] for x in results),'status':'PASS'},ensure_ascii=False))
