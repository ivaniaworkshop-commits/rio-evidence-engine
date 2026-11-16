"""RÍO gateway API. DEMO default; fail-closed live readiness. NO settlement claims."""
import base64
import decimal
import hmac
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from .pey import LivePeyGateway, MockPeyGateway
from .signatures import InvalidWebhook, verify_signature
from .store import PaymentStore, StoreError


@dataclass(frozen=True)
class Config:
    mode: str = "DEMO"
    merchant: str = "merchant_demo"
    store_file: str = "./rio_pey_codi.sqlite3"
    server_token: str = field(default="", repr=False)
    webhook_secret: str = field(default="", repr=False)
    pey_key: str = field(default="", repr=False)
    pey_api_key_id: str = field(default="", repr=False)
    bank_account_id: str = field(default="", repr=False)
    response_id_field: str = ""
    response_display_field: str = ""
    live_enabled: bool = False
    docs_attested: bool = False
    amount_unit_attested: bool = False
    webhook_contract_attested: bool = False
    account_active_attested: bool = False
    durable_host_attested: bool = False
    compliance_attested: bool = False

    @staticmethod
    def from_env():
        flag = lambda k: os.environ.get(k, "").lower() == "true"
        return Config(mode=os.environ.get("RPG_MODE","DEMO"),merchant=os.environ.get("RPG_MERCHANT_ID","merchant_demo"),
                      store_file=os.environ.get("RPG_STORE_FILE","./rio_pey_codi.sqlite3"),
                      server_token=os.environ.get("RPG_SERVER_TOKEN",""),webhook_secret=os.environ.get("PEY_WEBHOOK_SECRET",""),
                      pey_key=os.environ.get("PEY_API_KEY",""),pey_api_key_id=os.environ.get("PEY_API_KEY_ID",""),
                      bank_account_id=os.environ.get("PEY_BANK_ACCOUNT_ID",""),
                      response_id_field=os.environ.get("PEY_QR_ID_RESPONSE_FIELD",""),
                      response_display_field=os.environ.get("PEY_QR_DISPLAY_RESPONSE_FIELD",""),
                      live_enabled=flag("PAYMENTS_LIVE_ENABLED"),docs_attested=flag("PEY_DOCS_ATTESTED"),
                      amount_unit_attested=flag("PEY_AMOUNT_UNIT_ATTESTED"),
                      webhook_contract_attested=flag("PEY_WEBHOOK_CONTRACT_ATTESTED"),
                      account_active_attested=flag("PEY_ACCOUNT_ACTIVE_ATTESTED"),
                      durable_host_attested=flag("RPG_SINGLE_HOST_DURABLE_DB_ATTESTED"),
                      compliance_attested=flag("RPG_COMPLIANCE_AND_AUTH_ATTESTED"))

    def assert_ready(self):
        if self.mode not in ("DEMO", "LIVE"):
            raise ValueError("Invalid mode")
        if self.mode == "LIVE":
            flags = [self.live_enabled,self.docs_attested,self.amount_unit_attested,self.webhook_contract_attested,
                     self.account_active_attested,self.durable_host_attested,self.compliance_attested]
            if not all(flags):
                raise ValueError("LIVE is blocked by missing explicit readiness attestations")
            if not all([len(self.server_token)>=32,len(self.webhook_secret)>=16,len(self.pey_key)>=16,
                        self.pey_api_key_id,self.bank_account_id,self.response_id_field,self.response_display_field]):
                raise ValueError("LIVE is blocked by missing verified secrets or provider response mapping")
            if self.store_file in (":memory:",""):
                raise ValueError("LIVE requires persistent single-host SQLite storage")
        else:
            if self.live_enabled:
                raise ValueError("Cannot enable live payments in DEMO mode")


class CreateIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    merchant: str = Field(min_length=1,max_length=70)
    order_id: str = Field(min_length=1,max_length=70)
    amount_minor: StrictInt = Field(gt=0,le=100_000_000)
    concept: str = Field(min_length=1,max_length=140)
    numref: str = Field(min_length=1,max_length=40)
    expiration_s: StrictInt = Field(ge=60,le=3600)

    @field_validator("merchant","order_id","numref")
    @classmethod
    def safe_identifiers(cls,value):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*",value):
            raise ValueError("Only ascii identifiers allowed")
        return value


def parse_provider_amount(value):
    if isinstance(value, bool) or not isinstance(value, (int, str, float, decimal.Decimal)):
        raise ValueError("Unexpected amount")
    # json.loads defaults to float: round-trip decimal string must have <=2 exact decimal digits.
    try:
        d = decimal.Decimal(str(value))
    except decimal.InvalidOperation as exc:
        raise ValueError("Invalid decimal amount") from exc
    if not d.is_finite() or not decimal.Decimal('0.01') <= d <= 1_000_000:
        raise ValueError("Unexpected payment range")
    cents = d.quantize(decimal.Decimal('0.01'))
    if d != cents:
        raise ValueError("Unexpected payment precision")
    return int(cents * 100)



