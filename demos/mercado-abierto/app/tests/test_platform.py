"""Tenant, identity and payment regressions: only LOCAL DEMO money."""
import base64
import json
import time
from dataclasses import replace
from fastapi.testclient import TestClient
import pytest
from rio_pey_codi.platform import Settings,create_platform
from rio_pey_codi.signatures import make_signature

SECRET='whsec_'+base64.b64encode(b'local-test-secret-32-bytes-long-ok').decode()

@pytest.fixture
def env(tmp_path):
    cfg=Settings(database_url='sqlite+pysqlite:///'+str(tmp_path/'rio.sqlite3'),webhook_secret=SECRET)
    app=create_platform(cfg)
    client=TestClient(app)
    return app,client

def signup(env,email='owner@example.com',business='Negocio local',password='veryLongSecurePass123'):
    app,client=env
    r=client.post('/v1/auth/signup',json={'email':email,'password':password,'business_name':business})
    assert r.status_code==201,r.text
    return r.json()

def verified_login(env,email='owner@example.com',password='veryLongSecurePass123'):
    app,client=env
    t=next(m['token'] for m in app.state.mailer.outbox if m['kind']=='verify' and m['email']==email)
    assert client.post('/v1/auth/verify-email',json={'token':t}).status_code==200
    r=client.post('/v1/auth/login',json={'email':email,'password':password})
    assert r.status_code==200,r.text
    csrf=r.json()['csrf_token']
    return csrf

def checkout(env,merchant_id,csrf,order='a1',amount=5000):
    return env[1].post('/v1/checkout/qr',headers={'x-csrf-token':csrf},json={
        'merchant_id':merchant_id,'order_id':order,'numref':order,'concept':'Pan','amount_minor':amount,'expiration_s':600})

def signed_webhook(client,payload,event_id='event01'):
    raw=json.dumps(payload,separators=(',',':')).encode()
    t=int(time.time())
    return client.post('/v1/webhooks/pey',data=raw,headers={'webhook-id':event_id,
          'webhook-timestamp':str(t),'webhook-signature':make_signature(SECRET,event_id,t,raw),'content-type':'application/json'})

def test_signup_verification_login_session_logout(env):
    signup(env)
    app,client=env
    assert client.post('/v1/auth/login',json={'email':'owner@example.com','password':'veryLongSecurePass123'}).status_code==403
    csrf=verified_login(env)
    assert client.get('/v1/auth/me').status_code==200
    assert client.get('/v1/auth/me').json()['email']=='owner@example.com'
    csrf=client.get('/v1/auth/me').json()['csrf_token']
    assert client.post('/v1/auth/logout',headers={'x-csrf-token':csrf}).status_code==200
    assert client.get('/v1/auth/me').status_code==401

def test_signup_does_not_disclose_token(env):
    r=signup(env)
    assert 'token' not in json.dumps(r).lower()
    assert env[0].state.mailer.outbox and 'token' in env[0].state.mailer.outbox[0]

def test_duplicate_user(env):
    signup(env)
    r=env[1].post('/v1/auth/signup',json={'email':'OWNER@example.com','password':'veryLongSecurePass123','business_name':'Otro'})
    assert r.status_code==409

def test_short_password(env):
    r=env[1].post('/v1/auth/signup',json={'email':'owner@example.com','password':'123','business_name':'Local'})
    assert r.status_code==422

def test_invalid_verification_token(env):
    assert env[1].post('/v1/auth/verify-email',json={'token':'invalid-token-length-xxxxxxxxxx'}).status_code==400

def test_unverified_cannot_charge(env):
    m=signup(env)['merchant_id']
    res=checkout(env,m,'anything')
    assert res.status_code==401

def test_csrf_required(env):
    m=signup(env)['merchant_id'];csrf=verified_login(env)
    assert checkout(env,m,'none').status_code==403
    assert checkout(env,m,csrf).status_code==201


def test_csrf_remains_valid_when_another_tab_reads_the_session(env):
    signup(env)
    csrf = verified_login(env)
    second = TestClient(env[0], cookies=env[1].cookies)
    other_csrf = second.get('/v1/auth/me').json()['csrf_token']
    assert other_csrf == csrf
    assert env[1].post('/v1/merchants', headers={'x-csrf-token':csrf}, json={'name':'Primero'}).status_code == 201
    assert second.post('/v1/merchants', headers={'x-csrf-token':other_csrf}, json={'name':'Segundo'}).status_code == 201


