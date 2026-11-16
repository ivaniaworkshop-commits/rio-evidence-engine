import pytest
from rio_pey_codi.models import database, User, Merchant, Intent
from rio_pey_codi.payments_db import PaymentRepository, PaymentConflict

@pytest.fixture
def ctx(tmp_path):
    session=database('sqlite+pysqlite:///'+str(tmp_path/'test.sqlite'),auto_create=True)
    with session.begin() as db:
        for n in ('a','b'):
            db.add(User(id=n*32,email=n+'@example.invalid',password_hash='synthetic',created_at=1))
        db.flush()
        for n in ('a','b'):
            db.add(Merchant(id=n*32,name='Synthetic',owner_id=n*32,created_at=1))
    return session, PaymentRepository(session)

def test_tenant_webhook_cannot_confirm_another_merchants_qr(ctx):
    session, repo=ctx
    row,created=repo.reserve('a'*32,'sale1',1,'Test','123',600)
    assert created
    repo.qr_issued(row.id,'qr-a','payload')
    with pytest.raises(PaymentConflict):
        repo.confirm_event('evt1',b'body','qr-a',1,'123','txn1',merchant_id='b'*32)
    with session() as db:
        assert db.get(Intent,row.id).status=='QR_ISSUED'
    assert repo.confirm_event('evt1',b'body','qr-a',1,'123','txn1',merchant_id='a'*32)['outcome']=='PROVIDER_REPORTED'
    with pytest.raises(PaymentConflict):
        repo.confirm_event('evt1',b'body','qr-a',1,'123','txn1',merchant_id='b'*32)

def test_early_tenant_webhook_must_retry_and_is_not_stored(ctx):
    session,repo=ctx
    with pytest.raises(PaymentConflict):
        repo.confirm_event('early',b'body','qr-later',1,'12','txn',merchant_id='a'*32)
    row,_=repo.reserve('a'*32,'sale2',1,'Test','12',600)
    repo.qr_issued(row.id,'qr-later','payload')
    assert repo.confirm_event('early',b'body','qr-later',1,'12','txn',merchant_id='a'*32)['outcome']=='PROVIDER_REPORTED'
