"""Privileged merchant writes must recheck session state inside their transaction."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from rio_pey_codi.models import Beneficiary, Membership, MembershipChange, Merchant, SessionRow, User
from test_platform import env, signup, verified_login


def prepare(env, operation):
    merchant = signup(env)['merchant_id']
    csrf = verified_login(env)
    target_id = None
    if operation == 'role':
        target = (env[0], TestClient(env[0]))
        signup(target, 'target-admin-race@example.com')
        verified_login(target, 'target-admin-race@example.com')
        with env[0].state.accounts.Session() as db:
            target_id = db.scalar(select(User.id).where(User.email == 'target-admin-race@example.com'))
    return merchant, csrf, target_id


def write(env, operation, merchant, csrf):
    headers = {'x-csrf-token':csrf}
    if operation == 'merchant':
        return env[1].post('/v1/merchants', headers=headers, json={'name':'Second synthetic merchant'})
    if operation == 'role':
        return env[1].put(f'/v1/merchants/{merchant}/members', headers=headers,
                          json={'email':'target-admin-race@example.com', 'role':'admin'})
    return env[1].post(f'/v1/merchants/{merchant}/beneficiary-onboarding', headers=headers)


def assert_no_write(env, operation, merchant, target_id):
    with env[0].state.accounts.Session() as db:
        if operation == 'merchant':
            assert db.scalar(select(func.count()).select_from(Merchant)) == 1
        elif operation == 'role':
            assert db.get(Membership, {'merchant_id':merchant, 'user_id':target_id}) is None
            assert db.scalar(select(func.count()).select_from(MembershipChange)) == 0
        else:
            assert db.get(Beneficiary, merchant) is None


@pytest.mark.parametrize('operation', ['merchant', 'role', 'onboarding'])
@pytest.mark.parametrize(('change', 'status'), [('revoked', 401), ('deleted', 401),
                                                 ('csrf_changed', 403), ('unverified', 401)])
def test_privileged_writes_recheck_session_after_initial_auth(env, monkeypatch, operation, change, status):
    merchant, csrf, target_id = prepare(env, operation)
    svc = env[0].state.accounts
    original = svc.session

    def changed_after_auth(request, csrf=False):
        principal = original(request, csrf=csrf)
        with svc.Session.begin() as db:
            row = db.get(SessionRow, principal['session_hash'])
            if change == 'revoked':
                row.revoked_at = 1
            elif change == 'deleted':
                db.delete(row)
            elif change == 'csrf_changed':
                row.csrf_hash = 'a' * 64 if row.csrf_hash != 'a' * 64 else 'b' * 64
            else:
                db.get(User, principal['id']).verified_at = None
        return principal

    monkeypatch.setattr(svc, 'session', changed_after_auth)
    response = write(env, operation, merchant, csrf)
    assert response.status_code == status
    assert_no_write(env, operation, merchant, target_id)


@pytest.mark.parametrize(('change', 'status'), [('demoted', 403), ('removed', 404)])
@pytest.mark.parametrize('operation', ['role', 'onboarding'])
def test_owner_membership_rechecked_before_privileged_write(env, monkeypatch, operation, change, status):
    merchant, csrf, target_id = prepare(env, operation)
    svc = env[0].state.accounts
    original = svc.session

    def changed_after_auth(request, csrf=False):
        principal = original(request, csrf=csrf)
        with svc.Session.begin() as db:
            member = db.get(Membership, {'merchant_id':merchant, 'user_id':principal['id']})
            if change == 'demoted':
                member.role = 'admin'
            else:
                db.delete(member)
        return principal

    monkeypatch.setattr(svc, 'session', changed_after_auth)
    assert write(env, operation, merchant, csrf).status_code == status
    assert_no_write(env, operation, merchant, target_id)
