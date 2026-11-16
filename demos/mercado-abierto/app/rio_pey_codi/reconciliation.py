"""Compare provider reports with separately supplied bank records for review."""

from dataclasses import dataclass
import decimal
import hashlib
import hmac
import json
from typing import Literal


@dataclass(frozen=True)
class ProviderReport:
    beneficiary: str
    tracking_key: str
    amount_minor: int


@dataclass(frozen=True)
class BankRecord:
    beneficiary: str
    tracking_key: str
    amount_minor: int
    direction: Literal['credit', 'reversal']
    evidence_reference: str
    currency: str = 'MXN'


def compare_for_review(report: ProviderReport, records: list[BankRecord]) -> str:
    """Return a review classification. Caller-supplied records carry no authority."""
    if not report.beneficiary or not report.tracking_key or type(report.amount_minor) is not int or report.amount_minor <= 0:
        raise ValueError('Incomplete provider report')
    candidates = [record for record in records if record.tracking_key == report.tracking_key]
    if not candidates:
        return 'NO_BANK_RECORD'
    if any(
        record.beneficiary != report.beneficiary
        or type(record.amount_minor) is not int
        or record.amount_minor != report.amount_minor
        or record.currency != 'MXN'
        or not record.evidence_reference
        or record.direction not in ('credit', 'reversal')
        for record in candidates
    ):
        return 'DISCREPANCY_REVIEW_REQUIRED'
    if any(record.direction == 'reversal' for record in candidates):
        return 'REVERSAL_REVIEW_REQUIRED'
    if len(candidates) != 1:
        return 'AMBIGUOUS_BANK_RECORDS'
    return 'MATCH_CANDIDATE_UNVERIFIED'


def _text(value, maximum):
    return (isinstance(value, str) and 0 < len(value) <= maximum and
            value == value.strip() and value.isprintable())


def _clabe(value):
    return isinstance(value, str) and len(value) == 18 and all('0' <= c <= '9' for c in value)


def stored_provider_report(intent, events):
    """Extract a review candidate; stored bytes and hashes do not prove authenticity.

    Do not infer a tracking key or beneficiary from the transaction ID. The
    provider's documented metadata fields may be absent depending on the flow.
    """
    from .app import _no_duplicate_pairs, parse_provider_amount

    if intent.status != 'PROVIDER_REPORTED':
        return 'NO_PROVIDER_REPORT', None
    if (not _text(intent.provider_qr_id, 140) or not _text(intent.transaction_id, 140) or
        not _text(intent.numref, 40) or type(intent.amount_minor) is not int or
        not 0 < intent.amount_minor <= 100_000_000):
        return 'PROVIDER_EVIDENCE_INVALID', None
    if not events:
        return 'PROVIDER_EVENT_MISSING', None
    if len(events) > 100:
        return 'PROVIDER_EVIDENCE_LIMIT_EXCEEDED', None
    candidates, key_ids, bank_ids = set(), set(), set()
    missing = False
    for event in events:
        if event.raw_body is None:
            return 'PROVIDER_EVIDENCE_MISSING', None
        try:
            raw = bytes(event.raw_body)
        except (TypeError, ValueError):
            return 'PROVIDER_EVIDENCE_INVALID', None
        if (not isinstance(event.sha256, str) or len(event.sha256) != 64 or
            any(c not in '0123456789abcdef' for c in event.sha256) or len(raw) > 65536 or
            not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), event.sha256)):
            return 'PROVIDER_EVIDENCE_INVALID', None
        try:
            def invalid_constant(_value):
                raise ValueError('Invalid JSON constant')
            payload = json.loads(raw, parse_float=decimal.Decimal, object_pairs_hook=_no_duplicate_pairs,
                                 parse_constant=invalid_constant)
            if (not isinstance(payload, dict) or payload.get('type') != 'codi.qr.payment_received' or
                payload.get('codiQrId') != intent.provider_qr_id or payload.get('numRef') != intent.numref or
                payload.get('transactionId') != intent.transaction_id or
                parse_provider_amount(payload.get('amount')) != intent.amount_minor or
                not _text(payload.get('apiKeyId'), 140)):
                return 'PROVIDER_EVIDENCE_INVALID', None
        except (TypeError, ValueError, RecursionError, OverflowError, decimal.DecimalException):
            return 'PROVIDER_EVIDENCE_INVALID', None
        key_ids.add(payload['apiKeyId'])
        bank_id = payload.get('bankAccountId')
        if bank_id is not None:
            if not _text(bank_id, 140):
                return 'PROVIDER_EVIDENCE_INVALID', None
            bank_ids.add(bank_id)
        metadata = payload.get('metadata')
        if metadata is None:
            missing = True
            continue
        if not isinstance(metadata, dict):
            return 'PROVIDER_EVIDENCE_INVALID', None
        beneficiary, tracking = metadata.get('clabe'), metadata.get('trackingKey')
        if beneficiary is None or tracking is None:
            missing = True
            continue
        if not _clabe(beneficiary) or not _text(tracking, 256):
            return 'PROVIDER_EVIDENCE_INVALID', None
        candidates.add((beneficiary, tracking, intent.amount_minor))
    if len(candidates) > 1 or len(key_ids) > 1 or len(bank_ids) > 1:
        return 'PROVIDER_EVIDENCE_CONFLICT', None
    if missing or not candidates:
        return 'PROVIDER_FIELDS_MISSING', None
    return None, ProviderReport(*next(iter(candidates)))
