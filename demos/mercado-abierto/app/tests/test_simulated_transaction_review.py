"""Tenant-scoped review using local in-memory provider pages only."""
import json
import socket
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from rio_pey_codi.identity import sha
from rio_pey_codi.models import Event, Intent, Membership, PendingEvent, SessionRow
from rio_pey_codi.pey_transaction_review import PageResponse
from rio_pey_codi.platform import Settings, create_platform
from rio_pey_codi.simulated_pey import SimulatedPeyPages
from test_platform import SECRET, checkout, signed_webhook, signup, verified_login

CLABE = '0' * 18


def record(tracking):
    return {'beneficiary': CLABE, 'tracking_key': tracking, 'amount_minor': 15000,
            'direction': 'credit', 'evidence_reference': 'synthetic-statement', 'currency': 'MXN'}


def page(items, token=None):
    return PageResponse(200, json.dumps({'items': items, 'nextToken': token}).encode())


def item(qr, tracking, ident, status='PAID'):
    result = {'id': ident, 'status': status, 'amount': 150, 'currency': 'MXN',
              'paymentMethod': 'CODI', 'payableId': qr, 'payableType': 'API_CODI_QR',
              'metadata': {'clabe': CLABE, 'trackingKey': tracking,
                           'externalMetadata': {'customerEmail': 'private@example.com'}}}
    if status == 'PAID':
        result['datePaid'] = 1704067260
    return result


@pytest.fixture
def demo(tmp_path, monkeypatch):
    original_socket = socket.socket
    def local_socket_only(family=socket.AF_INET, *args, **kwargs):
        if family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError('IP network forbidden during synthetic integration')
        return original_socket(family, *args, **kwargs)
    monkeypatch.setattr(socket, 'socket', local_socket_only)
    simulation = SimulatedPeyPages()
    app = create_platform(Settings(database_url='sqlite+pysqlite:///' + str(tmp_path / 'demo.sqlite3'),
                                   webhook_secret=SECRET),
                          simulated_pey=simulation)
    a = (app, TestClient(app))
    b = (app, TestClient(app))
    merchant_a = signup(a, 'owner-a@example.com')['merchant_id']
    csrf_a = verified_login(a, 'owner-a@example.com')
    merchant_b = signup(b, 'owner-b@example.com')['merchant_id']
    csrf_b = verified_login(b, 'owner-b@example.com')
    intent_a = checkout(a, merchant_a, csrf_a, order='shared', amount=15000).json()['intent']
    intent_b = checkout(b, merchant_b, csrf_b, order='shared', amount=15000).json()['intent']
    qr_a = app.state.payments.get(intent_a['id']).provider_qr_id
    qr_b = app.state.payments.get(intent_b['id']).provider_qr_id
    assert qr_a != qr_b
    simulation.install(qr_a, {None: page([item(qr_a, 'tracking-a', 'pending-a', 'PENDING')], 'cursor+1'),
                              'cursor+1': page([item(qr_a, 'tracking-a', 'paid-a')])})
    simulation.install(qr_b, {None: page([item(qr_b, 'tracking-b', 'paid-b')])})
    return app, simulation, a, b, merchant_a, merchant_b, csrf_a, csrf_b, intent_a['id'], intent_b['id']


def call(client, intent_id, csrf, records=None, **kwargs):
    return client.post(f'/v1/checkout/qr/{intent_id}/simulated-transaction-review',
                       headers={'x-csrf-token': csrf},
                       json={'bank_records': [record('tracking-a')] if records is None else records}, **kwargs)


def database_snapshot(app):
    with app.state.accounts.Session() as db:
        counts = tuple(db.scalar(select(func.count()).select_from(model)) for model in (Intent, Event, PendingEvent))
        rows = tuple((row.id, row.merchant_id, row.status, row.provider_qr_id, row.transaction_id, row.amount_minor)
                     for row in db.scalars(select(Intent).order_by(Intent.id)).all())
        return counts, rows


