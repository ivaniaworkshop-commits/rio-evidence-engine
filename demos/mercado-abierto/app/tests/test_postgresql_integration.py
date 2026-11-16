"""Integration tests for a disposable local PostgreSQL service.

RIO_TEST_POSTGRES_ADMIN_URL must point to the local postgres maintenance
database with permission to create temporary databases. It is never printed.
"""
import os
import shutil
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy import func, inspect, select, text, update
from sqlalchemy.engine import make_url

from rio_pey_codi.identity import AccountService, EmailConfig, Mailer, Signup
from rio_pey_codi.models import AuthLimit, Event, Intent, Merchant, PendingEvent, SessionRow, User, database
from rio_pey_codi.payments_db import PaymentConflict, PaymentRepository, ReferenceConflict
from rio_pey_codi.platform import Settings, create_platform


def local_admin_url(value):
    url = make_url(value)
    if (url.drivername not in ('postgresql', 'postgresql+psycopg')
            or url.host not in ('localhost', '127.0.0.1', '::1')
            or url.database != 'postgres' or url.query):
        raise ValueError('Tests require a local PostgreSQL maintenance database')
    return url.set(drivername='postgresql')


@pytest.fixture
def temporary_database(monkeypatch):
    value = os.environ.get('RIO_TEST_POSTGRES_ADMIN_URL')
    if not value:
        pytest.skip('RIO_TEST_POSTGRES_ADMIN_URL not configured')
    admin = local_admin_url(value)
    names = []
    engines = []

    def create():
        name = 'rio_test_' + uuid.uuid4().hex
        with psycopg.connect(admin.render_as_string(hide_password=False), autocommit=True) as conn:
            conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        names.append(name)
        return admin.set(database=name)

    def remember(factory):
        engines.append(factory.kw['bind'])
        return factory

    try:
        yield create, remember, admin
    finally:
        for engine in engines:
            engine.dispose()
        if names:
            with psycopg.connect(admin.render_as_string(hide_password=False), autocommit=True) as conn:
                for name in names:
                    conn.execute(
                        'SELECT pg_terminate_backend(pid) FROM pg_stat_activity '
                        'WHERE datname = %s AND pid <> pg_backend_pid()', (name,),
                    )
                    conn.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))


def migrated_database(temporary_database, monkeypatch):
    create, remember, _ = temporary_database
    url = create()
    monkeypatch.setenv('DATABASE_URL', url.render_as_string(hide_password=False))
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    command.upgrade(config, 'head')
    return url, remember(database(url.render_as_string(hide_password=False))), config


def merchant(factory):
    user_id, merchant_id = uuid.uuid4().hex, uuid.uuid4().hex
    with factory.begin() as db:
        db.add(User(id=user_id, email=f'{user_id}@example.com', password_hash='fixture',
                    verified_at=1, created_at=1))
        db.flush()
        db.add(Merchant(id=merchant_id, name='Synthetic', owner_id=user_id, created_at=1))
    return merchant_id


@pytest.mark.parametrize('bad_url', [
    'postgresql://localhost/production',
    'postgresql://example.com/postgres',
    'postgresql://localhost/postgres?host=example.com',
    'sqlite:///postgres',
])
def test_database_guard_rejects_nonlocal_or_unexpected_targets(bad_url):
    with pytest.raises(ValueError):
        local_admin_url(bad_url)


def test_postgresql_migrations_and_transaction_rollback(temporary_database, monkeypatch):
    _, factory, config = migrated_database(temporary_database, monkeypatch)
    command.check(config)
    command.downgrade(config, 'base')
    command.upgrade(config, 'head')
    with pytest.raises(RuntimeError):
        with factory.begin() as db:
            db.add(User(id='a' * 32, email='rollback@example.com', password_hash='fixture', created_at=1))
            db.flush()
            raise RuntimeError('force rollback')
    with factory() as db:
        assert db.get(User, 'a' * 32) is None


def test_postgresql_timeouts_apply_in_each_transaction(temporary_database, monkeypatch):
    _, factory, _ = migrated_database(temporary_database, monkeypatch)
    for _ in range(2):
        with factory.begin() as db:
            values = db.execute(text("SELECT current_setting('statement_timeout'), "
                                     "current_setting('lock_timeout')")).one()
            assert tuple(values) == ('15s', '5s')


