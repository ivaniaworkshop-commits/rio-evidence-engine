"""Cross-account commerce, cash persistence and database receipt verification.

No external provider or SMTP calls: all actors and payment evidence are test-only.
"""
import base64
from datetime import datetime, timezone
import uuid

from fastapi.testclient import TestClient
import pytest

from production_acceptance_fixture import make_app


KEY = 'acceptance-fixture-boundary-' + 'f' * 40
FIXTURE = {'X-Production-Fixture-Key': KEY}


def actor(app, name, email):
    client = TestClient(app)
    credentials = {'email': email, 'password': 'Acceptance-Only-Password-2026'}
    signup = client.post('/v1/auth/signup', json={**credentials, 'business_name': name})
    assert signup.status_code == 201, signup.text
    token = client.get('/__production_test/verification-token', params={'email': email}, headers=FIXTURE)
    assert token.status_code == 200
    assert client.post('/v1/auth/verify-email', json={'token': token.json()['token']}).status_code == 200
    login = client.post('/v1/auth/login', json=credentials)
    assert login.status_code == 200
    return client, signup.json()['merchant_id'], {'x-csrf-token': login.json()['csrf_token']}


def ok(response, *statuses):
    assert response.status_code in (statuses or (200, 201)), response.text
    return response.json()


@pytest.fixture
def market(tmp_path, monkeypatch):
    monkeypatch.setenv('RPG_MERCHANT_VAULT_KEY', base64.urlsafe_b64encode(b't' * 32).decode())
    app = make_app(tmp_path / 'full-story.sqlite', KEY, 8099)
    seller = actor(app, 'Verduras del Centro', 'seller-story@example.org')
    buyer = actor(app, 'Abarrotes del Sur', 'buyer-story@example.org')
    carrier = actor(app, 'Fletes CDMX', 'carrier-story@example.org')
    for (client, merchant, headers), kind, area in (
        (seller, 'merchant', 'coyoacan'), (buyer, 'merchant', 'iztapalapa'),
        (carrier, 'freighter', 'coyoacan'),
    ):
        ok(client.put('/v1/market/profiles/' + merchant, headers=headers, json={
            'kind': kind, 'alcaldia': area, 'colonia': 'Centro',
            'description': 'Atención en Ciudad de México', 'published': True,
        }))
    return app, seller, buyer, carrier


def test_shared_offer_to_quote_order_carrier_and_read_only_payment(market):
    app, (seller, mid, sh), (buyer, bid, bh), (carrier, cid, ch) = market
    listing = ok(seller.post('/v1/market/listings', headers=sh, json={
        'merchant_id': mid, 'name': 'Salsa de temporada', 'description': 'Frasco',
        'unit': 'kg', 'category': 'Abarrotes', 'price_minor': 1250,
        'stock_milli': 20000, 'published': True,
    }))
    shared = ok(buyer.get('/v1/market/bootstrap'))
    assert len(shared['localities']) == 16
    assert [row['id'] for row in shared['listings']] == [listing['id']]
    assert shared['my_listings'] == []
    assert ok(buyer.get('/v1/market/listings', params={'alcaldia': 'iztapalapa'}))['listings'] == []
    assert buyer.patch('/v1/market/listings/' + listing['id'], headers=bh,
                       json={'price_minor': 1}).status_code in (403, 404)
    quote = ok(buyer.post('/v1/market/quotes', headers=bh, json={
        'listing_id': listing['id'], 'buyer_merchant_id': bid, 'quantity_milli': 1500,
        'message': 'Solicito entrega',
    }))
    assert carrier.post('/v1/market/quotes/' + quote['id'] + '/respond', headers=ch,
                        json={'unit_price_minor': 1, 'delivery_fee_minor': 0}).status_code in (403, 404)
    quoted = ok(seller.post('/v1/market/quotes/' + quote['id'] + '/respond', headers=sh,
                           json={'unit_price_minor': 1200, 'delivery_fee_minor': 100, 'message': 'Entrega acordada'}))
    assert quoted['status'] == 'QUOTED'
    accepted = ok(buyer.post('/v1/market/quotes/' + quote['id'] + '/accept', headers=bh,
                            json={'request_key': uuid.uuid4().hex}))
    ident = accepted['id']
    # 1,800 product subtotal + 100 agreed delivery + 5% freight surcharge.
    assert accepted['total_minor'] == 1995
    assert accepted['payment']['status'] == 'UNVERIFIED'
    # A synthetic provider readback is required before preparation. This stays
    # inside SQLite and exercises the same service hook as the pey webhook.
    from rio_pey_codi.models import Intent, MerchantPeyCredential, PaymentReceipt
    credential_ref, intent_id = 'c' * 32, 'd' * 32
    with app.state.accounts.Session.begin() as db:
        db.add(MerchantPeyCredential(ref=credential_ref, merchant_id=mid,
            api_key=b'synthetic-test-only', webhook_secret=b'synthetic-test-only', checked_at=1))
        db.flush()
        db.add(Intent(id=intent_id, merchant_id=mid, order_id='market-' + ident,
            amount_minor=accepted['total_minor'], concept='Synthetic market payment',
            numref='1234567', expiration_s=600, status='PROVIDER_REPORTED',
            provider_qr_id='synthetic-provider-qr', transaction_id='synthetic-provider-transaction',
            created_at=1, pey_credential_ref=credential_ref, provider_payment_source='PEY_API',
            provider_payment_observed_at=1, provider_payment_sha256='e' * 64))
        db.add(PaymentReceipt(intent_id=intent_id, public_id='f' * 32, payer_email=None,
            enabled=False, created_at=1, issued_at=1))
    assert app.state.production_market.pey_payment_confirmed(intent_id)
    for action in ('accept', 'prepare'):
        ok(seller.post('/v1/market/orders/' + ident + '/transition', headers=sh, json={'action': action}))
    freight = ok(seller.post('/v1/market/freights', headers=sh, json={
        'order_id': ident, 'carrier_merchant_id': cid, 'fee_minor': 100, 'notes': 'Entrega CDMX',
    }))
    assert buyer.post('/v1/market/freights/' + freight['id'] + '/transition', headers=bh,
                      json={'action': 'accept'}).status_code in (403, 404)
    ok(carrier.post('/v1/market/freights/' + freight['id'] + '/transition', headers=ch,
                    json={'action': 'accept'}))
    ok(seller.post('/v1/market/orders/' + ident + '/transition', headers=sh, json={'action': 'ship'}))
    from sqlalchemy import select
    from rio_pey_codi.production_market_models import MarketOrderQR
    with app.state.accounts.Session() as db:
        transit_qr = db.scalar(select(MarketOrderQR).where(
            MarketOrderQR.order_id == ident, MarketOrderQR.kind == 'TRANSIT'))
        assert transit_qr is not None
        transit_digest = transit_qr.sha256
    blocked = carrier.post('/v1/market/order-qr/scan', headers=ch,
                           json={'order_id': ident, 'kind': 'TRANSIT', 'sha256': transit_digest})
    assert blocked.status_code == 409 and 'acreditación bancaria' in blocked.text
    premature_delivery = carrier.post('/v1/market/freights/' + freight['id'] + '/transition',
                                      headers=ch, json={'action': 'deliver'})
    assert premature_delivery.status_code == 409 and 'QR de tránsito' in premature_delivery.text
    pending = ok(buyer.get('/v1/market/orders/' + ident))['order']
    assert pending['status'] == 'PREPARED'
    assert pending['payment']['status'] == 'PEY_CONFIRMED'
    assert pending['payment']['label'] == 'Pago confirmado por pey'
    assert pending['payment']['bank_payment_confirmed'] is False
    assert carrier.get('/v1/market/orders/' + ident).status_code in (403, 404)