def test_each_company_sees_only_its_own_simulated_pages_and_no_writes(demo):
    app, _, a, b, _, _, csrf_a, csrf_b, id_a, id_b = demo
    before = database_snapshot(app)
    response_a = call(a[1], id_a, csrf_a)
    response_b = call(b[1], id_b, csrf_b, [record('tracking-b')])
    for response in (response_a, response_b):
        assert response.status_code == 200
        data = response.json()
        assert data['mode'] == 'LOCAL_SIMULATION'
        assert data['classification'] == 'MATCH_CANDIDATE_UNVERIFIED'
        assert not any(data[key] for key in ('bank_payment_confirmed', 'provider_authenticity_verified',
                   'independent_bank_source_verified', 'beneficiary_binding_verified',
                   'temporal_completeness_verified', 'payment_state_changed',
                   'bank_records_persisted', 'provider_records_persisted'))
        for sensitive in (CLABE, 'tracking-a', 'tracking-b', 'private@example.com', 'synthetic-statement'):
            assert sensitive not in response.text
    assert response_a.json()['pages_read'] == 2 and response_b.json()['pages_read'] == 1
    wrong_company_record = call(a[1], id_a, csrf_a, [record('tracking-b')])
    assert wrong_company_record.json()['classification'] == 'NO_BANK_RECORD'
    assert database_snapshot(app) == before


def test_cross_tenant_session_and_csrf_denied_before_transport(demo, monkeypatch):
    app, _, a, b, _, _, csrf_a, csrf_b, id_a, id_b = demo
    calls = []
    original = SimulatedPeyPages.__call__
    def spy(self, request):
        calls.append(1)
        return original(self, request)
    monkeypatch.setattr(SimulatedPeyPages, '__call__', spy)
    assert call(a[1], id_b, csrf_a).status_code == 404
    assert call(b[1], id_a, csrf_b).status_code == 404
    assert call(a[1], id_a, 'bad-csrf').status_code == 403
    assert call(TestClient(app), id_a, csrf_a).status_code == 401
    assert calls == []


def test_cashier_denied_admin_allowed_and_inputs_cannot_override_server_intent(demo, monkeypatch):
    app, _, owner, _, merchant, _, csrf, _, intent_id, _ = demo
    cashier, admin = (app, TestClient(app)), (app, TestClient(app))
    for env, email, role in ((cashier, 'cashier@example.com', 'cashier'),
                             (admin, 'admin@example.com', 'admin')):
        signup(env, email)
        token = verified_login(env, email)
        response = owner[1].put(f'/v1/merchants/{merchant}/members', headers={'x-csrf-token': csrf},
                                json={'email': email, 'role': role})
        assert response.status_code == 200
        if role == 'cashier': cashier_token = token
        else: admin_token = token
    calls = []
    original = SimulatedPeyPages.__call__
    def spy(self, request):
        calls.append(1)
        return original(self, request)
    monkeypatch.setattr(SimulatedPeyPages, '__call__', spy)
    assert call(cashier[1], intent_id, cashier_token).status_code == 403
    assert calls == []
    path = f'/v1/checkout/qr/{intent_id}/simulated-transaction-review'
    response = owner[1].post(path, headers={'x-csrf-token': csrf},
                             json={'bank_records': [], 'qr_id': 'other', 'expected_amount_minor': 1})
    assert response.status_code == 422 and calls == []
    assert call(admin[1], intent_id, admin_token).json()['classification'] == 'MATCH_CANDIDATE_UNVERIFIED'
    assert len(calls) == 2


def test_bad_input_is_bounded_and_never_echoed(demo, monkeypatch):
    _, _, a, _, _, _, csrf, _, intent_id, _ = demo
    def unexpected(*_args):
        raise AssertionError('transport must not run')
    monkeypatch.setattr(SimulatedPeyPages, '__call__', unexpected)
    path = f'/v1/checkout/qr/{intent_id}/simulated-transaction-review'
    headers = {'x-csrf-token': csrf, 'content-type': 'application/json'}
    assert a[1].post(path, headers=headers, content=b'{"bank_records":[],"bank_records":[]}').status_code == 422
    assert a[1].post(path, headers=headers, content=b'x' * 16385).status_code == 413
    assert a[1].post(path, headers={'x-csrf-token': csrf}, content='not-json').status_code == 415
    bad = {**record('private-tracking'), 'amount_minor': True}
    response = call(a[1], intent_id, csrf, [bad])
    assert response.status_code == 422 and 'private-tracking' not in response.text


