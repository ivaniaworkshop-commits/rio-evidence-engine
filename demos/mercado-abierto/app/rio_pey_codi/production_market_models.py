"""Production marketplace records, separate from historical demonstration snapshots.

Import this module before Base.metadata.create_all in local environments. These
records contain participant-authenticated trade actions, never bank settlement.
"""
from sqlalchemy import (BigInteger, Boolean, CheckConstraint, Column, ForeignKey, LargeBinary,
                        Index, Integer, String, Text, UniqueConstraint, false)
from .models import Base


class MarketProfile(Base):
    __tablename__ = 'market_profiles'
    merchant_id = Column(String(32), ForeignKey('merchants.id'), primary_key=True)
    kind = Column(String(16), nullable=False)
    alcaldia = Column(String(40), nullable=False)
    colonia = Column(String(100), nullable=False)
    description = Column(String(1000), nullable=False, default='', server_default='')
    # Deliberately public only when the merchant publishes their profile.
    whatsapp_phone = Column(String(16), nullable=True)
    published = Column(Boolean, nullable=False, default=False, server_default=false())
    revision = Column(Integer, nullable=False, default=1, server_default='1')
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)
    __table_args__ = (
        CheckConstraint("kind IN ('merchant','freighter','both')", name='ck_market_profile_kind'),
        CheckConstraint('revision >= 1', name='ck_market_profile_revision'),
        Index('idx_market_profile_locality', 'published', 'alcaldia', 'kind'),
    )


class MarketListing(Base):
    __tablename__ = 'market_listings'
    id = Column(String(32), primary_key=True)
    merchant_id = Column(String(32), ForeignKey('merchants.id'), nullable=False)
    name = Column(String(120), nullable=False)
    description = Column(String(1000), nullable=False, default='', server_default='')
    category = Column(String(80), nullable=False)
    unit = Column(String(16), nullable=False)
    # price_minor is the customer-facing amount; the seller breakdown is private.
    price_minor = Column(BigInteger, nullable=False)
    seller_price_minor = Column(BigInteger, nullable=False, default=0, server_default='0')
    platform_fee_minor = Column(BigInteger, nullable=False, default=0, server_default='0')
    wholesale_discount_bps = Column(Integer, nullable=False, default=0, server_default='0')
    discounted_seller_price_minor = Column(BigInteger, nullable=False, default=0, server_default='0')
    stock_milli = Column(BigInteger, nullable=False)
    image_data = Column(LargeBinary, nullable=True)
    image_mime = Column(String(32), nullable=True)
    image_sha256 = Column(String(64), nullable=True)
    qr_sha256 = Column(String(64), nullable=True)
    published = Column(Boolean, nullable=False, default=False, server_default=false())
    revision = Column(Integer, nullable=False, default=1, server_default='1')
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)
    __table_args__ = (
        CheckConstraint("unit IN ('piece','kg','meter','service')", name='ck_market_listing_unit'),
        CheckConstraint('price_minor > 0 AND price_minor <= 100000000', name='ck_market_listing_price'),
        CheckConstraint('seller_price_minor >= 0 AND seller_price_minor <= 100000000', name='ck_market_listing_seller_price'),
        CheckConstraint('platform_fee_minor >= 0 AND platform_fee_minor <= 100000000', name='ck_market_listing_platform_fee'),
        CheckConstraint('wholesale_discount_bps >= 0 AND wholesale_discount_bps <= 9900', name='ck_market_listing_wholesale_discount'),
        CheckConstraint('discounted_seller_price_minor >= 0 AND discounted_seller_price_minor <= 100000000', name='ck_market_listing_discounted_seller_price'),
        CheckConstraint('stock_milli >= 0 AND stock_milli <= 1000000000000', name='ck_market_listing_stock'),
        CheckConstraint('revision >= 1', name='ck_market_listing_revision'),
        UniqueConstraint('qr_sha256', name='uq_market_listing_qr_sha256'),
        Index('idx_market_listing_feed', 'published', 'created_at', 'id'),
        Index('idx_market_listing_merchant', 'merchant_id', 'id'),
    )


