"""Account email can be enabled independently from payments in limited mode."""
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from sqlalchemy import func, select

from rio_pey_codi.models import User, database
from rio_pey_codi.platform import Settings, create_platform


def settings(**changes):
    cfg = Settings(
        env='production', mode='DEMO', limited_launch=True,
        limited_registration_enabled=True,
        email_delivery_attested=True,
        database_url='postgresql://synthetic:synthetic@127.0.0.1/fixture', auto_create=False,
        email_mode='smtp', public_url='https://rio.example.org', origin='https://rio.example.org',
        smtp_host='smtp.example.org', smtp_port=587, smtp_user='synthetic-user',
        smtp_password='synthetic-password', smtp_sender='no-reply@example.org',
    )
    return replace(cfg, **changes)


@pytest.mark.parametrize('field', ['smtp_host', 'smtp_user', 'smtp_password', 'smtp_sender'])
def test_limited_registration_requires_complete_authenticated_smtp(field):
    with pytest.raises(ValueError):
        settings(**{field: ''}).validate()


def test_registration_flag_defaults_off_and_requires_limited_launch(monkeypatch):
    monkeypatch.delenv('RPG_LIMITED_REGISTRATION_ENABLED', raising=False)
    assert Settings.from_env().limited_registration_enabled is False
    monkeypatch.setenv('RPG_LIMITED_REGISTRATION_ENABLED', 'true')
    assert Settings.from_env().limited_registration_enabled is True
    with pytest.raises(ValueError):
        settings(limited_launch=False).validate()


def test_resend_integration_uses_injected_key_without_exposing_it(monkeypatch):
    monkeypatch.delenv('SMTP_PASSWORD', raising=False)
    monkeypatch.setenv('RESEND_API_KEY', 'synthetic-resend-key')
    monkeypatch.setenv('SMTP_FROM', 'noreply@example.org')
    cfg = Settings.from_env()
    assert (cfg.smtp_host, cfg.smtp_port, cfg.smtp_user) == ('smtp.resend.com', 465, 'resend')
    assert cfg.smtp_password == 'synthetic-resend-key'
    assert cfg.smtp_sender == 'noreply@example.org'
    assert 'synthetic-resend-key' not in repr(cfg)
    assert cfg.limited_registration_enabled is False


def test_explicit_smtp_credentials_take_precedence_over_resend(monkeypatch):
    monkeypatch.setenv('RESEND_API_KEY', 'synthetic-resend-key')
    monkeypatch.setenv('SMTP_PASSWORD', 'synthetic-smtp-password')
    monkeypatch.setenv('SMTP_HOST', 'smtp.example.org')
    monkeypatch.setenv('SMTP_PORT', '587')
    monkeypatch.setenv('SMTP_USER', 'smtp-user')
    cfg = Settings.from_env()
    assert (cfg.smtp_host, cfg.smtp_port, cfg.smtp_user) == ('smtp.example.org', 587, 'smtp-user')
    assert cfg.smtp_password == 'synthetic-smtp-password'


def test_limited_registration_is_separate_from_payment_and_webhook(tmp_path, monkeypatch):
    import rio_pey_codi.platform as platform

    monkeypatch.delenv('VERCEL', raising=False)
    monkeypatch.delenv('VERCEL_ENV', raising=False)
    factory = database('sqlite+pysqlite:///' + str(tmp_path / 'accounts.sqlite3'), auto_create=True)
    monkeypatch.setattr(platform, 'database', lambda *_args, **_kwargs: factory)
    monkeypatch.setattr(platform, 'database_ready', lambda _factory: True)
    monkeypatch.setattr(platform, 'database_readiness', lambda _factory: (True, 'OK'))
    sent = []

    class SyntheticSMTP:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ('smtp.example.org', 587, 10)
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def ehlo(self): pass
        def starttls(self, *, context): assert context is not None
        def login(self, username, password):
            assert (username, password) == ('synthetic-user', 'synthetic-password')
        def send_message(self, message): sent.append(message)

    monkeypatch.setattr('rio_pey_codi.identity.smtplib.SMTP', SyntheticSMTP)
    client = TestClient(create_platform(settings()), base_url='https://rio.example.org')
    status = client.get('/public-status').json()
    assert status['registration_enabled'] is True
    assert status['email_delivery'] == 'smtp'
    assert status['email_delivery_verified'] is False
    assert status['payment_requests_enabled'] is False
    assert status['webhook_enabled'] is False
    assert status['live_payments_enabled'] is False

    credentials = {'email': 'synthetic@example.org', 'password': 'synthetic-password-123'}
    signup = client.post('/v1/auth/signup', json={**credentials, 'business_name': 'Synthetic'})
    assert signup.status_code == 201
    assert sent[-1]['To'] == credentials['email']
    assert client.post('/v1/auth/login', json=credentials).status_code == 403
    verify_link = next(line for line in sent[-1].get_content().splitlines() if line.startswith('https://'))
    verify_token = parse_qs(urlsplit(verify_link).fragment)['token'][0]
    assert client.get('/verify-email').status_code == 200
    assert client.post('/v1/auth/verify-email', json={'token': verify_token}).status_code == 200
    login = client.post('/v1/auth/login', json=credentials)
    assert login.status_code == 200
    assert client.get('/v1/auth/me').status_code == 200
    assert client.post('/v1/checkout/qr', headers={'x-csrf-token': login.json()['csrf_token']}, json={
        'merchant_id': signup.json()['merchant_id'], 'order_id': 'sale-1', 'numref': '1',
        'concept': 'Synthetic', 'amount_minor': 100, 'expiration_s': 600,
    }).status_code == 503
    assert client.post('/v1/webhooks/pey', json={'synthetic': True}).status_code == 503
    assert client.post('/v1/auth/reset-request', json={'email': credentials['email']}).status_code == 200
    reset_link = next(line for line in sent[-1].get_content().splitlines() if line.startswith('https://'))
    reset_token = parse_qs(urlsplit(reset_link).fragment)['token'][0]
    new_password = 'synthetic-new-password-456'
    assert client.get('/reset-password').status_code == 200
    assert client.post('/v1/auth/reset-confirm', json={'token': reset_token, 'password': new_password}).status_code == 200
    assert client.get('/v1/auth/me').status_code == 401
    assert client.post('/v1/auth/login', json={**credentials, 'password': new_password}).status_code == 200
    factory.kw['bind'].dispose()


def test_limited_registration_fails_closed_if_database_is_unavailable(tmp_path, monkeypatch):
    import rio_pey_codi.platform as platform

    monkeypatch.delenv('VERCEL', raising=False)
    monkeypatch.delenv('VERCEL_ENV', raising=False)
    factory = database('sqlite+pysqlite:///' + str(tmp_path / 'offline.sqlite3'), auto_create=True)
    monkeypatch.setattr(platform, 'database', lambda *_args, **_kwargs: factory)
    monkeypatch.setattr(platform, 'database_ready', lambda _factory: False)
    monkeypatch.setattr(platform, 'database_readiness', lambda _factory: (False, 'NETWORK'))
    client = TestClient(create_platform(settings()), base_url='https://rio.example.org')
    assert client.get('/public-status').json()['registration_enabled'] is False
    assert client.post('/v1/auth/signup', json={
        'email': 'synthetic@example.org', 'password': 'synthetic-password-123', 'business_name': 'Synthetic',
    }).status_code == 503
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0
    factory.kw['bind'].dispose()
