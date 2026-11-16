"""Hosted Neon connections retain verified TLS with a bundled CA file."""
import pytest
from sqlalchemy import create_engine as real_create_engine

import rio_pey_codi.models as models


BASE = 'postgresql+psycopg://synthetic:synthetic@demo-pooler.region.aws.neon.tech/rio_fintech'


def test_hosted_neon_uses_bundled_ca_without_weakening_tls(tmp_path, monkeypatch):
    import certifi

    bundle = tmp_path / 'ca.pem'
    bundle.write_text('synthetic CA placeholder')
    monkeypatch.setattr(certifi, 'where', lambda: str(bundle))
    monkeypatch.setenv('VERCEL', '1')
    observed = {}
    engine = real_create_engine('sqlite+pysqlite:///:memory:')

    def fake_engine(url, **kwargs):
        observed.update(url=url, kwargs=kwargs)
        return engine

    monkeypatch.setattr(models, 'create_engine', fake_engine)
    factory = models.database(BASE + '?sslmode=verify-full&sslrootcert=system&channel_binding=require')
    assert observed['kwargs']['connect_args']['sslrootcert'] == str(bundle)
    assert 'sslmode=verify-full' in observed['url']
    assert 'channel_binding=require' in observed['url']
    factory.kw['bind'].dispose()


def test_bundled_ca_overrides_url_in_effective_psycopg_connection(tmp_path, monkeypatch):
    import certifi
    import psycopg

    bundle = tmp_path / 'ca.pem'
    bundle.write_text('synthetic CA placeholder')
    monkeypatch.setattr(certifi, 'where', lambda: str(bundle))
    monkeypatch.setenv('VERCEL', '1')
    observed = {}

    class StopConnection(Exception):
        pass

    def fake_connect(*_args, **kwargs):
        observed.update(kwargs)
        raise StopConnection()

    monkeypatch.setattr(psycopg, 'connect', fake_connect)
    factory = models.database(BASE + '?sslmode=verify-full&sslrootcert=system&channel_binding=require')
    with pytest.raises(StopConnection):
        factory.kw['bind'].connect()
    assert observed['sslrootcert'] == str(bundle)
    assert observed['sslmode'] == 'verify-full'
    assert observed['channel_binding'] == 'require'
    factory.kw['bind'].dispose()


def test_hosted_neon_fails_closed_if_bundled_ca_is_missing(tmp_path, monkeypatch):
    import certifi

    monkeypatch.setattr(certifi, 'where', lambda: str(tmp_path / 'missing-ca.pem'))
    monkeypatch.setenv('VERCEL', '1')
    with pytest.raises(ValueError, match='Trusted CA bundle unavailable'):
        models.database(BASE + '?sslmode=verify-full&sslrootcert=system&channel_binding=require')


@pytest.mark.parametrize('query', [
    'sslmode=require&sslrootcert=system&channel_binding=require',
    'sslmode=verify-full&sslrootcert=system&channel_binding=prefer',
    'sslmode=verify-full&sslrootcert=system',
])
def test_hosted_neon_rejects_weaker_tls_with_system_root(monkeypatch, query):
    monkeypatch.setenv('VERCEL', '1')
    with pytest.raises(ValueError, match='verified TLS'):
        models.database(BASE + '?' + query)


def test_non_neon_database_does_not_override_the_explicit_ca(monkeypatch):
    monkeypatch.setenv('VERCEL', '1')
    observed = {}
    engine = real_create_engine('sqlite+pysqlite:///:memory:')

    def fake_engine(url, **kwargs):
        observed.update(url=url, kwargs=kwargs)
        return engine

    monkeypatch.setattr(models, 'create_engine', fake_engine)
    url = 'postgresql+psycopg://synthetic:synthetic@db.example.org/db?sslrootcert=system'
    factory = models.database(url)
    assert 'sslrootcert' not in observed['kwargs']['connect_args']
    factory.kw['bind'].dispose()
