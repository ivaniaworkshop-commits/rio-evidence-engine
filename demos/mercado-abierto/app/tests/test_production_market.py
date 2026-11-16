"""Shared production commerce, synthetic accounts and no external money or mail."""
import json
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

# Metadata must be registered before the local auto-create boundary.
from rio_pey_codi.production_market import register_production_market_routes
from rio_pey_codi.production_market_models import MarketListing, MarketOrder
from rio_pey_codi.models import Intent, MerchantPeyCredential, PaymentReceipt
from rio_pey_codi.platform import Settings, create_platform


def key():
    return uuid.uuid4().hex


@pytest.fixture
def env(tmp_path):
    app = create_platform(Settings(database_url='sqlite+pysqlite:///' + str(tmp_path/'market.sqlite')))
    if not hasattr(app.state, 'production_market'):
        register_production_market_routes(app, app.state.accounts)
    users = []
    for index in range(4):
        client = TestClient(app)
        email = f'market-{index}@example.org'
        created = client.post('/v1/auth/signup', json={'email': email,
            'password': 'Production-Market-Test-2026', 'business_name': f'Negocio {index}'})
        assert created.status_code == 201, created.text
        token = app.state.mailer.outbox[-1]['token']
        assert client.post('/v1/auth/verify-email', json={'token': token}).status_code == 200
        login = client.post('/v1/auth/login', json={'email': email, 'password': 'Production-Market-Test-2026'})
        assert login.status_code == 200
        users.append((client, created.json()['merchant_id'], {'X-CSRF-Token': login.json()['csrf_token']}))
    return app, users


def profile(user, *, published=True, kind='merchant', alcaldia='iztapalapa'):
    client, merchant, headers = user
    result = client.put('/v1/market/profiles/' + merchant, json={'kind': kind,
        'alcaldia': alcaldia, 'colonia': 'Colonia registrada', 'description': 'Negocio registrado',
        'published': published}, headers=headers)
    assert result.status_code == 200, result.text
    return result.json()


def listing(user, **values):
    client, merchant, headers = user
    result = client.post('/v1/market/listings', json={'merchant_id': merchant,
        'name': 'Producto del comerciante', 'category': 'Abarrotes', 'description': 'Oferta vigente',
        'unit': 'piece', 'price_minor': 1234, 'stock_milli': 10_000,
        'published': True, **values}, headers=headers)
    assert result.status_code == 201, result.text
    return result.json()


def order(user, product, **values):
    client, merchant, headers = user
    result = client.post('/v1/market/orders', json={'listing_id': product['id'],
        'buyer_merchant_id': merchant, 'quantity_milli': 1000,
        'request_key': key(), 'notes': 'Recoger en el negocio', **values}, headers=headers)
    assert result.status_code == 201, result.text
    return result.json()


def transition(user, row, action):
    client, _, headers = user
    return client.post('/v1/market/orders/' + row['id'] + '/transition',
        json={'action': action}, headers=headers)


def test_auth_csrf_cdmx_validation_and_no_seed_data(env):
    app, users = env
    client, merchant, _ = users[0]
    assert TestClient(app).get('/v1/market/bootstrap').status_code == 401
    initial = client.get('/v1/market/bootstrap').json()
    assert initial['listings'] == initial['profiles'] == initial['quotes'] == initial['orders'] == []
    assert len(initial['localities']) == 16
    assert {row['code'] for row in initial['localities']} >= {'coyoacan', 'iztapalapa', 'tlalpan'}
    assert client.put('/v1/market/profiles/' + merchant, json={'kind': 'merchant',
        'alcaldia': 'iztapalapa', 'colonia': 'Colonia'}).status_code == 403
    bad = client.put('/v1/market/profiles/' + merchant, json={'kind': 'merchant',
        'alcaldia': 'guadalajara', 'colonia': 'Colonia'}, headers=users[0][2])
    assert bad.status_code == 422
    assert client.get('/v1/market/bootstrap?alcaldia=monterrey').status_code == 422
    assert client.put('/v1/market/profiles/' + merchant, json={'kind': 'merchant',
        'alcaldia': 'iztapalapa', 'colonia': '  '}, headers=users[0][2]).status_code == 422


