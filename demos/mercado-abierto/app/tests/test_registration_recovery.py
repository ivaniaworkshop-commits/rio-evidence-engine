"""Recover an existing unverified account without masking verification delivery failures."""
import smtplib
import time
from dataclasses import replace

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from rio_pey_codi.models import Merchant, OneTimeToken, User
from rio_pey_codi.platform import Settings, create_platform


def test_failed_initial_mail_can_be_resent_without_recreating_account(tmp_path, monkeypatch, caplog):
    app=create_platform(Settings(database_url='sqlite+pysqlite:///'+str(tmp_path/'registration.sqlite')))
    client=TestClient(app)
    data={'email':'pending@example.org','password':'Original-password-123','business_name':'Original business'}
    send=app.state.mailer.send
    def fail(*args):raise smtplib.SMTPDataError(550,b'private-provider-detail pending@example.org secret-token')
    monkeypatch.setattr(app.state.mailer,'send',fail)
    first=client.post('/v1/auth/signup',json=data)
    assert first.status_code==503 and first.json()['code']=='VERIFICATION_DELIVERY_UNAVAILABLE'
    assert first.json()['account_created'] is True
    duplicate=client.post('/v1/auth/signup',json={**data,'password':'Different-password-456','business_name':'Replacement'})
    assert duplicate.status_code==409 and duplicate.json()['code']=='ACCOUNT_EXISTS'
    assert 'Este correo ya tiene una cuenta' in duplicate.json()['detail']
    blocked=client.post('/v1/auth/login',json={'email':data['email'],'password':data['password']})
    assert blocked.status_code==503 and blocked.json()['code']=='EMAIL_DELIVERY_UNAVAILABLE'
    failed=client.post('/v1/auth/resend-verification',json={'email':data['email']})
    assert failed.status_code==503 and failed.json()['code']=='EMAIL_DELIVERY_UNAVAILABLE'
    assert app.state.mailer.outbox==[]
    with app.state.accounts.Session() as db:
        assert db.scalar(select(func.count()).select_from(User))==1
        assert db.scalar(select(func.count()).select_from(Merchant))==1
        assert db.scalar(select(Merchant.name))=='Original business'
        assert db.scalar(select(User.verified_at)) is None
        assert all(t.expires_at<=int(time.time()) for t in db.scalars(select(OneTimeToken)))
    assert 'SMTP_MESSAGE_REJECTED' in caplog.text
    assert 'pending@example.org' not in caplog.text and 'secret-token' not in caplog.text
    assert 'private-provider-detail' not in first.text+failed.text
    monkeypatch.setattr(app.state.mailer,'send',send)
    resent=client.post('/v1/auth/resend-verification',json={'email':data['email']})
    assert resent.status_code==200 and len(app.state.mailer.outbox)==1
    assert client.post('/v1/auth/verify-email',json={'token':app.state.mailer.outbox[-1]['token']}).status_code==200
    assert client.post('/v1/auth/login',json={'email':data['email'],'password':'Different-password-456'}).status_code==401
    assert client.post('/v1/auth/login',json={'email':data['email'],'password':data['password']}).status_code==200


def test_refused_recipient_is_not_reported_as_success(tmp_path, monkeypatch):
    class SMTP:
        def __init__(self,*args,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def send_message(self,msg):return {msg['To']:(550,b'synthetic rejection')}
    monkeypatch.setattr('rio_pey_codi.identity.smtplib.SMTP_SSL',SMTP)
    app=create_platform(Settings(database_url='sqlite+pysqlite:///'+str(tmp_path/'refused.sqlite')))
    app.state.mailer.cfg=replace(app.state.mailer.cfg,mode='smtp',host='smtp.invalid',port=465,sender='sender@example.org')
    client=TestClient(app)
    result=client.post('/v1/auth/signup',json={'email':'refused@example.org','password':'Synthetic-password-123','business_name':'Synthetic'})
    assert result.status_code==503 and result.json()['account_created'] is True
    result=client.post('/v1/auth/resend-verification',json={'email':'refused@example.org'})
    assert result.status_code==503 and result.json()['code']=='EMAIL_DELIVERY_UNAVAILABLE'


def test_unrelated_or_verified_addresses_keep_generic_resend_response(tmp_path):
    app=create_platform(Settings(database_url='sqlite+pysqlite:///'+str(tmp_path/'generic.sqlite')))
    client=TestClient(app)
    data={'email':'verified@example.org','password':'Synthetic-password-123','business_name':'Synthetic'}
    assert client.post('/v1/auth/signup',json=data).status_code==201
    assert client.post('/v1/auth/verify-email',json={'token':app.state.mailer.outbox[-1]['token']}).status_code==200
    before=len(app.state.mailer.outbox)
    unknown=client.post('/v1/auth/resend-verification',json={'email':'missing@example.org'})
    verified=client.post('/v1/auth/resend-verification',json={'email':data['email']})
    assert unknown.status_code==verified.status_code==200 and unknown.json()==verified.json()
    assert len(app.state.mailer.outbox)==before


def test_correct_password_for_pending_account_requests_another_verification(tmp_path):
    app=create_platform(Settings(database_url='sqlite+pysqlite:///'+str(tmp_path/'login-resend.sqlite')))
    client=TestClient(app)
    data={'email':'login-pending@example.org','password':'Synthetic-password-123','business_name':'Synthetic'}
    assert client.post('/v1/auth/signup',json=data).status_code==201
    assert len(app.state.mailer.outbox)==1
    wrong=client.post('/v1/auth/login',json={'email':data['email'],'password':'wrong-password'})
    assert wrong.status_code==401 and len(app.state.mailer.outbox)==1
    login=client.post('/v1/auth/login',json={'email':data['email'],'password':data['password']})
    assert login.status_code==403 and login.json()['verification_requested'] is True
    assert len(app.state.mailer.outbox)==2 and 'rio_sid' not in client.cookies
    assert client.get('/v1/auth/me').status_code==401
    assert client.post('/v1/auth/verify-email',json={'token':app.state.mailer.outbox[-1]['token']}).status_code==200
    assert client.post('/v1/auth/login',json={'email':data['email'],'password':data['password']}).status_code==200
