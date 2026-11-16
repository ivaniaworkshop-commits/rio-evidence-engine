"""Atomic application tables; server-side SQLAlchemy transactions."""
import os
import time
import certifi
from sqlalchemy import (BigInteger, Boolean, CheckConstraint, Column, ForeignKey, Index,
                        Integer, LargeBinary, String, Text, UniqueConstraint, create_engine, event)
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.engine import make_url

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__='users'
    id=Column(String(32),primary_key=True)
    email=Column(String(254),unique=True,nullable=False)
    password_hash=Column(Text,nullable=False)
    verified_at=Column(BigInteger,nullable=True)
    created_at=Column(BigInteger,nullable=False)

class Merchant(Base):
    __tablename__='merchants'
    id=Column(String(32),primary_key=True)
    name=Column(String(120),nullable=False)
    owner_id=Column(String(32),ForeignKey('users.id'),nullable=False)
    created_at=Column(BigInteger,nullable=False)
    archived_at=Column(BigInteger,nullable=True)

class Membership(Base):
    __tablename__='memberships'
    merchant_id=Column(String(32),ForeignKey('merchants.id'),primary_key=True)
    user_id=Column(String(32),ForeignKey('users.id'),primary_key=True)
    role=Column(String(20),nullable=False)

class SessionRow(Base):
    __tablename__='app_sessions'
    token_hash=Column(String(64),primary_key=True)
    csrf_hash=Column(String(64),nullable=False)
    user_id=Column(String(32),ForeignKey('users.id'),nullable=False)
    created_at=Column(BigInteger,nullable=False)
    expires_at=Column(BigInteger,nullable=False)
    revoked_at=Column(BigInteger,nullable=True)
    __table_args__=(Index('idx_sessions_user','user_id'),)

class OneTimeToken(Base):
    __tablename__='one_time_tokens'
    token_hash=Column(String(64),primary_key=True)
    user_id=Column(String(32),ForeignKey('users.id'),nullable=False)
    purpose=Column(String(20),nullable=False)
    expires_at=Column(BigInteger,nullable=False)
    used_at=Column(BigInteger,nullable=True)

class AuthAttempt(Base):
    __tablename__='auth_attempts'
    id=Column(String(32),primary_key=True)
    identity_hash=Column(String(64),nullable=False)
    created_at=Column(BigInteger,nullable=False)
    __table_args__=(Index('idx_auth_attempts_key_time','identity_hash','created_at'),)

class Intent(Base):
    __tablename__='payment_intents'
    id=Column(String(32),primary_key=True)
    merchant_id=Column(String(32),ForeignKey('merchants.id'),nullable=False)
    order_id=Column(String(70),nullable=False)
    amount_minor=Column(BigInteger,nullable=False)
    concept=Column(String(140),nullable=False)
    numref=Column(String(40),nullable=False)
    expiration_s=Column(Integer,nullable=False)
    status=Column(String(32),nullable=False)
    provider_qr_id=Column(String(140),unique=True,nullable=True)
    qr_display=Column(Text,nullable=True)
    transaction_id=Column(String(140),unique=True,nullable=True)
    created_at=Column(BigInteger,nullable=False)
    pey_credential_ref=Column(String(32),ForeignKey('merchant_pey_credentials.ref'),nullable=True)
    provider_payment_source=Column(String(32),nullable=True)
    provider_payment_observed_at=Column(BigInteger,nullable=True)
    provider_payment_sha256=Column(String(64),nullable=True)
    __table_args__=(UniqueConstraint('merchant_id','order_id'),UniqueConstraint('merchant_id','numref'),
                    CheckConstraint('amount_minor>0'),
                    Index('idx_payment_intents_recovery', 'merchant_id', 'status', 'created_at', 'id'))

class Event(Base):
    __tablename__='payment_events'
    id=Column(String(140),primary_key=True)
    raw_body=Column(LargeBinary,nullable=True)
    sha256=Column(String(64),nullable=False)
    intent_id=Column(String(32),ForeignKey('payment_intents.id'),nullable=True)
    processed_at=Column(BigInteger,nullable=False)
    signature=Column(String(47),nullable=True)
    signature_timestamp=Column(BigInteger,nullable=True)
    signature_received_at=Column(BigInteger,nullable=True)
    signature_key_ref=Column(String(64),nullable=True)

