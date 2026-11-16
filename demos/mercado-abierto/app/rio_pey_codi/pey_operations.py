"""Tenant-scoped public pey API workflows and authenticated payment readback."""
import decimal
import hashlib
import hmac
import json
import time
from typing import Literal

from fastapi import HTTPException, Request, BackgroundTasks, Query
from pydantic import BaseModel, ConfigDict, Field, StrictInt, EmailStr, StrictBool, ValidationError, model_validator
from sqlalchemy import select, text, or_, and_
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from .app import parse_provider_amount
from .bank_accounts import BankAccountRegistration
from .models import Intent, PaymentReceipt
from .merchant_pey_checkout import merchant_gateway, _signing_version
from .pey import ProviderError, ProviderRejected, provider_json
from .pey_extended import FullPeyGateway, encode, identifier
from .pey_operations_models import PeyOperation
from .receipts import reserve_receipt
from .signatures import verify_and_capture


class OperationInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    id: str = Field(pattern=r'^[0-9a-f]{32}$')
    kind: Literal['BANK', 'PUSH', 'LINK', 'LINK_UPDATE']
    amount_minor: StrictInt | None = Field(default=None, gt=0, le=100000000)
    concept: str = Field(default='', max_length=140)
    order_id: str = Field(default='', max_length=70)
    numref: str = Field(default='0', pattern=r'^[0-9]{1,7}$')
    phone: str = Field(default='', max_length=10)
    expiration_s: StrictInt = Field(default=360, ge=360, le=86400)
    bank_account_id: str = Field(default='', max_length=140)
    alias: str = Field(default='', max_length=255)
    name: str = Field(default='', max_length=255)
    clabe: str = Field(default='', max_length=18)
    entity: Literal['BUSINESS', 'PERSON'] = 'PERSON'
    has_tip: StrictBool = False
    receipt_enabled: StrictBool = True
    payer_email: EmailStr | None = None
    parent_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{32}$')

    @model_validator(mode='after')
    def valid_operation(self):
        if self.kind == 'BANK':
            BankAccountRegistration(self.alias, self.name, self.clabe, self.entity)
        else:
            if self.amount_minor is None:
                raise ValueError('Indica un importe')
            if self.kind in ('PUSH', 'LINK') and self.receipt_enabled and not self.payer_email:
                raise ValueError('Indica el correo del cliente o desactiva el envío')
            if self.kind in ('PUSH', 'LINK') and not self.order_id.strip():
                raise ValueError('Indica un folio')
            if self.kind == 'PUSH' and (len(self.phone) != 10 or not self.phone.isascii() or not self.phone.isdigit()):
                raise ValueError('Teléfono de 10 dígitos requerido')
            if self.kind == 'LINK_UPDATE' and self.parent_id is None:
                raise ValueError('Selecciona el enlace')
        if self.bank_account_id:
            identifier(self.bank_account_id)
        return self


def gateway(accounts, row):
    c = merchant_gateway(accounts.Session, row.merchant_id, row.credential_ref)
    return FullPeyGateway(api_key=c.gateway.api_key, bank_account_id=c.gateway.bank_account_id)


def view(row):
    result = json.loads(row.result_json)
    local_archive = result.pop('_mercado_abierto_local_archive', None)
    return {'id': row.id, 'kind': row.kind, 'state': row.state, 'provider_id': row.provider_id,
        'intent_id': row.intent_id, 'amount_minor': row.amount_minor, 'created_at': row.created_at,
        'observed_at': row.observed_at, 'result': result, 'bank_settlement_verified': False,
        'locally_archived': isinstance(local_archive, dict),
        'locally_archived_at': local_archive.get('archived_at') if isinstance(local_archive, dict) else None}


def access(accounts, db, principal, merchant, *, owner=False):
    accounts.authorize_checkout(db, principal, merchant)
    accounts._member_role(db, principal['id'], merchant, {'owner'} if owner else {'owner', 'admin', 'cashier'}, lock=True)


def begin_lock(db):
    if db.bind.dialect.name == 'sqlite':
        db.execute(text('BEGIN IMMEDIATE'))