def test_public_readiness_tracks_migration_version_tables_and_recovery(temporary_database, monkeypatch):
    create, remember, _ = temporary_database
    url = create().render_as_string(hide_password=False)
    monkeypatch.setenv('DATABASE_URL', url)
    monkeypatch.delenv('VERCEL', raising=False)
    monkeypatch.delenv('VERCEL_ENV', raising=False)
    settings = Settings(env='staging', database_url=url, auto_create=False, email_mode='smtp',
                        smtp_host='smtp.example.invalid', smtp_sender='fixture@example.invalid',
                        smtp_user='fixture', smtp_password='fixture-password',
                        public_url='https://stage.example.invalid', origin='https://stage.example.invalid',
                        webhook_key_ref='stage-key')
    app = create_platform(settings)
    factory = remember(app.state.accounts.Session)
    client = TestClient(app)
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))

    assert client.get('/healthz').status_code == 503  # No migration marker or tables yet.
    command.upgrade(config, 'head')
    ready = client.get('/healthz')
    assert ready.status_code == 200
    assert ready.json()['database_readiness'] == 'SCHEMA_VERSION_AND_COLUMNS_MATCH'
    assert ready.json()['email_delivery_verified'] is False
    assert client.get('/').status_code == 200

    with factory.begin() as db:
        db.execute(text("UPDATE alembic_version SET version_num = '012'"))
    assert client.get('/healthz').status_code == 503
    assert client.post('/v1/auth/signup', json={}).status_code == 503
    with factory.begin() as db:
        db.execute(text("UPDATE alembic_version SET version_num = '013'"))
        db.execute(text('INSERT INTO alembic_version (version_num) VALUES (:version)'), {'version':'other-head'})
    assert client.get('/healthz').status_code == 503
    with factory.begin() as db:
        db.execute(text('DELETE FROM alembic_version WHERE version_num = :version'), {'version':'other-head'})
        db.execute(text('ALTER TABLE users RENAME TO users_unavailable_for_test'))
    assert client.get('/healthz').status_code == 503
    with factory.begin() as db:
        db.execute(text('ALTER TABLE users_unavailable_for_test RENAME TO users'))
    assert client.get('/healthz').status_code == 200
    with factory.begin() as db:
        db.execute(text('ALTER TABLE users RENAME COLUMN password_hash TO unavailable_for_test'))
    assert client.get('/healthz').status_code == 503
    with factory.begin() as db:
        db.execute(text('ALTER TABLE users RENAME COLUMN unavailable_for_test TO password_hash'))
    assert client.get('/healthz').status_code == 200


def test_postgresql_limited_launch_keeps_disabled_paths_write_free(temporary_database, monkeypatch):
    url, factory, _ = migrated_database(temporary_database, monkeypatch)
    monkeypatch.delenv('VERCEL', raising=False)
    monkeypatch.delenv('VERCEL_ENV', raising=False)
    settings = Settings(env='production', mode='DEMO', limited_launch=True,
                        database_url=url.render_as_string(hide_password=False), auto_create=False,
                        email_mode='smtp', public_url='https://example.invalid', origin='https://example.invalid')
    app = create_platform(settings)
    client = TestClient(app, base_url='https://example.invalid')
    response = client.get('/healthz')
    assert response.status_code == 200
    assert response.json()['database_readiness'] == 'SCHEMA_VERSION_AND_COLUMNS_MATCH'
    assert response.json()['launch_mode'] == 'LIMITED'
    assert client.get('/').status_code == 200
    assert client.post('/v1/auth/signup', json={
        'email': 'synthetic@example.org', 'password': 'synthetic-password-123', 'business_name': 'Synthetic',
    }).status_code == 503
    assert client.post('/v1/webhooks/pey', json={'synthetic': True}).status_code == 503
    assert client.post('/v1/checkout/qr', json={
        'merchant_id': 'a' * 32, 'order_id': 'synthetic', 'numref': '1', 'concept': 'Synthetic',
        'amount_minor': 100, 'expiration_s': 600,
    }).status_code == 503
    with factory() as db:
        for model in (User, Intent, Event, AuthLimit):
            assert db.scalar(select(func.count()).select_from(model)) == 0
    app.state.accounts.Session.kw['bind'].dispose()


