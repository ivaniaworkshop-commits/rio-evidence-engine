"""Credential versions, scoped incoming events, and provider readback."""
from alembic import op
import sqlalchemy as sa

revision = '016'
down_revision = '015'
branch_labels = None
depends_on = None


def upgrade():
    credential = 'merchant_pey_credentials.ref'
    op.create_table(
        'merchant_pey_credentials',
        sa.Column('ref', sa.String(32), primary_key=True),
        sa.Column('merchant_id', sa.String(32), sa.ForeignKey('merchants.id'), nullable=False),
        sa.Column('api_key_id', sa.String(26)),
        sa.Column('api_key', sa.LargeBinary(), nullable=False),
        sa.Column('webhook_secret', sa.LargeBinary(), nullable=False),
        sa.Column('bank_account_id', sa.LargeBinary()),
        sa.Column('checked_at', sa.BigInteger(), nullable=False),
    )
    with op.batch_alter_table('merchant_pey_secrets') as table:
        table.add_column(sa.Column('api_key_id', sa.String(26)))
        table.add_column(sa.Column('active_credential_ref', sa.String(32), sa.ForeignKey(
            credential, name='fk_pey_settings_active_credential')))
    with op.batch_alter_table('payment_intents') as table:
        table.add_column(sa.Column('pey_credential_ref', sa.String(32), sa.ForeignKey(
            credential, name='fk_pey_intent_credential')))
        table.add_column(sa.Column('provider_payment_source', sa.String(32)))
        table.add_column(sa.Column('provider_payment_observed_at', sa.BigInteger()))
        table.add_column(sa.Column('provider_payment_sha256', sa.String(64)))
    with op.batch_alter_table('pending_payment_events') as table:
        table.add_column(sa.Column('merchant_id', sa.String(32), sa.ForeignKey(
            'merchants.id', name='fk_pey_pending_merchant')))
        table.add_column(sa.Column('pey_credential_ref', sa.String(32), sa.ForeignKey(
            credential, name='fk_pey_pending_credential')))
        table.add_column(sa.Column('intent_id', sa.String(32), sa.ForeignKey(
            'payment_intents.id', name='fk_pey_pending_intent')))
        table.add_column(sa.Column('provider_verified', sa.Boolean(), server_default=sa.false(), nullable=False))
        table.add_column(sa.Column('provider_payment_sha256', sa.String(64)))


def downgrade():
    db = op.get_bind()
    if db.dialect.name == 'sqlite':
        db.exec_driver_sql('BEGIN IMMEDIATE')
    elif db.dialect.name == 'postgresql':
        db.exec_driver_sql('LOCK TABLE merchant_pey_credentials, merchant_pey_secrets, '
                           'payment_intents, pending_payment_events IN ACCESS EXCLUSIVE MODE')
    if db.execute(sa.text('SELECT 1 FROM merchant_pey_credentials LIMIT 1')).first() or db.execute(
            sa.text('SELECT 1 FROM merchant_pey_secrets WHERE api_key_id IS NOT NULL LIMIT 1')).first():
        raise RuntimeError('Refusing to discard pey credential history. Roll back the application instead.')
    if db.execute(sa.text('SELECT 1 FROM payment_intents WHERE pey_credential_ref IS NOT NULL OR '
                          'provider_payment_source IS NOT NULL OR provider_payment_observed_at IS NOT NULL OR '
                          'provider_payment_sha256 IS NOT NULL LIMIT 1')).first() or db.execute(sa.text(
            'SELECT 1 FROM pending_payment_events WHERE merchant_id IS NOT NULL OR '
            'pey_credential_ref IS NOT NULL OR intent_id IS NOT NULL OR provider_verified = true OR '
            'provider_payment_sha256 IS NOT NULL LIMIT 1')).first():
        raise RuntimeError('Refusing to discard pey payment evidence. Roll back the application instead.')
    # SQLite rebuilds payment_intents for these column removals. Referencing
    # evidence prevents that rebuild; reject before any table has been altered.
    if db.dialect.name == 'sqlite':
        review = db.execute(sa.text('SELECT account_assessment, owner_claim_id, signature_assessment '
                                    'FROM reconciliation_reviews LIMIT 1')).first()
        if review is not None:
            if review.account_assessment is not None or review.owner_claim_id is not None:
                raise RuntimeError('Refusing to discard account comparison evidence')
            if review.signature_assessment is not None:
                raise RuntimeError('Refusing to discard recorded signature assessments')
            raise RuntimeError('Refusing to remove reconciliation reviews with recorded data')
        event = db.execute(sa.text('SELECT 1 FROM payment_events WHERE intent_id IS NOT NULL LIMIT 1')).first()
        if event is not None:
            if db.execute(sa.text('SELECT 1 FROM payment_events WHERE signature IS NOT NULL OR '
                                  'signature_timestamp IS NOT NULL OR signature_received_at IS NOT NULL OR '
                                  'signature_key_ref IS NOT NULL LIMIT 1')).first():
                raise RuntimeError('Refusing to discard stored webhook signature evidence')
            raise RuntimeError('Refusing to rebuild payment intents with recorded events')
    with op.batch_alter_table('pending_payment_events') as table:
        for constraint in ('fk_pey_pending_intent', 'fk_pey_pending_credential', 'fk_pey_pending_merchant'):
            table.drop_constraint(constraint, type_='foreignkey')
        for column in ('provider_payment_sha256', 'provider_verified', 'intent_id', 'pey_credential_ref', 'merchant_id'):
            table.drop_column(column)
    with op.batch_alter_table('payment_intents') as table:
        table.drop_constraint('fk_pey_intent_credential', type_='foreignkey')
        for column in ('provider_payment_sha256', 'provider_payment_observed_at', 'provider_payment_source', 'pey_credential_ref'):
            table.drop_column(column)
    with op.batch_alter_table('merchant_pey_secrets') as table:
        table.drop_constraint('fk_pey_settings_active_credential', type_='foreignkey')
        table.drop_column('active_credential_ref')
        table.drop_column('api_key_id')
    op.drop_table('merchant_pey_credentials')
