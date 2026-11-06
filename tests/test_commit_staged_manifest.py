"""Deterministic local commit-producer tests using disposable Git repositories."""
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
SPEC = importlib.util.spec_from_file_location('commit_staged_manifest', ROOT / 'scripts/commit_staged_manifest.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CommitProducerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'RÍO test')
        self.git('config', 'user.email', 'rio-test@example.invalid')
        for name in ('prepare_staged_manifest.py', 'commit_staged_manifest.py'):
            target = self.root / 'scripts' / name
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(ROOT / 'scripts' / name, target)
        (self.root / 'app.txt').write_text('one', encoding='utf-8')
        self.git('add', 'scripts/prepare_staged_manifest.py',
                 'scripts/commit_staged_manifest.py', 'app.txt')
        subprocess.run([sys.executable, str(self.root / 'scripts/prepare_staged_manifest.py'),
                        '--prepare'], check=True, capture_output=True)
        self.git('commit', '-qm', 'baseline')

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args],
                              check=True, capture_output=True, text=True).stdout.strip()

    def test_source_and_manifest_same_commit(self):
        before = self.git('rev-parse', 'HEAD')
        (self.root / 'app.txt').write_text('two', encoding='utf-8')
        self.git('add', 'app.txt')
        result = MODULE.commit_staged(self.root, 'approved', expected_head=before)
        self.assertEqual(result['status'], 'LOCAL_COMMIT_READBACK_PASS')
        self.assertEqual(result['parent'], before)
        self.assertFalse(result['push'])
        snap = json.loads(self.git('show', 'HEAD:MANIFEST.json'))
        app = next(e for e in snap['files'] if e['path'] == 'app.txt')
        self.assertEqual(app['sha256'], hashlib.sha256(b'two').hexdigest())
        self.assertEqual(self.git('show', 'HEAD:app.txt'), 'two')

    def test_stale_head_aborts_without_creating_commit(self):
        (self.root / 'app.txt').write_text('two', encoding='utf-8')
        self.git('add', 'app.txt')
        head = self.git('rev-parse', 'HEAD')
        with self.assertRaisesRegex(ValueError, 'STALE_HEAD'):
            MODULE.commit_staged(self.root, 'bad', expected_head='0'*40)
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)

    def test_unstaged_changes_are_not_committed(self):
        (self.root / 'app.txt').write_text('staged', encoding='utf-8')
        self.git('add', 'app.txt')
        (self.root / 'app.txt').write_text('unstaged', encoding='utf-8')
        MODULE.commit_staged(self.root, 'approved')
        self.assertEqual(self.git('show', 'HEAD:app.txt'), 'staged')
        self.assertEqual((self.root / 'app.txt').read_text(), 'unstaged')

    def test_hook_injecting_unlisted_file_is_detected_after_commit(self):
        # A user hook may stage extra source after the manifest was prepared.
        # This test establishes fail detection, NOT rollback of the local commit.
        (self.root / 'app.txt').write_text('two', encoding='utf-8')
        self.git('add', 'app.txt')
        hook = self.root / '.git' / 'hooks' / 'pre-commit'
        hook.write_text('#!/bin/sh\nprintf injected > extra.txt\ngit add extra.txt\n')
        hook.chmod(0o755)
        previous_head = self.git('rev-parse', 'HEAD')
        with self.assertRaisesRegex(MODULE.PostCommitIntegrityError,
                                    'POST_COMMIT_TREE_MANIFEST_MISMATCH'):
            MODULE.commit_staged(self.root, 'invalid-local-commit')
        new_head = self.git('rev-parse', 'HEAD')
        self.assertNotEqual(previous_head, new_head)
        self.assertEqual(self.git('show', 'HEAD:extra.txt'), 'injected')
        data = json.loads(self.git('show', 'HEAD:MANIFEST.json'))
        self.assertNotIn('extra.txt', {item['path'] for item in data['files']})

    def test_hook_deleting_manifest_prevents_git_commit(self):
        (self.root / 'app.txt').write_text('two', encoding='utf-8')
        self.git('add', 'app.txt')
        hook = self.root / '.git' / 'hooks' / 'pre-commit'
        hook.write_text('#!/bin/sh\ngit rm -q MANIFEST.json\n')
        hook.chmod(0o755)
        previous_head = self.git('rev-parse', 'HEAD')
        with self.assertRaises(subprocess.CalledProcessError):
            MODULE.commit_staged(self.root, 'invalid-local-commit')
        self.assertEqual(self.git('rev-parse', 'HEAD'), previous_head)

    def test_empty_index_source_delta_aborts(self):
        head = self.git('rev-parse', 'HEAD')
        with self.assertRaisesRegex(ValueError, 'NO_STAGED_SOURCE_DELTA'):
            MODULE.commit_staged(self.root, 'no-op')
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)

    def test_unstaged_manifest_is_preserved_on_failure(self):
        (self.root / 'app.txt').write_text('two', encoding='utf-8')
        self.git('add', 'app.txt')
        (self.root / 'MANIFEST.json').write_text('do-not-overwrite')
        head = self.git('rev-parse', 'HEAD')
        with self.assertRaisesRegex(ValueError, 'UNSTAGED_MANIFEST_CHANGES'):
            MODULE.commit_staged(self.root, 'bad')
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)
        self.assertEqual((self.root / 'MANIFEST.json').read_text(), 'do-not-overwrite')


if __name__ == '__main__':
    unittest.main()
