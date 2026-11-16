import json
from unittest.mock import patch

import pytest
from rio_pey_codi.pey import LivePeyGateway, ProviderError


def test_live_request_matches_documented_fields_without_network():
    gateway=LivePeyGateway(api_key="example-not-real",bank_account_id="bank-fixture")
    with patch("rio_pey_codi.pey._open_provider") as send:
        req=gateway.prepare_qr_request(intent_id="x",amount_minor=1,concept="Primer centavo",numref="123",expiration_s=600)
        qr=gateway.parse_qr_response(201, b'{"id":"qr-xyz","qrString":"CoDi payload from fixture"}')
        send.assert_not_called()
    assert qr.provider_id=="qr-xyz"
    assert req.full_url=="https://api.pey.mx/codi/qr"
    assert req.get_method()=="POST"
    assert '"amount":0.01' in req.data.decode()
    assert '"amount":1' not in req.data.decode()
    assert json.loads(req.data)=={"amount":0.01,"concept":"Primer centavo","numRef":"123","bankAccountId":"bank-fixture","expiration":600,"metadata":{"rioIntentId":"x"}}


def test_unknown_response_mapping_fails_closed():
    gateway=LivePeyGateway(api_key="example-not-real",bank_account_id="bank-fixture")
    with pytest.raises(ProviderError,match="attested schema"):
        gateway.parse_qr_response(201, b'{"foo":"bar"}')


def test_live_transport_does_not_retry_when_the_result_is_uncertain():
    gateway=LivePeyGateway(api_key="example-not-real",bank_account_id="bank-fixture")
    with patch("rio_pey_codi.pey._open_provider", side_effect=TimeoutError('synthetic timeout')) as f:
        with pytest.raises(ProviderError,match="uncertain; reconcile before reissuing"):
            gateway.create_qr(intent_id="x",amount_minor=5000,concept="Pedido",numref="1",expiration_s=600)
        assert f.call_count==1


def test_user_qr_example_maps_pesos_and_merchant_account_without_network():
    gateway = LivePeyGateway(api_key='synthetic-key', bank_account_id='merchant-account-fixture')
    with patch('rio_pey_codi.pey._open_provider') as transport:
        request = gateway.prepare_qr_request(
            intent_id='order-fixture', amount_minor=15000, concept='Pedido #12345',
            expiration_s=600, numref='12345',
        )
        result = gateway.parse_qr_response(201, b'{"id":"qr-fixture","qrString":"synthetic-qr"}')
    assert request.full_url == 'https://api.pey.mx/codi/qr'
    assert request.get_method() == 'POST'
    assert request.get_header('Authorization') == 'Bearer synthetic-key'
    assert json.loads(request.data) == {
        'amount': 150, 'concept': 'Pedido #12345', 'expiration': 600,
        'numRef': '12345', 'bankAccountId': 'merchant-account-fixture',
        'metadata': {'rioIntentId':'order-fixture'},
    }
    assert result.provider_id == 'qr-fixture'
    transport.assert_not_called()


@pytest.mark.parametrize("reference,expiration", [("abc",600),("12345678",600),("123",359)])
def test_rejects_invalid_request_without_transport(reference, expiration):
    gateway = LivePeyGateway(api_key="synthetic", bank_account_id="fixture")
    with patch("rio_pey_codi.pey._open_provider") as transport:
        with pytest.raises(ProviderError, match="supported CoDi"):
            gateway.prepare_qr_request(intent_id="x", amount_minor=1, concept="Demo",
                                       numref=reference, expiration_s=expiration)
        transport.assert_not_called()
