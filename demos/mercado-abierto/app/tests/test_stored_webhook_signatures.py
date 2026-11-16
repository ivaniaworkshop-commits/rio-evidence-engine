"""The stored event hash alone cannot authenticate a reconciliation candidate."""
import base64
import hashlib
import json
import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from rio_pey_codi.models import Event, PendingEvent
from rio_pey_codi.platform import Settings, create_platform
from rio_pey_codi.signatures import make_signature
from test_platform import SECRET, signed_webhook
from test_reconciliation_preview import RECORD, deliver, payment, post_preview  # noqa: F401


@pytest.mark.parametrize('invalid', ['', 'a' * 65, 'space ref', 'whsec_not-a-reference'])
def test_secret_references_must_be_bounded_nonsecret_identifiers(invalid):
    with pytest.raises(ValueError, match='non-secret webhook signing key reference'):
        Settings(webhook_key_ref=invalid).validate()


def test_staging_requires_explicit_key_reference():
    settings = Settings(env='staging', database_url='postgresql://example.invalid/db', auto_create=False,
                        email_mode='smtp', public_url='https://example.invalid', origin='https://example.invalid',
                        smtp_host='example.invalid', smtp_sender='synthetic@example.invalid',
                        smtp_user='synthetic', smtp_password='synthetic')
    with pytest.raises(ValueError, match='explicit webhook signing key reference'):
        settings.validate()
    replace(settings, webhook_key_ref='staging-v1').validate()


def test_recomputed_hash_does_not_authenticate_altered_provider_payload(payment):
    deliver(payment)
    forged = {**payment[-1], 'metadata':{**payment[-1]['metadata'], 'trackingKey':'forged-tracking'}}
    raw = json.dumps(forged, separators=(',', ':')).encode()
    with payment[0][0].state.accounts.Session.begin() as db:
        event = db.get(Event, 'review-event')
        event.raw_body = raw
        event.sha256 = hashlib.sha256(raw).hexdigest()
    result = post_preview(payment, [{**RECORD, 'tracking_key':'forged-tracking'}]).json()
    assert result['classification'] == 'PROVIDER_SIGNATURE_INVALID'
    assert result['provider_signature_reverified'] is False
    assert result['bank_payment_confirmed'] is False


def test_signature_is_reverified_and_assessment_survives_restart(payment):
    deliver(payment)
    env, _, csrf, intent_id, _ = payment
    preview = post_preview(payment, [RECORD]).json()
    assert preview['classification'] == 'MATCH_CANDIDATE_UNVERIFIED'
    assert preview['signature_assessment'] == 'VERIFIED' and preview['provider_signature_reverified'] is True
    assert preview['beneficiary_binding_verified'] is False and preview['bank_payment_confirmed'] is False
    path = f'/v1/checkout/qr/{intent_id}/reconciliation-reviews'
    saved = env[1].post(path, headers={'x-csrf-token':csrf,'idempotency-key':'a' * 32},
                        json={'bank_records':[RECORD]})
    assert saved.status_code == 201 and saved.json()['provider_signature_reverified'] is True
    assert saved.json()['review']['signature_assessment_at_review'] == 'VERIFIED'
    with env[0].state.accounts.Session() as db:
        event = db.get(Event, 'review-event')
        assert event.signature and event.signature_key_ref == 'local-v1'
        assert SECRET not in str(event.signature)
        signature = event.signature
    assert signature not in saved.text and SECRET not in saved.text
    reopened = create_platform(env[0].state.settings)
    client = TestClient(reopened, cookies=env[1].cookies)
    history = client.get(path).json()
    assert history['provider_signature_reverified'] is False  # history read does not reverify
    assert history['reviews'][0]['signature_assessment_at_review'] == 'VERIFIED'
    assert signature not in json.dumps(history) and SECRET not in json.dumps(history)
    again = post_preview(payment, [RECORD], client=client).json()
    assert again['signature_assessment'] == 'VERIFIED'


def test_old_events_without_signature_are_never_promoted(payment):
    deliver(payment)
    with payment[0][0].state.accounts.Session.begin() as db:
        event = db.get(Event, 'review-event')
        event.signature = event.signature_timestamp = event.signature_received_at = event.signature_key_ref = None
    result = post_preview(payment, [RECORD]).json()
    assert result['classification'] == 'PROVIDER_SIGNATURE_NOT_RECORDED'
    assert result['signature_assessment'] == 'NOT_RECORDED' and not result['provider_signature_reverified']


def test_partial_signature_evidence_is_invalid(payment):
    deliver(payment)
    with payment[0][0].state.accounts.Session.begin() as db:
        db.get(Event, 'review-event').signature = None
    result = post_preview(payment, [RECORD]).json()
    assert result['classification'] == 'PROVIDER_SIGNATURE_INVALID'
    assert result['signature_assessment'] == 'INVALID'


