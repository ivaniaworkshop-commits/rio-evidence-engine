"""Persistent immutable cash declarations for authenticated merchant members."""
from alembic import op
import sqlalchemy as sa

revision = '020'
down_revision = '019'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('cash_sales',
        sa.Column('merchant_id', sa.String(32), sa.ForeignKey('merchants.id'), primary_key=True),
        sa.Column('id', sa.String(41), primary_key=True),
        sa.Column('actor_id', sa.String(32), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('folio', sa.String(70)),
        sa.Column('amount_minor', sa.BigInteger(), nullable=False),
        sa.Column('received_minor', sa.BigInteger(), nullable=False),
        sa.Column('change_minor', sa.BigInteger(), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=False),
        sa.Column('payload_sha256', sa.String(64), nullable=False),
        sa.Column('recorded_at', sa.BigInteger(), nullable=False),
        sa.UniqueConstraint('merchant_id', 'folio', name='uq_cash_sale_folio'),
        sa.CheckConstraint('amount_minor > 0 AND amount_minor <= 100000000', name='ck_cash_sale_amount'),
        sa.CheckConstraint('received_minor >= amount_minor AND received_minor <= 100000000', name='ck_cash_sale_received'),
        sa.CheckConstraint('change_minor = received_minor - amount_minor', name='ck_cash_sale_change'))
    op.create_index('idx_cash_sales_merchant_time', 'cash_sales', ['merchant_id', 'recorded_at', 'id'])
    from rio_pey_codi.cash_ledger_models import install_cash_guards
    install_cash_guards(op.get_bind())


def downgrade():
    db = op.get_bind()
    if db.execute(sa.text('SELECT 1 FROM cash_sales LIMIT 1')).first():
        raise RuntimeError('Refusing to discard cash records. Roll back application code instead.')
    op.drop_index('idx_cash_sales_merchant_time', table_name='cash_sales')
    op.drop_table('cash_sales')
    if db.dialect.name == 'postgresql':
        db.execute(sa.text('DROP FUNCTION IF EXISTS mercado_cash_immutable()'))
