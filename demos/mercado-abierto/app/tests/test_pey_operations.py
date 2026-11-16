import base64
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from rio_pey_codi.platform import Settings, create_platform
from rio_pey_codi.models import MerchantPeySecret, Intent, PaymentReceipt
from rio_pey_codi.pey_extended import FullPeyGateway
from rio_pey_codi.pey import ProviderError
from test_merchant_pey_checkout import activate_fixture

@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(Settings,'validate',lambda self:None)
    key=b'z'*32;monkeypatch.setenv('RPG_MERCHANT_VAULT_KEY',base64.urlsafe_b64encode(key).decode())
    app=create_platform(Settings(mode='LIVE',live_enabled=True,webhook_attested=True,public_url='https://mercado.example',database_url='sqlite+pysqlite:///'+str(tmp_path/'ops.sqlite')))
    c=TestClient(app);mid=c.post('/v1/auth/signup',json={'email':'owner@example.com','password':'VeryLongPassword123!','business_name':'Shop'}).json()['merchant_id']
    with app.state.accounts.Session.begin() as db:
        db.add(MerchantPeySecret(merchant_id=mid,updated_at=1));db.flush();activate_fixture(db,key,mid,'a')
    token=next(x['token'] for x in app.state.mailer.outbox if x['kind']=='verify');c.post('/v1/auth/verify-email',json={'token':token})
    c.headers['x-csrf-token']=c.post('/v1/auth/login',json={'email':'owner@example.com','password':'VeryLongPassword123!'}).json()['csrf_token']
    return app,c,'/v1/merchants/'+mid

def body(kind='PUSH'):
    return dict(id='b'*32,kind=kind,amount_minor=101,order_id='order-1',numref='123',phone='5512345678',concept='Venta',payer_email='buyer@example.com')

def tx(kind='API_CODI_PN'):
    return dict(id='TX1',status='PAID',currency='MXN',paymentMethod='CODI',payableType=kind,payableId='LINK1' if kind=='PAYMENT_LINK' else '12345678901234567890',amount=Decimal('1.01'),amountBreakdown={'base':Decimal('1.01')},datePaid=1790000000)

def test_push_replay_readback_receipt(env,monkeypatch):
    app,c,p=env;calls=[]
    monkeypatch.setattr(FullPeyGateway,'push',lambda self,**kw:calls.append(kw) or {'transactionId':'TX1','codiId':'12345678901234567890'})
    r=c.post(p+'/pey-operations',json=body());assert r.status_code==200,r.text
    assert r.json()['state']=='PENDING';assert c.post(p+'/pey-operations',json=body()).status_code==200;assert len(calls)==1
    with app.state.accounts.Session() as db:assert db.get(PaymentReceipt,'b'*32).issued_at is None
    monkeypatch.setattr(FullPeyGateway,'transaction',lambda *a:tx())
    r=c.post(p+'/pey-operations/'+('b'*32)+'/refresh');assert r.status_code==200,r.text
    assert r.json()['state']=='PAID'
    with app.state.accounts.Session() as db:assert db.get(PaymentReceipt,'b'*32).issued_at
    count=len(app.state.mailer.outbox);assert c.post(p+'/pey-operations/'+('b'*32)+'/refresh').status_code==200;assert len(app.state.mailer.outbox)==count

def test_timeout_never_resends(env,monkeypatch):
    app,c,p=env;calls=[]
    def timeout(self,**kw):calls.append(kw);raise ProviderError('timeout')
    monkeypatch.setattr(FullPeyGateway,'push',timeout)
    assert c.post(p+'/pey-operations',json=body()).json()['state']=='UNCERTAIN'
    assert c.post(p+'/pey-operations',json=body()).json()['state']=='UNCERTAIN';assert len(calls)==1

def test_auth_and_validation(env,monkeypatch):
    app,c,p=env
    monkeypatch.setattr(FullPeyGateway,'push',lambda *a,**kw:pytest.fail('must not call provider'))
    assert c.post('/v1/merchants/'+('f'*32)+'/pey-operations',json=body()).status_code in (403,404)
    assert c.post(p+'/pey-operations',json={**body(),'phone':'123'}).status_code==422
    assert c.post(p+'/pey-operations',json={**body(),'amount_minor':True}).status_code==422
    del c.headers['x-csrf-token'];assert c.post(p+'/pey-operations',json=body()).status_code==403

