from dataclasses import replace
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, func
from rio_pey_codi.identity import now, sha
from rio_pey_codi.models import User, OneTimeToken, SessionRow
from rio_pey_codi.platform import Settings, create_platform

@pytest.fixture
def flow(tmp_path):
    app=create_platform(Settings(database_url='sqlite+pysqlite:///'+str(tmp_path/'verify.sqlite')))
    client=TestClient(app,base_url='https://example.org')
    app.state.accounts.cookie_secure=True
    credentials={'email':'verify-session@example.org','password':'Synthetic-password-123'}
    assert client.post('/v1/auth/signup',json={**credentials,'business_name':'Synthetic'}).status_code==201
    return app,client,credentials,app.state.mailer.outbox[-1]['token']

def test_verify_logs_in_and_redirects_with_session(flow):
    app,client,credentials,token=flow
    assert client.get('/v1/auth/me').status_code==401
    response=client.post('/v1/auth/verify-email',json={'token':token})
    assert response.status_code==200
    cookie=response.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite=lax' in cookie
    assert token not in cookie
    me=client.get('/v1/auth/me').json()
    assert me['verified'] is True and me['email']==credentials['email']
    assert me['id']==response.json()['user_id']
    assert client.get('/login',follow_redirects=False).headers['location']=='/'
    assert 'id="dashboard"' in client.get('/login').text
    assert client.post('/v1/merchants',json={'name':'Another business'}).status_code==403
    assert client.post('/v1/merchants',headers={'x-csrf-token':me['csrf_token']},json={'name':'Another business'}).status_code==201

def test_retry_requires_the_same_valid_session(flow):
    app,client,credentials,token=flow
    first=client.post('/v1/auth/verify-email',json={'token':token})
    second=client.post('/v1/auth/verify-email',json={'token':token})
    assert first.status_code==second.status_code==200 and 'set-cookie' not in second.headers
    anonymous=TestClient(app,base_url='https://example.org')
    assert anonymous.post('/v1/auth/verify-email',json={'token':token}).status_code==400
    assert anonymous.get('/v1/auth/me').status_code==401
    with app.state.accounts.Session() as db:
        assert db.scalar(select(func.count()).select_from(SessionRow))==1

@pytest.mark.parametrize('kind',['expired','wrong-purpose','unknown'])
def test_invalid_link_never_verifies_or_starts_session(flow,kind):
    app,client,credentials,token=flow
    with app.state.accounts.Session.begin() as db:
        row=db.get(OneTimeToken,sha(token))
        if kind=='expired':row.expires_at=now()-1
        elif kind=='wrong-purpose':row.purpose='reset'
        else:token='unknown-token-that-is-long-enough'
    response=client.post('/v1/auth/verify-email',json={'token':token})
    assert response.status_code==400 and 'set-cookie' not in response.headers
    assert client.get('/v1/auth/me').status_code==401
    with app.state.accounts.Session() as db:assert db.scalar(select(User)).verified_at is None

def test_existing_link_works_while_smtp_is_disabled(flow):
    app,client,credentials,token=flow
    app.state.mailer.cfg=replace(app.state.mailer.cfg,mode='disabled')
    assert client.post('/v1/auth/verify-email',json={'token':token}).status_code==200
    assert client.get('/v1/auth/me').json()['verified'] is True

def test_session_write_failure_rolls_back_verification_and_token(flow):
    app,client,credentials,token=flow
    def fail(*_):raise RuntimeError('synthetic session persistence failure')
    event.listen(SessionRow,'before_insert',fail)
    try:
        with pytest.raises(RuntimeError):client.post('/v1/auth/verify-email',json={'token':token})
    finally:event.remove(SessionRow,'before_insert',fail)
    with app.state.accounts.Session() as db:
        assert db.get(OneTimeToken,sha(token)).used_at is None
        assert db.scalar(select(User)).verified_at is None
    assert client.post('/v1/auth/verify-email',json={'token':token}).status_code==200

def test_resend_sibling_cannot_create_another_session(flow):
    app,client,credentials,token=flow
    client.post('/v1/auth/resend-verification',json={'email':credentials['email']})
    sibling=app.state.mailer.outbox[-1]['token']
    assert client.post('/v1/auth/verify-email',json={'token':token}).status_code==200
    anonymous=TestClient(app)
    assert anonymous.post('/v1/auth/verify-email',json={'token':sibling}).status_code==400

def test_password_reset_revokes_old_verification_credentials(flow):
    app,client,credentials,token=flow
    with app.state.accounts.Session.begin() as db:
        db.scalar(select(User)).verified_at=now()
    client.post('/v1/auth/reset-request',json={'email':credentials['email']})
    reset=app.state.mailer.outbox[-1]['token']
    assert client.post('/v1/auth/reset-confirm',json={'token':reset,'password':'New-synthetic-password-456'}).status_code==200
    assert client.post('/v1/auth/verify-email',json={'token':token}).status_code==400
    assert client.get('/v1/auth/me').status_code==401

def test_link_preview_get_does_not_consume_token(flow):
    app,client,credentials,token=flow
    assert client.get('/verify-email?token='+token).status_code==200
    assert client.get('/v1/auth/me').status_code==401
    with app.state.accounts.Session() as db:assert db.get(OneTimeToken,sha(token)).used_at is None
