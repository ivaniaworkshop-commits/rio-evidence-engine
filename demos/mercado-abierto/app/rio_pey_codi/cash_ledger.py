"""Authenticated cash declarations. A saved declaration is never bank evidence."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
import re
import time
from typing import Literal

from fastapi import HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError, field_validator, model_validator
from sqlalchemy import and_, or_, select, text
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from starlette.concurrency import run_in_threadpool

from .cash_ledger_models import CashSale

MAX_CENTS = 100000000
ROLES = {'owner', 'admin', 'cashier'}
SALE_ID = r'^CASH-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'


class CashLine(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    description: str = Field(min_length=1, max_length=90)
    kind: Literal['piece', 'weight']
    quantity: StrictInt = Field(gt=0, le=1000000)
    priceCents: StrictInt = Field(ge=0, le=MAX_CENTS)
    amountCents: StrictInt = Field(gt=0, le=MAX_CENTS)

    @field_validator('description')
    @classmethod
    def description_text(cls, value):
        value = value.strip()
        if not value or any(ord(c) < 32 for c in value):
            raise ValueError('Invalid product description')
        return value

    @model_validator(mode='after')
    def exact_total(self):
        expected = self.priceCents * self.quantity
        if self.kind == 'weight':
            expected = (expected + 500) // 1000
        if expected != self.amountCents:
            raise ValueError('Product total does not match quantity and price')
        return self


class CashInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    id: str = Field(pattern=SALE_ID)
    createdAt: str = Field(min_length=20, max_length=40)
    folio: str = Field(max_length=70)
    concept: str = Field(min_length=1, max_length=140)
    amountMinor: StrictInt = Field(gt=0, le=MAX_CENTS)
    receivedMinor: StrictInt = Field(ge=0, le=MAX_CENTS)
    changeMinor: StrictInt = Field(ge=0, le=MAX_CENTS)
    lines: list[CashLine] = Field(max_length=30)
    source: Literal['USER_DECLARED_CASH']
    paymentMethod: Literal['cash']
    bankPaymentConfirmed: Literal[False]

    @field_validator('createdAt')
    @classmethod
    def valid_created(cls, value):
        try:
            stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if stamp.tzinfo is None or stamp.timestamp() < 0 or stamp.timestamp() > time.time() + 300:
                raise ValueError('Invalid date')
            return stamp.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        except (ValueError, OverflowError):
            raise ValueError('Invalid date') from None

    @field_validator('folio')
    @classmethod
    def valid_folio(cls, value):
        if value and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,69}', value):
            raise ValueError('Invalid sale folio')
        return value

    @field_validator('concept')
    @classmethod
    def valid_concept(cls, value):
        value = value.strip()
        if not value or any(ord(c) < 32 for c in value):
            raise ValueError('Invalid concept')
        return value

    @field_validator('bankPaymentConfirmed', mode='before')
    @classmethod
    def only_false(cls, value):
        if value is not False:
            raise ValueError('Cash cannot confirm bank payments')
        return value

    @model_validator(mode='after')
    def exact_cash(self):
        if self.receivedMinor < self.amountMinor or self.changeMinor != self.receivedMinor - self.amountMinor:
            raise ValueError('Cash change does not match received amount')
        if self.lines and sum(line.amountCents for line in self.lines) != self.amountMinor:
            raise ValueError('Products do not match cash total')
        return self


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def _view(row):
    value = json.loads(row.payload_json)
    return {**value, 'recordedAt': datetime.fromtimestamp(row.recorded_at, timezone.utc).isoformat().replace('+00:00', 'Z'),
            'recordedBy': row.actor_id, 'persisted': True}


def _cursor(row):
    return base64.urlsafe_b64encode(_canonical([row.recorded_at, row.id]).encode()).decode().rstrip('=')


def _decode_cursor(value):
    if value is None:
        return None
    try:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', value):
            raise ValueError()
        data = json.loads(base64.urlsafe_b64decode(value + '=' * (-len(value) % 4)))
        if not (isinstance(data, list) and len(data) == 2 and type(data[0]) is int and data[0] >= 0
                and isinstance(data[1], str) and re.fullmatch(SALE_ID, data[1])):
            raise ValueError()
        return data
    except (ValueError, TypeError, UnicodeDecodeError):
        raise HTTPException(422, 'Cursor de efectivo inválido.') from None


async def _body(request):
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > 32768:
            raise HTTPException(413, 'El registro de efectivo excede el límite.')
        raw.extend(chunk)
    def unique_pairs(pairs):
        output = {}
        for key, value in pairs:
            if key in output:
                raise ValueError('Duplicate key')
            output[key] = value
        return output
    try:
        data = json.loads(raw, object_pairs_hook=unique_pairs,
                          parse_constant=lambda _v: (_ for _ in ()).throw(ValueError('Invalid JSON')))
        return CashInput.model_validate(data).model_dump()
    except (ValueError, ValidationError, TypeError, RecursionError):
        raise HTTPException(422, 'Registro de efectivo inválido: revisa folio, productos, importes y cambio.') from None


def register_cash_ledger_routes(app, accounts):
    def load(principal, merchant_id, limit, before, sale_id=None):
        try:
            with accounts.Session() as db:
                accounts._session_access(db, principal, lock=False)
                accounts._member_role(db, principal['id'], merchant_id, ROLES)
                if sale_id is not None:
                    row = db.get(CashSale, {'merchant_id': merchant_id, 'id': sale_id})
                    if row is None:
                        raise HTTPException(404, 'Registro de efectivo no encontrado.')
                    return {'sale': _view(row)}
                query = select(CashSale).where(CashSale.merchant_id == merchant_id)
                if before:
                    query = query.where(or_(CashSale.recorded_at < before[0],
                        and_(CashSale.recorded_at == before[0], CashSale.id < before[1])))
                rows = list(db.scalars(query.order_by(CashSale.recorded_at.desc(), CashSale.id.desc()).limit(limit + 1)))
                return {'sales': [_view(row) for row in rows[:limit]],
                        'next_cursor': _cursor(rows[limit - 1]) if len(rows) > limit else None}
        except (OperationalError, ProgrammingError):
            raise HTTPException(503, 'El historial de efectivo no está disponible.') from None

    def save(principal, merchant_id, value):
        serialized = _canonical(value)
        digest = hashlib.sha256(serialized.encode()).hexdigest()
        try:
            with accounts.Session.begin() as db:
                if db.bind.dialect.name == 'sqlite':
                    db.execute(text('BEGIN IMMEDIATE'))
                accounts.authorize_checkout(db, principal, merchant_id)
                previous = db.get(CashSale, {'merchant_id': merchant_id, 'id': value['id']})
                if previous is not None:
                    if previous.payload_sha256 != digest:
                        raise HTTPException(409, 'Ese registro ya existe con datos diferentes; no se modificó.')
                    return {'sale': _view(previous), 'persisted': True, 'replayed': True}
                row = CashSale(merchant_id=merchant_id, id=value['id'], actor_id=principal['id'],
                    folio=value['folio'] or None, amount_minor=value['amountMinor'], received_minor=value['receivedMinor'],
                    change_minor=value['receivedMinor']-value['amountMinor'], payload_json=serialized,
                    payload_sha256=digest, recorded_at=int(time.time()))
                db.add(row)
                db.flush()
                return {'sale': _view(row), 'persisted': True, 'replayed': False}
        except IntegrityError:
            raise HTTPException(409, 'El folio ya está registrado en este negocio; revisa el historial.') from None
        except (OperationalError, ProgrammingError):
            raise HTTPException(503, 'No se pudo confirmar el guardado de efectivo. Conserva esta venta y reintenta.') from None

    @app.get('/v1/merchants/{merchant_id}/cash-sales')
    async def get_cash(request: Request, merchant_id: str, limit: int = Query(default=100, ge=1, le=200), cursor: str | None = None):
        principal = await run_in_threadpool(accounts.session, request)
        return await run_in_threadpool(load, principal, merchant_id, limit, _decode_cursor(cursor))

    @app.get('/v1/merchants/{merchant_id}/cash-sales/{sale_id}')
    async def get_cash_sale(request: Request, merchant_id: str, sale_id: str):
        principal = await run_in_threadpool(accounts.session, request)
        return await run_in_threadpool(load, principal, merchant_id, 1, None, sale_id)

    @app.post('/v1/merchants/{merchant_id}/cash-sales', status_code=201)
    async def post_cash(request: Request, merchant_id: str):
        principal = await run_in_threadpool(accounts.session, request, True)
        value = await _body(request)
        return await run_in_threadpool(save, principal, merchant_id, value)
