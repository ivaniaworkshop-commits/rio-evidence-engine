"""Revoke synthetic session or role while a real review preview is in flight."""
import time

import pytest
from sqlalchemy import func, select

import rio_pey_codi.platform as platform
from rio_pey_codi.identity import sha
from rio_pey_codi.models import Intent, Membership, ReconciliationReview, SessionRow
from test_reconciliation_preview import RECORD, deliver, payment, post_preview  # noqa: F401


@pytest.mark.parametrize('change', ['session', 'role'])
def test_revoked_while_reading_input_never_reaches_provider_review(payment, monkeypatch, change):
    deliver(payment)
    env, merchant, _, _, _ = payment
    app, client = env
    user_id = client.get('/v1/auth/me').json()['id']
    sid = sha(client.cookies.get('rio_sid'))
    original_read = platform._read_bank_review
    calls = []
    original_review = app.state.payments.reconciliation_preview

    async def revoke_during_body(request):
        records = await original_read(request)
        with app.state.accounts.Session.begin() as db:
            if change == 'session':
                db.get(SessionRow, sid).revoked_at = int(time.time())
            else:
                db.get(Membership, {'merchant_id':merchant, 'user_id':user_id}).role = 'cashier'
        return records

    def track(*args):
        calls.append(True)
        return original_review(*args)

    monkeypatch.setattr(platform, '_read_bank_review', revoke_during_body)
    monkeypatch.setattr(app.state.payments, 'reconciliation_preview', track)
    response = post_preview(payment, [RECORD])
    assert response.status_code == (401 if change == 'session' else 403)
    assert calls == []
    assert 'MATCH_CANDIDATE' not in response.text


@pytest.mark.parametrize(('change', 'expected'), [('session', 401), ('role', 403), ('intent', 409)])
def test_changed_authority_or_intent_during_preview_is_not_returned(payment, monkeypatch, change, expected):
    deliver(payment)
    env, merchant, _, intent_id, _ = payment
    app, client = env
    user_id = client.get('/v1/auth/me').json()['id']
    sid = sha(client.cookies.get('rio_sid'))
    original = app.state.payments.reconciliation_preview

    def mutate_after_read(*args):
        result = original(*args)
        with app.state.accounts.Session.begin() as db:
            if change == 'session':
                db.get(SessionRow, sid).revoked_at = int(time.time())
            elif change == 'role':
                db.get(Membership, {'merchant_id':merchant, 'user_id':user_id}).role = 'cashier'
            else:
                db.get(Intent, intent_id).status = 'QR_ISSUED'
        return result

    monkeypatch.setattr(app.state.payments, 'reconciliation_preview', mutate_after_read)
    response = post_preview(payment, [RECORD])
    assert response.status_code == expected
    assert 'MATCH_CANDIDATE' not in response.text
    with app.state.accounts.Session() as db:
        assert db.scalar(select(func.count()).select_from(ReconciliationReview)) == 0
