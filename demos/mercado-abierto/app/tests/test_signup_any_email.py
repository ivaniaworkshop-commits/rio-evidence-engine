"""Registration accepts different email providers without bypassing verification."""
import smtplib

import pytest
from fastapi.testclient import TestClient

from rio_pey_codi.platform import Settings, create_platform


@pytest.mark.parametrize('email', [
    'rio.synthetic.user@gmail.com',
    'rio.synthetic.user@outlook.com',
    'rio.synthetic.user@yahoo.com.mx',
    'rio.synthetic.user@proton.me',
    'rio.synthetic.user@example.org',
    'rio.synthetic.user@bücher.de',
    'usuario.ñ@example.org',
])
def test_registration_allows_provider_but_requires_verified_address(tmp_path, email):
    app = create_platform(Settings(database_url='sqlite+pysqlite:///' + str(tmp_path / 'app.sqlite3')))
    client = TestClient(app)
    credentials = {'email': email, 'password': 'synthetic-password-123'}
    signup = client.post('/v1/auth/signup', json={**credentials, 'business_name': 'Synthetic'})
    assert signup.status_code == 201
    assert signup.json()['status'] == 'VERIFICATION_REQUIRED'
    assert client.post('/v1/auth/login', json=credentials).status_code == 403

    delivery = app.state.mailer.outbox[-1]
    assert delivery['email'] == email and delivery['kind'] == 'verify'
    assert client.post('/v1/auth/verify-email', json={'token': delivery['token']}).status_code == 200
    assert client.post('/v1/auth/login', json=credentials).status_code == 200
    assert client.get('/v1/auth/me').json()['email'] == email


def test_registration_still_rejects_invalid_email(tmp_path):
    app = create_platform(Settings(database_url='sqlite+pysqlite:///' + str(tmp_path / 'app.sqlite3')))
    client = TestClient(app)
    response = client.post('/v1/auth/signup', json={
        'email': 'not-an-email', 'password': 'synthetic-password-123', 'business_name': 'Synthetic',
    })
    assert response.status_code == 422
    assert app.state.mailer.outbox == []


@pytest.mark.parametrize('email', ['straße@example.org', 'Owner@example.org'])
def test_registration_rejects_address_if_normalization_would_change_recipient(tmp_path, email):
    app = create_platform(Settings(database_url='sqlite+pysqlite:///' + str(tmp_path / 'app.sqlite3')))
    client = TestClient(app)
    response = client.post('/v1/auth/signup', json={
        'email': email, 'password': 'synthetic-password-123', 'business_name': 'Synthetic',
    })
    assert response.status_code == 422
    assert app.state.mailer.outbox == []
    with app.state.accounts.Session() as db:
        from sqlalchemy import func, select
        from rio_pey_codi.models import User
        assert db.scalar(select(func.count()).select_from(User)) == 0


def test_resend_verification_response_does_not_disclose_account_state(tmp_path):
    app = create_platform(Settings(database_url='sqlite+pysqlite:///' + str(tmp_path / 'app.sqlite3')))
    client = TestClient(app)
    email = 'rio.synthetic.user@outlook.com'
    signup = client.post('/v1/auth/signup', json={
        'email': email, 'password': 'synthetic-password-123', 'business_name': 'Synthetic',
    })
    assert signup.status_code == 201
    first_token = app.state.mailer.outbox[-1]['token']
    unknown = client.post('/v1/auth/resend-verification', json={'email': 'unknown@example.org'})
    resent = client.post('/v1/auth/resend-verification', json={'email': email})
    assert unknown.status_code == resent.status_code == 200
    assert unknown.json() == resent.json()
    assert len(app.state.mailer.outbox) == 2
    second_token = app.state.mailer.outbox[-1]['token']
    assert second_token != first_token
    assert client.post('/v1/auth/verify-email', json={'token': second_token}).status_code == 200
    verified = client.post('/v1/auth/resend-verification', json={'email': email})
    assert verified.status_code == 200 and verified.json() == unknown.json()
    assert len(app.state.mailer.outbox) == 2


def test_smtp_signup_targets_the_users_provider_without_real_delivery(tmp_path, monkeypatch):
    deliveries = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ('smtp.example.org', 587, 10)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def ehlo(self):
            pass

        def starttls(self, *, context):
            assert context is not None

        def login(self, username, password):
            assert (username, password) == ('synthetic-sender', 'synthetic-password')

        def send_message(self, message):
            deliveries.append(message)

    monkeypatch.setattr('rio_pey_codi.identity.smtplib.SMTP', FakeSMTP)
    app = create_platform(Settings(
        database_url='sqlite+pysqlite:///' + str(tmp_path / 'app.sqlite3'),
        email_mode='smtp', public_url='https://rio.example.org',
        smtp_host='smtp.example.org', smtp_port=587,
        smtp_user='synthetic-sender', smtp_password='synthetic-password',
        smtp_sender='no-reply@example.org',
    ))
    client = TestClient(app)
    response = client.post('/v1/auth/signup', json={
        'email': 'rio.synthetic.user@outlook.com', 'password': 'synthetic-password-123',
        'business_name': 'Synthetic',
    })
    assert response.status_code == 201
    assert len(deliveries) == 1
    assert deliveries[0]['To'] == 'rio.synthetic.user@outlook.com'
    assert deliveries[0]['From'] == 'no-reply@example.org'
    assert 'https://rio.example.org/verify-email#token=' in deliveries[0].get_content()


@pytest.mark.parametrize('supports_utf8', [True, False])
def test_international_address_obeys_smtp_server_capability(tmp_path, monkeypatch, supports_utf8):
    real_send_message = smtplib.SMTP.send_message
    deliveries = []

    class FakeSMTP:
        send_message = real_send_message

        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def ehlo(self):
            pass

        def ehlo_or_helo_if_needed(self):
            pass

        def starttls(self, *, context):
            assert context is not None

        def login(self, *_args):
            pass

        def has_extn(self, name):
            assert name == 'smtputf8'
            return supports_utf8

        def sendmail(self, sender, recipients, message, options, rcpt_options):
            deliveries.append((sender, recipients, options))
            return {}

    monkeypatch.setattr('rio_pey_codi.identity.smtplib.SMTP', FakeSMTP)
    app = create_platform(Settings(
        database_url='sqlite+pysqlite:///' + str(tmp_path / 'app.sqlite3'),
        email_mode='smtp', public_url='https://rio.example.org',
        smtp_host='smtp.example.org', smtp_port=587, smtp_sender='no-reply@example.org',
    ))
    client = TestClient(app)
    email = 'usuario.ñ@example.org'
    credentials = {'email': email, 'password': 'synthetic-password-123'}
    response = client.post('/v1/auth/signup', json={**credentials, 'business_name': 'Synthetic'})
    if supports_utf8:
        assert response.status_code == 201
        assert len(deliveries) == 1
        assert deliveries[0][1] == [email]
        assert 'SMTPUTF8' in deliveries[0][2]
    else:
        assert response.status_code == 503
        assert deliveries == []
        login = client.post('/v1/auth/login', json=credentials)
        assert login.status_code == 503
        assert login.json()['code'] == 'EMAIL_DELIVERY_UNAVAILABLE'
        assert client.get('/v1/auth/me').status_code == 401