@pytest.mark.parametrize('operation', ['merchant', 'role', 'onboarding'])
def test_postgresql_privileged_write_serializes_with_session_revocation(temporary_database, monkeypatch, operation):
    from rio_pey_codi.identity import sha

    url, factory, _ = migrated_database(temporary_database, monkeypatch)
    app = create_platform(Settings(database_url=url.render_as_string(hide_password=False), auto_create=False))
    owner = TestClient(app)

    def register(client, email):
        password = 'synthetic-password-123'
        response = client.post('/v1/auth/signup', json={'email':email, 'password':password,
                                                        'business_name':'Synthetic'})
        assert response.status_code == 201
        token = next(item['token'] for item in app.state.mailer.outbox if item['email'] == email)
        assert client.post('/v1/auth/verify-email', json={'token':token}).status_code == 200
        login = client.post('/v1/auth/login', json={'email':email, 'password':password})
        assert login.status_code == 200
        return response.json()['merchant_id'], login.json()['csrf_token']

    merchant, csrf = register(owner, 'lock-owner@example.com')
    if operation == 'role':
        register(TestClient(app), 'lock-target@example.com')
    cookie = owner.cookies.get('rio_sid')
    entered, release, writer_started, writer_finished = (threading.Event() for _ in range(4))
    writer_pid = []
    original = AccountService._session_access

    def paused(db, principal, *, lock):
        original(db, principal, lock=lock)
        entered.set()
        if not release.wait(timeout=10):
            raise RuntimeError('test did not release the authorized writer')

    monkeypatch.setattr(AccountService, '_session_access', staticmethod(paused))

    def privileged_write():
        headers = {'x-csrf-token':csrf}
        if operation == 'merchant':
            return owner.post('/v1/merchants', headers=headers, json={'name':'Concurrent synthetic'})
        if operation == 'role':
            return owner.put(f'/v1/merchants/{merchant}/members', headers=headers,
                             json={'email':'lock-target@example.com', 'role':'admin'})
        return owner.post(f'/v1/merchants/{merchant}/beneficiary-onboarding', headers=headers)

    def revoke():
        with factory.begin() as db:
            writer_pid.append(db.scalar(text('SELECT pg_backend_pid()')))
            writer_started.set()
            db.execute(update(SessionRow).where(SessionRow.token_hash == sha(cookie)).values(revoked_at=1))
        writer_finished.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(privileged_write)
        try:
            assert entered.wait(5)
            revocation = pool.submit(revoke)
            assert writer_started.wait(5)
            blocked = False
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if revocation.done():
                    revocation.result()
                    break
                with factory() as db:
                    blockers = db.scalar(text('SELECT pg_blocking_pids(:pid)'), {'pid':writer_pid[0]})
                if blockers:
                    blocked = True
                    break
                time.sleep(.05)
            assert blocked and not writer_finished.is_set()
        finally:
            release.set()
        response = pending.result(timeout=10)
        revocation.result(timeout=10)
    assert response.status_code == (201 if operation == 'merchant' else 200)
    assert writer_finished.is_set()
    assert owner.get('/v1/auth/me').status_code == 401
    app.state.accounts.Session.kw['bind'].dispose()


def test_postgresql_concurrent_order_reservation(temporary_database, monkeypatch):
    url, factory, _ = migrated_database(temporary_database, monkeypatch)
    merchant_id = merchant(factory)
    repo = PaymentRepository(factory)
    barrier = threading.Barrier(8)

    def reserve():
        barrier.wait(timeout=10)
        row, created = repo.reserve(merchant_id, 'same-order', 123, 'Demo', '123', 600)
        return row.id, created

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: reserve(), range(8)))
    assert len({row_id for row_id, _ in results}) == 1
    assert sum(created for _, created in results) == 1
    with pytest.raises(PaymentConflict):
        repo.reserve(merchant_id, 'same-order', 124, 'Demo', '123', 600)

    reference_barrier = threading.Barrier(2)

    def reserve_reference(order):
        reference_barrier.wait(timeout=10)
        try:
            repo.reserve(merchant_id, order, 123, 'Demo', '456', 600)
            return 'created'
        except ReferenceConflict:
            return 'reference-conflict'

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(reserve_reference, ['other-a', 'other-b']))
    assert sorted(outcomes) == ['created', 'reference-conflict']
    factory.kw['bind'].dispose()
    reopened = database(url.render_as_string(hide_password=False))
    try:
        with reopened() as db:
            assert db.scalar(select(func.count()).select_from(Intent)) == 2
            assert db.get(Intent, results[0][0]).amount_minor == 123
    finally:
        reopened.kw['bind'].dispose()


def test_postgresql_unresolved_queue_is_indexed_and_survives_reconnect(temporary_database, monkeypatch):
    url, factory, _ = migrated_database(temporary_database, monkeypatch)
    first, second = merchant(factory), merchant(factory)
    repo = PaymentRepository(factory)
    identities = []
    for i in range(4):
        row, created = repo.reserve(first, f'old-{i}', 100 + i, 'Synthetic', f'ref-{i}', 600)
        assert created
        repo.uncertain(row.id)
        identities.append(row.id)
    other, _ = repo.reserve(second, 'other', 100, 'Other', 'other', 600)
    repo.uncertain(other.id)
    with factory.begin() as db:
        for ident in identities + [other.id]:
            db.get(Intent, ident).created_at = 1700000000
    assert any(index['name'] == 'idx_payment_intents_recovery'
               for index in inspect(factory.kw['bind']).get_indexes('payment_intents'))
    factory.kw['bind'].dispose()
    reopened = database(url.render_as_string(hide_password=False))
    try:
        resumed = PaymentRepository(reopened)
        page1, cursor = resumed.unresolved_page(first, 2)
        page2, last = resumed.unresolved_page(first, 2, (cursor['created_at'], cursor['id']))
        assert [row['id'] for row in page1 + page2] == sorted(identities)
        assert last is None
        assert all(row['merchant_id'] == first and row['bank_payment_confirmed'] is False
                   for row in page1 + page2)
    finally:
        reopened.kw['bind'].dispose()


