import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('prepare_staged_manifest', ROOT / 'scripts/prepare_staged_manifest.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class StagedManifestTests(unittest.TestCase):
    def setup_repo(self, path):
        subprocess.run(['git', 'init', '-q', str(path)], check=True)
        (path / 'file.txt').write_text('one', encoding='utf-8')
        subprocess.run(['git', '-C', str(path), 'add', 'file.txt'], check=True)

    def test_prepare_and_readback_from_index(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            self.setup_repo(p)
            x = MODULE.process(p, prepare=True)
            self.assertEqual(x['status'], 'MANIFEST_PREPARED')
            self.assertEqual(MODULE.process(p)['status'], 'STAGED_MANIFEST_PASS')
            data = json.loads((p / 'MANIFEST.json').read_text())
            self.assertEqual(data['files'][0]['bytes'], 3)

    def test_staged_mutation_rejected_until_explicit_prepare(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            self.setup_repo(p)
            MODULE.process(p, prepare=True)
            (p / 'file.txt').write_text('two', encoding='utf-8')
            subprocess.run(['git', '-C', str(p), 'add', 'file.txt'], check=True)
            with self.assertRaisesRegex(ValueError, 'STAGED_MANIFEST_MISMATCH'):
                MODULE.process(p)
            MODULE.process(p, prepare=True)
            self.assertEqual(MODULE.process(p)['status'], 'STAGED_MANIFEST_PASS')

    def test_unstaged_source_does_not_contaminate_staged_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            self.setup_repo(p)
            MODULE.process(p, prepare=True)
            (p / 'file.txt').write_text('changed-but-unstaged', encoding='utf-8')
            self.assertEqual(MODULE.process(p)['status'], 'STAGED_MANIFEST_PASS')
            self.assertEqual(json.loads((p / 'MANIFEST.json').read_text())['files'][0]['bytes'], 3)

    def test_unstaged_manifest_protected_from_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            self.setup_repo(p)
            MODULE.process(p, prepare=True)
            (p / 'MANIFEST.json').write_text('user-edit')
            with self.assertRaisesRegex(ValueError, 'UNSTAGED_MANIFEST_CHANGES'):
                MODULE.process(p, prepare=True)
            self.assertEqual((p / 'MANIFEST.json').read_text(), 'user-edit')


if __name__ == '__main__':
    unittest.main()
