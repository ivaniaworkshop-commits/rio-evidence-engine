from dataclasses import replace

from fastapi.testclient import TestClient
from sqlalchemy import select

from rio_pey_codi.models import ProviderAccountObservation, User, database
from rio_pey_codi.platform import Settings, create_platform


def test_verified_accounts_and_each_merchants_own_pey_lookup(tmp_path, monkeypatch):
    import rio_pey_codi.platform as platform

    factory=database('sqlite+pysqlite:///' + str(tmp_path / 'accounts.sqlite3'), auto_create=True)
    monkeypatch.setattr(platform, 'database', lambda *_args, **_kwargs: factory)
    monkeypatch.setattr(platform, 'database_ready', lambda _factory: True)
    monkeypatch.setattr(platform, 'database_readiness', lambda _factory: (True, 'OK'))
    cfg=Settings(database_url='sqlite+pysqlite:///' + str(tmp_path / 'accounts.sqlite3'),
                 public_url='https://rio.example.org', origin='https://rio.example.org')
    app=create_platform(cfg)
    a=TestClient(app,base_url='https://rio.example.org')
    b=TestClient(app,base_url='https://rio.example.org')
    status=a.get('/public-status').json()
    assert status['registration_enabled'] is True and status['registration_email_required'] is True
    assert status['verification_email_enabled'] is True and status['password_reset_enabled'] is True
    assert status['live_payments_enabled'] is False and status['email_delivery'] == 'memory'

    credentials={'email':'owner-a@example.org', 'password':'password-for-owner-a'}
    signup=a.post('/v1/auth/signup',json={**credentials,'business_name':'Comercio A'})
    assert signup.status_code == 201
    assert signup.json()['status'] == 'VERIFICATION_REQUIRED'
    merchant_a=signup.json()['merchant_id']
    with factory() as db:
        user=db.scalar(select(User).where(User.email==credentials['email']))
        assert user.verified_at is None
    assert a.post('/v1/auth/signup',json={**credentials,'business_name':'Comercio A'}).status_code == 409
    assert a.post('/v1/auth/login',json=credentials).status_code == 403
    assert a.post('/v1/auth/verify-email',json={'token':app.state.mailer.outbox[-1]['token']}).status_code == 200
    login=a.post('/v1/auth/login',json=credentials)
    assert login.status_code == 200
    csrf_a={'x-csrf-token':login.json()['csrf_token']}
    me=a.get('/v1/auth/me').json()
    assert me['verified'] is True and me['access_origin'] == 'email_verified' and me['can_invite'] is False

    credentials_b={'email':'owner-b@example.org', 'password':'password-for-owner-b'}
    signup_b=b.post('/v1/auth/signup',json={**credentials_b,'business_name':'Comercio B'})
    assert signup_b.status_code == 201
    assert b.post('/v1/auth/verify-email',json={'token':app.state.mailer.outbox[-1]['token']}).status_code == 200
    login_b=b.post('/v1/auth/login',json=credentials_b)
    csrf_b={'x-csrf-token':login_b.json()['csrf_token']}
    account_id='01ARZ3NDEKTSV4RRFFQ69G5FAV'
    claim=a.post(f'/v1/merchants/{merchant_a}/beneficiary-claims',
        headers={**csrf_a,'idempotency-key':'a'*32},
        json={'claim':'OWNER_REPORTED_VERIFIED','provider_account_id':account_id})
    assert claim.status_code == 201

    calls=[]
    def fake_lookup(key, actual_account):
        calls.append((key,actual_account))
        return 'ACTIVE'
    monkeypatch.setattr(platform,'lookup_pey_account',fake_lookup)
    key='synthetic-owner-a-key'
    outsider=b.post(f'/v1/merchants/{merchant_a}/own-pey-account-checks',
        headers={**csrf_b,'idempotency-key':'b'*32},json={'api_key':key})
    assert outsider.status_code == 404 and not calls
    checked=a.post(f'/v1/merchants/{merchant_a}/own-pey-account-checks',
        headers={**csrf_a,'idempotency-key':'c'*32},json={'api_key':key})
    assert checked.status_code == 201
    assert calls == [(key,account_id)]
    assert checked.json()['key_saved'] is False and checked.json()['observation']['status'] == 'ACTIVE'
    assert checked.json()['observation']['merchant_ownership_verified'] is False
    assert key not in checked.text
    replay=a.post(f'/v1/merchants/{merchant_a}/own-pey-account-checks',
        headers={**csrf_a,'idempotency-key':'c'*32},json={'api_key':key})
    assert replay.status_code == 409 and len(calls) == 1
    malformed=a.post(f'/v1/merchants/{merchant_a}/own-pey-account-checks',
        headers={**csrf_a,'idempotency-key':'d'*32},content='{"api_key":"do-not-echo","api_key":"other"}')
    assert malformed.status_code == 422 and 'do-not-echo' not in malformed.text
    readiness=a.get(f'/v1/merchants/{merchant_a}/production-readiness').json()
    assert readiness['provider_observation_matches_current_declaration'] is True
    assert readiness['live_payments_enabled'] is False
    with factory() as db:
        obs=db.scalar(select(ProviderAccountObservation))
        assert obs.credential_ref == 'ephemeral_owner_key_v1' and key not in repr(obs.__dict__)
    assert a.post('/v1/webhooks/pey',json={'x':'synthetic'}).status_code == 503
    factory.kw['bind'].dispose()


def test_signup_modes_are_mutually_exclusive():
    import pytest
    with pytest.raises(ValueError):
        Settings(env='production',mode='DEMO',limited_launch=True,self_signup_no_email=True,
                 limited_registration_enabled=True).validate()


def test_hosted_signup_cannot_skip_email_verification():
    import pytest
    for environment in ('production', 'staging'):
        with pytest.raises(ValueError, match='Hosted signup without email verification is forbidden'):
            Settings(env=environment, mode='DEMO', limited_launch=True, self_signup_no_email=True).validate()
