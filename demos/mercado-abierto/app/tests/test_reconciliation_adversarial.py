"""Reject inconsistent stored events and never promote caller assertions."""
import hashlib
import json

from rio_pey_codi.models import Event
from test_reconciliation_preview import RECORD, deliver, payment, post_preview  # noqa: F401


def test_non_ascii_stored_digest_fails_closed(payment):
    deliver(payment)
    with payment[0][0].state.accounts.Session.begin() as db:
        db.get(Event, 'review-event').sha256 = 'ñ' * 64
    response = post_preview(payment, [RECORD])
    assert response.status_code == 200
    assert response.json()['classification'] == 'PROVIDER_EVIDENCE_INVALID'
    assert response.json()['bank_payment_confirmed'] is False


def test_consistent_hash_does_not_make_a_conflicting_payload_valid(payment):
    deliver(payment)
    altered = {**payment[-1], 'amount':151}
    raw = json.dumps(altered, separators=(',', ':')).encode()
    with payment[0][0].state.accounts.Session.begin() as db:
        event = db.get(Event, 'review-event')
        event.raw_body = raw
        event.sha256 = hashlib.sha256(raw).hexdigest()
    response = post_preview(payment, [RECORD])
    assert response.json()['classification'] == 'PROVIDER_EVIDENCE_INVALID'
    assert response.json()['bank_payment_confirmed'] is False


def test_duplicate_provider_reports_with_identical_evidence_are_not_extra_bank_credits(payment):
    deliver(payment)
    deliver(payment, 'same-transaction-second-event')
    response = post_preview(payment, [RECORD])
    assert response.json()['classification'] == 'MATCH_CANDIDATE_UNVERIFIED'
    assert response.json()['independent_source_verified'] is False


def test_provider_event_limit_fails_closed(payment):
    deliver(payment)
    with payment[0][0].state.accounts.Session.begin() as db:
        original = db.get(Event, 'review-event')
        for i in range(100):
            db.add(Event(id=f'extra-event-{i}', raw_body=original.raw_body, sha256=original.sha256,
                         intent_id=original.intent_id, processed_at=original.processed_at))
    response = post_preview(payment, [RECORD])
    assert response.json()['classification'] == 'PROVIDER_EVIDENCE_LIMIT_EXCEEDED'
    assert response.json()['bank_payment_confirmed'] is False


def test_caller_cannot_assert_verified_or_settled_flags(payment):
    deliver(payment)
    env, _, csrf, intent_id, _ = payment
    response = env[1].post(f'/v1/checkout/qr/{intent_id}/reconciliation-preview',
        headers={'x-csrf-token':csrf}, json={'bank_records':[RECORD], 'bank_payment_confirmed':True})
    assert response.status_code == 422
    assert response.headers['cache-control'] == 'no-store'
