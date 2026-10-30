import tempfile
from pathlib import Path
import unittest
from rio_evidence.json_io import load,loads,MAX_BYTES

class StrictJsonTests(unittest.TestCase):
    def test_duplicate_key_rejected(self):
        with self.assertRaises(ValueError):loads('{"tasks":[],"tasks":[]}')
    def test_nonstandard_numbers_rejected(self):
        for value in ['NaN','Infinity','-Infinity']:
            with self.subTest(value=value), self.assertRaises(ValueError):loads(value)
    def test_oversize_file_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'input';p.write_bytes(b' '*(MAX_BYTES+1))
            with self.assertRaises(ValueError):load(p)
    def test_regular_json_preserves_large_integer(self):
        self.assertEqual(loads('{"n":9007199254740993}'),{'n':9007199254740993})