def test_shared_feed_requires_explicit_publication_and_has_no_private_fields(env):
    _, users = env
    seller, buyer = users[:2]
    profile(seller)
    product = listing(seller)
    result = buyer[0].get('/v1/market/bootstrap').json()
    assert result['listings'][0]['id'] == product['id']
    assert result['my_listings'] == []
    assert result['listings'][0]['merchant_name'] == 'Negocio 0'
    assert result['listings'][0]['price_minor'] == 1296
    assert 'market-0@example.org' not in json.dumps(result)
    assert not {'api_key', 'webhook_secret', 'owner_id'}.intersection(result['listings'][0])
    assert buyer[0].get('/v1/market/listings?alcaldia=coyoacan').json()['listings'] == []
    assert buyer[0].get('/v1/market/listings?q=Producto').json()['listings'][0]['id'] == product['id']
    assert buyer[0].get('/v1/market/listings?q=%25').json()['listings'] == []
    profile(seller, published=False)
    assert buyer[0].get('/v1/market/bootstrap').json()['listings'] == []
    assert seller[0].get('/v1/market/bootstrap').json()['my_listings'][0]['id'] == product['id']


def test_whatsapp_contact_is_opt_in_validated_and_only_public_when_profile_is_published(env):
    _, users = env
    seller, buyer = users[:2]
    client, merchant, headers = seller
    saved = client.put('/v1/market/profiles/' + merchant, headers=headers, json={
        'kind': 'merchant', 'alcaldia': 'iztapalapa', 'colonia': 'Centro',
        'description': 'Abarrotes', 'published': True,
        'whatsapp_phone': '+52 (55) 1234-5678',
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()['whatsapp_phone'] == '+525512345678'
    product = listing(seller)
    public = buyer[0].get('/v1/market/bootstrap').json()
    assert next(row for row in public['profiles'] if row['merchant_id'] == merchant)['whatsapp_phone'] == '+525512345678'
    assert public['listings'][0]['whatsapp_phone'] == '+525512345678'

    invalid = client.put('/v1/market/profiles/' + merchant, headers=headers, json={
        'kind': 'merchant', 'alcaldia': 'iztapalapa', 'colonia': 'Centro',
        'description': 'Abarrotes', 'published': True, 'whatsapp_phone': '5551234567',
    })
    assert invalid.status_code == 422

    saved = client.put('/v1/market/profiles/' + merchant, headers=headers, json={
        'kind': 'merchant', 'alcaldia': 'iztapalapa', 'colonia': 'Centro',
        'description': 'Abarrotes', 'published': False,
        'whatsapp_phone': '+525512345678',
    })
    assert saved.status_code == 200
    assert buyer[0].get('/v1/market/listings').json()['listings'] == []


def test_status_chatbot_reads_current_owned_orders_and_hides_foreign_order_existence(env):
    _, users = env
    seller, buyer, outsider = users[:3]
    profile(seller)
    product = listing(seller)
    profile(buyer)
    created = order(buyer, product)
    ident = created['id']

    response = buyer[0].post('/v1/chatbot/message', headers=buyer[2], json={
        'message': '¿En qué estado está mi pedido market-' + ident,
    })
    assert response.status_code == 200, response.text
    assert 'solicitado' in response.json()['reply']
    status = response.json()['orders']
    assert status[0]['id'] == ident
    assert status[0]['bank_payment_confirmed'] is False
    page = buyer[0].get('/').text
    assert 'data-open-chatbot' in page and '/static/chatbot.js' in page
    market_ui = buyer[0].get('/static/unificada/hackaton/production.js').text
    assert 'whatsappLink' in market_ui and 'data-view' in market_ui

    hidden = outsider[0].post('/v1/chatbot/message', headers=outsider[2], json={
        'message': 'Estado del pedido ' + ident,
    })
    assert hidden.status_code == 200
    assert 'no encuentro ese folio' in hidden.json()['reply'].lower()
    assert hidden.json()['orders'] == []

    anonymous = TestClient(users[0][0].app)
    assert anonymous.get('/v1/chatbot/status').status_code == 401


def test_listing_acl_revision_exact_quantities_and_hidden_drafts(env):
    _, users = env
    seller, buyer = users[:2]
    profile(seller)
    profile(buyer)
    product = listing(seller)
    path = '/v1/market/listings/' + product['id']
    assert buyer[0].patch(path, json={'price_minor': 1}, headers=buyer[2]).status_code == 404
    changed = seller[0].patch(path, json={'price_minor': 2000, 'revision': 1}, headers=seller[2])
    assert changed.status_code == 200
    assert seller[0].patch(path, json={'stock_milli': 50_000, 'revision': 1}, headers=seller[2]).status_code == 409
    assert seller[0].patch(path, json={'price_minor': 1.4}, headers=seller[2]).status_code == 422
    assert seller[0].patch(path, json={'published': None}, headers=seller[2]).status_code == 422
    assert buyer[0].post('/v1/market/orders', json={'listing_id': product['id'],
        'buyer_merchant_id': buyer[1], 'quantity_milli': 1500, 'request_key': key()}, headers=buyer[2]).status_code == 422
    assert seller[0].post('/v1/market/listings', json={'merchant_id': seller[1],
        'name': 'Inválido', 'price_minor': 100, 'stock_milli': 1500, 'published': False}, headers=seller[2]).status_code == 422
    draft = listing(seller, published=False)
    assert draft['id'] not in {row['id'] for row in buyer[0].get('/v1/market/bootstrap').json()['listings']}


def test_quotes_cross_users_and_order_actor_transitions(env):
    _, users = env
    seller, buyer, outsider = users[:3]
    profile(seller)
    profile(buyer, published=False, alcaldia='coyoacan')
    product = listing(seller, unit='kg', stock_milli=4000)
    quoted = buyer[0].post('/v1/market/quotes', json={'listing_id': product['id'],
        'buyer_merchant_id': buyer[1], 'quantity_milli': 1500, 'message': 'Cotizar 1.5 kg'}, headers=buyer[2])
    assert quoted.status_code == 201, quoted.text
    quote = quoted.json()
    path = '/v1/market/quotes/' + quote['id']
    assert quote['status'] == 'REQUESTED'
    assert seller[0].get('/v1/market/bootstrap').json()['quotes'][0]['id'] == quote['id']
    assert outsider[0].get('/v1/market/bootstrap').json()['quotes'] == []
    assert buyer[0].post(path + '/respond', json={'unit_price_minor': 1000}, headers=buyer[2]).status_code == 404
    response = seller[0].post(path + '/respond', json={'unit_price_minor': 1000,
        'delivery_fee_minor': 250, 'message': 'Disponible'}, headers=seller[2])
    assert response.status_code == 200 and response.json()['total_minor'] == 1838
    request_key = key()
    accepted = buyer[0].post(path + '/accept', json={'request_key': request_key}, headers=buyer[2])
    assert accepted.status_code == 201, accepted.text
    row = accepted.json()
    assert row['status'] == 'REQUESTED' and row['total_minor'] == 1838
    assert row['checkout_order_id'] == 'market-' + row['id']
    replay = buyer[0].post(path + '/accept', json={'request_key': request_key}, headers=buyer[2])
    assert replay.json()['id'] == row['id']
    assert outsider[0].get('/v1/market/orders/' + row['id']).status_code == 404
    assert transition(buyer, row, 'accept').status_code == 404
    assert transition(seller, row, 'accept').json()['status'] == 'ACCEPTED'
    assert transition(seller, row, 'prepare').status_code == 409
    assert transition(seller, row, 'ship').status_code == 409
    assert transition(seller, row, 'receive').status_code == 409
    assert transition(buyer, row, 'receive').status_code == 409
    assert buyer[0].get('/v1/market/orders/' + row['id']).json()['order']['payment']['status'] == 'UNVERIFIED'


def test_idempotent_order_replay_never_reinterprets_changed_price_or_payload(env):
    _, users = env
    seller, buyer = users[:2]
    profile(seller)
    profile(buyer)
    product = listing(seller)
    request_key = key()
    row = order(buyer, product, request_key=request_key)
    seller[0].patch('/v1/market/listings/' + product['id'], json={'price_minor': 5000, 'published': False}, headers=seller[2])
    replay = order(buyer, product, request_key=request_key)
    assert replay['id'] == row['id'] and replay['unit_price_minor'] == 1296
    bad = buyer[0].post('/v1/market/orders', json={'listing_id': product['id'],
        'buyer_merchant_id': buyer[1], 'quantity_milli': 2000,
        'request_key': request_key, 'notes': 'Recoger en el negocio'}, headers=buyer[2])
    assert bad.status_code == 409


def test_concurrent_acceptance_reserves_stock_once_and_prevents_overselling(env):
    app, users = env
    seller, buyer, other = users[:3]
    for user in (seller, buyer, other):
        profile(user)
    product = listing(seller, stock_milli=1000)
    first = order(buyer, product)
    second = order(other, product)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda row: transition(seller, row, 'accept'), (first, second)))
    assert sorted(result.status_code for result in results) == [200, 409]
    accepted = next(result.json() for result in results if result.status_code == 200)
    assert transition(seller, accepted, 'accept').status_code == 200
    with app.state.accounts.Session() as db:
        assert db.get(MarketListing, product['id']).stock_milli == 0
        assert len(list(db.scalars(select(MarketOrder).where(MarketOrder.status == 'ACCEPTED')))) == 1


