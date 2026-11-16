"""Read a single pey account over authenticated HTTPS; never initiate payments."""
import http.client
import json
import re
import ssl
from time import monotonic

from .app import _no_duplicate_pairs

_ULID = re.compile(r'^[0-7][0-9A-HJKMNP-TV-Z]{25}$')
_TOKEN = re.compile(r'^[A-Za-z0-9._~+/\-]+={0,2}$')
_STATUSES = frozenset(('PENDING', 'PROCESSING', 'ACTIVE', 'ERROR'))


class ProviderAccountUnavailable(ValueError):
    """A deliberately generic failure which never includes credentials or payloads."""


def valid_readonly_token(value):
    return isinstance(value, str) and 1 <= len(value) <= 512 and _TOKEN.fullmatch(value) is not None


def lookup_pey_account(token, account_id):
    """Return the provider's status, not ownership or a bank-settlement assertion.

    The origin is fixed; redirects are not followed. No request/response body or
    credential is returned or logged. This function performs a real GET when
    explicitly invoked with a configured credential.
    """
    if not valid_readonly_token(token) or not isinstance(account_id, str) or not _ULID.fullmatch(account_id):
        raise ProviderAccountUnavailable('Account lookup unavailable')
    connection = None
    try:
        connection = http.client.HTTPSConnection('api.pey.mx', 443, timeout=5,
                                                  context=ssl.create_default_context())
        connection.request('GET', '/bank-account/' + account_id,
                           headers={'Accept':'application/json', 'Authorization':'Bearer ' + token})
        response = connection.getresponse()
        if response.status == 404:
            return 'NOT_FOUND'
        if response.status != 200 or (response.getheader('Content-Type') or '').split(';', 1)[0].strip().lower() != 'application/json':
            raise ProviderAccountUnavailable('Account lookup unavailable')
        deadline = monotonic() + 10
        raw = bytearray()
        while True:
            if monotonic() >= deadline:
                raise ProviderAccountUnavailable('Account lookup unavailable')
            part = response.read1(min(4096, 16385 - len(raw)))
            if not part:
                break
            raw.extend(part)
            if len(raw) > 16384:
                raise ProviderAccountUnavailable('Account lookup unavailable')
        if getattr(response, 'length', None) not in (None, 0):
            raise ProviderAccountUnavailable('Account lookup unavailable')
        def reject_constant(_value):
            raise ValueError('Invalid JSON constant')
        data = json.loads(bytes(raw), object_pairs_hook=_no_duplicate_pairs, parse_constant=reject_constant)
        if type(data) is not dict or data.get('id') != account_id or data.get('codiStatus') not in _STATUSES:
            raise ProviderAccountUnavailable('Account lookup unavailable')
        return data['codiStatus']
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError, http.client.HTTPException):
        raise ProviderAccountUnavailable('Account lookup unavailable') from None
    finally:
        if connection is not None:
            try:
                connection.close()
            except (OSError, http.client.HTTPException):
                pass
