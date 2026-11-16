"""Durable bank registrations, push payments and payment links."""
from alembic import op
import sqlalchemy as sa
revision = '021'
down_revision = '020'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('pey_operations',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('merchant_id', sa.String(32), sa.ForeignKey('merchants.id'), nullable=False),
        sa.Column('actor_id', sa.String(32), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('credential_ref', sa.String(32), sa.ForeignKey('merchant_pey_credentials.ref'), nullable=False),
        sa.Column('kind', sa.String(16), nullable=False),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('state', sa.String(32), nullable=False),
        sa.Column('provider_id', sa.String(140)),
        sa.Column('intent_id', sa.String(32), sa.ForeignKey('payment_intents.id')),
        sa.Column('parent_id', sa.String(32), sa.ForeignKey('pey_operations.id')),
        sa.Column('amount_minor', sa.BigInteger()),
        sa.Column('account_id', sa.String(140)),
        sa.Column('result_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('observed_at', sa.BigInteger()),
        sa.UniqueConstraint('credential_ref', 'kind', 'provider_id', name='uq_pey_operation_provider'))
    op.create_index('idx_pey_operations_merchant', 'pey_operations', ['merchant_id', 'created_at', 'id'])


def downgrade():
    if op.get_bind().execute(sa.text('SELECT 1 FROM pey_operations LIMIT 1')).first():
        raise RuntimeError('Cannot discard provider operations')
    op.drop_index('idx_pey_operations_merchant', table_name='pey_operations')
    op.drop_table('pey_operations')
