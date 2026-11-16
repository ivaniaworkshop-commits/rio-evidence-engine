"""Immutable, merchant-scoped cash declarations persisted by the server."""
from sqlalchemy import BigInteger, CheckConstraint, Column, ForeignKey, Index, String, Text, UniqueConstraint, event, text
from .models import Base


class CashSale(Base):
    __tablename__ = 'cash_sales'
    merchant_id = Column(String(32), ForeignKey('merchants.id'), primary_key=True)
    id = Column(String(41), primary_key=True)
    actor_id = Column(String(32), ForeignKey('users.id'), nullable=False)
    folio = Column(String(70))
    amount_minor = Column(BigInteger, nullable=False)
    received_minor = Column(BigInteger, nullable=False)
    change_minor = Column(BigInteger, nullable=False)
    payload_json = Column(Text, nullable=False)
    payload_sha256 = Column(String(64), nullable=False)
    recorded_at = Column(BigInteger, nullable=False)
    __table_args__ = (
        UniqueConstraint('merchant_id', 'folio', name='uq_cash_sale_folio'),
        CheckConstraint('amount_minor > 0 AND amount_minor <= 100000000', name='ck_cash_sale_amount'),
        CheckConstraint('received_minor >= amount_minor AND received_minor <= 100000000', name='ck_cash_sale_received'),
        CheckConstraint('change_minor = received_minor - amount_minor', name='ck_cash_sale_change'),
        Index('idx_cash_sales_merchant_time', 'merchant_id', 'recorded_at', 'id'),
    )


def install_cash_guards(connection):
    if connection.dialect.name == 'sqlite':
        for action in ('UPDATE', 'DELETE'):
            connection.execute(text('CREATE TRIGGER mercado_cash_no_' + action.lower() +
                ' BEFORE ' + action + " ON cash_sales BEGIN SELECT RAISE(ABORT, 'cash sales are immutable'); END"))
    elif connection.dialect.name == 'postgresql':
        connection.execute(text("""CREATE FUNCTION mercado_cash_immutable() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'cash sales are immutable'; END; $$"""))
        connection.execute(text("""CREATE TRIGGER mercado_cash_no_mutation BEFORE UPDATE OR DELETE
            ON cash_sales FOR EACH ROW EXECUTE FUNCTION mercado_cash_immutable()"""))
    else:
        raise RuntimeError('Cash ledger requires PostgreSQL or SQLite')


@event.listens_for(CashSale.__table__, 'after_create')
def create_cash_guards(_table, connection, **_kwargs):
    install_cash_guards(connection)


@event.listens_for(CashSale.__table__, 'after_drop')
def drop_cash_function(_table, connection, **_kwargs):
    if connection.dialect.name == 'postgresql':
        connection.execute(text('DROP FUNCTION IF EXISTS mercado_cash_immutable()'))