def test_postgresql_event_linkage_race_and_replay(temporary_database, monkeypatch):
    _, factory, _ = migrated_database(temporary_database, monkeypatch)
    merchant_id = merchant(factory)
    repo = PaymentRepository(factory)
    row, _ = repo.reserve(merchant_id, 'event-order', 123, 'Demo', '456', 600)
    barrier = threading.Barrier(2)
    body = b'{"synthetic":true}'

    def issue():
        barrier.wait(timeout=10)
        repo.qr_issued(row.id, 'fixture-qr', 'synthetic')

    def event():
        barrier.wait(timeout=10)
        return repo.confirm_event('fixture-event', body, 'fixture-qr', 123, '456', 'fixture-tx')

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(issue), pool.submit(event)
        first.result(timeout=20)
        second.result(timeout=20)
    assert repo.confirm_event('fixture-event', body, 'fixture-qr', 123, '456', 'fixture-tx')['outcome'] == 'DUPLICATE_EVENT'
    with pytest.raises(PaymentConflict):
        repo.confirm_event('fixture-event', b'changed', 'fixture-qr', 123, '456', 'fixture-tx')
    with factory() as db:
        assert db.get(Intent, row.id).status == 'PROVIDER_REPORTED'
        assert db.get(Event, 'fixture-event').raw_body == body
        assert db.get(PendingEvent, 'fixture-event') is None


def test_postgresql_uncertain_order_survives_app_restart(temporary_database, monkeypatch):
    class TimeoutProvider:
        calls = 0

        def create_qr(self, **_kwargs):
            self.calls += 1
            raise TimeoutError('synthetic timeout')

    url, _factory, _ = migrated_database(temporary_database, monkeypatch)
    settings = Settings(database_url=url.render_as_string(hide_password=False), auto_create=False)
    provider = TimeoutProvider()
    app = create_platform(settings, provider=provider)
    client = TestClient(app)
    credentials = {'email':'restart-checkout@example.com', 'password':'synthetic-password-123'}
    created = client.post('/v1/auth/signup', json={**credentials, 'business_name':'Synthetic'})
    assert created.status_code == 201
    merchant_id = created.json()['merchant_id']
    token = app.state.mailer.outbox[0]['token']
    assert client.post('/v1/auth/verify-email', json={'token':token}).status_code == 200
    login = client.post('/v1/auth/login', json=credentials)
    csrf = login.json()['csrf_token']
    body = {'merchant_id':merchant_id, 'order_id':'restart-uncertain', 'numref':'12345',
            'concept':'Synthetic', 'amount_minor':15000, 'expiration_s':600}
    assert client.post('/v1/checkout/qr', headers={'x-csrf-token':csrf}, json=body).status_code == 502

    restarted = create_platform(settings, provider=provider)
    second = TestClient(restarted, cookies=client.cookies)
    path = f'/v1/merchants/{merchant_id}/checkout-orders/restart-uncertain'
    result = second.get(path)
    assert result.status_code == 200
    assert result.json()['intent']['status'] == 'PROVIDER_UNCERTAIN'
    assert result.json()['intent']['amount_minor'] == 15000
    again = second.post('/v1/checkout/qr', headers={'x-csrf-token':csrf}, json=body)
    assert again.json()['status'] == 'REPLAY_NO_PROVIDER_RETRY'
    assert provider.calls == 1
    app.state.accounts.Session.kw['bind'].dispose()
    restarted.state.accounts.Session.kw['bind'].dispose()


def test_postgresql_shared_sale_collision_across_authorized_sessions(temporary_database, monkeypatch):
    from test_shared_sale import TimeoutProvider, exercise_shared_sale_race

    url, _factory, _ = migrated_database(temporary_database, monkeypatch)
    provider = TimeoutProvider()
    app = create_platform(Settings(database_url=url.render_as_string(hide_password=False), auto_create=False),
                          provider=provider)
    try:
        exercise_shared_sale_race(app, provider)
    finally:
        app.state.accounts.Session.kw['bind'].dispose()