def test_csrf_is_session_specific_and_legacy_session_can_upgrade(env):
    from rio_pey_codi.identity import sha
    from rio_pey_codi.models import SessionRow

    signup(env)
    first_csrf = verified_login(env)
    other = TestClient(env[0])
    login = other.post('/v1/auth/login', json={'email':'owner@example.com', 'password':'veryLongSecurePass123'})
    other_csrf = login.json()['csrf_token']
    assert first_csrf != other_csrf
    assert other.post('/v1/merchants', headers={'x-csrf-token':first_csrf}, json={'name':'No autorizado'}).status_code == 403

    sid = env[1].cookies.get('rio_sid')
    with env[0].state.accounts.Session.begin() as db:
        db.get(SessionRow, sha(sid)).csrf_hash = sha('legacy-synthetic-token')
    upgraded = env[1].get('/v1/auth/me').json()['csrf_token']
    assert upgraded == first_csrf
    assert env[1].post('/v1/merchants', headers={'x-csrf-token':'legacy-synthetic-token'}, json={'name':'Antiguo'}).status_code == 403
    assert env[1].post('/v1/merchants', headers={'x-csrf-token':upgraded}, json={'name':'Actual'}).status_code == 201

def test_create_checkout_and_status(env):
    m=signup(env)['merchant_id'];csrf=verified_login(env)
    r=checkout(env,m,csrf)
    assert r.status_code==201,r.text
    obj=r.json()['intent']
    assert obj['status']=='QR_ISSUED' and obj['amount_minor']==5000
    assert obj['bank_payment_confirmed'] is False
    assert 'NO PAGABLE' in obj['qr_display']
    st=env[1].get('/v1/checkout/qr/'+obj['id'])
    assert st.status_code==200 and st.json()['bank_payment_confirmed'] is False

def test_checkout_idempotent_and_conflict(env):
    m=signup(env)['merchant_id'];csrf=verified_login(env)
    assert checkout(env,m,csrf).status_code==201
    assert checkout(env,m,csrf).json()['status']=='REPLAY_NO_PROVIDER_RETRY'
    assert checkout(env,m,csrf,amount=123).status_code==409


def test_checkout_by_order_recovers_only_authorized_merchant(env):
    merchant = signup(env)['merchant_id']
    csrf = verified_login(env)
    intent = checkout(env, merchant, csrf, order='recover-123', amount=15000).json()['intent']
    path = f'/v1/merchants/{merchant}/checkout-orders/recover-123'
    response = env[1].get(path)
    assert response.status_code == 200
    assert response.json()['intent']['id'] == intent['id']
    assert response.json()['intent']['concept'] == 'Pan'
    assert response.json()['intent']['amount_minor'] == 15000
    assert response.json()['intent']['expiration_s'] == 600
    assert response.json()['bank_payment_confirmed'] is False
    assert env[1].get(f'/v1/merchants/{merchant}/checkout-orders/missing').status_code == 404

    outsider = (env[0], TestClient(env[0]))
    signup(outsider, 'outsider-recovery@example.com')
    verified_login(outsider, 'outsider-recovery@example.com')
    assert outsider[1].get(path).status_code == 404


def test_uncertain_checkout_replay_does_not_call_provider_again(tmp_path):
    class TimeoutProvider:
        calls = 0

        def create_qr(self, **_kwargs):
            self.calls += 1
            raise TimeoutError('synthetic timeout')

    provider = TimeoutProvider()
    app = create_platform(Settings(database_url='sqlite+pysqlite:///' + str(tmp_path/'uncertain.sqlite3')),
                          provider=provider)
    env = (app, TestClient(app))
    merchant = signup(env)['merchant_id']
    csrf = verified_login(env)
    assert checkout(env, merchant, csrf, order='uncertain').status_code == 502
    path = f'/v1/merchants/{merchant}/checkout-orders/uncertain'
    assert env[1].get(path).json()['intent']['status'] == 'PROVIDER_UNCERTAIN'
    retry = checkout(env, merchant, csrf, order='uncertain')
    assert retry.status_code == 201
    assert retry.json()['status'] == 'REPLAY_NO_PROVIDER_RETRY'
    assert retry.json()['intent']['status'] == 'PROVIDER_UNCERTAIN'
    assert provider.calls == 1


