"""The public response contains authentication only; modules require a session."""
from html.parser import HTMLParser
from urllib.parse import urlsplit, parse_qs

from fastapi.testclient import TestClient
import pytest

from rio_pey_codi.platform import Settings, create_platform


class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('id'):
            self.ids.append(attrs['id'])
        if tag == 'script' and attrs.get('src'):
            self.scripts.append(attrs['src'])


@pytest.fixture
def context(tmp_path):
    app = create_platform(Settings(database_url='sqlite+pysqlite:///' + str(tmp_path / 'login.sqlite3')))
    with TestClient(app) as client:
        yield app, client


def sign_in(app, client):
    account = {'email': 'workspace@example.com', 'password': 'Workspace-synthetic-123'}
    result = client.post('/v1/auth/signup', json={**account, 'business_name': 'Comercio de prueba'})
    assert result.status_code == 201
    assert client.post('/v1/auth/verify-email', json={'token': app.state.mailer.outbox[-1]['token']}).status_code == 200
    result = client.post('/v1/auth/login', json=account)
    assert result.status_code == 200
    return result.json()['csrf_token']


@pytest.mark.parametrize('path', ['/', '/login', '/verify-email', '/reset-password'])
def test_public_html_contains_only_access_forms(context, path):
    _, client = context
    response = client.get(path)
    assert response.status_code == 200
    tree = Elements()
    tree.feed(response.text)
    assert 'login' in tree.ids
    assert 'signup' in tree.ids
    assert 'forgot-password-form' in tree.ids
    assert '/static/auth.js' in tree.scripts
    assert '/static/app.js' not in tree.scripts
    assert not {'dashboard', 'merchant', 'cobro-codi', 'configuracion-pey', 'pey-setup',
                'local-cash', 'history', 'unresolved'}.intersection(tree.ids)
    assert response.headers['cache-control'] == 'no-store'


PROTECTED = ['/caja', '/hackaton', '/mercado-abierto', '/static/index.html', '/static/unificada/index.html',
             '/static/unificada/caja/index.html', '/static/unificada/mercado/index.html',
             '/static/unificada/hackaton/index.html']


@pytest.mark.parametrize('path', PROTECTED)
def test_direct_module_links_redirect_to_login_before_serving_html(context, path):
    _, client = context
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 303
    assert urlsplit(response.headers['location']).path == '/login'
    assert response.headers['cache-control'] == 'no-store'
    assert 'merchant' not in response.text and 'carrito' not in response.text.lower()


def test_authenticated_workspace_has_each_operation_once_and_logout_removes_access(context):
    app, client = context
    csrf = sign_in(app, client)
    response = client.get('/')
    tree = Elements()
    tree.feed(response.text)
    assert response.status_code == 200
    assert not {'login', 'signup', 'forgot-password-form'}.intersection(tree.ids)
    for name in ('dashboard', 'merchant', 'main-area-menu', 'cobro-codi', 'mis-negocios', 'history', 'unresolved', 'receipt-scan-open'):
        assert tree.ids.count(name) == 1
    assert len(tree.ids) == len(set(tree.ids))
    for path in PROTECTED:
        expected = 403 if path == '/static/unificada/mercado/index.html' else 200
        assert client.get(path).status_code == expected
    assert client.post('/v1/auth/logout', headers={'x-csrf-token': csrf}).status_code == 200
    assert client.get('/caja', follow_redirects=False).status_code == 303
    tree = Elements()
    tree.feed(client.get('/').text)
    assert 'login' in tree.ids and 'dashboard' not in tree.ids


def test_expired_cookie_cannot_open_a_module(context):
    _, client = context
    client.cookies.set('rio_sid', 'expired-synthetic-cookie')
    response = client.get('/static/unificada/mercado/index.html', follow_redirects=False)
    assert response.status_code == 303


def test_login_return_path_cannot_redirect_to_an_external_site(context):
    app, client = context
    sign_in(app, client)
    response = client.get('/login?next=https://example.org/private', follow_redirects=False)
    assert response.status_code == 303
    assert response.headers['location'] == '/'


def test_unauthenticated_market_checkout_keeps_only_valid_order_reference(context):
    _, client = context
    order_id = 'a' * 32
    response = client.get('/caja?market_order=' + order_id, follow_redirects=False)
    assert response.status_code == 303
    next_value = parse_qs(urlsplit(response.headers['location']).query)['next'][0]
    assert next_value == '/caja?market_order=' + order_id + '#cobro-codi'

    unsafe = client.get('/caja?market_order=other', follow_redirects=False)
    next_value = parse_qs(urlsplit(unsafe.headers['location']).query)['next'][0]
    assert next_value == '/'
