"""Store immutable, user-reported review results without bank input fields."""
from alembic import op
import sqlalchemy as sa

from rio_pey_codi.review_schema import drop_review_guard_function, install_review_guards

revision = '009'
down_revision = '008'


def upgrade():
    op.create_table(
        'reconciliation_reviews',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('intent_id', sa.String(32), sa.ForeignKey('payment_intents.id'), nullable=False),
        sa.Column('actor_id', sa.String(32), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('request_id', sa.String(32), nullable=False),
        sa.Column('classification', sa.String(64), nullable=False),
        sa.Column('bank_record_count', sa.Integer(), nullable=False),
        sa.Column('provider_event_count', sa.Integer(), nullable=False),
        sa.Column('event_ids_hashes_sha256', sa.String(64), nullable=True),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.UniqueConstraint('intent_id', 'request_id'),
        sa.CheckConstraint('bank_record_count >= 0 AND bank_record_count <= 50'),
        sa.CheckConstraint('provider_event_count >= 0 AND provider_event_count <= 101'),
    )
    op.create_index('idx_review_intent_created', 'reconciliation_reviews', ['intent_id', 'created_at', 'id'])
    install_review_guards(op.get_bind())


def downgrade():
    connection = op.get_bind()
    if connection.dialect.name == 'postgresql':
        connection.exec_driver_sql('LOCK TABLE reconciliation_reviews IN ACCESS EXCLUSIVE MODE')
    elif connection.dialect.name == 'sqlite':
        # Serialize the empty-table check and DROP against concurrent writers.
        # If an outer transaction prevents the lock, the downgrade fails closed.
        connection.exec_driver_sql('BEGIN IMMEDIATE')
    if connection.execute(sa.text('SELECT 1 FROM reconciliation_reviews LIMIT 1')).first() is not None:
        raise RuntimeError('Refusing to remove reconciliation reviews with recorded data')
    op.drop_index('idx_review_intent_created', table_name='reconciliation_reviews')
    op.drop_table('reconciliation_reviews')
    drop_review_guard_function(connection)
