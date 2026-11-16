"""Synthetic LIVE receipts: no external provider or SMTP requests."""
import base64
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from rio_pey_codi.models import MerchantPeySecret, PaymentReceipt, ReceiptDelivery
from rio_pey_codi.platform import Settings, create_platform
from rio_pey_codi.pey import LivePeyGateway, QRResult
from rio_pey_codi.signatures import make_signature
from test_merchant_pey_checkout import activate_fixture
from test_merchant_pey_vault import create_user


@pytest.fixture
def env(tmp_path, monkeypatch):
    key=b'z'*32
    monkeypatch.setenv('RPG_MERCHANT_VAULT_KEY',base64.urlsafe_b64encode(key).decode())
    monkeypatch.setattr(Settings,'validate',lambda self:None)
    monkeypatch.setattr(LivePeyGateway,'create_qr',lambda self,**kw: QRResult('qr-synthetic','synthetic QR'))
    app=create_platform(Settings(mode='LIVE',live_enabled=True,webhook_attested=True,public_url='http://testserver',
        database_url='sqlite+pysqlite:///'+str(tmp_path/'receipts.sqlite')))
    client=TestClient(app)
    merchant,csrf=create_user(app,client,'receiver@example.com')
    with app.state.accounts.Session.begin() as db:
        db.add(MerchantPeySecret(merchant_id=merchant,updated_at=1));db.flush()
        activate_fixture(db,key,merchant,'a')
    body={'merchant_id':merchant,'order_id':'receipt-sale','amount_minor':1000,'concept':'Synthetic',
        'numref':'123','expiration_s':600,'receipt_enabled':True,'payer_email':'payer@example.com'}
    return app,client,body,{'x-csrf-token':csrf}


def checkout(env, **changes):
    app,c,body,headers=env
    response=c.post('/v1/checkout/qr',json={**body,**changes},headers=headers)
    assert response.status_code==201,response.text
    return response.json()['intent']['id']


def confirm(app, ident):
    row=app.state.payments.get(ident)
    app.state.payments.confirm_provider_lookup(row,'tx-synthetic','a'*64)


def emails(app):
    return [m for m in app.state.mailer.outbox if m['kind']=='payment_receipt']


def test_confirmation_sends_two_verifiable_qrs_once(env):
    app,c,body,headers=env
    ident=checkout(env)
    app.state.receipts.issue(ident)
    assert emails(app)==[]
    confirm(app,ident)
    assert c.post('/v1/checkout/qr/'+ident+'/provider-status',headers=headers).status_code==200
    sent=emails(app)
    assert {m['email'] for m in sent}=={'payer@example.com','receiver@example.com'}
    assert all(m['qr_png'].startswith(b'\x89PNG') for m in sent)
    assert all('Pago confirmado por pey' in m['body'] for m in sent)
    assert sent[0]['link']==sent[1]['link']
    public=TestClient(app)
    response=public.get(sent[0]['link'])
    assert response.status_code==200
    assert 'Pago confirmado por pey' in response.text and 'MXN 10.00' in response.text
    assert 'payer@example.com' not in response.text and 'receiver@example.com' not in response.text
    assert public.get(sent[0]['link']+'/qr.png').content==sent[0]['qr_png']
    assert response.headers['cache-control']=='no-store'
    assert public.get(sent[0]['link'][:-1]+('a' if sent[0]['link'][-1]!='a' else 'b')).status_code==404
    assert public.get('/v1/checkout/qr/'+ident+'/receipt').status_code==401
    app.state.receipts.issue(ident)
    assert len(emails(app))==2
    data=c.get('/v1/checkout/qr/'+ident+'/receipt').json()
    assert data['issued'] and data['deliveries']=={'payer':'SENT','receiver':'SENT'}


def test_opt_out_persists_and_replay_cannot_change_recipient(env):
    app,c,body,headers=env
    ident=checkout(env,receipt_enabled=False,payer_email=None)
    replay=c.post('/v1/checkout/qr',json=body,headers=headers)
    assert replay.json()['status']=='REPLAY_NO_PROVIDER_RETRY'
    confirm(app,ident);app.state.receipts.issue(ident)
    assert emails(app)==[]
    with app.state.accounts.Session() as db:
        receipt=db.get(PaymentReceipt,ident)
        assert not receipt.enabled and receipt.payer_email is None
    status=c.get('/v1/checkout/qr/'+ident+'/receipt').json()
    assert status['enabled'] is False and status['issued'] is True
    assert TestClient(app).get(status['link']).status_code==200