def reconcile(accounts, operation_id):
    with accounts.Session() as db:
        row = db.get(PeyOperation, operation_id)
    if row is None or row.provider_id is None:
        raise HTTPException(409, 'Resultado aún incierto. No repitas el cobro; revisa pey.')
    api = gateway(accounts, row)
    paid = []
    resolved_update = None
    expected_amount = row.amount_minor
    if row.kind == 'BANK':
        data = api.account(row.provider_id)
        if data.get('id') != row.provider_id or data.get('codiStatus') not in {'PENDING', 'PROCESSING', 'ACTIVE', 'ERROR'}:
            raise ValueError('Cuenta incompatible')
        state = data['codiStatus']
        result = {k: data[k] for k in ('alias', 'name', 'entity', 'codiStatus', 'errorMessage', 'dateCreated') if k in data}
        clabe = data.get('clabe')
        if isinstance(clabe, str):
            result['clabe_masked'] = '•••• ' + clabe[-4:]
    elif row.kind == 'PUSH':
        data = api.transaction(row.provider_id)
        if data.get('id') != row.provider_id or data.get('payableType') != 'API_CODI_PN' or data.get('status') not in {'PENDING', 'PAID'}:
            raise ValueError('Transacción incompatible')
        state = data['status']
        result = json.loads(row.result_json)
        if state == 'PAID':
            paid = [data]
    elif row.kind == 'LINK':
        data = api.link(row.provider_id)
        if data.get('id') != row.provider_id or data.get('clientReferenceId') != row.id or data.get('status') not in {'pending', 'processing', 'partial', 'paid'}:
            raise ValueError('Enlace incompatible')
        actual_amount = parse_provider_amount(data.get('amount'))
        if row.state == 'UPDATE_UNCERTAIN':
            with accounts.Session() as db:
                pending = list(db.scalars(select(PeyOperation).where(PeyOperation.parent_id == row.id, PeyOperation.state == 'UNCERTAIN')))
            if len(pending) != 1 or actual_amount not in {row.amount_minor, pending[0].amount_minor}:
                raise ValueError('Actualización incompatible')
            resolved_update = pending[0].id
            expected_amount = actual_amount
        elif actual_amount != row.amount_minor:
            raise ValueError('Importe del enlace modificado; requiere resolver la actualización antes de cobrar')
        state = data['status'].upper()
        result = json.loads(row.result_json)
        result['payment_methods'] = data.get('paymentMethods', [])
        if state == 'PAID':
            items = data.get('transactions')
            if not isinstance(items, list) or not 1 <= len(items) <= 20:
                raise ValueError('Transacciones del enlace requieren revisión')
            for item in items:
                tx = api.transaction(item.get('transactionId'))
                if tx.get('id') != item.get('transactionId') or tx.get('payableType') != 'PAYMENT_LINK' or tx.get('payableId') != row.provider_id:
                    raise ValueError('Transacción ajena al enlace')
                paid.append(tx)
    else:
        raise HTTPException(409, 'Consulta el enlace original')
    digest = None
    if paid:
        ids = set()
        base = 0
        evidence = []
        for tx in paid:
            txid = tx.get('id')
            identifier(txid)
            if txid in ids or tx.get('status') != 'PAID' or tx.get('currency') != 'MXN' or tx.get('paymentMethod') not in {'CODI', 'CARD'}:
                raise ValueError('Pago incompatible')
            ids.add(txid)
            date = tx.get('datePaid')
            if type(date) is not int or date <= 0:
                raise ValueError('Fecha de pago inválida')
            total = parse_provider_amount(tx.get('amount'))
            breakdown = tx.get('amountBreakdown')
            if not isinstance(breakdown, dict) or 'base' not in breakdown:
                raise ValueError('Desglose de pago requerido')
            parts = [0 if type(breakdown.get(k, 0)) in (int, decimal.Decimal) and breakdown.get(k, 0) == 0 else parse_provider_amount(breakdown[k]) for k in ('base', 'tip', 'fee')]
            if any(v < 0 for v in parts) or sum(parts) != total:
                raise ValueError('Desglose incompatible')
            base += parts[0]
            if row.kind == 'PUSH' and tx.get('paymentMethod') != 'CODI':
                raise ValueError('Método incompatible')
            evidence.append([txid, total, parts, date])
        if base != expected_amount:
            raise ValueError('Pago parcial o excedente; requiere revisión')
        digest = hashlib.sha256(encode(evidence).encode()).hexdigest()
        result['transactions'] = [{'id': x[0], 'amount_minor': x[1], 'base_minor': x[2][0], 'tip_minor': x[2][1], 'fee_minor': x[2][2], 'date_paid': x[3]} for x in evidence]
    with accounts.Session.begin() as db:
        begin_lock(db)
        current = db.get(PeyOperation, row.id, with_for_update=True)
        if current.state == 'UPDATING':
            raise HTTPException(409, 'El importe se está actualizando; vuelve a consultar')
        if current.amount_minor != row.amount_minor:
            raise HTTPException(409, 'La operación cambió; vuelve a consultar')
        if current.state == 'PAID' and state != 'PAID':
            raise ValueError('Estado de pago contradictorio')
        if resolved_update:
            update = db.get(PeyOperation, resolved_update, with_for_update=True)
            if current.state != 'UPDATE_UNCERTAIN' or update.state != 'UNCERTAIN':
                raise HTTPException(409, 'La actualización cambió; vuelve a consultar')
            update.state = 'UPDATED' if expected_amount == update.amount_minor else 'NOT_APPLIED'
            current.amount_minor = expected_amount
            db.get(Intent, current.intent_id).amount_minor = expected_amount
        # Preserve the local list-hiding marker when a previously archived bank
        # account is refreshed from pey. It is not a provider-side deletion.
        previous_result = json.loads(current.result_json)
        local_archive = previous_result.get('_mercado_abierto_local_archive')
        if isinstance(local_archive, dict):
            result['_mercado_abierto_local_archive'] = local_archive
        current.state, current.result_json, current.observed_at = state, encode(result), int(time.time())
        if digest:
            intent = db.get(Intent, current.intent_id, with_for_update=True)
            # Receipt ID binds the aggregate link or the exact push transaction.
            transaction_id = paid[0]['id'] if len(paid) == 1 else 'link:' + row.provider_id
            if intent.transaction_id and intent.transaction_id != transaction_id:
                raise ValueError('Confirmación contradictoria')
            intent.status, intent.transaction_id = 'PROVIDER_REPORTED', transaction_id
            intent.provider_payment_source = 'PEY_AUTHENTICATED_READBACK'
            intent.provider_payment_sha256 = digest
            intent.provider_payment_observed_at = int(time.time())
        db.flush()
        observed = view(current)
    if state != row.state:
        accounts.activity.record('PEY_OPERATION_CONFIRMED', reference=row.id)
    return observed


