"""Retain minimal signature evidence for future verified webhook deliveries."""
from alembic import op
import sqlalchemy as sa

revision = '011'
down_revision = '010'


def upgrade():
    for table in ('payment_events', 'pending_payment_events'):
        op.add_column(table, sa.Column('signature', sa.String(47), nullable=True))
        op.add_column(table, sa.Column('signature_timestamp', sa.BigInteger(), nullable=True))
        op.add_column(table, sa.Column('signature_received_at', sa.BigInteger(), nullable=True))
        op.add_column(table, sa.Column('signature_key_ref', sa.String(64), nullable=True))
    op.add_column('reconciliation_reviews', sa.Column('signature_assessment', sa.String(32), nullable=True))


def downgrade():
    connection = op.get_bind()
    if connection.dialect.name == 'postgresql':
        connection.exec_driver_sql('LOCK TABLE payment_events, pending_payment_events, reconciliation_reviews IN ACCESS EXCLUSIVE MODE')
    elif connection.dialect.name == 'sqlite':
        connection.exec_driver_sql('BEGIN IMMEDIATE')
    else:
        raise RuntimeError('Signature evidence requires SQLite or PostgreSQL')
    for table in ('payment_events', 'pending_payment_events'):
        if connection.execute(sa.text(f'SELECT 1 FROM {table} WHERE signature IS NOT NULL OR '
                                      'signature_timestamp IS NOT NULL OR signature_received_at IS NOT NULL OR '
                                      'signature_key_ref IS NOT NULL LIMIT 1')).first() is not None:
            raise RuntimeError('Refusing to discard stored webhook signature evidence')
    if connection.execute(sa.text('SELECT 1 FROM reconciliation_reviews WHERE signature_assessment IS NOT NULL LIMIT 1')).first() is not None:
        raise RuntimeError('Refusing to discard recorded signature assessments')
    op.drop_column('reconciliation_reviews', 'signature_assessment')
    for table in ('pending_payment_events', 'payment_events'):
        for column in ('signature_key_ref', 'signature_received_at', 'signature_timestamp', 'signature'):
            op.drop_column(table, column)
