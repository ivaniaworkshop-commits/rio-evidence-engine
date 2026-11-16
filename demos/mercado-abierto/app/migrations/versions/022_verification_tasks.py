"""Persistent Ivania-only verification queue."""
from alembic import op
import sqlalchemy as sa

revision = '022'
down_revision = '021'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('verification_tasks',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('task_key', sa.String(64), nullable=False, unique=True),
        sa.Column('domain', sa.String(24), nullable=False),
        sa.Column('priority', sa.String(8), nullable=False),
        sa.Column('title', sa.String(140), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('source_label', sa.String(120), nullable=False),
        sa.Column('source_url', sa.String(300)),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('evidence_reference', sa.String(160)),
        sa.Column('note', sa.String(500)),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('updated_at', sa.BigInteger(), nullable=False),
        sa.Column('verified_at', sa.BigInteger()),
        sa.Column('updated_by', sa.String(32), sa.ForeignKey('users.id')),
        sa.Column('verified_by', sa.String(32), sa.ForeignKey('users.id')),
        sa.Column('revision', sa.Integer(), nullable=False, server_default='1'),
        sa.CheckConstraint("status IN ('PENDING','IN_PROGRESS','BLOCKED','VERIFIED')",
                           name='ck_verification_task_status'),
        sa.CheckConstraint("priority IN ('HIGH','NORMAL')", name='ck_verification_task_priority'),
        sa.CheckConstraint('revision >= 1', name='ck_verification_task_revision'))
    op.create_index('idx_verification_tasks_status_domain', 'verification_tasks',
                    ['status', 'domain', 'priority'])


def downgrade():
    db = op.get_bind()
    if db.execute(sa.text('SELECT 1 FROM verification_tasks LIMIT 1')).first():
        raise RuntimeError('Refusing to discard verification tasks and their evidence')
    op.drop_index('idx_verification_tasks_status_domain', table_name='verification_tasks')
    op.drop_table('verification_tasks')
