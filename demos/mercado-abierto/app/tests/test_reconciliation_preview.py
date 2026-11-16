"""Review-only reconciliation using synthetic signed events and asserted bank records."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from rio_pey_codi.models import Event, Intent, PendingEvent
from rio_pey_codi.platform import Settings, create_platform
from test_platform import SECRET, checkout, signed_webhook, signup, verified_login

CLABE = '000000000000000000'  # Synthetic placeholder, not a bank account.
TRACKING = '000123456789'
RECORD = {'beneficiary':CLABE, 'tracking_key':TRACKING, 'amount_minor':15000,
          'direction':'credit', 'evidence_reference':'statement-fixture', 'currency':'MXN'}


@pytest.fixture
def payment(tmp_path):
    app = create_platform(Settings(database_url='sqlite+pysqlite:///' + str(tmp_path/'review.sqlite3'),
                                   webhook_secret=SECRET))
    env = (app, TestClient(app))
    merchant = signup(env)['merchant_id']
    csrf = verified_login(env)
    result = checkout(env, merchant, csrf, order='review-1', amount=15000)
    assert result.status_code == 201
    intent = app.state.payments.get(result.json()['intent']['id'])
    payload = {'amount':150, 'apiKeyId':'synthetic-key-id', 'codiQrId':intent.provider_qr_id,
               'concept':'Pan', 'datePaid':1790724818, 'numRef':'review-1',
               'transactionId':'synthetic-tx', 'type':'codi.qr.payment_received',
               'metadata':{'clabe':CLABE, 'trackingKey':TRACKING}}
    return env, merchant, csrf, intent.id, payload


def post_preview(payment, records, client=None, csrf=None):
    env, _, owner_csrf, intent_id, _ = payment
    client = client or env[1]
    token = owner_csrf if csrf is None else csrf
    return client.post(f'/v1/checkout/qr/{intent_id}/reconciliation-preview',
                       headers={'x-csrf-token':token}, json={'bank_records':records})


def deliver(payment, event_id='review-event'):
    env, _, _, _, payload = payment
    result = signed_webhook(env[1], payload, event_id)
    assert result.status_code == 200


def test_review_preview_uses_metadata_without_claiming_bank_settlement(payment):
    deliver(payment)
    env, _, _, intent_id, _ = payment
    with env[0].state.accounts.Session() as db:
        before = [db.scalar(select(func.count()).select_from(model)) for model in (Intent, Event, PendingEvent)]
        status = db.get(Intent, intent_id).status
    response = post_preview(payment, [RECORD])
    assert response.status_code == 200
    result = response.json()
    assert result == {'classification':'MATCH_CANDIDATE_UNVERIFIED', 'bank_payment_confirmed':False,
                      'independent_source_verified':False, 'provider_signature_reverified':True,
                      'signature_assessment':'VERIFIED',
                      'account_assessment':'NO_OWNER_REPORT',
                      'beneficiary_binding_verified':False, 'bank_records_persisted':False}
    assert CLABE not in response.text and TRACKING not in response.text and RECORD['evidence_reference'] not in response.text
    with env[0].state.accounts.Session() as db:
        assert [db.scalar(select(func.count()).select_from(model)) for model in (Intent, Event, PendingEvent)] == before
        assert db.get(Intent, intent_id).status == status == 'PROVIDER_REPORTED'


@pytest.mark.parametrize(('records', 'expected'), [
    ([], 'NO_BANK_RECORD'),
    ([RECORD, RECORD], 'AMBIGUOUS_BANK_RECORDS'),
    ([{**RECORD, 'amount_minor':15001}], 'DISCREPANCY_REVIEW_REQUIRED'),
    ([{**RECORD, 'beneficiary':'111111111111111111'}], 'DISCREPANCY_REVIEW_REQUIRED'),
    ([{**RECORD, 'currency':'USD'}], 'DISCREPANCY_REVIEW_REQUIRED'),
    ([{**RECORD, 'direction':'reversal'}], 'REVERSAL_REVIEW_REQUIRED'),
    ([{**RECORD, 'tracking_key':'123456789'}], 'NO_BANK_RECORD'),
])
def test_review_classifies_asserted_records_without_normalizing_identity(payment, records, expected):
    deliver(payment)
    result = post_preview(payment, records)
    assert result.status_code == 200
    assert result.json()['classification'] == expected
    assert result.json()['bank_payment_confirmed'] is False


def test_review_does_not_invent_missing_provider_metadata(payment):
    assert post_preview(payment, [RECORD]).json()['classification'] == 'NO_PROVIDER_REPORT'
    del payment[-1]['metadata']
    deliver(payment)
    result = post_preview(payment, [RECORD]).json()
    assert result['classification'] == 'PROVIDER_FIELDS_MISSING'
    assert result['bank_payment_confirmed'] is False


def test_review_rejects_conflicting_or_corrupted_provider_evidence(payment):
    deliver(payment)
    payment[-1]['metadata']['trackingKey'] = 'different-tracking'
    deliver(payment, 'second-event')
    assert post_preview(payment, [RECORD]).json()['classification'] == 'PROVIDER_EVIDENCE_CONFLICT'
    with payment[0][0].state.accounts.Session.begin() as db:
        db.get(Event, 'review-event').raw_body = b'{"tampered":true}'
    assert post_preview(payment, [RECORD]).json()['classification'] == 'PROVIDER_EVIDENCE_INVALID'


def test_preview_requires_owner_or_admin_csrf_and_tenant_membership(payment):
    env, merchant, owner_csrf, intent_id, _ = payment
    deliver(payment)
    cashier = (env[0], TestClient(env[0]))
    signup(cashier, 'preview-cashier@example.com')
    cashier_csrf = verified_login(cashier, 'preview-cashier@example.com')
    grant = env[1].put(f'/v1/merchants/{merchant}/members', headers={'x-csrf-token':owner_csrf},
                       json={'email':'preview-cashier@example.com', 'role':'cashier'})
    assert grant.status_code == 200
    assert post_preview(payment, [RECORD], cashier[1], cashier_csrf).status_code == 403
    outsider = (env[0], TestClient(env[0]))
    signup(outsider, 'preview-outsider@example.com')
    outsider_csrf = verified_login(outsider, 'preview-outsider@example.com')
    assert post_preview(payment, [RECORD], outsider[1], outsider_csrf).status_code == 404
    assert post_preview(payment, [RECORD], csrf='invalid').status_code == 403
    assert TestClient(env[0]).post(f'/v1/checkout/qr/{intent_id}/reconciliation-preview',
                                  json={'bank_records':[RECORD]}).status_code == 401


def test_preview_rejects_bad_input_without_echoing_financial_data(payment):
    deliver(payment)
    invalid = {**RECORD, 'amount_minor':True, 'evidence_reference':'sensitive-synthetic-marker'}
    response = post_preview(payment, [invalid])
    assert response.status_code == 422
    assert 'sensitive-synthetic-marker' not in response.text and CLABE not in response.text
    env, _, csrf, intent_id, _ = payment
    path = f'/v1/checkout/qr/{intent_id}/reconciliation-preview'
    headers={'x-csrf-token':csrf, 'content-type':'application/json'}
    duplicate = env[1].post(path, headers=headers, content=b'{"bank_records":[],"bank_records":[]}')
    assert duplicate.status_code == 422
    oversized = env[1].post(path, headers=headers, content=b'x' * 16385)
    assert oversized.status_code == 413
    assert post_preview(payment, [RECORD] * 51).status_code == 422
