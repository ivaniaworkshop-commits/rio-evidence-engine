import json
from pathlib import Path
from unittest.mock import patch

import jsonschema
import pytest
from pydantic import ValidationError

from rio_pey_codi.bank_accounts import BankAccountRegistration
from rio_pey_codi.pey import LivePeyGateway
from rio_pey_codi.platform import Checkout


@pytest.fixture(scope='module')
def contract():
    path = Path(__file__).parent / 'fixtures' / 'pey-contract-2026-10-20.json'
    return json.loads(path.read_text(encoding='utf-8'))


def test_openapi_example_and_adapter_support_open_amount_without_network(contract):
    schema = contract['operations']['/codi/qr']['request']
    example = {
        'amount': 0, 'concept': 'string', 'expiration': 0, 'numRef': '0',
        'generateImage': False, 'bankAccountId': 'string', 'metadata': {},
    }
    jsonschema.Draft202012Validator(schema).validate(example)
    gateway = LivePeyGateway(api_key='synthetic', bank_account_id='fixture')
    with patch('rio_pey_codi.pey._open_provider') as transport:
        request = gateway.prepare_qr_request(intent_id='fixture', amount_minor=0, concept='string', numref='0', expiration_s=0)
    payload = json.loads(request.data)
    jsonschema.Draft202012Validator(schema).validate(payload)
    assert payload['amount'] == 0
    assert payload['expiration'] == 0
    assert payload['numRef'] == '0'
    transport.assert_not_called()


def test_open_amount_and_no_expiry_remain_unavailable_in_checkout():
    base = {'merchant_id': 'a' * 32, 'order_id': 'order', 'numref': '1',
            'concept': 'Demo', 'amount_minor': 100, 'expiration_s': 600}
    with pytest.raises(ValidationError):
        Checkout(**{**base, 'amount_minor': 0})
    with pytest.raises(ValidationError):
        Checkout(**{**base, 'expiration_s': 0})


def test_bank_account_placeholder_is_rejected_by_provider_schema(contract):
    schema = contract['operations']['/bank-account']['request']
    placeholder = {'alias': 'string', 'name': 'string', 'clabe': 'string', 'entity': 'BUSINESS'}
    errors = list(jsonschema.Draft202012Validator(schema).iter_errors(placeholder))
    assert [list(error.path) for error in errors] == [['clabe']]


def test_bank_account_body_is_redacted_and_matches_provider_schema(contract):
    account = BankAccountRegistration(alias='Demo', name='Persona de prueba',
                                      clabe='0' * 18, entity='BUSINESS')
    assert 'Persona de prueba' not in repr(account)
    assert '0' * 18 not in repr(account)
    payload = json.loads(account.to_json_bytes())
    assert payload == {'alias': 'Demo', 'name': 'Persona de prueba', 'clabe': '0' * 18, 'entity': 'BUSINESS'}
    jsonschema.Draft202012Validator(contract['operations']['/bank-account']['request']).validate(payload)
    assert contract['operations']['/bank-account']['success_status'] == 200


def test_bank_account_response_uses_provider_status_casing(contract):
    schema = contract['operations']['/bank-account']['response']
    response = {'id': '01HXYZQR1234567890ABCDEFGH', 'codiStatus': 'PENDING'}
    jsonschema.Draft202012Validator(schema).validate(response)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate({**response, 'codiStatus': 'pending'})


@pytest.mark.parametrize(('prefix', 'check_digit'), [
    ('000' + '12345678901234', '5'),
    ('000' + '98765432101234', '3'),
])
def test_synthetic_clabe_check_digits(prefix, check_digit):
    BankAccountRegistration(alias='Demo', name='Persona de prueba', clabe=prefix + check_digit, entity='PERSON')
    with pytest.raises(ValueError, match='check digit'):
        BankAccountRegistration(alias='Demo', name='Persona de prueba', clabe=prefix + '9', entity='PERSON')


@pytest.mark.parametrize(('clabe', 'entity'), [
    ('string', 'BUSINESS'),
    ('0' * 17 + '1', 'BUSINESS'),
    ('０' * 18, 'BUSINESS'),
    ('0' * 18, 'business'),
])
def test_bank_account_invalid_fields_are_rejected_without_echoing_clabe(clabe, entity):
    with pytest.raises(ValueError) as error:
        BankAccountRegistration(alias='Demo', name='Persona de prueba', clabe=clabe, entity=entity)
    assert clabe not in str(error.value)


def test_contract_fixture_is_anchored_to_provided_source(contract):
    assert contract['openapi'] == '3.1.1'
    assert contract['version'] == '2026-10-20'
    assert contract['source_sha256'] == '497f48eb8047d88b1c8672fcb252eb8c7eee46546acaeb01440cfac8cd37335a'
