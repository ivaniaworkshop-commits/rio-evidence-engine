"""Compare signed account identifiers to an owner's tenant-scoped assertion."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event as ThreadEvent

from fastapi.testclient import TestClient

from rio_pey_codi.models import Event, ReconciliationReview
from rio_pey_codi.platform import create_platform
from test_beneficiary_claims import ACCOUNT, WITHDRAWN, post
from test_platform import signup, verified_login
from test_reconciliation_preview import RECORD, deliver, payment, post_preview  # noqa: F401

OTHER_ACCOUNT = '01JBAVWE4NS5TGXHWGMX3KH23R'  # Synthetic identifier only.


def test_mismatched_owner_account_cannot_be_reported_as_matching_candidate(payment):
    env, merchant, csrf, _, payload = payment
    assert post(env[1], merchant, csrf, 'a' * 32).status_code == 201
    payload['bankAccountId'] = OTHER_ACCOUNT
    deliver(payment)
    result = post_preview(payment, [RECORD]).json()
    assert result['classification'] == 'OWNER_ACCOUNT_MISMATCH'
    assert result['account_assessment'] == 'MISMATCH_OWNER_REPORT'
    assert result['provider_signature_reverified'] is True
    assert result['beneficiary_binding_verified'] is False
    assert result['bank_payment_confirmed'] is False


def test_matching_id_is_only_a_report_and_is_durable_without_exposing_ids(payment):
    env, merchant, csrf, intent_id, payload = payment
    claim = post(env[1], merchant, csrf, 'a' * 32).json()['claim']
    payload['bankAccountId'] = ACCOUNT
    deliver(payment)
    preview = post_preview(payment, [RECORD])
    assert preview.json()['account_assessment'] == 'MATCH_OWNER_REPORT_UNVERIFIED'
    assert preview.json()['classification'] == 'MATCH_CANDIDATE_UNVERIFIED'
    assert not preview.json()['beneficiary_binding_verified'] and not preview.json()['bank_payment_confirmed']
    assert ACCOUNT not in preview.text
    path = f'/v1/checkout/qr/{intent_id}/reconciliation-reviews'
    saved = env[1].post(path, headers={'x-csrf-token':csrf, 'idempotency-key':'1' * 32},
                        json={'bank_records':[RECORD]})
    assert saved.status_code == 201
    assert saved.json()['review']['account_assessment_at_review'] == 'MATCH_OWNER_REPORT_UNVERIFIED'
    assert ACCOUNT not in saved.text and claim['id'] not in saved.text
    with env[0].state.accounts.Session() as db:
        row = db.get(ReconciliationReview, saved.json()['review']['id'])
        assert row.owner_claim_id == claim['id'] and row.account_assessment == 'MATCH_OWNER_REPORT_UNVERIFIED'
    assert post(env[1], merchant, csrf, 'b' * 32, WITHDRAWN).status_code == 201
    assert post_preview(payment, [RECORD]).json()['account_assessment'] == 'OWNER_REPORT_WITHDRAWN'
    reopened = create_platform(env[0].state.settings)
    history = TestClient(reopened, cookies=env[1].cookies).get(path)
    assert history.json()['reviews'][0]['account_assessment_at_review'] == 'MATCH_OWNER_REPORT_UNVERIFIED'
    assert ACCOUNT not in history.text and claim['id'] not in history.text


def test_missing_webhook_account_id_is_not_inferred_from_owner_or_default(payment):
    env, merchant, csrf, _, _ = payment
    assert post(env[1], merchant, csrf, 'a' * 32).status_code == 201
    deliver(payment)
    result = post_preview(payment, [RECORD]).json()
    assert result['account_assessment'] == 'WEBHOOK_ACCOUNT_ID_ABSENT'
    assert result['classification'] == 'MATCH_CANDIDATE_UNVERIFIED'
    assert not result['beneficiary_binding_verified'] and not result['bank_payment_confirmed']


def test_claim_without_account_id_does_not_create_an_association(payment):
    env, merchant, csrf, _, payload = payment
    assert post(env[1], merchant, csrf, 'a' * 32,
                {'claim':'OWNER_REPORTED_VERIFIED', 'provider_account_id':None}).status_code == 201
    payload['bankAccountId'] = ACCOUNT
    deliver(payment)
    result = post_preview(payment, [RECORD]).json()
    assert result['account_assessment'] == 'OWNER_REPORT_NO_ACCOUNT_ID'
    assert not result['beneficiary_binding_verified']


def test_report_in_another_merchant_is_not_used(payment):
    env, _, csrf, _, payload = payment
    other = env[1].post('/v1/merchants', headers={'x-csrf-token':csrf}, json={'name':'Otro comercio'}).json()['id']
    assert post(env[1], other, csrf, 'a' * 32).status_code == 201
    payload['bankAccountId'] = ACCOUNT
    deliver(payment)
    result = post_preview(payment, [RECORD]).json()
    assert result['account_assessment'] == 'NO_OWNER_REPORT'
    assert not result['beneficiary_binding_verified']


def test_partial_id_presence_is_not_full_account_match(payment):
    env, merchant, csrf, _, payload = payment
    assert post(env[1], merchant, csrf, 'a' * 32).status_code == 201
    payload['bankAccountId'] = ACCOUNT
    deliver(payment, 'with-account')
    del payload['bankAccountId']
    deliver(payment, 'without-account')
    result = post_preview(payment, [RECORD]).json()
    assert result['account_assessment'] == 'PARTIAL_MATCH_UNVERIFIED'
    assert not result['beneficiary_binding_verified']


def test_account_disagreement_remains_visible_when_bank_metadata_is_missing(payment):
    env, merchant, csrf, _, payload = payment
    assert post(env[1], merchant, csrf, 'a' * 32).status_code == 201
    payload['bankAccountId'] = OTHER_ACCOUNT
    del payload['metadata']
    deliver(payment)
    result = post_preview(payment, [RECORD]).json()
    assert result['classification'] == 'PROVIDER_FIELDS_MISSING'
    assert result['account_assessment'] == 'MISMATCH_OWNER_REPORT'
    assert not result['bank_payment_confirmed']


def test_unverified_signature_never_produces_account_comparison(payment):
    env, merchant, csrf, _, payload = payment
    assert post(env[1], merchant, csrf, 'a' * 32).status_code == 201
    payload['bankAccountId'] = OTHER_ACCOUNT
    deliver(payment)
    forged = {**payload, 'bankAccountId':ACCOUNT}
    raw = json.dumps(forged, separators=(',', ':')).encode()
    with env[0].state.accounts.Session.begin() as db:
        event = db.get(Event, 'review-event')
        event.raw_body, event.sha256 = raw, hashlib.sha256(raw).hexdigest()
    result = post_preview(payment, [RECORD]).json()
    assert result['account_assessment'] == 'SIGNATURE_NOT_VERIFIED'
    assert result['classification'] == 'PROVIDER_SIGNATURE_INVALID'


def test_preview_rejects_owner_report_change_during_evaluation(payment, monkeypatch):
    env, merchant, csrf, _, payload = payment
    assert post(env[1], merchant, csrf, 'a' * 32).status_code == 201
    payload['bankAccountId'] = ACCOUNT
    deliver(payment)
    original = env[0].state.payments.reconciliation_preview
    def change_claim(*args):
        result = original(*args)
        client = TestClient(env[0], cookies=env[1].cookies)
        assert post(client, merchant, csrf, 'b' * 32,
                    {'claim':'OWNER_REPORTED_VERIFIED','provider_account_id':OTHER_ACCOUNT}).status_code == 201
        return result
    monkeypatch.setattr(env[0].state.payments, 'reconciliation_preview', change_claim)
    response = post_preview(payment, [RECORD])
    assert response.status_code == 409 and 'MATCH_CANDIDATE' not in response.text


def test_review_serializes_owner_claim_update(payment, monkeypatch):
    env, merchant, csrf, intent_id, payload = payment
    first = post(env[1], merchant, csrf, 'a' * 32).json()['claim']
    payload['bankAccountId'] = ACCOUNT
    deliver(payment)
    admin = (env[0], TestClient(env[0]))
    signup(admin, 'account-admin@example.com')
    admin_csrf = verified_login(admin, 'account-admin@example.com')
    granted = env[1].put(f'/v1/merchants/{merchant}/members', headers={'x-csrf-token':csrf},
                         json={'email':'account-admin@example.com','role':'admin'})
    assert granted.status_code == 200
    ready, release, writing, written = ThreadEvent(), ThreadEvent(), ThreadEvent(), ThreadEvent()
    original = env[0].state.payments._review_assessment
    def pause(*args):
        result = original(*args)
        ready.set()
        if not release.wait(8):
            raise RuntimeError('test did not release review')
        return result
    monkeypatch.setattr(env[0].state.payments, '_review_assessment', pause)
    path = f'/v1/checkout/qr/{intent_id}/reconciliation-reviews'
    def review():
        return admin[1].post(path, headers={'x-csrf-token':admin_csrf,'idempotency-key':'2' * 32},
                             json={'bank_records':[RECORD]})
    def change_claim():
        writing.set()
        client = TestClient(env[0], cookies=env[1].cookies)
        response = post(client, merchant, csrf, 'b' * 32,
                        {'claim':'OWNER_REPORTED_VERIFIED','provider_account_id':OTHER_ACCOUNT})
        written.set()
        return response
    with ThreadPoolExecutor(max_workers=2) as pool:
        reader = pool.submit(review)
        assert ready.wait(8)
        writer = pool.submit(change_claim)
        assert writing.wait(8)
        blocked = not written.wait(.4)
        release.set()
        reviewed, changed = reader.result(timeout=8), writer.result(timeout=8)
    assert blocked and reviewed.status_code == 201 and changed.status_code == 201
    assert reviewed.json()['review']['account_assessment_at_review'] == 'MATCH_OWNER_REPORT_UNVERIFIED'
    with env[0].state.accounts.Session() as db:
        row = db.get(ReconciliationReview, reviewed.json()['review']['id'])
        assert row.owner_claim_id == first['id']
