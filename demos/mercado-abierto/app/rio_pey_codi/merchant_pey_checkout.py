"""Merchant credentials, signed pey deliveries and independent API readback."""
import decimal
import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass
from io import BytesIO

import qrcode
from fastapi import HTTPException
from qrcode.image.pure import PyPNGImage
from sqlalchemy import select

from .app import parse_provider_amount
from .merchant_pey_vault import master_key, open_value
from .models import Intent, MerchantPeyCredential, MerchantPeySecret
from .pey import LivePeyGateway, PROVIDER_ID, ProviderError, provider_json
from .signatures import InvalidWebhook, SignatureEvidence, reverify_stored_events, verify_and_capture


@dataclass(frozen=True, repr=False)
class MerchantPey:
    reference: str
    api_key_id: str | None
    gateway: LivePeyGateway
    webhook_secret: str


class MerchantPeyUnavailable(HTTPException):
    def __init__(self):
        super().__init__(503, 'Habilita la conexión de pey para este comercio antes de cobrar.')


def _resolve(db, merchant_id, reference):
    row = db.get(MerchantPeyCredential, reference)
    if row is None or row.merchant_id != merchant_id:
        raise ValueError('Unknown pey credential')
    key = master_key()

    def decrypt(name, data):
        return open_value(key, merchant_id, name + ':' + reference, data)

    return MerchantPey(reference, row.api_key_id, LivePeyGateway(
        api_key=decrypt('api_key', row.api_key),
        bank_account_id=decrypt('bank_account_id', row.bank_account_id) if row.bank_account_id else '',
    ), decrypt('webhook_secret', row.webhook_secret))


def merchant_gateway(session_factory, merchant_id, reference=None, *, db=None):
    """Resolve the active version for issuance or the version pinned to an intent."""
    def resolve(session):
        if reference is not None:
            return _resolve(session, merchant_id, reference)
        row = session.get(MerchantPeySecret, merchant_id, with_for_update=db is not None)
        if row is None or not row.active_credential_ref:
            raise ValueError('Merchant payments inactive')
        return _resolve(session, merchant_id, row.active_credential_ref)

    try:
        if db is not None:
            return resolve(db)
        with session_factory() as session:
            return resolve(session)
    except Exception:
        raise MerchantPeyUnavailable() from None


def qr_png(payload):
    image = qrcode.make(payload.encode('utf-8'), image_factory=PyPNGImage, box_size=6,
                        error_correction=qrcode.constants.ERROR_CORRECT_L)
    output = BytesIO()
    image.save(output)
    return output.getvalue()


def _payment(transaction, qr_id, amount, transaction_id, *, intent_id=None):
    if (transaction.get('id') != transaction_id or transaction.get('status') != 'PAID'
            or transaction.get('currency') != 'MXN' or transaction.get('paymentMethod') != 'CODI'
            or transaction.get('payableType', 'API_CODI_QR') != 'API_CODI_QR'
            or transaction.get('payableId', qr_id) != qr_id):
        raise ValueError('Inconsistent provider transaction')
    value = transaction.get('amount')
    if type(value) not in (int, decimal.Decimal) or parse_provider_amount(value) != amount:
        raise ValueError('Inconsistent provider amount')
    date_paid = transaction.get('datePaid')
    if type(date_paid) is not int or date_paid <= 0:
        raise ValueError('Invalid provider timestamp')
    if intent_id is not None:
        if (transaction.get('payableId') != qr_id or transaction.get('payableType') != 'API_CODI_QR'
                or _provider_intent(transaction) != intent_id):
            raise ValueError('Provider transaction does not identify this order')
    evidence = [transaction_id, qr_id, amount, 'MXN', date_paid, intent_id]
    return hashlib.sha256(json.dumps(evidence, separators=(',', ':')).encode()).hexdigest()


def _provider_intent(payload):
    metadata = payload.get('metadata')
    external = metadata.get('externalMetadata') if isinstance(metadata, dict) else None
    return external.get('rioIntentId') if isinstance(external, dict) else None


def _same_api_key(first, second):
    return hmac.compare_digest(first.gateway.api_key.encode(), second.gateway.api_key.encode())


def _signing_version(factory, intent, credential, headers, body):
    try:
        return verify_and_capture(headers, body, credential.webhook_secret, credential.reference)
    except InvalidWebhook as original:
        # A merchant may rotate the webhook secret while keeping the same
        # provider key. The original version remains valid for older deliveries.
        try:
            current = merchant_gateway(factory, intent.merchant_id)
        except MerchantPeyUnavailable:
            raise original from None
        if current.reference == credential.reference or not _same_api_key(credential, current):
            raise original
        return verify_and_capture(headers, body, current.webhook_secret, current.reference)


def merchant_signing_keys(factory, intent, references):
    """Resolve only recorded signing versions with the same tenant and API key."""
    try:
        pinned = merchant_gateway(factory, intent.merchant_id, intent.pey_credential_ref)
    except MerchantPeyUnavailable:
        return '', ()
    historical = []
    for ref in sorted(set(references) - {None, pinned.reference}):
        try:
            alternate = merchant_gateway(factory, intent.merchant_id, ref)
        except MerchantPeyUnavailable:
            continue
        if _same_api_key(pinned, alternate):
            historical.append((ref, alternate.webhook_secret))
    return pinned.webhook_secret, tuple(historical)


