"""RÍO merchant platform: email sign-up, sessions, tenant-scoped QR checkout.

No real money is sent unless LIVE attestation plus an authorized active merchant
are configured. LIVE banking settlement is not claimed on webhook receipt.
"""
from __future__ import annotations
import decimal
import json
import os
import posixpath
import re
from pathlib import Path
from dataclasses import asdict, dataclass, field
from typing import Literal
from urllib.parse import parse_qsl, quote, urlsplit
from starlette.concurrency import run_in_threadpool
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import EmailStr, StrictBool, model_validator, BaseModel, ConfigDict, Field, StrictInt, ValidationError, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from .app import parse_provider_amount, _no_duplicate_pairs
from .identity import AccountService, EmailConfig, Mailer, router_for
from .hackaton_auth import register_hackaton_routes
from .commerce_state import register_commerce_state_routes, DemoCommercialState
from .models import Base, database
from .payments_db import (PaymentConflict, PaymentRepository, ReferenceConflict, ReviewAccessError,
                          ReviewRequestConflict, ReviewWriteError, view)
from .pey import LivePeyGateway, MockPeyGateway, ProviderError, ProviderRejected
from .pey_transaction_review import review_qr_transactions
from .provider_account import ProviderAccountUnavailable, lookup_pey_account, valid_readonly_token
from .provider_observations import ProviderObservations
from .reconciliation import BankRecord
from .signatures import InvalidWebhook, validate_webhook_keyring, verify_and_capture
from .simulated_pey import SimulatedPeyPages
from .merchant_pey_vault import master_key, register_merchant_pey_vault, vault_backup_matches
from .merchant_pey_checkout import (MerchantPeyUnavailable, merchant_gateway, merchant_signing_keys,
                                    qr_png, receive_merchant_event, reconcile_qr, recover_early_delivery)

from .receipts import Receipts, reserve_receipt
from .receipt_verification import register_receipt_verification
from .production_market import register_production_market_routes
from .status_chatbot import register_status_chatbot
from .cash_ledger import register_cash_ledger_routes
from .pey_operations import register_pey_operations, receive_extended_event, route_webhook_merchant
from . import production_market_models, cash_ledger_models, pey_operations_models  # register tables before readiness/create_all
from .verification_tasks import register_verification_tasks


def safe_login_destination(value):
    """Allow only app pages and exact, validated marketplace checkout/QR links."""
    if not isinstance(value, str) or len(value) > 512:
        return '/'
    try:
        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc or parsed.fragment:
            return '/'
        allowed = {'/', '/caja', '/hackaton', '/mercado-abierto',
            '/static/unificada/caja/index.html', '/static/unificada/mercado/index.html',
            '/static/unificada/hackaton/index.html'}
        if parsed.path not in allowed:
            return '/'
        if not parsed.query:
            return parsed.path
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
        params = dict(pairs)
        if len(pairs) != len(params):
            return '/'
        if (parsed.path == '/caja' and len(pairs) == 1 and set(params) == {'market_order'}
                and re.fullmatch(r'[0-9a-f]{32}', params['market_order'])):
            return '/caja?market_order=' + params['market_order'] + '#cobro-codi'
        if parsed.path != '/mercado-abierto':
            return '/'
        if (len(pairs) == 2 and set(params) == {'producto', 'sha256'}
                and re.fullmatch(r'[0-9a-f]{32}', params['producto'])
                and re.fullmatch(r'[0-9a-f]{64}', params['sha256'])):
            return '/mercado-abierto?producto=' + params['producto'] + '&sha256=' + params['sha256']
        if (len(pairs) == 3 and set(params) == {'pedido', 'etapa', 'sha256'}
                and re.fullmatch(r'[0-9a-f]{32}', params['pedido'])
                and params['etapa'] in {'payment', 'bank_credit', 'transit', 'receipt'}
                and re.fullmatch(r'[0-9a-f]{64}', params['sha256'])):
            return ('/mercado-abierto?pedido=' + params['pedido'] + '&etapa=' + params['etapa']
                    + '&sha256=' + params['sha256'])
    except (ValueError, UnicodeError):
        return '/'
    return '/'