def test_freight_assignment_and_delivery_actor_acl(env):
    _, users = env
    seller, buyer, carrier, outsider = users
    profile(seller)
    profile(buyer)
    profile(carrier, kind='freighter', alcaldia='tlalpan')
    product = listing(seller)
    row = order(buyer, product)
    assert transition(seller, row, 'accept').status_code == 200
    payload = {'order_id': row['id'], 'carrier_merchant_id': carrier[1], 'fee_minor': 300,
        'notes': 'Entregar el paquete'}
    assert buyer[0].post('/v1/market/freights', json=payload, headers=buyer[2]).status_code == 404
    freight = seller[0].post('/v1/market/freights', json=payload, headers=seller[2])
    assert freight.status_code == 201, freight.text
    freight = freight.json()
    assert carrier[0].get('/v1/market/bootstrap').json()['freights'][0]['id'] == freight['id']
    assert outsider[0].get('/v1/market/bootstrap').json()['freights'] == []
    path = '/v1/market/freights/' + freight['id'] + '/transition'
    assert seller[0].post(path, json={'action': 'accept'}, headers=seller[2]).status_code == 404
    assert carrier[0].post(path, json={'action': 'deliver'}, headers=carrier[2]).status_code == 409
    assert carrier[0].post(path, json={'action': 'accept'}, headers=carrier[2]).json()['status'] == 'ACCEPTED'
    assert carrier[0].post(path, json={'action': 'deliver'}, headers=carrier[2]).status_code == 409
    assert buyer[0].get('/v1/market/orders/' + row['id']).json()['order']['status'] == 'ACCEPTED'
    assert transition(buyer, row, 'receive').status_code == 409


