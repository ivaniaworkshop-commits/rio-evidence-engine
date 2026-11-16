"""Read-only QR transaction review using an injected transport.

No network transport, API key, persistence, endpoint, or payment state change is
provided here. Pagination ending is not proof of a consistent provider snapshot.
"""
from __future__ import annotations

import decimal
import json
import re
from dataclasses import dataclass
from typing import Callable
from urllib.parse import quote, urlencode

from .app import _no_duplicate_pairs, parse_provider_amount
from .reconciliation import BankRecord, ProviderReport, compare_for_review

MAX_RESPONSE = 65536
MAX_PAGES = 10
QR_ID = re.compile(r"[A-Za-z0-9_-]{1,140}\Z")


@dataclass(frozen=True, repr=False)
class PageRequest:
    method: str
    path_and_query: str

    def __repr__(self):
        return "PageRequest(GET, redacted)"


@dataclass(frozen=True, repr=False)
class PageResponse:
    status: int
    body: bytes

    def __repr__(self):
        return "PageResponse(redacted)"


@dataclass(frozen=True)
class ReviewOutcome:
    classification: str
    pages_read: int
    pagination_ended: bool = False
    paid_transactions_observed: int | None = None
    bank_payment_confirmed: bool = False
    provider_authenticity_verified: bool = False
    independent_bank_source_verified: bool = False
    beneficiary_binding_verified: bool = False
    temporal_completeness_verified: bool = False
    payment_state_changed: bool = False


def _text(value, limit):
    return (isinstance(value, str) and 0 < len(value) <= limit and
            value == value.strip() and value.isprintable())


def _clabe(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9]{18}", value) is not None


def _valid_records(records):
    return (isinstance(records, tuple) and len(records) <= 50 and all(
        type(r) is BankRecord and _clabe(r.beneficiary) and _text(r.tracking_key, 256)
        and type(r.amount_minor) is int and 0 < r.amount_minor <= 100_000_000
        and r.direction in ("credit", "reversal") and _text(r.evidence_reference, 100)
        and isinstance(r.currency, str) and re.fullmatch(r"[A-Z]{3}", r.currency)
        for r in records
    ))


def _no_constant(_):
    raise ValueError("Invalid JSON number")


def _request(qr_id, token):
    path = "/transaction/codi/qr/" + quote(qr_id, safe="")
    if token is not None:
        path += "?" + urlencode({"nextToken": token})
    return PageRequest("GET", path)


