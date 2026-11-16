"""Owner declarations are durable records, not verified pey account state."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

from rio_pey_codi.identity import sha
from rio_pey_codi.models import Beneficiary, Membership, SessionRow
from rio_pey_codi.platform import create_platform
from test_platform import env, signup, verified_login

ACCOUNT = '01JBAVWE4NS5TGXHWGMX3KH23Q'  # published documentation example only
VERIFIED = {'claim': 'OWNER_REPORTED_VERIFIED', 'provider_account_id': ACCOUNT}
WITHDRAWN = {'claim': 'OWNER_WITHDREW_REPORT', 'provider_account_id': None}


def path(merchant):
    return f'/v1/merchants/{merchant}/beneficiary-claims'


def post(client, merchant, csrf, key, body=VERIFIED):
    return client.post(path(merchant), headers={'x-csrf-token': csrf, 'idempotency-key': key}, json=body)


def test_owner_claim_persists_without_activation_and_restarts(env):
    merchant = signup(env)['merchant_id']
    csrf = verified_login(env)
    made = post(env[1], merchant, csrf, 'a' * 32)
    assert made.status_code == 201, made.text
    item = made.json()['claim']
    assert item['sequence'] == 1 and item['provider_account_id'] == ACCOUNT
    assert made.json()['provider_status_verified'] is False
    assert made.json()['bank_payment_confirmed'] is False
    assert made.json()['live_payments_enabled'] is False
    assert env[1].get(path(merchant)).json()['claims'] == [item]
    with env[0].state.accounts.Session() as db:
        assert db.get(Beneficiary, merchant) is None
    reopened = create_platform(env[0].state.settings)
    client = TestClient(reopened, cookies=env[1].cookies)
    assert client.get(path(merchant)).json()['claims'] == [item]


def test_owner_only_and_csrf_and_tenant_isolation(env):
    merchant = signup(env)['merchant_id']
    csrf = verified_login(env)
    assert post(env[1], merchant, 'invalid', 'a' * 32).status_code == 403
    assert env[1].post(path(merchant), json=VERIFIED).status_code == 403
    outsider = (env[0], TestClient(env[0]))
    other_merchant = signup(outsider, 'employee@example.com')['merchant_id']
    outsider_csrf = verified_login(outsider, 'employee@example.com')
    assert post(outsider[1], merchant, outsider_csrf, 'b' * 32).status_code == 404
    assert outsider[1].get(path(merchant)).status_code == 404
    assert env[1].get(path(other_merchant)).status_code == 404
    member = {'email':'employee@example.com', 'role':'admin'}
    assert env[1].put(f'/v1/merchants/{merchant}/members', headers={'x-csrf-token':csrf}, json=member).status_code == 200
    assert post(outsider[1], merchant, outsider_csrf, 'c' * 32).status_code == 403
    assert outsider[1].get(path(merchant)).status_code == 403


def test_correction_retry_validation_and_database_immutability(env):
    merchant = signup(env)['merchant_id']
    csrf = verified_login(env)
    created = post(env[1], merchant, csrf, 'a' * 32)
    assert created.status_code == 201
    assert post(env[1], merchant, csrf, 'a' * 32).json()['claim'] == created.json()['claim']
    assert post(env[1], merchant, csrf, 'a' * 32, WITHDRAWN).status_code == 409
    corrected = post(env[1], merchant, csrf, 'b' * 32, WITHDRAWN)
    assert corrected.status_code == 201 and corrected.json()['claim']['sequence'] == 2
    claims = env[1].get(path(merchant)).json()['claims']
    assert [c['claim'] for c in claims] == ['OWNER_WITHDREW_REPORT', 'OWNER_REPORTED_VERIFIED']
    assert post(env[1], merchant, csrf, 'c' * 32, {**VERIFIED, 'provider_account_id':'bad'}).status_code == 422
    assert post(env[1], merchant, csrf, 'c' * 32, {**WITHDRAWN, 'provider_account_id':ACCOUNT}).status_code == 422
    invalid = post(env[1], merchant, csrf, 'c' * 32, {**VERIFIED, 'api_key':'never-store'})
    assert invalid.status_code == 422 and 'never-store' not in invalid.text
    assert post(env[1], merchant, csrf, 'invalid').status_code == 422
    with pytest.raises(DatabaseError), env[0].state.accounts.Session.begin() as db:
        db.execute(text('UPDATE beneficiary_claims SET sequence=3'))
    with pytest.raises(DatabaseError), env[0].state.accounts.Session.begin() as db:
        db.execute(text('DELETE FROM beneficiary_claims'))


def test_revoked_session_between_http_auth_and_commit_denied(env, monkeypatch):
    merchant = signup(env)['merchant_id']
    csrf = verified_login(env)
    svc = env[0].state.accounts
    original = svc.session
    def revoke_after_initial_auth(request, csrf=False):
        value = original(request, csrf=csrf)
        with svc.Session.begin() as db:
            db.get(SessionRow, value['session_hash']).revoked_at = 1
        return value
    monkeypatch.setattr(svc, 'session', revoke_after_initial_auth)
    assert post(env[1], merchant, csrf, 'a' * 32).status_code == 401
    with svc.Session() as db:
        assert db.execute(text('SELECT COUNT(*) FROM beneficiary_claims')).scalar_one() == 0


def test_owner_role_changed_between_http_auth_and_commit_denied(env, monkeypatch):
    merchant = signup(env)['merchant_id']
    csrf = verified_login(env)
    svc = env[0].state.accounts
    original = svc.session
    def demote_after_initial_auth(request, csrf=False):
        principal = original(request, csrf=csrf)
        with svc.Session.begin() as db:
            db.get(Membership, {'merchant_id':merchant, 'user_id':principal['id']}).role = 'admin'
        return principal
    monkeypatch.setattr(svc, 'session', demote_after_initial_auth)
    assert post(env[1], merchant, csrf, 'a' * 32).status_code == 403
    with svc.Session() as db:
        assert db.execute(text('SELECT COUNT(*) FROM beneficiary_claims')).scalar_one() == 0


def test_history_read_serializes_against_session_revocation(env, monkeypatch):
    merchant = signup(env)['merchant_id']
    csrf = verified_login(env)
    assert post(env[1], merchant, csrf, 'a' * 32).status_code == 201
    service = env[0].state.accounts
    cookie = env[1].cookies.get('rio_sid')
    ready, release, writing, written = Event(), Event(), Event(), Event()
    original = service._claim_access
    def paused(db, principal, merchant_id, *, lock):
        original(db, principal, merchant_id, lock=lock)
        ready.set()
        if not release.wait(timeout=5):
            raise RuntimeError('test did not release the reader')
    monkeypatch.setattr(service, '_claim_access', paused)
    def read():
        return TestClient(env[0], cookies={'rio_sid':cookie}).get(path(merchant))
    def revoke():
        writing.set()
        with service.Session.begin() as db:
            db.get(SessionRow, sha(cookie)).revoked_at = 1
        written.set()
    with ThreadPoolExecutor(max_workers=2) as pool:
        reader = pool.submit(read)
        assert ready.wait(5)
        writer = pool.submit(revoke)
        assert writing.wait(5)
        blocked = not written.wait(.3)
        release.set()
        assert reader.result(timeout=5).status_code == 200
        writer.result(timeout=5)
    assert blocked, 'revocation completed while the authorized history read was still in flight'
    assert TestClient(env[0], cookies={'rio_sid':cookie}).get(path(merchant)).status_code == 401


def test_concurrent_identical_retries_create_one_record(env):
    merchant = signup(env)['merchant_id']
    csrf = verified_login(env)
    cookies = dict(env[1].cookies)
    def write(_):
        return post(TestClient(env[0], cookies=cookies), merchant, csrf, 'a' * 32)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(write, range(6)))
    assert all(r.status_code == 201 for r in results)
    assert len({r.json()['claim']['id'] for r in results}) == 1
    assert len(env[1].get(path(merchant)).json()['claims']) == 1


def test_concurrent_distinct_claims_have_monotone_sequences(env):
    merchant = signup(env)['merchant_id']
    csrf = verified_login(env)
    cookies = dict(env[1].cookies)
    def write(key):
        return post(TestClient(env[0], cookies=cookies), merchant, csrf, key * 32)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(write, 'abcd'))
    assert all(r.status_code == 201 for r in results)
    assert sorted(r.json()['claim']['sequence'] for r in results) == [1, 2, 3, 4]


def test_unidentified_report_can_be_recorded_and_bad_json_is_not_echoed(env):
    merchant = signup(env)['merchant_id']
    csrf = verified_login(env)
    item = post(env[1], merchant, csrf, 'd' * 32, {'claim':'OWNER_REPORTED_VERIFIED'})
    assert item.status_code == 201 and item.json()['claim']['provider_account_id'] is None
    headers = {'x-csrf-token':csrf, 'idempotency-key':'e' * 32, 'content-type':'application/json'}
    duplicate = env[1].post(path(merchant), headers=headers,
                            content=b'{"claim":"OWNER_REPORTED_VERIFIED","claim":"secret-data"}')
    assert duplicate.status_code == 422 and 'secret-data' not in duplicate.text
    assert env[1].post(path(merchant), headers=headers, content=b'x' * 2049).status_code == 413
