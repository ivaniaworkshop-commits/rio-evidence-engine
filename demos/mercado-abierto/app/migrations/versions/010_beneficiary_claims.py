"""Record owner reports without changing the provider's account status."""
from alembic import op
import sqlalchemy as sa

from rio_pey_codi.beneficiary_schema import drop_claim_guard_function, install_claim_guards

revision = '010'
down_revision = '009'


def upgrade():
    op.create_table(
        'beneficiary_claims',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('merchant_id', sa.String(32), sa.ForeignKey('merchants.id'), nullable=False),
        sa.Column('actor_id', sa.String(32), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('sequence', sa.BigInteger(), nullable=False),
        sa.Column('request_id', sa.String(32), nullable=False),
        sa.Column('claim', sa.String(32), nullable=False),
        sa.Column('provider_account_id', sa.String(26)),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.UniqueConstraint('merchant_id', 'sequence'),
        sa.UniqueConstraint('merchant_id', 'request_id'),
        sa.CheckConstraint('sequence > 0'),
        sa.CheckConstraint("claim IN ('OWNER_REPORTED_VERIFIED','OWNER_WITHDREW_REPORT')"),
        sa.CheckConstraint("provider_account_id IS NULL OR length(provider_account_id) = 26"),
        sa.CheckConstraint("claim <> 'OWNER_WITHDREW_REPORT' OR provider_account_id IS NULL"),
    )
    op.create_index('idx_beneficiary_claims_merchant_sequence', 'beneficiary_claims', ['merchant_id', 'sequence'])
    install_claim_guards(op.get_bind())


def downgrade():
    connection = op.get_bind()
    if connection.dialect.name == 'postgresql':
        connection.exec_driver_sql('LOCK TABLE beneficiary_claims IN ACCESS EXCLUSIVE MODE')
    elif connection.dialect.name == 'sqlite':
        connection.exec_driver_sql('BEGIN IMMEDIATE')
    if connection.execute(sa.text('SELECT 1 FROM beneficiary_claims LIMIT 1')).first() is not None:
        raise RuntimeError('Refusing to remove recorded beneficiary claims')
    op.drop_index('idx_beneficiary_claims_merchant_sequence', table_name='beneficiary_claims')
    op.drop_table('beneficiary_claims')
    drop_claim_guard_function(connection)
