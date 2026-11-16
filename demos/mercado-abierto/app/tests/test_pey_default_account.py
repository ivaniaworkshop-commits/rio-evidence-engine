import json
import unittest
from unittest.mock import patch
from rio_pey_codi import pey

class Reply:
    status=201
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,n):return b'{"id":"qr-123","qrString":"payload"}'

class LiveTests(unittest.TestCase):
    def test_default_account_and_variable_amount(self):
        gateway=pey.LivePeyGateway(api_key='dummy',bank_account_id='')
        with patch.object(pey,'_open_provider',return_value=Reply()) as opener:
            qr=gateway.create_qr(intent_id='i',amount_minor=12345,concept='Venta',numref='123',expiration_s=600)
        data=json.loads(opener.call_args.args[0].data)
        self.assertEqual(data['amount'],123.45)
        self.assertNotIn('bankAccountId',data)
        self.assertEqual(qr.provider_id,'qr-123')
    def test_explicit_account(self):
        req=pey.LivePeyGateway(api_key='dummy',bank_account_id='account').prepare_qr_request(intent_id='i',amount_minor=1,concept='Venta',numref='1',expiration_s=600)
        self.assertEqual(json.loads(req.data)['bankAccountId'],'account')
    def test_timeout_is_not_retried(self):
        gateway=pey.LivePeyGateway(api_key='dummy',bank_account_id='')
        with patch.object(pey,'_open_provider',side_effect=TimeoutError()) as op:
            with self.assertRaises(pey.ProviderError):
                gateway.create_qr(intent_id='i',amount_minor=99,concept='Venta',numref='1',expiration_s=600)
            self.assertEqual(op.call_count,1)

if __name__ == '__main__':unittest.main()
