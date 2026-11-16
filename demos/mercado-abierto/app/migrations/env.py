import os

from alembic import context
from rio_pey_codi.models import Base, database
from rio_pey_codi.commerce_state import DemoCommercialState  # register metadata
from rio_pey_codi import production_market_models, cash_ledger_models, pey_operations_models  # production metadata
from rio_pey_codi import verification_tasks  # owner verification queue metadata

if context.is_offline_mode():
    context.configure(dialect_name="postgresql", target_metadata=Base.metadata,
                      literal_binds=True, transactional_ddl=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = database(os.environ["DATABASE_URL"]).kw["bind"]
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