class MarketQuote(Base):
    __tablename__ = 'market_quotes'
    id = Column(String(32), primary_key=True)
    buyer_merchant_id = Column(String(32), ForeignKey('merchants.id'), nullable=False)
    seller_merchant_id = Column(String(32), ForeignKey('merchants.id'), nullable=False)
    listing_id = Column(String(32), ForeignKey('market_listings.id'), nullable=False)
    listing_name = Column(String(120), nullable=False)
    unit = Column(String(16), nullable=False)
    quantity_milli = Column(BigInteger, nullable=False)
    unit_price_minor = Column(BigInteger, nullable=True)
    seller_unit_price_minor = Column(BigInteger, nullable=True)
    platform_fee_minor = Column(BigInteger, nullable=False, default=0, server_default='0')
    seller_delivery_fee_minor = Column(BigInteger, nullable=False, default=0, server_default='0')
    freight_platform_fee_minor = Column(BigInteger, nullable=False, default=0, server_default='0')
    delivery_fee_minor = Column(BigInteger, nullable=False, default=0, server_default='0')
    total_minor = Column(BigInteger, nullable=True)
    message = Column(String(1000), nullable=False, default='', server_default='')
    seller_message = Column(String(1000), nullable=False, default='', server_default='')
    status = Column(String(16), nullable=False)
    order_id = Column(String(32), nullable=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)
    revision = Column(Integer, nullable=False, default=1, server_default='1')
    __table_args__ = (
        CheckConstraint("status IN ('REQUESTED','QUOTED','ACCEPTED','REJECTED','CANCELLED')", name='ck_market_quote_status'),
        CheckConstraint("unit IN ('piece','kg','meter','service')", name='ck_market_quote_unit'),
        CheckConstraint('quantity_milli > 0 AND quantity_milli <= 1000000000000', name='ck_market_quote_quantity'),
        CheckConstraint('unit_price_minor > 0 AND unit_price_minor <= 100000000', name='ck_market_quote_price'),
        CheckConstraint('delivery_fee_minor >= 0 AND delivery_fee_minor <= 100000000', name='ck_market_quote_delivery'),
        CheckConstraint('seller_delivery_fee_minor >= 0 AND seller_delivery_fee_minor <= 100000000', name='ck_market_quote_seller_delivery'),
        CheckConstraint('platform_fee_minor >= 0 AND platform_fee_minor <= 100000000', name='ck_market_quote_platform_fee'),
        CheckConstraint('freight_platform_fee_minor >= 0 AND freight_platform_fee_minor <= 100000000', name='ck_market_quote_freight_platform_fee'),
        CheckConstraint('total_minor > 0 AND total_minor <= 100000000', name='ck_market_quote_total'),
        CheckConstraint('buyer_merchant_id <> seller_merchant_id', name='ck_market_quote_parties'),
        CheckConstraint('revision >= 1', name='ck_market_quote_revision'),
        Index('idx_market_quote_buyer', 'buyer_merchant_id', 'created_at', 'id'),
        Index('idx_market_quote_seller', 'seller_merchant_id', 'created_at', 'id'),
    )


