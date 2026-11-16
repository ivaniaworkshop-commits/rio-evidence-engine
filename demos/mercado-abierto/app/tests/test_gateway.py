import base64
import dataclasses
import json
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from rio_pey_codi.app import Config, create_app, parse_provider_amount
from rio_pey_codi.pey import MockPeyGateway, ProviderError
from rio_pey_codi.signatures import InvalidWebhook, make_signature, verify_signature

TOKEN = "integration-test-server-token-not-live-use"
SECRET = "whsec_" + base64.b64encode(b"a-test-webhook-key-not-production-32").decode()
HEAD = {"Authorization": f"Bearer {TOKEN}"}

@pytest.fixture
def setup(tmp_path):
    config = Config(mode="DEMO",merchant="merchant_demo",store_file=str(tmp_path / "payments.sqlite3"),server_token=TOKEN,webhook_secret=SECRET)
    app = create_app(config)
    return TestClient(app), app


def payload(**changes):
    d={"merchant":"merchant_demo","order_id":"o-1001","amount_minor":5000,"concept":"2 panes + 0.5 kg jitomate",
       "numref":"1001","expiration_s":600}
    d.update(changes)
    return d


def order(client,**changes):
    return client.post("/v1/intents",json=payload(**changes),headers=HEAD)


def webhook(client,app,event_id="evt_100",**changes):
    row=app.state.store.get(changes.pop("intent_id"))
    data={"type":"codi.qr.payment_received","codiQrId":row["provider_qr_id"],"amount":"50.00",
          "numRef":row["numref"],"transactionId":"tx-1001","apiKeyId":"demo_api_key"}
    data.update(changes)
    raw=json.dumps(data,separators=(",", ":")).encode()
    now=int(time.time())
    headers={"webhook-id":event_id,"webhook-timestamp":str(now),"webhook-signature":make_signature(SECRET,event_id,now,raw)}
    return client.post("/v1/webhooks/pey",content=raw,headers=headers)


def test_health_does_not_claim_production(setup):
    client,_=setup
    d=client.get("/healthz").json()
    assert d["mode"]=="DEMO" and d["payment_settlement"]=="NOT_OBSERVED"


def test_auth_enforced(setup):
    client,_=setup
    assert client.post("/v1/intents",json=payload()).status_code==401
    assert client.post("/v1/intents",json=payload(),headers={"Authorization":"Bearer wrong"}).status_code==401


def test_create_mock_intent_is_not_payable(setup):
    client,_=setup
    r=order(client)
    assert r.status_code==201, r.text
    d=r.json()
    assert d["intent"]["amount_minor"]==5000
    assert d["intent"]["status"]=="QR_ISSUED"
    assert "NO PAGABLE" in d["intent"]["qr_display"]
    assert d["bank_payment_confirmed"] is False


def test_idempotency_does_not_call_provider_again(setup):
    client,_=setup
    a=order(client).json()
    b=order(client).json()
    assert a["intent"]["id"]==b["intent"]["id"]
    assert b["status"]=="REPLAY_NO_PROVIDER_RETRY"


def test_idempotency_different_amount_fails(setup):
    client,_=setup
    order(client)
    assert order(client,amount_minor=5200).status_code==409


def test_cross_merchant_blocked(setup):
    client,_=setup
    assert order(client,merchant="another_business").status_code==403


def test_reuse_reference_for_another_order_blocked(setup):
    client,_=setup
    order(client)
    assert order(client,order_id="other-order").status_code==409


@pytest.mark.parametrize("bad",[0,-1,True,2.25,"5000",100_000_001])
def test_exact_minor_units_only(setup,bad):
    client,_=setup
    assert order(client,amount_minor=bad).status_code==422


def test_bad_identifiers_rejected(setup):
    client,_=setup
    assert order(client,order_id="invalid/path").status_code==422
    assert order(client,numref="ñ").status_code==422


