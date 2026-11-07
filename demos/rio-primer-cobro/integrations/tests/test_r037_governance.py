"""R037 adversarial policy tests; synthetic data never counts as real protection."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from r037_governance import blueprint, evaluate, GateError, TARGET, BASE, BASE_REF, BASE_RULESET_NAME, CHECKS, APP_ID

HEAD = 'a' * 40


def fixtures():
    rules = [blueprint(), blueprint(BASE_REF, BASE_RULESET_NAME)]
    pr = {'number': 41, 'state': 'open', 'draft': False,
          'head': {'ref': TARGET.removeprefix('refs/heads/'), 'sha': HEAD},
          'base': {'ref': BASE}, 'user': {'login': 'author'}}
    reviews = [{'state': 'APPROVED', 'commit_id': HEAD, 'user': {'login': 'other'}}]
    checks = {'total_count': len(CHECKS), 'check_runs': [
        {'name': c, 'head_sha': HEAD, 'status': 'completed', 'conclusion': 'success',
         'app': {'id': APP_ID}} for c in CHECKS]}
    return rules, pr, reviews, checks


class GovernanceR037Tests(unittest.TestCase):
    def check(self, mutate=None):
        d = list(copy.deepcopy(fixtures()))
        if mutate:
            mutate(d)
        return evaluate(*d, HEAD)

    def test_synthetic_contract_meets_prerequisites_not_production(self):
        x = self.check()
        self.assertEqual(x['result'], 'POLICY_AND_REVIEW_PREREQUISITES_OBSERVED')
        self.assertFalse(x['production_authorized'])
    def test_actual_current_missing_ruleset_blocks(self):
        x = self.check(lambda d: d[0].clear())
        self.assertIn('NO_UNIQUE_EXACT_ACTIVE_CANDIDATE_RULESET', x['blockers'])
        self.assertIn('NO_UNIQUE_EXACT_ACTIVE_REVIEW_BASE_RULESET', x['blockers'])
    def test_missing_review_base_ruleset_blocks(self):
        x = self.check(lambda d: d[0].pop())
        self.assertIn('NO_UNIQUE_EXACT_ACTIVE_REVIEW_BASE_RULESET', x['blockers'])
    def test_review_base_not_confusable_with_main(self):
        x = self.check(lambda d: d[0][1]['conditions']['ref_name'].update(include=['refs/heads/main']))
        self.assertFalse(x['review_base_ruleset_observed'])
    def test_review_missing_blocks(self):
        x = self.check(lambda d: d[2].clear())
        self.assertIn('INDEPENDENT_REVIEW_NOT_OBSERVED', x['blockers'])
    def test_self_review_not_independent(self):
        x = self.check(lambda d: d[2][0]['user'].update(login='author'))
        self.assertIn('INDEPENDENT_REVIEW_NOT_OBSERVED', x['blockers'])
    def test_stale_review_commit_fails(self):
        x = self.check(lambda d: d[2][0].update(commit_id='b'*40))
        self.assertIn('INDEPENDENT_REVIEW_NOT_OBSERVED', x['blockers'])
    def test_draft_blocks(self):
        x = self.check(lambda d: d[1].update(draft=True))
        self.assertIn('PR_NOT_READY_OR_IDENTITY_MISMATCH', x['blockers'])
    def test_wrong_head_blocks(self):
        x = self.check(lambda d: d[1]['head'].update(sha='b'*40))
        self.assertIn('PR_NOT_READY_OR_IDENTITY_MISMATCH', x['blockers'])
    def test_main_only_ruleset_not_valid(self):
        x = self.check(lambda d: d[0][0]['conditions']['ref_name'].update(include=['refs/heads/main']))
        self.assertFalse(x['ruleset_contract_observed'])
    def test_bypass_denied(self):
        x = self.check(lambda d: d[0][0].update(bypass_actors=[{'actor_id': 1}]))
        self.assertFalse(x['ruleset_contract_observed'])
    def test_missing_check_denied(self):
        x = self.check(lambda d: d[0][0]['rules'][-1]['parameters']['required_status_checks'].pop())
        self.assertFalse(x['ruleset_contract_observed'])
    def test_fake_check_producer_denied(self):
        x = self.check(lambda d: d[3]['check_runs'][0]['app'].update(id=9999))
        self.assertIn('TRUSTED_CI_NOT_ALL_SUCCESS_VERIFY', x['blockers'])
    def test_failed_check_denied(self):
        x = self.check(lambda d: d[3]['check_runs'][0].update(conclusion='failure'))
        self.assertIn('TRUSTED_CI_NOT_ALL_SUCCESS_VERIFY', x['blockers'])
    def test_missing_check_runs_denied(self):
        x = self.check(lambda d: d[3]['check_runs'].pop())
        self.assertTrue(any(x.startswith('TRUSTED_CI_NOT_ALL_SUCCESS_') for x in x['blockers']))
    def test_truncated_checks_denied(self):
        x = self.check(lambda d: d[3].update(total_count=100))
        self.assertIn('TRUNCATED_CHECK_RUNS', x['blockers'])
    def test_non_strict_checks_denied(self):
        x = self.check(lambda d: d[0][0]['rules'][-1]['parameters'].update(strict_required_status_checks_policy=False))
        self.assertFalse(x['ruleset_contract_observed'])
    def test_stale_approvals_allowed_only_after_push_blocks(self):
        x = self.check(lambda d: d[0][0]['rules'][2]['parameters'].update(dismiss_stale_reviews_on_push=False))
        self.assertFalse(x['ruleset_contract_observed'])
    def test_non_list_rulesets_fail_closed(self):
        with self.assertRaises(GateError):
            evaluate({}, *fixtures()[1:], HEAD)


if __name__ == '__main__':
    unittest.main()
