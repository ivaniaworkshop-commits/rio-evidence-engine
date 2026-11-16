"""Production marketplace: opt-in shared catalog and participant-authorized trade records.

No historical demonstration snapshots are promoted or modified by this migration.
"""
from alembic import op
import sqlalchemy as sa

revision = '019'
down_revision = '018'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('market_profiles',
        sa.Column('merchant_id', sa.String(32), sa.ForeignKey('merchants.id'), primary_key=True, nullable=False),
        sa.Column('kind', sa.String(16), nullable=False),
        sa.Column('alcaldia', sa.String(40), nullable=False),
        sa.Column('colonia', sa.String(100), nullable=False),
        sa.Column('description', sa.String(1000), nullable=False, server_default=''),
        sa.Column('published', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('revision', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('updated_at', sa.BigInteger(), nullable=False),
        sa.CheckConstraint("kind IN ('merchant','freighter','both')", name='ck_market_profile_kind'),
        sa.CheckConstraint('revision >= 1', name='ck_market_profile_revision'),
    )
    op.create_index('idx_market_profile_locality', 'market_profiles', ['published', 'alcaldia', 'kind'])

    op.create_table('market_listings',
        sa.Column('id', sa.String(32), primary_key=True, nullable=False),
        sa.Column('merchant_id', sa.String(32), sa.ForeignKey('merchants.id'), nullable=False),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('description', sa.String(1000), nullable=False, server_default=''),
        sa.Column('category', sa.String(80), nullable=False),
        sa.Column('unit', sa.String(16), nullable=False),
        sa.Column('price_minor', sa.BigInteger(), nullable=False),
        sa.Column('stock_milli', sa.BigInteger(), nullable=False),
        sa.Column('published', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('revision', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('updated_at', sa.BigInteger(), nullable=False),
        sa.CheckConstraint('price_minor > 0 AND price_minor <= 100000000', name='ck_market_listing_price'),
        sa.CheckConstraint('revision >= 1', name='ck_market_listing_revision'),
        sa.CheckConstraint('stock_milli >= 0 AND stock_milli <= 1000000000000', name='ck_market_listing_stock'),
        sa.CheckConstraint("unit IN ('piece','kg','meter','service')", name='ck_market_listing_unit'),
    )
    op.create_index('idx_market_listing_feed', 'market_listings', ['published', 'created_at', 'id'])
    op.create_index('idx_market_listing_merchant', 'market_listings', ['merchant_id', 'id'])

    op.create_table('market_quotes',
        sa.Column('id', sa.String(32), primary_key=True, nullable=False),
        sa.Column('buyer_merchant_id', sa.String(32), sa.ForeignKey('merchants.id'), nullable=False),
        sa.Column('seller_merchant_id', sa.String(32), sa.ForeignKey('merchants.id'), nullable=False),
        sa.Column('listing_id', sa.String(32), sa.ForeignKey('market_listings.id'), nullable=False),
        sa.Column('listing_name', sa.String(120), nullable=False),
        sa.Column('unit', sa.String(16), nullable=False),
        sa.Column('quantity_milli', sa.BigInteger(), nullable=False),
        sa.Column('unit_price_minor', sa.BigInteger(), nullable=True),
        sa.Column('delivery_fee_minor', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('total_minor', sa.BigInteger(), nullable=True),
        sa.Column('message', sa.String(1000), nullable=False, server_default=''),
        sa.Column('seller_message', sa.String(1000), nullable=False, server_default=''),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('order_id', sa.String(32), nullable=True),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('updated_at', sa.BigInteger(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False, server_default='1'),
        sa.CheckConstraint('delivery_fee_minor >= 0 AND delivery_fee_minor <= 100000000', name='ck_market_quote_delivery'),
        sa.CheckConstraint('buyer_merchant_id <> seller_merchant_id', name='ck_market_quote_parties'),
        sa.CheckConstraint('unit_price_minor > 0 AND unit_price_minor <= 100000000', name='ck_market_quote_price'),
        sa.CheckConstraint('quantity_milli > 0 AND quantity_milli <= 1000000000000', name='ck_market_quote_quantity'),
        sa.CheckConstraint('revision >= 1', name='ck_market_quote_revision'),
        sa.CheckConstraint("status IN ('REQUESTED','QUOTED','ACCEPTED','REJECTED','CANCELLED')", name='ck_market_quote_status'),
        sa.CheckConstraint('total_minor > 0 AND total_minor <= 100000000', name='ck_market_quote_total'),
        sa.CheckConstraint("unit IN ('piece','kg','meter','service')", name='ck_market_quote_unit'),
    )
    op.create_index('idx_market_quote_buyer', 'market_quotes', ['buyer_merchant_id', 'created_at', 'id'])
    op.create_index('idx_market_quote_seller', 'market_quotes', ['seller_merchant_id', 'created_at', 'id'])

    op.create_table('market_orders',
        sa.Column('id', sa.String(32), primary_key=True, nullable=False),
        sa.Column('buyer_merchant_id', sa.String(32), sa.ForeignKey('merchants.id'), nullable=False),
        sa.Column('seller_merchant_id', sa.String(32), sa.ForeignKey('merchants.id'), nullable=False),
        sa.Column('listing_id', sa.String(32), sa.ForeignKey('market_listings.id'), nullable=False),
        sa.Column('quote_id', sa.String(32), sa.ForeignKey('market_quotes.id'), nullable=True),
        sa.Column('listing_name', sa.String(120), nullable=False),
        sa.Column('unit', sa.String(16), nullable=False),
        sa.Column('quantity_milli', sa.BigInteger(), nullable=False),
        sa.Column('unit_price_minor', sa.BigInteger(), nullable=False),
        sa.Column('delivery_fee_minor', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('total_minor', sa.BigInteger(), nullable=False),
        sa.Column('notes', sa.String(1000), nullable=False, server_default=''),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('request_key', sa.String(32), nullable=False),
        sa.Column('request_sha256', sa.String(64), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('updated_at', sa.BigInteger(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False, server_default='1'),
        sa.CheckConstraint('delivery_fee_minor >= 0 AND delivery_fee_minor <= 100000000', name='ck_market_order_delivery'),
        sa.CheckConstraint('buyer_merchant_id <> seller_merchant_id', name='ck_market_order_parties'),
        sa.CheckConstraint('unit_price_minor > 0 AND unit_price_minor <= 100000000', name='ck_market_order_price'),
        sa.CheckConstraint('quantity_milli > 0 AND quantity_milli <= 1000000000000', name='ck_market_order_quantity'),
        sa.CheckConstraint('revision >= 1', name='ck_market_order_revision'),
        sa.CheckConstraint("status IN ('REQUESTED','ACCEPTED','PREPARED','SHIPPED','RECEIVED','REJECTED','CANCELLED')", name='ck_market_order_status'),
        sa.CheckConstraint('total_minor > 0 AND total_minor <= 100000000', name='ck_market_order_total'),
        sa.CheckConstraint("unit IN ('piece','kg','meter','service')", name='ck_market_order_unit'),
        sa.UniqueConstraint('quote_id', name='uq_market_order_quote'),
        sa.UniqueConstraint('buyer_merchant_id', 'request_key', name='uq_market_order_request'),
    )
    op.create_index('idx_market_order_buyer', 'market_orders', ['buyer_merchant_id', 'created_at', 'id'])
    op.create_index('idx_market_order_seller', 'market_orders', ['seller_merchant_id', 'created_at', 'id'])

    op.create_table('market_freights',
        sa.Column('id', sa.String(32), primary_key=True, nullable=False),
        sa.Column('order_id', sa.String(32), sa.ForeignKey('market_orders.id'), nullable=False),
        sa.Column('carrier_merchant_id', sa.String(32), sa.ForeignKey('merchants.id'), nullable=False),
        sa.Column('fee_minor', sa.BigInteger(), nullable=False),
        sa.Column('notes', sa.String(1000), nullable=False, server_default=''),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('updated_at', sa.BigInteger(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False, server_default='1'),
        sa.CheckConstraint('fee_minor >= 0 AND fee_minor <= 100000000', name='ck_market_freight_fee'),
        sa.CheckConstraint('revision >= 1', name='ck_market_freight_revision'),
        sa.CheckConstraint("status IN ('PROPOSED','ACCEPTED','DELIVERED')", name='ck_market_freight_status'),
        sa.UniqueConstraint('order_id', name='uq_market_freight_order'),
    )
    op.create_index('idx_market_freight_carrier', 'market_freights', ['carrier_merchant_id', 'created_at', 'id'])


def downgrade():
    bind = op.get_bind()
    tables = ('market_profiles', 'market_listings', 'market_quotes', 'market_orders', 'market_freights')
    # Check every table before the first destructive operation.
    for table in tables:
        if bind.execute(sa.text('SELECT 1 FROM '+table+' LIMIT 1')).first() is not None:
            raise RuntimeError('Refusing to discard production marketplace records. Roll back application code instead.')
    op.drop_index('idx_market_freight_carrier', table_name='market_freights')
    op.drop_table('market_freights')
    op.drop_index('idx_market_order_seller', table_name='market_orders')
    op.drop_index('idx_market_order_buyer', table_name='market_orders')
    op.drop_table('market_orders')
    op.drop_index('idx_market_quote_seller', table_name='market_quotes')
    op.drop_index('idx_market_quote_buyer', table_name='market_quotes')
    op.drop_table('market_quotes')
    op.drop_index('idx_market_listing_merchant', table_name='market_listings')
    op.drop_index('idx_market_listing_feed', table_name='market_listings')
    op.drop_table('market_listings')
    op.drop_index('idx_market_profile_locality', table_name='market_profiles')
    op.drop_table('market_profiles')
