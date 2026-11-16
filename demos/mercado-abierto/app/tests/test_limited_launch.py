"""Hosted limited launch exposes only functions whose dependencies are ready."""
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from rio_pey_codi.identity import HASHER
from rio_pey_codi.models import AuthLimit, Event, Intent, Membership, Merchant, User, database
from rio_pey_codi.platform import Settings, create_platform


def limited_settings(**changes):
    settings = Settings(
        env='production', mode='DEMO', limited_launch=True,
        database_url='postgresql://synthetic:synthetic@127.0.0.1/fixture', auto_create=False,
        email_mode='smtp', public_url='https://example.invalid', origin='https://example.invalid',
    )
    return replace(settings, **changes)


def test_limited_launch_accepts_missing_email_and_provider_credentials():
    limited_settings().validate()


@pytest.mark.parametrize('changes', [
    {'env': 'local'}, {'mode': 'LIVE'}, {'live_enabled': True}, {'auto_create': True},
    {'database_url': 'sqlite:///not-allowed.sqlite3'}, {'origin': 'http://example.invalid'},
    {'email_mode': 'memory'}, {'account_lookup_enabled': True},
    {'api_key': 'synthetic-key'}, {'webhook_secret': 'c3ludGhldGljLWtleS1mb3ItdGVzdGluZw=='},
])
def test_limited_launch_refuses_unsafe_configurations(changes):
    with pytest.raises(ValueError):
        limited_settings(**changes).validate()


def test_limited_launch_keeps_auth_and_payments_fail_closed(tmp_path, monkeypatch):
    import rio_pey_codi.platform as platform

    monkeypatch.delenv('VERCEL', raising=False)
    monkeypatch.delenv('VERCEL_ENV', raising=False)
    factory = database('sqlite+pysqlite:///' + str(tmp_path / 'launch.sqlite3'), auto_create=True)
    owner_id, merchant_id = 'a' * 32, 'b' * 32
    with factory.begin() as db:
        db.add(User(id=owner_id, email='owner@example.org', password_hash=HASHER.hash('synthetic-password-123'),
                    verified_at=1, created_at=1))
        db.flush()
        db.add(Merchant(id=merchant_id, name='Synthetic', owner_id=owner_id, created_at=1))
        db.flush()
        db.add(Membership(user_id=owner_id, merchant_id=merchant_id, role='owner'))
    monkeypatch.setattr(platform, 'database', lambda *_args, **_kwargs: factory)
    monkeypatch.setattr(platform, 'database_ready', lambda _factory: True)
    monkeypatch.setattr(platform, 'database_readiness', lambda _factory: (True, 'OK'))
    app = create_platform(limited_settings())
    client = TestClient(app, base_url='https://example.invalid')
    status = client.get('/healthz')
    assert status.status_code == 200
    assert status.json()['launch_mode'] == 'LIMITED'
    assert status.json()['registration_enabled'] is False
    assert status.json()['email_delivery'] == 'DISABLED'
    assert status.json()['payment_requests_enabled'] is False
    assert status.json()['webhook_enabled'] is False
    assert status.json()['live_payments_enabled'] is False
    assert status.json()['bank_settlement'] == 'NOT_OBSERVED'
    assert client.get('/public-status').json()['access_enabled'] is True
    assert client.get('/').status_code == 200
    assert client.get('/static/app.js').status_code == 200
    assert client.get('/openapi.json').status_code == 404

    signup = client.post('/v1/auth/signup', json={
        'email': 'new@example.org', 'password': 'synthetic-password-123', 'business_name': 'Synthetic',
    })
    assert signup.status_code == 503
    for route, body in [
        ('/v1/auth/resend-verification', {'email': 'new@example.org'}),
        ('/v1/auth/reset-request', {'email': 'new@example.org'}),
        ('/v1/auth/reset-confirm', {'token': 'x' * 40, 'password': 'synthetic-password-123'}),
    ]:
        assert client.post(route, json=body).status_code == 503
    assert client.post('/v1/webhooks/pey', json={'synthetic': True}).status_code == 503
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(AuthLimit)) == 0
        assert db.scalar(select(func.count()).select_from(Event)) == 0

    login = client.post('/v1/auth/login', json={'email': 'owner@example.org', 'password': 'synthetic-password-123'})
    assert login.status_code == 200
    assert client.get('/v1/auth/me').status_code == 200
    response = client.post('/v1/checkout/qr', headers={'x-csrf-token': login.json()['csrf_token']}, json={
        'merchant_id': merchant_id, 'order_id': 'sale-1', 'numref': '1', 'concept': 'Synthetic',
        'amount_minor': 100, 'expiration_s': 600,
    })
    assert response.status_code == 503
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Intent)) == 0
    factory.kw['bind'].dispose()


def test_limited_public_page_remains_read_only_when_database_is_unavailable(tmp_path, monkeypatch):
    import rio_pey_codi.platform as platform

    monkeypatch.delenv('VERCEL', raising=False)
    monkeypatch.delenv('VERCEL_ENV', raising=False)
    factory = database('sqlite+pysqlite:///' + str(tmp_path / 'offline.sqlite3'), auto_create=True)
    monkeypatch.setattr(platform, 'database', lambda *_args, **_kwargs: factory)
    monkeypatch.setattr(platform, 'database_ready', lambda _factory: False)
    monkeypatch.setattr(platform, 'database_readiness', lambda _factory: (False, 'NETWORK'))
    app = create_platform(limited_settings())
    client = TestClient(app, base_url='https://example.invalid')
    assert client.get('/').status_code == 200
    assert client.get('/static/app.js').status_code == 200
    state = client.get('/public-status')
    assert state.status_code == 200
    assert state.json()['launch_mode'] == 'LIMITED'
    assert state.json()['database_readiness'] == 'UNAVAILABLE'
    assert state.json()['database_failure'] == 'NETWORK'
    assert state.json()['access_enabled'] is False
    assert state.json()['registration_enabled'] is False
    assert state.json()['live_payments_enabled'] is False
    assert client.get('/healthz').status_code == 503
    assert client.get('/v1/auth/me').status_code == 503
    assert client.post('/v1/auth/signup', json={
        'email':'new@example.org', 'password':'synthetic-password-123', 'business_name':'Synthetic',
    }).status_code == 503
    with factory() as db:
        for model in (User, Intent, Event, AuthLimit):
            assert db.scalar(select(func.count()).select_from(model)) == 0
    factory.kw['bind'].dispose()


@pytest.mark.parametrize(('error_message', 'expected'), [
    ('synthetic-password certificate verify failed', 'TLS_VERIFY'),
    ('synthetic-password unknown certificate error', 'TLS'),
    ('synthetic-password root certificate file does not exist', 'TLS_ROOT_MISSING'),
    ('synthetic-password certificate verification failed', 'TLS_VERIFY'),
    ('synthetic-password sslrootcert unsupported', 'TLS_OPTION'),
    ('synthetic-password password authentication failed', 'AUTH'),
    ('synthetic-password could not translate host name', 'DNS'),
    ('synthetic-password timed out', 'TIMEOUT'),
    ('synthetic-password connection refused', 'NETWORK'),
    ('synthetic-password unexpected', 'UNAVAILABLE'),
])
def test_database_failure_diagnostics_are_fixed_non_secret_categories(error_message, expected):
    from rio_pey_codi.platform import database_readiness

    class FailingFactory:
        def __call__(self):
            raise RuntimeError(error_message)

    ready, reason = database_readiness(FailingFactory())
    assert ready is False and reason == expected
    assert 'synthetic-password' not in reason
