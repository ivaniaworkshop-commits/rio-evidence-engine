from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from rio_pey_codi.identity import HASHER, now, sha
from rio_pey_codi.models import Merchant, Membership, OneTimeToken, User
from rio_pey_codi.platform import Settings, create_platform


def test_owner_can_invite_and_recipient_owns_only_their_merchant(tmp_path):
    owner = 'a' * 32
    original_merchant = 'b' * 32
    cfg = Settings(database_url='sqlite+pysqlite:///' + str(tmp_path / 'invite.sqlite'),
                   auto_create=True, platform_owner_id=owner)
    app = create_platform(cfg)
    t = now()
    with app.state.accounts.Session.begin() as db:
        db.add(User(id=owner, email='owner@example.org',
                    password_hash=HASHER.hash('owner-password-123'), created_at=t))
        db.flush()
        db.add(Merchant(id=original_merchant, name='Owner', owner_id=owner, created_at=t))
        db.flush()
        db.add(Membership(user_id=owner, merchant_id=original_merchant, role='owner'))
        db.add(OneTimeToken(token_hash=sha('previous-owner-invitation'), user_id=owner,
                            purpose='owner_invitation', used_at=t, expires_at=t+1))
    client = TestClient(app)
    assert client.post('/v1/admin/invitations', json={
        'email':'first@example.org', 'business_name':'First',
    }).status_code == 401
    login = client.post('/v1/auth/login', json={
        'email':'owner@example.org', 'password':'owner-password-123',
    })
    assert login.status_code == 200
    headers = {'x-csrf-token':login.json()['csrf_token']}
    assert client.get('/v1/auth/me').json()['can_invite'] is True
    payload = {'email':'first@example.org', 'business_name':'First'}
    first = client.post('/v1/admin/invitations', headers=headers, json=payload)
    assert first.status_code == 201
    old = parse_qs(urlsplit(first.json()['invitation_url']).fragment)['owner_invite'][0]
    second = client.post('/v1/admin/invitations', headers=headers, json=payload)
    assert second.status_code == 201
    token = parse_qs(urlsplit(second.json()['invitation_url']).fragment)['owner_invite'][0]
    assert token != old
    assert client.post('/v1/auth/activate-owner', json={
        'token':old, 'password':'recipient-password-123',
    }).status_code == 400
    activation = client.post('/v1/auth/activate-owner', json={
        'token':token, 'password':'recipient-password-123',
    })
    assert activation.status_code == 200
    assert activation.json()['email_verified'] is False
    assert client.post('/v1/auth/activate-owner', json={
        'token':token, 'password':'recipient-password-123',
    }).status_code == 400
    assert client.post('/v1/admin/invitations', headers=headers, json=payload).status_code == 409
    assert client.post('/v1/auth/logout', headers=headers).status_code == 200
    recipient = client.post('/v1/auth/login', json={
        'email':'first@example.org', 'password':'recipient-password-123',
    })
    assert recipient.status_code == 200
    info = client.get('/v1/auth/me').json()
    assert info['verified'] is False and info['can_invite'] is False
    merchants = client.get('/v1/merchants').json()['merchants']
    assert len(merchants) == 1 and merchants[0]['name'] == 'First'
    assert merchants[0]['id'] != original_merchant
    assert client.post('/v1/admin/invitations',
        headers={'x-csrf-token':recipient.json()['csrf_token']},
        json={'email':'third@example.org', 'business_name':'Third'}).status_code == 403
