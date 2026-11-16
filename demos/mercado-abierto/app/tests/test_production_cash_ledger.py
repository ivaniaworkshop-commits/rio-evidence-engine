"""Cash is immutable server evidence of a manual declaration, never a bank payment."""
import concurrent.futures
from datetime import datetime, timezone
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from rio_pey_codi.cash_ledger import register_cash_ledger_routes
from rio_pey_codi.cash_ledger_models import CashSale
from rio_pey_codi.platform import Settings, create_platform
from test_merchant_pey_vault import create_user


def sale(**changes):
    value = {'id': 'CASH-'+str(uuid.uuid4()), 'createdAt': datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z'),
        'folio': '', 'concept': 'Manzana', 'amountMinor':313, 'receivedMinor':500, 'changeMinor':187,
        'lines':[{'description':'Manzana','kind':'weight','quantity':250,'priceCents':1250,'amountCents':313}],
        'source':'USER_DECLARED_CASH','paymentMethod':'cash','bankPaymentConfirmed':False}
    return {**value, **changes}


def wire(app):
    if not any(getattr(route, 'path', '') == '/v1/merchants/{merchant_id}/cash-sales' for route in app.routes):
        register_cash_ledger_routes(app, app.state.accounts)


@pytest.fixture
def context(tmp_path):
    app=create_platform(Settings(database_url='sqlite+pysqlite:///'+str(tmp_path/'cash.sqlite')))
    wire(app)
    owner=TestClient(app); outsider=TestClient(app)
    merchant,csrf=create_user(app,owner,'cash-owner@example.org')
    other,other_csrf=create_user(app,outsider,'cash-outsider@example.org')
    return app,owner,outsider,merchant,csrf,other,other_csrf


def test_persists_after_restart_and_cross_browser_without_local_storage(context):
    app,owner,_,merchant,csrf,*_=context
    value=sale(folio='TICKET-1')
    path=f'/v1/merchants/{merchant}/cash-sales'
    saved=owner.post(path,json=value,headers={'x-csrf-token':csrf})
    assert saved.status_code==201,saved.text
    assert saved.json()['persisted'] is True and saved.json()['replayed'] is False
    record=owner.get(path+'/'+value['id']).json()['sale']
    assert record['bankPaymentConfirmed'] is False
    assert record['persisted'] is True and record['recordedAt'] and record['recordedBy']
    assert record['changeMinor']==187
    restarted=create_platform(Settings(database_url=app.state.settings.database_url,auto_create=False))
    wire(restarted)
    fresh=TestClient(restarted)
    assert fresh.post('/v1/auth/login',json={'email':'cash-owner@example.org','password':'VeryLongPassword123!'}).status_code==200
    assert fresh.get(path).json()['sales']==[record]


def test_cash_membership_and_csrf_are_server_enforced(context):
    app,owner,outsider,merchant,csrf,_,other_csrf=context
    path=f'/v1/merchants/{merchant}/cash-sales'
    assert TestClient(app).get(path).status_code==401
    assert outsider.get(path).status_code==404
    assert outsider.post(path,json=sale(),headers={'x-csrf-token':other_csrf}).status_code==404
    assert owner.post(path,json=sale()).status_code==403
    assert owner.put(f'/v1/merchants/{merchant}/members',json={'email':'cash-outsider@example.org','role':'reader'},headers={'x-csrf-token':csrf}).status_code==200
    assert outsider.get(path).status_code==403
    assert outsider.post(path,json=sale(),headers={'x-csrf-token':other_csrf}).status_code==403
    assert owner.put(f'/v1/merchants/{merchant}/members',json={'email':'cash-outsider@example.org','role':'cashier'},headers={'x-csrf-token':csrf}).status_code==200
    response=outsider.post(path,json=sale(),headers={'x-csrf-token':other_csrf})
    assert response.status_code==201,response.text
    assert len(owner.get(path).json()['sales'])==1


@pytest.mark.parametrize('changes',[
    {'changeMinor':999},{'amountMinor':1},{'receivedMinor':200},{'amountMinor':True},
    {'bankPaymentConfirmed':True},{'bankPaymentConfirmed':0},{'source':'BANK_CONFIRMED'},
    {'actor_id':'f'*32},{'provider_status':'PAID'},{'merchant_id':'f'*32},
    {'id':'CASH-not-a-real-uuid'},{'folio':'has spaces'},
    {'lines':[{'description':'Wrong','kind':'piece','quantity':3,'priceCents':100,'amountCents':313}]},
])
def test_rejects_forged_money_actor_payment_flags_and_malformed_records(context,changes):
    _,owner,_,merchant,csrf,*_=context
    path=f'/v1/merchants/{merchant}/cash-sales'
    response=owner.post(path,json=sale(**changes),headers={'x-csrf-token':csrf})
    assert response.status_code==422,response.text
    assert owner.get(path).json()['sales']==[]