class MarketOrder(Base):
    __tablename__ = 'market_orders'
    id = Column(String(32), primary_key=True)
    buyer_merchant_id = Column(String(32), ForeignKey('merchants.id'), nullable=False)
    seller_merchant_id = Column(String(32), ForeignKey('merchants.id'), nullable=False)
    listing_id = Column(String(32), ForeignKey('market_listings.id'), nullable=False)
    quote_id = Column(String(32), ForeignKey('market_quotes.id'), nullable=True)
    listing_name = Column(String(120), nullable=False)
    unit = Column(String(16), nullable=False)
    quantity_milli = Column(BigInteger, nullable=False)
    unit_price_minor = Column(BigInteger, nullable=False)
    seller_unit_price_minor = Column(BigInteger, nullable=False, default=0, server_default='0')
    platform_fee_minor = Column(BigInteger, nullable=False, default=0, server_default='0')
    seller_delivery_fee_minor = Column(BigInteger, nullable=False, default=0, server_default='0')
    freight_platform_fee_minor = Column(BigInteger, nullable=False, default=0, server_default='0')
    delivery_fee_minor = Column(BigInteger, nullable=False, default=0, server_default='0')
    total_minor = Column(BigInteger, nullable=False)
    notes = Column(String(1000), nullable=False, default='', server_default='')
    status = Column(String(16), nullable=False)
    request_key = Column(String(32), nullable=False)
    request_sha256 = Column(String(64), nullable=False)
    cart_checkout_key = Column(String(32), nullable=True)
    delivery_address_json = Column(Text, nullable=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)
    revision = Column(Integer, nullable=False, default=1, server_default='1')
    __table_args__ = (
        UniqueConstraint('buyer_merchant_id', 'request_key', name='uq_market_order_request'),
        UniqueConstraint('quote_id', name='uq_market_order_quote'),
        CheckConstraint("status IN ('REQUESTED','ACCEPTED','PREPARED','SHIPPED','RECEIVED','REJECTED','CANCELLED')", name='ck_market_order_status'),
        CheckConstraint("unit IN ('piece','kg','meter','service')", name='ck_market_order_unit'),
        CheckConstraint('quantity_milli > 0 AND quantity_milli <= 1000000000000', name='ck_market_order_quantity'),
        CheckConstraint('unit_price_minor > 0 AND unit_price_minor <= 100000000', name='ck_market_order_price'),
        CheckConstraint('delivery_fee_minor >= 0 AND delivery_fee_minor <= 100000000', name='ck_market_order_delivery'),
        CheckConstraint('seller_delivery_fee_minor >= 0 AND seller_delivery_fee_minor <= 100000000', name='ck_market_order_seller_delivery'),
        CheckConstraint('platform_fee_minor >= 0 AND platform_fee_minor <= 100000000', name='ck_market_order_platform_fee'),
        CheckConstraint('freight_platform_fee_minor >= 0 AND freight_platform_fee_minor <= 100000000', name='ck_market_order_freight_platform_fee'),
        CheckConstraint('total_minor > 0 AND total_minor <= 100000000', name='ck_market_order_total'),
        CheckConstraint('buyer_merchant_id <> seller_merchant_id', name='ck_market_order_parties'),
        CheckConstraint('revision >= 1', name='ck_market_order_revision'),
        Index('idx_market_order_buyer', 'buyer_merchant_id', 'created_at', 'id'),
        Index('idx_market_order_seller', 'seller_merchant_id', 'created_at', 'id'),
    )


class MarketCart(Base):
    __tablename__ = 'market_carts'
    buyer_merchant_id = Column(String(32), ForeignKey('merchants.id'), primary_key=True)
    status = Column(String(16), nullable=False, default='OPEN', server_default='OPEN')
    last_checkout_key = Column(String(32), nullable=True)
    last_order_ids = Column(Text, nullable=True)
    revision = Column(Integer, nullable=False, default=1, server_default='1')
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)
    __table_args__ = (
        CheckConstraint("status IN ('OPEN','CHECKED_OUT')", name='ck_market_cart_status'),
        CheckConstraint('revision >= 1', name='ck_market_cart_revision'),
    )


class MarketCartItem(Base):
    __tablename__ = 'market_cart_items'
    buyer_merchant_id = Column(String(32), ForeignKey('market_carts.buyer_merchant_id'), primary_key=True)
    listing_id = Column(String(32), ForeignKey('market_listings.id'), primary_key=True)
    quantity_milli = Column(BigInteger, nullable=False)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)
    __table_args__ = (
        CheckConstraint('quantity_milli > 0 AND quantity_milli <= 1000000000', name='ck_market_cart_quantity'),
        Index('idx_market_cart_item_listing', 'listing_id'),
    )


class MarketOrderQR(Base):
    __tablename__ = 'market_order_qrs'
    id = Column(String(32), primary_key=True)
    order_id = Column(String(32), ForeignKey('market_orders.id'), nullable=False)
    kind = Column(String(20), nullable=False)
    sha256 = Column(String(64), nullable=False, unique=True)
    created_at = Column(BigInteger, nullable=False)
    used_at = Column(BigInteger, nullable=True)
    __table_args__ = (
        UniqueConstraint('order_id', 'kind', name='uq_market_order_qr_kind'),
        CheckConstraint("kind IN ('PAYMENT','BANK_CREDIT','TRANSIT','RECEIPT')", name='ck_market_order_qr_kind'),
        Index('idx_market_order_qr_order', 'order_id', 'kind'),
    )


class MarketOrderEvent(Base):
    __tablename__ = 'market_order_events'
    id = Column(String(32), primary_key=True)
    order_id = Column(String(32), ForeignKey('market_orders.id'), nullable=False)
    actor_user_id = Column(String(32), ForeignKey('users.id'), nullable=True)
    event_type = Column(String(40), nullable=False)
    stage = Column(String(32), nullable=False)
    source = Column(String(24), nullable=False)
    created_at = Column(BigInteger, nullable=False)
    __table_args__ = (
        CheckConstraint("source IN ('ACTOR','PEY','BANK','SYSTEM','QR_SCAN')", name='ck_market_order_event_source'),
        Index('idx_market_order_events_history', 'order_id', 'created_at', 'id'),
    )


