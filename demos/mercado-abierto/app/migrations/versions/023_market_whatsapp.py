"""Optional public WhatsApp contact for published business profiles."""
from alembic import op
import sqlalchemy as sa

revision = '023'
down_revision = '022'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('market_profiles', sa.Column('whatsapp_phone', sa.String(16), nullable=True))


def downgrade():
    db = op.get_bind()
    if db.execute(sa.text(
            "SELECT 1 FROM market_profiles WHERE whatsapp_phone IS NOT NULL LIMIT 1")).first():
        raise RuntimeError('Refusing to discard published WhatsApp contact numbers')
    op.drop_column('market_profiles', 'whatsapp_phone')
