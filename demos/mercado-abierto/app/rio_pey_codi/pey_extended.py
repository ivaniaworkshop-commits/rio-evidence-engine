"""Public pey operations. Fixed origin, bounded reads, no automatic POST retries."""
import decimal
import json
import re
import time
import urllib.error
import urllib.request
from urllib.parse import quote, urlencode

from .bank_accounts import BankAccountRegistration
from .pey import LivePeyGateway, ProviderError, ProviderRejected, PROVIDER_ID, MAX_RESPONSE, _open_provider, _read_provider_body, provider_json


def identifier(value):
    if not isinstance(value, str) or not PROVIDER_ID.fullmatch(value):
        raise ValueError('Identificador inválido')
    return quote(value, safe='')


def money(value, *, zero=False):
    if type(value) is not int or value < (0 if zero else 1) or value > 100000000:
        raise ValueError('Importe fuera de rango')
    return decimal.Decimal(value) / 100


def encode(value):
    # Decimal remains a JSON number, never a binary float or a quoted amount.
    if isinstance(value, decimal.Decimal):
        if not value.is_finite():
            raise ValueError('Importe inválido')
        return format(value, 'f')
    if isinstance(value, (list, tuple)):
        return '[' + ','.join(encode(v) for v in value) + ']'
    if isinstance(value, dict):
        return '{' + ','.join(json.dumps(k) + ':' + encode(v) for k, v in value.items()) + '}'
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class FullPeyGateway(LivePeyGateway):
    def post(self, path, payload):
        if path not in {'/codi/pn', '/bank-account', '/payment-link/create', '/payment-link/update'}:
            raise ValueError('Operación no permitida')
        request = urllib.request.Request('https://api.pey.mx' + path, data=encode(payload).encode(),
            headers={'Authorization': 'Bearer ' + self.api_key, 'Content-Type': 'application/json', 'Accept': 'application/json'}, method='POST')
        deadline = time.monotonic() + 15
        try:
            with _open_provider(request, timeout=15) as response:
                if response.status != 200:
                    raise ProviderError('Resultado de pey incierto; consulta antes de repetir')
                return provider_json(_read_provider_body(response, MAX_RESPONSE, deadline))
        except urllib.error.HTTPError as exc:
            # Only explicit, documented validation responses prove rejection.
            with exc:
                raw = _read_provider_body(exc, 8192, deadline)
                data = provider_json(raw)
                error = data.get('error')
                if exc.code in (400, 403, 404, 409) and isinstance(error, dict) and isinstance(error.get('type'), str):
                    raise ProviderRejected('pey rechazó la operación; revisa los datos y el estado') from None
            raise ProviderError('Resultado de pey incierto; consulta antes de repetir') from None
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise ProviderError('Resultado de pey incierto; consulta antes de repetir') from exc

    def register_account(self, *, alias, name, clabe, entity):
        account = BankAccountRegistration(alias, name, clabe, entity)
        result = self.post('/bank-account', json.loads(account.to_json_bytes()))
        identifier(result.get('id'))
        if result.get('codiStatus') not in {'PENDING', 'PROCESSING', 'ACTIVE', 'ERROR'}:
            raise ProviderError('Respuesta de cuenta inválida')
        return result

    def account(self, account_id):
        return self._get('/bank-account/' + identifier(account_id))

    def transactions(self, *, account_id=None, token=None):
        path = '/transaction/bank-account/' + identifier(account_id) if account_id else '/transaction/api-key'
        if token is not None:
            if not isinstance(token, str) or not 0 < len(token) <= 4096 or not token.isprintable():
                raise ValueError('Cursor inválido')
            path += '?' + urlencode({'nextToken': token})
        return self._get(path)

    def qr_transactions(self, qr_id, token=None):
        path = '/transaction/codi/qr/' + identifier(qr_id)
        if token is not None:
            if not isinstance(token, str) or not 0 < len(token) <= 4096 or not token.isprintable():
                raise ValueError('Cursor inválido')
            path += '?' + urlencode({'nextToken': token})
        return self._get(path)

    def push(self, *, amount_minor, phone, concept, numref, expiration_s, operation_id, bank_account_id=None):
        if not isinstance(phone, str) or not re.fullmatch(r'[0-9]{10}', phone):
            raise ValueError('El teléfono debe tener 10 dígitos')
        if not re.fullmatch(r'[0-9]{1,7}', numref) or type(expiration_s) is not int or expiration_s < 360:
            raise ValueError('Referencia o vigencia inválida')
        payload = {'amount': money(amount_minor), 'phoneNumber': phone, 'concept': concept,
            'numRef': numref, 'expiration': expiration_s, 'metadata': {'mercadoOperationId': operation_id}}
        account = bank_account_id if bank_account_id is not None else self.bank_account_id
        if account:
            identifier(account)
            payload['bankAccountId'] = account
        result = self.post('/codi/pn', payload)
        identifier(result.get('transactionId'))
        if not isinstance(result.get('codiId'), str) or not re.fullmatch(r'[0-9]{20}', result['codiId']):
            raise ProviderError('Respuesta de notificación inválida')
        return result

    def create_link(self, *, amount_minor, operation_id, success_url, back_url, has_tip=False):
        if not all(isinstance(u, str) and u.startswith('https://') for u in (success_url, back_url)):
            raise ValueError('Las URLs deben usar HTTPS')
        if type(has_tip) is not bool:
            raise ValueError('Propina inválida')
        result = self.post('/payment-link/create', {'amount': money(amount_minor), 'successUrl': success_url,
            'backUrl': back_url, 'hasTip': has_tip, 'clientReferenceId': operation_id,
            'metadata': {'mercadoOperationId': operation_id}})
        identifier(result.get('id'))
        # URLs are provider data, not arbitrary browser navigation targets.
        from urllib.parse import urlsplit
        url = urlsplit(result.get('url', ''))
        if url.scheme != 'https' or url.hostname not in {'app.mipey.mx', 'app.pey.mx'} or url.username or url.password or url.port not in (None, 443):
            raise ProviderError('URL de pago no reconocida')
        return result

    def link(self, link_id):
        return self._get('/payment-link/' + identifier(link_id))

    def update_link(self, link_id, amount_minor):
        identifier(link_id)
        return self.post('/payment-link/update', {'paymentLinkId': link_id, 'amount': money(amount_minor)})