def test_reference_collision_is_identified_before_provider_call(env):
    from unittest.mock import patch
    from rio_pey_codi.pey import MockPeyGateway, QRResult

    merchant_id = signup(env)['merchant_id']
    csrf = verified_login(env)
    client = env[1]

    def submit(order, reference, amount=15000, merchant=merchant_id):
        return client.post('/v1/checkout/qr', headers={'x-csrf-token': csrf}, json={
            'merchant_id': merchant, 'order_id': order, 'numref': reference,
            'concept': 'Pedido', 'amount_minor': amount, 'expiration_s': 600,
        })

    def issue(_gateway, *, intent_id, **_kwargs):
        return QRResult('DEMO_' + intent_id, 'synthetic')

    with patch.object(MockPeyGateway, 'create_qr', autospec=True, side_effect=issue) as provider:
        assert submit('first', '12345').status_code == 201
        conflict = submit('second', '12345')
        assert conflict.status_code == 409
        assert conflict.json()['code'] == 'REFERENCE_TAKEN'
        assert provider.call_count == 1
        assert submit('second', '12346').status_code == 201
        assert submit('second', '12346').json()['status'] == 'REPLAY_NO_PROVIDER_RETRY'
        assert provider.call_count == 2
        different_amount = submit('second', '12346', amount=15001)
        assert different_amount.status_code == 409
        assert 'code' not in different_amount.json()
        assert provider.call_count == 2
        other = client.post('/v1/merchants', headers={'x-csrf-token': csrf}, json={'name':'Otro negocio'}).json()['id']
        assert submit('third', '12345', merchant=other).status_code == 201
        assert provider.call_count == 3


def test_checkout_ui_preserves_order_across_reference_collision_and_timeout():
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which('node')
    if node is None:
        pytest.skip('Node is required for the checkout UI regression')
    script = Path(__file__).with_name('checkout_reference_ui.cjs')
    result = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=20, check=True)
    assert 'CHECKOUT_REFERENCE_UI_OK' in result.stdout


def test_checkout_ui_recovers_uncertain_order_after_reload():
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which('node')
    if node is None:
        pytest.skip('Node is required for the checkout UI regression')
    script = Path(__file__).with_name('checkout_recovery_ui.cjs')
    result = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=20, check=True)
    assert 'CHECKOUT_RECOVERY_UI_OK' in result.stdout

def test_cross_merchant_rejected(env):
    signup(env);csrf=verified_login(env)
    assert checkout(env,'f'*32,csrf).status_code==404

def test_multi_user_isolation(env):
    merchant_1=signup(env)['merchant_id'];csrf1=verified_login(env)
    item=checkout(env,merchant_1,csrf1).json()['intent']
    env[1].post('/v1/auth/logout',headers={'x-csrf-token':csrf1})
    merchant_2=signup(env,'second@example.com')['merchant_id'];csrf2=verified_login(env,'second@example.com')
    assert checkout(env,merchant_1,csrf2,order='two').status_code==404
    assert env[1].get('/v1/checkout/qr/'+item['id']).status_code==404
    assert checkout(env,merchant_2,csrf2,order='three').status_code==201

def test_add_merchant_and_member_visibility(env):
    signup(env);csrf=verified_login(env)
    r=env[1].post('/v1/merchants',headers={'x-csrf-token':csrf},json={'name':'La Tercera Tienda'})
    assert r.status_code==201
    assert len(env[1].get('/v1/merchants').json()['merchants'])==2

def test_webhook_requires_signature(env):
    assert env[1].post('/v1/webhooks/pey',data=b'{}').status_code==401

def test_signed_webhook_reports_not_bank_settlement(env):
    m=signup(env)['merchant_id'];csrf=verified_login(env)
    obj=checkout(env,m,csrf)['intent'] if False else checkout(env,m,csrf).json()['intent']
    key='DEMO_'+obj['id']
    payload={'type':'codi.qr.payment_received','codiQrId':key,'amount':50,'apiKeyId':'mock','transactionId':'tx1','numRef':'a1'}
    r=signed_webhook(env[1],payload)
    assert r.status_code==200,r.text
    assert r.json()['outcome']=='PROVIDER_REPORTED' and r.json()['bank_settlement']=='NOT_VERIFIED'
    data=env[1].get('/v1/checkout/qr/'+obj['id']).json()
    assert data['provider_reported_payment'] is True and data['bank_payment_confirmed'] is False
    assert signed_webhook(env[1],payload).json()['outcome']=='DUPLICATE_EVENT'

