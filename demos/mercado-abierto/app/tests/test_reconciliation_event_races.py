"""Do not return a preview computed from an obsolete provider event set."""

import hashlib

import pytest

from rio_pey_codi.models import Event
from test_platform import signed_webhook
from test_reconciliation_preview import RECORD, deliver, payment, post_preview  # noqa: F401


@pytest.mark.parametrize('change', ['new_signed_conflict', 'raw_body', 'signature'])
def test_provider_evidence_changes_during_preview_require_retry(payment, monkeypatch, change):
    deliver(payment)
    app, client = payment[0]
    original = app.state.payments.reconciliation_preview

    def change_after_assessment(*args):
        result = original(*args)
        if change == 'new_signed_conflict':
            payload = {**payment[-1], 'metadata':{**payment[-1]['metadata'],
                                                   'trackingKey':'different-synthetic-tracking'}}
            received = signed_webhook(client, payload, 'later-synthetic-event')
            assert received.status_code == 200
            assert received.json()['outcome'] == 'DUPLICATE_TRANSACTION'
        else:
            with app.state.accounts.Session.begin() as db:
                event = db.get(Event, 'review-event')
                if change == 'raw_body':
                    event.raw_body = b'{"tampered":true}'
                    event.sha256 = hashlib.sha256(event.raw_body).hexdigest()
                else:
                    event.signature = None
        return result

    monkeypatch.setattr(app.state.payments, 'reconciliation_preview', change_after_assessment)
    response = post_preview(payment, [RECORD])
    assert response.status_code == 409
    assert 'MATCH_CANDIDATE' not in response.text
    monkeypatch.setattr(app.state.payments, 'reconciliation_preview', original)
    retry = post_preview(payment, [RECORD])
    assert retry.status_code == 200
    assert retry.json()['classification'] == {
        'new_signed_conflict':'PROVIDER_EVIDENCE_CONFLICT',
        'raw_body':'PROVIDER_EVIDENCE_INVALID',
        'signature':'PROVIDER_SIGNATURE_INVALID',
    }[change]
    assert retry.json()['bank_payment_confirmed'] is False


def test_preview_compares_exact_assessed_snapshot_even_if_evidence_is_restored(payment, monkeypatch):
    deliver(payment)
    app, _client = payment[0]
    with app.state.accounts.Session.begin() as db:
        event = db.get(Event, 'review-event')
        signature = event.signature
        event.signature = None
    original = app.state.payments.reconciliation_preview

    def temporarily_restore_signature(*args):
        with app.state.accounts.Session.begin() as db:
            db.get(Event, 'review-event').signature = signature
        result = original(*args)
        with app.state.accounts.Session.begin() as db:
            db.get(Event, 'review-event').signature = None
        return result

    monkeypatch.setattr(app.state.payments, 'reconciliation_preview', temporarily_restore_signature)
    response = post_preview(payment, [RECORD])
    assert response.status_code == 409
    assert 'MATCH_CANDIDATE' not in response.text
    monkeypatch.setattr(app.state.payments, 'reconciliation_preview', original)
    retry = post_preview(payment, [RECORD])
    assert retry.status_code == 200
    assert retry.json()['classification'] == 'PROVIDER_SIGNATURE_INVALID'
    assert retry.json()['bank_payment_confirmed'] is False
