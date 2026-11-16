"""R017 migration checks on disposable SQLite, never production."""
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from rio_pey_codi.platform import EXPECTED_SCHEMA_REVISION


@pytest.fixture
def migration_db(tmp_path,monkeypatch):
    url="sqlite+pysqlite:///"+str(tmp_path/"migration.sqlite")
    monkeypatch.setenv("DATABASE_URL",url)
    root=Path(__file__).resolve().parents[1]
    config=Config(str(root/"alembic.ini"))
    return url,config


def test_upgrade_from_historical_head_preserves_account_table(migration_db):
    url,cfg=migration_db
    command.upgrade(cfg,"013")
    engine=create_engine(url)
    before=set(inspect(engine).get_table_names())
    assert "users" in before
    assert "hackaton_commercial_states" not in before
    command.upgrade(cfg,"014")
    after=set(inspect(engine).get_table_names())
    assert after-before=={"hackaton_commercial_states"}
    cols={c["name"]:c for c in inspect(engine).get_columns("hackaton_commercial_states")}
    assert set(cols)=={"user_id","revision","state_json","updated_at"}
    with engine.connect() as c:
        assert c.execute(text("SELECT version_num FROM alembic_version")).scalar_one()=="014"
    command.upgrade(cfg,"head")
    with engine.connect() as c:
        assert c.execute(text("SELECT version_num FROM alembic_version")).scalar_one()==EXPECTED_SCHEMA_REVISION
    command.upgrade(cfg,"head")  # idempotent at the current head


def test_downgrade_empty_only_and_no_data_erasure(migration_db):
    url,cfg=migration_db
    command.upgrade(cfg,"014")
    engine=create_engine(url)
    # A nonempty commercial state must block removal.
    with engine.begin() as c:
        c.execute(text("INSERT INTO users (id,email,password_hash,verified_at,created_at) "
                       "VALUES ('U-R017','r017@example.org','not-a-real-login',1,1)"))
        c.execute(text("INSERT INTO hackaton_commercial_states "
                       "(user_id,revision,state_json,updated_at) VALUES "
                       "('U-R017',1,'{}',1)"))
    with pytest.raises(RuntimeError,match="Refusing to delete"):
        command.downgrade(cfg,"013")
    with engine.connect() as c:
        assert c.execute(text("SELECT revision FROM hackaton_commercial_states")).scalar_one()==1
    with engine.begin() as c:
        c.execute(text("DELETE FROM hackaton_commercial_states"))
    command.downgrade(cfg,"013")
    assert "hackaton_commercial_states" not in set(inspect(engine).get_table_names())
