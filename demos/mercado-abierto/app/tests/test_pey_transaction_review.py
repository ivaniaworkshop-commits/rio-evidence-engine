"""Synthetic transport and asserted bank records; no provider connection."""
import json
import socket
from dataclasses import replace
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import jsonschema
import pytest

from rio_pey_codi.pey_transaction_review import PageResponse, review_qr_transactions
from rio_pey_codi.reconciliation import BankRecord

QR = "qr-synthetic-123"
CLABE = "0" * 18
TRACKING = "synthetic-tracking"
RECORD = BankRecord(CLABE, TRACKING, 15000, "credit", "statement-fixture")
PAID = {"id": "transaction-synthetic", "status": "PAID", "amount": 150,
        "currency": "MXN", "paymentMethod": "CODI", "datePaid": 1704067260,
        "metadata": {"clabe": CLABE, "trackingKey": TRACKING,
                     "externalMetadata": {"customerEmail": "private@example.test"}}}


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    def blocked(*_args, **_kwargs):
        raise AssertionError("Network access forbidden in synthetic test")
    monkeypatch.setattr(socket, "socket", blocked)


def encoded(items, token=None):
    return PageResponse(200, json.dumps({"items": items, "nextToken": token}).encode())


class FakeTransport:
    def __init__(self, pages):
        self.pages = iter(pages)
        self.calls = []

    def __call__(self, request):
        self.calls.append(request)
        return next(self.pages)


def review(pages, **overrides):
    transport = FakeTransport(pages)
    args = dict(qr_id=QR, expected_amount_minor=15000, bank_records=[RECORD], fetch_page=transport)
    result = review_qr_transactions(**{**args, **overrides})
    return result, transport


def test_two_pages_reuse_reconciliation_without_asserting_settlement_or_leaking_metadata():
    pending = {**PAID, "id": "pending-transaction", "status": "PENDING"}
    del pending["datePaid"]
    token = "synthetic+/= page"
    result, transport = review([encoded([pending], token), encoded([PAID])],
                               expected_transaction_id=PAID["id"])
    assert result.classification == "MATCH_CANDIDATE_UNVERIFIED"
    assert result.pages_read == 2 and result.pagination_ended and result.paid_transactions_observed == 1
    assert not result.bank_payment_confirmed and not result.provider_authenticity_verified
    assert not result.independent_bank_source_verified and not result.beneficiary_binding_verified
    assert not result.temporal_completeness_verified and not result.payment_state_changed
    assert [call.method for call in transport.calls] == ["GET", "GET"]
    assert transport.calls[0].path_and_query == f"/transaction/codi/qr/{QR}"
    parsed = urlsplit(transport.calls[1].path_and_query)
    assert parsed.path == f"/transaction/codi/qr/{QR}"
    assert parse_qs(parsed.query) == {"nextToken": [token]}
    assert token not in repr(transport.calls[1])
    assert all(secret not in repr(result) for secret in (CLABE, TRACKING, "private@example.test"))


@pytest.mark.parametrize(("records", "classification"), [
    ([], "NO_BANK_RECORD"),
    ([RECORD, RECORD], "AMBIGUOUS_BANK_RECORDS"),
    ([replace(RECORD, amount_minor=14999)], "DISCREPANCY_REVIEW_REQUIRED"),
    ([replace(RECORD, beneficiary="1" * 18)], "DISCREPANCY_REVIEW_REQUIRED"),
    ([replace(RECORD, direction="reversal")], "REVERSAL_REVIEW_REQUIRED"),
    ([replace(RECORD, tracking_key="other")], "NO_BANK_RECORD"),
])
def test_reuses_existing_review_classifications(records, classification):
    result, _ = review([encoded([PAID])], bank_records=records)
    assert result.classification == classification
    assert result.pagination_ended and not result.bank_payment_confirmed


def test_incomplete_scan_does_not_return_a_candidate_from_first_page():
    result, transport = review([encoded([PAID], "next")], max_pages=1)
    assert result.classification == "PAGE_LIMIT_EXCEEDED"
    assert not result.pagination_ended and result.paid_transactions_observed is None
    assert len(transport.calls) == 1 and not result.payment_state_changed


def test_cycle_and_duplicate_transactions_fail_closed():
    cycle, transport = review([encoded([], "repeat"), encoded([], "repeat")])
    assert cycle.classification == "PAGINATION_CYCLE" and len(transport.calls) == 2
    duplicate, _ = review([encoded([PAID], "second"), encoded([PAID])])
    assert duplicate.classification == "DUPLICATE_PROVIDER_TRANSACTION"
    assert not cycle.pagination_ended and not duplicate.pagination_ended


def test_multiple_paid_transactions_are_not_silently_reduced_to_first_match():
    other = {**PAID, "id": "second-tx"}
    result, _ = review([encoded([PAID], "second"), encoded([other])])
    assert result.classification == "MULTIPLE_PAID_TRANSACTIONS_REVIEW_REQUIRED"
    assert result.paid_transactions_observed == 2 and not result.bank_payment_confirmed


def test_empty_result_never_proves_no_payment_or_authorizes_retry():
    result, _ = review([encoded([])])
    assert result.classification == "NO_PAID_PROVIDER_TRANSACTION_OBSERVED"
    assert result.pagination_ended and result.paid_transactions_observed == 0
    assert not result.temporal_completeness_verified and not result.payment_state_changed


