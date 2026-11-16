"""Loopback E2E: real SQLite signup/token/cookie/redirect; no SMTP or payments."""
import json, os, socket, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

if len(sys.argv)>1 and sys.argv[1]=='--serve':
    assert os.environ.get('RIO_LOCAL_ONLY')=='1'
    import uvicorn
    from rio_pey_codi.platform import Settings, create_platform
    app=create_platform(Settings(database_url='sqlite+pysqlite:///'+sys.argv[2]))
    @app.get('/_fixture/link')
    def link(email: str):
        return next({'token':x['token']} for x in reversed(app.state.mailer.outbox) if x['email']==email and x['kind']=='verify')
    uvicorn.run(app,host='127.0.0.1',port=int(sys.argv[3]),access_log=False,log_level='error')
    raise SystemExit

from playwright.sync_api import sync_playwright
server_python=sys.argv[1] if len(sys.argv)>1 else sys.executable
root=Path(__file__).resolve().parents[1]
with socket.socket() as sock:
    sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
base=f'http://127.0.0.1:{port}'
with tempfile.TemporaryDirectory() as tmp:
    env={**os.environ,'RIO_LOCAL_ONLY':'1','PYTHONPATH':str(root)}
    proc=subprocess.Popen([server_python,__file__,'--serve',tmp+'/local.sqlite',str(port)],cwd=root,env=env)
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(base+'/public-status',timeout=1) as r:
                    assert json.load(r)['environment']=='local'
                break
            except OSError: time.sleep(.1)
        else:raise AssertionError('local fixture did not start')
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
            context=browser.new_context(viewport={'width':390,'height':844})
            page=context.new_page();errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(base)
            page.locator('[data-auth-view="login"] [data-auth-open="signup"]').click()
            page.locator('#signup input[name=business_name]').fill('Synthetic browser business')
            page.locator('#signup-email').fill('browser-verify@example.org')
            page.locator('#signup input[name=password]').fill('Synthetic-password-123')
            page.locator('#signup-submit:not([disabled])').click()
            page.locator('[data-auth-view="verify"]:visible').wait_for()
            token=context.request.get(base+'/_fixture/link?email=browser-verify@example.org').json()['token']
            tab=context.new_page();tab.on('pageerror',lambda e:errors.append(str(e)))
            tab.route('**/public-status',lambda route:route.fulfill(status=503,json={'detail':'synthetic status outage'}),times=1)
            tab.goto(base+'/verify-email#token='+token)
            tab.wait_for_url(base+'/');tab.locator('#dashboard:visible').wait_for()
            page.wait_for_url(base+'/');page.locator('#dashboard:visible').wait_for()
            assert context.request.get(base+'/v1/auth/me').json()['verified'] is True
            assert all('token' not in p.url for p in [page,tab])
            # Same link cannot authenticate another browser.
            outsider=browser.new_context();bad=outsider.new_page()
            bad.goto(base+'/verify-email#token='+token)
            bad.locator('#verification-status').filter(has_text='ya se utilizó').wait_for()
            assert outsider.request.get(base+'/v1/auth/me').status==401
            outsider.close()
            # Query token survives an unrelated hash; transient errors can retry.
            for scenario in ['query','retry']:
                ctx=browser.new_context(viewport={'width':390,'height':844});p=ctx.new_page()
                email=scenario+'@example.org'
                assert ctx.request.post(base+'/v1/auth/signup',data={'email':email,'password':'Synthetic-password-123','business_name':'Synthetic'}).status==201
                tok=ctx.request.get(base+'/_fixture/link?email='+email).json()['token']
                if scenario=='retry':p.route('**/v1/auth/verify-email',lambda route:route.fulfill(status=503,json={'detail':'Intenta de nuevo'}))
                p.goto(base+'/verify-email?token='+tok+'#section')
                if scenario=='retry':
                    p.locator('#verification-retry:visible').wait_for()
                    p.unroute('**/v1/auth/verify-email');p.locator('#verification-retry').click()
                p.wait_for_url(base+'/');p.locator('#dashboard:visible').wait_for()
                assert ctx.request.get(base+'/v1/auth/me').json()['email']==email
                assert p.evaluate('document.documentElement.scrollWidth<=innerWidth')
                ctx.close()
            assert not errors,errors
            browser.close()
            print('PASS signup → email link → verification → HttpOnly session → dashboard; original tab refresh; status failure; query/hash; retry; replay denied')
    finally:
        proc.terminate();proc.wait(timeout=10)
