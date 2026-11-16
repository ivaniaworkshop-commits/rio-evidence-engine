"""Owner operational log, including explicitly labelled account history."""
from alembic import op
import sqlalchemy as sa
revision='018'
down_revision='017'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('app_activity_events',
        sa.Column('id',sa.String(32),primary_key=True),sa.Column('occurred_at',sa.BigInteger(),nullable=False),
        sa.Column('event_type',sa.String(48),nullable=False),sa.Column('category',sa.String(16),nullable=False),
        sa.Column('outcome',sa.String(24),nullable=False),sa.Column('email',sa.String(254)),
        sa.Column('reference',sa.String(32)),sa.Column('detail_code',sa.String(48)),
        sa.Column('source',sa.String(16),nullable=False))
    op.create_index('idx_activity_time','app_activity_events',['occurred_at','id'])
    # Stored account timestamps are evidence of creation/verification, not mail delivery.
    dialect=op.get_bind().dialect.name
    if dialect=='postgresql':
        op.execute("INSERT INTO app_activity_events (id,occurred_at,event_type,category,outcome,email,reference,source) SELECT md5('created:'||id),created_at,'ACCOUNT_CREATED','accounts','CREATED',email,id,'HISTORICAL_STATE' FROM users")
        op.execute("INSERT INTO app_activity_events (id,occurred_at,event_type,category,outcome,email,reference,source) SELECT md5('verified:'||id),verified_at,'EMAIL_VERIFIED','verification','VERIFIED',email,id,'HISTORICAL_STATE' FROM users WHERE verified_at IS NOT NULL")
    else:
        import hashlib
        db=op.get_bind()
        for row in db.execute(sa.text('SELECT id,email,created_at,verified_at FROM users')).mappings():
            for prefix,event,category,outcome,stamp in [('created:','ACCOUNT_CREATED','accounts','CREATED',row['created_at']),('verified:','EMAIL_VERIFIED','verification','VERIFIED',row['verified_at'])]:
                if stamp is not None:
                    db.execute(sa.text('INSERT INTO app_activity_events (id,occurred_at,event_type,category,outcome,email,reference,source) VALUES (:id,:stamp,:event,:category,:outcome,:email,:ref,:source)'),dict(id=hashlib.md5((prefix+row['id']).encode()).hexdigest(),stamp=stamp,event=event,category=category,outcome=outcome,email=row['email'],ref=row['id'],source='HISTORICAL_STATE'))


def downgrade():
    if op.get_bind().execute(sa.text('SELECT 1 FROM app_activity_events LIMIT 1')).first():
        raise RuntimeError('Refusing to discard activity history. Roll back application code instead.')
    op.drop_index('idx_activity_time',table_name='app_activity_events')
    op.drop_table('app_activity_events')