def test_link_partial_tip_and_readback(env,monkeypatch):
    app,c,p=env
    monkeypatch.setattr(FullPeyGateway,'create_link',lambda *a,**kw:{'id':'LINK1','url':'https://app.mipey.mx/payment-link/LINK1'})
    assert c.post(p+'/pey-operations',json=body('LINK')).status_code==200
    data={'id':'LINK1','clientReferenceId':'b'*32,'amount':Decimal('1.01'),'status':'partial','transactions':[]}
    monkeypatch.setattr(FullPeyGateway,'link',lambda *a:data)
    r=c.post(p+'/pey-operations/'+('b'*32)+'/refresh');assert r.json()['state']=='PARTIAL'
    with app.state.accounts.Session() as db:assert db.get(PaymentReceipt,'b'*32).issued_at is None
    data.update(status='paid',transactions=[{'transactionId':'TX1'}]);paid=tx('PAYMENT_LINK');paid.update(amount=Decimal('1.21'),amountBreakdown={'base':Decimal('1.01'),'tip':Decimal('.20')})
    monkeypatch.setattr(FullPeyGateway,'transaction',lambda *a:paid)
    r=c.post(p+'/pey-operations/'+('b'*32)+'/refresh');assert r.status_code==200,r.text
    with app.state.accounts.Session() as db:assert db.get(PaymentReceipt,'b'*32).issued_at
    paid['metadata']={'payerBankData':'must not be returned'}
    detail=c.get(p+'/pey-transactions/TX1')
    assert detail.status_code==200,detail.text
    assert detail.json()['payableId']=='LINK1' and 'metadata' not in detail.json()

def test_wrong_amount_no_receipt(env,monkeypatch):
    app,c,p=env
    monkeypatch.setattr(FullPeyGateway,'push',lambda *a,**kw:{'transactionId':'TX1','codiId':'12345678901234567890'})
    c.post(p+'/pey-operations',json=body());paid=tx();paid.update(amount=Decimal('2.01'),amountBreakdown={'base':Decimal('2.01')})
    monkeypatch.setattr(FullPeyGateway,'transaction',lambda *a:paid)
    assert c.post(p+'/pey-operations/'+('b'*32)+'/refresh').status_code==409
    with app.state.accounts.Session() as db:assert db.get(PaymentReceipt,'b'*32).issued_at is None

def test_bank_registered_masked(env,monkeypatch):
    app,c,p=env
    monkeypatch.setattr(FullPeyGateway,'register_account',lambda *a,**kw:{'id':'BANK1','codiStatus':'PENDING'})
    r=c.post(p+'/pey-operations',json={'id':'c'*32,'kind':'BANK','alias':'Cuenta','name':'Titular','clabe':'0'*18,'entity':'PERSON'});assert r.status_code==200,r.text
    monkeypatch.setattr(FullPeyGateway,'account',lambda *a:{'id':'BANK1','codiStatus':'ACTIVE','alias':'Cuenta','clabe':'012345678901234567'})
    r=c.post(p+'/pey-operations/'+('c'*32)+'/refresh');assert r.status_code==200,r.text
    assert '012345678901234567' not in r.text;assert r.json()['result']['clabe_masked']=='•••• 4567'

def test_bank_can_be_removed_from_this_business_list_and_restored_without_deleting_from_pey(env,monkeypatch):
    app,c,p=env
    provider_calls=[]
    monkeypatch.setattr(FullPeyGateway,'register_account',lambda *a,**kw:provider_calls.append('register') or {'id':'BANK2','codiStatus':'PENDING'})
    created=c.post(p+'/pey-operations',json={'id':'d'*32,'kind':'BANK','alias':'Otra cuenta','name':'Titular','clabe':'0'*18,'entity':'PERSON'})
    assert created.status_code==200,created.text
    assert created.json()['locally_archived'] is False
    listed=c.get(p+'/pey-operations').json()['items']
    assert next(x for x in listed if x['id']=='d'*32)['locally_archived'] is False

    csrf=c.headers.pop('x-csrf-token')
    assert c.post(p+'/pey-operations/'+('d'*32)+'/archive').status_code==403
    c.headers['x-csrf-token']=csrf
    archived=c.post(p+'/pey-operations/'+('d'*32)+'/archive')
    assert archived.status_code==200,archived.text
    assert archived.json()['locally_archived'] is True and archived.json()['state']=='PENDING'
    assert c.get(p+'/pey-operations').json()['items'][0]['locally_archived'] is True

    monkeypatch.setattr(FullPeyGateway,'account',lambda *a:{'id':'BANK2','codiStatus':'ACTIVE','alias':'Otra cuenta','clabe':'0'*18})
    refreshed=c.post(p+'/pey-operations/'+('d'*32)+'/refresh')
    assert refreshed.status_code==200,refreshed.text
    assert refreshed.json()['state']=='ACTIVE' and refreshed.json()['locally_archived'] is True

    restored=c.post(p+'/pey-operations/'+('d'*32)+'/restore')
    assert restored.status_code==200,restored.text
    assert restored.json()['locally_archived'] is False and restored.json()['state']=='ACTIVE'
    assert c.get(p+'/pey-operations').json()['items'][0]['locally_archived'] is False
    assert provider_calls==['register']  # No pey delete call is made by local removal.