def test_provider_report_not_bank_settlement(setup):
    client,app=setup
    r=order(client).json()["intent"]
    outcome=webhook(client,app,intent_id=r["id"])
    assert outcome.status_code==200, outcome.text
    assert outcome.json()["outcome"]=="PROVIDER_REPORTED"
    assert outcome.json()["bank_settled"] is False
    get=client.get(f"/v1/intents/{r['id']}",headers=HEAD).json()
    assert get["provider_reported_payment"] is True
    assert get["bank_payment_confirmed"] is False


def test_repeated_webhook_event_is_idempotent(setup):
    client,app=setup
    ident=order(client).json()["intent"]["id"]
    assert webhook(client,app,intent_id=ident).json()["outcome"]=="PROVIDER_REPORTED"
    assert webhook(client,app,intent_id=ident).json()["outcome"]=="DUPLICATE_EVENT"


def test_second_distinct_event_same_transaction_id_no_second_payment(setup):
    client,app=setup
    ident=order(client).json()["intent"]["id"]
    webhook(client,app,intent_id=ident)
    r=webhook(client,app,intent_id=ident,event_id="evt_101")
    assert r.json()["outcome"]=="DUPLICATE_TRANSACTION"


def test_modified_event_with_same_id_rejected(setup):
    client,app=setup
    ident=order(client).json()["intent"]["id"]
    webhook(client,app,intent_id=ident)
    assert webhook(client,app,intent_id=ident,amount="49.00").status_code==409


def test_amount_mismatch_rejected_without_state_mutation(setup):
    client,app=setup
    ident=order(client).json()["intent"]["id"]
    assert webhook(client,app,intent_id=ident,amount="49.99").status_code==409
    assert app.state.store.get(ident)["status"]=="QR_ISSUED"


def test_transaction_mismatch_rejected(setup):
    client,app=setup
    ident=order(client).json()["intent"]["id"]
    webhook(client,app,intent_id=ident)
    assert webhook(client,app,intent_id=ident,event_id="evt_102",transactionId="tx-different").status_code==409


def test_reference_mismatch_rejected(setup):
    client,app=setup
    ident=order(client).json()["intent"]["id"]
    assert webhook(client,app,intent_id=ident,numRef="other").status_code==409


def test_qr_mismatch_rejected(setup):
    client,app=setup
    ident=order(client).json()["intent"]["id"]
    r=webhook(client,app,intent_id=ident,codiQrId="unknown")
    assert r.status_code==200
    assert r.json()["outcome"]=="PENDING_LINKAGE"
    assert app.state.store.get(ident)["status"]=="QR_ISSUED"


def test_invalid_signature_rejected(setup):
    client,app=setup
    ident=order(client).json()["intent"]["id"]
    r=webhook(client,app,intent_id=ident)
    assert r.status_code==200
    raw=b'{"type":"codi.qr.payment_received"}'
    assert client.post("/v1/webhooks/pey",content=raw,headers={"webhook-id":"event_bad","webhook-timestamp":str(int(time.time())),"webhook-signature":"v1,ZmFrZQ=="}).status_code==401


def test_stale_signature_rejected():
    old=int(time.time())-1000
    body=b"{}"
    headers={"webhook-id":"evt-a","webhook-timestamp":str(old),"webhook-signature":make_signature(SECRET,"evt-a",old,body)}
    with pytest.raises(InvalidWebhook):
        verify_signature(headers,body,SECRET)


def test_future_signature_rejected():
    new=int(time.time())+1000
    body=b"{}"
    headers={"webhook-id":"evt-a","webhook-timestamp":str(new),"webhook-signature":make_signature(SECRET,"evt-a",new,body)}
    with pytest.raises(InvalidWebhook):
        verify_signature(headers,body,SECRET)


def test_unknown_event_type_not_paid(setup):
    client,app=setup
    ident=order(client).json()["intent"]["id"]
    assert webhook(client,app,intent_id=ident,type="other.event").status_code==422
    assert app.state.store.get(ident)["status"]=="QR_ISSUED"


