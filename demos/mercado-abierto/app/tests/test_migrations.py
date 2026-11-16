import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.engine import Engine

from rio_pey_codi.platform import EXPECTED_SCHEMA_REVISION, Settings, create_platform


def _insert_legacy_payment_fixture(connection):
    """Seed rows using the schema at the migration under test, not today's ORM."""
    user_id, merchant_id, intent_id = 'a' * 32, 'b' * 32, 'c' * 32
    connection.execute(
        'INSERT INTO users (id,email,password_hash,created_at) VALUES (?,?,?,?)',
        (user_id, 'migration-fixture@example.invalid', 'synthetic', 1))
    connection.execute(
        'INSERT INTO merchants (id,name,owner_id,created_at) VALUES (?,?,?,?)',
        (merchant_id, 'Migration fixture', user_id, 1))
    connection.execute(
        'INSERT INTO payment_intents (id,merchant_id,order_id,amount_minor,concept,numref,expiration_s,status,created_at) '
        'VALUES (?,?,?,?,?,?,?,?,?)',
        (intent_id, merchant_id, 'migration-order', 100, 'Fixture', '123', 600, 'PENDING', 1))
    return user_id, merchant_id, intent_id


def test_public_readiness_revision_tracks_migration_head():
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    assert ScriptDirectory.from_config(config).get_current_head() == EXPECTED_SCHEMA_REVISION


@pytest.mark.parametrize('evidence', ['review', 'event', 'provider_readback', 'pending_provider_readback'])
def test_016_downgrade_rejects_evidence_before_changing_database(tmp_path, monkeypatch, evidence):
    source = tmp_path / 'retained.sqlite3'
    url = f'sqlite:///{source}'
    monkeypatch.setenv('DATABASE_URL', url)
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    command.upgrade(config, '016')
    with sqlite3.connect(source) as connection:
        user_id, merchant_id, intent_id = _insert_legacy_payment_fixture(connection)
        if evidence == 'review':
            connection.execute(
                'INSERT INTO reconciliation_reviews '
                '(id,intent_id,actor_id,request_id,classification,bank_record_count,provider_event_count,created_at,account_assessment) '
                'VALUES (?,?,?,?,?,?,?,?,?)',
                ('d' * 32, intent_id, user_id, 'e' * 32, 'NO_PROVIDER_REPORT', 0, 0, 1, 'NOT_VERIFIED'))
            reason = 'Refusing to discard account comparison evidence'
        elif evidence == 'event':
            connection.execute(
                'INSERT INTO payment_events (id,sha256,intent_id,processed_at,signature) VALUES (?,?,?,?,?)',
                ('retained-event', 'a' * 64, intent_id, 1, 'synthetic-migration-fixture'))
            reason = 'Refusing to discard stored webhook signature evidence'
        elif evidence == 'provider_readback':
            connection.execute(
                'UPDATE payment_intents SET provider_payment_source=?,provider_payment_observed_at=?,provider_payment_sha256=? WHERE id=?',
                ('PEY_API', 1, 'b' * 64, intent_id))
            reason = 'Refusing to discard pey payment evidence'
        else:
            connection.execute(
                'INSERT INTO pending_payment_events '
                '(id,sha256,qr_id,amount_minor,numref,transaction_id,received_at,merchant_id,intent_id,provider_verified,provider_payment_sha256) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                ('retained-pending', 'c' * 64, 'fixture-qr', 100, 'fixture', 'fixture-tx', 1,
                 merchant_id, intent_id, 1, 'd' * 64))
            reason = 'Refusing to discard pey payment evidence'
        connection.commit()
    with sqlite3.connect(source) as connection:
        before = '\n'.join(connection.iterdump())
    with pytest.raises(RuntimeError, match=reason):
        command.downgrade(config, '015')
    with sqlite3.connect(source) as connection:
        assert '\n'.join(connection.iterdump()) == before
        assert connection.execute('SELECT version_num FROM alembic_version').fetchone()[0] == '016'


