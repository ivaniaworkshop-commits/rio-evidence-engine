"""Exercise the opt-in pre-commit hook with real Git commits."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]


class ManifestHookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.run_git('init', '-q')
        self.run_git('config', 'user.name', 'RÍO test')
        self.run_git('config', 'user.email', 'rio-test@example.invalid')
        self.run_git('config', 'core.hooksPath', '.githooks')
        for name in ('.githooks/pre-commit', 'scripts/prepare_staged_manifest.py'):
            dest = self.root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / name, dest)
            if name.endswith('pre-commit'):
                dest.chmod(0o755)
        (self.root / 'app.txt').write_text('one', encoding='utf-8')
        self.run_git('add', '.githooks/pre-commit',
                     'scripts/prepare_staged_manifest.py', 'app.txt')
        self.prepare()
        self.run_git('commit', '-qm', 'baseline')

    def tearDown(self):
        self.tmp.cleanup()

    def run_git(self, *args, check=True):
        return subprocess.run(['git', '-C', str(self.root), *args],
                              capture_output=True, text=True, check=check)

    def prepare(self):
        subprocess.run(['python3', str(self.root / 'scripts/prepare_staged_manifest.py'),
                        '--prepare'], capture_output=True, text=True, check=True)

    def stage_new_app(self):
        (self.root / 'app.txt').write_text('changed', encoding='utf-8')
        self.run_git('add', 'app.txt')

    def test_stale_manifest_blocks_commit_without_mutating_it(self):
        self.stage_new_app()
        old_head = self.run_git('rev-parse', 'HEAD').stdout.strip()
        old_manifest = (self.root / 'MANIFEST.json').read_bytes()
        result = self.run_git('commit', '-qm', 'should-fail', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('STAGED_MANIFEST_MISMATCH', result.stderr)
        self.assertEqual(self.run_git('rev-parse', 'HEAD').stdout.strip(), old_head)
        self.assertEqual((self.root / 'MANIFEST.json').read_bytes(), old_manifest)

    def test_prepared_manifest_allows_commit(self):
        self.stage_new_app()
        self.prepare()
        result = self.run_git('commit', '-qm', 'approved', check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.run_git('show', 'HEAD:app.txt').stdout, 'changed')

    def test_missing_manifest_rejected(self):
        self.stage_new_app()
        self.run_git('rm', '-q', 'MANIFEST.json')
        result = self.run_git('commit', '-qm', 'missing-manifest', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('STAGED_MANIFEST_MISMATCH', result.stderr)


if __name__ == '__main__':
    unittest.main()
