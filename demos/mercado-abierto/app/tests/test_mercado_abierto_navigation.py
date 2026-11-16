"""Role-gated Mercado, merged workspace and multiple receiver accounts per profile."""
import base64
from html.parser import HTMLParser
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
import pytest
from rio_pey_codi.platform import Settings, create_platform


MARKET_PATHS = (
    '/static/unificada/mercado/index.html',
    '/static/unificada/caja/%2e%2e/mercado/index.html',
    '/static/unificada//mercado/index.html',
    '/static//unificada/mercado/index.html',
    '/static/unificada/mercado/index.html/',
)


class Workspace(HTMLParser):
    def __init__(self):
        super().__init__(); self.ids=[]; self.views=[]; self.scripts=[]
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if attrs.get('id'):self.ids.append(attrs['id'])
        if 'data-workspace-panel' in attrs:self.views.append(attrs['data-workspace-panel'])
        if tag=='script' and attrs.get('src'):self.scripts.append(attrs['src'])


def register(app, client, email):
    credentials={'email':email,'password':'Mercado-synthetic-123'}
    result=client.post('/v1/auth/signup',json={**credentials,'business_name':'Synthetic business'})
    assert result.status_code==201,result.text
    token=next(mail['token'] for mail in reversed(app.state.mailer.outbox) if mail['kind']=='verify' and mail['email']==email)
    assert client.post('/v1/auth/verify-email',json={'token':token}).status_code==200
    result_login=client.post('/v1/auth/login',json=credentials)
    assert result_login.status_code==200,result_login.text
    return result.json()['merchant_id'],result_login.json()['csrf_token'],result_login.json()['user_id']


@pytest.fixture
def state(tmp_path,monkeypatch):
    monkeypatch.setenv('RPG_MERCHANT_VAULT_KEY',base64.urlsafe_b64encode(b'n'*32).decode())
    app=create_platform(Settings(database_url='sqlite+pysqlite:///'+str(tmp_path/'navigation.sqlite')))
    owner,member=TestClient(app),TestClient(app)
    owner_merchant,owner_csrf,owner_id=register(app,owner,'ivania-navigation@example.org')
    app.state.accounts.platform_owner_id=owner_id
    member_merchant,member_csrf,_=register(app,member,'ordinary-navigation@example.org')
    return app,owner,member,owner_merchant,owner_csrf,member_merchant,member_csrf


def test_public_entry_is_branded_login_and_cannot_serve_modules(state):
    app,*_=state
    visitor=TestClient(app)
    html=visitor.get('/').text
    assert 'Mercado Abierto' in html
    assert 'id="login"' in html and 'id="dashboard"' not in html
    for path in ('/mercado-abierto','/static/unificada/caja/index.html', *MARKET_PATHS):
        response=visitor.get(path,follow_redirects=False)
        assert response.status_code==303
        assert urlsplit(response.headers['location']).path=='/login'
        assert response.headers['cache-control']=='no-store'


def test_mercado_page_requires_pinned_owner_even_for_business_owners(state):
    app,owner,member,*_=state
    for path in MARKET_PATHS:
        for method in ('get','head'):
            denied=getattr(member,method)(path,follow_redirects=False)
            assert denied.status_code==403, (method,path,denied.status_code)
            assert 'data-session-required' not in denied.text
            allowed=getattr(owner,method)(path,follow_redirects=False)
            assert allowed.status_code==303, (method,path,allowed.status_code)
            assert allowed.headers['location']=='/mercado-abierto#catalogo'
    assert member.get('/api/auth/me').json()['user']['can_access_market'] is False
    assert owner.get('/api/auth/me').json()['user']['can_access_market'] is True


def test_merged_workspace_contains_one_copy_of_each_form_and_real_operations_page(state):
    _,owner,member,*_=state
    response=member.get('/')
    assert response.status_code==200
    tree=Workspace();tree.feed(response.text)
    assert set(tree.views)=={'menu','caja','historial','negocios'}
    assert len(tree.views)==len(set(tree.views))
    assert len(tree.ids)==len(set(tree.ids))
    for ident in ('main-area-menu','merchant','charge','sale-concept','amount','add-merchant','private-pey-form','private-pey-delete','cash-tools'):
        assert tree.ids.count(ident)==1,ident
    assert 'Mis negocios' in response.text
    assert '/static/cash-ui.js' in tree.scripts
    operations=member.get('/mercado-abierto',follow_redirects=False)
    assert operations.status_code==200
    assert 'Mercado Abierto' in operations.text and 'id="market-app"' in operations.text
    assert 'Mis negocios · cuenta pey' in operations.text
    legacy=member.get('/static/unificada/caja/index.html',follow_redirects=False)
    assert legacy.status_code==303 and legacy.headers['location']=='/#cobro-codi'


def test_same_profile_can_keep_separate_pey_accounts_for_multiple_businesses(state):
    _,owner,member,first,csrf,*_=state
    second=owner.post('/v1/merchants',json={'name':'Second receiver'},headers={'x-csrf-token':csrf})
    assert second.status_code==201
    second_id=second.json()['id']
    assert second_id!=first
    account_ids=['01JBAVWE4NS5TGXHWGMX3KH23Q','01M3QMMR6X9CBVDY1SF3G8QWNW']
    for index,merchant in enumerate((first,second_id)):
        path='/v1/merchants/'+merchant+'/pey-settings'
        result=owner.put(path,json={'api_key':'sk_synthetic_'+str(index),'bank_account_id':account_ids[index]},headers={'x-csrf-token':csrf})
        assert result.status_code==200,result.text
        assert owner.get(path).json()['bank_account_id']==account_ids[index]
        assert member.get(path).status_code==404
    assert {first,second_id}<={m['id'] for m in owner.get('/v1/merchants').json()['merchants']}
    assert owner.delete('/v1/merchants/'+second_id+'/pey-settings',headers={'x-csrf-token':csrf}).status_code==200
    assert owner.get('/v1/merchants/'+first+'/pey-settings').json()['bank_account_id']==account_ids[0]