def receive_extended_event(accounts, merchant, headers, body):
    data = provider_json(body)
    kind = {'bank.account.updated': 'BANK', 'codi.pn.payment_received': 'PUSH', 'payment_link.status_updated': 'LINK'}.get(data.get('type'))
    if kind is None:
        return None
    provider_id = data.get({'BANK': 'bankAccountId', 'PUSH': 'transactionId', 'LINK': 'paymentLinkId'}[kind])
    identifier(provider_id)
    with accounts.Session() as db:
        row = db.scalar(select(PeyOperation).where(PeyOperation.merchant_id == merchant, PeyOperation.kind == kind, PeyOperation.provider_id == provider_id))
    if row is None:
        credential = merchant_gateway(accounts.Session, merchant)
        verify_and_capture(headers, body, credential.webhook_secret, credential.reference)
        raise HTTPException(409, 'Operación todavía no asociada; consulta el estado en la aplicación')
    credential = merchant_gateway(accounts.Session, merchant, row.credential_ref)
    from types import SimpleNamespace
    _signing_version(accounts.Session, SimpleNamespace(merchant_id=row.merchant_id, pey_credential_ref=row.credential_ref), credential, headers, body)
    if credential.api_key_id and data.get('apiKeyId', data.get('ownerId')) != credential.api_key_id:
        raise ValueError('Llave incompatible')
    # Notification fields alone never confirm payment: re-read the persisted resource.
    result = reconcile(accounts, row.id)
    return {'outcome': result['state'], 'intent_id': result['intent_id']}