@dataclass(frozen=True)
class Settings:
    env:str='local'
    mode:str='DEMO'
    limited_launch:bool=False
    limited_registration_enabled:bool=False
    email_delivery_attested:bool=False  # explicit operational gate; not a substitute for delivery logs
    self_signup_no_email:bool=False
    platform_owner_id:str=''
    database_url:str=field(default='sqlite+pysqlite:///./rio_platform.sqlite3',repr=False)
    auto_create:bool=True
    email_mode:str='memory'
    public_url:str='http://localhost:8000'
    smtp_host:str=''
    smtp_port:int=587
    smtp_user:str=''
    smtp_password:str=field(default='',repr=False)
    smtp_sender:str=''
    origin:str=''
    live_enabled:bool=False
    docs_attested:bool=False
    amount_attested:bool=False
    webhook_attested:bool=False
    account_active_attested:bool=False
    compliance_attested:bool=False
    migrations_attested:bool=False
    api_key:str=field(default='',repr=False)
    api_key_id:str=field(default='',repr=False)
    bank_account_id:str=field(default='',repr=False)
    live_merchant_id:str=''
    webhook_secret:str=field(default='',repr=False)
    webhook_key_ref:str='local-v1'
    webhook_previous_keys:tuple[tuple[str,str],...]=field(default=(),repr=False)
    account_lookup_enabled:bool=False
    account_lookup_merchant_id:str=''
    account_lookup_key_ref:str=''
    account_lookup_api_key:str=field(default='',repr=False)
    response_id_field:str=''
    response_display_field:str=''

    @classmethod
    def from_env(cls):
        flag=lambda name:os.environ.get(name,'').casefold()=='true'
        # Vercel's Resend integration injects RESEND_API_KEY directly. Prefer an
        # explicitly configured SMTP password if one is present; do not copy
        # the API key into another environment variable or expose it in status.
        smtp_password=os.environ.get('SMTP_PASSWORD','')
        resend_key=os.environ.get('RESEND_API_KEY','')
        use_resend=bool(resend_key and not smtp_password)
        return cls(env=os.environ.get('APP_ENV','local'),mode=os.environ.get('RPG_MODE','DEMO'),
           limited_launch=flag('RPG_LIMITED_LAUNCH'),
           limited_registration_enabled=flag('RPG_LIMITED_REGISTRATION_ENABLED'),
           email_delivery_attested=flag('RPG_EMAIL_DELIVERY_ATTESTED'),
           self_signup_no_email=flag('RPG_SELF_SIGNUP_NO_EMAIL'),
           platform_owner_id=os.environ.get('RPG_PLATFORM_OWNER_ID',''),
           database_url=os.environ.get('DATABASE_URL','sqlite+pysqlite:///./rio_platform.sqlite3'),
           auto_create=flag('ALLOW_CREATE_SCHEMA'),email_mode=os.environ.get('EMAIL_MODE','memory'),
           public_url=os.environ.get('PUBLIC_BASE_URL','http://localhost:8000'),
           smtp_host='smtp.resend.com' if use_resend else os.environ.get('SMTP_HOST',''),
           smtp_port=465 if use_resend else int(os.environ.get('SMTP_PORT','587')),
           smtp_user='resend' if use_resend else os.environ.get('SMTP_USER',''),
           smtp_password=resend_key if use_resend else smtp_password,
           smtp_sender=os.environ.get('SMTP_FROM',''),origin=os.environ.get('APP_ORIGIN',''),
           live_enabled=flag('PAYMENTS_LIVE_ENABLED'),docs_attested=flag('PEY_DOCS_ATTESTED'),
           amount_attested=flag('PEY_AMOUNT_UNIT_ATTESTED'),webhook_attested=flag('PEY_WEBHOOK_CONTRACT_ATTESTED'),
           account_active_attested=flag('PEY_ACCOUNT_ACTIVE_ATTESTED'),
           compliance_attested=flag('RPG_COMPLIANCE_AND_AUTH_ATTESTED'),
           migrations_attested=flag('DB_MIGRATIONS_ATTESTED'),api_key=os.environ.get('PEY_API_KEY',''),
           api_key_id=os.environ.get('PEY_API_KEY_ID',''),bank_account_id=os.environ.get('PEY_BANK_ACCOUNT_ID',''),
           live_merchant_id=os.environ.get('PEY_LIVE_MERCHANT_ID',''),
           webhook_secret=os.environ.get('PEY_WEBHOOK_SECRET',''),
           webhook_key_ref=os.environ.get('PEY_WEBHOOK_SIGNING_KEY_REF','local-v1'),
           webhook_previous_keys=parse_previous_webhook_keys(os.environ.get('PEY_WEBHOOK_PREVIOUS_SECRETS_JSON','')),
           account_lookup_enabled=flag('PEY_READONLY_ACCOUNT_LOOKUP_ENABLED'),
           account_lookup_merchant_id=os.environ.get('PEY_READONLY_ACCOUNT_LOOKUP_MERCHANT',''),
           account_lookup_key_ref=os.environ.get('PEY_READONLY_ACCOUNT_LOOKUP_KEY_REF',''),
           account_lookup_api_key=os.environ.get('PEY_READONLY_ACCOUNT_LOOKUP_KEY',''),
           response_id_field=os.environ.get('PEY_QR_ID_RESPONSE_FIELD',''),
           response_display_field=os.environ.get('PEY_QR_DISPLAY_RESPONSE_FIELD',''))

    def validate(self):
        if self.env not in ('local','production','staging') or self.mode not in ('DEMO','LIVE'):
            raise ValueError('Unknown application environment')
        if (type(self.limited_launch) is not bool or type(self.limited_registration_enabled) is not bool
                or type(self.self_signup_no_email) is not bool):
            raise ValueError('Invalid limited launch configuration')
        if self.limited_registration_enabled and not self.limited_launch:
            raise ValueError('Limited registration requires limited launch')
        if self.env != 'local' and self.limited_registration_enabled and not self.email_delivery_attested:
            raise ValueError('Email delivery evidence required before hosted registration')
        if self.self_signup_no_email and (not self.limited_launch or self.limited_registration_enabled):
            raise ValueError('Email-free signup requires limited launch and disabled registration email')
        if self.env != 'local' and self.self_signup_no_email:
            raise ValueError('Hosted signup without email verification is forbidden')
        if self.platform_owner_id and not re.fullmatch(r'[0-9a-f]{32}', self.platform_owner_id):
            raise ValueError('Invalid platform owner configuration')
        if self.limited_launch and (
                self.env == 'local' or self.account_lookup_enabled
                or self.api_key or self.api_key_id or self.bank_account_id or self.live_merchant_id
                or self.webhook_secret or self.webhook_previous_keys or self.account_lookup_api_key):
            raise ValueError('Limited launch cannot use global provider credentials')
        vercel_target = os.environ.get('VERCEL_ENV', '')
        if os.environ.get('VERCEL') == '1' or vercel_target in ('preview', 'production'):
            expected = {'preview':'staging', 'production':'production'}.get(vercel_target)
            if expected is None or self.env != expected:
                raise ValueError('Vercel requires matching explicit staging or production configuration')
        if (self.env != 'local' and (self.webhook_secret or self.webhook_previous_keys)
                and not self.webhook_attested):
            raise ValueError('Provider webhook contract attestation required before activation')
        validate_webhook_keyring(self.webhook_key_ref, self.webhook_secret, self.webhook_previous_keys)
        if self.account_lookup_enabled and (
                not isinstance(self.account_lookup_merchant_id, str)
                or not re.fullmatch(r'[0-9a-f]{32}', self.account_lookup_merchant_id)
                or not isinstance(self.account_lookup_key_ref, str)
                or not re.fullmatch(r'[a-z][a-z0-9_-]{0,31}', self.account_lookup_key_ref)
                or not valid_readonly_token(self.account_lookup_api_key)):
            raise ValueError('Invalid read-only provider account configuration')
        if self.env != 'local':
            if not self.limited_launch and self.webhook_key_ref == 'local-v1':
                raise ValueError('Public deployment requires an explicit webhook signing key reference')
            if not self.database_url.startswith(('postgresql+psycopg://','postgresql://')):
                raise ValueError('Public deployment requires durable PostgreSQL')
            if self.auto_create:raise ValueError('Production/staging schema must be migrated explicitly')
            if self.email_mode!='smtp' or not self.public_url.startswith('https://') or not self.origin.startswith('https://'):
                raise ValueError('Public deployment requires SMTP and HTTPS origin')
            if not self.limited_launch and not all(isinstance(value, str) and value.strip() for value in (self.smtp_user, self.smtp_password)):
                raise ValueError('Public deployment requires SMTP authentication')
            if self.limited_registration_enabled and not all(
                    isinstance(value, str) and value.strip() for value in
                    (self.smtp_host, self.smtp_user, self.smtp_password, self.smtp_sender)):
                raise ValueError('Limited registration requires complete authenticated SMTP')
        if self.mode=='DEMO' and self.live_enabled:raise ValueError('LIVE payments forbidden in DEMO')
        if self.mode=='LIVE':
            if (self.env == 'local' or self.api_key or self.api_key_id or self.bank_account_id
                    or self.live_merchant_id or self.webhook_secret or self.webhook_previous_keys):
                raise ValueError('Hosted LIVE requires exclusively merchant-scoped credentials')
            if not all((self.docs_attested, self.amount_attested, self.webhook_attested, self.migrations_attested)):
                raise ValueError('LIVE requires verified provider contract and explicit migrations')
        if self.env!='local' and self.email_mode=='memory':raise ValueError('Memory email forbidden in deployed service')