def test_duplicate_json_keys_rejected(setup):
    client,_=setup
    now=int(time.time())
    raw=b'{"type":"codi.qr.payment_received","type":"other"}'
    headers={"webhook-id":"evt_dup","webhook-timestamp":str(now),"webhook-signature":make_signature(SECRET,"evt_dup",now,raw)}
    assert client.post("/v1/webhooks/pey",content=raw,headers=headers).status_code==400


def test_large_webhook_body_rejected(setup):
    client,_=setup
    assert client.post("/v1/webhooks/pey",content=b"X"*65537).status_code==413


def test_json_amount_precision_is_exact():
    assert parse_provider_amount("0.01")==1
    assert parse_provider_amount("150")==15000
    assert parse_provider_amount("150.00")==15000
    for bad in ["1.001","NaN","Infinity","-1.00","0",True]:
        with pytest.raises(ValueError): parse_provider_amount(bad)


def test_live_configuration_fails_closed(tmp_path):
    cfg=Config(mode="LIVE",store_file=str(tmp_path/"payment.sqlite3"))
    with pytest.raises(ValueError, match="readiness"):
        create_app(cfg)
    # Even with attested flags, secrets/response mapping must be present.
    flags=dict(live_enabled=True,docs_attested=True,amount_unit_attested=True,webhook_contract_attested=True,
               account_active_attested=True,durable_host_attested=True,compliance_attested=True)
    with pytest.raises(ValueError, match="secrets"):
        create_app(dataclasses.replace(cfg,**flags))


def test_demo_cannot_enable_live_flag(tmp_path):
    with pytest.raises(ValueError):create_app(Config(mode="DEMO",live_enabled=True,store_file=str(tmp_path/"foo.db")))


class BrokenProvider:
    def create_qr(self,**_kwargs):
        raise ProviderError("network timeout; may have received request")


def test_provider_uncertain_disables_automatic_retry(tmp_path):
    cfg=Config(store_file=str(tmp_path/"d.db"),merchant="merchant_demo",server_token=TOKEN)
    app=create_app(cfg,provider=BrokenProvider())
    client=TestClient(app)
    first=order(client)
    assert first.status_code==502
    second=order(client)
    assert second.status_code==201
    assert second.json()["status"]=="REPLAY_NO_PROVIDER_RETRY"
    assert second.json()["intent"]["status"]=="PROVIDER_UNCERTAIN"


def test_parallel_same_order_reserves_once(tmp_path):
    cfg=Config(store_file=str(tmp_path/"d.db"),merchant="merchant_demo",server_token=TOKEN)
    app=create_app(cfg)
    def call(_):
        return TestClient(app).post("/v1/intents",json=payload(),headers=HEAD).json()
    with ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(call,range(12)))
    ids={x["intent"]["id"] for x in results}
    assert len(ids)==1
    assert sum(x["status"]=="CREATED" for x in results)==1
    with app.state.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM intents").fetchone()[0]==1

def test_signed_event_before_qr_mapping_is_reconciled(tmp_path):
    """QR provider event arrives before the local QR ID is written."""
    cfg=Config(store_file=str(tmp_path/"p.sqlite3"),merchant="merchant_demo",server_token=TOKEN,webhook_secret=SECRET)
    class EarlyWebhookProvider:
        def __init__(self):self.client=None
        def create_qr(self, *, intent_id, **kwargs):
            from rio_pey_codi.pey import QRResult
            obj={"type":"codi.qr.payment_received","codiQrId":"provider-prerecorded-qr",
                 "amount":"50.00","numRef":"1001","transactionId":"early-tx","apiKeyId":"demo_api_key"}
            raw=json.dumps(obj).encode()
            now=int(time.time())
            headers={"webhook-id":"evt_before_link","webhook-timestamp":str(now),
                     "webhook-signature":make_signature(SECRET,"evt_before_link",now,raw)}
            early=self.client.post("/v1/webhooks/pey",content=raw,headers=headers)
            assert early.status_code==200,early.text
            assert early.json()["outcome"]=="PENDING_LINKAGE"
            return QRResult("provider-prerecorded-qr","DEMO NO PAGABLE")
    provider=EarlyWebhookProvider()
    app=create_app(cfg,provider=provider)
    client=TestClient(app)
    provider.client=client
    created=order(client)
    assert created.status_code==201
    assert created.json()["intent"]["status"]=="PROVIDER_REPORTED"
    with app.state.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM pending_events").fetchone()[0]==0
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==1


