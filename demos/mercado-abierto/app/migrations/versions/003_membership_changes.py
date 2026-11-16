"""Record changes to merchant permissions."""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"


def upgrade():
    op.create_table(
        "membership_changes",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("merchant_id", sa.String(32), sa.ForeignKey("merchants.id"), nullable=False),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("actor_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("previous_role", sa.String(20)),
        sa.Column("new_role", sa.String(20), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
    )


def downgrade():
    op.drop_table("membership_changes")