def test_email_validation_and_pending_or_unsigned_status_cannot_issue(env):
    app,c,body,headers=env
    for changes in ({'payer_email':None},{'payer_email':'bad\r\nBcc:x@example.com'},{'receipt_enabled':'yes'}):
        assert c.post('/v1/checkout/qr',json={**body,**changes},headers=headers).status_code==422
    ident=checkout(env)
    with app.state.accounts.Session.begin() as db:
        from rio_pey_codi.models import Intent
        db.get(Intent,ident).status='PROVIDER_REPORTED'  # forged/incomplete local evidence
    app.state.receipts.issue(ident)
    assert emails(app)==[]
    with app.state.accounts.Session() as db:
        receipt=db.get(PaymentReceipt,ident)
        assert TestClient(app).get(app.state.receipts.link(receipt)).status_code==404


def test_signed_webhook_and_provider_readback_trigger_delivery(env,monkeypatch):
    app,c,body,headers=env
    ident=checkout(env)
    transaction={'id':'tx-synthetic','status':'PAID','amount':10,'currency':'MXN','paymentMethod':'CODI',
        'payableType':'API_CODI_QR','payableId':'qr-synthetic','datePaid':int(time.time())}
    monkeypatch.setattr(LivePeyGateway,'transaction',lambda self,tx:transaction)
    raw=json.dumps({'type':'codi.qr.payment_received','codiQrId':'qr-synthetic','transactionId':'tx-synthetic',
        'apiKeyId':'key-synthetic','amount':10,'numRef':'123','metadata':{'externalMetadata':{'rioIntentId':ident}}}).encode()
    stamp=int(time.time());event='evt-synthetic'
    signature=make_signature('whsec_'+'a'*24,event,stamp,raw)
    wh={'webhook-id':event,'webhook-timestamp':str(stamp),'webhook-signature':signature}
    path='/v1/webhooks/pey/'+body['merchant_id']
    assert c.post(path,content=raw,headers={**wh,'webhook-signature':'invalid'}).status_code==401
    assert emails(app)==[]
    assert c.post(path,content=raw,headers=wh).status_code==200
    assert len(emails(app))==2
    assert c.post(path,content=raw,headers=wh).status_code==200
    assert len(emails(app))==2


def test_smtp_uncertain_does_not_repeat_already_claimed_email(env,monkeypatch):
    app,c,body,headers=env
    ident=checkout(env);confirm(app,ident)
    calls=[]
    def fail(*args):calls.append(args[0]);raise TimeoutError()
    monkeypatch.setattr(app.state.receipts,'send',fail)
    app.state.receipts.issue(ident);app.state.receipts.issue(ident)
    assert len(calls)==2
    assert set(c.get('/v1/checkout/qr/'+ident+'/receipt').json()['deliveries'].values())=={'UNCERTAIN'}


def test_concurrent_callbacks_claim_each_recipient_only_once(env):
    app,c,body,headers=env
    ident=checkout(env);confirm(app,ident)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _:app.state.receipts.issue(ident),range(2)))
    assert len(emails(app))==2