def test_only_matching_issued_provider_receipt_confirms_market_payment(env):
    app, users = env
    seller, buyer = users[:2]
    profile(seller)
    profile(buyer)
    product = listing(seller)
    row = order(buyer, product)
    path = '/v1/market/orders/' + row['id']
    assert buyer[0].get(path).json()['order']['payment']['status'] == 'UNVERIFIED'
    assert buyer[0].post(path + '/transition', json={'action': 'receive', 'paid': True}, headers=buyer[2]).status_code == 422
    credential, ident = key(), key()
    with app.state.accounts.Session.begin() as db:
        db.add(MerchantPeyCredential(ref=credential, merchant_id=seller[1], api_key=b'synthetic',
            webhook_secret=b'synthetic', checked_at=1))
        db.flush()
        db.add(Intent(id=ident, merchant_id=seller[1], order_id=row['checkout_order_id'],
            amount_minor=row['total_minor'], concept='Pago de pedido', numref='market-test', expiration_s=600,
            status='PROVIDER_REPORTED', pey_credential_ref=credential, transaction_id='synthetic-market-payment',
            provider_payment_source='AUTHENTICATED_LOOKUP', provider_payment_observed_at=1,
            provider_payment_sha256='a'*64, created_at=1))
        db.flush()
        db.add(PaymentReceipt(intent_id=ident, public_id=key(), enabled=False, created_at=1, issued_at=None))
    assert buyer[0].get(path).json()['order']['payment']['status'] == 'UNVERIFIED'
    with app.state.accounts.Session.begin() as db:
        db.get(PaymentReceipt, ident).issued_at = 2
    payment = buyer[0].get(path).json()['order']['payment']
    assert payment['status'] == 'PEY_CONFIRMED'
    assert payment['bank_payment_confirmed'] is False
    assert app.state.production_market.pey_payment_confirmed(ident) is True
    seller_view = seller[0].get('/v1/market/bootstrap').json()['my_listings']
    delisted = next(item for item in seller_view if item['id'] == product['id'])
    assert delisted['published'] is False and delisted['qr_sha256'] is None
    assert buyer[0].get(path).json()['order']['progress']['bank_credit_status'] == 'PENDING_BANK_INTEGRATION'
    with app.state.accounts.Session.begin() as db:
        db.get(Intent, ident).amount_minor += 1
    assert buyer[0].get(path).json()['order']['payment']['status'] == 'UNVERIFIED'


