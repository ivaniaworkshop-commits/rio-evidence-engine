"""Durable, tenant-scoped review of synthetic provider events and bank records."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from rio_pey_codi.identity import sha
from rio_pey_codi.models import Membership, ReconciliationReview, SessionRow
from rio_pey_codi.platform import create_platform
from test_platform import signup, verified_login
from test_reconciliation_preview import CLABE, RECORD, TRACKING, deliver, payment  # noqa: F401


def save(payment, key='1' * 32, records=None, client=None, csrf=None):
    env, _, owner_csrf, intent_id, _ = payment
    return (client or env[1]).post(f'/v1/checkout/qr/{intent_id}/reconciliation-reviews',
        headers={'x-csrf-token':owner_csrf if csrf is None else csrf, 'idempotency-key':key},
        json={'bank_records':[RECORD] if records is None else records})


def test_review_persists_across_restart_without_storing_bank_fields(payment):
    deliver(payment)
    env, _, csrf, intent_id, _ = payment
    path = f'/v1/checkout/qr/{intent_id}/reconciliation-reviews'
    result = env[1].post(path, headers={'x-csrf-token':csrf, 'idempotency-key':'1' * 32},
                         json={'bank_records':[RECORD]})
    assert result.status_code == 201
    assert result.json()['review']['classification'] == 'MATCH_CANDIDATE_UNVERIFIED'
    assert result.json()['bank_payment_confirmed'] is False
    restarted = create_platform(env[0].state.settings)
    reader = TestClient(restarted, cookies=env[1].cookies)
    response = reader.get(path)
    assert response.status_code == 200
    assert len(response.json()['reviews']) == 1
    assert response.json()['reviews'][0]['id'] == result.json()['review']['id']
    assert all(value not in response.text for value in (CLABE, TRACKING, RECORD['evidence_reference']))
    with env[0].state.accounts.Session() as db:
        rows = [dict(row._mapping) for row in db.execute(text('SELECT * FROM reconciliation_reviews'))]
    stored = json.dumps(rows)
    assert all(value not in stored for value in (CLABE, TRACKING, RECORD['evidence_reference']))
    assert rows[0]['bank_record_count'] == 1 and rows[0]['provider_event_count'] == 1


def test_retries_cannot_duplicate_or_silently_replace_record(payment):
    deliver(payment)
    first = save(payment)
    assert first.status_code == 201
    duplicate = save(payment, records=[{**RECORD, 'amount_minor':14999}])
    assert duplicate.status_code == 409 and duplicate.json()['code'] == 'REVIEW_REQUEST_ALREADY_USED'
    env, _, _, intent_id, _ = payment
    path = f'/v1/checkout/qr/{intent_id}/reconciliation-reviews'
    recovered = env[1].get(path + '/by-request/' + '1' * 32)
    assert recovered.status_code == 200 and recovered.json()['review']['id'] == first.json()['review']['id']
    second = save(payment, key='2' * 32, records=[{**RECORD, 'amount_minor':14999}])
    assert second.status_code == 201 and second.json()['review']['classification'] == 'DISCREPANCY_REVIEW_REQUIRED'
    assert len(env[1].get(path).json()['reviews']) == 2


def test_database_triggers_reject_update_and_delete(payment):
    deliver(payment)
    result = save(payment)
    ident = result.json()['review']['id']
    engine = payment[0][0].state.accounts.Session.kw['bind']
    for statement in ('UPDATE reconciliation_reviews SET classification = :classification WHERE id = :id',
                      'DELETE FROM reconciliation_reviews WHERE id = :id'):
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(text(statement), {'classification':'FAKE', 'id':ident})
    with payment[0][0].state.accounts.Session() as db:
        assert db.get(ReconciliationReview, ident).classification == 'MATCH_CANDIDATE_UNVERIFIED'


def test_requires_owner_or_admin_and_session_for_reads_and_writes(payment):
    deliver(payment)
    env, merchant_id, owner_csrf, intent_id, _ = payment
    assert save(payment).status_code == 201
    cashier, outsider = (env[0], TestClient(env[0])), (env[0], TestClient(env[0]))
    signup(cashier, 'durable-cashier@example.com')
    cashier_csrf = verified_login(cashier, 'durable-cashier@example.com')
    assert env[1].put(f'/v1/merchants/{merchant_id}/members', headers={'x-csrf-token':owner_csrf},
                      json={'email':'durable-cashier@example.com', 'role':'cashier'}).status_code == 200
    signup(outsider, 'durable-outsider@example.com')
    outsider_csrf = verified_login(outsider, 'durable-outsider@example.com')
    path = f'/v1/checkout/qr/{intent_id}/reconciliation-reviews'
    assert save(payment, key='2' * 32, client=cashier[1], csrf=cashier_csrf).status_code == 403
    assert cashier[1].get(path).status_code == 403
    assert save(payment, key='2' * 32, client=outsider[1], csrf=outsider_csrf).status_code == 404
    assert outsider[1].get(path).status_code == 404
    assert save(payment, key='2' * 32, csrf='invalid').status_code == 403
    assert TestClient(env[0]).get(path).status_code == 401
    with env[0].state.accounts.Session() as db:
        assert db.scalar(select(func.count()).select_from(ReconciliationReview)) == 1


def test_same_request_key_race_records_one_review(payment):
    deliver(payment)
    env = payment[0]
    barrier = threading.Barrier(2)
    def submit():
        client = TestClient(env[0], cookies=env[1].cookies)
        barrier.wait(timeout=5)
        return save(payment, client=client, key='3' * 32).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _: submit(), range(2)))
    assert sorted(statuses) == [201, 409]
    with env[0].state.accounts.Session() as db:
        assert db.scalar(select(func.count()).select_from(ReconciliationReview)) == 1


@pytest.mark.parametrize(('change', 'status'), [('session', 401), ('role', 403)])
def test_authority_is_rechecked_inside_write_transaction(payment, monkeypatch, change, status):
    deliver(payment)
    env, merchant_id, _, _, _ = payment
    app, client = env
    user_id = client.get('/v1/auth/me').json()['id']
    sid = sha(client.cookies.get('rio_sid'))
    original = app.state.payments.record_reconciliation_review
    def revoke(*args):
        with app.state.accounts.Session.begin() as db:
            if change == 'session':
                db.get(SessionRow, sid).revoked_at = int(time.time())
            else:
                db.get(Membership, {'merchant_id':merchant_id, 'user_id':user_id}).role = 'cashier'
        return original(*args)
    monkeypatch.setattr(app.state.payments, 'record_reconciliation_review', revoke)
    assert save(payment).status_code == status
    with app.state.accounts.Session() as db:
        assert db.scalar(select(func.count()).select_from(ReconciliationReview)) == 0


def test_invalid_request_keys_and_untrusted_fields_never_persist(payment):
    env, _, csrf, intent_id, _ = payment
    path = f'/v1/checkout/qr/{intent_id}/reconciliation-reviews'
    assert save(payment, key='invalid').status_code == 422
    forged = env[1].post(path, headers={'x-csrf-token':csrf, 'idempotency-key':'4' * 32},
                         json={'bank_records':[RECORD], 'bank_payment_confirmed':True})
    assert forged.status_code == 422 and CLABE not in forged.text
    assert env[1].get(path + '/by-request/not-valid').status_code == 422
    with env[0].state.accounts.Session() as db:
        assert db.scalar(select(func.count()).select_from(ReconciliationReview)) == 0