@pytest.mark.parametrize(("item", "classification"), [
    ({**PAID, "amount": 149.99}, "PROVIDER_AMOUNT_MISMATCH_REVIEW_REQUIRED"),
    ({**PAID, "id": "another-transaction"}, "PROVIDER_TRANSACTION_CONFLICT"),
    ({**PAID, "metadata": None}, "PROVIDER_FIELDS_MISSING"),
    ({**PAID, "metadata": {"trackingKey": TRACKING}}, "PROVIDER_FIELDS_MISSING"),
    ({**PAID, "metadata": {"clabe": "1", "trackingKey": TRACKING}}, "PROVIDER_FIELDS_INVALID"),
    ({**PAID, "metadata": []}, "PROVIDER_FIELDS_INVALID"),
])
def test_inconsistent_paid_transaction_is_held(item, classification):
    result, _ = review([encoded([item])], expected_transaction_id=PAID["id"])
    assert result.classification == classification
    assert not result.bank_payment_confirmed and not result.payment_state_changed


@pytest.mark.parametrize("patch", [
    {"amount": "150.00"}, {"amount": True}, {"amount": 150.001},
    {"currency": "USD"}, {"paymentMethod": "CARD"}, {"status": "REFUNDED"},
    {"datePaid": True}, {"payableId": "another-qr"}, {"payableType": "API_CODI_PN"},
])
def test_wrong_provider_fields_cannot_create_a_candidate(patch):
    result, _ = review([encoded([{**PAID, **patch}])])
    assert result.classification == "PROVIDER_RESPONSE_INVALID"
    assert not result.pagination_ended and not result.bank_payment_confirmed


@pytest.mark.parametrize("body", [
    b'{}', b'{"items":[],"nextToken":null,"nextToken":null}',
    b'{"items":[],"nextToken":""}', b'{"items":[NaN],"nextToken":null}',
    b'x' * 65537, b'\xff',
])
def test_malformed_duplicate_or_oversized_response_fails_closed(body):
    result, _ = review([PageResponse(200, body)])
    assert result.classification == "PROVIDER_RESPONSE_INVALID" and not result.pagination_ended


def test_more_than_twenty_items_rejected():
    items = [{**PAID, "id": f"tx-{n}"} for n in range(21)]
    result, _ = review([encoded(items)])
    assert result.classification == "PROVIDER_RESPONSE_INVALID"


def test_404_and_transport_failure_do_not_imply_no_payment_or_leak_error():
    http, _ = review([PageResponse(404, b"sensitive provider body")])
    assert http.classification == "PROVIDER_HTTP_ERROR" and not http.pagination_ended
    def failing(_):
        raise RuntimeError("sensitive exception value")
    failed, _ = review([], fetch_page=failing)
    assert failed.classification == "PROVIDER_TRANSPORT_UNAVAILABLE"
    assert "sensitive" not in repr(failed) and not failed.pagination_ended


@pytest.mark.parametrize(("kwargs", "classification"), [
    ({"qr_id": None}, "QR_ID_REQUIRED"),
    ({"qr_id": "../bad"}, "QR_ID_INVALID"),
    ({"expected_amount_minor": True}, "REVIEW_INPUT_INVALID"),
    ({"expected_amount_minor": 0}, "REVIEW_INPUT_INVALID"),
    ({"max_pages": 11}, "REVIEW_INPUT_INVALID"),
    ({"max_pages": True}, "REVIEW_INPUT_INVALID"),
    ({"bank_records": [replace(RECORD, direction="unknown")]}, "REVIEW_INPUT_INVALID"),
])
def test_invalid_input_never_calls_transport(kwargs, classification):
    result, transport = review([], **kwargs)
    assert result.classification == classification
    assert not transport.calls and not result.bank_payment_confirmed


def test_pending_transaction_is_not_treated_as_paid():
    pending = {**PAID, "status": "PENDING"}
    del pending["datePaid"]
    result, _ = review([encoded([pending])])
    assert result.classification == "NO_PAID_PROVIDER_TRANSACTION_OBSERVED"
    assert result.paid_transactions_observed == 0 and not result.bank_payment_confirmed


def test_bank_record_list_is_snapshotted_before_transport_can_mutate_it():
    records = [RECORD]
    def mutating_transport(_request):
        records.clear()
        return encoded([PAID])
    result = review_qr_transactions(qr_id=QR, expected_amount_minor=15000,
                                    bank_records=records, fetch_page=mutating_transport)
    assert records == []
    assert result.classification == "MATCH_CANDIDATE_UNVERIFIED"
    assert not result.independent_bank_source_verified and not result.bank_payment_confirmed


def test_synthetic_page_matches_pinned_provider_schema_and_missing_cursor_holds():
    fixture = json.loads((Path(__file__).parent / "fixtures" /
                          "pey-qr-transactions-contract-2026-10-20.json").read_text())
    assert fixture["source_sha256"] == "497f48eb8047d88b1c8672fcb252eb8c7eee46546acaeb01440cfac8cd37335a"
    assert fixture["path"] == "/transaction/codi/qr/{id}" and fixture["method"] == "GET"
    assert {p["name"] for p in fixture["parameters"]} == {"id", "nextToken"}
    validator = jsonschema.Draft202012Validator(fixture["response_schema"])
    validator.validate({"items": [PAID], "nextToken": None})
    # The published schema does not mark nextToken required, but omission must
    # not be interpreted as the end of pagination in this recovery review.
    validator.validate({"items": []})
    outcome, _ = review([PageResponse(200, b'{"items":[]}')])
    assert outcome.classification == "PROVIDER_RESPONSE_INVALID"
    assert not outcome.pagination_ended
