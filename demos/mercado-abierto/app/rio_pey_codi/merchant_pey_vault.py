"""Encrypted, merchant-scoped configuration. Secret key values are never returned."""
import base64
import binascii
import hmac
import json
import os
import re
import time
import uuid
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy import text
from .models import MerchantPeyCredential, MerchantPeySecret
from .pey import LivePeyGateway, ProviderError
from .provider_account import ProviderAccountUnavailable, lookup_pey_account, valid_readonly_token
from .signatures import validate_webhook_keyring

MAX_BODY = 4096

def master_key():
    primary = os.environ.get('RPG_MERCHANT_VAULT_KEY', '')
    backup = os.environ.get('RPG_MERCHANT_VAULT_KEY_BACKUP', '')
    if primary and backup and not hmac.compare_digest(primary.encode(), backup.encode()):
        raise HTTPException(503, 'Configuración privada no disponible')
    raw = primary or backup
    try:
        key = base64.b64decode(raw, altchars=b'-_', validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(503, 'Configuración privada no disponible') from None
    if len(key) != 32:
        raise HTTPException(503, 'Configuración privada no disponible')
    return key


def vault_backup_matches():
    primary = os.environ.get('RPG_MERCHANT_VAULT_KEY', '')
    backup = os.environ.get('RPG_MERCHANT_VAULT_KEY_BACKUP', '')
    return bool(primary and backup and hmac.compare_digest(primary.encode(), backup.encode()))

def seal(key, merchant, name, value):
    nonce = os.urandom(12)
    aad = ('rio-pey-v1:' + merchant + ':' + name).encode()
    return nonce + AESGCM(key).encrypt(nonce, value.encode(), aad)

def open_value(key, merchant, name, data):
    aad = ('rio-pey-v1:' + merchant + ':' + name).encode()
    return AESGCM(key).decrypt(data[:12], data[12:], aad).decode()

def begin(accounts, principal, merchant):
    db = accounts.Session()
    try:
        if db.bind.dialect.name == 'sqlite':
            db.execute(text('BEGIN IMMEDIATE'))
        accounts._claim_access(db, principal, merchant, lock=True, conceal_non_owner=True)
        return db
    except BaseException:
        db.close()
        raise

def draft_snapshot(row):
    return row.api_key_id, row.api_key, row.webhook_secret, row.bank_account_id


def register_merchant_pey_vault(app, accounts, cfg):
    @app.get('/v1/merchants/{merchant}/pey-status')
    def payment_status(merchant: str, request: Request):
        principal = accounts.session(request)
        accounts.assert_member(principal['id'], merchant)
        with accounts.Session() as db:
            row = db.get(MerchantPeySecret, merchant)
            try:
                master_key()
                available = True
            except HTTPException:
                available = False
            return {'payment_active': bool(available and cfg.mode == 'LIVE' and cfg.live_enabled
                                           and row and row.active_credential_ref)}

    @app.get('/v1/merchants/{merchant}/pey-settings')
    def status(merchant: str, request: Request):
        principal = accounts.session(request)
        with accounts.Session() as db:
            accounts._claim_access(db, principal, merchant, lock=False, conceal_non_owner=True)
            row = db.get(MerchantPeySecret, merchant)
            try:
                master_key()
                available = True
            except HTTPException:
                available = False
            account_id = None
            if available and row and row.bank_account_id:
                try:
                    account_id = open_value(master_key(), merchant, 'bank_account_id', row.bank_account_id)
                except Exception:
                    available = False
            credential = db.get(MerchantPeyCredential, row.active_credential_ref) if row and row.active_credential_ref else None
            return {'api_key_configured': bool(row and row.api_key),
                    'api_key_id_configured': bool(row and row.api_key_id),
                    'webhook_secret_configured': bool(row and row.webhook_secret),
                    'bank_account_id_configured': bool(row and row.bank_account_id),
                    'configuration_available': available,
                    'configuration_saved': row is not None,
                    'bank_account_id': account_id,
                    'api_key_id': row.api_key_id if row else None,
                    'updated_at': row.updated_at if row else None,
                    'verified_at': credential.checked_at if credential else None,
                    'payment_active': bool(available and cfg.mode == 'LIVE' and cfg.live_enabled
                                           and row and row.active_credential_ref),
                    'webhook_url': (cfg.public_url.rstrip('/') + '/v1/webhooks/pey/' + merchant
                                    if cfg.mode == 'LIVE' else None)}

    @app.put('/v1/merchants/{merchant}/pey-settings')
    async def save(merchant: str, request: Request):
        principal = await run_in_threadpool(accounts.session, request, csrf=True)
        # Check ownership before reading a secret from the request.
        def check_owner():
            with accounts.Session() as db:
                accounts._claim_access(db, principal, merchant, lock=False, conceal_non_owner=True)
        await run_in_threadpool(check_owner)
        key = master_key()
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > MAX_BODY:
                raise HTTPException(413, 'Solicitud demasiado grande')
            raw.extend(chunk)
        try:
            def pairs(items):
                out = {}
                for k, v in items:
                    if k in out: raise ValueError()
                    out[k] = v
                return out
            data = json.loads(bytes(raw), object_pairs_hook=pairs)
            if type(data) is not dict or not data or set(data) - {'api_key','api_key_id','webhook_secret','bank_account_id'}:
                raise ValueError()
            for name, value in data.items():
                if name == 'bank_account_id' and value is None:
                    continue
                if not isinstance(value, str) or not value or len(value) > 512:
                    raise ValueError()
                if name in ('bank_account_id', 'api_key_id') and not re.fullmatch(r'[0-7][0-9A-HJKMNP-TV-Z]{25}', value):
                    raise ValueError()
                if name == 'api_key' and not valid_readonly_token(value):
                    raise ValueError()
                if name == 'webhook_secret':
                    validate_webhook_keyring('draft', value, ())
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise HTTPException(422, 'Datos de pey inválidos') from None
        finally:
            raw.clear()
        def store_draft():
            with begin(accounts, principal, merchant) as db:
                try:
                    row = db.get(MerchantPeySecret, merchant)
                    if row is None:
                        row = MerchantPeySecret(merchant_id=merchant)
                        db.add(row)
                    for name, value in data.items():
                        protected = value if name == 'api_key_id' or value is None else seal(key, merchant, name, value)
                        setattr(row, name, protected)
                    if 'api_key' in data and 'api_key_id' not in data:
                        row.api_key_id = None
                    row.active_credential_ref = None
                    row.updated_at = int(time.time())
                    db.commit()
                except Exception:
                    db.rollback()
                    raise HTTPException(503, 'No se pudo guardar la configuración') from None
        try:
            await run_in_threadpool(store_draft)
        finally:
            data.clear()
        accounts.activity.record('PEY_SAVED',email=principal['email'],reference=merchant)
        return JSONResponse({'saved': True, 'payment_active': False}, headers={'Cache-Control':'no-store'})

    @app.post('/v1/merchants/{merchant}/pey-settings/activate')
    def activate(merchant: str, request: Request):
        principal = accounts.session(request, csrf=True)
        if cfg.mode != 'LIVE' or not cfg.live_enabled:
            raise HTTPException(503, 'Activación de cobros temporalmente no disponible')
        if request.headers.getlist('x-pey-beneficiary-confirmed') != ['true']:
            raise HTTPException(422, 'Confirma en pey la cuenta CoDi receptora de esta llave')
        key = master_key()
        with begin(accounts, principal, merchant) as db:
            row = db.get(MerchantPeySecret, merchant)
            if not row or not all((row.api_key, row.webhook_secret)):
                raise HTTPException(409, 'Guarda la API key y el secreto del webhook')
            snapshot = draft_snapshot(row)
            if row.active_credential_ref:
                return {'payment_active': True}
        accounts.limit(request, 'activate-pey', principal['id'])
        api_key_id, api_cipher, webhook_cipher, account_cipher = snapshot
        try:
            api_key = open_value(key, merchant, 'api_key', api_cipher)
            webhook_secret = open_value(key, merchant, 'webhook_secret', webhook_cipher)
            account_id = open_value(key, merchant, 'bank_account_id', account_cipher) if account_cipher else ''
            validate_webhook_keyring('activate', webhook_secret, ())
        except Exception:
            raise HTTPException(503, 'Configuración privada no disponible') from None
        try:
            if account_id:
                if lookup_pey_account(api_key, account_id) != 'ACTIVE':
                    raise HTTPException(409, 'La cuenta indicada debe estar activa y accesible desde esta llave')
            else:
                LivePeyGateway(api_key=api_key, bank_account_id='').check_key()
        except (ProviderError, ProviderAccountUnavailable):
            raise HTTPException(502, 'pey no pudo verificar el acceso con la llave guardada') from None
        with begin(accounts, principal, merchant) as db:
            row = db.get(MerchantPeySecret, merchant)
            if not row or draft_snapshot(row) != snapshot:
                raise HTTPException(409, 'La configuración cambió. Vuelve a verificarla.')
            if not row.active_credential_ref:
                ref = uuid.uuid4().hex
                # Bind encrypted copies to this version in addition to the tenant and field.
                db.add(MerchantPeyCredential(
                    ref=ref, merchant_id=merchant, api_key_id=api_key_id,
                    api_key=seal(key, merchant, 'api_key:' + ref, api_key),
                    webhook_secret=seal(key, merchant, 'webhook_secret:' + ref, webhook_secret),
                    bank_account_id=seal(key, merchant, 'bank_account_id:' + ref, account_id) if account_id else None,
                    checked_at=int(time.time()),
                ))
                db.flush()
                row.active_credential_ref = ref
                db.commit()
        accounts.activity.record('PEY_ACTIVATED',email=principal['email'],reference=merchant)
        return {'payment_active': True}

    @app.delete('/v1/merchants/{merchant}/pey-settings')
    def remove(merchant: str, request: Request):
        principal = accounts.session(request, csrf=True)
        with begin(accounts, principal, merchant) as db:
            row = db.get(MerchantPeySecret, merchant)
            if row:
                db.delete(row)
                db.commit()
        accounts.activity.record('PEY_REMOVED',email=principal['email'],reference=merchant)
        return {'deleted': True, 'payment_active': False}