def receive_merchant_event(factory, repository, merchant_id, headers, raw_body):
    # Resolve only a version already bound to the intent. Metadata is untrusted
    # until the signature is verified and the transaction is read back from pey.
    data = provider_json(raw_body)
    if data.get('type') != 'codi.qr.payment_received':
        credential = merchant_gateway(factory, merchant_id)
        verify_and_capture(headers, raw_body, credential.webhook_secret, credential.reference)
        return {'outcome': 'IGNORED_EVENT_TYPE'}
    intent_id = _provider_intent(data)
    qr_id, transaction_id, api_key_id = (data.get(k) for k in ('codiQrId', 'transactionId', 'apiKeyId'))
    if not all(isinstance(value, str) and PROVIDER_ID.fullmatch(value)
               for value in (qr_id, transaction_id, api_key_id)):
        raise ValueError('Invalid provider identity')
    with factory() as db:
        query = select(Intent).where(Intent.merchant_id == merchant_id)
        if isinstance(intent_id, str) and re.fullmatch(r'[0-9a-f]{32}', intent_id):
            intent = db.scalar(query.where(Intent.id == intent_id))
        else:
            intent = db.scalar(query.where(Intent.provider_qr_id == qr_id))
    if intent is None or intent.pey_credential_ref is None:
        raise InvalidWebhook('Unknown merchant payment')
    intent_id = intent.id
    credential = merchant_gateway(factory, merchant_id, intent.pey_credential_ref)
    event_id, signature = _signing_version(factory, intent, credential, headers, raw_body)
    if (not event_id.isascii() or len(event_id) > 140 or not event_id.isprintable()
            or (credential.api_key_id is not None and api_key_id != credential.api_key_id)):
        raise InvalidWebhook('Invalid event or signing key identity')
    if credential.gateway.bank_account_id and data.get('bankAccountId') != credential.gateway.bank_account_id:
        raise ValueError('Inconsistent provider bank account')
    value, numref = data.get('amount'), data.get('numRef')
    if type(value) not in (int, decimal.Decimal):
        raise ValueError('Invalid provider amount')
    amount = parse_provider_amount(value)
    if (amount != intent.amount_minor or numref != intent.numref
            or (intent.provider_qr_id is not None and intent.provider_qr_id != qr_id)):
        raise ValueError('Inconsistent provider order')
    try:
        transaction = credential.gateway.transaction(transaction_id)
        digest = None
        if transaction.get('id') != transaction_id or transaction.get('status') != 'PENDING':
            if intent.provider_qr_id is None:
                digest = _payment(transaction, qr_id, amount, transaction_id, intent_id=intent_id)
            elif transaction.get('payableId') == qr_id and transaction.get('payableType') == 'API_CODI_QR':
                digest = _payment(transaction, qr_id, amount, transaction_id)
            else:
                lookup = reconcile_qr(credential, intent)
                if lookup is not None and lookup[0] == transaction_id:
                    digest = lookup[1]
    except ProviderError:
        # The signed delivery is stored but cannot advance the payment until
        # an authenticated readback agrees. A later real lookup can recover it.
        digest = None
    return repository.confirm_event(
        event_id, raw_body, qr_id, amount, numref, transaction_id, signature,
        merchant_id=merchant_id, credential_ref=credential.reference, intent_id=intent_id,
        provider_digest=digest,
    )


def reconcile_qr(credential, row):
    token, seen_tokens, seen_ids, paid = None, set(), set(), []
    deadline = time.monotonic() + 13
    for _ in range(10):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        page = credential.gateway.qr_transactions(row.provider_qr_id, token, timeout=min(5, remaining))
        items = page.get('items')
        if type(items) is not list or len(items) > 20:
            raise ValueError('Invalid transaction page')
        for transaction in items:
            if not isinstance(transaction, dict):
                raise ValueError('Invalid provider transaction')
            tx = transaction.get('id')
            if not isinstance(tx, str) or not PROVIDER_ID.fullmatch(tx) or tx in seen_ids:
                raise ValueError('Invalid or repeated transaction identifier')
            seen_ids.add(tx)
            if transaction.get('status') == 'PAID':
                paid.append((tx, _payment(transaction, row.provider_qr_id, row.amount_minor, tx)))
            elif transaction.get('status') != 'PENDING':
                raise ValueError('Unknown provider status')
        token = page.get('nextToken')
        if token is None:
            if len(paid) > 1:
                raise ValueError('Multiple paid transactions require review')
            return paid[0] if paid else None
        if (not isinstance(token, str) or not 0 < len(token) <= 2048
                or not token.isprintable() or token in seen_tokens):
            raise ValueError('Invalid provider pagination')
        seen_tokens.add(token)
    raise ProviderError('Provider pagination did not complete')


def recover_early_delivery(factory, repository, credential, row):
    pending = repository.pending_provider_events(row)
    if len(pending) > 5 or len({(item.qr_id, item.transaction_id) for item in pending}) > 1:
        raise ValueError('Conflicting early deliveries')
    if not pending:
        return None
    event = pending[0]
    secret, previous = merchant_signing_keys(factory, row, [event.signature_key_ref])
    if reverify_stored_events([event], secret, credential.reference, historical_keys=previous) != 'VERIFIED':
        raise ValueError('Stored delivery could not be verified')
    transaction = credential.gateway.transaction(event.transaction_id)
    if transaction.get('id') == event.transaction_id and transaction.get('status') == 'PENDING':
        return None
    digest = _payment(transaction, event.qr_id, row.amount_minor, event.transaction_id, intent_id=row.id)
    signature = SignatureEvidence(event.signature, event.signature_timestamp,
                                  event.signature_received_at, event.signature_key_ref)
    repository.confirm_event(
        event.id, bytes(event.raw_body), event.qr_id, event.amount_minor, event.numref,
        event.transaction_id, signature, merchant_id=row.merchant_id,
        credential_ref=credential.reference, intent_id=row.id, provider_digest=digest,
    )
    return repository.get(row.id)