def route_webhook_merchant(accounts, merchant, headers, body):
    """One webhook per API key: route only to a resource owned by that same key."""
    data = provider_json(body)
    kind = {'bank.account.updated': 'BANK', 'codi.pn.payment_received': 'PUSH',
            'payment_link.status_updated': 'LINK'}.get(data.get('type'))
    with accounts.Session() as db:
        if kind:
            value = data.get({'BANK':'bankAccountId','PUSH':'transactionId','LINK':'paymentLinkId'}[kind])
            identifier(value)
            candidates = list(db.scalars(select(PeyOperation).where(PeyOperation.kind == kind, PeyOperation.provider_id == value).limit(20)))
            refs = [(x.merchant_id, x.credential_ref) for x in candidates]
        elif data.get('type') == 'codi.qr.payment_received':
            from .merchant_pey_checkout import _provider_intent
            value = _provider_intent(data)
            query = select(Intent).where(Intent.id == value) if value else select(Intent).where(Intent.provider_qr_id == data.get('codiQrId'))
            refs = [(x.merchant_id, x.pey_credential_ref) for x in db.scalars(query.limit(20))]
        else:
            return merchant
    if any(m == merchant for m, _ in refs):
        return merchant
    if not refs:
        return merchant
    endpoint = merchant_gateway(accounts.Session, merchant)
    verify_and_capture(headers, body, endpoint.webhook_secret, endpoint.reference)
    matches = []
    for other, ref in refs:
        if not ref:
            continue
        candidate = merchant_gateway(accounts.Session, other, ref)
        if hmac.compare_digest(endpoint.gateway.api_key, candidate.gateway.api_key):
            matches.append(other)
    if len(set(matches)) != 1:
        raise ValueError('Webhook no asociado de forma única a este negocio')
    return matches[0]


