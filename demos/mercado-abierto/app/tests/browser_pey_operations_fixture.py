"""Loopback acceptance only; all pey network transports prohibited."""
import base64, os, tempfile
from decimal import Decimal
from unittest.mock import patch
from fastapi.testclient import TestClient
import uvicorn
from rio_pey_codi.platform import Settings,create_platform
from rio_pey_codi.models import MerchantPeySecret
from rio_pey_codi.pey_extended import FullPeyGateway
from test_merchant_pey_checkout import activate_fixture

if __name__=='__main__':
    if os.environ.get('RIO_LOCAL_ONLY')!='1':raise SystemExit('Local fixture only')
    key=b'z'*32;os.environ['RPG_MERCHANT_VAULT_KEY']=base64.urlsafe_b64encode(key).decode()
    with tempfile.TemporaryDirectory() as d, patch.object(Settings,'validate',lambda self:None), patch('rio_pey_codi.pey._open_provider',side_effect=AssertionError('No provider network')), patch('rio_pey_codi.pey_extended._open_provider',side_effect=AssertionError('No provider network')):
        FullPeyGateway.push=lambda self,**kw:{'transactionId':'TX1','codiId':'12345678901234567890'}
        FullPeyGateway.transaction=lambda self,tx:{'id':tx,'status':'PAID','currency':'MXN','paymentMethod':'CODI','payableType':'API_CODI_PN','amount':Decimal('1.01'),'amountBreakdown':{'base':Decimal('1.01')},'datePaid':1790000000}
        FullPeyGateway.register_account=lambda self,**kw:{'id':'BANK1','codiStatus':'PENDING'}
        FullPeyGateway.account=lambda self,ident:{'id':ident,'codiStatus':'ACTIVE','alias':'Cuenta local','name':'Titular','clabe':'0'*18}
        app=create_platform(Settings(mode='LIVE',live_enabled=True,database_url='sqlite+pysqlite:///'+d+'/db.sqlite',public_url='http://127.0.0.1:8772'))
        c=TestClient(app);mid=c.post('/v1/auth/signup',json={'email':'browser@example.com','password':'synthetic-password-123','business_name':'Negocio local'}).json()['merchant_id']
        token=next(m['token'] for m in app.state.mailer.outbox if m['kind']=='verify');c.post('/v1/auth/verify-email',json={'token':token})
        with app.state.accounts.Session.begin() as db:
            db.add(MerchantPeySecret(merchant_id=mid,updated_at=1));db.flush();activate_fixture(db,key,mid,'a')
        uvicorn.run(app,host='127.0.0.1',port=8772,log_level='warning',access_log=False)
