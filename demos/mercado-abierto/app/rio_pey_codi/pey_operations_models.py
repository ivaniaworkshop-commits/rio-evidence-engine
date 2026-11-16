"""Durable provider operations; ambiguous requests are never silently retried."""
from sqlalchemy import Column, String, Text, BigInteger, ForeignKey, UniqueConstraint, Index
from .models import Base


class PeyOperation(Base):
    __tablename__ = 'pey_operations'
    id = Column(String(32), primary_key=True)
    merchant_id = Column(String(32), ForeignKey('merchants.id'), nullable=False)
    actor_id = Column(String(32), ForeignKey('users.id'), nullable=False)
    credential_ref = Column(String(32), ForeignKey('merchant_pey_credentials.ref'), nullable=False)
    kind = Column(String(16), nullable=False)
    request_hash = Column(String(64), nullable=False)
    state = Column(String(32), nullable=False)
    provider_id = Column(String(140))
    intent_id = Column(String(32), ForeignKey('payment_intents.id'))
    parent_id = Column(String(32), ForeignKey('pey_operations.id'))
    amount_minor = Column(BigInteger)
    account_id = Column(String(140))
    result_json = Column(Text, nullable=False, default='{}')
    created_at = Column(BigInteger, nullable=False)
    observed_at = Column(BigInteger)
    __table_args__ = (Index('idx_pey_operations_merchant', 'merchant_id', 'created_at', 'id'),
        UniqueConstraint('credential_ref', 'kind', 'provider_id', name='uq_pey_operation_provider'))