def test_pending_event_does_not_settle_unrelated_qr(setup):
    client,app=setup
    first=order(client).json()["intent"]
    r=webhook(client,app,intent_id=first["id"],codiQrId="no-linked-qr",amount="10.00")
    assert r.json()["outcome"]=="PENDING_LINKAGE"
    assert app.state.store.get(first["id"])["status"]=="QR_ISSUED"


def test_pending_event_same_id_changed_payload_rejected(setup):
    client,app=setup
    ident=order(client).json()["intent"]["id"]
    kwargs=dict(intent_id=ident,codiQrId="missing")
    assert webhook(client,app,**kwargs).json()["outcome"]=="PENDING_LINKAGE"
    assert webhook(client,app,**kwargs,amount="1.00").status_code==409

def test_live_event_identity_rejected_without_real_network(tmp_path):
    # This only tests the LOCAL code gate, never a bank transfer.
    cfg=Config(mode="LIVE",merchant="merchant_demo",store_file=str(tmp_path/"durable.db"),
               server_token=TOKEN,webhook_secret=SECRET,pey_key="fake-but-long-key-value",
               pey_api_key_id="authorized-provider-key-id",bank_account_id="bank-account-fixture",
               response_id_field="attested_response_id",response_display_field="attested_payload",
               live_enabled=True,docs_attested=True,amount_unit_attested=True,
               webhook_contract_attested=True,account_active_attested=True,
               durable_host_attested=True,compliance_attested=True)
    app=create_app(cfg,provider=MockPeyGateway())
    client=TestClient(app)
    ident=order(client).json()["intent"]["id"]
    rejected=webhook(client,app,intent_id=ident)
    assert rejected.status_code==409
    assert "API key identity mismatch" in rejected.text
    assert app.state.store.get(ident)["status"]=="QR_ISSUED"
    accepted=webhook(client,app,intent_id=ident,apiKeyId="authorized-provider-key-id")
    assert accepted.status_code==200
    assert accepted.json()["bank_settlement"]=="NOT_VERIFIED"


def test_pending_event_amount_mismatch_survives_for_manual_audit(tmp_path):
    cfg=Config(store_file=str(tmp_path/"p.sqlite3"),merchant="merchant_demo",server_token=TOKEN,webhook_secret=SECRET)
    class Provider:
        def create_qr(self,**kwargs):
            from rio_pey_codi.pey import QRResult
            raw=json.dumps({"type":"codi.qr.payment_received","codiQrId":"early-bad-amount","amount":"49.99",
                            "numRef":"1001","transactionId":"tx-manual","apiKeyId":"demo_api_key"}).encode()
            ts=int(time.time())
            resp=self.client.post("/v1/webhooks/pey",content=raw,headers={"webhook-id":"e-mismatch","webhook-timestamp":str(ts),
                             "webhook-signature":make_signature(SECRET,"e-mismatch",ts,raw)})
            assert resp.status_code==200
            return QRResult("early-bad-amount","DEMO NO PAGABLE")
    provider=Provider()
    app=create_app(cfg,provider=provider)
    provider.client=TestClient(app)
    created=order(provider.client)
    assert created.status_code==201
    assert created.json()["intent"]["status"]=="QR_ISSUED"
    with app.state.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM pending_events").fetchone()[0]==1
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==0
