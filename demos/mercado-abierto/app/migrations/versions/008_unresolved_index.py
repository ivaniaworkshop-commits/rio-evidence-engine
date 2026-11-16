"""Index the merchant-scoped unresolved checkout queue."""
from alembic import op

revision = '008'
down_revision = '007'


def upgrade():
    op.create_index('idx_payment_intents_recovery', 'payment_intents',
                    ['merchant_id', 'status', 'created_at', 'id'], unique=False)


def downgrade():
    op.drop_index('idx_payment_intents_recovery', table_name='payment_intents')
