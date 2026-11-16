"""Read-only pey account observations; all credentials and responses are synthetic."""
import json
import ssl
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DatabaseError

import rio_pey_codi.platform as platform
import rio_pey_codi.provider_account as provider_account
from rio_pey_codi.identity import sha
from rio_pey_codi.models import Membership, ProviderAccountObservation, SessionRow
from rio_pey_codi.platform import Settings, create_platform
from test_beneficiary_claims import ACCOUNT, VERIFIED, WITHDRAWN, post
from test_platform import SECRET, signup, verified_login

TOKEN = 'synthetic-readonly-token'


class Response:
    def __init__(self, status=200, data=None, content_type='application/json'):
        self.status = status
        self.data = data if data is not None else json.dumps({'id':ACCOUNT, 'codiStatus':'ACTIVE',
                                                              'clabe':'000000000000000000'}).encode()
        self.content_type = content_type
        self.offset = 0
    def getheader(self, name):
        assert name == 'Content-Type'
        return self.content_type
    def read1(self, size):
        part = self.data[self.offset:self.offset + size]
        self.offset += len(part)
        return part


@pytest.mark.parametrize('status', ['ACTIVE', 'PENDING', 'PROCESSING', 'ERROR'])
def test_fixed_https_read_only_lookup_accepts_documented_statuses(monkeypatch, status):
    response = Response(data=json.dumps({'id':ACCOUNT, 'codiStatus':status,
                                         'clabe':'000000000000000000'}).encode())
    calls = []
    class Connection:
        def __init__(self, host, port, *, timeout, context):
            assert (host, port, timeout) == ('api.pey.mx', 443, 5)
            assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
        def request(self, method, path, headers):
            assert method == 'GET' and path == '/bank-account/' + ACCOUNT
            assert headers['Authorization'] == 'Bearer ' + TOKEN
            calls.append(True)
        def getresponse(self): return response
        def close(self): calls.append('closed')
    monkeypatch.setattr(provider_account.http.client, 'HTTPSConnection', Connection)
    assert provider_account.lookup_pey_account(TOKEN, ACCOUNT) == status
    assert calls == [True, 'closed']


@pytest.mark.parametrize('response', [
    Response(status=302), Response(status=401), Response(status=500),
    Response(content_type='text/html'), Response(data=b'x' * 16385),
    Response(data=b'{"id":"bad","codiStatus":"ACTIVE"}'),
    Response(data=('{"id":"' + ACCOUNT + '","codiStatus":"ACTIVE","codiStatus":"PENDING"}').encode()),
    Response(data=('{"id":"' + ACCOUNT + '","codiStatus":"unknown"}').encode()),
])
def test_lookup_rejects_redirects_invalid_or_oversized_responses_without_echo(monkeypatch, response):
    class Connection:
        def __init__(self, *args, **kwargs): pass
        def request(self, *args, **kwargs): pass
        def getresponse(self): return response
        def close(self): pass
    monkeypatch.setattr(provider_account.http.client, 'HTTPSConnection', Connection)
    with pytest.raises(provider_account.ProviderAccountUnavailable) as error:
        provider_account.lookup_pey_account(TOKEN, ACCOUNT)
    assert TOKEN not in str(error.value) and ACCOUNT not in str(error.value)


def test_provider_404_is_ambiguous_and_does_not_assert_ownership(monkeypatch):
    class Connection:
        def __init__(self, *args, **kwargs): pass
        def request(self, *args, **kwargs): pass
        def getresponse(self): return Response(status=404)
        def close(self): pass
    monkeypatch.setattr(provider_account.http.client, 'HTTPSConnection', Connection)
    assert provider_account.lookup_pey_account(TOKEN, ACCOUNT) == 'NOT_FOUND'