def test_actual_mime_includes_inline_qr_without_exposing_other_recipient(env):
    app,c,body,headers=env
    ident=checkout(env);confirm(app,ident)
    sent=[]
    class SMTP:
        def __init__(self,*a,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def login(self,*a):pass
        def send_message(self,msg):sent.append(msg)
    app.state.mailer.cfg=replace(app.state.mailer.cfg,mode='smtp',port=465,host='smtp.invalid',sender='sender@example.com')
    with patch('rio_pey_codi.receipts.smtplib.SMTP_SSL',SMTP):app.state.receipts.issue(ident)
    assert len(sent)==2
    assert sent[0]['To']=='payer@example.com' and sent[0]['Cc'] is None
    images=[p for p in sent[0].walk() if p.get_content_type()=='image/png']
    assert len(images)==1 and images[0].get_payload(decode=True).startswith(b'\x89PNG')
    assert 'Content-ID: <receipt-qr>' in sent[0].as_string()


def test_qr_decodes_to_the_actual_validation_url(env):
    import io
    zxing=pytest.importorskip('zxingcpp')
    Image=pytest.importorskip('PIL.Image')
    app,c,body,headers=env
    ident=checkout(env);confirm(app,ident);app.state.receipts.issue(ident)
    message=emails(app)[0]
    decoded=zxing.read_barcode(Image.open(io.BytesIO(message['qr_png'])))
    assert decoded is not None and decoded.text==message['link']
    assert TestClient(app).get(decoded.text).status_code==200


def test_receipt_is_not_valid_if_payment_record_loses_confirmation(env):
    from rio_pey_codi.models import Intent
    app,c,body,headers=env
    ident=checkout(env);confirm(app,ident);app.state.receipts.issue(ident)
    link=emails(app)[0]['link']
    with app.state.accounts.Session.begin() as db:db.get(Intent,ident).status='PROVIDER_REJECTED'
    assert TestClient(app).get(link).status_code==404


def test_017_downgrade_preserves_receipt_bytes(env,monkeypatch):
    import sqlite3
    from pathlib import Path
    from alembic.config import Config
    from alembic import command
    app,c,body,headers=env
    checkout(env)
    engine=app.state.accounts.Session.kw['bind']
    monkeypatch.setenv('DATABASE_URL',str(engine.url))
    config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))
    command.stamp(config,'017')
    with sqlite3.connect(engine.url.database) as db:before='\n'.join(db.iterdump())
    with pytest.raises(RuntimeError,match='Refusing to discard payment receipts'):
        command.downgrade(config,'016')
    with sqlite3.connect(engine.url.database) as db:assert '\n'.join(db.iterdump())==before


def test_receiver_requires_verified_mailbox_and_can_recover_after_verification(env):
    from rio_pey_codi.models import Merchant,User
    app,c,body,headers=env
    ident=checkout(env);confirm(app,ident)
    with app.state.accounts.Session.begin() as db:
        owner_id=db.get(Merchant,body['merchant_id']).owner_id
        db.get(User,owner_id).verified_at=None
    app.state.receipts.issue(ident)
    assert [m['role'] for m in emails(app)]==['payer']
    with app.state.accounts.Session.begin() as db:db.get(User,owner_id).verified_at=1
    app.state.receipts.issue(ident)
    assert [m['role'] for m in emails(app)]==['payer','receiver']


def test_early_verified_webhook_issues_after_qr_is_persisted(env,monkeypatch):
    from rio_pey_codi.merchant_pey_checkout import receive_merchant_event
    app,c,body,headers=env
    def early(self,**kw):
        ident=kw['intent_id'];stamp=int(time.time())
        transaction={'id':'tx-synthetic','status':'PAID','amount':10,'currency':'MXN','paymentMethod':'CODI',
            'payableType':'API_CODI_QR','payableId':'qr-synthetic','datePaid':stamp,
            'metadata':{'externalMetadata':{'rioIntentId':ident}}}
        monkeypatch.setattr(LivePeyGateway,'transaction',lambda self,tx:transaction)
        raw=json.dumps({'type':'codi.qr.payment_received','codiQrId':'qr-synthetic','transactionId':'tx-synthetic',
            'apiKeyId':'key-synthetic','amount':10,'numRef':'123','metadata':{'externalMetadata':{'rioIntentId':ident}}}).encode()
        wh={'webhook-id':'early-synthetic','webhook-timestamp':str(stamp),
            'webhook-signature':make_signature('whsec_'+'a'*24,'early-synthetic',stamp,raw)}
        outcome=receive_merchant_event(app.state.accounts.Session,app.state.payments,body['merchant_id'],wh,raw)
        assert outcome['outcome']=='PROVIDER_REPORTED'
        assert emails(app)==[]
        return QRResult('qr-synthetic','synthetic QR')
    monkeypatch.setattr(LivePeyGateway,'create_qr',early)
    ident=checkout(env)
    assert app.state.payments.get(ident).status=='PROVIDER_REPORTED'
    assert len(emails(app))==2
