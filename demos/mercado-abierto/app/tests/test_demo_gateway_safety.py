"""The known live gateway must never be wired into either DEMO application."""
from unittest.mock import patch

import pytest

from rio_pey_codi.app import Config, create_app
from rio_pey_codi.pey import LivePeyGateway, ProviderError
from rio_pey_codi.platform import Settings, create_platform


@pytest.mark.parametrize("application", ["gateway", "platform"])
def test_live_pey_gateway_is_rejected_even_in_demo(application, tmp_path):
    provider = LivePeyGateway(api_key="synthetic-unused", bank_account_id="fixture")
    with patch("rio_pey_codi.pey._open_provider") as send:
        reason = ("Live pey gateway is blocked" if application == "gateway"
                  else "LIVE uses only persisted merchant credentials")
        with pytest.raises(ValueError, match=reason):
            if application == "gateway":
                create_app(Config(store_file=str(tmp_path / "gateway.sqlite")), provider=provider)
            else:
                create_platform(Settings(database_url="sqlite+pysqlite:///" + str(tmp_path / "platform.sqlite")),
                                provider=provider)
        send.assert_not_called()


def test_demo_checkout_never_uses_the_live_adapter(tmp_path):
    from fastapi.testclient import TestClient

    app = create_platform(Settings(database_url="sqlite+pysqlite:///" + str(tmp_path / "demo.sqlite")))
    client = TestClient(app)
    account = {"email":"demo@example.org", "password":"synthetic-password-123"}
    signup = client.post('/v1/auth/signup', json={**account, "business_name":"Demo"})
    assert signup.status_code == 201
    token = app.state.mailer.outbox[-1]['token']
    assert client.post('/v1/auth/verify-email', json={"token":token}).status_code == 200
    login = client.post('/v1/auth/login', json=account)
    assert login.status_code == 200
    with patch("rio_pey_codi.pey._open_provider") as send:
        result = client.post('/v1/checkout/qr', headers={"x-csrf-token":login.json()['csrf_token']}, json={
            "merchant_id":signup.json()['merchant_id'], "order_id":"demo-sale", "amount_minor":100,
            "concept":"Demo", "numref":"1", "expiration_s":600,
        })
        assert result.status_code == 201
        assert result.json()['mode'] == 'DEMO'
        assert result.json()['intent']['bank_payment_confirmed'] is False
        send.assert_not_called()
