"""R010 integration tests for the historic FastAPI gateway.
This suite requires the actual rio_pey_codi package and must run locally via CI Cero.
Never uses real credentials, actual pey, SMTP or bank accounts.
"""
import pytest
from fastapi.testclient import TestClient
from rio_pey_codi.platform import Settings, create_platform

@pytest.fixture()
def service(tmp_path):
    app=create_platform(Settings(
        env='local',mode='DEMO',database_url='sqlite+pysqlite:///'+str(tmp_path/'auth-r010.sqlite'),
        auto_create=True,email_mode='memory',public_url='http://testserver',origin='http://testserver'))
    with TestClient(app) as client:yield app,client

def authenticate(app,client,email='r010-synthetic@example.org'):
    registration=client.post('/v1/auth/signup',json={
        'email':email,'password':'Synthetic-Test-Credential-2026','business_name':'Negocio sintético R010'})
    assert registration.status_code==201,registration.text
    response=client.post('/v1/auth/verify-email',json={'token':app.state.mailer.outbox[-1]['token']})
    assert response.status_code==200
    logged=client.post('/v1/auth/login',json={'email':email,'password':'Synthetic-Test-Credential-2026'})
    assert logged.status_code==200
    return logged.json()['csrf_token']

def test_app_and_identity_requires_gateway_cookie(service):
    _,c=service
    assert c.get('/hackaton', follow_redirects=False).status_code==303
    assert c.get('/api/auth/me').status_code==401
    assert c.get('/api/admin/dashboard').status_code==401
    c.cookies.set('rio_admin_session','r003-bogus-cookie')
    assert c.get('/api/auth/me').status_code==401

def test_real_historical_login_survives_adapter(service):
    app,c=service
    csrf=authenticate(app,c)
    legacy=c.get('/v1/auth/me');compat=c.get('/api/auth/me')
    assert legacy.status_code==compat.status_code==200
    assert compat.json()['user']['id']==legacy.json()['id']
    assert compat.json()['csrf_token']==legacy.json()['csrf_token']==csrf
    assert compat.json()['permissions']==['account.manage']
    assert compat.json()['auth_source']=='RIO_GATEWAY_RIO_SID'
    assert compat.json()['commercial_state']=='DATABASE_SHARED_CDMX'
    assert compat.json()['payments']=='PEY_AND_DECLARED_CASH'
    assert not any(x.startswith('admin.') for x in compat.json()['permissions'])

def test_session_protected_html_and_strict_csp(service):
    app,c=service;authenticate(app,c)
    response=c.get('/hackaton')
    assert response.status_code==200
    assert 'production.js' in response.text and 'production.css' in response.text
    assert 'id="market-app"' in response.text
    assert '/static/unificada/hackaton/app.js' not in response.text
    assert '<script>' not in response.text and '<style>' not in response.text
    assert response.headers['x-frame-options']=='DENY'
    assert "default-src 'self'" in response.headers['content-security-policy']
    legacy=c.get('/static/unificada/hackaton/index.html',follow_redirects=False)
    assert legacy.status_code==303 and legacy.headers['location']=='/mercado-abierto'
    for f in ('production.html','production.js','production.css'):
        a=c.get('/static/unificada/hackaton/'+f)
        assert a.status_code==200,f

def test_r003_admin_never_inherited(service):
    app,c=service;authenticate(app,c)
    for method,path in [('get','/api/admin/dashboard'),('get','/api/admin/users'),('post','/api/admin/users')]:
        assert getattr(c,method)(path).status_code==403,path

def test_csrf_and_logout_on_shared_gateway_session(service):
    app,c=service;csrf=authenticate(app,c)
    assert c.post('/api/auth/logout').status_code==403
    assert c.post('/api/auth/logout',headers={'X-CSRF-Token':'invalid'}).status_code==403
    ok=c.post('/api/auth/logout',headers={'X-CSRF-Token':csrf},json={})
    assert ok.status_code==200
    assert c.get('/v1/auth/me').status_code==401
    assert c.get('/api/auth/me').status_code==401
    assert c.get('/hackaton', follow_redirects=False).status_code==303