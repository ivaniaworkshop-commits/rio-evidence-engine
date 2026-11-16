"""Encrypted merchant-specific pey settings."""
from alembic import op
import sqlalchemy as sa
revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('merchant_pey_secrets',
        sa.Column('merchant_id', sa.String(32), sa.ForeignKey('merchants.id'), primary_key=True),
        sa.Column('api_key', sa.LargeBinary(), nullable=True),
        sa.Column('webhook_secret', sa.LargeBinary(), nullable=True),
        sa.Column('bank_account_id', sa.LargeBinary(), nullable=True),
        sa.Column('updated_at', sa.BigInteger(), nullable=False))

def downgrade():
    if op.get_bind().execute(sa.text('SELECT 1 FROM merchant_pey_secrets LIMIT 1')).first():
        raise RuntimeError('Refusing to delete merchant pey credentials')
    op.drop_table('merchant_pey_secrets')