def parse_previous_webhook_keys(raw):
    """Parse a bounded secret-manager value; never echo invalid input."""
    if not raw:
        return ()
    if not isinstance(raw, str) or len(raw) > 8192:
        raise ValueError('Invalid historical webhook signing key configuration')
    try:
        def invalid_constant(_value):
            raise ValueError('Invalid constant')
        values = json.loads(raw, object_pairs_hook=_no_duplicate_pairs, parse_constant=invalid_constant)
        if type(values) is not dict or len(values) > 8:
            raise ValueError('Invalid key collection')
        return tuple(values.items())
    except (TypeError, ValueError, RecursionError):
        raise ValueError('Invalid historical webhook signing key configuration') from None

class Checkout(BaseModel):
    model_config=ConfigDict(extra='forbid')
    merchant_id:str=Field(min_length=32,max_length=32)
    order_id:str=Field(min_length=1,max_length=70,pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]*$')
    numref:str=Field(min_length=1,max_length=40,pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]*$')
    concept:str=Field(min_length=1,max_length=140)
    amount_minor:StrictInt=Field(gt=0,le=100_000_000)
    expiration_s:StrictInt=Field(ge=60,le=3600)
    receipt_enabled:StrictBool=False
    payer_email:EmailStr | None=None

    @model_validator(mode='after')
    def receipt_destination(self):
        if self.receipt_enabled and not self.payer_email:
            raise ValueError('Indica el correo del pagador o desactiva el envío del comprobante')
        return self


