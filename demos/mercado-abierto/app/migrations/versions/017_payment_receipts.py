"""Verifiable pey receipts and recipient delivery ledger."""
from alembic import op
import sqlalchemy as sa
revision = '017'
down_revision = '016'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('payment_receipts',
        sa.Column('intent_id',sa.String(32),sa.ForeignKey('payment_intents.id'),primary_key=True),
        sa.Column('public_id',sa.String(32),unique=True,nullable=False),
        sa.Column('payer_email',sa.String(254)),
        sa.Column('enabled',sa.Boolean(),nullable=False),
        sa.Column('created_at',sa.BigInteger(),nullable=False),
        sa.Column('issued_at',sa.BigInteger()))
    op.create_table('receipt_deliveries',
        sa.Column('receipt_id',sa.String(32),sa.ForeignKey('payment_receipts.intent_id'),primary_key=True),
        sa.Column('recipient_role',sa.String(12),primary_key=True),
        sa.Column('recipient_email',sa.String(254),nullable=False),
        sa.Column('state',sa.String(16),nullable=False),
        sa.Column('sent_at',sa.BigInteger()))


def downgrade():
    db=op.get_bind()
    if db.dialect.name == "sqlite" and not db.connection.driver_connection.in_transaction:
        db.exec_driver_sql("BEGIN IMMEDIATE")
    if db.execute(sa.text('SELECT 1 FROM payment_receipts LIMIT 1')).first():
        raise RuntimeError('Refusing to discard payment receipts. Roll back application code instead.')
    op.drop_table('receipt_deliveries')
    op.drop_table('payment_receipts')
