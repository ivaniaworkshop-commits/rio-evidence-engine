"""Additive production marketplace migration, disposable SQLite only."""
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from rio_pey_codi.production_market_models import (
    MarketProfile, MarketListing, MarketQuote, MarketOrder, MarketFreight)

MODELS = (MarketProfile, MarketListing, MarketQuote, MarketOrder, MarketFreight)
TABLES = {model.__tablename__ for model in MODELS}


@pytest.fixture
def schema(tmp_path, monkeypatch):
    url = 'sqlite+pysqlite:///' + str(tmp_path / 'market-migration.sqlite')
    monkeypatch.setenv('DATABASE_URL', url)
    cfg = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    command.upgrade(cfg, '018')
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(text("INSERT INTO users (id,email,password_hash,verified_at,created_at) VALUES ('fixture-user','market-migration@example.org','not-a-password',1,1)"))
        db.execute(text("INSERT INTO merchants (id,name,owner_id,created_at) VALUES ('fixture-merchant','Synthetic merchant','fixture-user',1)"))
        db.execute(text("INSERT INTO hackaton_commercial_states (user_id,revision,state_json,updated_at) VALUES ('fixture-user',1,:snapshot,1)"), {'snapshot':'{"historical":"not promoted","products":[{"id":"synthetic-seed"}]}'})
    return cfg, engine


def test_market_migration_is_additive_and_does_not_promote_demo_records(schema):
    cfg, engine = schema
    before = set(inspect(engine).get_table_names())
    with engine.connect() as db:
        original = db.execute(text('SELECT state_json FROM hackaton_commercial_states')).scalar_one()
    command.upgrade(cfg, '019')
    assert set(inspect(engine).get_table_names()) - before == TABLES
    with engine.connect() as db:
        assert db.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '019'
        assert db.execute(text('SELECT state_json FROM hackaton_commercial_states')).scalar_one() == original
        for table in TABLES:
            assert db.execute(text('SELECT count(*) FROM '+table)).scalar_one() == 0
    inspector = inspect(engine)
    for model in MODELS:
        table = model.__table__
        actual = {col['name']:col for col in inspector.get_columns(table.name)}
        expected_columns = {col.name for col in table.columns}
        post_019_columns = {
            'market_listings': {'seller_price_minor', 'platform_fee_minor', 'wholesale_discount_bps',
                'discounted_seller_price_minor', 'image_data', 'image_mime', 'image_sha256', 'qr_sha256'},
            'market_quotes': {'seller_unit_price_minor', 'platform_fee_minor', 'seller_delivery_fee_minor',
                'freight_platform_fee_minor'},
            'market_orders': {'seller_unit_price_minor', 'platform_fee_minor', 'seller_delivery_fee_minor',
                'freight_platform_fee_minor', 'cart_checkout_key', 'delivery_address_json'},
        }
        expected_columns -= post_019_columns.get(table.name, set())
        # This test deliberately stops at historical revision 019; later additive revisions
        # add WhatsApp and checkout columns.
        if table.name == 'market_profiles':
            expected_columns.remove('whatsapp_phone')
        assert set(actual) == expected_columns
        assert all(actual[col.name]['nullable'] == col.nullable for col in table.columns
                   if col.name in actual)
        assert {index['name'] for index in inspector.get_indexes(table.name)} == {index.name for index in table.indexes}
        actual_checks = {constraint['name']:constraint['sqltext'] for constraint in inspector.get_check_constraints(table.name)}
        expected_checks = {c.name:str(c.sqltext) for c in table.constraints if hasattr(c, 'sqltext')}
        expected_checks = {name:value for name,value in expected_checks.items() if name not in {
            'ck_market_listing_seller_price', 'ck_market_listing_platform_fee',
            'ck_market_listing_wholesale_discount', 'ck_market_listing_discounted_seller_price',
            'ck_market_quote_platform_fee', 'ck_market_quote_seller_delivery',
            'ck_market_quote_freight_platform_fee', 'ck_market_order_platform_fee',
            'ck_market_order_seller_delivery', 'ck_market_order_freight_platform_fee'}}
        assert actual_checks == expected_checks
    command.upgrade(cfg, '019')


def test_market_downgrade_checks_all_data_before_dropping_any_table(schema):
    cfg, engine = schema
    command.upgrade(cfg, '019')
    with engine.begin() as db:
        db.execute(text("INSERT INTO market_profiles (merchant_id,kind,alcaldia,colonia,created_at,updated_at) VALUES ('fixture-merchant','merchant','iztapalapa','Colonia sintética',1,1)"))
    with pytest.raises(RuntimeError, match='Refusing to discard production marketplace records'):
        command.downgrade(cfg, '018')
    assert TABLES.issubset(inspect(engine).get_table_names())
    with engine.connect() as db:
        assert db.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '019'
        assert db.execute(text('SELECT published FROM market_profiles')).scalar_one() == 0
        assert db.execute(text('SELECT count(*) FROM market_profiles')).scalar_one() == 1


