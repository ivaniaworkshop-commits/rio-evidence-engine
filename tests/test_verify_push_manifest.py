"""Real Git-to-bare-remote regressions for the opt-in pre-push guard."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SOURCES = Path(__file__).resolve().parents[1]


class PushGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.parent = Path(self.temp.name)
        self.repo = self.parent / 'working'
        self.remote = self.parent / 'origin.git'
        subprocess.run(['git', 'init', '--bare', '-q', '--initial-branch=main', str(self.remote)], check=True)
        subprocess.run(['git', 'init', '-q', '--initial-branch=main', str(self.repo)], check=True)
        self.git('config', 'user.name', 'RÍO fixture')
        self.git('config', 'user.email', 'rio-fixture@example.invalid')
        self.git('remote', 'add', 'origin', str(self.remote))
        for name in ('scripts/prepare_staged_manifest.py', 'scripts/commit_staged_manifest.py',
                     'scripts/verify_push_manifest.py', '.githooks/pre-push'):
            target = self.repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCES / name, target)
            if name.endswith('pre-push'):
                target.chmod(0o755)
        (self.repo/'app.txt').write_text('baseline')
        self.git('add', '.')
        self.prepare()
        self.git('commit', '-qm', 'baseline')
        self.git('push', '--no-verify', '-u', 'origin', 'main')
        self.git('config', 'core.hooksPath', '.githooks')
        self.git('checkout', '-qb', 'feature')

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args, check=True):
        return subprocess.run(['git', '-C', str(self.repo), *args],
                              check=check, capture_output=True, text=True)

    def prepare(self):
        return subprocess.run([sys.executable, str(self.repo/'scripts/prepare_staged_manifest.py'),
                               '--prepare'], check=True, capture_output=True, text=True)

    def make_commit(self, content, valid=True):
        (self.repo/'app.txt').write_text(content)
        self.git('add', 'app.txt')
        if valid:
            self.prepare()
            self.git('commit', '-qm', 'valid source+manifest')
        else:
            self.git('-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'bad source-only')
        return self.git('rev-parse', 'HEAD').stdout.strip()

    def remote_ref(self, name='feature'):
        return subprocess.run(['git', '--git-dir', str(self.remote), 'show-ref', '--verify',
                               '--hash', f'refs/heads/{name}'],
                              check=False, capture_output=True, text=True)

    def test_valid_new_branch_push_accepted(self):
        head = self.make_commit('one', valid=True)
        x = self.git('push', 'origin', 'feature', check=False)
        self.assertEqual(x.returncode, 0, x.stderr)
        self.assertEqual(self.remote_ref().stdout.strip(), head)

    def test_invalid_final_commit_rejected_and_remote_untouched(self):
        self.make_commit('bad', valid=False)
        x = self.git('push', 'origin', 'feature', check=False)
        self.assertNotEqual(x.returncode, 0)
        self.assertIn('COMMIT_MANIFEST_MISMATCH', x.stderr)
        self.assertNotEqual(self.remote_ref().returncode, 0)

    def test_bad_intermediate_commit_cannot_be_hidden_by_good_head(self):
        first = self.make_commit('first', valid=True)
        self.assertEqual(self.git('push', 'origin', 'feature').returncode, 0)
        self.make_commit('bad-intermediate', valid=False)
        self.make_commit('repaired-final', valid=True)
        x = self.git('push', 'origin', 'feature', check=False)
        self.assertNotEqual(x.returncode, 0)
        self.assertIn('COMMIT_MANIFEST_MISMATCH', x.stderr)
        self.assertEqual(self.remote_ref().stdout.strip(), first)

    def test_protected_main_denied_even_when_manifest_valid(self):
        self.git('checkout', '-q', 'main')
        initial = self.remote_ref('main').stdout.strip()
        self.make_commit('changed-main', valid=True)
        x = self.git('push', 'origin', 'main', check=False)
        self.assertNotEqual(x.returncode, 0)
        self.assertIn('PROTECTED_TARGET_DENIED', x.stderr)
        self.assertEqual(self.remote_ref('main').stdout.strip(), initial)

    def test_missing_fetched_main_anchor_blocks_new_branch(self):
        self.make_commit('one', valid=True)
        self.git('update-ref', '-d', 'refs/remotes/origin/main')
        x = self.git('push', 'origin', 'feature', check=False)
        self.assertNotEqual(x.returncode, 0)
        self.assertNotEqual(self.remote_ref().returncode, 0)

    def test_remote_branch_delete_is_denied(self):
        self.make_commit('one', valid=True)
        self.assertEqual(self.git('push', 'origin', 'feature').returncode, 0)
        previous = self.remote_ref().stdout.strip()
        x = self.git('push', 'origin', ':feature', check=False)
        self.assertNotEqual(x.returncode, 0)
        self.assertIn('REMOTE_DELETION_DENIED', x.stderr)
        self.assertEqual(self.remote_ref().stdout.strip(), previous)

    def test_valid_update_of_existing_branch(self):
        self.make_commit('one', valid=True)
        self.assertEqual(self.git('push', 'origin', 'feature').returncode, 0)
        final = self.make_commit('two', valid=True)
        x = self.git('push', 'origin', 'feature', check=False)
        self.assertEqual(x.returncode, 0, x.stderr)
        self.assertEqual(self.remote_ref().stdout.strip(), final)


if __name__ == '__main__':
    unittest.main()