def test_rotated_key_reference_and_wrong_secret_fail_closed(payment):
    deliver(payment)
    env = payment[0]
    settings = env[0].state.settings
    newer = create_platform(replace(settings, webhook_key_ref='key-v2'))
    result = post_preview(payment, [RECORD], client=TestClient(newer, cookies=env[1].cookies)).json()
    assert result['classification'] == 'PROVIDER_SIGNATURE_KEY_UNAVAILABLE'
    assert result['signature_assessment'] == 'KEY_UNAVAILABLE'
    wrong_secret = 'whsec_' + base64.b64encode(b'synthetic-wrong-signing-key-32-bytes').decode()
    wrong = create_platform(replace(settings, webhook_secret=wrong_secret))
    result = post_preview(payment, [RECORD], client=TestClient(wrong, cookies=env[1].cookies)).json()
    assert result['classification'] == 'PROVIDER_SIGNATURE_INVALID'
    assert result['signature_assessment'] == 'INVALID'


def test_old_but_fresh_when_received_still_reverifies(payment, monkeypatch):
    past = int(time.time()) - 7200
    with monkeypatch.context() as context:
        context.setattr(time, 'time', lambda: past)
        deliver(payment)
    result = post_preview(payment, [RECORD]).json()
    assert result['signature_assessment'] == 'VERIFIED'
    assert result['classification'] == 'MATCH_CANDIDATE_UNVERIFIED'


def test_freshness_rejected_at_ingress_does_not_persist_event(payment):
    env, _, _, _, payload = payment
    raw = json.dumps(payload, separators=(',', ':')).encode()
    old = int(time.time()) - 7200
    event_id = 'stale-event'
    response = env[1].post('/v1/webhooks/pey', content=raw, headers={
        'webhook-id':event_id, 'webhook-timestamp':str(old),
        'webhook-signature':make_signature(SECRET,event_id,old,raw),'content-type':'application/json'})
    assert response.status_code == 401
    with env[0].state.accounts.Session() as db:
        assert db.get(Event, event_id) is None and db.get(PendingEvent, event_id) is None


def test_pending_event_keeps_signature_after_qr_link(payment):
    env, merchant, _, _, payload = payment
    repo = env[0].state.payments
    row, created = repo.reserve(merchant,'pending-signature',15000,'Pan','pending-signature',600)
    assert created
    payload = {**payload, 'codiQrId':'pending-qr', 'numRef':'pending-signature', 'transactionId':'pending-tx'}
    assert signed_webhook(env[1], payload, 'pending-event').json()['outcome'] == 'PENDING_LINKAGE'
    with env[0].state.accounts.Session() as db:
        pending = db.get(PendingEvent, 'pending-event')
        expected = (pending.signature, pending.signature_timestamp, pending.signature_received_at, pending.signature_key_ref)
        assert all(value is not None for value in expected)
    repo.qr_issued(row.id, 'pending-qr', 'nonpayable')
    with env[0].state.accounts.Session() as db:
        event = db.get(Event, 'pending-event')
        assert (event.signature, event.signature_timestamp, event.signature_received_at, event.signature_key_ref) == expected
        assert db.get(PendingEvent, 'pending-event') is None
    second = (env, merchant, payment[2], row.id, payload)
    assert post_preview(second, [RECORD]).json()['signature_assessment'] == 'VERIFIED'


def test_duplicate_delivery_preserves_original_signature_evidence(payment):
    deliver(payment)
    with payment[0][0].state.accounts.Session() as db:
        event = db.get(Event, 'review-event')
        first = (event.signature, event.signature_timestamp, event.signature_received_at, event.signature_key_ref)
    deliver(payment)
    with payment[0][0].state.accounts.Session() as db:
        event = db.get(Event, 'review-event')
        assert (event.signature, event.signature_timestamp, event.signature_received_at, event.signature_key_ref) == first


def test_one_legacy_event_cannot_be_masked_by_another_valid_signature(payment):
    deliver(payment, 'review-event')
    deliver(payment, 'second-event')
    with payment[0][0].state.accounts.Session.begin() as db:
        event = db.get(Event, 'second-event')
        event.signature = event.signature_timestamp = event.signature_received_at = event.signature_key_ref = None
    result = post_preview(payment, [RECORD]).json()
    assert result['classification'] == 'PROVIDER_SIGNATURE_NOT_RECORDED'
    assert not result['provider_signature_reverified']


def test_altered_signed_timestamp_is_rejected(payment):
    deliver(payment)
    with payment[0][0].state.accounts.Session.begin() as db:
        db.get(Event, 'review-event').signature_timestamp += 1
    result = post_preview(payment, [RECORD]).json()
    assert result['classification'] == 'PROVIDER_SIGNATURE_INVALID'
    assert not result['provider_signature_reverified']
