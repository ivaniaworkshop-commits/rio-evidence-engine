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
    def test_unsafe_integer_is_preserved_by_generic_decoder_but_rejected_in_compare(self):
        from rio_evidence.core import compare_results
        rows=loads('[{"case_id":"a","correct":true,"latency_ms":9007199254740993}]')
        self.assertEqual(rows[0]['latency_ms'],9007199254740993)
        with self.assertRaisesRegex(ValueError,'unsafe integer latency'):
            compare_results([dict(rows[0],latency_ms=0)],rows)

    def test_python_schedule_preserves_exact_integer_duration(self):
        from rio_evidence.core import critical_path
        data=loads('{"tasks":[{"id":"a"}],"durations":{"a":9007199254740993}}')
        result=critical_path(data['tasks'],data['durations'])
        self.assertEqual(result['minutes'],9007199254740993)
        self.assertEqual(result['single_worker_minutes'],9007199254740993)

    def test_regular_json_preserves_large_integer(self):
        self.assertEqual(loads('{"n":9007199254740993}'),{'n':9007199254740993})