def test_qr_transaction_ledger_is_local_and_paginated(env,monkeypatch):
    app,c,p=env;merchant=p.rsplit('/',1)[-1]
    with app.state.accounts.Session.begin() as db:
        db.add(Intent(id='d'*32,merchant_id=merchant,order_id='qr-ledger',amount_minor=101,
            concept='Venta',numref='444',expiration_s=600,status='PENDING',provider_qr_id='QR123',
            pey_credential_ref='a'*32,created_at=1))
    calls=[]
    monkeypatch.setattr(FullPeyGateway,'qr_transactions',lambda self,qr_id,token=None:
        calls.append((qr_id,token)) or {'items':[{'id':'TXQR','status':'PAID','amount':Decimal('1.01'),
            'currency':'MXN','paymentMethod':'CODI','metadata':{'private':'not returned'}}], 'nextToken':'cursor+/='})
    r=c.get(p+'/pey-transactions',params={'qr_id':'QR123'})
    assert r.status_code==200,r.text
    assert calls==[('QR123',None)]
    assert r.json()['next_token']=='cursor+/='
    assert len(r.json()['items'])==1 and r.json()['items'][0]['id']=='TXQR'
    assert 'metadata' not in r.json()['items'][0]
    next_page=c.get(p+'/pey-transactions',params={'qr_id':'QR123','next_token':'cursor+/='})
    assert next_page.status_code==200,next_page.text
    assert calls[-1]==('QR123','cursor+/=')
    assert c.get(p+'/pey-transactions',params={'qr_id':'OTHER'}).status_code==404
    assert c.get(p+'/pey-transactions',params={'qr_id':'QR123','account_id':'BANK1'}).status_code==422

def test_qr_transaction_detail_is_scoped_to_saved_intent(env,monkeypatch):
    app,c,p=env;merchant=p.rsplit('/',1)[-1]
    with app.state.accounts.Session.begin() as db:
        db.add(Intent(id='e'*32,merchant_id=merchant,order_id='qr-detail',amount_minor=101,
            concept='Venta',numref='445',expiration_s=600,status='PROVIDER_REPORTED',provider_qr_id='QR456',
            transaction_id='TX456',pey_credential_ref='a'*32,created_at=1))
    monkeypatch.setattr(FullPeyGateway,'transaction',lambda *a:{'id':'TX456','status':'PAID',
        'amount':Decimal('1.01'),'currency':'MXN','paymentMethod':'CODI','payableType':'API_CODI_QR',
        'payableId':'QR456','metadata':{'sensitive':'never expose'}})
    r=c.get(p+'/pey-transactions/TX456')
    assert r.status_code==200,r.text
    assert r.json()['payableId']=='QR456' and 'metadata' not in r.json()
    monkeypatch.setattr(FullPeyGateway,'transaction',lambda *a:pytest.fail('unknown transaction must not call pey'))
    assert c.get(p+'/pey-transactions/TX999').status_code==404

def test_link_update_only_pending_and_readback(env,monkeypatch):
    app,c,p=env
    monkeypatch.setattr(FullPeyGateway,'create_link',lambda *a,**kw:{'id':'LINK1','url':'https://app.mipey.mx/payment-link/LINK1'})
    c.post(p+'/pey-operations',json=body('LINK'))
    data={'id':'LINK1','status':'pending','clientReferenceId':'b'*32,'amount':Decimal('1.01')}
    monkeypatch.setattr(FullPeyGateway,'link',lambda *a:data)
    def change(self,link_id,amount):data['amount']=Decimal(amount)/100;return {'id':link_id,'amount':data['amount']}
    monkeypatch.setattr(FullPeyGateway,'update_link',change)
    r=c.post(p+'/pey-operations',json={'id':'c'*32,'kind':'LINK_UPDATE','parent_id':'b'*32,'amount_minor':202});assert r.status_code==200,r.text
    assert r.json()['state']=='UPDATED'
    with app.state.accounts.Session() as db:assert db.get(Intent,'b'*32).amount_minor==202
    data['status']='processing'
    c.post(p+'/pey-operations/'+('b'*32)+'/refresh')
    assert c.post(p+'/pey-operations',json={'id':'d'*32,'kind':'LINK_UPDATE','parent_id':'b'*32,'amount_minor':303}).status_code==409