def test_postgresql_reconciliation_preview_after_app_restart(temporary_database, monkeypatch):
    from test_platform import SECRET, checkout, signed_webhook, signup, verified_login
    from test_reconciliation_preview import CLABE, RECORD, TRACKING

    url, _factory, _ = migrated_database(temporary_database, monkeypatch)
    settings = Settings(database_url=url.render_as_string(hide_password=False), auto_create=False,
                        webhook_secret=SECRET)
    app = create_platform(settings)
    env = (app, TestClient(app))
    merchant_id = signup(env, 'review-postgres@example.com')['merchant_id']
    csrf = verified_login(env, 'review-postgres@example.com')
    response = checkout(env, merchant_id, csrf, order='postgres-review', amount=15000)
    intent = app.state.payments.get(response.json()['intent']['id'])
    event = {'amount':150, 'apiKeyId':'synthetic-key-id', 'codiQrId':intent.provider_qr_id,
             'numRef':'postgres-review', 'transactionId':'synthetic-pg-review',
             'type':'codi.qr.payment_received', 'metadata':{'clabe':CLABE, 'trackingKey':TRACKING}}
    assert signed_webhook(env[1], event, 'synthetic-pg-event').status_code == 200
    restarted = create_platform(settings)
    second = TestClient(restarted, cookies=env[1].cookies)
    path = f'/v1/checkout/qr/{intent.id}/reconciliation-preview'
    result = second.post(path, headers={'x-csrf-token':csrf}, json={'bank_records':[RECORD]})
    assert result.status_code == 200
    assert result.json()['classification'] == 'MATCH_CANDIDATE_UNVERIFIED'
    assert result.json()['bank_payment_confirmed'] is False
    assert result.json()['independent_source_verified'] is False
    assert result.json()['beneficiary_binding_verified'] is False
    assert result.json()['bank_records_persisted'] is False
    app.state.accounts.Session.kw['bind'].dispose()
    restarted.state.accounts.Session.kw['bind'].dispose()


def test_postgresql_simulated_qr_review_preserves_tenant_and_payment_state(temporary_database, monkeypatch):
    from rio_pey_codi.simulated_pey import SimulatedPeyPages
    from test_platform import checkout, signup, verified_login
    from test_simulated_transaction_review import item, page, record

    url, _factory, _ = migrated_database(temporary_database, monkeypatch)
    simulation = SimulatedPeyPages()
    app = create_platform(Settings(database_url=url.render_as_string(hide_password=False), auto_create=False),
                          simulated_pey=simulation)
    owner, outsider = (app, TestClient(app)), (app, TestClient(app))
    merchant_id = signup(owner, 'pg-simulation-owner@example.com')['merchant_id']
    csrf = verified_login(owner, 'pg-simulation-owner@example.com')
    signup(outsider, 'pg-simulation-other@example.com')
    outsider_csrf = verified_login(outsider, 'pg-simulation-other@example.com')
    intent_id = checkout(owner, merchant_id, csrf, order='pg-simulation', amount=15000).json()['intent']['id']
    row = app.state.payments.get(intent_id)
    simulation.install(row.provider_qr_id, {None: page([item(row.provider_qr_id, 'pg-track', 'pg-tx')])})
    path = f'/v1/checkout/qr/{intent_id}/simulated-transaction-review'
    response = owner[1].post(path, headers={'x-csrf-token': csrf}, json={'bank_records': [record('pg-track')]})
    assert response.status_code == 200
    assert response.json()['classification'] == 'MATCH_CANDIDATE_UNVERIFIED'
    assert not response.json()['bank_payment_confirmed'] and not response.json()['payment_state_changed']
    assert outsider[1].post(path, headers={'x-csrf-token': outsider_csrf},
                            json={'bank_records': [record('pg-track')]}).status_code == 404
    with app.state.accounts.Session() as db:
        actual = db.get(Intent, intent_id)
        assert actual.status == 'QR_ISSUED' and actual.transaction_id is None
        assert db.scalar(select(func.count()).select_from(Event)) == 0
        assert db.scalar(select(func.count()).select_from(PendingEvent)) == 0
    app.state.accounts.Session.kw['bind'].dispose()


def test_postgresql_durable_reviews_lock_retries_and_preserve_history(temporary_database, monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    from rio_pey_codi.models import ReconciliationReview
    from test_platform import SECRET, checkout, signed_webhook, signup, verified_login
    from test_reconciliation_preview import CLABE, RECORD, TRACKING

    url, _factory, config = migrated_database(temporary_database, monkeypatch)
    command.check(config)
    settings = Settings(database_url=url.render_as_string(hide_password=False), auto_create=False,
                        webhook_secret=SECRET)
    app = create_platform(settings)
    owner = (app, TestClient(app))
    merchant = signup(owner, 'durable-postgres@example.com')['merchant_id']
    csrf = verified_login(owner, 'durable-postgres@example.com')
    intent_id = checkout(owner, merchant, csrf, order='durable-pg', amount=15000).json()['intent']['id']
    row = app.state.payments.get(intent_id)
    payload = {'type':'codi.qr.payment_received', 'codiQrId':row.provider_qr_id, 'amount':150,
               'numRef':'durable-pg', 'transactionId':'durable-pg-tx', 'apiKeyId':'synthetic',
               'metadata':{'clabe':CLABE, 'trackingKey':TRACKING}}
    assert signed_webhook(owner[1], payload, 'durable-pg-event').status_code == 200
    path = f'/v1/checkout/qr/{intent_id}/reconciliation-reviews'
    barrier = threading.Barrier(2)
    def submit():
        client = TestClient(app, cookies=owner[1].cookies)
        barrier.wait(timeout=10)
        return client.post(path, headers={'x-csrf-token':csrf, 'idempotency-key':'9' * 32},
                           json={'bank_records':[RECORD]})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: submit(), range(2)))
    assert sorted(response.status_code for response in responses) == [201, 409]
    expected = next(response.json()['review']['id'] for response in responses if response.status_code == 201)
    with app.state.accounts.Session() as db:
        assert db.scalar(select(func.count()).select_from(ReconciliationReview)) == 1
    engine = app.state.accounts.Session.kw['bind']
    for sql_statement in ('UPDATE reconciliation_reviews SET classification = :value WHERE id = :id',
                          'DELETE FROM reconciliation_reviews WHERE id = :id'):
        with pytest.raises(DBAPIError):
            with engine.begin() as connection:
                connection.execute(text(sql_statement), {'value':'FAKE', 'id':expected})
    with pytest.raises(RuntimeError, match='Refusing to (remove reconciliation reviews|discard stored webhook signature evidence|discard recorded signature assessments|discard account comparison evidence)'):
        command.downgrade(config, '008')
    restarted = create_platform(settings)
    response = TestClient(restarted, cookies=owner[1].cookies).get(path)
    assert response.status_code == 200 and response.json()['reviews'][0]['id'] == expected
    assert not response.json()['bank_payment_confirmed']
    app.state.accounts.Session.kw['bind'].dispose()
    restarted.state.accounts.Session.kw['bind'].dispose()


