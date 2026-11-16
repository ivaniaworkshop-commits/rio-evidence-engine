"""Start a loopback-only DEMO server for the optional browser regression."""
import os
import tempfile
import time
import uuid
from pathlib import Path

import uvicorn
from fastapi.testclient import TestClient

from rio_pey_codi.identity import Signup
from rio_pey_codi.models import Intent
from rio_pey_codi.platform import Settings, create_platform


class SyntheticTimeoutProvider:
    def __init__(self, counter):
        self.counter = counter

    def create_qr(self, **_kwargs):
        with self.counter.open('a', encoding='utf-8') as file:
            file.write('attempt\n')
        time.sleep(2)
        raise TimeoutError('synthetic timeout')


def main():
    if os.environ.get('RIO_BROWSER_TEST') != '1':
        raise SystemExit('Set RIO_BROWSER_TEST=1 for the isolated DEMO fixture')
    counter = Path(os.environ['RIO_BROWSER_COUNTER'])
    port = int(os.environ.get('RIO_BROWSER_PORT', '8765'))
    with tempfile.TemporaryDirectory(prefix='rio-browser-test-') as directory:
        settings = Settings(database_url='sqlite+pysqlite:///' + str(Path(directory) / 'demo.sqlite3'))
        app = create_platform(settings, provider=SyntheticTimeoutProvider(counter))
        accounts = app.state.accounts
        owner = accounts.signup(Signup(email='browser@example.com', password='synthetic-password-123', business_name='Principal'))
        accounts.verify(app.state.mailer.outbox[0]['token'])
        setup = TestClient(app)
        login = setup.post('/v1/auth/login', json={'email':'browser@example.com', 'password':'synthetic-password-123'})
        if login.status_code != 200:
            raise RuntimeError('Synthetic owner login failed')
        if os.environ.get('RIO_BROWSER_OWNER') == '1':
            accounts.platform_owner_id = login.json()['user_id']
        headers = {'x-csrf-token':login.json()['csrf_token']}
        if setup.post('/v1/merchants', headers=headers, json={'name':'Segundo comercio'}).status_code != 201:
            raise RuntimeError('Synthetic merchant setup failed')
        if os.environ.get('RIO_BROWSER_SECOND_CASHIER') == '1':
            accounts.signup(Signup(email='cashier@example.com', password='synthetic-password-123', business_name='Caja auxiliar'))
            accounts.verify(app.state.mailer.outbox[-1]['token'])
            response = setup.put(f"/v1/merchants/{owner['merchant_id']}/members", headers=headers,
                                 json={'email':'cashier@example.com', 'role':'cashier'})
            if response.status_code != 200:
                raise RuntimeError('Synthetic cashier setup failed')
        if os.environ.get('RIO_BROWSER_SEED_OLD') == '1':
            merchant_id = owner['merchant_id']
            old, _ = app.state.payments.reserve(merchant_id, 'old-queue-order', 15000,
                                               'Pedido anterior', '1000999', 600)
            app.state.payments.uncertain(old.id)
            with accounts.Session.begin() as db:
                db.get(Intent, old.id).created_at = 1700000000
                for i in range(55):
                    db.add(Intent(id=uuid.uuid4().hex, merchant_id=merchant_id, order_id=f'new-{i}',
                                  amount_minor=100, concept='Synthetic', numref=f'new-{i}',
                                  expiration_s=600, status='QR_ISSUED', created_at=1800000000+i))
        uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning', access_log=False)


if __name__ == '__main__':
    main()
