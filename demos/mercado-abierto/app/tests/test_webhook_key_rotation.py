"""Historical key use is explicit, isolated and never exposed in settings."""
import base64
import json
import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from rio_pey_codi.app import Config
from rio_pey_codi.identity import EmailConfig
from rio_pey_codi.models import Event
from rio_pey_codi.platform import Settings
from rio_pey_codi.platform import create_platform, parse_previous_webhook_keys
from rio_pey_codi.signatures import make_signature
from test_platform import SECRET, signed_webhook
from test_reconciliation_preview import RECORD, deliver, payment, post_preview  # noqa: F401

NEW_SECRET = 'whsec_' + base64.b64encode(b'synthetic-rotation-current-key-32bytes').decode()
WRONG_SECRET = 'whsec_' + base64.b64encode(b'synthetic-rotation-wrong-key-material').decode()


@pytest.fixture
def clean_settings_environment(monkeypatch):
    for name in ('PEY_API_KEY','PEY_API_KEY_ID','PEY_BANK_ACCOUNT_ID','PEY_LIVE_MERCHANT_ID',
                 'PEY_WEBHOOK_SECRET','PEY_WEBHOOK_SIGNING_KEY_REF','PEY_WEBHOOK_PREVIOUS_SECRETS_JSON',
                 'DATABASE_URL','SMTP_USER','SMTP_PASSWORD','SMTP_FROM','SMTP_HOST','SMTP_PORT',
                 'APP_ENV','RPG_MODE','PAYMENTS_LIVE_ENABLED','PUBLIC_BASE_URL','APP_ORIGIN',
                 'PEY_READONLY_ACCOUNT_LOOKUP_ENABLED','PEY_READONLY_ACCOUNT_LOOKUP_MERCHANT',
                 'PEY_READONLY_ACCOUNT_LOOKUP_KEY_REF','PEY_READONLY_ACCOUNT_LOOKUP_KEY'):
        monkeypatch.delenv(name, raising=False)


def test_settings_repr_does_not_expose_secrets_or_database_password():
    settings = Settings(database_url='postgresql://user:synthetic-db-password@example.invalid/db',
                        smtp_password='synthetic-smtp-password', api_key='synthetic-pey-api-key',
                        webhook_secret='synthetic-webhook-secret')
    value = repr(settings)
    for secret in ('synthetic-db-password','synthetic-smtp-password','synthetic-pey-api-key','synthetic-webhook-secret'):
        assert secret not in value
    assert 'synthetic-smtp-password' not in repr(EmailConfig(password='synthetic-smtp-password'))
    legacy = Config(server_token='synthetic-server-token', webhook_secret='synthetic-legacy-webhook',
                    pey_key='synthetic-legacy-api-key')
    assert all(secret not in repr(legacy) for secret in
               ('synthetic-server-token','synthetic-legacy-webhook','synthetic-legacy-api-key'))


def test_old_key_can_reverify_history_but_cannot_authorize_new_delivery(payment):
    deliver(payment)
    env, _, _, _, payload = payment
    settings = replace(env[0].state.settings, webhook_secret=NEW_SECRET, webhook_key_ref='current-v2',
                       webhook_previous_keys=(('local-v1',SECRET),))
    assert SECRET not in repr(settings) and NEW_SECRET not in repr(settings)
    reopened = create_platform(settings)
    client = TestClient(reopened, cookies=env[1].cookies)
    history = post_preview(payment, [RECORD], client=client).json()
    assert history['signature_assessment'] == 'VERIFIED'
    assert history['classification'] == 'MATCH_CANDIDATE_UNVERIFIED'
    assert not history['beneficiary_binding_verified'] and not history['bank_payment_confirmed']
    assert signed_webhook(client, payload, 'old-key-new-event').status_code == 401
    with reopened.state.accounts.Session() as db:
        assert db.get(Event, 'old-key-new-event') is None
    raw = json.dumps(payload, separators=(',', ':')).encode()
    timestamp = int(time.time())
    new_event = client.post('/v1/webhooks/pey', content=raw, headers={
        'webhook-id':'new-key-event','webhook-timestamp':str(timestamp),
        'webhook-signature':make_signature(SECRET,'new-key-event',timestamp,raw) + ' ' +
                            make_signature(NEW_SECRET,'new-key-event',timestamp,raw),
        'content-type':'application/json'})
    assert new_event.status_code == 200 and new_event.json()['outcome'] == 'DUPLICATE_TRANSACTION'
    result = post_preview(payment, [RECORD], client=client).json()
    assert result['signature_assessment'] == 'VERIFIED'
    with reopened.state.accounts.Session() as db:
        first, second = db.get(Event,'review-event'), db.get(Event,'new-key-event')
        assert (first.signature_key_ref, second.signature_key_ref) == ('local-v1','current-v2')
        assert second.signature == make_signature(NEW_SECRET,'new-key-event',timestamp,raw)
        assert SECRET not in repr(first.__dict__) and NEW_SECRET not in repr(second.__dict__)
    assert SECRET not in new_event.text and NEW_SECRET not in new_event.text