def test_webhook_amount_mismatch_not_paid(env):
    m=signup(env)['merchant_id'];csrf=verified_login(env)
    obj=checkout(env,m,csrf).json()['intent']
    payload={'type':'codi.qr.payment_received','codiQrId':'DEMO_'+obj['id'],'amount':99,'apiKeyId':'mock','transactionId':'tx1','numRef':'a1'}
    assert signed_webhook(env[1],payload).status_code==409
    assert env[1].get('/v1/checkout/qr/'+obj['id']).json()['intent']['status']=='QR_ISSUED'

def test_webhook_before_qr_is_pending(env):
    payload={'type':'codi.qr.payment_received','codiQrId':'not-yet-linked','amount':50,'apiKeyId':'mock','transactionId':'tx1','numRef':'one'}
    assert signed_webhook(env[1],payload).json()['outcome']=='PENDING_LINKAGE'

def test_forged_webhook_rejected(env):
    raw=b'{"type":"codi.qr.payment_received"}'
    t=int(time.time())
    res=env[1].post('/v1/webhooks/pey',data=raw,headers={'webhook-id':'forged','webhook-timestamp':str(t),'webhook-signature':'v1,forged'})
    assert res.status_code==401

def test_reset_revokes_sessions(env):
    signup(env);csrf=verified_login(env)
    client=env[1]
    assert client.post('/v1/auth/reset-request',json={'email':'owner@example.com'}).status_code==200
    token=next(m['token'] for m in env[0].state.mailer.outbox if m['kind']=='reset')
    assert client.post('/v1/auth/reset-confirm',json={'token':token,'password':'newSecurePassword456'}).status_code==200
    assert client.get('/v1/auth/me').status_code==401
    assert client.post('/v1/auth/login',json={'email':'owner@example.com','password':'newSecurePassword456'}).status_code==200
    assert client.post('/v1/auth/reset-confirm',json={'token':token,'password':'newSecurePassword456'}).status_code==400

def test_staging_refuses_sqlite_or_memory_email():
    s=Settings(env='staging')
    with pytest.raises(ValueError):s.validate()

def test_live_cannot_be_unlocked_without_attestations():
    with pytest.raises(ValueError):Settings(mode='LIVE',live_enabled=True).validate()

def test_never_enable_live_in_demo():
    with pytest.raises(ValueError):Settings(mode='DEMO',live_enabled=True).validate()

def test_health_explicit_no_bank_settlement(env):
    d=env[1].get('/healthz').json()
    assert d['bank_settlement']=='NOT_OBSERVED'

def test_home_page(env):
    resp=env[1].get('/')
    assert resp.status_code==200 and 'Iniciar sesión' in resp.text
    assert 'id="dashboard"' not in resp.text
    assert env[1].get('/static/app.js').status_code==200


def test_home_page_serves_original_provider_logos(env):
    import hashlib

    signup(env)
    verified_login(env)
    html = env[1].get('/').text
    assert 'alt="pey y CoDi"' in html
    assert 'prefers-color-scheme: dark' in html
    expected = {
        'pey_codi_light.svg':'7c75bb68bceef48e79b2a0db6fe397bcaf6c9be36bdf6166fa8412a56809f1c4',
        'pey_codi_dark.svg':'d88ce81917a79fd14bff890a1c98988da710715eb834f6756f9da2398bfe0664',
    }
    for name, digest in expected.items():
        response = env[1].get('/static/' + name)
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('image/svg+xml')
        assert hashlib.sha256(response.content).hexdigest() == digest

def test_merchant_creation_requires_csrf(env):
    signup(env);verified_login(env)
    assert env[1].post('/v1/merchants',json={'name':'Dos'}).status_code==403


def test_reset_request_is_rate_limited(env):
    client = env[1]
    for _ in range(7):
        assert client.post('/v1/auth/reset-request', json={'email':'unknown@example.com'}).status_code == 200
    assert client.post('/v1/auth/reset-request', json={'email':'unknown@example.com'}).status_code == 429


def test_owner_can_grant_checkout_permission_without_granting_admin_access(env):
    merchant = signup(env)['merchant_id']
    owner_csrf = verified_login(env)
    employee = (env[0], TestClient(env[0]))
    signup(employee, 'employee@example.com')
    employee_csrf = verified_login(employee, 'employee@example.com')
    path = f'/v1/merchants/{merchant}/members'
    payload = {'email':'employee@example.com', 'role':'reader'}
    assert env[1].put(path, headers={'x-csrf-token':owner_csrf}, json=payload).status_code == 200
    assert checkout(employee, merchant, employee_csrf).status_code == 403
    payload['role'] = 'cashier'
    assert employee[1].put(path, headers={'x-csrf-token':employee_csrf}, json=payload).status_code == 404
    assert env[1].put(path, headers={'x-csrf-token':owner_csrf}, json=payload).status_code == 200
    assert checkout(employee, merchant, employee_csrf).status_code == 201


