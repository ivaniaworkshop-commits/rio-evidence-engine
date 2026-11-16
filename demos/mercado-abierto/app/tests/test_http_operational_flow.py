"""Real loopback HTTP through uvicorn; all users, events and bank inputs are synthetic."""
import base64
import json
import socket
import threading
import time
from contextlib import contextmanager

import httpx
import uvicorn

from rio_pey_codi.platform import Settings, create_platform
from rio_pey_codi.signatures import make_signature


@contextmanager
def serve_on_loopback(app):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(('127.0.0.1', 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port,
                                           log_level='error', access_log=False))
    thread = threading.Thread(target=server.run, kwargs={'sockets':[listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    try:
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(.02)
        if not server.started:
            raise RuntimeError('Loopback test server did not start')
        yield f'http://127.0.0.1:{port}'
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        if thread.is_alive():
            raise RuntimeError('Loopback test server did not stop')


def sign_up_and_log_in(client, app, email):
    credentials = {'email':email, 'password':'synthetic-password-123'}
    response = client.post('/v1/auth/signup', json={**credentials, 'business_name':'Comercio sintético'})
    assert response.status_code == 201 and 'token' not in response.text.lower()
    token = next(item['token'] for item in app.state.mailer.outbox if item['email'] == email)
    assert client.post('/v1/auth/verify-email', json={'token':token}).status_code == 200
    login = client.post('/v1/auth/login', json=credentials)
    assert login.status_code == 200
    return response.json()['merchant_id'], login.json()['csrf_token']


def test_signup_to_durable_review_over_http_and_restart(tmp_path):
    secret = 'whsec_' + base64.b64encode(b'synthetic-http-webhook-secret-32-bytes').decode()
    settings = Settings(database_url='sqlite+pysqlite:///' + str(tmp_path / 'loopback.sqlite3'),
                        webhook_secret=secret)
    app = create_platform(settings)
    bank = {'beneficiary':'0' * 18, 'tracking_key':'synthetic-http-tracking', 'amount_minor':15000,
            'direction':'credit', 'evidence_reference':'synthetic-statement', 'currency':'MXN'}
    request_key = 'a' * 32
    with serve_on_loopback(app) as origin:
        with httpx.Client(base_url=origin, timeout=5, trust_env=False) as owner:
            merchant, csrf = sign_up_and_log_in(owner, app, 'http-owner@example.com')
            headers = {'x-csrf-token':csrf}
            charge = owner.post('/v1/checkout/qr', headers=headers, json={
                'merchant_id':merchant, 'order_id':'http-order', 'numref':'12345',
                'concept':'Pedido sintético', 'amount_minor':15000, 'expiration_s':600})
            assert charge.status_code == 201
            assert 'NO PAGABLE' in charge.json()['intent']['qr_display']
            intent_id = charge.json()['intent']['id']
            qr_id = app.state.payments.get(intent_id).provider_qr_id
            payload = {'type':'codi.qr.payment_received', 'codiQrId':qr_id, 'numRef':'12345',
                       'transactionId':'synthetic-http-tx', 'apiKeyId':'synthetic-key-id', 'amount':150,
                       'metadata':{'clabe':bank['beneficiary'], 'trackingKey':bank['tracking_key']}}
            raw = json.dumps(payload, separators=(',', ':')).encode()
            timestamp = int(time.time())
            webhook = owner.post('/v1/webhooks/pey', content=raw, headers={
                'webhook-id':'synthetic-http-event', 'webhook-timestamp':str(timestamp),
                'webhook-signature':make_signature(secret, 'synthetic-http-event', timestamp, raw),
                'content-type':'application/json'})
            assert webhook.status_code == 200 and webhook.json()['bank_settlement'] == 'NOT_VERIFIED'
            base = f'/v1/checkout/qr/{intent_id}'
            preview = owner.post(base + '/reconciliation-preview', headers=headers, json={'bank_records':[bank]})
            assert preview.status_code == 200 and preview.json()['classification'] == 'MATCH_CANDIDATE_UNVERIFIED'
            saved = owner.post(base + '/reconciliation-reviews',
                               headers={**headers, 'idempotency-key':request_key}, json={'bank_records':[bank]})
            assert saved.status_code == 201 and not saved.json()['bank_payment_confirmed']
            review_id = saved.json()['review']['id']
            duplicate = owner.post(base + '/reconciliation-reviews',
                                   headers={**headers, 'idempotency-key':request_key}, json={'bank_records':[bank]})
            assert duplicate.status_code == 409
            cookies = httpx.Cookies(owner.cookies)
            with httpx.Client(base_url=origin, timeout=5, trust_env=False) as outsider:
                _, outsider_csrf = sign_up_and_log_in(outsider, app, 'http-outsider@example.com')
                assert outsider.get(base + '/reconciliation-reviews').status_code == 404
                assert outsider.post(base + '/reconciliation-reviews', headers={
                    'x-csrf-token':outsider_csrf, 'idempotency-key':'b' * 32},
                    json={'bank_records':[bank]}).status_code == 404
    app.state.accounts.Session.kw['bind'].dispose()
    restarted = create_platform(settings)
    with serve_on_loopback(restarted) as origin:
        with httpx.Client(base_url=origin, cookies=cookies, timeout=5, trust_env=False) as owner:
            history = owner.get(base + '/reconciliation-reviews')
            assert history.status_code == 200
            assert [entry['id'] for entry in history.json()['reviews']] == [review_id]
            assert history.json()['reviews'][0]['source'] == 'USER_REPORTED_UNVERIFIED'
            assert not history.json()['bank_payment_confirmed']
            assert bank['beneficiary'] not in history.text and bank['tracking_key'] not in history.text
    restarted.state.accounts.Session.kw['bind'].dispose()
