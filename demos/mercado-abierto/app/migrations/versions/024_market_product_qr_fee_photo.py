"""Add product QR/photo, wholesale pricing, delivery addresses and cart checkout."""
from hashlib import sha256
import json

from alembic import op
import sqlalchemy as sa


revision = '024'
down_revision = '023'
branch_labels = None
depends_on = None


def _qr_digest(merchant_id, listing_id):
    payload = json.dumps(
        {'version': 1, 'merchant_id': merchant_id, 'listing_id': listing_id},
        sort_keys=True, separators=(',', ':')).encode()
    return sha256(b'rio.market.product-qr.v1\0' + payload).hexdigest()


def _fee(price_minor):
    return (price_minor * 5 + 50) // 100


def upgrade():
    op.add_column('merchants', sa.Column('archived_at', sa.BigInteger(), nullable=True))
    op.add_column('market_listings', sa.Column('seller_price_minor', sa.BigInteger(), nullable=False, server_default='0'))
    op.add_column('market_listings', sa.Column('platform_fee_minor', sa.BigInteger(), nullable=False, server_default='0'))
    op.add_column('market_listings', sa.Column('wholesale_discount_bps', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('market_listings', sa.Column('discounted_seller_price_minor', sa.BigInteger(), nullable=False, server_default='0'))
    op.add_column('market_listings', sa.Column('image_data', sa.LargeBinary(), nullable=True))
    op.add_column('market_listings', sa.Column('image_mime', sa.String(32), nullable=True))
    op.add_column('market_listings', sa.Column('image_sha256', sa.String(64), nullable=True))
    op.add_column('market_listings', sa.Column('qr_sha256', sa.String(64), nullable=True))

    op.add_column('market_quotes', sa.Column('seller_unit_price_minor', sa.BigInteger(), nullable=True))
    op.add_column('market_quotes', sa.Column('platform_fee_minor', sa.BigInteger(), nullable=False, server_default='0'))
    op.add_column('market_quotes', sa.Column('seller_delivery_fee_minor', sa.BigInteger(), nullable=False, server_default='0'))
    op.add_column('market_quotes', sa.Column('freight_platform_fee_minor', sa.BigInteger(), nullable=False, server_default='0'))
    op.add_column('market_orders', sa.Column('seller_unit_price_minor', sa.BigInteger(), nullable=False, server_default='0'))
    op.add_column('market_orders', sa.Column('platform_fee_minor', sa.BigInteger(), nullable=False, server_default='0'))
    op.add_column('market_orders', sa.Column('seller_delivery_fee_minor', sa.BigInteger(), nullable=False, server_default='0'))
    op.add_column('market_orders', sa.Column('freight_platform_fee_minor', sa.BigInteger(), nullable=False, server_default='0'))
    op.add_column('market_orders', sa.Column('cart_checkout_key', sa.String(32), nullable=True))
    op.add_column('market_orders', sa.Column('delivery_address_json', sa.Text(), nullable=True))

    connection = op.get_bind()
    listings = connection.execute(sa.text(
        'SELECT id, merchant_id, price_minor, published FROM market_listings')).mappings().all()
    for row in listings:
        seller_price = int(row['price_minor'])
        fee = _fee(seller_price) if row['published'] else 0
        buyer_price = seller_price + fee
        if buyer_price > 100_000_000:
            raise RuntimeError('A published product exceeds the limit after applying the 5% platform surcharge')
        qr_sha = _qr_digest(row['merchant_id'], row['id']) if row['published'] else None
        connection.execute(sa.text(
            'UPDATE market_listings SET seller_price_minor=:seller, platform_fee_minor=:fee, '
            'discounted_seller_price_minor=:seller, '
            'price_minor=:buyer, qr_sha256=:qr WHERE id=:id'),
            {'seller': seller_price, 'fee': fee, 'buyer': buyer_price, 'qr': qr_sha, 'id': row['id']})

    connection.execute(sa.text(
        'UPDATE market_quotes SET seller_unit_price_minor=unit_price_minor '
        'WHERE unit_price_minor IS NOT NULL'))
    connection.execute(sa.text(
        'UPDATE market_quotes SET seller_delivery_fee_minor=delivery_fee_minor'))
    connection.execute(sa.text(
        'UPDATE market_orders SET seller_unit_price_minor=unit_price_minor'))
    connection.execute(sa.text(
        'UPDATE market_orders SET seller_delivery_fee_minor=delivery_fee_minor'))

    # Batch mode supports the disposable SQLite acceptance schema and PostgreSQL.
    with op.batch_alter_table('market_listings') as batch:
        batch.create_unique_constraint('uq_market_listing_qr_sha256', ['qr_sha256'])
        batch.create_check_constraint('ck_market_listing_seller_price',
            'seller_price_minor >= 0 AND seller_price_minor <= 100000000')
        batch.create_check_constraint('ck_market_listing_platform_fee',
            'platform_fee_minor >= 0 AND platform_fee_minor <= 100000000')
        batch.create_check_constraint('ck_market_listing_wholesale_discount',
            'wholesale_discount_bps >= 0 AND wholesale_discount_bps <= 9900')
        batch.create_check_constraint('ck_market_listing_discounted_seller_price',
            'discounted_seller_price_minor >= 0 AND discounted_seller_price_minor <= 100000000')
    with op.batch_alter_table('market_quotes') as batch:
        batch.create_check_constraint('ck_market_quote_platform_fee',
            'platform_fee_minor >= 0 AND platform_fee_minor <= 100000000')
        batch.create_check_constraint('ck_market_quote_seller_delivery',
            'seller_delivery_fee_minor >= 0 AND seller_delivery_fee_minor <= 100000000')
        batch.create_check_constraint('ck_market_quote_freight_platform_fee',
            'freight_platform_fee_minor >= 0 AND freight_platform_fee_minor <= 100000000')
    with op.batch_alter_table('market_orders') as batch:
        batch.create_check_constraint('ck_market_order_platform_fee',
            'platform_fee_minor >= 0 AND platform_fee_minor <= 100000000')
        batch.create_check_constraint('ck_market_order_seller_delivery',
            'seller_delivery_fee_minor >= 0 AND seller_delivery_fee_minor <= 100000000')
        batch.create_check_constraint('ck_market_order_freight_platform_fee',
            'freight_platform_fee_minor >= 0 AND freight_platform_fee_minor <= 100000000')

    op.create_table('market_carts',
        sa.Column('buyer_merchant_id', sa.String(32), sa.ForeignKey('merchants.id'), primary_key=True),
        sa.Column('status', sa.String(16), nullable=False, server_default='OPEN'),
        sa.Column('last_checkout_key', sa.String(32), nullable=True),
        sa.Column('last_order_ids', sa.Text(), nullable=True),
        sa.Column('revision', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('updated_at', sa.BigInteger(), nullable=False),
        sa.CheckConstraint("status IN ('OPEN','CHECKED_OUT')", name='ck_market_cart_status'),
        sa.CheckConstraint('revision >= 1', name='ck_market_cart_revision'))
    op.create_table('market_cart_items',
        sa.Column('buyer_merchant_id', sa.String(32), sa.ForeignKey('market_carts.buyer_merchant_id'), primary_key=True),
        sa.Column('listing_id', sa.String(32), sa.ForeignKey('market_listings.id'), primary_key=True),
        sa.Column('quantity_milli', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('updated_at', sa.BigInteger(), nullable=False),
        sa.CheckConstraint('quantity_milli > 0 AND quantity_milli <= 1000000000', name='ck_market_cart_quantity'))
    op.create_index('idx_market_cart_item_listing', 'market_cart_items', ['listing_id'])
    op.create_table('market_order_qrs',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('order_id', sa.String(32), sa.ForeignKey('market_orders.id'), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False, unique=True),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('used_at', sa.BigInteger(), nullable=True),
        sa.UniqueConstraint('order_id', 'kind', name='uq_market_order_qr_kind'),
        sa.CheckConstraint("kind IN ('PAYMENT','BANK_CREDIT','TRANSIT','RECEIPT')", name='ck_market_order_qr_kind'))
    op.create_index('idx_market_order_qr_order', 'market_order_qrs', ['order_id', 'kind'])
    op.create_table('market_order_events',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('order_id', sa.String(32), sa.ForeignKey('market_orders.id'), nullable=False),
        sa.Column('actor_user_id', sa.String(32), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('event_type', sa.String(40), nullable=False),
        sa.Column('stage', sa.String(32), nullable=False),
        sa.Column('source', sa.String(24), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.CheckConstraint("source IN ('ACTOR','PEY','BANK','SYSTEM','QR_SCAN')", name='ck_market_order_event_source'))
    op.create_index('idx_market_order_events_history', 'market_order_events', ['order_id', 'created_at', 'id'])
    op.create_table('market_order_items',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('order_id', sa.String(32), sa.ForeignKey('market_orders.id'), nullable=False),
        sa.Column('listing_id', sa.String(32), sa.ForeignKey('market_listings.id'), nullable=False),
        sa.Column('listing_name', sa.String(120), nullable=False),
        sa.Column('unit', sa.String(16), nullable=False),
        sa.Column('quantity_milli', sa.BigInteger(), nullable=False),
        sa.Column('unit_price_minor', sa.BigInteger(), nullable=False),
        sa.Column('seller_unit_price_minor', sa.BigInteger(), nullable=False),
        sa.Column('platform_fee_minor', sa.BigInteger(), nullable=False),
        sa.Column('product_qr_sha256', sa.String(64), nullable=True),
        sa.Column('total_minor', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.CheckConstraint('quantity_milli > 0 AND quantity_milli <= 1000000000', name='ck_market_order_item_quantity'),
        sa.CheckConstraint('unit_price_minor > 0 AND unit_price_minor <= 100000000', name='ck_market_order_item_price'),
        sa.CheckConstraint('seller_unit_price_minor >= 0 AND seller_unit_price_minor <= 100000000', name='ck_market_order_item_seller_price'),
        sa.CheckConstraint('platform_fee_minor >= 0 AND platform_fee_minor <= 100000000', name='ck_market_order_item_fee'),
        sa.CheckConstraint('total_minor > 0 AND total_minor <= 100000000', name='ck_market_order_item_total'))
    op.create_index('idx_market_order_items_order', 'market_order_items', ['order_id', 'id'])
    op.create_table('market_delivery_addresses',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('merchant_id', sa.String(32), sa.ForeignKey('merchants.id'), nullable=False),
        sa.Column('label', sa.String(80), nullable=False),
        sa.Column('recipient', sa.String(120), nullable=False),
        sa.Column('phone', sa.String(16), nullable=False),
        sa.Column('street', sa.String(160), nullable=False),
        sa.Column('exterior_number', sa.String(20), nullable=False),
        sa.Column('interior_number', sa.String(20), nullable=False, server_default=''),
        sa.Column('colonia', sa.String(100), nullable=False),
        sa.Column('alcaldia', sa.String(40), nullable=False),
        sa.Column('postal_code', sa.String(5), nullable=False),
        sa.Column('reference_notes', sa.String(240), nullable=False, server_default=''),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('updated_at', sa.BigInteger(), nullable=False),
        sa.CheckConstraint('length(postal_code) = 5', name='ck_market_delivery_postal_code'),
        sa.CheckConstraint("alcaldia IN ('alvaro-obregon','azcapotzalco','benito-juarez','coyoacan','cuajimalpa-de-morelos','cuauhtemoc','gustavo-a-madero','iztacalco','iztapalapa','la-magdalena-contreras','miguel-hidalgo','milpa-alta','tlahuac','tlalpan','venustiano-carranza','xochimilco')", name='ck_market_delivery_alcaldia'))
    op.create_index('idx_market_delivery_address_merchant', 'market_delivery_addresses', ['merchant_id', 'created_at', 'id'])


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text(
            'SELECT 1 FROM market_listings WHERE image_data IS NOT NULL OR qr_sha256 IS NOT NULL '
            'OR platform_fee_minor > 0 OR wholesale_discount_bps > 0 LIMIT 1')).first() or connection.execute(sa.text(
            'SELECT 1 FROM market_order_events LIMIT 1')).first() or connection.execute(sa.text(
            'SELECT 1 FROM market_carts LIMIT 1')).first() or connection.execute(sa.text(
            'SELECT 1 FROM market_order_qrs LIMIT 1')).first() or connection.execute(sa.text(
            'SELECT 1 FROM market_order_items LIMIT 1')).first() or connection.execute(sa.text(
            'SELECT 1 FROM market_delivery_addresses LIMIT 1')).first():
        raise RuntimeError('Refusing to discard marketplace photos, purchase QR identities, cart or order history')
    op.drop_index('idx_market_delivery_address_merchant', table_name='market_delivery_addresses')
    op.drop_table('market_delivery_addresses')
    op.drop_index('idx_market_order_items_order', table_name='market_order_items')
    op.drop_table('market_order_items')
    op.drop_index('idx_market_order_events_history', table_name='market_order_events')
    op.drop_table('market_order_events')
    op.drop_index('idx_market_order_qr_order', table_name='market_order_qrs')
    op.drop_table('market_order_qrs')
    op.drop_index('idx_market_cart_item_listing', table_name='market_cart_items')
    op.drop_table('market_cart_items')
    op.drop_table('market_carts')
    with op.batch_alter_table('market_orders') as batch:
        batch.drop_constraint('ck_market_order_platform_fee', type_='check')
        batch.drop_constraint('ck_market_order_freight_platform_fee', type_='check')
        batch.drop_constraint('ck_market_order_seller_delivery', type_='check')
    with op.batch_alter_table('market_quotes') as batch:
        batch.drop_constraint('ck_market_quote_platform_fee', type_='check')
        batch.drop_constraint('ck_market_quote_freight_platform_fee', type_='check')
        batch.drop_constraint('ck_market_quote_seller_delivery', type_='check')
    with op.batch_alter_table('market_listings') as batch:
        batch.drop_constraint('ck_market_listing_platform_fee', type_='check')
        batch.drop_constraint('ck_market_listing_discounted_seller_price', type_='check')
        batch.drop_constraint('ck_market_listing_wholesale_discount', type_='check')
        batch.drop_constraint('ck_market_listing_seller_price', type_='check')
        batch.drop_constraint('uq_market_listing_qr_sha256', type_='unique')
    op.drop_column('market_orders', 'platform_fee_minor')
    op.drop_column('market_orders', 'seller_unit_price_minor')
    op.drop_column('market_orders', 'freight_platform_fee_minor')
    op.drop_column('market_orders', 'seller_delivery_fee_minor')
    op.drop_column('market_orders', 'cart_checkout_key')
    op.drop_column('market_orders', 'delivery_address_json')
    op.drop_column('market_quotes', 'platform_fee_minor')
    op.drop_column('market_quotes', 'seller_unit_price_minor')
    op.drop_column('market_quotes', 'freight_platform_fee_minor')
    op.drop_column('market_quotes', 'seller_delivery_fee_minor')
    op.drop_column('market_listings', 'qr_sha256')
    op.drop_column('market_listings', 'image_sha256')
    op.drop_column('market_listings', 'image_mime')
    op.drop_column('market_listings', 'image_data')
    op.drop_column('market_listings', 'platform_fee_minor')
    op.drop_column('market_listings', 'seller_price_minor')
    op.drop_column('market_listings', 'discounted_seller_price_minor')
    op.drop_column('market_listings', 'wholesale_discount_bps')
    op.drop_column('merchants', 'archived_at')