class BankReviewRecord(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    beneficiary: str = Field(min_length=18, max_length=18, pattern=r'^[0-9]{18}$')
    tracking_key: str = Field(min_length=1, max_length=256)
    amount_minor: StrictInt = Field(gt=0, le=100_000_000)
    direction: Literal['credit', 'reversal']
    evidence_reference: str = Field(min_length=1, max_length=100)
    currency: str = Field(default='MXN', pattern=r'^[A-Z]{3}$')

    @field_validator('tracking_key', 'evidence_reference')
    @classmethod
    def safe_text(cls, value):
        if value != value.strip() or not value.isprintable():
            raise ValueError('Invalid text')
        return value


class BankReviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    bank_records: list[BankReviewRecord] = Field(max_length=50)


async def _read_bank_review(request: Request):
    if request.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'application/json':
        raise HTTPException(415, 'JSON content required')
    chunks = bytearray()
    async for chunk in request.stream():
        if len(chunks) + len(chunk) > 16384:
            raise HTTPException(413, 'Review input exceeds size limit')
        chunks.extend(chunk)
    try:
        def invalid_constant(_value):
            raise ValueError('Invalid JSON constant')
        body = json.loads(bytes(chunks), parse_float=decimal.Decimal,
                          object_pairs_hook=_no_duplicate_pairs, parse_constant=invalid_constant)
        review = BankReviewRequest.model_validate(body)
        return [BankRecord(**item.model_dump()) for item in review.bank_records]
    except (ValidationError, TypeError, ValueError, RecursionError, OverflowError, decimal.DecimalException):
        raise HTTPException(422, 'Invalid reconciliation data') from None


EXPECTED_SCHEMA_REVISION = '024'
# Market checkout, product QR, and saved delivery addresses require the
# additive 024 schema migration. Keep the deployment fail-closed until it is
# present rather than serving partially available purchase flows.
ROLLING_SCHEMA_REVISIONS = frozenset({EXPECTED_SCHEMA_REVISION})
REQUIRED_TABLES = tuple(sorted(Base.metadata.tables))
REQUIRED_COLUMNS = frozenset(f'{table.name}.{column.name}' for table in Base.metadata.tables.values()
                             for column in table.columns)


def database_readiness(factory):
    """Return a safe status for PostgreSQL reachability, revision and columns.

    Matching markers and column names do not prove the full schema, privileges,
    backup recoverability, or the authenticity of anything stored in it.
    """
    try:
        with factory() as db:
            if db.get_bind().dialect.name != 'postgresql':
                return False, 'DIALECT'
            result = db.execute(text("""
                SELECT ARRAY(SELECT version_num FROM public.alembic_version
                             ORDER BY version_num LIMIT 2) AS versions,
                       ARRAY(SELECT c.relname::text || '.' || a.attname::text
                             FROM pg_catalog.pg_class c
                             JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                             JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid
                             WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
                               AND a.attnum > 0 AND NOT a.attisdropped
                               AND c.relname::text = ANY(:required_tables)
                               AND has_table_privilege(current_user, c.oid, 'SELECT')) AS columns
            """), {'required_tables': list(REQUIRED_TABLES)}).one()
            row = result._mapping
            if len(row['versions']) != 1 or row['versions'][0] not in ROLLING_SCHEMA_REVISIONS:
                return False, 'SCHEMA_VERSION'
            expected_columns = REQUIRED_COLUMNS
            if set(row['columns']) != expected_columns:
                return False, 'SCHEMA_STRUCTURE'
            return True, 'OK'
    except Exception as exc:
        # Driver errors can contain credentials. Only return fixed categories,
        # never the exception, database URL, SQL text, or connection details.
        try:
            original = getattr(exc, 'orig', exc)
            state = getattr(original, 'sqlstate', None)
            message = str(original).casefold()
        except Exception:
            return False, 'UNAVAILABLE'
        if state in ('28000', '28P01') or 'password authentication failed' in message:
            return False, 'AUTH'
        if 'root certificate file' in message and ('does not exist' in message or 'no such file' in message):
            return False, 'TLS_ROOT_MISSING'
        if 'certificate verify failed' in message or 'certificate verification failed' in message:
            return False, 'TLS_VERIFY'
        if 'sslrootcert' in message and ('invalid' in message or 'unsupported' in message):
            return False, 'TLS_OPTION'
        if 'certificate' in message or 'sslrootcert' in message or 'tls verification' in message:
            return False, 'TLS'
        if 'could not translate host name' in message or 'name or service not known' in message:
            return False, 'DNS'
        if 'timeout' in message or 'timed out' in message:
            return False, 'TIMEOUT'
        if 'connection refused' in message or 'network is unreachable' in message:
            return False, 'NETWORK'
        if state in ('42501', '42P01', '42703'):
            return False, 'SCHEMA_ACCESS'
        return False, 'UNAVAILABLE'


def database_ready(factory):
    return database_readiness(factory)[0]


def create_platform(settings:Settings|None=None,provider=None,*,simulated_pey=None):
    cfg=settings if settings is not None else Settings.from_env()
    cfg.validate()
    if isinstance(provider, LivePeyGateway) or (cfg.mode == 'LIVE' and provider is not None):
        raise ValueError('LIVE uses only persisted merchant credentials')
    if cfg.limited_launch and provider is not None and type(provider) is not MockPeyGateway:
        raise ValueError('Limited launch cannot use a provider gateway')
    if simulated_pey is not None and (cfg.env != 'local' or cfg.mode != 'DEMO'
                                     or type(simulated_pey) is not SimulatedPeyPages):
        raise ValueError('Synthetic provider pages are local DEMO only')
    simulation = simulated_pey if simulated_pey is not None else SimulatedPeyPages()
    factory=database(cfg.database_url,auto_create=cfg.auto_create)
    email_disabled = cfg.limited_launch and not cfg.limited_registration_enabled
    mailer=Mailer(EmailConfig(mode='disabled' if email_disabled else cfg.email_mode,public_url=cfg.public_url,
              host=cfg.smtp_host,port=cfg.smtp_port,username=cfg.smtp_user,
              password=cfg.smtp_password,sender=cfg.smtp_sender))
    accounts=AccountService(factory,mailer,cookie_secure=cfg.env!='local',
                            platform_owner_id=cfg.platform_owner_id,
                            self_signup_no_email=cfg.self_signup_no_email)
    repository=PaymentRepository(factory, cfg.webhook_secret, cfg.webhook_key_ref, cfg.webhook_previous_keys,
                                 merchant_signing_keys=lambda row, refs: merchant_signing_keys(factory, row, refs))
    provider_observations=ProviderObservations(accounts)
    pey = provider if provider is not None else MockPeyGateway()
    app=FastAPI(title='Mercado Abierto',version='0.5.0',
                docs_url=None if cfg.limited_launch else '/docs',
                redoc_url=None if cfg.limited_launch else '/redoc',
                openapi_url=None if cfg.limited_launch else '/openapi.json')
    receipts=Receipts(factory,mailer,cfg.public_url)
    receipts.register(app,accounts)
    register_receipt_verification(app,accounts,receipts)
    app.state.receipts=receipts
    app.state.accounts=accounts;app.state.payments=repository;app.state.settings=cfg;app.state.mailer=mailer
    app.state.provider_observations=provider_observations
    accounts.activity.register(app,accounts)
    register_verification_tasks(app,accounts)
    app.include_router(router_for(accounts))
    register_hackaton_routes(app, accounts)
    register_commerce_state_routes(app, accounts)
    register_production_market_routes(app, accounts, cfg.public_url)
    register_status_chatbot(app, accounts)
    register_cash_ledger_routes(app, accounts)
    register_merchant_pey_vault(app, accounts, cfg)
    register_pey_operations(app, accounts, cfg, receipts)
    app.mount('/static',StaticFiles(directory=Path(__file__).resolve().parent/'static'),name='static')

    def availability(ready=True, reason='OK'):
        database_status = ('LOCAL_NOT_CHECKED' if cfg.env == 'local' else
                           'SCHEMA_VERSION_AND_COLUMNS_MATCH' if ready else 'UNAVAILABLE')
        try:
            master_key()
            vault_available = ready and cfg.env != 'local'
        except HTTPException:
            vault_available = False
        live = cfg.mode == 'LIVE' and cfg.live_enabled and vault_available
        return {'application':'rio-merchant-codi','mode':cfg.mode,'environment':cfg.env,
                'launch_mode':'LIMITED' if cfg.limited_launch else 'STANDARD',
                'access_enabled':ready,'registration_enabled':ready and (cfg.self_signup_no_email or not email_disabled),
                'registration_email_required':not cfg.self_signup_no_email,
                'verification_email_enabled':ready and not email_disabled,
                'password_reset_enabled':ready and not email_disabled,
                'payment_requests_enabled':live or (ready and cfg.mode == 'DEMO' and not cfg.limited_launch),
                'webhook_enabled':(vault_available and cfg.mode == 'LIVE')
                    or (ready and bool(cfg.webhook_secret) and not cfg.limited_launch and cfg.webhook_attested),
                'live_payments_enabled':live,
                'merchant_pey_configuration_enabled':vault_available,
                'merchant_vault_backup_matches':vault_available and vault_backup_matches(),
                'bank_settlement':'NOT_OBSERVED','email_delivery':'DISABLED' if email_disabled else cfg.email_mode,
                'email_delivery_verified':False,'email_delivery_attested':bool(cfg.email_delivery_attested),
                'database_readiness':database_status,
                'database_failure':reason if not ready else None,
                'registered_user_support':ready}

    @app.middleware('http')
    async def security(request:Request,call_next):
        is_webhook = request.url.path == '/v1/webhooks/pey' or request.url.path.startswith('/v1/webhooks/pey/')
        if cfg.origin and request.method not in ('GET','HEAD','OPTIONS') and not is_webhook:
            origin=request.headers.get('origin')
            if origin and origin!=cfg.origin:
                return __import__('fastapi').responses.JSONResponse({'detail':'Untrusted origin'},status_code=403)
        # StaticFiles normalizes decoded paths before resolving files. Apply the
        # same normalization to the authorization decision, including repeated
        # slashes, dot segments and trailing slashes on private HTML files.
        path = '/' + posixpath.normpath(request.url.path).lstrip('/')
        page_response = None
        protected_page = request.method in ('GET', 'HEAD') and (
            path in ('/caja', '/hackaton', '/mercado-abierto') or
            (path.startswith('/static/') and path.lower().endswith('.html')))
        if protected_page:
            try:
                principal = await run_in_threadpool(accounts.session, request)
            except HTTPException as error:
                if error.status_code not in (401, 403):
                    raise
                candidate = path + (('?' + request.url.query) if path in ('/mercado-abierto', '/caja') and request.url.query else '')
                destination = safe_login_destination(candidate)
                page_response = RedirectResponse('/login?next=' + quote(destination, safe=''), status_code=303)
            except SQLAlchemyError:
                page_response = JSONResponse({'status': 'UNAVAILABLE'}, status_code=503)
            else:
                if path.startswith('/static/unificada/mercado/') and path.lower().endswith('.html') and not accounts.can_invite(principal):
                    page_response = JSONResponse({'detail':'Mercado solo está disponible para la cuenta titular.'},status_code=403)
                elif path.startswith('/static/unificada/mercado/') and path.lower().endswith('.html'):
                    page_response = RedirectResponse('/mercado-abierto#catalogo',status_code=303)
                elif path == '/static/unificada/caja/index.html':
                    page_response = RedirectResponse('/#cobro-codi',status_code=303)
                elif path == '/static/unificada/hackaton/index.html':
                    page_response = RedirectResponse('/mercado-abierto',status_code=303)
                elif path in ('/static/index.html', '/static/unificada/index.html', '/static/login.html'):
                    page_response = RedirectResponse('/', status_code=303)
        public_assets = (request.method in ('GET','HEAD') and
                         (path in ('/', '/login', '/verify-email', '/reset-password') or path.startswith('/static/')))
        public_status = request.method == 'GET' and request.url.path == '/public-status'
        if page_response is not None:
            response = page_response
        elif public_assets:
            response = await call_next(request)
        elif public_status and cfg.env != 'local':
            ready, reason = await run_in_threadpool(database_readiness, factory)
            response = JSONResponse(availability(ready, reason))
        elif cfg.env != 'local' and not await run_in_threadpool(database_ready, factory):
            response = JSONResponse({'status':'UNAVAILABLE', 'live_payments_enabled':False,
                                     'bank_payment_confirmed':False}, status_code=503,
                                    headers={'Retry-After':'30'})
        else:
            response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Cache-Control']='no-store'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Permissions-Policy']='camera=(self)'
        response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        return response

    @app.get('/healthz')
    def health():
        return availability()

    @app.get('/public-status')
    def public_status():
        return availability()

    @app.get('/v1/merchants/{merchant_id}/production-readiness')
    async def production_readiness(merchant_id: str, request: Request):
        principal = await run_in_threadpool(accounts.session, request)
        configured = cfg.account_lookup_enabled and cfg.account_lookup_merchant_id == merchant_id
        ref = cfg.account_lookup_key_ref if configured else 'ephemeral_owner_key_v1'
        state = await run_in_threadpool(provider_observations.readiness, principal, merchant_id, ref)
        return {**state, 'account_lookup_configured':configured}

    @app.post('/v1/merchants/{merchant_id}/provider-account-checks', status_code=201)
    async def provider_account_check(merchant_id: str, request: Request):
        principal = await run_in_threadpool(accounts.session, request, csrf=True)
        await run_in_threadpool(accounts.assert_member, principal['id'], merchant_id, {'owner'})
        if not cfg.account_lookup_enabled or cfg.account_lookup_merchant_id != merchant_id:
            raise HTTPException(503, 'Read-only account lookup is not configured for this merchant')
        values = request.headers.getlist('idempotency-key')
        if len(values) != 1 or not re.fullmatch(r'[0-9a-f]{32}', values[0]):
            raise HTTPException(422, 'A 32-character lowercase account check request key is required')
        async for chunk in request.stream():
            if chunk:
                raise HTTPException(422, 'No request body is accepted')
        claim_id, account_id = await run_in_threadpool(provider_observations.prepare,
            principal, merchant_id, values[0])
        try:
            status = await run_in_threadpool(lookup_pey_account, cfg.account_lookup_api_key, account_id)
        except ProviderAccountUnavailable:
            raise HTTPException(503, 'Account lookup unavailable') from None
        observation = await run_in_threadpool(provider_observations.record, principal, merchant_id,
            values[0], claim_id, account_id, cfg.account_lookup_key_ref, status)
        return {'observation':observation}

    @app.post('/v1/merchants/{merchant_id}/own-pey-account-checks', status_code=201)
    async def own_pey_account_check(merchant_id: str, request: Request):
        """Read the owner's declared account with a supplied, non-persisted key."""
        principal = await run_in_threadpool(accounts.session, request, csrf=True)
        await run_in_threadpool(accounts.assert_member, principal['id'], merchant_id, {'owner'})
        values = request.headers.getlist('idempotency-key')
        if len(values) != 1 or not re.fullmatch(r'[0-9a-f]{32}', values[0]):
            raise HTTPException(422, 'A request key is required')
        await run_in_threadpool(accounts.limit, request, 'own-pey-lookup', principal['id'])
        claim_id, account_id = await run_in_threadpool(provider_observations.prepare,
            principal, merchant_id, values[0])
        raw=bytearray()
        async for chunk in request.stream():
            if len(raw)+len(chunk)>2048:
                raise HTTPException(413, 'Request too large')
            raw.extend(chunk)
        try:
            data=json.loads(bytes(raw), object_pairs_hook=_no_duplicate_pairs,
                            parse_constant=lambda _x: (_ for _ in ()).throw(ValueError('invalid constant')))
            if type(data) is not dict or set(data) != {'api_key'} or not valid_readonly_token(data['api_key']):
                raise ValueError('invalid input')
            key=data['api_key']
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise HTTPException(422, 'Clave de pey inválida') from None
        try:
            status = await run_in_threadpool(lookup_pey_account, key, account_id)
        except ProviderAccountUnavailable:
            raise HTTPException(503, 'No se pudo consultar la cuenta en pey') from None
        finally:
            key = None
            data = None
            raw.clear()
        observation = await run_in_threadpool(provider_observations.record, principal, merchant_id,
            values[0], claim_id, account_id, 'ephemeral_owner_key_v1', status)
        return {'observation':observation, 'key_saved':False}

    @app.get('/',response_class=HTMLResponse)
    @app.get('/login',response_class=HTMLResponse)
    @app.get('/verify-email',response_class=HTMLResponse)
    @app.get('/reset-password',response_class=HTMLResponse)
    @app.get('/caja',response_class=HTMLResponse)
    def homepage(request: Request):
        auth_action = request.url.path in ('/verify-email', '/reset-password')
        principal = None
        if not auth_action:
            try:
                principal = accounts.session(request)
            except HTTPException as error:
                if error.status_code not in (401, 403):
                    raise
        if principal and request.url.path == '/login':
            destination = request.query_params.get('next', '/')
            return RedirectResponse(safe_login_destination(destination), status_code=303)
        filename=Path(__file__).resolve().parent/'static'/('index.html' if principal else 'login.html')
        return filename.read_text(encoding='utf-8')

    @app.post('/v1/checkout/qr',status_code=201)
    def checkout(req:Checkout,request:Request,background_tasks:BackgroundTasks):
        user=accounts.session(request,csrf=True)
        accounts.assert_member(user['id'],req.merchant_id,{'owner','admin','cashier'})
        gateway = pey
        if req.receipt_enabled and cfg.mode != 'LIVE':
            raise HTTPException(422,'Los comprobantes por correo requieren un pago real confirmado por pey')
        if cfg.mode=='LIVE':
            if not cfg.live_enabled:
                raise HTTPException(503,'Cobros desactivados temporalmente')
            if req.order_id.upper().startswith('DEMO-'):
                raise HTTPException(422, 'Usa un folio de venta real para cobrar con CoDi')
            if not re.fullmatch(r'[0-9]{1,7}', req.numref) or req.expiration_s < 360:
                raise HTTPException(422, 'Referencia o vigencia CoDi inválida')
        elif cfg.limited_launch:
            raise HTTPException(503,'Cobros desactivados temporalmente')
        try:
            args = (req.merchant_id,req.order_id,req.amount_minor,req.concept,req.numref,req.expiration_s)
            if cfg.mode == 'LIVE':
                row, created, credential = repository.reserve(
                    *args, authorize=lambda db: accounts.authorize_checkout(db, user, req.merchant_id),
                    live_gateway=lambda db: merchant_gateway(factory, req.merchant_id, db=db),
                    on_created=lambda db, row: reserve_receipt(db, row, req.receipt_enabled, str(req.payer_email) if req.payer_email else None),
                )
                if created:
                    gateway = credential.gateway
            else:
                row, created = repository.reserve(*args)
        except ReferenceConflict:
            return JSONResponse({'detail': 'Payment reference already used', 'code': 'REFERENCE_TAKEN'}, status_code=409)
        except MerchantPeyUnavailable as exc:
            return JSONResponse({'detail':exc.detail,'code':'MERCHANT_PEY_UNAVAILABLE'},status_code=503)
        except (PaymentConflict,IntegrityError) as exc:
            raise HTTPException(409,'Payment reference or order conflict') from exc
        if not created:
            intent = view(row)
            return {'status':'REPLAY_NO_PROVIDER_RETRY','intent':intent,'mode':intent['mode']}
        try:
            qr=gateway.create_qr(intent_id=row.id,amount_minor=req.amount_minor,concept=req.concept,
                             numref=req.numref,expiration_s=req.expiration_s)
            repository.qr_issued(row.id,qr.provider_id,qr.display)
        except ProviderRejected:
            intent = view(repository.reject(row.id))
            return {'status':intent['status'],'intent':intent,'mode':cfg.mode}
        except Exception:
            repository.uncertain(row.id)
            raise HTTPException(502,'Resultado incierto en pey. Recupera este folio antes de continuar.') from None
        if cfg.mode == 'LIVE':
            background_tasks.add_task(receipts.issue, row.id)
        return {'status':'CREATED','intent':view(repository.get(row.id)),'mode':cfg.mode}

    @app.get('/v1/checkout/qr/{intent_id}')
    def checkout_status(intent_id:str,request:Request):
        user=accounts.session(request)
        row=repository.get(intent_id)
        if not row:raise HTTPException(404,'Payment intent not found')
        accounts.assert_member(user['id'],row.merchant_id)
        return {'intent':view(row),'provider_reported_payment':row.status=='PROVIDER_REPORTED',
                'bank_payment_confirmed':False}

    @app.get('/v1/checkout/qr/{intent_id}/image')
    def checkout_image(intent_id: str, request: Request):
        user = accounts.session(request)
        row = repository.get(intent_id)
        if row is None:
            raise HTTPException(404, 'Solicitud no encontrada')
        accounts.assert_member(user['id'], row.merchant_id)
        if (not row.pey_credential_ref or row.status != 'QR_ISSUED' or not row.qr_display or view(row)['expired']):
            raise HTTPException(404, 'QR no disponible')
        return Response(qr_png(row.qr_display), media_type='image/png')

    @app.post('/v1/checkout/qr/{intent_id}/provider-status')
    def checkout_provider_status(intent_id: str, request: Request, background_tasks: BackgroundTasks):
        user = accounts.session(request, csrf=True)
        row = repository.get(intent_id)
        if row is None:
            raise HTTPException(404, 'Solicitud no encontrada')
        accounts.assert_member(user['id'], row.merchant_id, {'owner', 'admin', 'cashier'})
        if not row.pey_credential_ref or row.status == 'PROVIDER_REJECTED':
            raise HTTPException(409, 'La orden no se puede consultar en pey')
        background_tasks.add_task(receipts.issue, intent_id)
        if row.provider_payment_source:
            app.state.production_market.pey_payment_confirmed(row.id)
            return {'intent': view(row), 'provider_lookup': 'PAYMENT_OBSERVED'}
        accounts.limit(request, 'pey-status', user['id'])
        credential = merchant_gateway(factory, row.merchant_id, row.pey_credential_ref)
        try:
            if not row.provider_qr_id:
                recovered = recover_early_delivery(factory, repository, credential, row)
                row = recovered or repository.get(intent_id)
                app.state.production_market.pey_payment_confirmed(row.id)
                return {'intent':view(row), 'provider_lookup':
                        'PAYMENT_OBSERVED' if row.provider_payment_source else 'QR_NOT_IDENTIFIED'}
            result = reconcile_qr(credential, row)
            if result is None:
                row = repository.get(intent_id)
                return {'intent':view(row), 'provider_lookup':
                        'PAYMENT_OBSERVED' if row.provider_payment_source else 'NO_PAID_TRANSACTION_OBSERVED'}
            row = repository.confirm_provider_lookup(row, *result)
        except ProviderError:
            raise HTTPException(502, 'Consulta de pey incompleta. Conserva el folio.') from None
        except (ValueError, IntegrityError):
            raise HTTPException(409, 'Pey reportó datos que requieren revisión.') from None
        app.state.production_market.pey_payment_confirmed(row.id)
        return {'intent': view(row), 'provider_lookup': 'PAYMENT_OBSERVED'}

    @app.get('/v1/merchants/{merchant_id}/checkout-history')
    def checkout_history(merchant_id: str, request: Request):
        user = accounts.session(request)
        accounts.assert_member(user['id'], merchant_id)
        return {'intents': repository.history(merchant_id)}

    @app.get('/v1/merchants/{merchant_id}/checkout-unresolved')
    def checkout_unresolved(merchant_id: str, request: Request,
                            limit: int = Query(default=25, ge=1, le=100),
                            after_created_at: int | None = Query(default=None, ge=0, le=9223372036854775807),
                            after_id: str | None = Query(default=None, pattern=r'^[0-9a-f]{32}$')):
        user = accounts.session(request)
        accounts.assert_member(user['id'], merchant_id)
        if (after_created_at is None) != (after_id is None):
            raise HTTPException(422, 'Both cursor fields are required')
        after = (after_created_at, after_id) if after_id is not None else None
        intents, cursor = repository.unresolved_page(merchant_id, limit, after)
        return {'intents':intents, 'next_cursor':cursor, 'bank_payment_confirmed':False}

    @app.get('/v1/merchants/{merchant_id}/checkout-orders/{order_id}')
    def checkout_by_order(merchant_id: str, order_id: str, request: Request):
        user = accounts.session(request)
        accounts.assert_member(user['id'], merchant_id)
        row = repository.get_by_order(merchant_id, order_id)
        if row is None:
            return JSONResponse({'detail':'Payment intent not found', 'code':'ORDER_NOT_FOUND'}, status_code=404)
        return {'intent': view(row), 'bank_payment_confirmed': False}

    @app.get('/v1/checkout/qr/{intent_id}/practice-ticket')
    def practice_ticket(intent_id: str, request: Request):
        user = accounts.session(request)
        row = repository.get(intent_id)
        if row is None:
            raise HTTPException(404, 'Payment intent not found')
        accounts.assert_member(user['id'], row.merchant_id)
        if row.pey_credential_ref:
            raise HTTPException(409, 'Esta solicitud corresponde a un cobro real')
        return {'kind': 'PRACTICE_NON_FISCAL', 'order_id': row.order_id,
                'amount_minor': row.amount_minor, 'currency': 'MXN',
                'provider_status': row.status, 'bank_payment_confirmed': False}

    def review_context(request, intent_id):
        user = accounts.session(request, csrf=True)
        row = repository.get(intent_id)
        if row is None:
            raise HTTPException(404, 'Payment intent not found')
        accounts.assert_member(user['id'], row.merchant_id, {'owner', 'admin'})
        return (user['id'], row.merchant_id, row.provider_qr_id, row.amount_minor,
                row.transaction_id, row.status, repository.latest_claim_marker(row.merchant_id),
                repository.review_event_marker(intent_id, row.merchant_id))

    @app.post('/v1/checkout/qr/{intent_id}/reconciliation-preview')
    async def reconciliation_preview(intent_id: str, request: Request):
        initial = await run_in_threadpool(review_context, request, intent_id)
        records = await _read_bank_review(request)
        current = await run_in_threadpool(review_context, request, intent_id)
        if current != initial:
            raise HTTPException(409, 'Payment review context changed')
        try:
            classification, signature_assessment, account_assessment, assessed_events = await run_in_threadpool(repository.reconciliation_preview, intent_id, current[1], records)
        except PaymentConflict:
            raise HTTPException(404, 'Payment intent not found') from None
        final = await run_in_threadpool(review_context, request, intent_id)
        if final != current or assessed_events != final[-1]:
            raise HTTPException(409, 'Payment review context changed')
        return {'classification':classification, 'bank_payment_confirmed':False,
                'independent_source_verified':False, 'provider_signature_reverified':signature_assessment == 'VERIFIED',
                'signature_assessment':signature_assessment,
                'account_assessment':account_assessment,
                'beneficiary_binding_verified':False, 'bank_records_persisted':False}

    def review_flags(signature_reverified=False):
        return {'bank_payment_confirmed':False, 'independent_bank_source_verified':False,
                'provider_signature_reverified':signature_reverified, 'beneficiary_binding_verified':False,
                'bank_records_persisted':False}

    def review_error(error):
        if isinstance(error, ReviewAccessError):
            raise HTTPException(error.status, 'Review access denied') from None
        if isinstance(error, ReviewRequestConflict):
            return JSONResponse({'detail':'Review request already used',
                                 'code':'REVIEW_REQUEST_ALREADY_USED'}, status_code=409)
        raise HTTPException(503, 'Review could not be stored') from None

    @app.post('/v1/checkout/qr/{intent_id}/reconciliation-reviews', status_code=201)
    async def record_reconciliation_review(intent_id: str, request: Request):
        user = await run_in_threadpool(accounts.session, request, csrf=True)
        intent = await run_in_threadpool(repository.get, intent_id)
        if intent is None:
            raise HTTPException(404, 'Payment intent not found')
        await run_in_threadpool(accounts.assert_member, user['id'], intent.merchant_id, {'owner', 'admin'})
        values = request.headers.getlist('idempotency-key')
        if len(values) != 1 or not re.fullmatch(r'[0-9a-f]{32}', values[0]):
            raise HTTPException(422, 'A 32-character lowercase review request key is required')
        records = await _read_bank_review(request)
        try:
            result = await run_in_threadpool(repository.record_reconciliation_review,
                intent_id, user['id'], user['session_hash'], user['csrf_hash'], values[0], records)
        except (ReviewAccessError, ReviewRequestConflict, ReviewWriteError) as error:
            return review_error(error)
        return {'review':result, **review_flags(result['signature_assessment_at_review'] == 'VERIFIED')}

    @app.get('/v1/checkout/qr/{intent_id}/reconciliation-reviews')
    async def list_reconciliation_reviews(intent_id: str, request: Request):
        user = await run_in_threadpool(accounts.session, request)
        try:
            result = await run_in_threadpool(repository.read_reconciliation_reviews,
                intent_id, user['id'], user['session_hash'], user['csrf_hash'])
        except ReviewAccessError as error:
            return review_error(error)
        return {**result, **review_flags()}

    @app.get('/v1/checkout/qr/{intent_id}/reconciliation-reviews/by-request/{request_id}')
    async def find_reconciliation_review(intent_id: str, request_id: str, request: Request):
        user = await run_in_threadpool(accounts.session, request)
        if not re.fullmatch(r'[0-9a-f]{32}', request_id):
            raise HTTPException(422, 'Invalid review request key')
        try:
            result = await run_in_threadpool(repository.read_reconciliation_reviews,
                intent_id, user['id'], user['session_hash'], user['csrf_hash'], request_id)
        except ReviewAccessError as error:
            return review_error(error)
        if result is None:
            raise HTTPException(404, 'Review request not found')
        return {'review':result, **review_flags()}

    if cfg.env == 'local' and cfg.mode == 'DEMO':
        @app.post('/v1/checkout/qr/{intent_id}/simulated-transaction-review')
        async def simulated_transaction_review(intent_id: str, request: Request):
            initial = await run_in_threadpool(review_context, request, intent_id)
            records = await _read_bank_review(request)
            current = await run_in_threadpool(review_context, request, intent_id)
            if current != initial:
                raise HTTPException(409, 'Payment review context changed')
            outcome = await run_in_threadpool(
                review_qr_transactions, qr_id=current[2], expected_amount_minor=current[3],
                bank_records=records, fetch_page=simulation, expected_transaction_id=current[4],
            )
            final = await run_in_threadpool(review_context, request, intent_id)
            if final != current:
                raise HTTPException(409, 'Payment review context changed')
            return {'mode':'LOCAL_SIMULATION', **asdict(outcome),
                    'bank_records_persisted':False, 'provider_records_persisted':False}

    @app.post('/v1/webhooks/pey')
    async def webhook(request:Request):
        if cfg.limited_launch or cfg.mode == 'LIVE':raise HTTPException(503,'Webhook global desactivado')
        if not cfg.webhook_secret:raise HTTPException(503,'Webhook signing unavailable')
        if cfg.env != 'local' and not cfg.webhook_attested:
            raise HTTPException(503,'Provider webhook contract not verified')
        # No streaming/DB writes prior to signature check.
        try:
            chunks = bytearray()
            async for chunk in request.stream():
                if len(chunks) + len(chunk) > 65536:
                    raise HTTPException(413, 'Webhook exceeds size limit')
                chunks.extend(chunk)
            data_body = bytes(chunks)
            for header in ('webhook-id', 'webhook-timestamp', 'webhook-signature'):
                if len(request.headers.getlist(header)) != 1:
                    raise InvalidWebhook('Invalid signature header cardinality')
            if len(request.headers['webhook-signature']) > 2048:
                raise InvalidWebhook('Signature header too long')
            event_id, signature_evidence = verify_and_capture(dict(request.headers),data_body,cfg.webhook_secret,cfg.webhook_key_ref)
            if len(event_id) > 140:
                raise InvalidWebhook('Event identifier too long')
        except InvalidWebhook as exc:
            raise HTTPException(401,'Invalid provider signature') from exc
        try:
            data=json.loads(data_body,parse_float=decimal.Decimal,object_pairs_hook=_no_duplicate_pairs)
            if not isinstance(data,dict) or data.get('type')!='codi.qr.payment_received':
                raise ValueError('Unexpected type')
            for key in ('codiQrId','numRef','transactionId','apiKeyId'):
                if not isinstance(data.get(key),str) or not 0 < len(data[key]) <= (40 if key == 'numRef' else 140):
                    raise ValueError('Invalid event identity')
            if cfg.mode=='LIVE' and data['apiKeyId']!=cfg.api_key_id:
                raise ValueError('Provider API key identity mismatch')
            minor=parse_provider_amount(data.get('amount'))
            outcome=await run_in_threadpool(repository.confirm_event,event_id,data_body,data['codiQrId'],minor,data['numRef'],data['transactionId'],signature_evidence)
            if outcome.get('intent_id'):
                await run_in_threadpool(app.state.production_market.pey_payment_confirmed, outcome['intent_id'])
        except (TypeError,ValueError,RecursionError,PaymentConflict,IntegrityError) as exc:
            raise HTTPException(409,'Conflicting or invalid provider event') from exc
        return {'received':True,**outcome,'bank_settlement':'NOT_VERIFIED'}

    @app.post('/v1/webhooks/pey/{merchant_id}')
    async def merchant_webhook(merchant_id: str, request: Request, background_tasks: BackgroundTasks):
        if cfg.mode != 'LIVE' or not cfg.webhook_attested:
            raise HTTPException(503, 'Webhook de comercios desactivado')
        if not re.fullmatch(r'[0-9a-f]{32}', merchant_id):
            raise HTTPException(404, 'Webhook no encontrado')
        headers = {}
        for header in ('webhook-id', 'webhook-timestamp', 'webhook-signature'):
            values = request.headers.getlist(header)
            if len(values) != 1 or len(values[0]) > 2048 or not values[0].isascii():
                raise HTTPException(401, 'Firma de pey inválida')
            headers[header] = values[0]
        chunks = bytearray()
        async for chunk in request.stream():
            if len(chunks) + len(chunk) > 65536:
                raise HTTPException(413, 'Webhook demasiado grande')
            chunks.extend(chunk)
        try:
            merchant_id = await run_in_threadpool(route_webhook_merchant, accounts, merchant_id, headers, bytes(chunks))
            outcome = await run_in_threadpool(receive_extended_event, accounts, merchant_id, headers, bytes(chunks))
            if outcome is None:
                outcome = await run_in_threadpool(receive_merchant_event, factory, repository, merchant_id,
                                                  headers, bytes(chunks))
        except InvalidWebhook:
            raise HTTPException(401, 'Firma de pey inválida') from None
        except (ValueError, ProviderError, IntegrityError):
            raise HTTPException(409, 'Aviso de pey incompatible con la solicitud') from None
        if outcome.get('intent_id'):
            await run_in_threadpool(app.state.production_market.pey_payment_confirmed, outcome['intent_id'])
        if outcome.get('intent_id'):
            background_tasks.add_task(receipts.issue, outcome['intent_id'])
        return {'received':True, 'outcome':outcome['outcome'], 'bank_settlement':'NOT_VERIFIED'}
    return app

# Vercel ASGI convention: lazy factory ensures fail-closed configuration validation.
# Set environment variables and migrate database before startup.