def test_postgresql_beneficiary_claims_are_serialized_durable_and_immutable(temporary_database, monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    from test_beneficiary_claims import path, post
    from test_platform import signup, verified_login

    url, _factory, config = migrated_database(temporary_database, monkeypatch)
    command.check(config)
    settings = Settings(database_url=url.render_as_string(hide_password=False), auto_create=False)
    app = create_platform(settings)
    owner = (app, TestClient(app))
    merchant_id = signup(owner, 'claim-postgres@example.com')['merchant_id']
    csrf = verified_login(owner, 'claim-postgres@example.com')
    barrier = threading.Barrier(2)
    def submit():
        client = TestClient(app, cookies=owner[1].cookies)
        barrier.wait(timeout=10)
        return post(client, merchant_id, csrf, 'a' * 32)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: submit(), range(2)))
    assert [r.status_code for r in responses] == [201, 201]
    assert responses[0].json()['claim'] == responses[1].json()['claim']
    engine = app.state.accounts.Session.kw['bind']
    for statement in ('UPDATE beneficiary_claims SET sequence=2', 'DELETE FROM beneficiary_claims'):
        with pytest.raises(DBAPIError):
            with engine.begin() as connection:
                connection.execute(text(statement))
    with pytest.raises(RuntimeError, match='Refusing to remove recorded beneficiary claims'):
        command.downgrade(config, '009')
    reopened = create_platform(settings)
    readback = TestClient(reopened, cookies=owner[1].cookies).get(path(merchant_id))
    assert readback.status_code == 200 and readback.json()['claims'] == [responses[0].json()['claim']]
    app.state.accounts.Session.kw['bind'].dispose()
    reopened.state.accounts.Session.kw['bind'].dispose()


def test_postgresql_beneficiary_history_serializes_revocation(temporary_database, monkeypatch):
    from test_beneficiary_claims import test_history_read_serializes_against_session_revocation
    url, _factory, _config = migrated_database(temporary_database, monkeypatch)
    settings = Settings(database_url=url.render_as_string(hide_password=False), auto_create=False)
    app = create_platform(settings)
    try:
        test_history_read_serializes_against_session_revocation((app, TestClient(app)), monkeypatch)
    finally:
        app.state.accounts.Session.kw['bind'].dispose()


def test_postgresql_signature_reverification_and_migration_guard(temporary_database, monkeypatch):
    import hashlib
    import json
    from test_platform import SECRET, checkout, signed_webhook, signup, verified_login
    from test_reconciliation_preview import CLABE, RECORD, TRACKING

    url, _factory, config = migrated_database(temporary_database, monkeypatch)
    command.check(config)
    settings = Settings(database_url=url.render_as_string(hide_password=False), auto_create=False,
                        webhook_secret=SECRET)
    app = create_platform(settings)
    env = (app, TestClient(app))
    merchant_id = signup(env, 'signed-postgres@example.com')['merchant_id']
    csrf = verified_login(env, 'signed-postgres@example.com')
    intent = checkout(env, merchant_id, csrf, order='signed-pg', amount=15000).json()['intent']
    qr_id = app.state.payments.get(intent['id']).provider_qr_id
    payload = {'type':'codi.qr.payment_received', 'codiQrId':qr_id, 'amount':150,
               'numRef':'signed-pg', 'transactionId':'pg-tx', 'apiKeyId':'synthetic',
               'metadata':{'clabe':CLABE, 'trackingKey':TRACKING}}
    assert signed_webhook(env[1], payload, 'pg-signed-event').status_code == 200
    path = f"/v1/checkout/qr/{intent['id']}/reconciliation-preview"
    result = env[1].post(path, headers={'x-csrf-token':csrf}, json={'bank_records':[RECORD]}).json()
    assert result['provider_signature_reverified'] and result['classification'] == 'MATCH_CANDIDATE_UNVERIFIED'
    with pytest.raises(RuntimeError, match='Refusing to discard stored webhook signature evidence'):
        command.downgrade(config, '010')
    altered = {**payload, 'metadata':{**payload['metadata'], 'trackingKey':'pg-forged'}}
    raw = json.dumps(altered, separators=(',', ':')).encode()
    with app.state.accounts.Session.begin() as db:
        event = db.get(Event, 'pg-signed-event')
        event.raw_body, event.sha256 = raw, hashlib.sha256(raw).hexdigest()
    result = env[1].post(path, headers={'x-csrf-token':csrf},
                          json={'bank_records':[{**RECORD, 'tracking_key':'pg-forged'}]}).json()
    assert result['classification'] == 'PROVIDER_SIGNATURE_INVALID'
    assert result['provider_signature_reverified'] is False and result['bank_payment_confirmed'] is False
    app.state.accounts.Session.kw['bind'].dispose()


