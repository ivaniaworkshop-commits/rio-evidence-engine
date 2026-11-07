"""R036 adversarial local Git tests: audit every snapshot, not only HEAD."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_r036 import audit, AuditError


class IndependentHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run_git('init', '-q', '-b', 'testmain')
        self.run_git('config', 'user.email', 'ci@example.invalid')
        self.run_git('config', 'user.name', 'R036 Test')
        self.pay = 'demos/rio-primer-cobro/integrations/pey_evidence_r027.mjs'
        self.fixture = 'demos/rio-primer-cobro/tests/test_pey_r026.mjs'
        self.write('a.txt', 'baseline\n')
        self.write(self.pay, 'synthetic\n')
        self.write(self.fixture, 'legacy fixture\n')
        self.commit('trusted anchor')
        self.anchor = self.sha('HEAD')
        self.write('a.txt', 'new\n')
        self.commit('atomic candidate')
        self.checkpoint = self.sha('HEAD')
        self.tree = self.sha('HEAD^{tree}')

    def run_git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.DEVNULL).decode().strip()

    def sha(self, ref):
        return self.run_git('rev-parse', ref)

    def write(self, path, text):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')

    def commit(self, message, manifest=True):
        if manifest:
            files = []
            for p in sorted(self.root.rglob('*')):
                if not p.is_file() or '.git' in p.parts or p.name == 'MANIFEST.json':
                    continue
                b = p.read_bytes()
                files.append({'path': p.relative_to(self.root).as_posix(), 'bytes': len(b),
                              'sha256': hashlib.sha256(b).hexdigest()})
            self.write('MANIFEST.json', json.dumps({'scope': 'SOURCE_BYTES_NOT_TRUTH_OR_AUTHENTICITY', 'files': files})+'\n')
        self.run_git('add', '-A')
        self.run_git('commit', '-qm', message)

    def check(self):
        return audit(self.root, anchor=self.anchor, checkpoint=self.checkpoint,
                     checkpoint_tree=self.tree, fixture_blob=self.run_git('rev-parse', self.anchor + ':' + self.fixture),
                     sensitive=(self.pay, self.fixture))

    def test_valid_checkpoint(self):
        self.assertEqual(self.check()['checked_snapshots'], 2)

    def test_valid_successor(self):
        self.write('a.txt', 'latest\n')
        self.commit('followup')
        self.assertEqual(self.check()['checked_snapshots'], 3)

    def test_dirty_intermediate_cannot_be_repaired_at_head(self):
        self.write(self.pay, '123456789012345678\n')
        self.commit('bad intermediate')
        self.write(self.pay, 'clean again\n')
        self.commit('apparently clean head')
        with self.assertRaisesRegex(AuditError, 'SELECTED_PAYMENT_IDENTIFIER_FOUND'):
            self.check()

    def test_manifest_omission(self):
        self.write('untracked-by-manifest.txt', 'secret\n')
        self.commit('manifest missing', manifest=False)
        with self.assertRaisesRegex(AuditError, 'MANIFEST_TREE_MISMATCH'):
            self.check()

    def test_manifest_stale_hash(self):
        self.write('a.txt', 'other value\n')
        self.commit('stale hash', manifest=False)
        with self.assertRaisesRegex(AuditError, 'MANIFEST_SOURCE_MISMATCH'):
            self.check()

    def test_duplicate_json_keys_fail(self):
        self.write('MANIFEST.json', '{"files":[],"files":[]}\n')
        self.run_git('add', '-A')
        self.run_git('commit', '-qm', 'duplicate keys')
        with self.assertRaisesRegex(AuditError, 'DUPLICATE_JSON_KEY'):
            self.check()

    def test_non_linear_merge_fails(self):
        self.run_git('branch', 'other', self.checkpoint)
        self.write('main-note.txt', 'on main\n')
        self.commit('main change')
        self.run_git('checkout', '-q', 'other')
        self.write('other-note.txt', 'other\n')
        self.commit('other branch')
        self.run_git('checkout', '-q', 'testmain')
        self.run_git('merge', '-q', '-s', 'ours', '--no-ff', '-m', 'merge histories', 'other')
        with self.assertRaisesRegex(AuditError, 'NONLINEAR_HISTORY'):
            self.check()

    def test_wrong_checkpoint_tree_fails(self):
        with self.assertRaisesRegex(AuditError, 'CHECKPOINT_TREE_MISMATCH'):
            audit(self.root, anchor=self.anchor, checkpoint=self.checkpoint,
                  checkpoint_tree='0'*40)

    def test_unrelated_anchor_fails(self):
        with self.assertRaises(AuditError):
            audit(self.root, anchor='a'*40, checkpoint=self.checkpoint,
                  checkpoint_tree=self.tree)

    def test_sensitive_pattern_in_current_revision_fails(self):
        self.write(self.pay, 'not a bank account: 999999999999999999\n')
        self.commit('new unreviewed identifier')
        with self.assertRaisesRegex(AuditError, 'SELECTED_PAYMENT_IDENTIFIER_FOUND'):
            self.check()

if __name__ == '__main__':
    unittest.main()