def test_migrated_database_backup_preserves_session_and_merchant(tmp_path, monkeypatch):
    source = tmp_path / 'original.sqlite3'
    restored = tmp_path / 'restored.sqlite3'
    url = f'sqlite:///{source}'
    monkeypatch.setenv('DATABASE_URL', url)
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    command.upgrade(config, 'head')
    command.check(config)
    command.downgrade(config, 'base')
    command.upgrade(config, 'head')

    settings = Settings(database_url=url, auto_create=False)
    app = create_platform(settings)
    client = TestClient(app)
    credentials = {'email':'restore@example.com', 'password':'synthetic-password-123'}
    signup = client.post('/v1/auth/signup', json={**credentials, 'business_name':'Restauración'})
    assert signup.status_code == 201
    mail = app.state.mailer.outbox[0]
    assert '#token=' in mail['link'] and '?token=' not in mail['link']
    assert client.post('/v1/auth/verify-email', json={'token':mail['token']}).status_code == 200
    session = client.post('/v1/auth/login', json=credentials)
    assert session.status_code == 200
    assert 'HttpOnly' in session.headers['set-cookie']

    with sqlite3.connect(source) as src, sqlite3.connect(restored) as dst:
        src.backup(dst)
    restored_app = create_platform(replace(settings, database_url=f'sqlite:///{restored}'))
    reopened = TestClient(restored_app, cookies=client.cookies)
    assert reopened.get('/v1/auth/me').status_code == 200
    assert reopened.get('/v1/merchants').json()['merchants'][0]['id'] == signup.json()['merchant_id']


def test_recorded_review_survives_backup_and_blocks_destructive_downgrade(tmp_path, monkeypatch):
    source, restored = tmp_path / 'reviews.sqlite3', tmp_path / 'reviews-copy.sqlite3'
    url = f'sqlite:///{source}'
    monkeypatch.setenv('DATABASE_URL', url)
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    command.upgrade(config, '017')
    with sqlite3.connect(source) as db:
        user_id, _, intent_id = _insert_legacy_payment_fixture(db)
        review_id = 'd' * 32
        db.execute('INSERT INTO reconciliation_reviews '
                   '(id,intent_id,actor_id,request_id,classification,bank_record_count,provider_event_count,created_at,account_assessment) '
                   'VALUES (?,?,?,?,?,?,?,?,?)',
                   (review_id,intent_id,user_id,'e'*32,'NO_PROVIDER_REPORT',0,0,1,'SIGNATURE_NOT_VERIFIED'))
    with pytest.raises(RuntimeError, match='Refusing to discard account comparison evidence'):
        command.downgrade(config, '011')
    with pytest.raises(RuntimeError, match='Refusing to (remove reconciliation reviews|discard recorded signature assessments|discard account comparison evidence)'):
        command.downgrade(config, '008')
    with sqlite3.connect(source) as src, sqlite3.connect(restored) as dst:
        src.backup(dst)
    with sqlite3.connect(restored) as db:
        row = db.execute('SELECT account_assessment FROM reconciliation_reviews WHERE id=?',(review_id,)).fetchone()
        assert row == ('SIGNATURE_NOT_VERIFIED',)


def test_recorded_beneficiary_claim_survives_backup_and_blocks_downgrade(tmp_path, monkeypatch):
    source, restored = tmp_path / 'claims.sqlite3', tmp_path / 'claims-copy.sqlite3'
    url = f'sqlite:///{source}'
    monkeypatch.setenv('DATABASE_URL', url)
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    command.upgrade(config, '017')
    with sqlite3.connect(source) as db:
        user_id, merchant_id, _ = _insert_legacy_payment_fixture(db)
        claim_id = 'd' * 32
        db.execute('INSERT INTO beneficiary_claims '
                   '(id,merchant_id,actor_id,sequence,request_id,claim,provider_account_id,created_at) '
                   'VALUES (?,?,?,?,?,?,?,?)',
                   (claim_id,merchant_id,user_id,1,'e'*32,'OWNER_REPORTED_VERIFIED',None,1))
    with pytest.raises(RuntimeError, match='Refusing to remove recorded beneficiary claims'):
        command.downgrade(config, '009')
    with sqlite3.connect(source) as src, sqlite3.connect(restored) as dst:
        src.backup(dst)
    with sqlite3.connect(restored) as db:
        assert db.execute('SELECT claim FROM beneficiary_claims WHERE id=?',(claim_id,)).fetchone() == ('OWNER_REPORTED_VERIFIED',)


