"""Compare a signed account identifier with an owner's unverified assertion."""
import decimal
import json

from .app import _no_duplicate_pairs


def account_consistency(provider_status, signature_status, events, claim):
    """Return a status only; never expose account IDs or imply provider binding."""
    if signature_status != 'VERIFIED':
        return 'SIGNATURE_NOT_VERIFIED'
    if provider_status not in (None, 'PROVIDER_FIELDS_MISSING'):
        return 'PROVIDER_EVENT_UNAVAILABLE'
    if claim is None:
        return 'NO_OWNER_REPORT'
    if claim.claim != 'OWNER_REPORTED_VERIFIED':
        return 'OWNER_REPORT_WITHDRAWN'
    if not claim.provider_account_id:
        return 'OWNER_REPORT_NO_ACCOUNT_ID'
    ids = set()
    missing = 0
    try:
        def invalid_constant(_value):
            raise ValueError('Invalid JSON constant')
        for event in events:
            payload = json.loads(bytes(event.raw_body), parse_float=decimal.Decimal,
                                 object_pairs_hook=_no_duplicate_pairs, parse_constant=invalid_constant)
            value = payload.get('bankAccountId')
            if value is None:
                missing += 1
            else:
                ids.add(value)
    except (AttributeError, TypeError, ValueError, RecursionError, decimal.DecimalException):
        return 'PROVIDER_EVENT_UNAVAILABLE'
    if not ids:
        return 'WEBHOOK_ACCOUNT_ID_ABSENT'
    if ids != {claim.provider_account_id}:
        return 'MISMATCH_OWNER_REPORT'
    if missing:
        return 'PARTIAL_MATCH_UNVERIFIED'
    return 'MATCH_OWNER_REPORT_UNVERIFIED'