class PendingEvent(Base):
    __tablename__='pending_payment_events'
    id=Column(String(140),primary_key=True)
    raw_body=Column(LargeBinary,nullable=True)
    sha256=Column(String(64),nullable=False)
    qr_id=Column(String(140),nullable=False)
    amount_minor=Column(BigInteger,nullable=False)
    numref=Column(String(40),nullable=False)
    transaction_id=Column(String(140),nullable=False)
    received_at=Column(BigInteger,nullable=False)
    signature=Column(String(47),nullable=True)
    signature_timestamp=Column(BigInteger,nullable=True)
    signature_received_at=Column(BigInteger,nullable=True)
    signature_key_ref=Column(String(64),nullable=True)
    merchant_id=Column(String(32),ForeignKey('merchants.id'),nullable=True)
    pey_credential_ref=Column(String(32),ForeignKey('merchant_pey_credentials.ref'),nullable=True)
    intent_id=Column(String(32),ForeignKey('payment_intents.id'),nullable=True)
    provider_verified=Column(Boolean,nullable=False,server_default='false')
    provider_payment_sha256=Column(String(64),nullable=True)
    __table_args__=(Index('idx_pending_qr_id','qr_id'),)


class ReconciliationReview(Base):
    __tablename__ = 'reconciliation_reviews'
    id = Column(String(32), primary_key=True)
    intent_id = Column(String(32), ForeignKey('payment_intents.id'), nullable=False)
    actor_id = Column(String(32), ForeignKey('users.id'), nullable=False)
    request_id = Column(String(32), nullable=False)
    classification = Column(String(64), nullable=False)
    bank_record_count = Column(Integer, nullable=False)
    provider_event_count = Column(Integer, nullable=False)
    event_ids_hashes_sha256 = Column(String(64), nullable=True)
    signature_assessment = Column(String(32), nullable=True)
    account_assessment = Column(String(32), nullable=True)
    owner_claim_id = Column(String(32), nullable=True)
    created_at = Column(BigInteger, nullable=False)
    __table_args__ = (
        UniqueConstraint('intent_id', 'request_id'),
        CheckConstraint('bank_record_count >= 0 AND bank_record_count <= 50'),
        CheckConstraint('provider_event_count >= 0 AND provider_event_count <= 101'),
        Index('idx_review_intent_created', 'intent_id', 'created_at', 'id'),
    )


@event.listens_for(ReconciliationReview.__table__, 'after_create')
def create_review_guards(_table, connection, **_kwargs):
    from .review_schema import install_review_guards
    install_review_guards(connection)


@event.listens_for(ReconciliationReview.__table__, 'after_drop')
def drop_review_guards(_table, connection, **_kwargs):
    from .review_schema import drop_review_guard_function
    drop_review_guard_function(connection)


def database(url, auto_create=False):
    if not url:
        raise ValueError('DATABASE_URL is required')
    if url.startswith('postgresql://'):
        url = 'postgresql+psycopg://' + url.removeprefix('postgresql://')
    kwargs={'pool_pre_ping':True}
    if url.startswith('postgresql+psycopg://'):
        kwargs.update(pool_timeout=10, connect_args={
            'connect_timeout': 5,
        })
        parsed = make_url(url)
        hosted = os.environ.get('VERCEL') == '1' or os.environ.get('VERCEL_ENV') in ('preview', 'production')
        if (hosted and parsed.host and parsed.host.endswith('.neon.tech')
                and parsed.query.get('sslrootcert') == 'system'):
            if parsed.query.get('sslmode') != 'verify-full' or parsed.query.get('channel_binding') != 'require':
                raise ValueError('Hosted Neon requires verified TLS and channel binding')
            bundle = certifi.where()
            if not os.path.isfile(bundle):
                raise ValueError('Trusted CA bundle unavailable')
            kwargs['connect_args']['sslrootcert'] = bundle
    if url.startswith('sqlite'):
        kwargs['connect_args']={'check_same_thread':False,'timeout':10}
    engine=create_engine(url,**kwargs)
    if engine.dialect.name=='postgresql':
        @event.listens_for(engine,'begin')
        def postgres_transaction_timeouts(connection):
            # SET LOCAL works with transaction-pooling proxies and cannot leak
            # these settings into another client's later transaction.
            connection.exec_driver_sql("SET LOCAL statement_timeout = '15s'")
            connection.exec_driver_sql("SET LOCAL lock_timeout = '5s'")
    if engine.dialect.name=='sqlite':
        @event.listens_for(engine,'connect')
        def sqlite_foreign_keys(dbapi_connection, connection_record):
            cursor=dbapi_connection.cursor()
            cursor.execute('PRAGMA foreign_keys=ON')
            cursor.close()
    if auto_create:
        Base.metadata.create_all(engine)
    return sessionmaker(engine,expire_on_commit=False)


