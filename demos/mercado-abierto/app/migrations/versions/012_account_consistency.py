"""Record account comparisons and the owner assertion used at review time."""
from alembic import op
import sqlalchemy as sa

revision = '012'
down_revision = '011'


def upgrade():
    op.add_column('reconciliation_reviews', sa.Column('account_assessment', sa.String(32), nullable=True))
    op.add_column('reconciliation_reviews', sa.Column('owner_claim_id', sa.String(32), nullable=True))


def downgrade():
    connection = op.get_bind()
    if connection.dialect.name == 'postgresql':
        connection.exec_driver_sql('LOCK TABLE reconciliation_reviews IN ACCESS EXCLUSIVE MODE')
    elif connection.dialect.name == 'sqlite':
        connection.exec_driver_sql('BEGIN IMMEDIATE')
    else:
        raise RuntimeError('Account consistency evidence requires SQLite or PostgreSQL')
    if connection.execute(sa.text('SELECT 1 FROM reconciliation_reviews WHERE '
                                  'account_assessment IS NOT NULL OR owner_claim_id IS NOT NULL LIMIT 1')).first() is not None:
        raise RuntimeError('Refusing to discard account comparison evidence')
    op.drop_column('reconciliation_reviews', 'owner_claim_id')
    op.drop_column('reconciliation_reviews', 'account_assessment')
