from dataclasses import replace

import pytest

from rio_pey_codi.reconciliation import BankRecord, ProviderReport, compare_for_review


REPORT = ProviderReport('merchant-fixture', 'tracking-fixture', 123)
RECORD = BankRecord('merchant-fixture', 'tracking-fixture', 123, 'credit', 'fixture-01')


@pytest.mark.parametrize(('records', 'expected'), [
    ([], 'NO_BANK_RECORD'),
    ([RECORD], 'MATCH_CANDIDATE_UNVERIFIED'),
    ([RECORD, RECORD], 'AMBIGUOUS_BANK_RECORDS'),
    ([replace(RECORD, beneficiary='other')], 'DISCREPANCY_REVIEW_REQUIRED'),
    ([replace(RECORD, amount_minor=124)], 'DISCREPANCY_REVIEW_REQUIRED'),
    ([RECORD, replace(RECORD, direction='reversal')], 'REVERSAL_REVIEW_REQUIRED'),
])
def test_review_never_attests_bank_settlement(records, expected):
    assert compare_for_review(REPORT, records) == expected
