"""Live and mock adapter; never make a live request unless readiness gate passed."""
import json
import decimal
import re
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import quote, urlencode
import certifi


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open_provider(request, timeout):
    context = ssl.create_default_context(cafile=certifi.where())
    https = urllib.request.HTTPSHandler(context=context)
    return urllib.request.build_opener(NoRedirect(), https).open(request, timeout=timeout)


class ProviderError(RuntimeError):
    pass


def _read_provider_body(response, maximum, deadline):
    """Bound body size and stop drip-fed replies at the shared request deadline.

    HTTPResponse.read1 performs at most one underlying read, unlike read(N),
    which can wait indefinitely while bytes continue arriving. An in-flight
    socket read retains the opener's inactivity timeout and may finish after
    the deadline; this is not a hard cancellation of DNS or socket operations.
    """
    # HTTPError wraps the HTTPResponse in fp. Inspect concrete methods rather
    # than dynamic attributes supplied by transport proxies or test doubles.
    source = response
    if not callable(getattr(type(source), 'read1', None)):
        source = getattr(response, 'fp', response)
    if not callable(getattr(type(source), 'read1', None)):
        if time.monotonic() >= deadline:
            raise ProviderError('Provider response deadline exceeded')
        body = response.read(maximum + 1)
        if time.monotonic() >= deadline:
            raise ProviderError('Provider response deadline exceeded')
        if not isinstance(body, bytes) or len(body) > maximum:
            raise ProviderError('Provider response exceeds size limit')
        return body
    read = source.read1
    body = bytearray()
    while True:
        if time.monotonic() >= deadline:
            raise ProviderError('Provider response deadline exceeded')
        part = read(min(4096, maximum + 1 - len(body)))
        if time.monotonic() >= deadline:
            raise ProviderError('Provider response deadline exceeded')
        if not isinstance(part, bytes):
            raise ProviderError('Unexpected provider response body')
        if not part:
            return bytes(body)
        body.extend(part)
        if len(body) > maximum:
            raise ProviderError('Provider response exceeds size limit')


class ProviderRejected(ProviderError):
    """pey explicitly rejected the request before issuing a QR."""


PROVIDER_ID = re.compile(r'[A-Za-z0-9_-]{1,140}')
MAX_RESPONSE = 256 * 1024
QR_REJECTION_TYPES = frozenset({
    'INVALID_REQUEST', 'PEY_CONSISTENCY_ERROR', 'INVALID_STATE', 'INVALID_AMOUNT', 'INVALID_PARAMETER',
})


def provider_json(body):
    def unique_pairs(pairs):
        result = dict(pairs)
        if len(result) != len(pairs):
            raise ValueError('Duplicate provider field')
        return result

    def invalid_number(_value):
        raise ValueError('Invalid provider number')

    try:
        data = json.loads(body, parse_float=decimal.Decimal, parse_constant=invalid_number,
                          object_pairs_hook=unique_pairs)
        if type(data) is not dict:
            raise ValueError('Invalid provider object')
        return data
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ProviderError('Unexpected pey response') from exc


@dataclass(frozen=True)
class QRResult:
    provider_id: str
    display: str


class MockPeyGateway:
    def create_qr(self, *, intent_id: str, **kwargs) -> QRResult:
        # Deliberately NOT a QR URI / payment link: cannot accidentally be scanned to pay.
        return QRResult("DEMO_" + intent_id, "DEMOSTRACION - NO PAGABLE")


