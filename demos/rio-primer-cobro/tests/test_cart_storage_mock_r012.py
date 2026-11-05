"""Mocked storage contract only. Does NOT certify persistence in a physical browser."""
from pathlib import Path
from playwright.sync_api import sync_playwright
import json
root=Path(__file__).resolve().parents[1]
s=(root/'RIO_PRIMER_COBRO_R012_OFFLINE.html').read_text('utf8')
prefix='''<script>window.__mockSave=window.__mockSave||{};Object.defineProperty(window,'localStorage',{configurable:true,value:{getItem:k=>window.__mockSave[k]||null,setItem:(k,v)=>window.__mockSave[k]=v,removeItem:k=>delete window.__mockSave[k]}});</script>'''
s=s.replace('<head>','<head>'+prefix,1)
with sync_playwright() as pw:
 b=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 p=b.new_page();p.set_content(s)
 p.locator('#description').fill('Limón');p.locator('#price').fill('17.50');p.locator('#add').click()
 assert p.locator('#total').inner_text()=='$17.50 MXN'
 assert '"schema":"RIO_CART_R012"' in p.evaluate('window.__mockSave["RIO_PRIMER_COBRO_R012_CART"]')
 p.set_content(s)
 assert p.locator('#total').inner_text()=='$17.50 MXN'
 p.locator('#clear-cart').click()
 p.set_content(s)
 assert p.locator('#total').inner_text()=='$0.00 MXN'
 b.close()
print(json.dumps({'mocked_storage_roundtrip':'PASS','checks':3,'real_localStorage_origin':'NOT_VERIFIED'}))
