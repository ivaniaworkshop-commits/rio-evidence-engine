"""Malformed stored identities must not generate a reconciliation candidate."""
import hashlib
import json

from rio_pey_codi.models import Event, Intent
from test_reconciliation_preview import RECORD, deliver, payment, post_preview  # noqa: F401


def test_missing_provider_identifiers_fail_closed_even_with_matching_hash(payment):
    deliver(payment)
    payload = {**payment[-1], 'codiQrId':None, 'transactionId':None}
    raw = json.dumps(payload, separators=(',', ':')).encode()
    with payment[0][0].state.accounts.Session.begin() as db:
        intent = db.get(Intent, payment[3])
        intent.provider_qr_id = None
        intent.transaction_id = None
        event = db.get(Event, 'review-event')
        event.raw_body = raw
        event.sha256 = hashlib.sha256(raw).hexdigest()
    response = post_preview(payment, [RECORD])
    assert response.status_code == 200
    assert response.json()['classification'] == 'PROVIDER_EVIDENCE_INVALID'
    assert response.json()['bank_payment_confirmed'] is False