def test_onboarding_is_owner_scoped_and_cannot_activate_account(env):
    merchant = signup(env)['merchant_id']
    csrf = verified_login(env)
    path = f'/v1/merchants/{merchant}/beneficiary-onboarding'
    assert env[1].post(path).status_code == 403
    headers = {'x-csrf-token': csrf}
    first = env[1].post(path, headers=headers, json={'status':'active'})
    assert first.status_code == 200 and first.json()['status'] == 'pending'
    assert env[1].post(path, headers=headers).json() == first.json()
    outsider = (env[0], TestClient(env[0]))
    signup(outsider, 'outsider@example.com')
    outsider_csrf = verified_login(outsider, 'outsider@example.com')
    assert outsider[1].post(path, headers={'x-csrf-token':outsider_csrf}).status_code == 404


def test_concurrent_order_reservation_has_one_winner(env):
    from concurrent.futures import ThreadPoolExecutor

    merchant = signup(env)['merchant_id']
    repo = env[0].state.payments
    def reserve(_):
        row, created = repo.reserve(merchant, 'same', 1, 'Pan', '12', 600)
        return row.id, created

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(reserve, range(16)))
    assert len({ident for ident, _ in outcomes}) == 1
    assert sum(created for _, created in outcomes) == 1


def test_provider_amount_rejects_hidden_subcent_precision():
    from decimal import Decimal
    from rio_pey_codi.app import parse_provider_amount

    with pytest.raises(ValueError):
        parse_provider_amount(Decimal('0.0100000000000000000000000000000000001'))
    assert parse_provider_amount(Decimal('0.01000')) == 1


def test_concurrent_webhook_and_qr_link_after_database_reopen(env):
    from concurrent.futures import ThreadPoolExecutor
    from rio_pey_codi.models import Event, database
    from rio_pey_codi.payments_db import PaymentRepository

    merchant = signup(env)['merchant_id']
    repo = env[0].state.payments
    intent, _ = repo.reserve(merchant, 'parallel', 123, 'Pan', '123', 600)
    raw = b'{"synthetic": true}'
    with ThreadPoolExecutor(max_workers=2) as pool:
        event = pool.submit(repo.confirm_event, 'event-parallel', raw, 'qr-parallel', 123, '123', 'tx-parallel')
        issued = pool.submit(repo.qr_issued, intent.id, 'qr-parallel', 'synthetic')
        event.result()
        issued.result()

    reopened = database(env[0].state.settings.database_url)
    with reopened() as db:
        stored = db.get(Event, 'event-parallel')
        assert stored.raw_body == raw and stored.intent_id == intent.id
    assert PaymentRepository(reopened).get(intent.id).status == 'PROVIDER_REPORTED'


def test_webhook_large_body_is_rejected_before_signature(env):
    assert env[1].post('/v1/webhooks/pey', content=b'x' * 65537).status_code == 413


def test_user_webhook_example_reports_provider_payment_and_rejects_changed_replay(env):
    from rio_pey_codi.models import Event

    merchant_id = signup(env)['merchant_id']
    verified_login(env)
    repo = env[0].state.payments
    intent, _ = repo.reserve(merchant_id, 'order-12345', 15000, 'Pedido #12345', '12345', 600)
    qr_id = '01HXYZQR1234567890ABCDEFGH'
    repo.qr_issued(intent.id, qr_id, 'synthetic')
    payload = {
        'amount': 150,
        'apiKeyId': '01M3QMMR6X9CBVDY1SF3G8QBJW',
        'codiQrId': qr_id,
        'concept': 'Pedido #12345',
        'datePaid': 1790724818,
        'numRef': '12345',
        'transactionId': '01HXYZTXN1234567890RSTUVWX',
        'type': 'codi.qr.payment_received',
    }
    response = signed_webhook(env[1], payload, 'example-event')
    assert response.status_code == 200
    assert response.json()['outcome'] == 'PROVIDER_REPORTED'
    assert response.json()['bank_settlement'] == 'NOT_VERIFIED'
    assert repo.get(intent.id).amount_minor == 15000
    with repo.Session() as db:
        assert json.loads(db.get(Event, 'example-event').raw_body) == payload

    assert signed_webhook(env[1], payload, 'example-event').json()['outcome'] == 'DUPLICATE_EVENT'
    changed = {**payload, 'amount': 151}
    assert signed_webhook(env[1], changed, 'example-event').status_code == 409


