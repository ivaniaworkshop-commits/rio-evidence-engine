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

    def test_parent_path_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);entry=self.fixture(p);entry['path']='../outside'
            (p/'MANIFEST.json').write_text(json.dumps({'files':[entry]}))
            with self.assertRaisesRegex(ValueError,'escapes root'):module.verify(p)