def test_removed_historical_key_cannot_be_inferred_from_current_key(payment):
    deliver(payment)
    env = payment[0]
    app = create_platform(replace(env[0].state.settings,webhook_secret=NEW_SECRET,webhook_key_ref='current-v2'))
    result = post_preview(payment,[RECORD],client=TestClient(app,cookies=env[1].cookies)).json()
    assert result['signature_assessment'] == 'KEY_UNAVAILABLE'
    assert result['classification'] == 'PROVIDER_SIGNATURE_KEY_UNAVAILABLE'


def test_history_can_be_reviewed_without_enabling_new_webhooks(payment):
    deliver(payment)
    env, _, _, _, payload = payment
    app = create_platform(replace(env[0].state.settings,webhook_secret='',webhook_key_ref='current-v2',
                                  webhook_previous_keys=(('local-v1',SECRET),)))
    client = TestClient(app,cookies=env[1].cookies)
    result = post_preview(payment,[RECORD],client=client).json()
    assert result['signature_assessment'] == 'VERIFIED'
    assert signed_webhook(client,payload,'no-current-secret').status_code == 503


def test_wrong_historical_material_does_not_verify(payment):
    deliver(payment)
    env = payment[0]
    app = create_platform(replace(env[0].state.settings,webhook_secret=NEW_SECRET,webhook_key_ref='current-v2',
                                  webhook_previous_keys=(('local-v1',WRONG_SECRET),)))
    result = post_preview(payment,[RECORD],client=TestClient(app,cookies=env[1].cookies)).json()
    assert result['signature_assessment'] == 'INVALID'
    assert result['classification'] == 'PROVIDER_SIGNATURE_INVALID'


def test_tampered_reference_never_falls_back_to_the_other_key(payment):
    deliver(payment)
    env = payment[0]
    app = create_platform(replace(env[0].state.settings,webhook_secret=NEW_SECRET,webhook_key_ref='current-v2',
                                  webhook_previous_keys=(('local-v1',SECRET),)))
    with app.state.accounts.Session.begin() as db:
        db.get(Event, 'review-event').signature_key_ref = 'current-v2'
    result = post_preview(payment,[RECORD],client=TestClient(app,cookies=env[1].cookies)).json()
    assert result['signature_assessment'] == 'INVALID'
    assert result['classification'] == 'PROVIDER_SIGNATURE_INVALID'


def test_missing_signature_evidence_is_not_reconstructed_using_history(payment):
    deliver(payment)
    env = payment[0]
    app = create_platform(replace(env[0].state.settings,webhook_secret=NEW_SECRET,webhook_key_ref='current-v2',
                                  webhook_previous_keys=(('local-v1',SECRET),)))
    with app.state.accounts.Session.begin() as db:
        event = db.get(Event,'review-event')
        event.signature = event.signature_timestamp = event.signature_received_at = event.signature_key_ref = None
    result = post_preview(payment,[RECORD],client=TestClient(app,cookies=env[1].cookies)).json()
    assert result['signature_assessment'] == 'NOT_RECORDED'
    assert result['classification'] == 'PROVIDER_SIGNATURE_NOT_RECORDED'