class LivePeyGateway:
    """Create CoDi QR requests against the production pey API."""

    def __init__(self, *, api_key: str, bank_account_id: str):
        self.api_key = api_key
        self.bank_account_id = bank_account_id

    def prepare_qr_request(self, *, intent_id: str, amount_minor: int, concept: str, numref: str, expiration_s: int):
        # Manual serialization retains the user's MXN 2-decimal value as exact JSON numeric text.
        if (type(amount_minor) is not int or amount_minor < 0
                or not isinstance(numref, str) or not re.fullmatch(r'[0-9]{1,7}', numref)
                or type(expiration_s) is not int or (expiration_s != 0 and expiration_s < 360)
                or not isinstance(self.bank_account_id, str)):
            raise ProviderError("Request is outside the supported CoDi contract")
        amount_decimal = f"{amount_minor // 100}.{amount_minor % 100:02d}"
        parts = [f'"amount":{amount_decimal}']
        for name,value in [("concept",concept),("numRef",numref)]:
            parts.append(json.dumps(name) + ":" + json.dumps(value, ensure_ascii=False))
        if self.bank_account_id:
            parts.append(json.dumps("bankAccountId") + ":" + json.dumps(self.bank_account_id, ensure_ascii=False))
        parts.append('"metadata":' + json.dumps({"rioIntentId": intent_id}, separators=(',', ':')))
        parts.append('"expiration":' + str(expiration_s))
        raw = ("{" + ",".join(parts) + "}").encode("utf-8")
        return urllib.request.Request("https://api.pey.mx/codi/qr",data=raw,headers={"Authorization":"Bearer " + self.api_key,"Content-Type":"application/json","Accept":"application/json"},method="POST")

    @staticmethod
    def parse_qr_response(status: int, body: bytes) -> QRResult:
        if status != 201:
            raise ProviderError("Unexpected provider status")
        if not isinstance(body, bytes) or len(body) > 65536:
            raise ProviderError("Provider response exceeds safe limit")
        obj = provider_json(body)
        qr_id = obj.get("id")
        display = obj.get("qrString")
        if (not isinstance(qr_id, str) or not PROVIDER_ID.fullmatch(qr_id)
                or not isinstance(display, str) or not display or len(display.encode('utf-8')) > 2000):
            raise ProviderError("Provider response did not match attested schema")
        return QRResult(qr_id, display)

    def create_qr(self, **kwargs) -> QRResult:
        request = self.prepare_qr_request(**kwargs)
        deadline = time.monotonic() + 15
        try:
            with _open_provider(request, timeout=15) as response:
                return self.parse_qr_response(response.status, _read_provider_body(response, 65536, deadline))
        except urllib.error.HTTPError as exc:
            with exc:
                if exc.code == 400:
                    try:
                        raw = _read_provider_body(exc, 8192, deadline)
                        error = provider_json(raw).get('error') if len(raw) <= 8192 else None
                    except (OSError, ProviderError):
                        error = None
                    if (isinstance(error, dict) and isinstance(error.get('type'), str)
                            and error['type'] in QR_REJECTION_TYPES):
                        raise ProviderRejected('pey rejected the QR request') from None
            raise ProviderError('Provider status uncertain; reconcile before reissuing') from None
        except ProviderError:
            raise
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            # The outcome is uncertain; never automatically retry.
            raise ProviderError("Provider status uncertain; reconcile before reissuing") from exc

    def _get(self, path, *, timeout=6):
        request = urllib.request.Request('https://api.pey.mx' + path, headers={
            'Authorization': 'Bearer ' + self.api_key, 'Accept': 'application/json',
        })
        deadline = time.monotonic() + timeout
        try:
            with _open_provider(request, timeout=timeout) as response:
                if response.status != 200:
                    raise ProviderError('Provider lookup unavailable')
                raw = _read_provider_body(response, MAX_RESPONSE, deadline)
                return provider_json(raw)
        except (urllib.error.URLError, OSError, TimeoutError, ValueError) as exc:
            raise ProviderError('Provider lookup unavailable') from exc

    def check_key(self):
        data = self._get('/transaction/api-key')
        if type(data.get('items')) is not list:
            raise ProviderError('Unexpected pey response')

    def transaction(self, transaction_id):
        if not PROVIDER_ID.fullmatch(transaction_id):
            raise ProviderError('Invalid transaction identifier')
        return self._get('/transaction/' + quote(transaction_id, safe=''))

    def qr_transactions(self, qr_id, token=None, *, timeout=6):
        if not PROVIDER_ID.fullmatch(qr_id):
            raise ProviderError('Invalid QR identifier')
        path = '/transaction/codi/qr/' + quote(qr_id, safe='')
        if token is not None:
            path += '?' + urlencode({'nextToken': token})
        return self._get(path, timeout=timeout)