def review_qr_transactions(*, qr_id: str | None, expected_amount_minor: int,
                           bank_records: list[BankRecord], fetch_page: Callable[[PageRequest], PageResponse],
                           expected_transaction_id: str | None = None,
                           max_pages: int = MAX_PAGES) -> ReviewOutcome:
    """Classify a bounded, read-only scan; input and bank records are untrusted.

    A future caller must establish merchant/QR ownership and authenticate its
    transport separately. A candidate never confirms settlement or permits a
    new charge. Any incomplete or ambiguous scan returns a review-only hold.
    """
    if qr_id is None or qr_id == "":
        return ReviewOutcome("QR_ID_REQUIRED", 0)
    if not isinstance(qr_id, str) or not QR_ID.fullmatch(qr_id):
        return ReviewOutcome("QR_ID_INVALID", 0)
    if type(bank_records) is not list or len(bank_records) > 50:
        return ReviewOutcome("REVIEW_INPUT_INVALID", 0)
    records = tuple(bank_records)
    if (type(expected_amount_minor) is not int or not 0 < expected_amount_minor <= 100_000_000
            or type(max_pages) is not int or not 1 <= max_pages <= MAX_PAGES
            or not callable(fetch_page) or not _valid_records(records)
            or (expected_transaction_id is not None and not _text(expected_transaction_id, 140))):
        return ReviewOutcome("REVIEW_INPUT_INVALID", 0)

    token = None
    seen_tokens, seen_ids = set(), set()
    paid = []
    pages = 0
    while True:
        try:
            response = fetch_page(_request(qr_id, token))
        except Exception:
            return ReviewOutcome("PROVIDER_TRANSPORT_UNAVAILABLE", pages)
        if not isinstance(response, PageResponse) or type(response.status) is not int:
            return ReviewOutcome("PROVIDER_RESPONSE_INVALID", pages)
        if response.status != 200:
            return ReviewOutcome("PROVIDER_HTTP_ERROR", pages)
        if not isinstance(response.body, bytes) or len(response.body) > MAX_RESPONSE:
            return ReviewOutcome("PROVIDER_RESPONSE_INVALID", pages)
        try:
            page = json.loads(response.body, parse_float=decimal.Decimal,
                              object_pairs_hook=_no_duplicate_pairs, parse_constant=_no_constant)
            if (not isinstance(page, dict) or "items" not in page or "nextToken" not in page
                    or not isinstance(page["items"], list) or len(page["items"]) > 20):
                raise ValueError("Invalid page")
            next_token = page["nextToken"]
            if next_token is not None and not _text(next_token, 2048):
                raise ValueError("Invalid continuation")
            for item in page["items"]:
                if not isinstance(item, dict) or not _text(item.get("id"), 140):
                    raise ValueError("Invalid transaction")
                if item["id"] in seen_ids:
                    return ReviewOutcome("DUPLICATE_PROVIDER_TRANSACTION", pages)
                seen_ids.add(item["id"])
                amount = item.get("amount")
                if (item.get("status") not in ("PAID", "PENDING") or item.get("currency") != "MXN"
                        or item.get("paymentMethod") != "CODI" or isinstance(amount, bool)
                        or not isinstance(amount, (int, decimal.Decimal))
                        or ("payableId" in item and item["payableId"] != qr_id)
                        or ("payableType" in item and item["payableType"] != "API_CODI_QR")):
                    raise ValueError("Invalid transaction fields")
                minor = parse_provider_amount(amount)
                date_paid = item.get("datePaid")
                if date_paid is not None and (type(date_paid) is not int or date_paid <= 0
                                              or item["status"] != "PAID"):
                    raise ValueError("Invalid paid timestamp")
                if item["status"] == "PAID":
                    metadata = item.get("metadata")
                    if isinstance(metadata, dict):
                        metadata = {"clabe": metadata.get("clabe"),
                                    "trackingKey": metadata.get("trackingKey")}
                    elif metadata is not None:
                        metadata = False  # Retain neither unrelated values nor sensitive metadata.
                    paid.append((item["id"], minor, metadata))
        except (ValueError, TypeError, OverflowError, RecursionError, decimal.DecimalException):
            return ReviewOutcome("PROVIDER_RESPONSE_INVALID", pages)
        pages += 1
        if next_token is None:
            break
        if next_token in seen_tokens:
            return ReviewOutcome("PAGINATION_CYCLE", pages)
        seen_tokens.add(next_token)
        if pages >= max_pages:
            return ReviewOutcome("PAGE_LIMIT_EXCEEDED", pages)
        token = next_token

    def completed(classification):
        return ReviewOutcome(classification, pages, pagination_ended=True,
                             paid_transactions_observed=len(paid))

    if not paid:
        return completed("NO_PAID_PROVIDER_TRANSACTION_OBSERVED")
    if len(paid) != 1:
        return completed("MULTIPLE_PAID_TRANSACTIONS_REVIEW_REQUIRED")
    transaction_id, amount_minor, metadata = paid[0]
    if expected_transaction_id is not None and transaction_id != expected_transaction_id:
        return completed("PROVIDER_TRANSACTION_CONFLICT")
    if amount_minor != expected_amount_minor:
        return completed("PROVIDER_AMOUNT_MISMATCH_REVIEW_REQUIRED")
    if metadata is None:
        return completed("PROVIDER_FIELDS_MISSING")
    if not isinstance(metadata, dict):
        return completed("PROVIDER_FIELDS_INVALID")
    beneficiary, tracking = metadata.get("clabe"), metadata.get("trackingKey")
    if beneficiary is None or tracking is None:
        return completed("PROVIDER_FIELDS_MISSING")
    if not _clabe(beneficiary) or not _text(tracking, 256):
        return completed("PROVIDER_FIELDS_INVALID")
    return completed(compare_for_review(ProviderReport(beneficiary, tracking, amount_minor), records))
