import json
from pathlib import Path
from unittest.mock import patch
import pytest
import jsonschema
from rio_pey_codi.pey_extended import FullPeyGateway, encode
from rio_pey_codi.pey import ProviderError
from decimal import Decimal

CONTRACT=json.loads((Path(__file__).parent/'fixtures/pey-openapi-2026-10-20.json').read_text())

@pytest.mark.parametrize('kind',['bank','push','link','update'])
def test_post_requests_match_current_official_schema(kind):
    api=FullPeyGateway(api_key='synthetic',bank_account_id='BANK1');captured=[]
    def capture(path,payload):
        captured.append((path,json.loads(encode(payload))))
        return {'id':'RESOURCE1','codiStatus':'PENDING','transactionId':'TX1','codiId':'12345678901234567890','url':'https://app.mipey.mx/payment-link/RESOURCE1'}
    api.post=capture
    if kind=='bank':api.register_account(alias='Cuenta',name='Titular',clabe='0'*18,entity='PERSON')
    if kind=='push':api.push(amount_minor=101,phone='5512345678',concept='Venta',numref='123',expiration_s=360,operation_id='a'*32)
    if kind=='link':api.create_link(amount_minor=101,operation_id='a'*32,success_url='https://example.com/success',back_url='https://example.com/back',has_tip=True)
    if kind=='update':api.update_link('RESOURCE1',101)
    for path,payload in captured:
        jsonschema.Draft202012Validator(CONTRACT['paths'][path]['post']['requestBody']['content']['application/json']['schema']).validate(payload)
    assert len(captured)==1

@pytest.mark.parametrize(('method','args','path'),[
    ('account',('ACCOUNT1',),'/bank-account/ACCOUNT1'),
    ('transaction',('TX1',),'/transaction/TX1'),
    ('link',('LINK1',),'/payment-link/LINK1'),
    ('qr_transactions',('QR1',),'/transaction/codi/qr/QR1'),
    ('transactions',(),'/transaction/api-key'),
])
def test_lookup_fixed_paths(method,args,path):
    api=FullPeyGateway(api_key='synthetic',bank_account_id='');seen=[]
    api._get=lambda p,**kw:seen.append(p) or {}
    getattr(api,method)(*args);assert seen==[path]

def test_bank_pagination_encoded():
    api=FullPeyGateway(api_key='synthetic',bank_account_id='');seen=[];api._get=lambda p:seen.append(p) or {}
    api.transactions(account_id='BANK1',token='a+/=');assert seen==['/transaction/bank-account/BANK1?nextToken=a%2B%2F%3D']

def test_post_timeout_no_retry():
    api=FullPeyGateway(api_key='synthetic',bank_account_id='')
    with patch('rio_pey_codi.pey_extended._open_provider',side_effect=TimeoutError()) as transport:
        with pytest.raises(ProviderError):api.post('/payment-link/update',{'paymentLinkId':'LINK1','amount':Decimal('1.01')})
    assert transport.call_count==1

def test_exact_decimal_nested():
    assert encode({'amount':Decimal('999999.99'),'items':[Decimal('1.01')]})=='{"amount":999999.99,"items":[1.01]}'