def test_postgresql_account_review_serializes_owner_claim_update(temporary_database, monkeypatch):
    from test_beneficiary_reconciliation import test_review_serializes_owner_claim_update
    from test_platform import SECRET, checkout, signup, verified_login
    from test_reconciliation_preview import CLABE, TRACKING

    url, _factory, config = migrated_database(temporary_database, monkeypatch)
    command.check(config)
    settings = Settings(database_url=url.render_as_string(hide_password=False), auto_create=False, webhook_secret=SECRET)
    app = create_platform(settings)
    env = (app, TestClient(app))
    merchant_id = signup(env, 'owner@example.com')['merchant_id']
    csrf = verified_login(env, 'owner@example.com')
    intent_id = checkout(env, merchant_id, csrf, order='review-1', amount=15000).json()['intent']['id']
    intent = app.state.payments.get(intent_id)
    payload = {'amount':150, 'apiKeyId':'synthetic-key-id', 'codiQrId':intent.provider_qr_id,
               'concept':'Pan','datePaid':1790724818,'numRef':'review-1','transactionId':'synthetic-tx',
               'type':'codi.qr.payment_received','metadata':{'clabe':CLABE,'trackingKey':TRACKING}}
    try:
        test_review_serializes_owner_claim_update((env, merchant_id, csrf, intent_id, payload), monkeypatch)
        with pytest.raises(RuntimeError, match='Refusing to discard account comparison evidence'):
            command.downgrade(config, '011')
    finally:
        app.state.accounts.Session.kw['bind'].dispose()


def test_postgresql_retained_signing_key_reverifies_history(temporary_database, monkeypatch):
    from test_platform import SECRET, checkout, signup, verified_login
    from test_reconciliation_preview import CLABE, TRACKING
    from test_webhook_key_rotation import test_old_key_can_reverify_history_but_cannot_authorize_new_delivery

    url, _factory, config = migrated_database(temporary_database, monkeypatch)
    command.check(config)
    settings = Settings(database_url=url.render_as_string(hide_password=False), auto_create=False, webhook_secret=SECRET)
    app = create_platform(settings)
    env = (app, TestClient(app))
    merchant_id = signup(env, 'owner@example.com')['merchant_id']
    csrf = verified_login(env, 'owner@example.com')
    intent_id = checkout(env, merchant_id, csrf, order='review-1', amount=15000).json()['intent']['id']
    intent = app.state.payments.get(intent_id)
    payload = {'amount':150, 'apiKeyId':'synthetic-key-id', 'codiQrId':intent.provider_qr_id,
               'concept':'Pan','datePaid':1790724818,'numRef':'review-1','transactionId':'synthetic-tx',
               'type':'codi.qr.payment_received','metadata':{'clabe':CLABE,'trackingKey':TRACKING}}
    try:
        test_old_key_can_reverify_history_but_cannot_authorize_new_delivery((env, merchant_id, csrf, intent_id, payload))
    finally:
        app.state.accounts.Session.kw['bind'].dispose()


