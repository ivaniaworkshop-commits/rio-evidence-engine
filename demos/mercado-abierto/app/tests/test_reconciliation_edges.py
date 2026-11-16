"""Additional authorization and malformed-input boundaries for review previews."""
from fastapi.testclient import TestClient

from rio_pey_codi.models import Event
from test_platform import signup, verified_login
from test_reconciliation_preview import RECORD, deliver, payment, post_preview  # noqa: F401


def test_conflicting_bank_account_ids_are_not_silently_merged(payment):
    payment[-1]['bankAccountId'] = 'synthetic-account-one'
    deliver(payment)
    payment[-1]['bankAccountId'] = 'synthetic-account-two'
    deliver(payment, 'other-account-event')
    response = post_preview(payment, [RECORD])
    assert response.json()['classification'] == 'PROVIDER_EVIDENCE_CONFLICT'
    assert response.json()['bank_payment_confirmed'] is False


def test_missing_legacy_raw_event_is_not_reconstructed(payment):
    deliver(payment)
    with payment[0][0].state.accounts.Session.begin() as db:
        db.get(Event, 'review-event').raw_body = None
    assert post_preview(payment, [RECORD]).json()['classification'] == 'PROVIDER_EVIDENCE_MISSING'


def test_authorized_admin_can_review_without_receiving_bank_data(payment):
    env, merchant, owner_csrf, _, _ = payment
    deliver(payment)
    admin = (env[0], TestClient(env[0]))
    signup(admin, 'preview-admin@example.com')
    admin_csrf = verified_login(admin, 'preview-admin@example.com')
    grant = env[1].put(f'/v1/merchants/{merchant}/members', headers={'x-csrf-token':owner_csrf},
                       json={'email':'preview-admin@example.com', 'role':'admin'})
    assert grant.status_code == 200
    response = post_preview(payment, [RECORD], admin[1], admin_csrf)
    assert response.status_code == 200
    assert response.json()['classification'] == 'MATCH_CANDIDATE_UNVERIFIED'
    assert RECORD['beneficiary'] not in response.text and RECORD['tracking_key'] not in response.text


def test_preview_rejects_deep_or_wrong_content_type_without_traceback(payment):
    env, _, csrf, intent_id, _ = payment
    path = f'/v1/checkout/qr/{intent_id}/reconciliation-preview'
    deep = '{"bank_records":' + '[' * 1200 + '0' + ']' * 1200 + '}'
    response = env[1].post(path, headers={'x-csrf-token':csrf, 'content-type':'application/json'}, content=deep)
    assert response.status_code == 422 and 'Traceback' not in response.text
    response = env[1].post(path, headers={'x-csrf-token':csrf, 'content-type':'text/plain'}, content='{}')
    assert response.status_code == 415