def test_uncertain_update_can_recover_without_repeating_post(env,monkeypatch):
    app,c,p=env
    monkeypatch.setattr(FullPeyGateway,'create_link',lambda *a,**kw:{'id':'LINK1','url':'https://app.mipey.mx/payment-link/LINK1'})
    c.post(p+'/pey-operations',json=body('LINK'))
    data={'id':'LINK1','status':'pending','clientReferenceId':'b'*32,'amount':Decimal('1.01')}
    monkeypatch.setattr(FullPeyGateway,'link',lambda *a:data)
    def change(self,link_id,amount):data['amount']=Decimal(amount)/100;raise ProviderError('timeout after commit')
    monkeypatch.setattr(FullPeyGateway,'update_link',change)
    r=c.post(p+'/pey-operations',json={'id':'c'*32,'kind':'LINK_UPDATE','parent_id':'b'*32,'amount_minor':202});assert r.json()['state']=='UNCERTAIN'
    r=c.post(p+'/pey-operations/'+('b'*32)+'/refresh');assert r.status_code==200,r.text
    assert r.json()['amount_minor']==202

def test_recover_push_requires_operation_metadata(env,monkeypatch):
    app,c,p=env
    def fail(*a,**kw):raise ProviderError('timeout')
    monkeypatch.setattr(FullPeyGateway,'push',fail);c.post(p+'/pey-operations',json=body())
    data=tx();monkeypatch.setattr(FullPeyGateway,'transaction',lambda *a:data)
    path=p+'/pey-operations/'+('b'*32)+'/recover?provider_id=TX1'
    assert c.post(path).status_code==409
    data['metadata']={'externalMetadata':{'mercadoOperationId':'b'*32}}
    r=c.post(path);assert r.status_code==200,r.text
    with app.state.accounts.Session() as db:assert db.get(PaymentReceipt,'b'*32).issued_at

@pytest.mark.parametrize('kind',['PUSH','LINK','BANK'])
def test_signed_webhooks_and_duplicates(env,monkeypatch,kind):
    import json,time
    from rio_pey_codi.signatures import make_signature
    app,c,p=env
    if kind=='BANK':
        monkeypatch.setattr(FullPeyGateway,'register_account',lambda *a,**kw:{'id':'BANK1','codiStatus':'PENDING'})
        value={'id':'b'*32,'kind':'BANK','alias':'Cuenta','name':'Titular','clabe':'0'*18,'entity':'PERSON'}
        monkeypatch.setattr(FullPeyGateway,'account',lambda *a:{'id':'BANK1','codiStatus':'ACTIVE'})
        event={'type':'bank.account.updated','bankAccountId':'BANK1','codiStatus':'ACTIVE'}
    elif kind=='PUSH':
        monkeypatch.setattr(FullPeyGateway,'push',lambda *a,**kw:{'transactionId':'TX1','codiId':'12345678901234567890'})
        monkeypatch.setattr(FullPeyGateway,'transaction',lambda *a:tx())
        value=body();event={'type':'codi.pn.payment_received','transactionId':'TX1'}
    else:
        monkeypatch.setattr(FullPeyGateway,'create_link',lambda *a,**kw:{'id':'LINK1','url':'https://app.mipey.mx/payment-link/LINK1'})
        monkeypatch.setattr(FullPeyGateway,'link',lambda *a:{'id':'LINK1','status':'paid','clientReferenceId':'b'*32,'amount':Decimal('1.01'),'transactions':[{'transactionId':'TX1'}]})
        monkeypatch.setattr(FullPeyGateway,'transaction',lambda *a:tx('PAYMENT_LINK'))
        value=body('LINK');event={'type':'payment_link.status_updated','paymentLinkId':'LINK1','status':'paid'}
    assert c.post(p+'/pey-operations',json=value).status_code==200
    raw=json.dumps(event).encode();stamp=int(time.time());wid='event-test'
    headers={'webhook-id':wid,'webhook-timestamp':str(stamp),'webhook-signature':make_signature('whsec_'+'a'*24,wid,stamp,raw)}
    endpoint='/v1/webhooks/pey/'+p.split('/')[-1]
    assert c.post(endpoint,content=raw).status_code==401
    first=c.post(endpoint,content=raw,headers=headers);assert first.status_code==200,first.text
    count=len(app.state.mailer.outbox)
    second=c.post(endpoint,content=raw,headers=headers);assert second.status_code==200,second.text
    assert len(app.state.mailer.outbox)==count
