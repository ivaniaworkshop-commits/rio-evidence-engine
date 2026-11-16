import base64
import pytest
from fastapi import HTTPException
from rio_pey_codi.models import database, User, Merchant, MerchantPeySecret, MerchantPeyCredential
from rio_pey_codi.merchant_pey_vault import seal
from rio_pey_codi.merchant_pey_checkout import merchant_gateway

def activate_fixture(db, key, merchant, suffix):
    ref = suffix * 32
    db.add(MerchantPeyCredential(ref=ref, merchant_id=merchant,
        api_key=seal(key,merchant,'api_key:'+ref,'sk_'+suffix*24),
        webhook_secret=seal(key,merchant,'webhook_secret:'+ref,'whsec_'+suffix*24),checked_at=1))
    db.flush()
    db.get(MerchantPeySecret,merchant).active_credential_ref=ref

def test_selects_only_selected_merchant_and_requires_complete_setup(tmp_path,monkeypatch):
    key=b'z'*32
    monkeypatch.setenv('RPG_MERCHANT_VAULT_KEY',base64.urlsafe_b64encode(key).decode())
    sf=database('sqlite+pysqlite:///'+str(tmp_path/'db.sqlite'),auto_create=True)
    with sf.begin() as db:
        for c in ('a','b'):
            db.add(User(id=c*32,email=c+'@example.invalid',password_hash='synthetic',created_at=0))
        db.flush()
        for c in ('a','b'):
            db.add(Merchant(id=c*32,name='Synthetic',owner_id=c*32,created_at=0))
        db.flush()
        for c in ('a','b'):
            db.add(MerchantPeySecret(merchant_id=c*32,api_key=seal(key,c*32,'api_key','sk_'+c*24),
                webhook_secret=seal(key,c*32,'webhook_secret','whsec_'+c*24),updated_at=1))
    with pytest.raises(HTTPException) as inactive: merchant_gateway(sf,'a'*32)
    assert inactive.value.status_code==503
    with sf.begin() as db:
        for c in ('a','b'): activate_fixture(db,key,c*32,c)
    assert merchant_gateway(sf,'a'*32).gateway.api_key=='sk_'+'a'*24
    assert merchant_gateway(sf,'b'*32).gateway.api_key=='sk_'+'b'*24
    with pytest.raises(HTTPException) as missing: merchant_gateway(sf,'c'*32)
    assert missing.value.status_code==503
    monkeypatch.setenv('RPG_MERCHANT_VAULT_KEY',base64.urlsafe_b64encode(b'y'*32).decode())
    with pytest.raises(HTTPException) as wrong: merchant_gateway(sf,'a'*32)
    assert wrong.value.status_code==503
    assert 'sk_' not in str(wrong.value.detail)

def test_checkout_dispatches_for_authenticated_merchant_without_retry(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from rio_pey_codi.platform import Settings, create_platform
    from rio_pey_codi.pey import QRResult, LivePeyGateway

    # The production gate remains closed; isolate this branch with a fake provider.
    monkeypatch.setattr(Settings,'validate',lambda self: None)
    key=b'z'*32
    monkeypatch.setenv('RPG_MERCHANT_VAULT_KEY',base64.urlsafe_b64encode(key).decode())
    called=[]
    def fake_create(self,**kwargs):
        called.append((self.api_key,kwargs))
        return QRResult('QR-synthetic','synthetic')
    monkeypatch.setattr(LivePeyGateway,'create_qr',fake_create)
    app=create_platform(Settings(mode='LIVE',live_enabled=True,database_url='sqlite+pysqlite:///'+str(tmp_path/'checkout.sqlite')))
    client=TestClient(app)
    data={'email':'checkout@example.com','password':'VeryLongPassword123!', 'business_name':'Synthetic'}
    signup=client.post('/v1/auth/signup',json=data)
    assert signup.status_code==201,signup.text
    mid=signup.json()['merchant_id']
    with app.state.accounts.Session.begin() as db:
        db.add(MerchantPeySecret(merchant_id=mid,updated_at=1))
        db.flush()
        activate_fixture(db,key,mid,'a')
    token=next(x['token'] for x in app.state.mailer.outbox if x['kind']=='verify')
    assert client.post('/v1/auth/verify-email',json={'token':token}).status_code==200
    login=client.post('/v1/auth/login',json={'email':data['email'],'password':data['password']})
    csrf=login.json()['csrf_token']
    body={'merchant_id':mid,'order_id':'sale-1','amount_minor':1540,'concept':'Venta','numref':'123','expiration_s':600}
    first=client.post('/v1/checkout/qr',json=body,headers={'x-csrf-token':csrf})
    second=client.post('/v1/checkout/qr',json=body,headers={'x-csrf-token':csrf})
    assert first.status_code==201,first.text
    assert second.json()['status']=='REPLAY_NO_PROVIDER_RETRY'
    assert len(called)==1 and called[0][0]=='sk_'+'a'*24 and called[0][1]['amount_minor']==1540
    assert first.json()['intent']['mode']=='LIVE'
    assert first.json()['intent']['bank_payment_confirmed'] is False
    bad=dict(body,order_id='sale-2',numref='invalid')
    assert client.post('/v1/checkout/qr',json=bad,headers={'x-csrf-token':csrf}).status_code==422
    assert len(called)==1