def register_pey_operations(app, accounts, cfg, receipts):
    @app.get('/pago/{operation}')
    def payment_return(operation: str):
        from fastapi.responses import HTMLResponse
        from pathlib import Path
        if not __import__('re').fullmatch(r'[0-9a-f]{32}', operation):
            raise HTTPException(404, 'Pago no encontrado')
        return HTMLResponse((Path(__file__).parent/'static'/'payment-return.html').read_text())

    @app.get('/v1/public/payments/{operation}')
    def public_payment(operation: str):
        if not __import__('re').fullmatch(r'[0-9a-f]{32}', operation):
            raise HTTPException(404, 'Pago no encontrado')
        with accounts.Session() as db:
            row = db.get(PeyOperation, operation)
            if row is None or row.kind != 'LINK':
                raise HTTPException(404, 'Pago no encontrado')
            receipt = db.get(PaymentReceipt, row.intent_id)
            from .receipts import eligible
            confirmed = row.state == 'PAID' and receipt and receipt.issued_at and eligible(db.get(Intent, row.intent_id))
            return {'state': 'PAID' if confirmed else 'PENDING', 'amount_minor': row.amount_minor,
                'receipt_url': receipts.link(receipt) if confirmed else None}

    @app.get('/v1/merchants/{merchant}/pey-bank-accounts/{account_id}')
    def bank_details(merchant: str, account_id: str, request: Request):
        principal = accounts.session(request)
        with accounts.Session() as db:
            access(accounts, db, principal, merchant, owner=True)
        c = merchant_gateway(accounts.Session, merchant)
        api = FullPeyGateway(api_key=c.gateway.api_key, bank_account_id=c.gateway.bank_account_id)
        try:
            data = api.account(account_id)
            if data.get('id') != account_id:
                raise ValueError('Cuenta incompatible')
            result = {k: data[k] for k in ('id','alias','name','entity','codiStatus','errorMessage','dateCreated') if k in data}
            result['clabe_masked'] = '•••• ' + str(data.get('clabe',''))[-4:]
            return result
        except (ValueError, ProviderError):
            raise HTTPException(502, 'No se pudo consultar la cuenta con esta llave') from None

    def execute(principal, merchant, value):
        now = int(time.time())
        digest = hashlib.sha256(encode(value.model_dump(mode='json')).encode()).hexdigest()
        with accounts.Session.begin() as db:
            begin_lock(db)
            access(accounts, db, principal, merchant, owner=value.kind == 'BANK')
            existing = db.get(PeyOperation, value.id)
            if existing:
                if existing.merchant_id != merchant or existing.request_hash != digest:
                    raise HTTPException(409, 'Identificador usado para otra operación')
                return view(existing)
            credential = merchant_gateway(accounts.Session, merchant, db=db)
            parent = None
            if value.kind == 'LINK_UPDATE':
                parent = db.get(PeyOperation, value.parent_id, with_for_update=True)
                if not parent or parent.merchant_id != merchant or parent.kind != 'LINK' or parent.state != 'PENDING':
                    raise HTTPException(409, 'Solo puedes modificar enlaces pendientes')
                credential = merchant_gateway(accounts.Session, merchant, parent.credential_ref, db=db)
                parent.state = 'UPDATING'
            intent_id = None
            if value.kind in ('PUSH', 'LINK'):
                intent_id = value.id
                intent = Intent(id=intent_id, merchant_id=merchant, order_id=value.order_id,
                    amount_minor=value.amount_minor, concept=value.concept or 'Cobro', numref=value.numref,
                    expiration_s=value.expiration_s, status='EXT_PENDING', created_at=now, pey_credential_ref=credential.reference)
                db.add(intent)
                db.flush()
                reserve_receipt(db, intent, value.receipt_enabled, str(value.payer_email) if value.payer_email else None)
            row = PeyOperation(id=value.id, merchant_id=merchant, actor_id=principal['id'], credential_ref=credential.reference,
                kind=value.kind, request_hash=digest, state='SUBMITTING', intent_id=intent_id, parent_id=value.parent_id,
                amount_minor=value.amount_minor, account_id=value.bank_account_id or credential.gateway.bank_account_id,
                result_json='{}', created_at=now)
            db.add(row)
            db.flush()
            parent_provider_id = parent.provider_id if parent else None
        api = gateway(accounts, row)
        state, result, provider_id = 'UNCERTAIN', {}, None
        try:
            if value.kind == 'BANK':
                result = api.register_account(alias=value.alias, name=value.name, clabe=value.clabe, entity=value.entity)
                provider_id, state = result['id'], result['codiStatus']
            elif value.kind == 'PUSH':
                if row.account_id:
                    account = api.account(row.account_id)
                    if account.get('id') != row.account_id or account.get('codiStatus') != 'ACTIVE':
                        raise ProviderRejected('La cuenta aún no está activa')
                result = api.push(amount_minor=value.amount_minor, phone=value.phone, concept=value.concept,
                    numref=value.numref, expiration_s=value.expiration_s, operation_id=row.id, bank_account_id=row.account_id)
                provider_id, state = result['transactionId'], 'PENDING'
            elif value.kind == 'LINK':
                result = api.create_link(amount_minor=value.amount_minor, operation_id=row.id,
                    success_url=cfg.public_url.rstrip('/')+'/pago/'+row.id, back_url=cfg.public_url.rstrip('/')+'/pago/'+row.id, has_tip=value.has_tip)
                provider_id, state = result['id'], 'PENDING'
            else:
                before = api.link(parent_provider_id)
                if before.get('id') != parent_provider_id or before.get('status') != 'pending':
                    raise ProviderRejected('El enlace ya no está pendiente')
                api.update_link(parent_provider_id, value.amount_minor)
                after = api.link(parent_provider_id)
                if after.get('id') != parent_provider_id or parse_provider_amount(after.get('amount')) != value.amount_minor:
                    raise ProviderError('Actualización sin confirmar')
                state = 'UPDATED'
        except ProviderRejected:
            state = 'REJECTED'
        except (ProviderError, ValueError, TypeError, KeyError):
            state = 'UNCERTAIN'
        with accounts.Session.begin() as db:
            current = db.get(PeyOperation, row.id, with_for_update=True)
            current.provider_id, current.state, current.result_json = provider_id, state, encode(result)
            current.observed_at = int(time.time())
            if value.kind == 'LINK_UPDATE':
                parent = db.get(PeyOperation, value.parent_id, with_for_update=True)
                if state == 'UPDATED':
                    parent.amount_minor = value.amount_minor
                    db.get(Intent, parent.intent_id).amount_minor = value.amount_minor
                    parent.state = 'PENDING'
                else:
                    parent.state = 'UPDATE_UNCERTAIN' if state == 'UNCERTAIN' else 'PENDING'
            db.flush()
            result = view(current)
        event = 'PEY_OPERATION_UNCERTAIN' if state == 'UNCERTAIN' else 'PEY_OPERATION_REJECTED' if state == 'REJECTED' else 'PEY_OPERATION_SAVED'
        accounts.activity.record(event, email=principal['email'], reference=row.id)
        return result

    @app.post('/v1/merchants/{merchant}/pey-operations')
    async def create(merchant: str, request: Request):
        principal = await run_in_threadpool(accounts.session, request, csrf=True)
        if cfg.mode != 'LIVE' or not cfg.live_enabled:
            raise HTTPException(503, 'Cobros pey no habilitados')
        accounts.limit(request, 'pey-operation', principal['id'])
        raw = bytearray()
        async for part in request.stream():
            raw.extend(part)
            if len(raw) > 8192:
                raise HTTPException(413, 'Solicitud demasiado grande')
        try:
            value = OperationInput.model_validate(provider_json(bytes(raw)))
        except (ValueError, ValidationError, ProviderError):
            raise HTTPException(422, 'Revisa los datos de la operación') from None
        try:
            return await run_in_threadpool(execute, principal, merchant, value)
        except IntegrityError:
            raise HTTPException(409, 'Folio, referencia u operación ya registrados; consulta el historial') from None

    @app.get('/v1/merchants/{merchant}/pey-operations')
    def listing(merchant: str, request: Request, before: str | None = None):
        principal = accounts.session(request)
        with accounts.Session() as db:
            access(accounts, db, principal, merchant)
            query = select(PeyOperation).where(PeyOperation.merchant_id == merchant)
            if before:
                identifier(before)
                anchor = db.get(PeyOperation, before)
                if not anchor or anchor.merchant_id != merchant:
                    raise HTTPException(422, 'Cursor inválido')
                query = query.where(or_(PeyOperation.created_at < anchor.created_at, and_(PeyOperation.created_at == anchor.created_at, PeyOperation.id < anchor.id)))
            rows = list(db.scalars(query.order_by(PeyOperation.created_at.desc(), PeyOperation.id.desc()).limit(101)))
            return {'items': [view(r) for r in rows[:100]], 'next_cursor': rows[99].id if len(rows)>100 else None}

    @app.post('/v1/merchants/{merchant}/pey-operations/{operation}/archive')
    def archive_bank_account(merchant: str, operation: str, request: Request):
        principal = accounts.session(request, csrf=True)
        with accounts.Session.begin() as db:
            access(accounts, db, principal, merchant, owner=True)
            row = db.get(PeyOperation, operation, with_for_update=True)
            if not row or row.merchant_id != merchant:
                raise HTTPException(404, 'Cuenta no encontrada')
            if row.kind != 'BANK':
                raise HTTPException(409, 'Solo se pueden retirar cuentas bancarias de esta lista')
            result = json.loads(row.result_json)
            if not isinstance(result.get('_mercado_abierto_local_archive'), dict):
                result['_mercado_abierto_local_archive'] = {'archived_at': int(time.time())}
                row.result_json = encode(result)
            response = view(row)
        accounts.activity.record('PEY_BANK_ACCOUNT_HIDDEN', email=principal['email'], reference=row.id)
        return response

    @app.post('/v1/merchants/{merchant}/pey-operations/{operation}/restore')
    def restore_bank_account(merchant: str, operation: str, request: Request):
        principal = accounts.session(request, csrf=True)
        with accounts.Session.begin() as db:
            access(accounts, db, principal, merchant, owner=True)
            row = db.get(PeyOperation, operation, with_for_update=True)
            if not row or row.merchant_id != merchant:
                raise HTTPException(404, 'Cuenta no encontrada')
            if row.kind != 'BANK':
                raise HTTPException(409, 'Solo se pueden restaurar cuentas bancarias')
            result = json.loads(row.result_json)
            result.pop('_mercado_abierto_local_archive', None)
            row.result_json = encode(result)
            response = view(row)
        accounts.activity.record('PEY_BANK_ACCOUNT_RESTORED', email=principal['email'], reference=row.id)
        return response

    @app.post('/v1/merchants/{merchant}/pey-operations/{operation}/refresh')
    def refresh(merchant: str, operation: str, request: Request, background_tasks: BackgroundTasks):
        principal = accounts.session(request, csrf=True)
        with accounts.Session() as db:
            access(accounts, db, principal, merchant)
            row = db.get(PeyOperation, operation)
            if not row or row.merchant_id != merchant:
                raise HTTPException(404, 'Operación no encontrada')
        try:
            result = reconcile(accounts, operation)
        except (ProviderError, ValueError, IntegrityError, TypeError):
            raise HTTPException(409, 'pey no confirmó un estado compatible; se conserva el registro') from None
        if result.get('state') == 'PAID':
            background_tasks.add_task(receipts.issue, result['intent_id'])
        return result

    @app.post('/v1/merchants/{merchant}/pey-operations/{operation}/recover')
    def recover(merchant: str, operation: str, request: Request, background_tasks: BackgroundTasks, provider_id: str = Query(max_length=140)):
        principal = accounts.session(request, csrf=True)
        with accounts.Session() as db:
            access(accounts, db, principal, merchant, owner=True)
            row = db.get(PeyOperation, operation)
            if not row or row.merchant_id != merchant:
                raise HTTPException(404, 'Operación no encontrada')
            if row.state not in {'SUBMITTING','UNCERTAIN'} or row.provider_id:
                raise HTTPException(409, 'La operación ya tiene un resultado')
        api = gateway(accounts, row)
        try:
            identifier(provider_id)
            if row.kind == 'PUSH':
                data = api.transaction(provider_id)
                if data.get('id') != provider_id or data.get('payableType') != 'API_CODI_PN' or data.get('metadata',{}).get('externalMetadata',{}).get('mercadoOperationId') != row.id or parse_provider_amount(data.get('amount')) != row.amount_minor:
                    raise ValueError('Transacción incompatible')
                result = {'transactionId': provider_id, 'codiId': data.get('payableId')}
            elif row.kind == 'LINK':
                data = api.link(provider_id)
                if data.get('id') != provider_id or data.get('clientReferenceId') != row.id or parse_provider_amount(data.get('amount')) != row.amount_minor:
                    raise ValueError('Enlace incompatible')
                result = {'id':provider_id}
            elif row.kind == 'BANK':
                data = api.account(provider_id)
                original = OperationInput(id=row.id,kind='BANK',alias=data['alias'],name=data['name'],clabe=data['clabe'],entity=data['entity'])
                if data.get('id') != provider_id or hashlib.sha256(encode(original.model_dump(mode='json')).encode()).hexdigest() != row.request_hash:
                    raise ValueError('Cuenta incompatible')
                result = {'id':provider_id}
            else:
                raise ValueError('Consulta el enlace original')
            with accounts.Session.begin() as db:
                begin_lock(db)
                access(accounts, db, principal, merchant, owner=True)
                current = db.get(PeyOperation, row.id, with_for_update=True)
                if current.state not in {'SUBMITTING','UNCERTAIN'} or current.provider_id:
                    raise HTTPException(409, 'La operación cambió; consulta su estado')
                current.provider_id, current.result_json, current.state = provider_id, encode(result), 'PENDING'
            recovered = reconcile(accounts, row.id)
            if recovered['state'] == 'PAID':
                background_tasks.add_task(receipts.issue, recovered['intent_id'])
            return recovered
        except (ProviderError, ValueError, KeyError, TypeError, IntegrityError):
            raise HTTPException(409, 'El recurso de pey no coincide con esta solicitud') from None

    @app.get('/v1/merchants/{merchant}/pey-transactions/{transaction_id}')
    def transaction_details(merchant: str, transaction_id: str, request: Request):
        principal = accounts.session(request)
        try:
            identifier(transaction_id)
        except ValueError:
            raise HTTPException(422, 'Identificador de transacción inválido') from None
        with accounts.Session() as db:
            access(accounts, db, principal, merchant, owner=True)
            intent = db.scalar(select(Intent).where(Intent.merchant_id == merchant,
                Intent.transaction_id == transaction_id))
            operation = db.scalar(select(PeyOperation).where(PeyOperation.merchant_id == merchant,
                PeyOperation.kind == 'PUSH', PeyOperation.provider_id == transaction_id))
            link_candidates = list(db.scalars(select(PeyOperation).where(
                PeyOperation.merchant_id == merchant, PeyOperation.kind == 'LINK',
                PeyOperation.state == 'PAID',
                PeyOperation.result_json.contains('"id":"' + transaction_id + '"')).limit(3)))
            link_operation = None
            for candidate in link_candidates:
                try:
                    saved = json.loads(candidate.result_json)
                except (TypeError, json.JSONDecodeError):
                    continue
                if any(isinstance(item, dict) and item.get('id') == transaction_id
                       for item in saved.get('transactions', [])):
                    if link_operation is not None:
                        raise HTTPException(409, 'La transacción aparece en más de un enlace')
                    link_operation = candidate
            if intent is None and operation is None and link_operation is None:
                raise HTTPException(404, 'Transacción no encontrada en los registros de este negocio')
            if intent is not None:
                reference = intent.pey_credential_ref
                qr_id = intent.provider_qr_id
                related = db.scalar(select(PeyOperation).where(PeyOperation.intent_id == intent.id,
                    PeyOperation.kind.in_(('PUSH', 'LINK'))))
            elif link_operation is not None:
                reference = link_operation.credential_ref
                qr_id = None
                related = link_operation
            else:
                reference = operation.credential_ref
                qr_id = None
                related = operation
        credential = merchant_gateway(accounts.Session, merchant, reference)
        api = FullPeyGateway(api_key=credential.gateway.api_key,
                             bank_account_id=credential.gateway.bank_account_id)
        try:
            data = api.transaction(transaction_id)
            if data.get('id') != transaction_id:
                raise ValueError('ID de transacción incompatible')
            if qr_id:
                if data.get('payableType') != 'API_CODI_QR' or data.get('payableId') != qr_id:
                    raise ValueError('QR incompatible')
            elif related and related.kind == 'PUSH':
                saved = json.loads(related.result_json)
                if data.get('payableType') != 'API_CODI_PN' or data.get('payableId') != saved.get('codiId'):
                    raise ValueError('Notificación incompatible')
            elif related and related.kind == 'LINK':
                saved = json.loads(related.result_json)
                known = {item.get('id') for item in saved.get('transactions', []) if isinstance(item, dict)}
                if transaction_id not in known or data.get('payableType') != 'PAYMENT_LINK' or data.get('payableId') != related.provider_id:
                    raise ValueError('Enlace incompatible')
            else:
                raise ValueError('Referencia local incompatible')
            fields = {'id', 'status', 'amount', 'amountBreakdown', 'currency', 'paymentMethod',
                      'payableType', 'payableId', 'applicationFee', 'dateCreated', 'datePaid'}
            return {key: data[key] for key in fields if key in data}
        except (ProviderError, ValueError, TypeError, KeyError):
            raise HTTPException(502, 'No se pudo consultar una transacción de pey asociada a este negocio') from None

    @app.get('/v1/merchants/{merchant}/pey-transactions')
    def transactions(merchant: str, request: Request, account_id: str | None = None,
                     qr_id: str | None = None,
                     next_token: str | None = Query(default=None, max_length=4096)):
        principal = accounts.session(request)
        if account_id and qr_id:
            raise HTTPException(422, 'Consulta por cuenta bancaria o por QR, no por ambos')
        with accounts.Session() as db:
            access(accounts, db, principal, merchant, owner=True)
            intent = db.scalar(select(Intent).where(Intent.merchant_id == merchant,
                Intent.provider_qr_id == qr_id)) if qr_id else None
        if qr_id:
            try:
                identifier(qr_id)
            except ValueError:
                raise HTTPException(422, 'Identificador de QR inválido') from None
            if intent is None or not intent.pey_credential_ref:
                raise HTTPException(404, 'QR no encontrado en los registros de este negocio')
            credential = merchant_gateway(accounts.Session, merchant, intent.pey_credential_ref)
        else:
            credential = merchant_gateway(accounts.Session, merchant)
        api = FullPeyGateway(api_key=credential.gateway.api_key, bank_account_id=credential.gateway.bank_account_id)
        try:
            data = api.qr_transactions(qr_id, token=next_token) if qr_id else api.transactions(account_id=account_id, token=next_token)
            items = data.get('items')
            if not isinstance(items, list) or len(items) > 80 or any(not isinstance(x, dict) for x in items):
                raise ValueError('Página inválida')
            cursor = data.get('nextToken')
            if cursor is not None and (not isinstance(cursor, str) or not 0 < len(cursor) <= 4096 or not cursor.isprintable()):
                raise ValueError('Cursor inválido')
            # Minimize payer banking data; this is a ledger, not payment confirmation.
            fields = {'id','status','amount','currency','paymentMethod','payableType','payableId','datePaid','dateCreated','amountBreakdown','applicationFee'}
            return {'items': [{k: v for k, v in x.items() if k in fields} for x in items], 'next_token': cursor}
        except (ProviderError, ValueError, TypeError):
            raise HTTPException(502, 'No se pudo consultar el historial de pey') from None