def create_app(config:Config|None=None, provider=None) -> FastAPI:
    cfg=config or Config.from_env()
    cfg.assert_ready()
    if isinstance(provider, LivePeyGateway):
        raise ValueError("Live pey gateway is blocked pending production gates and operation authorization")
    if cfg.mode == "LIVE" and type(provider) is not MockPeyGateway:
        raise ValueError("LIVE blocked pending production gates and operation authorization")
    store=PaymentStore(cfg.store_file)
    pey = provider if provider is not None else MockPeyGateway()
    app=FastAPI(title="Rio Pey CoDi Gateway",version="0.4.0")
    app.state.store=store
    app.state.config=cfg

    def check_server_token(auth:str|None):
        if not cfg.server_token or not auth or not hmac.compare_digest(auth,"Bearer "+cfg.server_token):
            raise HTTPException(401,"Server-to-server authentication required")

    @app.get("/healthz")
    def health():
        return {"state":"READY_LOCAL" if cfg.mode=="DEMO" else "LIVE_CONFIGURED_NOT_SETTLEMENT_VERIFIED",
                "mode":cfg.mode,"payment_settlement":"NOT_OBSERVED"}

    @app.post("/v1/intents",status_code=201)
    def create_intent(req:CreateIntent,authorization:str|None=Header(default=None)):
        check_server_token(authorization)
        if req.merchant != cfg.merchant:
            raise HTTPException(403,"Merchant not authorized")
        try:
            row,created=store.reserve(merchant=req.merchant,order_id=req.order_id,amount_minor=req.amount_minor,
                                      concept=req.concept,numref=req.numref,expiration_s=req.expiration_s)
        except StoreError as exc:
            raise HTTPException(409,str(exc)) from exc
        if not created:
            return {"status":"REPLAY_NO_PROVIDER_RETRY","intent":store.public(row),"mode":cfg.mode}
        try:
            qr=pey.create_qr(intent_id=row["id"],amount_minor=req.amount_minor,concept=req.concept,
                             numref=req.numref,expiration_s=req.expiration_s)
            store.qr_issued(row["id"],qr.provider_id,qr.display)
        except Exception as exc:
            store.uncertain(row["id"])
            raise HTTPException(502,"Provider request uncertain; manual reconciliation required") from exc
        return {"status":"CREATED","intent":store.public(store.get(row["id"])),"mode":cfg.mode,
                "bank_payment_confirmed":False}

    @app.get("/v1/intents/{intent_id}")
    def get_intent(intent_id:str,authorization:str|None=Header(default=None)):
        check_server_token(authorization)
        row=store.get(intent_id)
        if row is None or row["merchant"] != cfg.merchant:
            raise HTTPException(404,"Intent not found")
        return {"intent":store.public(row),"bank_payment_confirmed":False,
                "provider_reported_payment":row["status"]=="PROVIDER_REPORTED"}

    @app.post("/v1/webhooks/pey")
    async def pey_webhook(request: Request):
        if not cfg.webhook_secret:
            raise HTTPException(503,"Webhook verifier not configured")
        body = await request.body()
        if len(body)>65536:
            raise HTTPException(413,"Webhook body too large")
        try:
            eid=verify_signature(dict(request.headers),body,cfg.webhook_secret)
        except InvalidWebhook as exc:
            raise HTTPException(401,str(exc)) from exc
        try:
            data=json.loads(body,parse_float=decimal.Decimal,parse_int=int,
                            object_pairs_hook=lambda pairs:_no_duplicate_pairs(pairs))
        except (ValueError,TypeError) as exc:
            raise HTTPException(400,"Malformed or duplicate-key JSON") from exc
        if not isinstance(data,dict) or data.get("type")!="codi.qr.payment_received":
            raise HTTPException(422,"Unknown payment event type")
        try:
            if not all(isinstance(data.get(k),str) and data[k] for k in ("codiQrId","transactionId","numRef","apiKeyId")):
                raise ValueError("Missing event identity")
            if cfg.mode=="LIVE" and data["apiKeyId"] != cfg.pey_api_key_id:
                raise ValueError("Provider API key identity mismatch")
            cents=parse_provider_amount(data.get("amount"))
            outcome=store.confirm_event(event_id=eid,raw_body=body,qr_id=data["codiQrId"],amount_minor=cents,
                                        numref=data["numRef"],transaction_id=data["transactionId"])
        except (ValueError,StoreError) as exc:
            raise HTTPException(409,str(exc)) from exc
        return {"received":True,**outcome,"bank_settlement":"NOT_VERIFIED"}
    return app


def _no_duplicate_pairs(pairs):
    result={}
    for k,v in pairs:
        if k in result:
            raise ValueError("Duplicate JSON key")
        result[k]=v
    return result


# Run with: uvicorn rio_pey_codi.app:create_app --factory --host 127.0.0.1 --port 8080
# No import-time filesystem writes; host must provide persistent DB, TLS proxy and secrets for LIVE.
