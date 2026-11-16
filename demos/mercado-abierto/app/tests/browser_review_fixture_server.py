"""Loopback-only server with synthetic merchants and signed synthetic events."""
import base64
import json
import os
import tempfile
import time
from pathlib import Path

import uvicorn
from fastapi.testclient import TestClient
from rio_pey_codi.identity import Signup
from rio_pey_codi.platform import Settings, create_platform
from rio_pey_codi.signatures import make_signature


def main():
    if os.environ.get('RIO_BROWSER_TEST') != '1':
        raise SystemExit('This fixture runs only when RIO_BROWSER_TEST=1')
    port = int(os.environ.get('RIO_BROWSER_PORT', '8765'))
    secret = 'whsec_' + base64.b64encode(b'synthetic-browser-review-secret-32').decode()
    with tempfile.TemporaryDirectory(prefix='rio-review-browser-') as directory:
        settings = Settings(database_url='sqlite+pysqlite:///' + str(Path(directory) / 'fixture.sqlite3'),
                            webhook_secret=secret)
        app = create_platform(settings)
        accounts = app.state.accounts
        owner = accounts.signup(Signup(email='review-browser@example.com', password='synthetic-password-123',
                                       business_name='Principal'))
        accounts.verify(accounts.mailer.outbox[0]['token'])
        client = TestClient(app)
        login = client.post('/v1/auth/login', json={'email':'review-browser@example.com',
                                                     'password':'synthetic-password-123'})
        if login.status_code != 200:
            raise RuntimeError('Synthetic owner login failed')
        second_response = client.post('/v1/merchants', headers={'x-csrf-token':login.json()['csrf_token']},
                                      json={'name':'Segundo comercio'})
        if second_response.status_code != 201:
            raise RuntimeError('Synthetic merchant setup failed')
        second = second_response.json()
        for merchant, order, reference, tracking in (
            (owner['merchant_id'], 'browser-review-a', '1000001', 'tracking-a'),
            (second['id'], 'browser-review-b', '1000002', 'tracking-b'),
        ):
            intent, _ = app.state.payments.reserve(merchant, order, 15000, 'Pedido de prueba', reference, 600)
            qr = 'DEMO_' + intent.id
            app.state.payments.qr_issued(intent.id, qr, 'DEMOSTRACION - NO PAGABLE')
            payload = {'type':'codi.qr.payment_received', 'codiQrId':qr, 'numRef':reference,
                       'transactionId':'synthetic-' + order, 'apiKeyId':'synthetic-key-id', 'amount':150,
                       'metadata':{'clabe':'0' * 18, 'trackingKey':tracking}}
            raw = json.dumps(payload, separators=(',', ':')).encode()
            event_id, timestamp = 'synthetic-event-' + order, int(time.time())
            response = client.post('/v1/webhooks/pey', content=raw, headers={
                'webhook-id':event_id, 'webhook-timestamp':str(timestamp),
                'webhook-signature':make_signature(secret, event_id, timestamp, raw),
                'content-type':'application/json'})
            if response.status_code != 200:
                raise RuntimeError('Synthetic event setup failed')
        uvicorn.run(app, host='127.0.0.1', port=port, log_level='error', access_log=False)


if __name__ == '__main__':
    main()
