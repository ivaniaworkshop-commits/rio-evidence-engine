"""Supplemental adversarial tests added during R007, not part of original R006 ZIP."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import test_verify_push_manifest as fixture
from verify_push_manifest import verify_ref_update, verify_stream, MAX_COMMITS

class SupplementalPushGuardTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.PushGuardTests(methodName='test_valid_new_branch_push_accepted')
        self.f.setUp()
    def tearDown(self):
        self.f.tearDown()
    @property
    def repo(self):
        return self.f.repo
    def test_tag_push_is_denied(self):
        self.f.make_commit('one',valid=True)
        self.f.git('tag','v1')
        result=self.f.git('push','origin','v1',check=False)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('BRANCH_REFS_ONLY',result.stderr)
        r=self.f.git('ls-remote','--tags','origin',check=False)
        self.assertFalse(any('refs/tags/v1' in line for line in r.stdout.splitlines()))
    def test_mixed_branch_push_rejected_as_one_operation(self):
        good_head=self.f.make_commit('good',valid=True)
        self.f.git('checkout','-qb','bad')
        self.f.make_commit('bad',valid=False)
        result=self.f.git('push','origin','feature','bad',check=False)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('COMMIT_MANIFEST_MISMATCH',result.stderr)
        self.assertNotEqual(self.f.remote_ref('feature').returncode,0)
        self.assertNotEqual(self.f.remote_ref('bad').returncode,0)
    def test_commit_span_limit_denies_bounded_history(self):
        for i in range(MAX_COMMITS+1):
            self.f.make_commit(f'revision-{i}',valid=False)
        local_sha=self.f.git('rev-parse','HEAD').stdout.strip()
        with self.assertRaisesRegex(ValueError,'COMMIT_RANGE_LIMIT_EXCEEDED'):
            verify_ref_update(self.repo,'origin','refs/heads/feature',local_sha,'refs/heads/feature','0'*40)
        self.assertNotEqual(self.f.remote_ref('feature').returncode,0)
    def test_valid_named_remote_requires_anchor(self):
        self.f.git('remote','add','mirror',str(self.f.remote))
        self.f.git('fetch','mirror','main')
        head=self.f.make_commit('valid',valid=True)
        result=self.f.git('push','mirror','feature',check=False)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.f.remote_ref().stdout.strip(),head)
    def test_malformed_pre_push_protocol_denied(self):
        with self.assertRaisesRegex(ValueError,'INVALID_PRE_PUSH_LINE'):
            verify_stream(self.repo,'origin',['one two three'])
        with self.assertRaisesRegex(ValueError,'NO_REF_UPDATES'):
            verify_stream(self.repo,'origin',[])

if __name__ == '__main__': unittest.main()