def test_listing_unit_is_immutable_and_quote_keeps_agreed_name_and_unit(env):
    _, users = env
    seller, buyer = users[:2]
    profile(seller)
    profile(buyer)
    product = listing(seller, name='Arroz por kilogramo', unit='kg', stock_milli=10_000)
    quoted = buyer[0].post('/v1/market/quotes', json={'listing_id': product['id'],
        'buyer_merchant_id': buyer[1], 'quantity_milli': 1500}, headers=buyer[2]).json()
    direct = order(buyer, product, quantity_milli=2500)
    changed = seller[0].patch('/v1/market/listings/' + product['id'],
        json={'unit': 'piece', 'stock_milli': 10_000}, headers=seller[2])
    assert changed.status_code == 409
    changed = seller[0].patch('/v1/market/listings/' + product['id'],
        json={'unit': 'meter'}, headers=seller[2])
    assert changed.status_code == 409
    assert seller[0].patch('/v1/market/listings/' + product['id'],
        json={'name': 'Nombre actualizado', 'price_minor': 9999}, headers=seller[2]).status_code == 200
    assert seller[0].post('/v1/market/quotes/' + quoted['id'] + '/respond',
        json={'unit_price_minor': 1000}, headers=seller[2]).status_code == 200
    accepted = buyer[0].post('/v1/market/quotes/' + quoted['id'] + '/accept',
        json={'request_key': key()}, headers=buyer[2]).json()
    assert accepted['unit'] == 'kg' and accepted['listing_name'] == 'Arroz por kilogramo'
    assert accepted['unit_price_minor'] == 1050 and accepted['total_minor'] == 1575
    assert transition(seller, direct, 'accept').status_code == 200
    assert transition(seller, accepted, 'accept').status_code == 200
    current = seller[0].get('/v1/market/bootstrap').json()['my_listings'][0]
    assert current['unit'] == 'kg' and current['stock_milli'] == 6000


