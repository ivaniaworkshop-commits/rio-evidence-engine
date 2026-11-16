"""Prevent a deployed function from silently using local-only defaults."""
import pytest

from rio_pey_codi.platform import Settings


@pytest.mark.parametrize('platform_env', [{'VERCEL':'1'}, {'VERCEL_ENV':'preview'},
                                           {'VERCEL_ENV':'production'}])
def test_vercel_never_accepts_local_database_and_memory_email_by_default(monkeypatch, platform_env):
    for name in ('VERCEL', 'VERCEL_ENV', 'APP_ENV', 'DATABASE_URL', 'EMAIL_MODE',
                 'ALLOW_CREATE_SCHEMA', 'RPG_MODE', 'PAYMENTS_LIVE_ENABLED',
                 'PEY_WEBHOOK_SECRET', 'PEY_WEBHOOK_SIGNING_KEY_REF',
                 'PEY_WEBHOOK_PREVIOUS_SECRETS_JSON', 'PEY_READONLY_ACCOUNT_LOOKUP_ENABLED'):
        monkeypatch.delenv(name, raising=False)
    for name, value in platform_env.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match='Vercel requires'):
        Settings.from_env().validate()


@pytest.mark.parametrize(('target', 'app_env'), [('preview','production'), ('production','staging')])
def test_vercel_preview_and_production_configurations_cannot_be_mixed(monkeypatch, target, app_env):
    monkeypatch.setenv('VERCEL', '1')
    monkeypatch.setenv('VERCEL_ENV', target)
    with pytest.raises(ValueError, match='Vercel requires'):
        Settings(env=app_env).validate()


def test_incomplete_hosted_configuration_returns_generic_503_on_all_routes(monkeypatch):
    import main
    from fastapi.testclient import TestClient

    monkeypatch.setenv('VERCEL', '1')
    monkeypatch.setenv('VERCEL_ENV', 'preview')
    monkeypatch.setenv('APP_ENV', 'local')
    monkeypatch.setenv('PEY_API_KEY', 'synthetic-sensitive-value')
    app = main.build_application()
    client = TestClient(app)
    for method, path in [('GET','/'), ('GET','/healthz'), ('GET','/openapi.json'),
                         ('POST','/v1/auth/signup'), ('POST','/v1/webhooks/pey')]:
        result = client.request(method, path)
        assert result.status_code == 503 and result.headers['cache-control'] == 'no-store'
        assert result.json() == {'status':'UNAVAILABLE', 'live_payments_enabled':False,
                                 'bank_payment_confirmed':False}
        assert 'synthetic-sensitive-value' not in result.text


def test_hosted_startup_error_is_not_exposed(monkeypatch):
    import main
    from fastapi.testclient import TestClient

    monkeypatch.setenv('VERCEL', '1')
    monkeypatch.setenv('VERCEL_ENV', 'production')
    def broken(): raise ValueError('synthetic-sensitive-error')
    monkeypatch.setattr(main, 'create_platform', broken)
    response = TestClient(main.build_application()).get('/healthz')
    assert response.status_code == 503 and 'synthetic-sensitive-error' not in response.text


def test_local_startup_errors_still_surface_for_developers(monkeypatch):
    import main
    monkeypatch.delenv('VERCEL', raising=False)
    monkeypatch.delenv('VERCEL_ENV', raising=False)
    def broken(): raise ValueError('local failure')
    monkeypatch.setattr(main, 'create_platform', broken)
    with pytest.raises(ValueError, match='local failure'):
        main.build_application()


@pytest.mark.parametrize(('username', 'password'), [('', 'synthetic'), ('synthetic', ''),
                                                     ('   ', 'synthetic'), ('synthetic', '  ')])
def test_hosted_email_requires_explicit_smtp_authentication(monkeypatch, username, password):
    monkeypatch.setenv('VERCEL', '1')
    monkeypatch.setenv('VERCEL_ENV', 'production')
    cfg = Settings(env='production', database_url='postgresql://synthetic:synthetic@127.0.0.1/fixture', auto_create=False,
                   email_mode='smtp', smtp_host='smtp.example.invalid', smtp_user=username,
                   smtp_password=password, smtp_sender='synthetic@example.invalid',
                   public_url='https://example.invalid', origin='https://example.invalid',
                   webhook_key_ref='prod-key')
    with pytest.raises(ValueError, match='SMTP authentication'):
        cfg.validate()


def test_staging_with_unreachable_database_is_unavailable(monkeypatch):
    import socket
    from fastapi.testclient import TestClient
    from rio_pey_codi.platform import create_platform

    monkeypatch.setenv('VERCEL', '1')
    monkeypatch.setenv('VERCEL_ENV', 'preview')
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1', 0))
        port = reserved.getsockname()[1]  # Bound but not listening: deterministic refusal.
        cfg = Settings(env='staging', database_url=f'postgresql://synthetic:synthetic-sensitive@127.0.0.1:{port}/fixture',
                       auto_create=False, email_mode='smtp', smtp_host='smtp.example.invalid',
                       smtp_sender='synthetic@example.invalid', smtp_user='synthetic', smtp_password='synthetic',
                       public_url='https://stage.example.invalid',
                       origin='https://stage.example.invalid', webhook_key_ref='stage-key')
        app = create_platform(cfg)
        try:
            client = TestClient(app)
            # Public HTML remains available so the browser can explain the outage;
            # account and health APIs still fail closed against an unavailable DB.
            page = client.get('/')
            assert page.status_code == 200 and 'synthetic-sensitive' not in page.text
            assert page.headers['cache-control'] == 'no-store'
            status = client.get('/public-status').json()
            assert status['access_enabled'] is False
            assert status['registration_enabled'] is False
            assert status['live_payments_enabled'] is False
            for method, path in [('GET', '/healthz'), ('POST', '/v1/auth/signup')]:
                result = client.request(method, path)
                assert result.status_code == 503
                assert result.headers['cache-control'] == 'no-store'
                assert result.json()['bank_payment_confirmed'] is False
                assert 'synthetic-sensitive' not in result.text
        finally:
            app.state.accounts.Session.kw['bind'].dispose()
