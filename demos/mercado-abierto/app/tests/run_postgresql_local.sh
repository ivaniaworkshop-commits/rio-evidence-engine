#!/usr/bin/env bash
# Disposable, loopback-only PostgreSQL cluster for synthetic integration tests.
set -euo pipefail

cd "$(dirname "$0")/.."
python_bin="${RIO_TEST_PYTHON:-python3}"
pg_bin="$(pg_config --bindir)"
export PATH="$pg_bin:$PATH"
test_dir="$(mktemp -d /tmp/rio-postgres-test.XXXXXXXX)"

cleanup() {
    "$pg_bin/pg_ctl" -D "$test_dir/data" -m immediate stop >/dev/null 2>&1 || true
    rm -rf -- "$test_dir"
}
trap cleanup EXIT

mkdir -m 700 "$test_dir/socket"
port="$("$python_bin" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"
"$pg_bin/initdb" -D "$test_dir/data" --auth=trust --no-locale --encoding=UTF8 > "$test_dir/init.log"
"$pg_bin/pg_ctl" -D "$test_dir/data" -l "$test_dir/server.log" \
    -o "-k $test_dir/socket -h 127.0.0.1 -p $port" -w start
db_user="$(id -un)"
export RIO_TEST_POSTGRES_ADMIN_URL="postgresql://$db_user@127.0.0.1:$port/postgres"

"$python_bin" -m pytest -q

createdb -h 127.0.0.1 -p "$port" -U "$db_user" rio_test_restart
export DATABASE_URL="postgresql://$db_user@127.0.0.1:$port/rio_test_restart"
"$python_bin" -m alembic upgrade head
"$python_bin" - <<'PY'
import os
from rio_pey_codi.models import Merchant, User, database
from rio_pey_codi.payments_db import PaymentRepository

factory = database(os.environ['DATABASE_URL'])
with factory.begin() as db:
    db.add(User(id='a' * 32, email='restart@example.com', password_hash='fixture', created_at=1))
    db.flush()
    db.add(Merchant(id='b' * 32, name='Synthetic', owner_id='a' * 32, created_at=1))
repo = PaymentRepository(factory)
row, _ = repo.reserve('b' * 32, 'restart-order', 123, 'Demo', '99', 600)
repo.qr_issued(row.id, 'restart-qr', 'synthetic')
repo.confirm_event('restart-event', b'{"synthetic":true}', 'restart-qr', 123, '99', 'restart-tx')
factory.kw['bind'].dispose()
PY

"$pg_bin/pg_ctl" -D "$test_dir/data" -l "$test_dir/server.log" -m fast -w restart
"$python_bin" - <<'PY'
import os
from sqlalchemy import select
from rio_pey_codi.models import Event, Intent, database

factory = database(os.environ['DATABASE_URL'])
with factory() as db:
    row = db.scalar(select(Intent).where(Intent.order_id == 'restart-order'))
    event = db.get(Event, 'restart-event')
    assert row.status == 'PROVIDER_REPORTED'
    assert row.amount_minor == 123
    assert event.intent_id == row.id
    assert event.raw_body == b'{"synthetic":true}'
print('RESTART_READBACK_OK')
factory.kw['bind'].dispose()
PY
