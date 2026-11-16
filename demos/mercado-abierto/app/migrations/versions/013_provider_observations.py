"""Record minimized append-only read-only provider account observations."""
from alembic import op
import sqlalchemy as sa
from rio_pey_codi.provider_observation_schema import (
    drop_provider_observation_guard_function, install_provider_observation_guards,
)

revision = '013'
down_revision = '012'


def upgrade():
    op.create_table('provider_account_observations',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('merchant_id', sa.String(32), sa.ForeignKey('merchants.id'), nullable=False),
        sa.Column('claim_id', sa.String(32), sa.ForeignKey('beneficiary_claims.id'), nullable=False),
        sa.Column('actor_id', sa.String(32), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('request_id', sa.String(32), nullable=False),
        sa.Column('sequence', sa.BigInteger(), nullable=False),
        sa.Column('credential_ref', sa.String(32), nullable=False),
        sa.Column('status', sa.String(12), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.UniqueConstraint('merchant_id', 'request_id'),
        sa.UniqueConstraint('merchant_id', 'sequence'),
        sa.CheckConstraint('sequence > 0'),
        sa.CheckConstraint("status IN ('ACTIVE','PENDING','PROCESSING','ERROR','NOT_FOUND')"))
    op.create_index('idx_provider_observation_merchant_sequence', 'provider_account_observations',
                    ['merchant_id', 'sequence'])
    install_provider_observation_guards(op.get_bind())


def downgrade():
    connection = op.get_bind()
    if connection.dialect.name == 'postgresql':
        connection.exec_driver_sql('LOCK TABLE provider_account_observations IN ACCESS EXCLUSIVE MODE')
    elif connection.dialect.name == 'sqlite':
        connection.exec_driver_sql('BEGIN IMMEDIATE')
    else:
        raise RuntimeError('Provider observations require SQLite or PostgreSQL')
    if connection.execute(sa.text('SELECT 1 FROM provider_account_observations LIMIT 1')).first() is not None:
        raise RuntimeError('Refusing to discard provider observations')
    op.drop_index('idx_provider_observation_merchant_sequence', table_name='provider_account_observations')
    op.drop_table('provider_account_observations')
    drop_provider_observation_guard_function(connection)
