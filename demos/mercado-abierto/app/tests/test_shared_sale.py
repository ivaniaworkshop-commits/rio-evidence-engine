"""Shared order identities are scoped and never trigger two synthetic provider calls."""
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rio_pey_codi.platform import Settings, create_platform


class TimeoutProvider:
    def __init__(self):
        self.calls = 0
        self.lock = threading.Lock()

    def create_qr(self, **_kwargs):
        with self.lock:
            self.calls += 1
        raise TimeoutError('synthetic timeout')


def setup_shared_users(app):
    owner, cashier, outsider = TestClient(app), TestClient(app), TestClient(app)
    password = 'synthetic-password-123'

    def account(client, email):
        signup = client.post('/v1/auth/signup', json={
            'email':email, 'password':password, 'business_name':'Synthetic',
        })
        assert signup.status_code == 201
        token = next(item['token'] for item in app.state.mailer.outbox if item['email'] == email)
        assert client.post('/v1/auth/verify-email', json={'token':token}).status_code == 200
        login = client.post('/v1/auth/login', json={'email':email, 'password':password})
        assert login.status_code == 200
        return signup.json()['merchant_id'], login.json()['csrf_token']

    merchant, owner_csrf = account(owner, 'shared-owner@example.com')
    _, cashier_csrf = account(cashier, 'shared-cashier@example.com')
    outsider_merchant, outsider_csrf = account(outsider, 'shared-outsider@example.com')
    grant = owner.put(f'/v1/merchants/{merchant}/members', headers={'x-csrf-token':owner_csrf},
                      json={'email':'shared-cashier@example.com', 'role':'cashier'})
    assert grant.status_code == 200
    return merchant, owner, owner_csrf, cashier, cashier_csrf, outsider, outsider_merchant, outsider_csrf


def exercise_shared_sale_race(app, provider):
    merchant, owner, owner_csrf, cashier, cashier_csrf, outsider, outsider_merchant, outsider_csrf = setup_shared_users(app)
    lookup = f'/v1/merchants/{merchant}/checkout-orders/sale-123'
    missing = owner.get(lookup)
    assert missing.status_code == 404 and missing.json()['code'] == 'ORDER_NOT_FOUND'
    forbidden = outsider.get(lookup)
    assert forbidden.status_code == 404 and 'code' not in forbidden.json()
    assert TestClient(app).get(lookup).status_code == 401
    barrier = threading.Barrier(2)

    def charge(client, csrf, numref):
        body = {'merchant_id':merchant, 'order_id':'sale-123', 'numref':numref,
                'concept':'Synthetic', 'amount_minor':15000, 'expiration_s':600}
        barrier.wait(timeout=10)
        return client.post('/v1/checkout/qr', headers={'x-csrf-token':csrf}, json=body)

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(charge, owner, owner_csrf, '1111111')
        b = pool.submit(charge, cashier, cashier_csrf, '2222222')
        results = [a.result(timeout=20), b.result(timeout=20)]
    assert sorted(response.status_code for response in results) == [409, 502]
    assert provider.calls == 1
    intent = cashier.get(lookup).json()['intent']
    assert intent['order_id'] == 'sale-123' and intent['numref'] in ('1111111', '2222222')
    assert intent['status'] == 'PROVIDER_UNCERTAIN' and intent['bank_payment_confirmed'] is False
    changed = {'merchant_id':merchant, 'order_id':'sale-123', 'numref':intent['numref'],
               'concept':'Synthetic', 'amount_minor':15001, 'expiration_s':600}
    assert owner.post('/v1/checkout/qr', headers={'x-csrf-token':owner_csrf}, json=changed).status_code == 409
    assert provider.calls == 1
    other = {**changed, 'merchant_id':outsider_merchant, 'amount_minor':15000}
    assert outsider.post('/v1/checkout/qr', headers={'x-csrf-token':outsider_csrf}, json=other).status_code == 502
    assert provider.calls == 2  # The same business folio in a different merchant is a separate order.


def test_shared_sale_race_across_authorized_sessions_sqlite(tmp_path):
    provider = TimeoutProvider()
    app = create_platform(Settings(database_url='sqlite+pysqlite:///' + str(tmp_path/'shared.sqlite3')),
                          provider=provider)
    exercise_shared_sale_race(app, provider)


@pytest.mark.parametrize(('script_name', 'marker'), [
    ('shared_sale_ui.cjs', 'SHARED_SALE_UI_OK'),
    ('selection_loading_ui.cjs', 'SELECTION_LOADING_UI_OK'),
    ('shared_sale_pattern.cjs', 'SHARED_SALE_NATIVE_PATTERN_OK'),
])
def test_shared_sale_browser_logic(script_name, marker):
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node is required for the shared sale UI regression')
    script = Path(__file__).with_name(script_name)
    result = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=20, check=True)
    assert marker in result.stdout