def test_history_and_practice_ticket_are_tenant_scoped(env):
    merchant = signup(env)['merchant_id']
    csrf = verified_login(env)
    intent = checkout(env, merchant, csrf).json()['intent']
    history = f'/v1/merchants/{merchant}/checkout-history'
    ticket = f"/v1/checkout/qr/{intent['id']}/practice-ticket"
    assert env[1].get(history).json()['intents'][0]['id'] == intent['id']
    assert env[1].get(ticket).json()['kind'] == 'PRACTICE_NON_FISCAL'
    assert env[1].get(ticket).json()['bank_payment_confirmed'] is False
    outsider = (env[0], TestClient(env[0]))
    signup(outsider, 'history@example.com')
    verified_login(outsider, 'history@example.com')
    assert outsider[1].get(history).status_code == 404
    assert outsider[1].get(ticket).status_code == 404


def test_unresolved_queue_recovers_older_orders_with_tenant_scoped_pagination(env):
    from rio_pey_codi.models import Intent

    merchant = signup(env)['merchant_id']
    owner_csrf = verified_login(env)
    other = (env[0], TestClient(env[0]))
    other_merchant = signup(other, 'second-queue@example.com')['merchant_id']
    verified_login(other, 'second-queue@example.com')
    rows = []
    # Four unresolved orders have the same timestamp to exercise cursor ties.
    for i in range(4):
        rows.append(Intent(id=f'{i + 1:032x}', merchant_id=merchant, order_id=f'old-{i}',
            amount_minor=100 + i, concept='Synthetic', numref=f'ref-{i}', expiration_s=600,
            status='PROVIDER_UNCERTAIN' if i % 2 else 'QR_REQUESTING', created_at=1700000000))
    for i in range(55):
        rows.append(Intent(id=f'{100 + i:032x}', merchant_id=merchant, order_id=f'new-{i}',
            amount_minor=100, concept='Synthetic', numref=f'new-ref-{i}', expiration_s=600,
            status='QR_ISSUED', created_at=1700000001 + i))
    rows.append(Intent(id=f'{999:032x}', merchant_id=other_merchant, order_id='other-old',
        amount_minor=100, concept='Other', numref='other-ref', expiration_s=600,
        status='PROVIDER_UNCERTAIN', created_at=1700000000))
    with env[0].state.accounts.Session.begin() as db:
        db.add_all(rows)
    assert all(not row['order_id'].startswith('old-') for row in
               env[1].get(f'/v1/merchants/{merchant}/checkout-history').json()['intents'])

    url = f'/v1/merchants/{merchant}/checkout-unresolved'
    first = env[1].get(url, params={'limit':2})
    assert first.status_code == 200
    assert TestClient(env[0]).get(url).status_code == 401
    assert other[1].get(url).status_code == 404
    page1 = first.json()
    assert [row['order_id'] for row in page1['intents']] == ['old-0', 'old-1']
    assert page1['next_cursor'] == {'created_at':1700000000, 'id':f'{2:032x}'}
    page2 = env[1].get(url, params={'limit':2, 'after_created_at':page1['next_cursor']['created_at'],
                                   'after_id':page1['next_cursor']['id']}).json()
    assert [row['order_id'] for row in page2['intents']] == ['old-2', 'old-3']
    assert page2['next_cursor'] is None
    assert all(row['bank_payment_confirmed'] is False for row in page1['intents'] + page2['intents'])
    assert env[1].get(url, params={'after_created_at':1700000000}).status_code == 422
    assert env[1].get(url, params={'after_id':f'{2:032x}'}).status_code == 422
    assert env[1].get(url, params={'limit':101}).status_code == 422

    # A newly authorized cashier can recover the same durable order, not create a new one.
    grant = env[1].put(f'/v1/merchants/{merchant}/members', headers={'x-csrf-token':owner_csrf},
                       json={'email':'second-queue@example.com', 'role':'cashier'})
    assert grant.status_code == 200
    assert other[1].get(url, params={'limit':2}).json()['intents'][0]['order_id'] == 'old-0'
