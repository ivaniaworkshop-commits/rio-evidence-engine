import base64
import pytest
from fastapi.testclient import TestClient
from cryptography.exceptions import InvalidTag
from rio_pey_codi.platform import Settings, create_platform
from rio_pey_codi.models import MerchantPeySecret
from rio_pey_codi.merchant_pey_vault import open_value

@pytest.fixture
def context(tmp_path, monkeypatch):
    key=b'k'*32
    monkeypatch.setenv('RPG_MERCHANT_VAULT_KEY', base64.urlsafe_b64encode(key).decode())
    app=create_platform(Settings(database_url='sqlite+pysqlite:///'+str(tmp_path/'db.sqlite')))
    return app, TestClient(app), key

def create_user(app,client,email):
    r=client.post('/v1/auth/signup',json={'email':email,'password':'VeryLongPassword123!', 'business_name':'Negocio'})
    assert r.status_code==201,r.text
    merchant=r.json()['merchant_id']
    token=next(m['token'] for m in app.state.mailer.outbox if m['kind']=='verify' and m['email']==email)
    assert client.post('/v1/auth/verify-email',json={'token':token}).status_code==200
    r=client.post('/v1/auth/login',json={'email':email,'password':'VeryLongPassword123!'})
    assert r.status_code==200,r.text
    return merchant,r.json()['csrf_token']

def test_owner_tenant_isolation_and_encryption(context):
    app,c1,key=context
    c2=TestClient(app)
    m1,t1=create_user(app,c1,'one@example.com')
    m2,t2=create_user(app,c2,'two@example.com')
    path=lambda m: '/v1/merchants/'+m+'/pey-settings'
    assert c1.put(path(m1),json={'api_key':'fake-provider-secret-test-123456789'},headers={'x-csrf-token':t1}).status_code==200
    r=c1.get(path(m1));assert r.status_code==200
    assert r.json()['api_key_configured'] is True
    assert 'fake-provider-secret-test-123456789' not in r.text
    assert c2.get(path(m1)).status_code==404
    assert c2.put(path(m1),json={'api_key':'stolen'},headers={'x-csrf-token':t2}).status_code==404
    assert c1.put(path(m1),json={'api_key':'other'}).status_code==403
    assert c2.get(path(m2)).json()['api_key_configured'] is False
    with app.state.accounts.Session() as db:
        row=db.get(MerchantPeySecret,m1)
        assert b'fake-provider-secret-test-123456789' not in row.api_key
        assert open_value(key,m1,'api_key',row.api_key)=='fake-provider-secret-test-123456789'
        with pytest.raises(InvalidTag): open_value(key,m2,'api_key',row.api_key)
    assert c1.delete(path(m1),headers={'x-csrf-token':t1}).status_code==200
    assert c1.get(path(m1)).json()['api_key_configured'] is False

def test_missing_key_and_no_session(context,monkeypatch):
    app,c,_=context
    m,t=create_user(app,c,'one@example.com')
    path='/v1/merchants/'+m+'/pey-settings'
    monkeypatch.delenv('RPG_MERCHANT_VAULT_KEY')
    assert c.put(path,json={'api_key':'fake-provider-secret-test-123456789'},headers={'x-csrf-token':t}).status_code==503
    assert c.get(path).json()['api_key_configured'] is False
    assert TestClient(app).get(path).status_code==401


def test_safe_status_persists_and_is_scoped_to_members(context):
    app, owner, _ = context
    merchant, csrf = create_user(app, owner, 'status-owner@example.com')
    other = TestClient(app)
    create_user(app, other, 'status-other@example.com')
    path = '/v1/merchants/' + merchant
    assert owner.put(path+'/pey-settings', json={'api_key':'sk_synthetic_status'}, headers={'x-csrf-token':csrf}).status_code == 200
    assert owner.get(path+'/pey-status').json() == {'payment_active':False}
    assert other.get(path+'/pey-status').status_code in (403,404)
    assert owner.put(path+'/members', json={'email':'status-other@example.com','role':'cashier'},
                     headers={'x-csrf-token':csrf}).status_code == 200
    assert other.get(path+'/pey-status').json() == {'payment_active':False}
    assert other.get(path+'/pey-settings').status_code in (403,404)
    assert TestClient(app).get(path+'/pey-status').status_code == 401
    assert owner.post('/v1/auth/logout',headers={'x-csrf-token':csrf}).status_code == 200
    assert owner.post('/v1/auth/login',json={'email':'status-owner@example.com','password':'VeryLongPassword123!'}).status_code == 200
    assert owner.get(path+'/pey-settings').json()['api_key_configured'] is True


def test_owner_can_identify_saved_account_and_delete_connection(context):
    app,owner,_=context
    merchant,csrf=create_user(app,owner,'account-summary@example.com')
    path='/v1/merchants/'+merchant+'/pey-settings'
    empty=owner.get(path).json()
    assert empty['configuration_saved'] is False and empty['bank_account_id'] is None
    account='01JBAVWE4NS5TGXHWGMX3KH23Q'
    key_id='01M3QMMR6X9CBVDY1SF3G8QWNW'
    response=owner.put(path,json={'api_key':'sk_synthetic_summary','api_key_id':key_id,'bank_account_id':account},headers={'x-csrf-token':csrf})
    assert response.status_code==200,response.text
    result=owner.get(path)
    data=result.json()
    assert data['configuration_saved'] and data['bank_account_id']==account and data['api_key_id']==key_id
    assert data['updated_at']>0 and data['verified_at'] is None and not data['payment_active']
    assert 'sk_synthetic_summary' not in result.text
    outsider=TestClient(app)
    create_user(app,outsider,'other-summary@example.com')
    assert outsider.get(path).status_code==404
    assert outsider.delete(path).status_code in (403,404)
    assert owner.delete(path,headers={'x-csrf-token':csrf}).status_code==200
    data=owner.get(path).json()
    assert not data['configuration_saved'] and data['bank_account_id'] is None and data['updated_at'] is None