def delivery_address(user, *, label='Casa'):
    client, merchant, headers = user
    response = client.post('/v1/market/delivery-addresses', headers=headers, json={
        'merchant_id': merchant, 'label': label, 'recipient': 'Persona receptora',
        'phone': '+525512345678', 'street': 'Calle de prueba', 'exterior_number': '15',
        'interior_number': '2', 'colonia': 'Centro', 'alcaldia': 'iztapalapa',
        'postal_code': '09000', 'reference_notes': 'Tocar el timbre',
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_delivery_addresses_are_private_managed_and_used_by_cart_checkout(env):
    _, users = env
    seller, buyer, outsider = users[:3]
    profile(seller)
    profile(buyer, published=False)
    first = delivery_address(buyer)
    second = delivery_address(buyer, label='Oficina')
    updated = buyer[0].put('/v1/market/delivery-addresses/' + second['id'], headers=buyer[2], json={
        'merchant_id': buyer[1], 'label': 'Oficina actualizada', 'recipient': 'Persona receptora',
        'phone': '+525512345678', 'street': 'Avenida nueva', 'exterior_number': '15',
        'interior_number': '2', 'colonia': 'Centro', 'alcaldia': 'iztapalapa',
        'postal_code': '09000', 'reference_notes': 'Tocar el timbre',
    })
    assert updated.status_code == 200 and updated.json()['street'] == 'Avenida nueva'
    address_path = '/v1/market/delivery-addresses?merchant_id=' + buyer[1]
    assert {row['id'] for row in buyer[0].get(address_path).json()['addresses']} == {first['id'], second['id']}
    assert outsider[0].get(address_path).status_code == 404

    products = [listing(seller, name='Producto ' + str(index)) for index in range(2)]
    for product in products:
        response = buyer[0].post('/v1/market/cart/items', headers=buyer[2], json={
            'buyer_merchant_id': buyer[1], 'listing_id': product['id'], 'quantity_milli': 1000,
        })
        assert response.status_code == 200, response.text
    cart = buyer[0].get('/v1/market/cart?buyer_merchant_id=' + buyer[1]).json()
    assert len(cart['items']) == 2

    request_key = key()
    payload = {'buyer_merchant_id': buyer[1], 'address_id': first['id'], 'request_key': request_key}
    checkout = buyer[0].post('/v1/market/cart/checkout', headers=buyer[2], json=payload)
    assert checkout.status_code == 201, checkout.text
    order_row = checkout.json()['order']
    assert len(order_row['items']) == 2
    assert order_row['total_minor'] == cart['total_minor']
    assert order_row['delivery_address']['id'] == first['id']
    assert order_row['unified_qr']['purpose'] == 'UNIFIED_ORDER_TRACKING'
    assert order_row['checkout_order_id'] == 'market-' + order_row['id']
    assert set(order_row['progress']['qr']) == {'payment'}
    assert order_row['unified_qr']['item_count'] == 2
    assert set(order_row['unified_qr']['product_qr_sha256']) == {p['qr_sha256'] for p in products}
    assert len(order_row['unified_qr']['sha256']) == 64
    qr_path = '/v1/market/orders/' + order_row['id'] + '/qr/payment.png?sha256=' + order_row['unified_qr']['sha256']
    qr_image = buyer[0].get(qr_path)
    assert qr_image.status_code == 200 and qr_image.headers['content-type'] == 'image/png'

    replay = buyer[0].post('/v1/market/cart/checkout', headers=buyer[2], json=payload)
    assert replay.status_code == 201 and replay.json()['replayed'] is True
    changed_address = {**payload, 'address_id': second['id']}
    assert buyer[0].post('/v1/market/cart/checkout', headers=buyer[2], json=changed_address).status_code == 409

    deleted = buyer[0].delete('/v1/market/delivery-addresses/' + first['id'] + '?merchant_id=' + buyer[1], headers=buyer[2])
    assert deleted.status_code == 200 and deleted.json()['past_orders_preserved'] is True
    history = buyer[0].get('/v1/market/orders/' + order_row['id']).json()['order']
    assert history['delivery_address']['street'] == 'Calle de prueba'
    assert buyer[0].get('/v1/market/delivery-addresses?merchant_id=' + buyer[1]).json()['addresses'][0]['id'] == second['id']


def test_cart_checkout_rejects_multiple_payout_sellers_without_erasing_cart(env):
    _, users = env
    seller_a, seller_b, buyer = users[:3]
    for seller in (seller_a, seller_b):
        profile(seller)
    profile(buyer, published=False)
    products = [listing(seller_a, name='Producto A'), listing(seller_b, name='Producto B')]
    address = delivery_address(buyer)
    for product in products:
        response = buyer[0].post('/v1/market/cart/items', headers=buyer[2], json={
            'buyer_merchant_id': buyer[1], 'listing_id': product['id'], 'quantity_milli': 1000,
        })
        assert response.status_code == 200, response.text
    response = buyer[0].post('/v1/market/cart/checkout', headers=buyer[2], json={
        'buyer_merchant_id': buyer[1], 'address_id': address['id'], 'request_key': key(),
    })
    assert response.status_code == 409
    assert 'mismo vendedor' in response.json()['detail']
    assert len(buyer[0].get('/v1/market/cart?buyer_merchant_id=' + buyer[1]).json()['items']) == 2