class AuthLimit(Base):
    __tablename__ = 'auth_limits'
    key = Column(String(64), primary_key=True)
    window = Column(BigInteger, primary_key=True)
    attempts = Column(Integer, nullable=False)


class MembershipChange(Base):
    __tablename__ = 'membership_changes'
    id = Column(String(32), primary_key=True)
    merchant_id = Column(String(32), ForeignKey('merchants.id'), nullable=False)
    user_id = Column(String(32), ForeignKey('users.id'), nullable=False)
    actor_id = Column(String(32), ForeignKey('users.id'), nullable=False)
    previous_role = Column(String(20))
    new_role = Column(String(20), nullable=False)
    created_at = Column(BigInteger, nullable=False)


class Beneficiary(Base):
    __tablename__ = 'merchant_beneficiaries'
    merchant_id = Column(String(32), ForeignKey('merchants.id'), primary_key=True)
    consent_by = Column(String(32), ForeignKey('users.id'), nullable=False)
    consent_at = Column(BigInteger, nullable=False)
    provider_account_id = Column(String(26), unique=True)
    status = Column(String(12), nullable=False)
    __table_args__ = (
        CheckConstraint("status IN ('pending','processing','active','error','revoked')"),
        CheckConstraint("status <> 'active' OR provider_account_id IS NOT NULL"),
    )


class BeneficiaryClaim(Base):
    """An owner's assertion, never proof of provider status or account ownership."""
    __tablename__ = 'beneficiary_claims'
    id = Column(String(32), primary_key=True)
    merchant_id = Column(String(32), ForeignKey('merchants.id'), nullable=False)
    actor_id = Column(String(32), ForeignKey('users.id'), nullable=False)
    sequence = Column(BigInteger, nullable=False)
    request_id = Column(String(32), nullable=False)
    claim = Column(String(32), nullable=False)
    provider_account_id = Column(String(26), nullable=True)
    created_at = Column(BigInteger, nullable=False)
    __table_args__ = (
        UniqueConstraint('merchant_id', 'sequence'),
        UniqueConstraint('merchant_id', 'request_id'),
        CheckConstraint('sequence > 0'),
        CheckConstraint("claim IN ('OWNER_REPORTED_VERIFIED','OWNER_WITHDREW_REPORT')"),
        CheckConstraint("provider_account_id IS NULL OR length(provider_account_id) = 26"),
        CheckConstraint("claim <> 'OWNER_WITHDREW_REPORT' OR provider_account_id IS NULL"),
        Index('idx_beneficiary_claims_merchant_sequence', 'merchant_id', 'sequence'),
    )


@event.listens_for(BeneficiaryClaim.__table__, 'after_create')
def create_beneficiary_claim_guards(_table, connection, **_kwargs):
    from .beneficiary_schema import install_claim_guards
    install_claim_guards(connection)


@event.listens_for(BeneficiaryClaim.__table__, 'after_drop')
def drop_beneficiary_claim_guards(_table, connection, **_kwargs):
    from .beneficiary_schema import drop_claim_guard_function
    drop_claim_guard_function(connection)


class ProviderAccountObservation(Base):
    """A server's provider response, not proof of merchant or bank ownership."""
    __tablename__ = 'provider_account_observations'
    id = Column(String(32), primary_key=True)
    merchant_id = Column(String(32), ForeignKey('merchants.id'), nullable=False)
    claim_id = Column(String(32), ForeignKey('beneficiary_claims.id'), nullable=False)
    actor_id = Column(String(32), ForeignKey('users.id'), nullable=False)
    request_id = Column(String(32), nullable=False)
    sequence = Column(BigInteger, nullable=False)
    credential_ref = Column(String(32), nullable=False)
    status = Column(String(12), nullable=False)
    created_at = Column(BigInteger, nullable=False)
    __table_args__ = (
        UniqueConstraint('merchant_id', 'request_id'),
        UniqueConstraint('merchant_id', 'sequence'),
        CheckConstraint('sequence > 0'),
        CheckConstraint("status IN ('ACTIVE','PENDING','PROCESSING','ERROR','NOT_FOUND')"),
        Index('idx_provider_observation_merchant_sequence', 'merchant_id', 'sequence'),
    )


