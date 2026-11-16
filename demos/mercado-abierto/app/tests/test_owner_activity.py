import json
import smtplib
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from rio_pey_codi.models import ActivityEvent
from rio_pey_codi.platform import Settings,create_platform
from test_merchant_pey_vault import create_user


def test_only_pinned_owner_reads_activity_with_safe_pagination(tmp_path):
    app=create_platform(Settings(database_url='sqlite+pysqlite:///'+str(tmp_path/'activity.sqlite')))
    owner=TestClient(app);member=TestClient(app)
    create_user(app,owner,'ivania@example.org')
    app.state.accounts.platform_owner_id=owner.get('/v1/auth/me').json()['id']
    create_user(app,member,'member@example.org')
    assert TestClient(app).get('/v1/admin/activity').status_code==401
    assert member.get('/v1/admin/activity').status_code==403
    assert member.get('/v1/auth/me').json()['can_invite'] is False
    assert owner.get('/v1/auth/me').json()['can_invite'] is True
    seen=set();cursor=None
    while True:
        result=owner.get('/v1/admin/activity',params={'limit':2,**({'before':cursor} if cursor else {})})
        assert result.status_code==200
        data=result.json()
        for event in data['events']:
            assert event['id'] not in seen;seen.add(event['id'])
            assert event['source']=='LIVE_EVENT'
        cursor=data['next_cursor']
        if not cursor:break
    assert len(seen)>=10
    assert owner.get('/v1/admin/activity',params={'before':'not-a-cursor'}).status_code==422
    assert owner.get('/v1/admin/activity',params={'category':'email'}).status_code==200
    assert owner.get('/v1/admin/activity',params={'limit':101}).status_code==422
    with app.state.accounts.Session() as db:
        types={r.event_type for r in db.scalars(select(ActivityEvent))}
    assert {'ACCOUNT_CREATED','VERIFICATION_ACCEPTED','EMAIL_VERIFIED','LOGIN_ACCEPTED'}<=types


def test_delivery_failures_and_duplicate_registration_are_persistent_without_secrets(tmp_path,monkeypatch):
    app=create_platform(Settings(database_url='sqlite+pysqlite:///'+str(tmp_path/'mail.sqlite')))
    client=TestClient(app)
    def fail(*args):raise smtplib.SMTPDataError(550,b'password=PRIVATE provider token=SECRET')
    monkeypatch.setattr(app.state.mailer,'send',fail)
    account={'email':'pending@example.org','business_name':'Test business','password':'Synthetic-secret-123'}
    assert client.post('/v1/auth/signup',json=account).status_code==503
    assert client.post('/v1/auth/signup',json=account).status_code==409
    assert client.post('/v1/auth/resend-verification',json={'email':account['email']}).status_code==503
    with app.state.accounts.Session() as db:
        events=list(db.scalars(select(ActivityEvent)))
    assert {'ACCOUNT_CREATED','ACCOUNT_EXISTS','VERIFICATION_REQUESTED','VERIFICATION_FAILED'}<={e.event_type for e in events}
    body=json.dumps([{key:getattr(e,key) for key in ('event_type','email','detail_code','reference')} for e in events])
    assert 'Synthetic-secret-123' not in body and 'PRIVATE' not in body and 'SECRET' not in body
    assert 'SMTP_MESSAGE_REJECTED' in body
    # Server restart sees the same events, without process-local storage.
    app2=create_platform(Settings(database_url=app.state.settings.database_url,auto_create=False))
    with app2.state.accounts.Session() as db:assert len(list(db.scalars(select(ActivityEvent))))==len(events)


def test_migration_labels_real_history_and_refuses_to_discard_it(tmp_path,monkeypatch):
    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    import sqlite3
    url='sqlite:///'+str(tmp_path/'historical.sqlite')
    monkeypatch.setenv('DATABASE_URL',url)
    config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))
    command.upgrade(config,'017')
    # Keep this revision test independent of newer ORM-only columns (for example
    # merchants.archived_at from 024) while proving 018 backfills stored state.
    with sqlite3.connect(tmp_path/'historical.sqlite') as db:
        db.execute('INSERT INTO users (id,email,password_hash,created_at,verified_at) VALUES (?,?,?,?,?)',
                   ('a'*32,'historical@example.org','synthetic-hash',100,200))
    app=create_platform(Settings(database_url=url,auto_create=False))
    command.upgrade(config,'018')
    # This fixture verifies revision018; current-head metadata is checked separately.
    with sqlite3.connect(tmp_path/'historical.sqlite') as db:
        assert db.execute('SELECT version_num FROM alembic_version').fetchone()[0] == '018'
    with app.state.accounts.Session() as db:
        rows=list(db.scalars(select(ActivityEvent)))
        assert {r.event_type for r in rows}=={'ACCOUNT_CREATED','EMAIL_VERIFIED'}
        assert all(r.source=='HISTORICAL_STATE' for r in rows)
    with sqlite3.connect(tmp_path/'historical.sqlite') as db:before='\n'.join(db.iterdump())
    with pytest.raises(RuntimeError,match='Refusing to discard activity history'):command.downgrade(config,'017')
    with sqlite3.connect(tmp_path/'historical.sqlite') as db:assert '\n'.join(db.iterdump())==before
