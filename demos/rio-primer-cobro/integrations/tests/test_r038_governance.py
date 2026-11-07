"""R038 adversarial review and policy tests; synthetic data never counts as real protection."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from r038_governance import blueprint, evaluate, GateError, TARGET, BASE, BASE_REF, BASE_RULESET_NAME, CHECKS, RULESET_CHECKS, APP_ID

HEAD = 'a' * 40


def fixtures():
    rules = [blueprint(), blueprint(BASE_REF, BASE_RULESET_NAME)]
    pr = {'number': 41, 'state': 'open', 'draft': False, 'merged': False,
          'head': {'ref': TARGET.removeprefix('refs/heads/'), 'sha': HEAD, 'repo': {'full_name': 'ivaniaworkshop-commits/rio-evidence-engine'}},
          'base': {'ref': BASE, 'sha': '5ee14ce6ca1a7e76a23d94e9804dabd4911f88dc', 'repo': {'full_name': 'ivaniaworkshop-commits/rio-evidence-engine'}}, 'user': {'login': 'author'}}
    reviews = [{'id': 100, 'state': 'APPROVED', 'commit_id': HEAD, 'user': {'login': 'other'}}]
    checks = {'total_count': len(CHECKS), 'check_runs': [
        {'name': c, 'head_sha': HEAD, 'status': 'completed', 'conclusion': 'success',
         'app': {'id': APP_ID}} for c in CHECKS]}
    return rules, pr, reviews, checks


class GovernanceR038Tests(unittest.TestCase):
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
    def test_dual_rulesets_require_r038_policy_hold(self):
        x = self.check(lambda d: d[0][0]['rules'][-1]['parameters']['required_status_checks'].pop())
        self.assertFalse(x['candidate_ruleset_observed'])
    def test_policy_hold_not_circular_dependency(self):
        x = self.check()
        self.assertEqual(x['required_ci_contexts'], list(CHECKS))
        self.assertIn('r038-policy-hold', RULESET_CHECKS)
        self.assertNotIn('r038-policy-hold', CHECKS)
    def test_no_parser_claim_of_review_pagination_proof(self):
        self.assertFalse(self.check()['review_history_complete_verified_by_parser'])
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

    def test_dismissed_old_approval_no_longer_counts(self):
        def mutate(d):
            d[2].append({'id': 101, 'state': 'DISMISSED', 'commit_id': HEAD, 'user': {'login': 'other'}})
        x = self.check(mutate)
        self.assertIn('INDEPENDENT_REVIEW_NOT_OBSERVED', x['blockers'])
    def test_request_changes_overrides_old_approval(self):
        def mutate(d):
            d[2].append({'id': 101, 'state': 'CHANGES_REQUESTED', 'commit_id': HEAD, 'user': {'login': 'other'}})
        x = self.check(mutate)
        self.assertIn('CHANGES_REQUESTED_OUTSTANDING', x['blockers'])
        self.assertIn('INDEPENDENT_REVIEW_NOT_OBSERVED', x['blockers'])
    def test_outstanding_changes_request_from_third_party_blocks(self):
        def mutate(d):
            d[2].append({'id': 110, 'state': 'CHANGES_REQUESTED', 'commit_id': HEAD, 'user': {'login': 'third'}})
        self.assertIn('CHANGES_REQUESTED_OUTSTANDING', self.check(mutate)['blockers'])
    def test_newer_valid_approval_supersedes_changes_request(self):
        def mutate(d):
            d[2].extend([
              {'id': 101, 'state': 'CHANGES_REQUESTED', 'commit_id': HEAD, 'user': {'login': 'third'}},
              {'id': 103, 'state': 'APPROVED', 'commit_id': HEAD, 'user': {'login': 'third'}}])
        self.assertEqual(self.check(mutate)['result'], 'POLICY_AND_REVIEW_PREREQUISITES_OBSERVED')
    def test_reverse_api_order_keeps_newest_review(self):
        def mutate(d):
            d[2].insert(0, {'id': 102, 'state': 'DISMISSED', 'commit_id': HEAD, 'user': {'login': 'other'}})
        self.assertIn('INDEPENDENT_REVIEW_NOT_OBSERVED', self.check(mutate)['blockers'])
    def test_duplicate_review_identity_rejected(self):
        def mutate(d):
            d[2].append({'id': 100, 'state': 'APPROVED', 'commit_id': HEAD, 'user': {'login': 'other'}})
        with self.assertRaisesRegex(GateError, 'DUPLICATE_REVIEW_ID'):
            self.check(mutate)
    def test_review_without_numeric_id_rejected(self):
        with self.assertRaisesRegex(GateError, 'MALFORMED_REVIEW_ID'):
            self.check(lambda d: d[2][0].pop('id'))
    def test_reviewer_changed_name_case_insensitive(self):
        def mutate(d):
            d[2].append({'id': 101, 'state': 'DISMISSED', 'commit_id': HEAD, 'user': {'login': 'OTHER'}})
        self.assertIn('INDEPENDENT_REVIEW_NOT_OBSERVED', self.check(mutate)['blockers'])
    def test_base_sha_moved_blocks(self):
        self.assertIn('PR_NOT_READY_OR_IDENTITY_MISMATCH', self.check(lambda d: d[1]['base'].update(sha='0'*40))['blockers'])
    def test_forked_head_blocks(self):
        self.assertIn('PR_NOT_READY_OR_IDENTITY_MISMATCH', self.check(lambda d: d[1]['head']['repo'].update(full_name='foreign/fork'))['blockers'])
    def test_foreign_base_repo_blocks(self):
        self.assertIn('PR_NOT_READY_OR_IDENTITY_MISMATCH', self.check(lambda d: d[1]['base']['repo'].update(full_name='foreign/repo'))['blockers'])
    def test_merged_pr_blocks(self):
        self.assertIn('PR_NOT_READY_OR_IDENTITY_MISMATCH', self.check(lambda d: d[1].update(merged=True))['blockers'])
    def test_unknown_review_state_rejected(self):
        with self.assertRaisesRegex(GateError, 'UNKNOWN_REVIEW_STATE'):
            self.check(lambda d: d[2][0].update(state='SOMETHING_ELSE'))
    def test_self_review_cannot_override_external_dismissal(self):
        def mutate(d):
            d[2].append({'id': 101, 'state': 'DISMISSED', 'commit_id': HEAD, 'user': {'login': 'other'}})
            d[2].append({'id': 102, 'state': 'APPROVED', 'commit_id': HEAD, 'user': {'login': 'author'}})
        self.assertIn('INDEPENDENT_REVIEW_NOT_OBSERVED', self.check(mutate)['blockers'])


if __name__ == '__main__':
    unittest.main()
