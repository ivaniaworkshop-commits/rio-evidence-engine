import hashlib
import json
from html.parser import HTMLParser
from urllib.parse import urljoin

import pytest
from fastapi.testclient import TestClient

from rio_pey_codi.platform import Settings, create_platform


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.assets = []
        self.inline_scripts = 0
        self.inline_styles = 0

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'script':
            if 'src' in values:
                self.assets.append(values['src'])
            else:
                self.inline_scripts += 1
        if tag == 'style':
            self.inline_styles += 1
        if tag == 'link' and values.get('rel') == 'stylesheet':
            self.assets.append(values['href'])


@pytest.fixture()
def service(tmp_path):
    database = tmp_path / 'isolated.sqlite'
    app = create_platform(Settings(
        env='local', mode='DEMO', database_url='sqlite+pysqlite:///' + str(database),
        auto_create=True, email_mode='memory', public_url='http://testserver',
        origin='http://testserver',
    ))
    with TestClient(app) as client:
        yield app, client


def login_synthetic(app, client):
    signup = client.post('/v1/auth/signup', json={
        'email':'evaluacion@example.org', 'password':'RioDemo-2026-Local',
        'business_name':'Tienda sintética',
    })
    assert signup.status_code == 201
    assert client.post('/v1/auth/verify-email', json={'token':app.state.mailer.outbox[-1]['token']}).status_code == 200
    login = client.post('/v1/auth/login', json={'email':'evaluacion@example.org','password':'RioDemo-2026-Local'})
    assert login.status_code == 200
    csrf = login.json()['csrf_token']
    merchants = client.get('/v1/merchants').json()['merchants']
    assert len(merchants) == 1
    return csrf, merchants[0]['id']


@pytest.mark.parametrize('page', ['/', '/mercado-abierto', '/static/unificada/caja/index.html', '/static/unificada/mercado/index.html'])
def test_pages_and_assets_are_served_same_origin_with_csp(service, page):
    app, client = service
    login_synthetic(app, client)
    # Mercado is reserved for the pinned platform owner, even when an account
    # already owns its own businesses. Ordinary-owner denial has a dedicated test.
    if page == '/static/unificada/mercado/index.html':
        app.state.accounts.platform_owner_id = client.get('/api/auth/me').json()['user']['id']
    response = client.get(page)
    assert response.status_code == 200
    csp = response.headers['content-security-policy']
    assert "default-src 'self'" in csp and 'unsafe-inline' not in csp
    assert response.headers['x-frame-options'] == 'DENY'
    tree = Assets()
    tree.feed(response.text)
    assert tree.inline_scripts == 0 and tree.inline_styles == 0
    assert tree.assets
    for asset in tree.assets:
        target = urljoin('http://testserver' + page, asset)
        assert target.startswith('http://testserver/')
        assert client.get(target).status_code == 200, target
    navigation = (['data-workspace-view="menu"', 'data-workspace-view="caja"',
                   'data-workspace-view="historial"', 'data-workspace-view="negocios"',
                   'href="/mercado-abierto"', 'data-owner-area="market" hidden']
                  if page in ('/', '/static/unificada/caja/index.html') else
                  ['href="/#mis-negocios"', 'Mis negocios · cuenta pey', 'id="market-app"',
                   '/static/unificada/hackaton/production.js'])
    for link in navigation:
        assert link in response.text


def test_browsing_modules_creates_no_payment_or_provider_request(service):
    app, client = service
    _, merchant = login_synthetic(app, client)
    path = f'/v1/merchants/{merchant}/checkout-history'
    assert client.get(path).json()['intents'] == []
    assert client.get('/static/unificada/mercado/index.html').status_code == 403
    for page in ['/', '/mercado-abierto', '/static/unificada/caja/index.html']:
        assert client.get(page).status_code == 200
    assert client.get(path).json()['intents'] == []
    status = client.get('/public-status').json()
    assert status['mode'] == 'DEMO' and status['live_payments_enabled'] is False
    assert status['bank_settlement'] == 'NOT_OBSERVED'
    assert len(app.state.mailer.outbox) == 1  # sólo correo de verificación simulado en memoria


def test_explicit_local_checkout_is_mock_and_retains_identical_reference(service):
    app, client = service
    csrf, merchant = login_synthetic(app, client)
    data = {'merchant_id':merchant,'order_id':'DEMO-123456-001',
            'numref':'1234567','concept':'Venta local de práctica',
            'amount_minor':38000,'expiration_s':300}
    result = client.post('/v1/checkout/qr', json=data, headers={'X-CSRF-Token':csrf})
    assert result.status_code == 201
    body = result.json()
    assert body['mode'] == 'DEMO'
    assert body['intent']['order_id'] == data['order_id']
    assert body['intent']['amount_minor'] == data['amount_minor']
    assert body['intent']['bank_payment_confirmed'] is False
    assert client.get('/public-status').json()['live_payments_enabled'] is False


def test_unauthenticated_checkout_rejected(service):
    _, client = service
    data = {'merchant_id':'a'*32,'order_id':'DEMO-123456-001',
            'numref':'1234567','concept':'Venta de práctica','amount_minor':38000,'expiration_s':300}
    assert client.post('/v1/checkout/qr', json=data).status_code in (401, 403)


def test_offline_manifest_matches_the_public_resources_served(service):
    _, client = service
    response = client.get('/static/unificada/offline-manifiesto.js')
    prefix, suffix = 'globalThis.RioOfflineManifest=Object.freeze(', ');\n'
    assert response.status_code == 200
    assert response.text.startswith(prefix) and response.text.endswith(suffix)
    manifest = json.loads(response.text[len(prefix):-len(suffix)])
    assert len(manifest['assets']) >= 18
    for url, expected in manifest['assets'].items():
        assert url.startswith('/static/unificada/') and '/..' not in url
        resource = client.get(url)
        assert resource.status_code == 200
        assert hashlib.sha256(resource.content).hexdigest() == expected, url
