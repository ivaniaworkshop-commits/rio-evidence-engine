import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('verify_manifest',Path(__file__).resolve().parents[1]/'scripts/verify_manifest.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class ManifestTests(unittest.TestCase):
    def fixture(self,path):
        (path/'file.txt').write_text('actual bytes')
        entry={'path':'file.txt','bytes':12,'sha256':hashlib.sha256(b'actual bytes').hexdigest()}
        (path/'MANIFEST.json').write_text(json.dumps({'files':[entry]}))
        return entry

    def test_inventory_and_bytes_verified(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);self.fixture(p)
            self.assertEqual(module.verify(p)['verified_files'],1)

    def test_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);self.fixture(p);(p/'file.txt').write_text('changed')
            with self.assertRaises(ValueError):module.verify(p)

    def test_untracked_file_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);self.fixture(p);(p/'extra.txt').write_text('unlisted')
            with self.assertRaises(ValueError):module.verify(p)

    def test_reconciles_auxiliary_paths_with_nested_roles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            expected_files = {
                'file.txt': 'source',
                'MANIFEST.json': 'manifest_control',
                'bundle/MANIFEST.json': 'manifest_control',
                '.git/HEAD': 'git_metadata',
                '.venv/bin/python': 'runtime_environment',
                'package/__pycache__/module.pyc': 'bytecode_cache',
                'output/run/report.json': 'generated_output',
                'output/run/__pycache__/report.pyc': 'bytecode_cache',
            }
            for relative in expected_files.keys() - {'file.txt', 'MANIFEST.json'}:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'fixture')
            (root / 'output/empty').mkdir()

            summary = module.verify(root)['reconciliation']
            result = module.verify(root, include_paths=True)
            report = result['reconciliation']
            self.assertEqual(result['verified_files'], 1)
            self.assertEqual(summary, {key: value for key, value in report.items() if key != 'paths'})
            self.assertEqual(report['total_paths'], 18)
            self.assertEqual(len(report['paths']), report['total_paths'])
            self.assertEqual(
                {path: entry['role'] for path, entry in report['paths'].items() if entry['kind'] == 'files'},
                expected_files,
            )
            self.assertEqual(report['paths']['output/empty'], {'role': 'generated_output', 'kind': 'directories'})
            self.assertEqual(report['by_role']['bytecode_cache']['files'], 2)
            self.assertEqual((root / 'output/run/report.json').read_bytes(), b'fixture')

    def test_auxiliary_paths_cannot_substitute_for_manifest_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = self.fixture(root)
            (root / 'output').mkdir()
            (root / 'file.txt').rename(root / 'output/file.txt')
            entry['path'] = 'output/file.txt'
            (root / 'MANIFEST.json').write_text(json.dumps({'files': [entry]}))
            with self.assertRaisesRegex(ValueError, 'inventory differs'):
                module.verify(root)

    def test_parent_path_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);entry=self.fixture(p);entry['path']='../outside'
            (p/'MANIFEST.json').write_text(json.dumps({'files':[entry]}))
            with self.assertRaisesRegex(ValueError,'escapes root'):module.verify(p)
