"""Database receipt lookup: synthetic confirmations only; no camera upload or provider call."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from rio_pey_codi.models import Intent, PaymentReceipt
from rio_pey_codi.receipt_verification import register_receipt_verification, receipt_token
from test_receipts import env, checkout, confirm
from test_merchant_pey_vault import create_user


@pytest.fixture
def verified(env):
    app, client, body, headers = env
    if not any(getattr(route, 'path', None) == '/v1/receipts/verify' for route in app.routes):
        register_receipt_verification(app, app.state.accounts, app.state.receipts)
    ident = checkout(env, receipt_enabled=False, payer_email=None)
    confirm(app, ident)
    app.state.receipts.issue(ident)
    data = client.get('/v1/checkout/qr/' + ident + '/receipt').json()
    assert data['issued'] is True
    return app, client, body, headers, ident, data['link']


def scan(verified, **changes):
    _, client, body, headers, _, link = verified
    return client.post('/v1/receipts/verify', headers=headers,
                       json={'qr_text': link, 'merchant_id': body['merchant_id'], **changes})


def test_scan_matches_persisted_payment_without_email_or_payment_side_effects(verified):
    app, client, body, headers, ident, link = verified
    before = list(app.state.mailer.outbox)
    result = scan(verified)
    assert result.status_code == 200, result.text
    info = result.json()
    assert info['verified'] is True
    assert info['title'] == 'Pago confirmado por pey'
    assert info['merchant_id'] == body['merchant_id']
    assert info['amount_minor'] == body['amount_minor'] and info['currency'] == 'MXN'
    assert info['order_id'] == body['order_id']
    assert info['verification_source'] == 'PEY_AUTHENTICATED_READBACK'
    assert info['bank_settlement_verified'] is False
    assert not {'payer_email', 'recipient_email', 'api_key', 'token', 'transaction_id'}.intersection(info)
    assert app.state.mailer.outbox == before
    assert app.state.payments.get(ident).status == 'PROVIDER_REPORTED'
    assert result.headers['cache-control'] == 'no-store'
    raw = link.rsplit('/', 1)[1]
    assert scan(verified, qr_text=raw).json() == info


def test_scan_requires_verified_session_csrf_and_selected_merchant(verified):
    app, client, body, _, _, link = verified
    payload = {'qr_text': link, 'merchant_id': body['merchant_id']}
    assert TestClient(app).post('/v1/receipts/verify', json=payload).status_code == 401
    assert client.post('/v1/receipts/verify', json=payload).status_code == 403
    assert client.post('/v1/receipts/verify', json=payload, headers={'x-csrf-token': 'forged'}).status_code == 403
    outsider = TestClient(app)
    other_merchant, other_csrf = create_user(app, outsider, 'outsider-scanner@example.com')
    response = outsider.post('/v1/receipts/verify', json=payload, headers={'x-csrf-token': other_csrf})
    assert response.status_code == 404
    response = outsider.post('/v1/receipts/verify', json={**payload, 'merchant_id': other_merchant},
                             headers={'x-csrf-token': other_csrf})
    assert response.status_code == 404
    assert 'receiver@example.com' not in response.text


def test_scan_cannot_present_another_owned_business_payment_as_selected_business(verified):
    _, client, _, headers, _, _ = verified
    merchant = client.post('/v1/merchants', json={'name': 'Second recipient'}, headers=headers).json()['id']
    assert scan(verified, merchant_id=merchant).status_code == 404


def test_scan_rechecks_confirmation_after_previous_success(verified):
    app, _, _, _, ident, _ = verified
    assert scan(verified).status_code == 200
    with app.state.accounts.Session.begin() as db:
        db.get(Intent, ident).status = 'PROVIDER_REJECTED'
    assert scan(verified).status_code == 404


def test_scan_rejects_unissued_and_tampered_receipts(verified):
    app, _, _, _, ident, link = verified
    changed = link[:-1] + ('a' if link[-1] != 'a' else 'b')
    assert scan(verified, qr_text=changed).status_code == 404
    assert scan(verified, qr_text='f' * 32 + '.' + 'b' * 43).status_code == 404
    with app.state.accounts.Session.begin() as db:
        db.get(PaymentReceipt, ident).issued_at = None
    assert scan(verified).status_code == 404


@pytest.mark.parametrize('value', [
    'https://unrelated.example/comprobante/{token}',
    'http://testserver.unrelated.example/comprobante/{token}',
    'http://testserver@unrelated.example/comprobante/{token}',
    'http://user@testserver/comprobante/{token}',
    'http://testserver/comprobante/{token}?paid=true',
    'http://testserver/comprobante/{token}#paid',
    'http://testserver/checkout/{token}',
    'http://testserver/comprobante/{token}/qr.png',
    '//testserver/comprobante/{token}',
    'javascript:alert(1)',
    'data:text/plain,PAID',
    'CoDi:payment-not-a-receipt',
])
def test_scanned_links_never_fetch_arbitrary_or_payment_qr_urls(value):
    from fastapi import HTTPException
    token = 'a' * 32 + '.' + 'b' * 43
    with pytest.raises(HTTPException) as raised:
        receipt_token(value.format(token=token), 'http://testserver')
    assert raised.value.status_code == 422


def test_client_cannot_add_payment_claim_or_unbounded_payload(verified):
    app, client, body, headers, _, link = verified
    data = {'qr_text': link, 'merchant_id': body['merchant_id']}
    assert client.post('/v1/receipts/verify', json={**data, 'paid': True}, headers=headers).status_code == 422
    assert scan(verified, qr_text='a' * 2049).status_code == 422
    assert scan(verified, qr_text={'paid': True}).status_code == 422