@pytest.mark.parametrize('change', ['new_signed_conflict', 'raw_body', 'signature', 'restored'])
def test_postgresql_reconciliation_preview_event_races(temporary_database, monkeypatch, change):
    from test_platform import SECRET, checkout, signup, verified_login
    from test_reconciliation_preview import CLABE, TRACKING
    from test_reconciliation_event_races import (
        test_preview_compares_exact_assessed_snapshot_even_if_evidence_is_restored,
        test_provider_evidence_changes_during_preview_require_retry,
    )

    url, _factory, config = migrated_database(temporary_database, monkeypatch)
    command.check(config)
    settings = Settings(database_url=url.render_as_string(hide_password=False), auto_create=False,
                        webhook_secret=SECRET)
    app = create_platform(settings)
    env = (app, TestClient(app))
    merchant_id = signup(env, 'owner@example.com')['merchant_id']
    csrf = verified_login(env, 'owner@example.com')
    intent_id = checkout(env, merchant_id, csrf, order='review-1', amount=15000).json()['intent']['id']
    intent = app.state.payments.get(intent_id)
    payload = {'amount':150, 'apiKeyId':'synthetic-key-id', 'codiQrId':intent.provider_qr_id,
               'concept':'Pan', 'datePaid':1790724818, 'numRef':'review-1', 'transactionId':'synthetic-tx',
               'type':'codi.qr.payment_received', 'metadata':{'clabe':CLABE, 'trackingKey':TRACKING}}
    payment = (env, merchant_id, csrf, intent_id, payload)
    try:
        if change == 'restored':
            test_preview_compares_exact_assessed_snapshot_even_if_evidence_is_restored(payment, monkeypatch)
        else:
            test_provider_evidence_changes_during_preview_require_retry(payment, monkeypatch, change)
    finally:
        app.state.accounts.Session.kw['bind'].dispose()


@pytest.mark.parametrize('scenario', ['durable', 'concurrent'])
def test_postgresql_readonly_provider_observation(temporary_database, monkeypatch, scenario):
    from test_platform import SECRET, signup, verified_login
    from test_beneficiary_claims import post
    from test_provider_account_observations import (
        TOKEN, test_concurrent_same_request_records_at_most_one_observation,
        test_owner_check_is_durable_minimized_and_never_enables_live,
    )

    url, _factory, config = migrated_database(temporary_database, monkeypatch)
    command.check(config)
    dsn = url.render_as_string(hide_password=False)
    base = create_platform(Settings(database_url=dsn, auto_create=False, webhook_secret=SECRET))
    env = (base, TestClient(base))
    merchant = signup(env)['merchant_id']; csrf = verified_login(env)
    assert post(env[1], merchant, csrf, 'a' * 32).status_code == 201
    settings = Settings(database_url=dsn, auto_create=False, webhook_secret=SECRET,
                        account_lookup_enabled=True, account_lookup_merchant_id=merchant,
                        account_lookup_key_ref='test_key', account_lookup_api_key=TOKEN)
    app = create_platform(settings)
    owner = (app, TestClient(app, cookies=env[1].cookies))
    try:
        if scenario == 'durable':
            test_owner_check_is_durable_minimized_and_never_enables_live((owner, merchant, csrf), monkeypatch)
        else:
            test_concurrent_same_request_records_at_most_one_observation((owner, merchant, csrf), monkeypatch)
        with pytest.raises(RuntimeError, match='Refusing to discard provider observations'):
            command.downgrade(config, '012')
    finally:
        app.state.accounts.Session.kw['bind'].dispose()
        base.state.accounts.Session.kw['bind'].dispose()


def test_postgresql_reset_token_is_consumed_once(temporary_database, monkeypatch):
    _, factory, _ = migrated_database(temporary_database, monkeypatch)
    mailer = Mailer(EmailConfig())
    accounts = AccountService(factory, mailer)
    accounts.signup(Signup(email='reset@example.com', password='synthetic-password-123', business_name='Demo'))
    accounts.reset_request('reset@example.com')
    token = next(item['token'] for item in mailer.outbox if item['kind'] == 'reset')
    barrier = threading.Barrier(2)

    def reset():
        barrier.wait(timeout=10)
        try:
            accounts.reset_confirm(token, 'new-synthetic-password-123')
            return 200
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: reset(), range(2)))
    assert sorted(results) == [200, 400]


def test_postgresql_backup_restores_synthetic_records(temporary_database, monkeypatch):
    if not shutil.which('pg_dump') or not shutil.which('pg_restore'):
        pytest.skip('PostgreSQL client utilities are not installed')
    url, factory, _ = migrated_database(temporary_database, monkeypatch)
    merchant_id = merchant(factory)
    row, _ = PaymentRepository(factory).reserve(merchant_id, 'backup-order', 123, 'Demo', '12', 600)
    create, remember, admin = temporary_database
    restored = create()
    env = os.environ.copy()
    env.update(PGHOST=admin.host, PGPORT=str(admin.port or 5432), PGUSER=admin.username or '')
    if admin.password:
        env['PGPASSWORD'] = admin.password
    backup = subprocess.run(['pg_dump', '--format=custom', '--no-owner', '--no-privileges', url.database],
                            env=env, capture_output=True, check=True, timeout=30).stdout
    subprocess.run(['pg_restore', '--exit-on-error', '--no-owner', '--no-privileges', '--dbname', restored.database],
                   input=backup, env=env, capture_output=True, check=True, timeout=30)
    restored_factory = remember(database(restored.render_as_string(hide_password=False)))
    with restored_factory() as db:
        assert db.get(Merchant, merchant_id).name == 'Synthetic'
        assert db.get(Intent, row.id).amount_minor == 123
