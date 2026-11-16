import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from rio_pey_codi.models import VerificationTask
from rio_pey_codi.platform import Settings, create_platform
from test_merchant_pey_vault import create_user


def test_owner_only_verification_queue_is_persistent_and_evidence_gated(tmp_path):
    url='sqlite+pysqlite:///'+str(tmp_path/'verification.sqlite')
    app=create_platform(Settings(database_url=url))
    owner=TestClient(app);member=TestClient(app)
    create_user(app,owner,'owner@example.org')
    app.state.accounts.platform_owner_id=owner.get('/v1/auth/me').json()['id']
    create_user(app,member,'merchant@example.org')

    assert TestClient(app).get('/v1/admin/verification-tasks').status_code==401
    assert member.get('/v1/admin/verification-tasks').status_code==403
    owner_page=owner.get('/').text
    member_page=member.get('/').text
    assert 'owner-verification-open' in owner_page and 'verification-tasks.js' in owner_page
    assert 'data-owner-area="verification" type="button" hidden' in member_page
    assert owner.get('/v1/auth/me').json()['can_invite'] is True
    assert member.get('/v1/auth/me').json()['can_invite'] is False
    assert owner.get('/static/verification-tasks.js').status_code==200
    listed=owner.get('/v1/admin/verification-tasks')
    assert listed.status_code==200
    data=listed.json()
    tolls=[task for task in data['tasks'] if task['domain']=='casetas']
    assert len(tolls)>=3
    assert all(task['status']=='PENDING' and task['evidence_reference'] is None for task in tolls)
    candidates=[task for task in tolls if task['task_key'].startswith('rnc25_plaza_')]
    assert len(candidates)==50
    assert len({task['task_key'] for task in candidates})==50
    assert all(task['status']=='PENDING' and 'Red Nacional de Caminos 2025' in task['source_label']
               for task in candidates)
    assert all(task['source_url']=='https://rnc.imt.mx/recursos/ShapeFiles/Plaza_cobro_shapefiles2025.zip'
               for task in candidates)
    assert data['counts']['pending']==len(data['tasks'])
    assert not any('secret' in task or 'token' in task for task in data['tasks'])

    session=owner.get('/v1/auth/me').json()
    task=tolls[0]
    endpoint='/v1/admin/verification-tasks/'+task['id']
    patch={'revision':task['revision'],'status':'VERIFIED','evidence_reference':'https://source.example/record',
           'note':'Comprobado contra fuente oficial en fecha de revisión.'}
    assert owner.patch(endpoint,json=patch).status_code==403
    headers={'X-CSRF-Token':session['csrf_token']}
    assert owner.patch(endpoint,json={**patch,'evidence_reference':None,'note':None},headers=headers).status_code==422
    updated=owner.patch(endpoint,json=patch,headers=headers)
    assert updated.status_code==200
    assert updated.json()['task']['status']=='VERIFIED'
    assert updated.json()['task']['revision']==task['revision']+1
    assert owner.patch(endpoint,json=patch,headers=headers).status_code==409
    assert member.patch(endpoint,json=patch,headers={'X-CSRF-Token':member.get('/v1/auth/me').json()['csrf_token']}).status_code==403

    app2=create_platform(Settings(database_url=url,auto_create=False))
    with app2.state.accounts.Session() as db:
        saved=db.get(VerificationTask,task['id'])
        assert saved.status=='VERIFIED'
        assert saved.evidence_reference=='https://source.example/record'


def test_owner_can_add_pending_task_but_cannot_store_personal_or_banking_data(tmp_path):
    app=create_platform(Settings(database_url='sqlite+pysqlite:///'+str(tmp_path/'create.sqlite')))
    client=TestClient(app);create_user(app,client,'owner@example.org')
    app.state.accounts.platform_owner_id=client.get('/v1/auth/me').json()['id']
    csrf=client.get('/v1/auth/me').json()['csrf_token']
    body={'task_key':'new_source_to_check','domain':'pey','priority':'HIGH','title':'Confirm current provider detail',
          'description':'Compare the state with the official documentation.',
          'source_label':'Provider documentation','source_url':'https://docs.example.org/current'}
    assert client.post('/v1/admin/verification-tasks',json=body).status_code==403  # CSRF required
    result=client.post('/v1/admin/verification-tasks',json=body,headers={'X-CSRF-Token':csrf})
    assert result.status_code==201 and result.json()['task']['status']=='PENDING'
    assert client.post('/v1/admin/verification-tasks',json=body,headers={'X-CSRF-Token':csrf}).status_code==409
    private={**body,'task_key':'email_in_task','description':'Verify delivery for person@example.org.'}
    assert client.post('/v1/admin/verification-tasks',json=private,headers={'X-CSRF-Token':csrf}).status_code==422
    clabe={**body,'task_key':'account_number_in_task','description':'Compare account 012345678901234567 before activation.'}
    assert client.post('/v1/admin/verification-tasks',json=clabe,headers={'X-CSRF-Token':csrf}).status_code==422


def test_verification_migration_refuses_to_discard_recorded_tasks(tmp_path,monkeypatch):
    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    url='sqlite:///'+str(tmp_path/'migrate.sqlite')
    monkeypatch.setenv('DATABASE_URL',url)
    config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))
    command.upgrade(config,'021')
    command.upgrade(config,'022')
    with sqlite3.connect(str(tmp_path/'migrate.sqlite')) as db:
        db.execute('INSERT INTO verification_tasks '
                   '(id,task_key,domain,priority,title,description,source_label,status,created_at,updated_at,revision) '
                   'VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                   ('a'*32,'synthetic_task','pey','NORMAL','Synthetic migration row',
                    'No operational details.','Synthetic fixture','PENDING',1,1,1))
    with pytest.raises(RuntimeError,match='Refusing to discard verification tasks'):
        command.downgrade(config,'021')
    with sqlite3.connect(str(tmp_path/'migrate.sqlite')) as db:
        assert db.execute('SELECT task_key FROM verification_tasks').fetchone()==('synthetic_task',)
