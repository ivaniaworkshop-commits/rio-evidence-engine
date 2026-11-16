"""Shared, actor-authorized commerce records for Mercado Abierto.

Catalog publication is explicit. Commercial transitions are durable declarations
by their authorized actors; payment evidence is read only from actual CoDi data.
The old educational snapshots are never imported into this market.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import secrets
import time
import uuid
from contextlib import contextmanager
from typing import Literal

from fastapi import HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import or_, select, text
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from starlette.concurrency import run_in_threadpool

from .models import Intent, Membership, Merchant, PaymentReceipt
from .merchant_pey_checkout import qr_png
from .production_market_models import (MarketCart, MarketCartItem, MarketDeliveryAddress, MarketFreight,
    MarketListing, MarketOrder, MarketOrderEvent, MarketOrderItem, MarketOrderQR, MarketProfile, MarketQuote)
from .receipts import eligible

LOCALITIES = (
    ('alvaro-obregon', 'Álvaro Obregón'), ('azcapotzalco', 'Azcapotzalco'),
    ('benito-juarez', 'Benito Juárez'), ('coyoacan', 'Coyoacán'),
    ('cuajimalpa-de-morelos', 'Cuajimalpa de Morelos'), ('cuauhtemoc', 'Cuauhtémoc'),
    ('gustavo-a-madero', 'Gustavo A. Madero'), ('iztacalco', 'Iztacalco'),
    ('iztapalapa', 'Iztapalapa'), ('la-magdalena-contreras', 'La Magdalena Contreras'),
    ('miguel-hidalgo', 'Miguel Hidalgo'), ('milpa-alta', 'Milpa Alta'),
    ('tlahuac', 'Tláhuac'), ('tlalpan', 'Tlalpan'),
    ('venustiano-carranza', 'Venustiano Carranza'), ('xochimilco', 'Xochimilco'),
)
LOCALITY_CODES = {code for code, _ in LOCALITIES}
WRITE_ROLES = {'owner', 'admin'}
MAX_MINOR = 100_000_000
MAX_QUANTITY = 1_000_000_000
PLATFORM_FEE_BPS = 500
MAX_LISTING_IMAGE_BYTES = 1_500_000


def cached(db, model, ident):
    # Strong references scoped to one DB session avoid per-card network queries.
    cache = db.info.setdefault('market_objects', {})
    key = (model, ident)
    if key not in cache:
        cache[key] = db.get(model, ident)
    return cache[key]


def prime(db, model, identifiers):
    cache = db.info.setdefault('market_objects', {})
    missing = {value for value in identifiers if value is not None and (model, value) not in cache}
    if not missing:
        return
    primary = model.__mapper__.primary_key[0]
    for row in db.scalars(select(model).where(primary.in_(missing))):
        ident = getattr(row, primary.key)
        cache[(model, ident)] = row
        missing.discard(ident)
    for ident in missing:
        cache[(model, ident)] = None


def uid():
    return uuid.uuid4().hex


def stamp():
    return int(time.time())


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)


class ProfileInput(Input):
    kind: Literal['merchant', 'freighter', 'both']
    alcaldia: str = Field(min_length=1, max_length=40)
    colonia: str = Field(min_length=2, max_length=100)
    description: str = Field(default='', max_length=1000)
    whatsapp_phone: str | None = Field(default=None, max_length=20)
    published: bool = False
    revision: int | None = Field(default=None, ge=1)

    @field_validator('whatsapp_phone', mode='before')
    @classmethod
    def normalize_whatsapp_phone(cls, value):
        if value is None:
            return None
        value = re.sub(r'[\s().-]', '', str(value).strip())
        if not value:
            return None
        if not re.fullmatch(r'\+[1-9][0-9]{7,14}', value):
            raise ValueError('Usa WhatsApp en formato internacional, por ejemplo +525512345678')
        return value

    @model_validator(mode='after')
    def locality(self):
        if self.alcaldia not in LOCALITY_CODES:
            raise ValueError('Selecciona una de las 16 alcaldías de Ciudad de México')
        return self


class ListingInput(Input):
    merchant_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default='', max_length=1000)
    category: str = Field(default='Otros', min_length=1, max_length=80)
    unit: Literal['piece', 'kg', 'meter', 'service'] = 'piece'
    price_minor: int = Field(ge=1, le=MAX_MINOR)
    wholesale_discount_bps: int = Field(default=0, ge=0, le=9900)
    stock_milli: int = Field(ge=0, le=1_000_000_000_000)
    published: bool = False

    @model_validator(mode='after')
    def integral_stock(self):
        if self.unit in ('piece', 'service') and self.stock_milli % 1000:
            raise ValueError('Piezas y servicios requieren cantidades enteras')
        return self


class ListingPatch(Input):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    unit: Literal['piece', 'kg', 'meter', 'service'] | None = None
    price_minor: int | None = Field(default=None, ge=1, le=MAX_MINOR)
    wholesale_discount_bps: int | None = Field(default=None, ge=0, le=9900)
    stock_milli: int | None = Field(default=None, ge=0, le=1_000_000_000_000)
    published: bool | None = None
    revision: int | None = Field(default=None, ge=1)


class ListingImageInput(Input):
    mime_type: Literal['image/jpeg', 'image/png', 'image/webp']
    data_base64: str = Field(min_length=4, max_length=2_000_000)


class CartItemInput(Input):
    buyer_merchant_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    listing_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    quantity_milli: int = Field(ge=1, le=MAX_QUANTITY)


class CartCheckoutInput(Input):
    buyer_merchant_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    address_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    request_key: str = Field(pattern=r'^[0-9a-f]{32}$')


class DeliveryAddressInput(Input):
    merchant_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    label: str = Field(min_length=2, max_length=80)
    recipient: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=9, max_length=16)
    street: str = Field(min_length=2, max_length=160)
    exterior_number: str = Field(min_length=1, max_length=20)
    interior_number: str = Field(default='', max_length=20)
    colonia: str = Field(min_length=2, max_length=100)
    alcaldia: str = Field(min_length=1, max_length=40)
    postal_code: str = Field(pattern=r'^[0-9]{5}$')
    reference_notes: str = Field(default='', max_length=240)

    @field_validator('phone', mode='before')
    @classmethod
    def normalize_delivery_phone(cls, value):
        digits = re.sub(r'[^0-9+]', '', str(value))
        if not re.fullmatch(r'\+?[1-9][0-9]{7,14}', digits):
            raise ValueError('Usa un teléfono con código de país, por ejemplo +525512345678')
        return digits if digits.startswith('+') else '+' + digits

    @field_validator('alcaldia')
    @classmethod
    def validate_delivery_alcaldia(cls, value):
        if value not in LOCALITY_CODES:
            raise ValueError('Selecciona una de las 16 alcaldías de Ciudad de México')
        return value


class PurchaseInput(Input):
    listing_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    buyer_merchant_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    quantity_milli: int = Field(ge=1, le=MAX_QUANTITY)
    request_key: str = Field(pattern=r'^[0-9a-f]{32}$')
    notes: str = Field(default='', max_length=1000)


class QuoteInput(Input):
    listing_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    buyer_merchant_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    quantity_milli: int = Field(ge=1, le=MAX_QUANTITY)
    message: str = Field(default='', max_length=1000)


class QuoteResponse(Input):
    unit_price_minor: int = Field(ge=1, le=MAX_MINOR)
    delivery_fee_minor: int = Field(default=0, ge=0, le=MAX_MINOR)
    message: str = Field(default='', max_length=1000)


class QuoteAccept(Input):
    request_key: str = Field(pattern=r'^[0-9a-f]{32}$')


class OrderTransition(Input):
    action: Literal['accept', 'reject', 'prepare', 'ship', 'receive', 'cancel']


class FreightInput(Input):
    order_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    carrier_merchant_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    fee_minor: int = Field(default=0, ge=0, le=MAX_MINOR)
    notes: str = Field(default='', max_length=1000)


class FreightTransition(Input):
    action: Literal['accept', 'deliver']


class OrderQRScanInput(Input):
    order_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    kind: Literal['PAYMENT', 'BANK_CREDIT', 'TRANSIT', 'RECEIPT']
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


def amount(price, quantity, delivery=0):
    value = (price * quantity + 500) // 1000 + delivery
    if not 1 <= value <= MAX_MINOR:
        raise HTTPException(422, 'El total debe ser mayor que cero y no superar $1,000,000 MXN')
    return value


def platform_fee(base_minor):
    """5% rounded half-up to the nearest centavo."""
    if base_minor <= 0:
        return 0
    return (base_minor * PLATFORM_FEE_BPS + 5000) // 10000


def priced_with_fee(base_minor, *, label='El importe'):
    fee = platform_fee(base_minor)
    gross = base_minor + fee
    if gross > MAX_MINOR:
        raise HTTPException(422, f'{label} supera el límite de $1,000,000 MXN al añadir el recargo del 5%')
    return gross, fee


def new_product_qr_sha256(merchant_id, listing_id):
    material = (b'rio.market.product-qr.v1|' + merchant_id.encode('ascii') + b'|'
                + listing_id.encode('ascii') + b'|' + secrets.token_bytes(32))
    return hashlib.sha256(material).hexdigest()


def quantity_allowed(listing, quantity):
    if listing.unit in ('piece', 'service') and quantity % 1000:
        raise HTTPException(422, 'Piezas y servicios requieren cantidades enteras')


def revision_matches(row, wanted):
    if wanted is not None and wanted != row.revision:
        raise HTTPException(409, 'El registro cambió. Actualiza antes de guardar')


def touch(row):
    row.revision += 1
    row.updated_at = stamp()


class ProductionMarket:
    def __init__(self, accounts, public_url=''):
        self.accounts = accounts
        self.Session = accounts.Session
        self.public_url = public_url.rstrip('/')

    @contextmanager
    def write(self, principal):
        try:
            with self.Session.begin() as db:
                if db.bind.dialect.name == 'sqlite':
                    db.execute(text('BEGIN IMMEDIATE'))
                self.accounts._session_access(db, principal, lock=True)
                yield db
        except IntegrityError:
            raise HTTPException(409, 'El registro ya existe o cambió. Actualiza y revisa antes de reintentar') from None
        except (OperationalError, ProgrammingError):
            raise HTTPException(503, 'El servicio comercial no está disponible. No se confirmó el cambio') from None

    def authorize(self, db, principal, merchant_id, *, write=False):
        return self.accounts._member_role(db, principal['id'], merchant_id,
            WRITE_ROLES if write else None, lock=write)

    @staticmethod
    def actor_can_manage(db, principal, merchant_id):
        role = db.scalar(select(Membership.role).where(
            Membership.user_id == principal['id'], Membership.merchant_id == merchant_id))
        return role in WRITE_ROLES

    @staticmethod
    def append_order_event(db, order, event_type, stage, source, actor_user_id=None):
        db.add(MarketOrderEvent(id=uid(), order_id=order.id, actor_user_id=actor_user_id,
            event_type=event_type, stage=stage, source=source, created_at=stamp()))

    def ensure_order_qr(self, db, order, kind):
        row = db.scalar(select(MarketOrderQR).where(
            MarketOrderQR.order_id == order.id, MarketOrderQR.kind == kind))
        if row is None:
            row = MarketOrderQR(id=uid(), order_id=order.id, kind=kind,
                sha256=hashlib.sha256(secrets.token_bytes(32)).hexdigest(), created_at=stamp())
            db.add(row)
            db.flush()
        return row

    def order_qr_url(self, row):
        return '/v1/market/orders/' + row.order_id + '/qr/' + row.kind.lower() + '.png?sha256=' + row.sha256

    @staticmethod
    def profile_view(db, row):
        merchant = cached(db, Merchant, row.merchant_id)
        return {'merchant_id': row.merchant_id, 'name': merchant.name,
            'kind': row.kind, 'city': 'Ciudad de México', 'state_code': 'CMX',
            'alcaldia': row.alcaldia, 'colonia': row.colonia, 'description': row.description,
            'whatsapp_phone': row.whatsapp_phone,
            'published': row.published, 'revision': row.revision,
            'created_at': row.created_at, 'updated_at': row.updated_at}

    def require_profile(self, db, merchant_id, *, seller=False, carrier=False):
        row = db.get(MarketProfile, merchant_id)
        if row is None:
            raise HTTPException(409, 'Completa la alcaldía y colonia del negocio en Ciudad de México')
        if seller and (not row.published or row.kind not in ('merchant', 'both')):
            raise HTTPException(409, 'El vendedor debe publicar su perfil comercial')
        if carrier and (not row.published or row.kind not in ('freighter', 'both')):
            raise HTTPException(409, 'Selecciona un fletero con perfil publicado en Ciudad de México')
        return row

    @staticmethod
    def listing_view(db, row, *, include_seller_financials=False):
        profile = cached(db, MarketProfile, row.merchant_id)
        merchant = cached(db, Merchant, row.merchant_id)
        result = {'id': row.id, 'merchant_id': row.merchant_id, 'merchant_name': merchant.name,
            'name': row.name, 'description': row.description, 'category': row.category,
            'unit': row.unit, 'price_minor': row.price_minor,
            'regular_price_minor': row.seller_price_minor + platform_fee(row.seller_price_minor),
            'wholesale_discount_bps': row.wholesale_discount_bps,
            'stock_milli': row.stock_milli,
            'image_url': ('/v1/market/listings/' + row.id + '/image?sha256=' + row.image_sha256
                if row.image_sha256 else None),
            'qr_sha256': row.qr_sha256 if row.published else None,
            'qr_url': ('/v1/market/listings/' + row.id + '/qr.png?sha256=' + row.qr_sha256
                if row.published and row.qr_sha256 else None),
            'published': row.published, 'city': 'Ciudad de México',
            'alcaldia': profile.alcaldia if profile else None,
            'colonia': profile.colonia if profile else None,
            'whatsapp_phone': profile.whatsapp_phone if profile and profile.published else None,
            'revision': row.revision, 'created_at': row.created_at, 'updated_at': row.updated_at}
        if include_seller_financials:
            result.update({'seller_price_minor': row.seller_price_minor,
                'discounted_seller_price_minor': row.discounted_seller_price_minor,
                'platform_fee_minor': row.platform_fee_minor, 'platform_fee_bps': PLATFORM_FEE_BPS})
        return result

    @staticmethod
    def scoped_names(db, row):
        result = {}
        for side in ('buyer', 'seller'):
            mid = getattr(row, side + '_merchant_id')
            merchant = cached(db, Merchant, mid)
            profile = cached(db, MarketProfile, mid)
            result[side + '_name'] = merchant.name
            result[side + '_alcaldia'] = profile.alcaldia if profile else None
            result[side + '_whatsapp_phone'] = (profile.whatsapp_phone
                if profile and profile.published else None)
        return result

    def quote_view(self, db, row, *, include_seller_financials=False):
        keys = ('id', 'buyer_merchant_id', 'seller_merchant_id', 'listing_id', 'listing_name',
                'unit', 'quantity_milli', 'unit_price_minor', 'delivery_fee_minor', 'total_minor',
                'message', 'seller_message', 'status', 'order_id', 'created_at', 'updated_at', 'revision')
        result = {**{key: getattr(row, key) for key in keys}, **self.scoped_names(db, row)}
        if include_seller_financials:
            result.update({'seller_unit_price_minor': row.seller_unit_price_minor,
                'platform_fee_minor': row.platform_fee_minor,
                'seller_delivery_fee_minor': row.seller_delivery_fee_minor,
                'freight_platform_fee_minor': row.freight_platform_fee_minor,
                'platform_fee_bps': PLATFORM_FEE_BPS})
        return result

    def order_view(self, db, row, *, include_seller_financials=False):
        keys = ('id', 'buyer_merchant_id', 'seller_merchant_id', 'listing_id', 'quote_id', 'listing_name',
                'unit', 'quantity_milli', 'unit_price_minor', 'delivery_fee_minor', 'total_minor',
                'notes', 'status', 'created_at', 'updated_at', 'revision')
        freight = (db.info['market_freight_orders'].get(row.id) if 'market_freight_orders' in db.info else
            db.scalar(select(MarketFreight).where(MarketFreight.order_id == row.id)))
        payment_order = 'market-' + row.id
        intent = (db.info['market_payment_intents'].get((row.seller_merchant_id, payment_order))
            if 'market_payment_intents' in db.info else db.scalar(select(Intent).where(
                Intent.merchant_id == row.seller_merchant_id, Intent.order_id == payment_order)))
        if intent is not None and intent.amount_minor != row.total_minor:
            intent = None
        receipt = cached(db, PaymentReceipt, intent.id) if intent else None
        confirmed = bool(eligible(intent) and receipt and receipt.issued_at is not None)
        payment = {'status': 'PEY_CONFIRMED' if confirmed else 'UNVERIFIED',
            'label': 'Pago confirmado por pey' if confirmed else 'Sin pago confirmado',
            'bank_payment_confirmed': False}
        if confirmed:
            payment['confirmed_at'] = receipt.issued_at
        if 'market_order_qrs' in db.info:
            qr_rows = db.info['market_order_qrs'].get(row.id, [])
        else:
            qr_rows = list(db.scalars(select(MarketOrderQR).where(MarketOrderQR.order_id == row.id)))
        qr_by_kind = {qr.kind: qr for qr in qr_rows}
        events = (db.info['market_order_events'].get(row.id, []) if 'market_order_events' in db.info else
            list(db.scalars(select(MarketOrderEvent).where(MarketOrderEvent.order_id == row.id)
                .order_by(MarketOrderEvent.created_at, MarketOrderEvent.id))))
        bank_confirmed = any(event.event_type == 'BANK_CREDIT_CONFIRMED' and event.source == 'BANK' for event in events)
        if 'market_order_items' in db.info:
            item_rows = db.info['market_order_items'].get(row.id, [])
        else:
            item_rows = list(db.scalars(select(MarketOrderItem).where(MarketOrderItem.order_id == row.id)
                .order_by(MarketOrderItem.created_at, MarketOrderItem.id)))
        items = [{'listing_id': item.listing_id, 'listing_name': item.listing_name, 'unit': item.unit,
            'quantity_milli': item.quantity_milli, 'unit_price_minor': item.unit_price_minor,
            'product_qr_sha256': item.product_qr_sha256,
            'total_minor': item.total_minor} for item in item_rows]
        workflow_qrs = {}
        for kind, qr in qr_by_kind.items():
            workflow_qrs[kind.lower()] = {'sha256': qr.sha256, 'image_url': self.order_qr_url(qr),
                'created_at': qr.created_at,
                'purpose': 'UNIFIED_ORDER_TRACKING' if kind == 'PAYMENT' and row.cart_checkout_key else 'STAGE_STATUS'}
        try:
            delivery_address = json.loads(row.delivery_address_json) if row.delivery_address_json else None
        except (ValueError, TypeError):
            delivery_address = None
        progress = {'stage': events[-1].stage if events else 'WAITING_SELLER',
            'history': [{'event_type': event.event_type, 'stage': event.stage, 'source': event.source,
                'created_at': event.created_at} for event in events],
            'bank_credit_status': 'CONFIRMED' if bank_confirmed else 'PENDING_BANK_INTEGRATION',
            'qr': workflow_qrs}
        unified_qr = None
        if row.cart_checkout_key and 'payment' in workflow_qrs:
            unified_qr = {'sha256': workflow_qrs['payment']['sha256'],
                'image_url': workflow_qrs['payment']['image_url'], 'purpose': 'UNIFIED_ORDER_TRACKING',
                'item_count': len(items),
                'product_qr_sha256': [item['product_qr_sha256'] for item in items if item['product_qr_sha256']]}
        result = {**{key: getattr(row, key) for key in keys}, **self.scoped_names(db, row),
            'freight_id': freight.id if freight else None, 'payment': payment,
            'checkout_order_id': payment_order, 'items': items,
            'delivery_address': delivery_address, 'progress': progress, 'unified_qr': unified_qr}
        if include_seller_financials:
            result.update({'seller_unit_price_minor': row.seller_unit_price_minor,
                'platform_fee_minor': row.platform_fee_minor,
                'seller_delivery_fee_minor': row.seller_delivery_fee_minor,
                'freight_platform_fee_minor': row.freight_platform_fee_minor,
                'platform_fee_bps': PLATFORM_FEE_BPS})
        return result

    def freight_view(self, db, row, *, include_seller_financials=False):
        order = cached(db, MarketOrder, row.order_id)
        carrier = cached(db, Merchant, row.carrier_merchant_id)
        profile = cached(db, MarketProfile, row.carrier_merchant_id)
        keys = ('id', 'order_id', 'carrier_merchant_id', 'fee_minor', 'notes', 'status',
                'created_at', 'updated_at', 'revision')
        result = {**{key: getattr(row, key) for key in keys}, **self.scoped_names(db, order),
            'buyer_merchant_id': order.buyer_merchant_id, 'seller_merchant_id': order.seller_merchant_id,
            'carrier_name': carrier.name, 'alcaldia': profile.alcaldia if profile else None,
            'carrier_whatsapp_phone': profile.whatsapp_phone if profile and profile.published else None,
            'fulfillment_source': 'AUTHORIZED_CARRIER_DECLARATION'}
        if include_seller_financials:
            result.update({'seller_delivery_fee_minor': order.seller_delivery_fee_minor,
                'freight_platform_fee_minor': order.freight_platform_fee_minor,
                'delivery_fee_minor': order.delivery_fee_minor,
                'platform_fee_bps': PLATFORM_FEE_BPS})
        return result

    @staticmethod
    def ids_for(db, principal):
        return list(db.scalars(select(Membership.merchant_id).where(Membership.user_id == principal['id'])))

    def listing_catalog(self, db, *, alcaldia=None, q='', after='', limit=200):
        query = select(MarketListing).join(MarketProfile, MarketProfile.merchant_id == MarketListing.merchant_id).join(
            Merchant, Merchant.id == MarketListing.merchant_id).where(
            MarketListing.published.is_(True), MarketProfile.published.is_(True),
            MarketProfile.kind.in_(('merchant', 'both')))
        if alcaldia:
            if alcaldia not in LOCALITY_CODES:
                raise HTTPException(422, 'Selecciona una alcaldía de Ciudad de México')
            query = query.where(MarketProfile.alcaldia == alcaldia)
        if q:
            escaped = q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            query = query.where(or_(MarketListing.name.ilike('%' + escaped + '%', escape='\\'),
                MarketListing.description.ilike('%' + escaped + '%', escape='\\'),
                MarketListing.category.ilike('%' + escaped + '%', escape='\\'),
                Merchant.name.ilike('%' + escaped + '%', escape='\\')))
        if after:
            query = query.where(MarketListing.id > after)
        rows = list(db.scalars(query.order_by(MarketListing.id).limit(limit + 1)))
        prime(db, MarketProfile, [row.merchant_id for row in rows[:limit]])
        prime(db, Merchant, [row.merchant_id for row in rows[:limit]])
        return {'listings': [self.listing_view(db, row) for row in rows[:limit]],
            'next_cursor': rows[limit - 1].id if len(rows) > limit else None}

    def bootstrap(self, principal, alcaldia=None, q=''):
        try:
            with self.Session() as db:
                owned = db.execute(select(Merchant, Membership.role).join(Membership,
                    Membership.merchant_id == Merchant.id).where(Membership.user_id == principal['id'])).all()
                ids = [merchant.id for merchant, _ in owned]
                role_by_id = {merchant.id: role for merchant, role in owned}
                profiles = list(db.scalars(select(MarketProfile).where(MarketProfile.published.is_(True)).order_by(MarketProfile.merchant_id)))
                if alcaldia:
                    if alcaldia not in LOCALITY_CODES:
                        raise HTTPException(422, 'Selecciona una alcaldía de Ciudad de México')
                    profiles = [row for row in profiles if row.alcaldia == alcaldia]
                quotes = list(db.scalars(select(MarketQuote).where(or_(MarketQuote.buyer_merchant_id.in_(ids), MarketQuote.seller_merchant_id.in_(ids))).order_by(MarketQuote.created_at.desc(), MarketQuote.id.desc()).limit(501)))
                orders = list(db.scalars(select(MarketOrder).where(or_(MarketOrder.buyer_merchant_id.in_(ids), MarketOrder.seller_merchant_id.in_(ids))).order_by(MarketOrder.created_at.desc(), MarketOrder.id.desc()).limit(501)))
                own_order_ids = [row.id for row in orders]
                freights = list(db.scalars(select(MarketFreight).where(or_(MarketFreight.order_id.in_(own_order_ids), MarketFreight.carrier_merchant_id.in_(ids))).order_by(MarketFreight.created_at.desc(), MarketFreight.id.desc()).limit(501)))
                truncated = {'quotes': len(quotes) > 500, 'orders': len(orders) > 500, 'freights': len(freights) > 500}
                quotes, orders, freights = quotes[:500], orders[:500], freights[:500]
                prime(db, MarketOrder, [row.order_id for row in freights])
                freight_orders = [cached(db, MarketOrder, row.order_id) for row in freights]
                parties = {merchant.id for merchant, _ in owned}
                parties.update(row.merchant_id for row in profiles)
                parties.update(row.carrier_merchant_id for row in freights)
                for row in [*quotes, *orders, *freight_orders]:
                    parties.update((row.buyer_merchant_id, row.seller_merchant_id))
                prime(db, Merchant, parties)
                prime(db, MarketProfile, parties)
                order_ids = [row.id for row in orders]
                db.info['market_freight_orders'] = {row.order_id: row for row in db.scalars(
                    select(MarketFreight).where(MarketFreight.order_id.in_(order_ids)))}
                intents = list(db.scalars(select(Intent).where(
                    Intent.order_id.in_(['market-' + ident for ident in order_ids]),
                    Intent.merchant_id.in_({row.seller_merchant_id for row in orders}))))
                db.info['market_payment_intents'] = {(row.merchant_id, row.order_id): row for row in intents}
                prime(db, PaymentReceipt, [row.id for row in intents])
                db.info['market_order_events'] = {}
                db.info['market_order_qrs'] = {}
                db.info['market_order_items'] = {}
                if order_ids:
                    for event in db.scalars(select(MarketOrderEvent).where(
                            MarketOrderEvent.order_id.in_(order_ids)).order_by(
                                MarketOrderEvent.created_at, MarketOrderEvent.id)):
                        db.info['market_order_events'].setdefault(event.order_id, []).append(event)
                    for qr in db.scalars(select(MarketOrderQR).where(MarketOrderQR.order_id.in_(order_ids))):
                        db.info['market_order_qrs'].setdefault(qr.order_id, []).append(qr)
                    for item in db.scalars(select(MarketOrderItem).where(MarketOrderItem.order_id.in_(order_ids))):
                        db.info['market_order_items'].setdefault(item.order_id, []).append(item)
                catalog = self.listing_catalog(db, alcaldia=alcaldia, q=q)
                return {'city': 'Ciudad de México', 'localities': [{'code': code, 'name': name} for code, name in LOCALITIES],
                    'my_businesses': [{'id': merchant.id, 'name': merchant.name, 'role': role,
                        'profile': self.profile_view(db, profile) if (profile := db.get(MarketProfile, merchant.id)) else None}
                        for merchant, role in owned],
                    'profiles': [self.profile_view(db, row) for row in profiles],
                    **catalog, 'my_listings': [self.listing_view(db, row,
                        include_seller_financials=role_by_id.get(row.merchant_id) in WRITE_ROLES)
                        for row in db.scalars(select(MarketListing).where(MarketListing.merchant_id.in_(ids)).order_by(MarketListing.created_at.desc()))],
                    'quotes': [self.quote_view(db, row,
                        include_seller_financials=role_by_id.get(row.seller_merchant_id) in WRITE_ROLES)
                        for row in quotes],
                    'orders': [self.order_view(db, row,
                        include_seller_financials=role_by_id.get(row.seller_merchant_id) in WRITE_ROLES)
                        for row in orders],
                    'freights': [self.freight_view(db, row,
                        include_seller_financials=role_by_id.get(
                            cached(db, MarketOrder, row.order_id).seller_merchant_id) in WRITE_ROLES)
                        for row in freights],
                    'source': 'DATABASE', 'payments_read_only': True,
                    'history_truncated': any(truncated.values()), 'truncated_collections': truncated, 'history_limit': 500}
        except (OperationalError, ProgrammingError):
            raise HTTPException(503, 'El servicio comercial no está disponible') from None

    def save_profile(self, principal, merchant_id, payload):
        with self.write(principal) as db:
            self.authorize(db, principal, merchant_id, write=True)
            row = db.get(MarketProfile, merchant_id, with_for_update=True)
            if row is None:
                row = MarketProfile(merchant_id=merchant_id, revision=1, created_at=stamp(), updated_at=stamp())
                db.add(row)
            else:
                revision_matches(row, payload.revision)
                touch(row)
            for key, value in payload.model_dump(exclude={'revision'}).items():
                setattr(row, key, value)
            db.flush()
            return self.profile_view(db, row)

    def create_listing(self, principal, payload):
        with self.write(principal) as db:
            self.authorize(db, principal, payload.merchant_id, write=True)
            self.require_profile(db, payload.merchant_id, seller=payload.published)
            listing_id = uid()
            seller_price = payload.price_minor
            discount_bps = payload.wholesale_discount_bps
            discounted_seller = (seller_price * (10000 - discount_bps) + 5000) // 10000
            buyer_price, fee = priced_with_fee(discounted_seller, label='El precio') if payload.published else (seller_price, 0)
            row = MarketListing(id=listing_id, merchant_id=payload.merchant_id,
                name=payload.name, description=payload.description, category=payload.category,
                unit=payload.unit, price_minor=buyer_price, seller_price_minor=seller_price,
                platform_fee_minor=fee, wholesale_discount_bps=discount_bps,
                discounted_seller_price_minor=discounted_seller,
                stock_milli=payload.stock_milli, published=payload.published,
                qr_sha256=new_product_qr_sha256(payload.merchant_id, listing_id) if payload.published else None,
                revision=1, created_at=stamp(), updated_at=stamp())
            db.add(row)
            db.flush()
            return self.listing_view(db, row, include_seller_financials=True)

    def update_listing(self, principal, listing_id, payload):
        with self.write(principal) as db:
            row = db.get(MarketListing, listing_id, with_for_update=True)
            if row is None:
                raise HTTPException(404, 'Producto no encontrado')
            self.authorize(db, principal, row.merchant_id, write=True)
            revision_matches(row, payload.revision)
            values = payload.model_dump(exclude_unset=True, exclude={'revision'})
            if any(value is None for value in values.values()):
                raise HTTPException(422, 'Los campos no pueden ser nulos')
            if not values:
                raise HTTPException(422, 'Indica un campo para actualizar')
            unit, stock = values.get('unit', row.unit), values.get('stock_milli', row.stock_milli)
            if unit != row.unit:
                raise HTTPException(409, 'Crea otro producto para utilizar una unidad diferente')
            if unit in ('piece', 'service') and stock % 1000:
                raise HTTPException(422, 'Piezas y servicios requieren existencias enteras')
            self.require_profile(db, row.merchant_id, seller=values.get('published', row.published))
            base_price = values.get('price_minor', row.seller_price_minor or row.price_minor)
            discount_bps = values.get('wholesale_discount_bps', row.wholesale_discount_bps)
            published = values.get('published', row.published)
            was_published = row.published
            discounted_seller = (base_price * (10000 - discount_bps) + 5000) // 10000
            buyer_price, fee = priced_with_fee(discounted_seller, label='El precio') if published else (base_price, 0)
            for key, value in values.items():
                if key not in ('price_minor', 'published', 'wholesale_discount_bps'):
                    setattr(row, key, value)
            row.seller_price_minor = base_price
            row.wholesale_discount_bps = discount_bps
            row.discounted_seller_price_minor = discounted_seller
            row.price_minor = buyer_price
            row.platform_fee_minor = fee
            row.published = published
            if published and (not row.qr_sha256 or not was_published):
                row.qr_sha256 = new_product_qr_sha256(row.merchant_id, row.id)
            elif not published:
                row.qr_sha256 = None
            touch(row)
            db.flush()
            return self.listing_view(db, row, include_seller_financials=True)

    def set_listing_image(self, principal, listing_id, payload):
        try:
            content = base64.b64decode(payload.data_base64, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(422, 'La imagen no tiene una codificación válida') from None
        if not content or len(content) > MAX_LISTING_IMAGE_BYTES:
            raise HTTPException(413, 'La imagen debe pesar 1.5 MB o menos')
        signatures = {
            'image/jpeg': content.startswith(b'\xff\xd8\xff'),
            'image/png': content.startswith(b'\x89PNG\r\n\x1a\n'),
            'image/webp': len(content) >= 12 and content.startswith(b'RIFF') and content[8:12] == b'WEBP',
        }
        if not signatures[payload.mime_type]:
            raise HTTPException(422, 'El contenido de la imagen no coincide con su formato')
        with self.write(principal) as db:
            row = db.get(MarketListing, listing_id, with_for_update=True)
            if row is None:
                raise HTTPException(404, 'Producto no encontrado')
            self.authorize(db, principal, row.merchant_id, write=True)
            row.image_data = content
            row.image_mime = payload.mime_type
            row.image_sha256 = hashlib.sha256(content).hexdigest()
            touch(row)
            db.flush()
            return self.listing_view(db, row, include_seller_financials=True)

    def get_listing_image(self, principal, listing_id, image_sha256):
        with self.Session() as db:
            row = db.get(MarketListing, listing_id)
            if row is None or not row.image_data or not row.image_mime or not row.image_sha256:
                raise HTTPException(404, 'Imagen no disponible')
            publicly_visible = row.published and row.qr_sha256 is not None
            profile = db.get(MarketProfile, row.merchant_id)
            publicly_visible = publicly_visible and profile is not None and profile.published and profile.kind in ('merchant', 'both')
            if not publicly_visible:
                self.authorize(db, principal, row.merchant_id)
            if not hmac.compare_digest(row.image_sha256, image_sha256):
                raise HTTPException(404, 'Imagen no disponible')
            return row.image_data, row.image_mime, row.image_sha256

    def verified_public_listing(self, principal, listing_id, qr_sha256):
        with self.Session() as db:
            row = db.get(MarketListing, listing_id)
            if row is None or not row.published or not row.qr_sha256:
                raise HTTPException(404, 'Oferta no disponible')
            profile = db.get(MarketProfile, row.merchant_id)
            if profile is None or not profile.published or profile.kind not in ('merchant', 'both'):
                raise HTTPException(404, 'Oferta no disponible')
            if not hmac.compare_digest(row.qr_sha256, qr_sha256):
                raise HTTPException(404, 'El QR no coincide con una oferta vigente')
            prime(db, MarketProfile, [row.merchant_id])
            prime(db, Merchant, [row.merchant_id])
            return self.listing_view(db, row)

    def listing_qr_png(self, principal, listing_id, qr_sha256):
        self.verified_public_listing(principal, listing_id, qr_sha256)
        if not self.public_url:
            raise HTTPException(503, 'El dominio público de Mercado Abierto no está configurado')
        target = (self.public_url + '/mercado-abierto?producto=' + listing_id
                  + '&sha256=' + qr_sha256)
        return qr_png(target)

    @staticmethod
    def address_view(row):
        return {key: getattr(row, key) for key in ('id', 'merchant_id', 'label', 'recipient', 'phone',
            'street', 'exterior_number', 'interior_number', 'colonia', 'alcaldia', 'postal_code',
            'reference_notes', 'created_at', 'updated_at')}

    def list_addresses(self, principal, merchant_id):
        with self.Session() as db:
            # Delivery addresses contain recipient and phone PII; limit reads to owners/admins.
            self.authorize(db, principal, merchant_id, write=True)
            rows = db.scalars(select(MarketDeliveryAddress).where(
                MarketDeliveryAddress.merchant_id == merchant_id).order_by(
                    MarketDeliveryAddress.created_at.desc(), MarketDeliveryAddress.id))
            return {'addresses': [self.address_view(row) for row in rows]}

    def save_address(self, principal, payload, address_id=None):
        with self.write(principal) as db:
            self.authorize(db, principal, payload.merchant_id, write=True)
            if address_id:
                row = db.get(MarketDeliveryAddress, address_id, with_for_update=True)
                if row is None or row.merchant_id != payload.merchant_id:
                    raise HTTPException(404, 'Dirección no encontrada')
            else:
                row = MarketDeliveryAddress(id=uid(), merchant_id=payload.merchant_id,
                    created_at=stamp(), updated_at=stamp())
                db.add(row)
            for key, value in payload.model_dump(exclude={'merchant_id'}).items():
                setattr(row, key, value)
            row.updated_at = stamp()
            db.flush()
            return self.address_view(row)

    def delete_address(self, principal, merchant_id, address_id):
        with self.write(principal) as db:
            self.authorize(db, principal, merchant_id, write=True)
            row = db.get(MarketDeliveryAddress, address_id, with_for_update=True)
            if row is None or row.merchant_id != merchant_id:
                raise HTTPException(404, 'Dirección no encontrada')
            db.delete(row)
            return {'id': address_id, 'deleted': True, 'past_orders_preserved': True}

    def cart_view(self, db, cart):
        rows = list(db.scalars(select(MarketCartItem).where(
            MarketCartItem.buyer_merchant_id == cart.buyer_merchant_id).order_by(MarketCartItem.created_at)))
        prime(db, MarketListing, [row.listing_id for row in rows])
        items, total = [], 0
        for row in rows:
            listing = cached(db, MarketListing, row.listing_id)
            if listing is None:
                continue
            total += amount(listing.price_minor, row.quantity_milli)
            items.append({'listing': self.listing_view(db, listing), 'quantity_milli': row.quantity_milli,
                'line_total_minor': amount(listing.price_minor, row.quantity_milli)})
        return {'buyer_merchant_id': cart.buyer_merchant_id, 'status': cart.status,
            'revision': cart.revision, 'items': items, 'total_minor': total,
            'last_checkout_key': cart.last_checkout_key,
            'last_order_ids': json.loads(cart.last_order_ids) if cart.last_order_ids else []}

    def get_cart(self, principal, buyer_merchant_id):
        with self.Session() as db:
            self.authorize(db, principal, buyer_merchant_id, write=True)
            cart = db.get(MarketCart, buyer_merchant_id)
            if cart is None:
                return {'buyer_merchant_id': buyer_merchant_id, 'status': 'OPEN', 'revision': 0,
                    'items': [], 'total_minor': 0, 'last_checkout_key': None, 'last_order_ids': []}
            return self.cart_view(db, cart)

    def add_cart_item(self, principal, payload):
        with self.write(principal) as db:
            listing = self.purchase_listing(db, principal, payload.listing_id,
                payload.buyer_merchant_id, payload.quantity_milli)
            cart = db.get(MarketCart, payload.buyer_merchant_id, with_for_update=True)
            if cart is None:
                cart = MarketCart(buyer_merchant_id=payload.buyer_merchant_id, status='OPEN',
                    revision=1, created_at=stamp(), updated_at=stamp())
                db.add(cart)
                db.flush()
            if cart.status == 'CHECKED_OUT':
                cart.status, cart.last_checkout_key, cart.last_order_ids = 'OPEN', None, None
            item = db.get(MarketCartItem, {'buyer_merchant_id': payload.buyer_merchant_id,
                'listing_id': listing.id}, with_for_update=True)
            quantity = payload.quantity_milli + (item.quantity_milli if item else 0)
            if quantity > MAX_QUANTITY or quantity > listing.stock_milli:
                raise HTTPException(409, 'La cantidad del carrito supera las existencias disponibles')
            quantity_allowed(listing, quantity)
            if item:
                item.quantity_milli, item.updated_at = quantity, stamp()
            else:
                db.add(MarketCartItem(buyer_merchant_id=payload.buyer_merchant_id,
                    listing_id=listing.id, quantity_milli=quantity, created_at=stamp(), updated_at=stamp()))
            touch(cart)
            db.flush()
            return self.cart_view(db, cart)

    def remove_cart_item(self, principal, buyer_merchant_id, listing_id):
        with self.write(principal) as db:
            self.authorize(db, principal, buyer_merchant_id, write=True)
            item = db.get(MarketCartItem, {'buyer_merchant_id': buyer_merchant_id,
                'listing_id': listing_id}, with_for_update=True)
            if item is None:
                raise HTTPException(404, 'Producto no encontrado en el carrito')
            db.delete(item)
            cart = db.get(MarketCart, buyer_merchant_id, with_for_update=True)
            if cart:
                touch(cart)
                db.flush()
                return self.cart_view(db, cart)
            return {'buyer_merchant_id': buyer_merchant_id, 'status': 'OPEN', 'items': [], 'total_minor': 0}

    def checkout_cart(self, principal, payload):
        with self.write(principal) as db:
            buyer_id = payload.buyer_merchant_id
            self.authorize(db, principal, buyer_id, write=True)
            cart = db.get(MarketCart, buyer_id, with_for_update=True)
            if cart is None:
                raise HTTPException(409, 'Agrega productos antes de comprar')
            if cart.status == 'CHECKED_OUT' and cart.last_checkout_key == payload.request_key and cart.last_order_ids:
                order_id = json.loads(cart.last_order_ids)[0]
                order = db.get(MarketOrder, order_id)
                if not order or order.buyer_merchant_id != buyer_id:
                    raise HTTPException(409, 'No se pudo recuperar el pedido anterior; consulta tu historial')
                try:
                    old_address = json.loads(order.delivery_address_json or '{}')
                except (ValueError, TypeError):
                    old_address = {}
                if old_address.get('id') != payload.address_id:
                    raise HTTPException(409, 'El folio ya se usó con otra dirección de entrega')
                return {'order': self.order_view(db, order), 'replayed': True}
            address = db.get(MarketDeliveryAddress, payload.address_id)
            if address is None or address.merchant_id != buyer_id:
                raise HTTPException(422, 'Elige una dirección de entrega guardada en este negocio')
            cart_items = list(db.scalars(select(MarketCartItem).where(
                MarketCartItem.buyer_merchant_id == buyer_id).order_by(MarketCartItem.created_at).with_for_update()))
            if not cart_items:
                raise HTTPException(409, 'Agrega productos antes de comprar')
            listings = []
            for item in cart_items:
                listing = db.get(MarketListing, item.listing_id, with_for_update=True)
                if listing is None or not listing.published:
                    raise HTTPException(409, 'Una oferta del carrito ya no está disponible')
                self.require_profile(db, listing.merchant_id, seller=True)
                if item.quantity_milli > listing.stock_milli:
                    raise HTTPException(409, 'Una oferta ya no tiene existencias suficientes')
                quantity_allowed(listing, item.quantity_milli)
                listings.append((item, listing))
            sellers = {listing.merchant_id for _, listing in listings}
            if len(sellers) != 1:
                raise HTTPException(409, 'Para emitir un solo QR CoDi, todos los productos del carrito deben ser del mismo vendedor. Separa la compra por negocio.')
            if buyer_id in sellers:
                raise HTTPException(422, 'Elige un negocio comprador distinto del vendedor')

            line_snapshots, gross_total, seller_total = [], 0, 0
            for item, listing in listings:
                line_gross = amount(listing.price_minor, item.quantity_milli)
                seller_unit = listing.discounted_seller_price_minor or listing.seller_price_minor
                line_seller = (seller_unit * item.quantity_milli + 500) // 1000
                line_fee = line_gross - line_seller
                gross_total += line_gross
                seller_total += line_seller
                line_snapshots.append((item, listing, line_gross, seller_unit, line_fee))
            if gross_total > MAX_MINOR:
                raise HTTPException(422, 'El total del carrito supera $1,000,000 MXN')
            first_listing = listings[0][1]
            request_data = {'cart': buyer_id, 'key': payload.request_key, 'address': address.id,
                'items': [[item.listing_id, item.quantity_milli] for item, _ in listings]}
            digest = hashlib.sha256(json.dumps(request_data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            previous = db.scalar(select(MarketOrder).where(MarketOrder.buyer_merchant_id == buyer_id,
                MarketOrder.request_key == payload.request_key))
            if previous:
                if previous.request_sha256 != digest:
                    raise HTTPException(409, 'El folio ya corresponde a otra compra')
                return {'order': self.order_view(db, previous), 'replayed': True}
            address_snapshot = {'id': address.id, **{key: getattr(address, key) for key in (
                'label', 'recipient', 'phone', 'street', 'exterior_number', 'interior_number',
                'colonia', 'alcaldia', 'postal_code', 'reference_notes')}}
            order = MarketOrder(id=uid(), buyer_merchant_id=buyer_id,
                seller_merchant_id=first_listing.merchant_id, listing_id=first_listing.id,
                quote_id=None, listing_name='Carrito · ' + str(len(listings)) + ' productos',
                unit='service', quantity_milli=1000, unit_price_minor=gross_total,
                seller_unit_price_minor=seller_total, platform_fee_minor=gross_total-seller_total,
                seller_delivery_fee_minor=0, freight_platform_fee_minor=0, delivery_fee_minor=0,
                total_minor=gross_total, notes='', status='REQUESTED', request_key=payload.request_key,
                request_sha256=digest, cart_checkout_key=payload.request_key,
                delivery_address_json=json.dumps(address_snapshot, ensure_ascii=False, sort_keys=True),
                revision=1, created_at=stamp(), updated_at=stamp())
            db.add(order)
            db.flush()
            for item, listing, line_gross, seller_unit, line_fee in line_snapshots:
                db.add(MarketOrderItem(id=uid(), order_id=order.id, listing_id=listing.id,
                    listing_name=listing.name, unit=listing.unit, quantity_milli=item.quantity_milli,
                    unit_price_minor=listing.price_minor, seller_unit_price_minor=seller_unit,
                    platform_fee_minor=line_fee, product_qr_sha256=listing.qr_sha256,
                    total_minor=line_gross, created_at=stamp()))
            self.append_order_event(db, order, 'ORDER_CREATED', 'WAITING_SELLER', 'ACTOR', principal['id'])
            self.ensure_order_qr(db, order, 'PAYMENT')
            for item, _ in listings:
                db.delete(item)
            cart.status, cart.last_checkout_key = 'CHECKED_OUT', payload.request_key
            cart.last_order_ids = json.dumps([order.id])
            touch(cart)
            db.flush()
            return {'order': self.order_view(db, order), 'replayed': False}

    def pey_payment_confirmed(self, intent_id):
        with self.Session.begin() as db:
            intent = db.get(Intent, intent_id)
            if not eligible(intent) or not intent.order_id or not intent.order_id.startswith('market-'):
                return False
            order_id = intent.order_id[7:]
            if not re.fullmatch(r'[0-9a-f]{32}', order_id):
                return False
            order = db.get(MarketOrder, order_id, with_for_update=True)
            if order is None or order.seller_merchant_id != intent.merchant_id or order.total_minor != intent.amount_minor:
                return False
            existing = db.scalar(select(MarketOrderEvent.id).where(MarketOrderEvent.order_id == order.id,
                MarketOrderEvent.event_type == 'PEY_PAYMENT_CONFIRMED'))
            if existing:
                return True
            listing_ids = list(db.scalars(select(MarketOrderItem.listing_id).where(
                MarketOrderItem.order_id == order.id))) or [order.listing_id]
            for listing_id in listing_ids:
                listing = db.get(MarketListing, listing_id, with_for_update=True)
                if listing and listing.published:
                    listing.published = False
                    listing.qr_sha256 = None
                    touch(listing)
            self.append_order_event(db, order, 'PEY_PAYMENT_CONFIRMED',
                'BANK_CREDIT_PENDING', 'PEY')
            self.ensure_order_qr(db, order, 'BANK_CREDIT')
            return True

    def order_qr_image(self, principal, order_id, kind, qr_sha256):
        with self.Session() as db:
            order = db.get(MarketOrder, order_id)
            if order is None:
                raise HTTPException(404, 'Pedido no encontrado')
            ids = self.ids_for(db, principal)
            if order.buyer_merchant_id not in ids and order.seller_merchant_id not in ids:
                raise HTTPException(404, 'Pedido no encontrado')
            qr = db.scalar(select(MarketOrderQR).where(
                MarketOrderQR.order_id == order_id, MarketOrderQR.kind == kind))
            if qr is None or not hmac.compare_digest(qr.sha256, qr_sha256):
                raise HTTPException(404, 'QR de etapa no disponible')
            if not self.public_url:
                raise HTTPException(503, 'El dominio público de Mercado Abierto no está configurado')
            target = (self.public_url + '/mercado-abierto?pedido=' + order_id
                + '&etapa=' + kind.lower() + '&sha256=' + qr.sha256)
            return qr_png(target)

    def scan_order_qr(self, principal, payload):
        with self.write(principal) as db:
            order = db.get(MarketOrder, payload.order_id, with_for_update=True)
            if order is None:
                raise HTTPException(404, 'Pedido no encontrado')
            qr = db.scalar(select(MarketOrderQR).where(
                MarketOrderQR.order_id == order.id, MarketOrderQR.kind == payload.kind))
            if qr is None or not hmac.compare_digest(qr.sha256, payload.sha256):
                raise HTTPException(422, 'El QR no coincide con una etapa válida de este pedido')
            events = list(db.scalars(select(MarketOrderEvent).where(
                MarketOrderEvent.order_id == order.id).order_by(MarketOrderEvent.created_at, MarketOrderEvent.id)))
            bank_confirmed = any(event.event_type == 'BANK_CREDIT_CONFIRMED' and event.source == 'BANK' for event in events)
            ids = self.ids_for(db, principal)
            if payload.kind in ('PAYMENT', 'BANK_CREDIT'):
                if order.buyer_merchant_id not in ids and order.seller_merchant_id not in ids:
                    raise HTTPException(404, 'Pedido no encontrado')
                result = self.order_view(db, order,
                    include_seller_financials=self.actor_can_manage(db, principal, order.seller_merchant_id))
                result['scan_result'] = 'PAYMENT_STATUS' if payload.kind == 'PAYMENT' else 'BANK_CREDIT_STATUS'
                return {'order': result, 'stage_advanced': False}
            if payload.kind == 'TRANSIT':
                freight = db.scalar(select(MarketFreight).where(MarketFreight.order_id == order.id))
                if freight is None or freight.carrier_merchant_id not in ids:
                    raise HTTPException(403, 'Solo el fletero asignado puede confirmar el tránsito')
                self.authorize(db, principal, freight.carrier_merchant_id, write=True)
                if not bank_confirmed:
                    raise HTTPException(409, 'La acreditación bancaria sigue pendiente de una notificación verificada del banco')
                if order.status == 'SHIPPED':
                    return {'order': self.order_view(db, order), 'stage_advanced': False}
                if order.status != 'PREPARED':
                    raise HTTPException(409, 'El pedido todavía no está listo para salir a tránsito')
                order.status = 'SHIPPED'
                touch(order)
                qr.used_at = qr.used_at or stamp()
                self.append_order_event(db, order, 'TRANSIT_QR_SCANNED', 'IN_TRANSIT', 'QR_SCAN', principal['id'])
                self.ensure_order_qr(db, order, 'RECEIPT')
            else:
                self.authorize(db, principal, order.buyer_merchant_id, write=True)
                if not bank_confirmed:
                    raise HTTPException(409, 'La acreditación bancaria sigue pendiente de verificación')
                if order.status == 'RECEIVED':
                    return {'order': self.order_view(db, order), 'stage_advanced': False}
                if order.status != 'SHIPPED':
                    raise HTTPException(409, 'El pedido todavía no está en tránsito')
                order.status = 'RECEIVED'
                touch(order)
                qr.used_at = qr.used_at or stamp()
                self.append_order_event(db, order, 'RECEIPT_QR_SCANNED', 'RECEIVED', 'QR_SCAN', principal['id'])
            db.flush()
            return {'order': self.order_view(db, order,
                include_seller_financials=self.actor_can_manage(db, principal, order.seller_merchant_id)),
                'stage_advanced': True}

    def purchase_listing(self, db, principal, listing_id, buyer_id, quantity):
        self.authorize(db, principal, buyer_id, write=True)
        self.require_profile(db, buyer_id)
        listing = db.get(MarketListing, listing_id)
        if listing is None or not listing.published:
            raise HTTPException(404, 'Oferta no disponible')
        self.require_profile(db, listing.merchant_id, seller=True)
        if buyer_id == listing.merchant_id:
            raise HTTPException(422, 'Elige un negocio comprador distinto del vendedor')
        quantity_allowed(listing, quantity)
        if listing.stock_milli < quantity:
            raise HTTPException(409, 'No hay existencias suficientes')
        return listing

    def create_quote(self, principal, payload):
        with self.write(principal) as db:
            listing = self.purchase_listing(db, principal, payload.listing_id, payload.buyer_merchant_id, payload.quantity_milli)
            row = MarketQuote(id=uid(), buyer_merchant_id=payload.buyer_merchant_id,
                seller_merchant_id=listing.merchant_id, listing_id=listing.id,
                listing_name=listing.name, unit=listing.unit, quantity_milli=payload.quantity_milli,
                unit_price_minor=None, delivery_fee_minor=0, total_minor=None, message=payload.message,
                seller_message='', status='REQUESTED', order_id=None, revision=1,
                created_at=stamp(), updated_at=stamp())
            db.add(row)
            db.flush()
            return self.quote_view(db, row)

    def respond_quote(self, principal, quote_id, payload):
        with self.write(principal) as db:
            row = db.get(MarketQuote, quote_id, with_for_update=True)
            if row is None:
                raise HTTPException(404, 'Cotización no encontrada')
            self.authorize(db, principal, row.seller_merchant_id, write=True)
            if row.status != 'REQUESTED':
                raise HTTPException(409, 'La cotización ya fue respondida o cerrada')
            listing = db.get(MarketListing, row.listing_id)
            discount_bps = listing.wholesale_discount_bps if listing else 0
            discounted_unit = (payload.unit_price_minor * (10000 - discount_bps) + 5000) // 10000
            buyer_unit, product_fee = priced_with_fee(discounted_unit, label='El precio unitario')
            buyer_delivery, freight_fee = priced_with_fee(payload.delivery_fee_minor, label='El flete') if payload.delivery_fee_minor else (0, 0)
            row.seller_unit_price_minor = discounted_unit
            row.platform_fee_minor = product_fee
            row.unit_price_minor = buyer_unit
            row.seller_delivery_fee_minor = payload.delivery_fee_minor
            row.freight_platform_fee_minor = freight_fee
            row.delivery_fee_minor = buyer_delivery
            row.total_minor = amount(buyer_unit, row.quantity_milli, buyer_delivery)
            row.seller_message = payload.message
            row.status = 'QUOTED'
            touch(row)
            db.flush()
            return self.quote_view(db, row, include_seller_financials=True)

    def new_order(self, db, principal, *, listing, buyer_id, quantity, key, notes, quote=None):
        data = {'listing_id': listing.id, 'buyer_id': buyer_id, 'quantity': quantity,
            'notes': notes, 'quote_id': quote.id if quote else None}
        digest = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        previous = db.scalar(select(MarketOrder).where(MarketOrder.buyer_merchant_id == buyer_id,
            MarketOrder.request_key == key))
        if previous:
            if previous.request_sha256 != digest:
                raise HTTPException(409, 'El folio de solicitud ya corresponde a otros datos')
            return previous
        if quote:
            price, delivery = quote.unit_price_minor, quote.delivery_fee_minor
            seller_price = quote.seller_unit_price_minor or price
            product_fee = quote.platform_fee_minor
            seller_delivery = quote.seller_delivery_fee_minor
            freight_fee = quote.freight_platform_fee_minor
        else:
            price, delivery = listing.price_minor, 0
            seller_price = listing.discounted_seller_price_minor or listing.seller_price_minor or price
            product_fee = listing.platform_fee_minor
            seller_delivery, freight_fee = 0, 0
        row = MarketOrder(id=uid(), buyer_merchant_id=buyer_id, seller_merchant_id=listing.merchant_id,
            listing_id=listing.id, quote_id=quote.id if quote else None,
            listing_name=quote.listing_name if quote else listing.name,
            unit=quote.unit if quote else listing.unit, quantity_milli=quantity, unit_price_minor=price,
            seller_unit_price_minor=seller_price, platform_fee_minor=product_fee,
            seller_delivery_fee_minor=seller_delivery, freight_platform_fee_minor=freight_fee,
            delivery_fee_minor=delivery,
            total_minor=amount(price, quantity, delivery), notes=notes, status='REQUESTED',
            request_key=key, request_sha256=digest, revision=1, created_at=stamp(), updated_at=stamp())
        db.add(row)
        db.flush()
        self.append_order_event(db, row, 'ORDER_CREATED', 'WAITING_SELLER', 'ACTOR', principal['id'])
        self.ensure_order_qr(db, row, 'PAYMENT')
        return row

    def create_order(self, principal, payload):
        with self.write(principal) as db:
            # Check an idempotent prior request before mutable stock/publication.
            self.authorize(db, principal, payload.buyer_merchant_id, write=True)
            old = db.scalar(select(MarketOrder).where(MarketOrder.buyer_merchant_id == payload.buyer_merchant_id,
                MarketOrder.request_key == payload.request_key))
            if old:
                digest = hashlib.sha256(json.dumps({'listing_id': payload.listing_id,
                    'buyer_id': payload.buyer_merchant_id, 'quantity': payload.quantity_milli,
                    'notes': payload.notes, 'quote_id': None}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                if old.request_sha256 != digest:
                    raise HTTPException(409, 'El folio de solicitud ya corresponde a otros datos')
                return self.order_view(db, old,
                    include_seller_financials=self.actor_can_manage(db, principal, old.seller_merchant_id))
            listing = self.purchase_listing(db, principal, payload.listing_id, payload.buyer_merchant_id, payload.quantity_milli)
            row = self.new_order(db, principal, listing=listing, buyer_id=payload.buyer_merchant_id,
                quantity=payload.quantity_milli, key=payload.request_key, notes=payload.notes)
            return self.order_view(db, row,
                include_seller_financials=self.actor_can_manage(db, principal, row.seller_merchant_id))

    def accept_quote(self, principal, quote_id, payload):
        with self.write(principal) as db:
            quote = db.get(MarketQuote, quote_id, with_for_update=True)
            if quote is None:
                raise HTTPException(404, 'Cotización no encontrada')
            self.authorize(db, principal, quote.buyer_merchant_id, write=True)
            if quote.status == 'ACCEPTED' and quote.order_id:
                row = db.get(MarketOrder, quote.order_id)
                if row.request_key != payload.request_key:
                    raise HTTPException(409, 'La cotización ya generó un pedido con otro folio')
                return self.order_view(db, row,
                    include_seller_financials=self.actor_can_manage(db, principal, row.seller_merchant_id))
            if quote.status != 'QUOTED':
                raise HTTPException(409, 'La cotización no tiene una oferta disponible')
            listing = self.purchase_listing(db, principal, quote.listing_id, quote.buyer_merchant_id, quote.quantity_milli)
            order = self.new_order(db, principal, listing=listing, buyer_id=quote.buyer_merchant_id,
                quantity=quote.quantity_milli, key=payload.request_key, notes=quote.message, quote=quote)
            quote.order_id, quote.status = order.id, 'ACCEPTED'
            touch(quote)
            db.flush()
            return self.order_view(db, order,
                include_seller_financials=self.actor_can_manage(db, principal, order.seller_merchant_id))

    def get_order(self, principal, order_id):
        with self.Session() as db:
            row = db.get(MarketOrder, order_id)
            if row is None:
                raise HTTPException(404, 'Pedido no encontrado')
            ids = self.ids_for(db, principal)
            if row.buyer_merchant_id not in ids and row.seller_merchant_id not in ids:
                raise HTTPException(404, 'Pedido no encontrado')
            return {'order': self.order_view(db, row,
                include_seller_financials=self.actor_can_manage(db, principal, row.seller_merchant_id))}

    def transition_order(self, principal, order_id, payload):
        with self.write(principal) as db:
            row = db.get(MarketOrder, order_id, with_for_update=True)
            if row is None:
                raise HTTPException(404, 'Pedido no encontrado')
            action = payload.action
            seller_actions = {'accept': ('REQUESTED', 'ACCEPTED'), 'reject': ('REQUESTED', 'REJECTED'),
                'prepare': ('ACCEPTED', 'PREPARED')}
            if action == 'ship':
                self.authorize(db, principal, row.seller_merchant_id, write=True)
                if row.status != 'PREPARED':
                    raise HTTPException(409, 'Prepara el pedido antes de generar el QR de tránsito')
                self.ensure_order_qr(db, row, 'TRANSIT')
                self.append_order_event(db, row, 'TRANSIT_QR_ISSUED', 'WAITING_TRANSIT_SCAN', 'ACTOR', principal['id'])
                touch(row)
                db.flush()
                return self.order_view(db, row, include_seller_financials=True)
            if action in seller_actions:
                self.authorize(db, principal, row.seller_merchant_id, write=True)
                old, new = seller_actions[action]
                if row.status == new:
                    return self.order_view(db, row,
                        include_seller_financials=self.actor_can_manage(db, principal, row.seller_merchant_id))
                if row.status != old:
                    raise HTTPException(409, 'La acción no corresponde al estado actual del pedido')
                if action == 'accept':
                    order_items = list(db.scalars(select(MarketOrderItem).where(
                        MarketOrderItem.order_id == row.id).with_for_update()))
                    if order_items:
                        listings = []
                        for item in order_items:
                            listing = db.get(MarketListing, item.listing_id, with_for_update=True)
                            if listing is None or listing.unit != item.unit or listing.stock_milli < item.quantity_milli:
                                raise HTTPException(409, 'Las existencias cambiaron; no se confirmó el pedido')
                            listings.append((listing, item.quantity_milli))
                        for listing, quantity in listings:
                            listing.stock_milli -= quantity
                            touch(listing)
                    else:
                        listing = db.get(MarketListing, row.listing_id, with_for_update=True)
                        if listing.unit != row.unit:
                            raise HTTPException(409, 'La unidad del producto cambió; revisa el pedido antes de confirmarlo')
                        if listing.stock_milli < row.quantity_milli:
                            raise HTTPException(409, 'Las existencias cambiaron; no se confirmó el pedido')
                        listing.stock_milli -= row.quantity_milli
                        touch(listing)
                if action == 'prepare':
                    intent = db.scalar(select(Intent).where(Intent.merchant_id == row.seller_merchant_id,
                        Intent.order_id == 'market-' + row.id))
                    if not eligible(intent) or intent.amount_minor != row.total_minor:
                        raise HTTPException(409, 'El pedido debe tener un pago confirmado por pey antes de prepararlo')
                    self.ensure_order_qr(db, row, 'TRANSIT')
                row.status = new
                self.append_order_event(db, row, action.upper(), new, 'ACTOR', principal['id'])
            elif action == 'receive':
                raise HTTPException(409, 'Confirma la recepción escaneando el QR de recepción del pedido')
            else:
                self.authorize(db, principal, row.buyer_merchant_id, write=True)
                if row.status == 'CANCELLED':
                    return self.order_view(db, row,
                        include_seller_financials=self.actor_can_manage(db, principal, row.seller_merchant_id))
                if row.status != 'REQUESTED':
                    raise HTTPException(409, 'Contacta al vendedor para cancelar un pedido ya confirmado')
                row.status = 'CANCELLED'
                self.append_order_event(db, row, 'CANCELLED', 'CANCELLED', 'ACTOR', principal['id'])
            touch(row)
            db.flush()
            return self.order_view(db, row,
                include_seller_financials=self.actor_can_manage(db, principal, row.seller_merchant_id))

    def create_freight(self, principal, payload):
        with self.write(principal) as db:
            order = db.get(MarketOrder, payload.order_id, with_for_update=True)
            if order is None:
                raise HTTPException(404, 'Pedido no encontrado')
            self.authorize(db, principal, order.seller_merchant_id, write=True)
            if order.status not in ('ACCEPTED', 'PREPARED'):
                raise HTTPException(409, 'Confirma el pedido antes de asignar su flete')
            self.require_profile(db, payload.carrier_merchant_id, carrier=True)
            previous = db.scalar(select(MarketFreight).where(MarketFreight.order_id == order.id))
            if previous:
                if (previous.carrier_merchant_id, previous.fee_minor, previous.notes) != (payload.carrier_merchant_id, payload.fee_minor, payload.notes):
                    raise HTTPException(409, 'Este pedido ya tiene otro flete asignado')
                return self.freight_view(db, previous, include_seller_financials=True)
            buyer_delivery, freight_fee = priced_with_fee(payload.fee_minor, label='El costo del flete') if payload.fee_minor else (0, 0)
            buyer_total = amount(order.unit_price_minor, order.quantity_milli, buyer_delivery)
            if (buyer_delivery, freight_fee, buyer_total) != (
                    order.delivery_fee_minor, order.freight_platform_fee_minor, order.total_minor):
                existing_intent = db.scalar(select(Intent).where(
                    Intent.merchant_id == order.seller_merchant_id,
                    Intent.order_id == 'market-' + order.id))
                if existing_intent is not None:
                    raise HTTPException(409, 'Ya se preparó un cobro para este pedido. No cambies el flete después de generar el QR CoDi')
                order.seller_delivery_fee_minor = payload.fee_minor
                order.freight_platform_fee_minor = freight_fee
                order.delivery_fee_minor = buyer_delivery
                order.total_minor = buyer_total
                touch(order)
            row = MarketFreight(id=uid(), order_id=order.id, carrier_merchant_id=payload.carrier_merchant_id,
                fee_minor=payload.fee_minor, notes=payload.notes, status='PROPOSED', revision=1,
                created_at=stamp(), updated_at=stamp())
            db.add(row)
            db.flush()
            return self.freight_view(db, row, include_seller_financials=True)

    def transition_freight(self, principal, freight_id, payload):
        with self.write(principal) as db:
            row = db.get(MarketFreight, freight_id, with_for_update=True)
            if row is None:
                raise HTTPException(404, 'Flete no encontrado')
            self.authorize(db, principal, row.carrier_merchant_id, write=True)
            expected, new = ('PROPOSED', 'ACCEPTED') if payload.action == 'accept' else ('ACCEPTED', 'DELIVERED')
            if row.status == new:
                order = db.get(MarketOrder, row.order_id)
                return self.freight_view(db, row,
                    include_seller_financials=self.actor_can_manage(db, principal, order.seller_merchant_id))
            if row.status != expected:
                raise HTTPException(409, 'La acción no corresponde al estado actual del flete')
            order = db.get(MarketOrder, row.order_id, with_for_update=True)
            if order.status in ('CANCELLED', 'REJECTED'):
                raise HTTPException(409, 'El pedido está cerrado')
            if payload.action == 'deliver' and order.status != 'SHIPPED':
                raise HTTPException(409, 'El QR de tránsito debe confirmarse antes de cerrar el flete')
            row.status = new
            touch(row)
            db.flush()
            return self.freight_view(db, row,
                include_seller_financials=self.actor_can_manage(db, principal, order.seller_merchant_id))


def register_production_market_routes(app, accounts, public_url=''):
    service = ProductionMarket(accounts, public_url)
    app.state.production_market = service

    async def principal(request, write=False):
        return await run_in_threadpool(accounts.session, request, write)

    @app.get('/v1/market/localities', include_in_schema=False)
    async def localities(request: Request):
        await principal(request)
        return {'city': 'Ciudad de México', 'state_code': 'CMX',
            'localities': [{'code': code, 'name': name} for code, name in LOCALITIES]}

    @app.get('/v1/market/bootstrap', include_in_schema=False)
    async def bootstrap(request: Request, alcaldia: str | None = None, q: str = Query(default='', max_length=120)):
        user = await principal(request)
        return await run_in_threadpool(service.bootstrap, user, alcaldia, q)

    @app.get('/v1/market/listings', include_in_schema=False)
    async def catalog(request: Request, alcaldia: str | None = None, q: str = Query(default='', max_length=120),
                      cursor: str = Query(default='', max_length=32, pattern=r'^[0-9a-f]{0,32}$'),
                      limit: int = Query(default=200, ge=1, le=200)):
        await principal(request)
        def read():
            with accounts.Session() as db:
                return service.listing_catalog(db, alcaldia=alcaldia, q=q, after=cursor, limit=limit)
        return await run_in_threadpool(read)

    @app.put('/v1/market/profiles/{merchant_id}', include_in_schema=False)
    async def profile(merchant_id: str, payload: ProfileInput, request: Request):
        user = await principal(request, True)
        return await run_in_threadpool(service.save_profile, user, merchant_id, payload)

    @app.post('/v1/market/listings', status_code=201, include_in_schema=False)
    async def create_listing(payload: ListingInput, request: Request):
        user = await principal(request, True)
        return await run_in_threadpool(service.create_listing, user, payload)

    @app.patch('/v1/market/listings/{listing_id}', include_in_schema=False)
    async def update_listing(listing_id: str, payload: ListingPatch, request: Request):
        user = await principal(request, True)
        return await run_in_threadpool(service.update_listing, user, listing_id, payload)

    @app.put('/v1/market/listings/{listing_id}/image', include_in_schema=False)
    async def put_listing_image(listing_id: str, payload: ListingImageInput, request: Request):
        user = await principal(request, True)
        return await run_in_threadpool(service.set_listing_image, user, listing_id, payload)

    @app.get('/v1/market/listings/{listing_id}/image', include_in_schema=False)
    async def get_listing_image(listing_id: str, request: Request, sha256: str = Query(pattern=r'^[0-9a-f]{64}$')):
        user = await principal(request)
        content, mime_type, digest = await run_in_threadpool(service.get_listing_image, user, listing_id, sha256)
        return Response(content=content, media_type=mime_type, headers={
            'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff',
            'ETag': '"' + digest + '"'})

    @app.get('/v1/market/listings/{listing_id}/qr.png', include_in_schema=False)
    async def listing_qr(listing_id: str, request: Request, sha256: str = Query(pattern=r'^[0-9a-f]{64}$')):
        user = await principal(request)
        png = await run_in_threadpool(service.listing_qr_png, user, listing_id, sha256)
        return Response(content=png, media_type='image/png', headers={
            'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})

    @app.get('/v1/market/listings/{listing_id}', include_in_schema=False)
    async def verified_listing(listing_id: str, request: Request, sha256: str = Query(pattern=r'^[0-9a-f]{64}$')):
        user = await principal(request)
        return await run_in_threadpool(service.verified_public_listing, user, listing_id, sha256)

    @app.get('/v1/market/delivery-addresses', include_in_schema=False)
    async def list_delivery_addresses(request: Request, merchant_id: str = Query(pattern=r'^[0-9a-f]{32}$')):
        user = await principal(request)
        return await run_in_threadpool(service.list_addresses, user, merchant_id)

    @app.post('/v1/market/delivery-addresses', status_code=201, include_in_schema=False)
    async def create_delivery_address(payload: DeliveryAddressInput, request: Request):
        user = await principal(request, True)
        return await run_in_threadpool(service.save_address, user, payload)

    @app.put('/v1/market/delivery-addresses/{address_id}', include_in_schema=False)
    async def update_delivery_address(address_id: str, payload: DeliveryAddressInput, request: Request):
        user = await principal(request, True)
        return await run_in_threadpool(service.save_address, user, payload, address_id)

    @app.delete('/v1/market/delivery-addresses/{address_id}', include_in_schema=False)
    async def delete_delivery_address(address_id: str, request: Request,
                                     merchant_id: str = Query(pattern=r'^[0-9a-f]{32}$')):
        user = await principal(request, True)
        return await run_in_threadpool(service.delete_address, user, merchant_id, address_id)

    @app.get('/v1/market/cart', include_in_schema=False)
    async def get_cart(request: Request, buyer_merchant_id: str = Query(pattern=r'^[0-9a-f]{32}$')):
        user = await principal(request)
        return await run_in_threadpool(service.get_cart, user, buyer_merchant_id)

    @app.post('/v1/market/cart/items', include_in_schema=False)
    async def add_cart_item(payload: CartItemInput, request: Request):
        user = await principal(request, True)
        return await run_in_threadpool(service.add_cart_item, user, payload)

    @app.delete('/v1/market/cart/items/{listing_id}', include_in_schema=False)
    async def delete_cart_item(listing_id: str, request: Request,
                              buyer_merchant_id: str = Query(pattern=r'^[0-9a-f]{32}$')):
        user = await principal(request, True)
        return await run_in_threadpool(service.remove_cart_item, user, buyer_merchant_id, listing_id)

    @app.post('/v1/market/cart/checkout', status_code=201, include_in_schema=False)
    async def checkout_cart(payload: CartCheckoutInput, request: Request):
        user = await principal(request, True)
        return await run_in_threadpool(service.checkout_cart, user, payload)

    @app.post('/v1/market/quotes', status_code=201, include_in_schema=False)
    async def create_quote(payload: QuoteInput, request: Request):
        user = await principal(request, True)
        return await run_in_threadpool(service.create_quote, user, payload)

    @app.post('/v1/market/quotes/{quote_id}/respond', include_in_schema=False)
    async def respond_quote(quote_id: str, payload: QuoteResponse, request: Request):
        user = await principal(request, True)
        return await run_in_threadpool(service.respond_quote, user, quote_id, payload)

    @app.post('/v1/market/quotes/{quote_id}/accept', status_code=201, include_in_schema=False)
    async def accept_quote(quote_id: str, payload: QuoteAccept, request: Request):
        user = await principal(request, True)
        return await run_in_threadpool(service.accept_quote, user, quote_id, payload)

    @app.post('/v1/market/orders', status_code=201, include_in_schema=False)
    async def create_order(payload: PurchaseInput, request: Request):
        user = await principal(request, True)
        return await run_in_threadpool(service.create_order, user, payload)

    @app.get('/v1/market/orders/{order_id}', include_in_schema=False)
    async def get_order(order_id: str, request: Request):
        user = await principal(request)
        return await run_in_threadpool(service.get_order, user, order_id)

    @app.get('/v1/market/orders/{order_id}/qr/{kind}.png', include_in_schema=False)
    async def order_qr(order_id: str, kind: Literal['payment', 'bank_credit', 'transit', 'receipt'],
                       request: Request, sha256: str = Query(pattern=r'^[0-9a-f]{64}$')):
        user = await principal(request)
        png = await run_in_threadpool(service.order_qr_image, user, order_id, kind.upper(), sha256)
        return Response(content=png, media_type='image/png', headers={
            'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})

    @app.post('/v1/market/order-qr/scan', include_in_schema=False)
    async def scan_order_qr(payload: OrderQRScanInput, request: Request):
        user = await principal(request, True)
        return await run_in_threadpool(service.scan_order_qr, user, payload)

    @app.post('/v1/market/orders/{order_id}/transition', include_in_schema=False)
    async def transition_order(order_id: str, payload: OrderTransition, request: Request):
        user = await principal(request, True)
        return await run_in_threadpool(service.transition_order, user, order_id, payload)

    @app.post('/v1/market/freights', status_code=201, include_in_schema=False)
    async def create_freight(payload: FreightInput, request: Request):
        user = await principal(request, True)
        return await run_in_threadpool(service.create_freight, user, payload)

    @app.post('/v1/market/freights/{freight_id}/transition', include_in_schema=False)
    async def transition_freight(freight_id: str, payload: FreightTransition, request: Request):
        user = await principal(request, True)
        return await run_in_threadpool(service.transition_freight, user, freight_id, payload)