def test_historical_keys_load_only_from_explicit_secret_configuration(monkeypatch, clean_settings_environment):
    monkeypatch.setenv('PEY_WEBHOOK_SECRET',NEW_SECRET)
    monkeypatch.setenv('PEY_WEBHOOK_SIGNING_KEY_REF','current-v2')
    monkeypatch.setenv('PEY_WEBHOOK_PREVIOUS_SECRETS_JSON',json.dumps({'local-v1':SECRET}))
    settings = Settings.from_env()
    settings.validate()
    assert settings.webhook_previous_keys == (('local-v1',SECRET),)
    assert SECRET not in repr(settings) and NEW_SECRET not in repr(settings)


@pytest.mark.parametrize('bad', ['[]', '{"v1":null}', '{"v1":{"nested":"secret"}}',
                                  '{"v1":"c2VjcmV0","v1":"c2VjcmV0"}', 'x' * 8193])
def test_invalid_history_configuration_fails_without_echoing_input(bad, monkeypatch, clean_settings_environment):
    monkeypatch.setenv('PEY_WEBHOOK_PREVIOUS_SECRETS_JSON',bad)
    with pytest.raises(ValueError) as error:
        settings = Settings.from_env()
        settings.validate()
    assert bad not in str(error.value)


@pytest.mark.parametrize('previous', [
    (('local-v1',WRONG_SECRET),),
    (('old-v1',SECRET),),  # same key material as active, under a different reference
    (('old-v1',WRONG_SECRET),('old-v1',NEW_SECRET)),
    (('old-v1',WRONG_SECRET),('older-v0',WRONG_SECRET.removeprefix('whsec_'))),
    (('bad ref',WRONG_SECRET),),
    (('old-v1','not-base64!'),),
    (('old-v1',''),),
    tuple((f'v{i}',WRONG_SECRET) for i in range(9)),
])
def test_keyring_rejects_duplicate_references_material_and_invalid_values(previous):
    with pytest.raises(ValueError, match='Invalid .*webhook signing key configuration'):
        Settings(webhook_secret=SECRET,webhook_key_ref='local-v1',webhook_previous_keys=previous).validate()


@pytest.mark.parametrize('size', [1, 23, 65, 100])
def test_keyring_rejects_keys_outside_standard_length(size):
    short_or_long = 'whsec_' + base64.b64encode(b'x' * size).decode()
    with pytest.raises(ValueError, match='Invalid webhook signing key configuration'):
        Settings(webhook_secret=short_or_long).validate()
    with pytest.raises(ValueError, match='Invalid webhook signing key configuration'):
        Settings(webhook_secret=NEW_SECRET,webhook_previous_keys=(('old-v1',short_or_long),)).validate()


@pytest.mark.parametrize('size', [24, 64])
def test_keyring_accepts_standard_length_boundaries(size):
    synthetic = 'whsec_' + base64.b64encode(b'x' * size).decode()
    Settings(webhook_secret=synthetic).validate()


def test_key_history_does_not_enable_live_mode():
    with pytest.raises(ValueError, match='Hosted LIVE requires exclusively merchant-scoped credentials'):
        Settings(mode='LIVE',live_enabled=True,webhook_secret=NEW_SECRET,webhook_key_ref='current-v2',
                 webhook_previous_keys=(('local-v1',SECRET),)).validate()


def test_standard_webhooks_accepts_valid_unpadded_base64_key():
    padded = 'whsec_' + base64.b64encode(b'synthetic-unpadded-key-32-bytes!').decode()
    assert padded.endswith('=')
    unpadded = padded.rstrip('=')
    Settings(webhook_secret=unpadded).validate()
    assert make_signature(padded,'synthetic-id',123,b'{}') == make_signature(unpadded,'synthetic-id',123,b'{}')
    with pytest.raises(ValueError, match='Invalid webhook signing key configuration'):
        Settings(webhook_secret=padded,webhook_previous_keys=(('old-v1',unpadded),)).validate()


@pytest.mark.parametrize('invalid', ['whsec_a','whsec_YQ=','whsec_abc!','whsec_'])
def test_noncanonical_or_malformed_key_is_rejected(invalid):
    with pytest.raises(ValueError, match='Invalid webhook signing key configuration'):
        Settings(webhook_secret=invalid).validate()