def test_saved_cash_appears_for_a_fresh_session_without_becoming_payment_evidence(market):
    app, (seller, mid, sh), (buyer, _, bh), _ = market
    value = {'id': 'CASH-' + str(uuid.uuid4()), 'createdAt': datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
             'folio': 'MOSTRADOR-1', 'concept': 'Venta de mostrador', 'amountMinor': 313,
             'receivedMinor': 500, 'changeMinor': 187, 'lines': [], 'source': 'USER_DECLARED_CASH',
             'paymentMethod': 'cash', 'bankPaymentConfirmed': False}
    path = '/v1/merchants/' + mid + '/cash-sales'
    saved = ok(seller.post(path, headers=sh, json=value))
    assert saved['persisted'] is True and saved['sale']['changeMinor'] == 187
    replay = ok(seller.post(path, headers=sh, json=value))
    assert replay['replayed'] is True
    assert seller.post(path, headers=sh, json={**value, 'amountMinor': 314, 'changeMinor': 186}).status_code == 409
    fresh = TestClient(app)
    login = ok(fresh.post('/v1/auth/login', json={'email': 'seller-story@example.org', 'password': 'Acceptance-Only-Password-2026'}))
    assert login['csrf_token']
    history = ok(fresh.get(path))['sales']
    assert len(history) == 1 and history[0]['id'] == value['id']
    assert history[0]['bankPaymentConfirmed'] is False
    assert buyer.get(path).status_code in (403, 404)
    assert buyer.post(path, headers=bh, json=value).status_code in (403, 404)
    assert ok(seller.get('/__production_test/metrics', headers=FIXTURE))['provider_calls'] == 0


def test_scanner_uses_current_database_evidence_and_merchant_acl(market):
    app, (seller, mid, sh), (buyer, bid, bh), _ = market
    assert seller.post('/__production_test/receipt/' + mid, headers=sh).status_code == 403
    receipt = ok(seller.post('/__production_test/receipt/' + mid, headers={**sh, **FIXTURE}))
    verified = ok(seller.post('/v1/receipts/verify', headers=sh, json={'qr_text': receipt['link'], 'merchant_id': mid}))
    assert verified['verified'] is True and verified['amount_minor'] == 1250
    assert verified['title'] == 'Pago confirmado por pey'
    assert verified['bank_settlement_verified'] is False
    assert buyer.post('/v1/receipts/verify', headers=bh,
                      json={'qr_text': receipt['link'], 'merchant_id': bid}).status_code in (403, 404)
    assert seller.post('/v1/receipts/verify', headers=sh,
                       json={'qr_text': receipt['link'].replace('127.0.0.1', 'example.org'), 'merchant_id': mid}).status_code == 422
    from sqlalchemy import select
    from rio_pey_codi.models import PaymentReceipt
    with app.state.accounts.Session.begin() as db:
        row = db.scalar(select(PaymentReceipt).where(PaymentReceipt.public_id == verified['receipt_id']))
        row.issued_at = None
    assert seller.post('/v1/receipts/verify', headers=sh,
                       json={'qr_text': receipt['link'], 'merchant_id': mid}).status_code == 404
    metrics = ok(seller.get('/__production_test/metrics', headers=FIXTURE))
    assert metrics['provider_calls'] == 0 and all(kind == 'verify' for kind in metrics['mail_kinds'])
