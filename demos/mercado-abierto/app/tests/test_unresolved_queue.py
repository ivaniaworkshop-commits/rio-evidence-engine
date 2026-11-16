"""Unresolved checkouts are discoverable and replayed without another provider send."""
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rio_pey_codi.platform import Settings, create_platform


def test_authorized_second_cashier_recovers_the_same_uncertain_order(tmp_path):
    class TimeoutProvider:
        calls = 0

        def create_qr(self, **_kwargs):
            self.calls += 1
            raise TimeoutError('synthetic timeout')

    provider = TimeoutProvider()
    app = create_platform(Settings(database_url='sqlite+pysqlite:///' + str(tmp_path / 'queue.sqlite3')),
                          provider=provider)
    owner, cashier, outsider = TestClient(app), TestClient(app), TestClient(app)

    def account(client, email):
        password = 'synthetic-password-123'
        response = client.post('/v1/auth/signup', json={
            'email':email, 'password':password, 'business_name':'Synthetic shop',
        })
        assert response.status_code == 201
        token = next(item['token'] for item in app.state.mailer.outbox if item['email'] == email)
        assert client.post('/v1/auth/verify-email', json={'token':token}).status_code == 200
        login = client.post('/v1/auth/login', json={'email':email, 'password':password})
        assert login.status_code == 200
        return response.json()['merchant_id'], login.json()['csrf_token']

    merchant, owner_csrf = account(owner, 'owner-queue@example.com')
    _, cashier_csrf = account(cashier, 'cashier-queue@example.com')
    account(outsider, 'outsider-queue@example.com')
    members = f'/v1/merchants/{merchant}/members'
    assert owner.put(members, headers={'x-csrf-token':owner_csrf},
                     json={'email':'cashier-queue@example.com', 'role':'cashier'}).status_code == 200
    body = {'merchant_id':merchant, 'order_id':'shared-order', 'numref':'12345',
            'concept':'Synthetic', 'amount_minor':15000, 'expiration_s':600}
    first = owner.post('/v1/checkout/qr', headers={'x-csrf-token':owner_csrf}, json=body)
    assert first.status_code == 502
    queue = f'/v1/merchants/{merchant}/checkout-unresolved'
    assert outsider.get(queue).status_code == 404
    found = cashier.get(queue)
    assert found.status_code == 200
    assert found.json()['intents'][0]['order_id'] == body['order_id']
    assert found.json()['intents'][0]['status'] == 'PROVIDER_UNCERTAIN'
    replay = cashier.post('/v1/checkout/qr', headers={'x-csrf-token':cashier_csrf}, json=body)
    assert replay.status_code == 201
    assert replay.json()['status'] == 'REPLAY_NO_PROVIDER_RETRY'
    assert replay.json()['intent']['bank_payment_confirmed'] is False
    assert provider.calls == 1


def test_unresolved_queue_browser_logic():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node is required for the queue UI regression')
    script = Path(__file__).with_name('unresolved_queue_ui.cjs')
    result = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=20, check=True)
    assert 'UNRESOLVED_QUEUE_UI_OK' in result.stdout