def test_provider_observation_survives_backup_and_blocks_downgrade(tmp_path, monkeypatch):
    source, restored = tmp_path/'provider.sqlite3', tmp_path/'provider-copy.sqlite3'
    url = f'sqlite:///{source}'
    monkeypatch.setenv('DATABASE_URL', url)
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    command.upgrade(config, '017')
    with sqlite3.connect(source) as db:
        user_id, merchant_id, _ = _insert_legacy_payment_fixture(db)
        claim_id, observation_id = 'd'*32, 'f'*32
        db.execute('INSERT INTO beneficiary_claims '
                   '(id,merchant_id,actor_id,sequence,request_id,claim,provider_account_id,created_at) '
                   'VALUES (?,?,?,?,?,?,?,?)',
                   (claim_id,merchant_id,user_id,1,'e'*32,'OWNER_REPORTED_VERIFIED',None,1))
        db.execute('INSERT INTO provider_account_observations '
                   '(id,merchant_id,claim_id,actor_id,request_id,sequence,credential_ref,status,created_at) '
                   'VALUES (?,?,?,?,?,?,?,?,?)',
                   (observation_id,merchant_id,claim_id,user_id,'a'*32,1,'fixture-key','ACTIVE',2))
    with pytest.raises(RuntimeError, match='Refusing to discard provider observations'):
        command.downgrade(config, '012')
    with sqlite3.connect(source) as src, sqlite3.connect(restored) as dst:
        src.backup(dst)
    with sqlite3.connect(restored) as db:
        assert db.execute('SELECT status FROM provider_account_observations WHERE id=?',(observation_id,)).fetchone() == ('ACTIVE',)


def test_webhook_signature_survives_backup_and_prevents_downgrade(tmp_path, monkeypatch):
    source, restored = tmp_path / 'signature.sqlite3', tmp_path / 'signature-copy.sqlite3'
    url = f'sqlite:///{source}'
    monkeypatch.setenv('DATABASE_URL', url)
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    command.upgrade(config, '017')
    with sqlite3.connect(source) as db:
        _, _, intent_id = _insert_legacy_payment_fixture(db)
        event_id = 'retained-signature-event'
        db.execute('INSERT INTO payment_events (id,sha256,intent_id,processed_at,signature,signature_timestamp,signature_received_at,signature_key_ref) '
                   'VALUES (?,?,?,?,?,?,?,?)',
                   (event_id,'a'*64,intent_id,1,'synthetic-signature',1,1,'fixture-key-ref'))
    with pytest.raises(RuntimeError, match='Refusing to discard stored webhook signature evidence'):
        command.downgrade(config, '010')
    with sqlite3.connect(source) as src, sqlite3.connect(restored) as dst:
        src.backup(dst)
    with sqlite3.connect(restored) as db:
        row = db.execute('SELECT signature_key_ref FROM payment_events WHERE id=?',(event_id,)).fetchone()
        assert row == ('fixture-key-ref',)


def test_sqlite_review_downgrade_locks_out_concurrent_writers(tmp_path, monkeypatch):
    source = tmp_path / 'concurrent-migration.sqlite3'
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{source}')
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    command.upgrade(config, 'head')
    observed = []
    def check_lock(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.strip().upper().startswith('SELECT 1 FROM RECONCILIATION_REVIEWS'):
            with sqlite3.connect(source, timeout=.1) as other:
                try:
                    other.execute("UPDATE users SET email = email")
                except sqlite3.OperationalError as error:
                    observed.append('locked' if 'locked' in str(error).lower() else 'other error')
                else:
                    observed.append('write admitted')
    event.listen(Engine, 'before_cursor_execute', check_lock)
    try:
        command.downgrade(config, '008')
    finally:
        event.remove(Engine, 'before_cursor_execute', check_lock)
    assert observed and all(value == 'locked' for value in observed)