class MarketOrderItem(Base):
    __tablename__ = 'market_order_items'
    id = Column(String(32), primary_key=True)
    order_id = Column(String(32), ForeignKey('market_orders.id'), nullable=False)
    listing_id = Column(String(32), ForeignKey('market_listings.id'), nullable=False)
    listing_name = Column(String(120), nullable=False)
    unit = Column(String(16), nullable=False)
    quantity_milli = Column(BigInteger, nullable=False)
    unit_price_minor = Column(BigInteger, nullable=False)
    seller_unit_price_minor = Column(BigInteger, nullable=False)
    platform_fee_minor = Column(BigInteger, nullable=False)
    product_qr_sha256 = Column(String(64), nullable=True)
    total_minor = Column(BigInteger, nullable=False)
    created_at = Column(BigInteger, nullable=False)
    __table_args__ = (
        CheckConstraint('quantity_milli > 0 AND quantity_milli <= 1000000000', name='ck_market_order_item_quantity'),
        CheckConstraint('unit_price_minor > 0 AND unit_price_minor <= 100000000', name='ck_market_order_item_price'),
        CheckConstraint('seller_unit_price_minor >= 0 AND seller_unit_price_minor <= 100000000', name='ck_market_order_item_seller_price'),
        CheckConstraint('platform_fee_minor >= 0 AND platform_fee_minor <= 100000000', name='ck_market_order_item_fee'),
        CheckConstraint('total_minor > 0 AND total_minor <= 100000000', name='ck_market_order_item_total'),
        Index('idx_market_order_items_order', 'order_id', 'id'),
    )


class MarketDeliveryAddress(Base):
    __tablename__ = 'market_delivery_addresses'
    id = Column(String(32), primary_key=True)
    merchant_id = Column(String(32), ForeignKey('merchants.id'), nullable=False)
    label = Column(String(80), nullable=False)
    recipient = Column(String(120), nullable=False)
    phone = Column(String(16), nullable=False)
    street = Column(String(160), nullable=False)
    exterior_number = Column(String(20), nullable=False)
    interior_number = Column(String(20), nullable=False, default='', server_default='')
    colonia = Column(String(100), nullable=False)
    alcaldia = Column(String(40), nullable=False)
    postal_code = Column(String(5), nullable=False)
    reference_notes = Column(String(240), nullable=False, default='', server_default='')
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)
    __table_args__ = (
        CheckConstraint('length(postal_code) = 5', name='ck_market_delivery_postal_code'),
        CheckConstraint("alcaldia IN ('alvaro-obregon','azcapotzalco','benito-juarez','coyoacan','cuajimalpa-de-morelos','cuauhtemoc','gustavo-a-madero','iztacalco','iztapalapa','la-magdalena-contreras','miguel-hidalgo','milpa-alta','tlahuac','tlalpan','venustiano-carranza','xochimilco')", name='ck_market_delivery_alcaldia'),
        Index('idx_market_delivery_address_merchant', 'merchant_id', 'created_at', 'id'),
    )


class MarketFreight(Base):
    __tablename__ = 'market_freights'
    id = Column(String(32), primary_key=True)
    order_id = Column(String(32), ForeignKey('market_orders.id'), nullable=False)
    carrier_merchant_id = Column(String(32), ForeignKey('merchants.id'), nullable=False)
    fee_minor = Column(BigInteger, nullable=False)
    notes = Column(String(1000), nullable=False, default='', server_default='')
    status = Column(String(16), nullable=False)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)
    revision = Column(Integer, nullable=False, default=1, server_default='1')
    __table_args__ = (
        UniqueConstraint('order_id', name='uq_market_freight_order'),
        CheckConstraint("status IN ('PROPOSED','ACCEPTED','DELIVERED')", name='ck_market_freight_status'),
        CheckConstraint('fee_minor >= 0 AND fee_minor <= 100000000', name='ck_market_freight_fee'),
        CheckConstraint('revision >= 1', name='ck_market_freight_revision'),
        Index('idx_market_freight_carrier', 'carrier_merchant_id', 'created_at', 'id'),
    )