def test_empty_market_downgrade_retains_existing_accounts_and_snapshots(schema):
    cfg, engine = schema
    command.upgrade(cfg, '019')
    command.downgrade(cfg, '018')
    assert TABLES.isdisjoint(inspect(engine).get_table_names())
    with engine.connect() as db:
        assert db.execute(text('SELECT count(*) FROM users')).scalar_one() == 1
        assert db.execute(text('SELECT count(*) FROM hackaton_commercial_states')).scalar_one() == 1


def test_whatsapp_migration_is_nullable_additive_and_refuses_to_drop_saved_contact(schema):
    cfg, engine = schema
    command.upgrade(cfg, '022')
    with engine.begin() as db:
        db.execute(text("INSERT INTO market_profiles (merchant_id,kind,alcaldia,colonia,created_at,updated_at) VALUES ('fixture-merchant','merchant','iztapalapa','Colonia sintética',1,1)"))
    command.upgrade(cfg, '023')
    with engine.connect() as db:
        assert db.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '023'
        assert db.execute(text('SELECT whatsapp_phone FROM market_profiles')).scalar_one() is None
    with engine.begin() as db:
        db.execute(text("UPDATE market_profiles SET whatsapp_phone='+525512345678' WHERE merchant_id='fixture-merchant'"))
    with pytest.raises(RuntimeError, match='Refusing to discard published WhatsApp contact numbers'):
        command.downgrade(cfg, '022')
    with engine.connect() as db:
        assert db.execute(text('SELECT whatsapp_phone FROM market_profiles')).scalar_one() == '+525512345678'
        assert db.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '023'
    with engine.begin() as db:
        db.execute(text("UPDATE market_profiles SET whatsapp_phone=NULL WHERE merchant_id='fixture-merchant'"))
    command.downgrade(cfg, '022')
    assert 'whatsapp_phone' not in {column['name'] for column in inspect(engine).get_columns('market_profiles')}


def test_database_rejects_forged_money_stock_unit_and_party_values(schema):
    cfg, engine = schema
    command.upgrade(cfg, '019')
    with engine.begin() as db:
        db.execute(text("INSERT INTO market_profiles (merchant_id,kind,alcaldia,colonia,created_at,updated_at) VALUES ('fixture-merchant','merchant','iztapalapa','Colonia sintética',1,1)"))
    for patch in ({'price':0}, {'stock':-1}, {'unit':'counterfeit'}):
        values={'price':100,'stock':1000,'unit':'piece',**patch}
        with pytest.raises(IntegrityError), engine.begin() as db:
            db.execute(text("INSERT INTO market_listings (id,merchant_id,name,category,unit,price_minor,stock_milli,created_at,updated_at) VALUES ('invalid-listing','fixture-merchant','Product','Food',:unit,:price,:stock,1,1)"), values)


def test_cart_and_delivery_migration_backfills_legacy_prices_and_preserves_seed_data(schema):
    cfg, engine = schema
    command.upgrade(cfg, '023')
    with engine.begin() as db:
        db.execute(text("INSERT INTO market_profiles (merchant_id,kind,alcaldia,colonia,created_at,updated_at) VALUES ('fixture-merchant','merchant','iztapalapa','Colonia sintética',1,1)"))
        db.execute(text("INSERT INTO market_listings (id,merchant_id,name,category,unit,price_minor,stock_milli,published,created_at,updated_at) VALUES ('legacy-listing','fixture-merchant','Producto legado','Abarrotes','piece',1000,5000,1,1,1)"))
        original = db.execute(text('SELECT state_json FROM hackaton_commercial_states')).scalar_one()
    command.upgrade(cfg, '024')
    new_tables = {'market_carts', 'market_cart_items', 'market_order_qrs', 'market_order_events',
        'market_order_items', 'market_delivery_addresses'}
    assert new_tables.issubset(inspect(engine).get_table_names())
    with engine.connect() as db:
        row = db.execute(text("SELECT seller_price_minor,platform_fee_minor,price_minor,qr_sha256 FROM market_listings WHERE id='legacy-listing'")).one()
        assert tuple(row[:3]) == (1000, 50, 1050)
        assert len(row.qr_sha256) == 64
        assert db.execute(text('SELECT state_json FROM hackaton_commercial_states')).scalar_one() == original
        assert db.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '024'
    with pytest.raises(RuntimeError, match='Refusing to discard marketplace photos, purchase QR identities, cart or order history'):
        command.downgrade(cfg, '023')
    with engine.connect() as db:
        assert db.execute(text("SELECT price_minor FROM market_listings WHERE id='legacy-listing'")).scalar_one() == 1050
        assert db.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '024'