def test_slow_provider_body_is_bounded_and_credential_is_not_echoed(monkeypatch):
    class Slow(Response):
        def read1(self, _size): return b'x'
    class Connection:
        def __init__(self, *args, **kwargs): pass
        def request(self, *args, **kwargs): pass
        def getresponse(self): return Slow()
        def close(self): pass
    ticks = iter([0, 1, 11])
    monkeypatch.setattr(provider_account, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(provider_account.http.client, 'HTTPSConnection', Connection)
    with pytest.raises(provider_account.ProviderAccountUnavailable) as error:
        provider_account.lookup_pey_account(TOKEN, ACCOUNT)
    assert TOKEN not in str(error.value)


def test_truncated_http_body_is_not_a_valid_provider_observation(monkeypatch):
    class Truncated(Response):
        length = 12  # A declared Content-Length still has unread bytes at EOF.
    class Connection:
        def __init__(self, *args, **kwargs): pass
        def request(self, *args, **kwargs): pass
        def getresponse(self): return Truncated()
        def close(self): pass
    monkeypatch.setattr(provider_account.http.client, 'HTTPSConnection', Connection)
    with pytest.raises(provider_account.ProviderAccountUnavailable):
        provider_account.lookup_pey_account(TOKEN, ACCOUNT)


@pytest.mark.parametrize('token', ['', 'bad\r\nheader', 'non ascii ñ', 'x' * 513])
def test_bad_token_never_opens_network(monkeypatch, token):
    def forbidden(*args, **kwargs): raise AssertionError('network must not be opened')
    monkeypatch.setattr(provider_account.http.client, 'HTTPSConnection', forbidden)
    with pytest.raises(provider_account.ProviderAccountUnavailable):
        provider_account.lookup_pey_account(token, ACCOUNT)


@pytest.fixture
def configured(tmp_path):
    db = 'sqlite+pysqlite:///' + str(tmp_path / 'provider.sqlite')
    app = create_platform(Settings(database_url=db, webhook_secret=SECRET))
    env = (app, TestClient(app))
    merchant_id = signup(env)['merchant_id']
    csrf = verified_login(env)
    assert post(env[1], merchant_id, csrf, 'a' * 32).status_code == 201
    settings = Settings(database_url=db, webhook_secret=SECRET, account_lookup_enabled=True,
                        account_lookup_merchant_id=merchant_id, account_lookup_key_ref='test_key_1',
                        account_lookup_api_key=TOKEN)
    new_app = create_platform(settings)
    return (new_app, TestClient(new_app, cookies=env[1].cookies)), merchant_id, csrf


def check(env, merchant_id, csrf, key='b' * 32):
    return env[1].post(f'/v1/merchants/{merchant_id}/provider-account-checks',
                       headers={'x-csrf-token':csrf, 'idempotency-key':key})


def test_owner_check_is_durable_minimized_and_never_enables_live(configured, monkeypatch):
    env, merchant, csrf = configured
    calls = []
    def lookup(token, account_id):
        assert token == TOKEN and account_id == ACCOUNT
        calls.append(True)
        return 'ACTIVE'
    monkeypatch.setattr(platform, 'lookup_pey_account', lookup)
    result = check(env, merchant, csrf)
    assert result.status_code == 201
    obs = result.json()['observation']
    assert obs['status'] == 'ACTIVE' and not obs['merchant_ownership_verified']
    assert not obs['bank_payment_confirmed'] and not obs['live_payments_enabled']
    assert TOKEN not in result.text and ACCOUNT not in result.text
    assert check(env, merchant, csrf).status_code == 409 and calls == [True]
    state = env[1].get(f'/v1/merchants/{merchant}/production-readiness')
    assert state.status_code == 200 and state.json()['provider_observation']['id'] == obs['id']
    assert state.json()['production'] == 'BLOCKED' and not state.json()['independent_bank_source_verified']
    assert not state.json()['provider_key_id_bound'] and not state.json()['specific_operation_authorized']
    assert state.json()['provider_observation_matches_current_declaration']
    assert TOKEN not in state.text and ACCOUNT not in state.text
    with env[0].state.accounts.Session() as db:
        rows = list(db.scalars(select(ProviderAccountObservation)))
        assert len(rows) == 1 and rows[0].status == 'ACTIVE'
        assert TOKEN not in repr(rows[0].__dict__) and ACCOUNT not in repr(rows[0].__dict__)
    for sql in ('UPDATE provider_account_observations SET status = :v',
                'DELETE FROM provider_account_observations WHERE status = :v'):
        with pytest.raises(DatabaseError), env[0].state.accounts.Session.begin() as db:
            db.execute(text(sql), {'v':'ACTIVE'})
    restarted = create_platform(env[0].state.settings)
    reader = TestClient(restarted, cookies=env[1].cookies)
    assert reader.get(f'/v1/merchants/{merchant}/production-readiness').json()['provider_observation']['id'] == obs['id']
    assert post(env[1], merchant, csrf, 'c' * 32, WITHDRAWN).status_code == 201
    assert not env[1].get(f'/v1/merchants/{merchant}/production-readiness').json()['provider_observation_matches_current_declaration']


@pytest.mark.parametrize('change,expected', [('session',401), ('role',403), ('claim',409)])
def test_authority_or_claim_change_during_lookup_prevents_record(configured, monkeypatch, change, expected):
    env, merchant, csrf = configured
    app, client = env
    user_id = client.get('/v1/auth/me').json()['id']
    sid = sha(client.cookies.get('rio_sid'))
    def lookup(*_args):
        if change == 'claim':
            assert post(client, merchant, csrf, 'd' * 32, WITHDRAWN).status_code == 201
        else:
            with app.state.accounts.Session.begin() as db:
                if change == 'session': db.get(SessionRow, sid).revoked_at = 1
                else: db.get(Membership, {'merchant_id':merchant, 'user_id':user_id}).role = 'admin'
        return 'ACTIVE'
    monkeypatch.setattr(platform, 'lookup_pey_account', lookup)
    assert check(env, merchant, csrf).status_code == expected
    with app.state.accounts.Session() as db:
        assert db.scalar(select(func.count()).select_from(ProviderAccountObservation)) == 0


def test_feature_off_cross_tenant_and_rejected_inputs_never_call_provider(configured, monkeypatch):
    env, merchant, csrf = configured
    calls = []
    monkeypatch.setattr(platform, 'lookup_pey_account', lambda *_: calls.append(True))
    path = f'/v1/merchants/{merchant}/provider-account-checks'
    assert env[1].post(path, headers={'x-csrf-token':csrf, 'idempotency-key':'b' * 32}, json={'key':'synthetic'}).status_code == 422
    assert check(env, merchant, 'invalid').status_code == 403
    assert check(env, merchant, csrf, 'invalid').status_code == 422
    other = signup((env[0], TestClient(env[0])), 'other@example.com')['merchant_id']
    assert check(env, other, csrf, 'c' * 32).status_code == 404
    assert calls == []
    assert TOKEN not in repr(env[0].state.settings)


def test_disabled_lookup_never_calls_provider(tmp_path, monkeypatch):
    env = (create_platform(Settings(database_url='sqlite+pysqlite:///' + str(tmp_path/'off.sqlite'))), None)
    env = (env[0], TestClient(env[0]))
    merchant = signup(env)['merchant_id']; csrf = verified_login(env)
    monkeypatch.setattr(platform, 'lookup_pey_account', lambda *_: pytest.fail('network called'))
    assert check(env, merchant, csrf).status_code == 503


def test_declared_configuration_cannot_open_live_or_pass_production_gates(configured):
    env, merchant, _csrf = configured
    cfg = env[0].state.settings
    with pytest.raises(ValueError, match='Hosted LIVE requires exclusively merchant-scoped credentials'):
        replace(cfg, mode='LIVE', live_enabled=True, docs_attested=True, amount_attested=True,
                webhook_attested=True, account_active_attested=True, compliance_attested=True,
                migrations_attested=True).validate()
    state = env[1].get(f'/v1/merchants/{merchant}/production-readiness').json()
    assert state['production'] == 'BLOCKED' and state['live_payments_enabled'] is False
    assert set(state['gates'].values()) == {'NOT_VERIFIED', 'NOT_AUTHORIZED'}


def test_failed_or_invalid_provider_result_never_creates_observation(configured, monkeypatch):
    env, merchant, csrf = configured
    for value in ('SPOOFED', None):
        monkeypatch.setattr(platform, 'lookup_pey_account', lambda *_: value)
        assert check(env, merchant, csrf).status_code == 503
    def unavailable(*_): raise provider_account.ProviderAccountUnavailable('Account lookup unavailable')
    monkeypatch.setattr(platform, 'lookup_pey_account', unavailable)
    assert check(env, merchant, csrf).status_code == 503
    with env[0].state.accounts.Session() as db:
        assert db.scalar(select(func.count()).select_from(ProviderAccountObservation)) == 0


def test_lookup_is_scoped_to_one_merchant_even_for_same_owner(configured, monkeypatch):
    env, merchant, csrf = configured
    other = env[1].post('/v1/merchants', headers={'x-csrf-token':csrf}, json={'name':'Otro'}).json()['id']
    assert other != merchant
    assert post(env[1], other, csrf, 'f' * 32).status_code == 201
    monkeypatch.setattr(platform, 'lookup_pey_account', lambda *_: pytest.fail('network called'))
    assert check(env, other, csrf).status_code == 503
    assert not env[1].get(f'/v1/merchants/{other}/production-readiness').json()['account_lookup_configured']


def test_concurrent_same_request_records_at_most_one_observation(configured, monkeypatch):
    env, merchant, csrf = configured
    barrier = threading.Barrier(2)
    def lookup(*_):
        barrier.wait(timeout=5)
        return 'ACTIVE'
    monkeypatch.setattr(platform, 'lookup_pey_account', lookup)
    def submit():
        client = TestClient(env[0], cookies=env[1].cookies)
        return check((env[0], client), merchant, csrf).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(lambda _: submit(), range(2)))
    assert sorted(statuses) == [201, 409]
    with env[0].state.accounts.Session() as db:
        assert db.scalar(select(func.count()).select_from(ProviderAccountObservation)) == 1