@event.listens_for(ProviderAccountObservation.__table__, 'after_create')
def create_provider_observation_guards(_table, connection, **_kwargs):
    from .provider_observation_schema import install_provider_observation_guards
    install_provider_observation_guards(connection)


@event.listens_for(ProviderAccountObservation.__table__, 'after_drop')
def drop_provider_observation_guards(_table, connection, **_kwargs):
    from .provider_observation_schema import drop_provider_observation_guard_function
    drop_provider_observation_guard_function(connection)


class MerchantPeySecret(Base):
    __tablename__ = 'merchant_pey_secrets'
    merchant_id = Column(String(32), ForeignKey('merchants.id'), primary_key=True)
    api_key = Column(LargeBinary, nullable=True)
    webhook_secret = Column(LargeBinary, nullable=True)
    bank_account_id = Column(LargeBinary, nullable=True)
    updated_at = Column(BigInteger, nullable=False)
    api_key_id = Column(String(26), nullable=True)
    active_credential_ref = Column(String(32), ForeignKey('merchant_pey_credentials.ref'), nullable=True)


class MerchantPeyCredential(Base):
    """A verified credential version retained for payments already issued."""

    __tablename__ = 'merchant_pey_credentials'
    ref = Column(String(32), primary_key=True)
    merchant_id = Column(String(32), ForeignKey('merchants.id'), nullable=False)
    api_key_id = Column(String(26), nullable=True)
    api_key = Column(LargeBinary, nullable=False)
    webhook_secret = Column(LargeBinary, nullable=False)
    bank_account_id = Column(LargeBinary, nullable=True)
    checked_at = Column(BigInteger, nullable=False)


class PaymentReceipt(Base):
    __tablename__ = 'payment_receipts'
    intent_id = Column(String(32), ForeignKey('payment_intents.id'), primary_key=True)
    public_id = Column(String(32), unique=True, nullable=False)
    payer_email = Column(String(254), nullable=True)
    enabled = Column(Boolean, nullable=False)
    created_at = Column(BigInteger, nullable=False)
    issued_at = Column(BigInteger, nullable=True)


class ReceiptDelivery(Base):
    __tablename__ = 'receipt_deliveries'
    receipt_id = Column(String(32), ForeignKey('payment_receipts.intent_id'), primary_key=True)
    recipient_role = Column(String(12), primary_key=True)
    recipient_email = Column(String(254), nullable=False)
    state = Column(String(16), nullable=False)
    sent_at = Column(BigInteger, nullable=True)


class ActivityEvent(Base):
    __tablename__ = 'app_activity_events'
    id = Column(String(32), primary_key=True)
    occurred_at = Column(BigInteger, nullable=False)
    event_type = Column(String(48), nullable=False)
    category = Column(String(16), nullable=False)
    outcome = Column(String(24), nullable=False)
    email = Column(String(254), nullable=True)
    reference = Column(String(32), nullable=True)
    detail_code = Column(String(48), nullable=True)
    source = Column(String(16), nullable=False)
    __table_args__ = (Index('idx_activity_time', 'occurred_at', 'id'),)


class VerificationTask(Base):
    """Owner-only queue for facts that still need independent readback."""
    __tablename__ = 'verification_tasks'
    id = Column(String(32), primary_key=True)
    task_key = Column(String(64), unique=True, nullable=False)
    domain = Column(String(24), nullable=False)
    priority = Column(String(8), nullable=False)
    title = Column(String(140), nullable=False)
    description = Column(Text, nullable=False)
    source_label = Column(String(120), nullable=False)
    source_url = Column(String(300), nullable=True)
    status = Column(String(16), nullable=False)
    evidence_reference = Column(String(160), nullable=True)
    note = Column(String(500), nullable=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)
    verified_at = Column(BigInteger, nullable=True)
    updated_by = Column(String(32), ForeignKey('users.id'), nullable=True)
    verified_by = Column(String(32), ForeignKey('users.id'), nullable=True)
    revision = Column(Integer, nullable=False, default=1)
    __table_args__ = (
        CheckConstraint("status IN ('PENDING','IN_PROGRESS','BLOCKED','VERIFIED')", name='ck_verification_task_status'),
        CheckConstraint("priority IN ('HIGH','NORMAL')", name='ck_verification_task_priority'),
        CheckConstraint('revision >= 1', name='ck_verification_task_revision'),
        Index('idx_verification_tasks_status_domain', 'status', 'domain', 'priority'),
    )