def test_idempotency_conflicts_and_parallel_tabs_do_not_lose_records(context):
    app,owner,_,merchant,csrf,*_=context
    path=f'/v1/merchants/{merchant}/cash-sales';headers={'x-csrf-token':csrf}
    value=sale(folio='UNIQUE')
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _i:owner.post(path,json=value,headers=headers),range(4)))
    assert all(result.status_code==201 for result in results),[r.text for r in results]
    assert sum(result.json()['replayed'] is False for result in results)==1
    assert owner.post(path,json={**value,'concept':'Different'},headers=headers).status_code==409
    assert owner.post(path,json=sale(folio='UNIQUE'),headers=headers).status_code==409
    values=[sale(folio='TAB-'+str(i)) for i in range(4)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        responses=list(pool.map(lambda item:owner.post(path,json=item,headers=headers),values))
    assert all(result.status_code==201 for result in responses)
    assert len(owner.get(path).json()['sales'])==5
    with app.state.accounts.Session() as db:
        assert len(list(db.scalars(select(CashSale))))==5


def test_pagination_is_stable_and_records_cannot_be_updated_or_deleted(context):
    app,owner,_,merchant,csrf,*_=context
    path=f'/v1/merchants/{merchant}/cash-sales'
    for i in range(5):assert owner.post(path,json=sale(folio='PAGE-'+str(i)),headers={'x-csrf-token':csrf}).status_code==201
    seen=set();cursor=None
    while True:
        response=owner.get(path,params={'limit':2,**({'cursor':cursor} if cursor else {})})
        assert response.status_code==200
        for item in response.json()['sales']:
            assert item['id'] not in seen;seen.add(item['id'])
        cursor=response.json()['next_cursor']
        if not cursor:break
    assert len(seen)==5
    assert owner.get(path,params={'cursor':'not-a-valid-cursor'}).status_code==422
    assert owner.get(path,params={'limit':201}).status_code==422
    for statement in ('UPDATE cash_sales SET amount_minor=1','DELETE FROM cash_sales'):
        with pytest.raises(IntegrityError,match='immutable'):
            with app.state.accounts.Session.begin() as db:db.execute(text(statement))
    assert len(owner.get(path).json()['sales'])==5


def test_rejects_duplicate_json_and_oversize_without_echoing_private_fields(context):
    _,owner,_,merchant,csrf,*_=context
    path=f'/v1/merchants/{merchant}/cash-sales';headers={'x-csrf-token':csrf,'content-type':'application/json'}
    raw=json.dumps(sale())[:-1]+',"concept":"duplicate-secret"}'
    response=owner.post(path,content=raw,headers=headers)
    assert response.status_code==422 and 'duplicate-secret' not in response.text
    response=owner.post(path,content='x'*32769,headers=headers)
    assert response.status_code==413

def test_migration_adds_empty_ledger_and_preserves_bytes_on_refused_downgrade(tmp_path,monkeypatch):
    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    import sqlite3
    source=tmp_path/'cash-migration.sqlite'
    url='sqlite:///'+str(source)
    monkeypatch.setenv('DATABASE_URL',url)
    config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))
    command.upgrade(config,'019')
    with sqlite3.connect(source) as db:
        assert not db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cash_sales'").fetchone()
    command.upgrade(config,'020')
    import hashlib
    merchant, actor, record_id = 'a'*32, 'b'*32, 'MIGRATION-1'
    payload = json.dumps({'synthetic': True}, separators=(',', ':'))
    with sqlite3.connect(source) as db:
        db.execute('INSERT INTO cash_sales '
                   '(merchant_id,id,actor_id,folio,amount_minor,received_minor,change_minor,payload_json,payload_sha256,recorded_at) '
                   'VALUES (?,?,?,?,?,?,?,?,?,?)',
                   (merchant,record_id,actor,'MIGRATION-1',313,500,187,payload,
                    hashlib.sha256(payload.encode()).hexdigest(),1))
        before='\n'.join(db.iterdump())
    with pytest.raises(RuntimeError,match='Refusing to discard cash records'):
        command.downgrade(config,'019')
    with sqlite3.connect(source) as db:
        assert '\n'.join(db.iterdump())==before
        assert db.execute('SELECT id FROM cash_sales WHERE merchant_id=?',(merchant,)).fetchone()==(record_id,)

def test_cash_migration_generates_postgresql_offline_ddl_with_immutable_guards():
    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    from io import StringIO
    output=StringIO()
    config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'),output_buffer=output)
    command.upgrade(config,'019:020',sql=True)
    ddl=output.getvalue()
    assert 'CREATE TABLE cash_sales' in ddl
    assert 'CREATE FUNCTION mercado_cash_immutable()' in ddl
    assert 'BEFORE UPDATE OR DELETE' in ddl
    assert "version_num='020'" in ddl
