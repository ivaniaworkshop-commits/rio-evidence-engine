from fastapi.testclient import TestClient

from rio_pey_codi.platform import Settings, create_platform


def test_local_demo_can_open_login_without_postgresql(tmp_path):
    app = create_platform(Settings(database_url='sqlite+pysqlite:///' + str(tmp_path / 'local.sqlite3')))
    client = TestClient(app)
    status = client.get('/public-status').json()
    health = client.get('/healthz').json()
    assert status['access_enabled'] is True
    assert status['registration_enabled'] is True
    assert status['database_readiness'] == 'LOCAL_NOT_CHECKED'
    assert status['database_failure'] is None
    assert status['mode'] == 'DEMO'
    assert status['live_payments_enabled'] is False
    assert status == health
