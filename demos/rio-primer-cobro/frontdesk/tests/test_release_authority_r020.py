import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release_authority_r020 import assess

def fixture(pattern='refs/heads/deploy/primer-cobro', approvals=1, bypass=None):
    return [{'target': 'branch', 'enforcement': 'active',
        'conditions': {'ref_name': {'include': [pattern], 'exclude': []}},
        'bypass_actors': bypass or [],
        'rules': [{'type': 'pull_request', 'parameters': {'required_approving_review_count': approvals}},
                  {'type': 'deletion'}, {'type': 'non_fast_forward'}]}]

class ReleaseAuthority(unittest.TestCase):
    def test_exact_ruleset_pass(self):
        self.assertEqual(assess(fixture())['result'], 'PASS_RULESET_POLICY_CONTRACT')
    def test_empty_fail(self):
        with self.assertRaisesRegex(ValueError, 'NO_ACTIVE'): assess([])
    def test_wrong_branch_fail(self):
        with self.assertRaisesRegex(ValueError, 'NO_ACTIVE'): assess(fixture('refs/heads/main'))
    def test_no_approvals_fail(self):
        with self.assertRaisesRegex(ValueError, 'BRANCH_GUARDS_MISSING'): assess(fixture(approvals=0))
    def test_bypass_fail(self):
        with self.assertRaisesRegex(ValueError, 'BYPASS'): assess(fixture(bypass=[{'actor_id':123,'actor_type':'Team','bypass_mode':'always'}]))
    def test_inactive_fail(self):
        x=fixture();x[0]['enforcement']='evaluate'
        with self.assertRaisesRegex(ValueError, 'NO_ACTIVE'): assess(x)
    def test_wildcard_allow(self):
        self.assertEqual(assess(fixture('refs/heads/deploy/*'))['result'], 'PASS_RULESET_POLICY_CONTRACT')
    def test_exclusion_fail(self):
        x=fixture('refs/heads/deploy/*');x[0]['conditions']['ref_name']['exclude']=['refs/heads/deploy/primer-cobro']
        with self.assertRaisesRegex(ValueError, 'NO_ACTIVE'): assess(x)
    def test_missing_nonfastforward_fail(self):
        x=fixture();x[0]['rules']=x[0]['rules'][:-1]
        with self.assertRaisesRegex(ValueError, 'non_fast_forward'): assess(x)

if __name__ == '__main__': unittest.main()
