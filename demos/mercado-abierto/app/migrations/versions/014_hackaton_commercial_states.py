"""R017 — Account-scoped DEMO commercial snapshots; migration, not live payment data.

Revision 014 follows verified historical head 013. Downgrade refuses nonempty
snapshot data. Explicit storage cap enforced by API, not schema.
"""
from alembic import op
import sqlalchemy as sa

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "hackaton_commercial_states",
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("state_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_hackaton_commercial_revision_positive"),
    )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name not in ("sqlite", "postgresql"):
        raise RuntimeError("Unsupported migration dialect")
    present = bind.execute(sa.text("SELECT 1 FROM hackaton_commercial_states LIMIT 1")).first()
    if present is not None:
        raise RuntimeError("Refusing to delete persisted DEMO commercial snapshots")
    op.drop_table("hackaton_commercial_states")
