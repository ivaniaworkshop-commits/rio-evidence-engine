"""Authenticated lookup of our existing signed payment receipt QR codes.

No camera frame, arbitrary URL, provider request or client payment claim is used.
"""
import re
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictStr

from .receipts import TITLE

TOKEN = re.compile(r'[0-9a-f]{32}\.[A-Za-z0-9_-]{43}')


class ReceiptVerificationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    qr_text: StrictStr = Field(min_length=1, max_length=2048)
    merchant_id: StrictStr = Field(pattern=r'^[0-9a-f]{32}$')


def receipt_token(value: str, public_url: str) -> str:
    """Accept only our canonical receipt URL or the signed token itself."""
    value = value.strip()
    if TOKEN.fullmatch(value):
        return value
    try:
        scanned, own = urlsplit(value), urlsplit(public_url)
        def origin(url):
            return (url.scheme.lower(), (url.hostname or '').lower(),
                    url.port or (443 if url.scheme.lower() == 'https' else 80))
        if (scanned.scheme not in ('http', 'https') or origin(scanned) != origin(own)
                or scanned.username is not None or scanned.password is not None
                or scanned.query or scanned.fragment):
            raise ValueError()
        match = re.fullmatch(r'/comprobante/(' + TOKEN.pattern + r')', scanned.path)
        if match:
            return match.group(1)
    except ValueError:
        pass
    raise HTTPException(422, 'Este QR no es un comprobante de Mercado Abierto.')


def register_receipt_verification(app, accounts, receipts):
    @app.post('/v1/receipts/verify')
    def verify_receipt(body: ReceiptVerificationRequest, request: Request):
        principal = accounts.session(request, csrf=True)
        accounts.assert_member(principal['id'], body.merchant_id)
        token = receipt_token(body.qr_text, receipts.public_url)
        # lookup checks the signature, persisted issuance and current provider
        # evidence again, so a once-valid receipt cannot outlive a reversal.
        receipt, intent, merchant_name = receipts.lookup(token)
        if intent.merchant_id != body.merchant_id:
            raise HTTPException(404, 'Comprobante no encontrado para este negocio.')
        return {
            'verified': True,
            'title': TITLE,
            'receipt_id': receipt.public_id,
            'merchant_id': intent.merchant_id,
            'merchant_name': merchant_name,
            'order_id': intent.order_id,
            'amount_minor': intent.amount_minor,
            'currency': 'MXN',
            'confirmed_at': intent.provider_payment_observed_at,
            'verification_source': 'PEY_AUTHENTICATED_READBACK',
            'bank_settlement_verified': False,
        }