def test_missing_qr_cannot_trigger_reissue_or_a_provider_query(demo, monkeypatch):
    app, _, a, _, _, _, csrf, _, intent_id, _ = demo
    with app.state.accounts.Session.begin() as db:
        row = db.get(Intent, intent_id)
        row.provider_qr_id = None
        row.status = 'PROVIDER_UNCERTAIN'
    before = database_snapshot(app)
    def unexpected(*_args):
        raise AssertionError('transport must not run without known QR')
    monkeypatch.setattr(SimulatedPeyPages, '__call__', unexpected)
    response = call(a[1], intent_id, csrf)
    assert response.status_code == 200 and response.json()['classification'] == 'QR_ID_REQUIRED'
    assert database_snapshot(app) == before


def test_saved_webhook_transaction_cannot_be_replaced_by_a_different_simulated_payment(demo):
    app, _, owner, _, _, _, csrf, _, intent_id, _ = demo
    row = app.state.payments.get(intent_id)
    event = {'type':'codi.qr.payment_received', 'codiQrId':row.provider_qr_id,
             'numRef':'shared', 'transactionId':'different-webhook-tx',
             'amount':150, 'apiKeyId':'synthetic-key-id'}
    assert signed_webhook(owner[1], event, 'signed-synthetic-event').status_code == 200
    before = database_snapshot(app)
    result = call(owner[1], intent_id, csrf)
    assert result.status_code == 200
    assert result.json()['classification'] == 'PROVIDER_TRANSACTION_CONFLICT'
    assert not result.json()['bank_payment_confirmed'] and database_snapshot(app) == before


def test_session_revoked_during_review_cannot_receive_result(demo, monkeypatch):
    app, _, a, _, _, _, csrf, _, intent_id, _ = demo
    sid_hash = sha(a[1].cookies.get('rio_sid'))
    original = SimulatedPeyPages.__call__
    def revoke(self, request):
        with app.state.accounts.Session.begin() as db:
            db.get(SessionRow, sid_hash).revoked_at = int(time.time())
        return original(self, request)
    monkeypatch.setattr(SimulatedPeyPages, '__call__', revoke)
    response = call(a[1], intent_id, csrf)
    assert response.status_code == 401
    assert 'MATCH_CANDIDATE' not in response.text and CLABE not in response.text


def test_role_or_payment_context_changed_during_review_is_not_returned(demo, monkeypatch):
    app, _, a, _, merchant, _, csrf, _, intent_id, _ = demo
    user_id = a[1].get('/v1/auth/me').json()['id']
    original = SimulatedPeyPages.__call__
    def demote(self, request):
        with app.state.accounts.Session.begin() as db:
            db.get(Membership, {'merchant_id': merchant, 'user_id': user_id}).role = 'cashier'
        return original(self, request)
    monkeypatch.setattr(SimulatedPeyPages, '__call__', demote)
    assert call(a[1], intent_id, csrf).status_code == 403
    with app.state.accounts.Session.begin() as db:
        db.get(Membership, {'merchant_id': merchant, 'user_id': user_id}).role = 'owner'
    def change(self, request):
        with app.state.accounts.Session.begin() as db:
            db.get(Intent, intent_id).status = 'PROVIDER_REPORTED'
        return original(self, request)
    monkeypatch.setattr(SimulatedPeyPages, '__call__', change)
    response = call(a[1], intent_id, csrf)
    assert response.status_code == 409 and 'MATCH_CANDIDATE' not in response.text


def test_simulation_cannot_be_supplied_as_an_arbitrary_network_transport(tmp_path):
    settings = Settings(database_url='sqlite+pysqlite:///' + str(tmp_path / 'demo.sqlite'))
    with pytest.raises(ValueError, match='local DEMO only'):
        create_platform(settings, simulated_pey=lambda _: None)
    remote = Settings(env='staging', database_url='postgresql://example.invalid/rio', auto_create=False,
                      email_mode='smtp', public_url='https://example.invalid', origin='https://example.invalid',
                      smtp_host='example.invalid', smtp_sender='synthetic@example.invalid',
                      smtp_user='synthetic', smtp_password='synthetic',
                      webhook_key_ref='staging-v1')
    with pytest.raises(ValueError, match='local DEMO only'):
        create_platform(remote, simulated_pey=SimulatedPeyPages())
    app = create_platform(remote)
    assert all('/simulated-transaction-review' not in getattr(route, 'path', '') for route in app.routes)
    app.state.accounts.Session.kw['bind'].dispose()
