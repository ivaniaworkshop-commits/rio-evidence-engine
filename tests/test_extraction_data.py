import importlib.util,json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('extraction_data_builder',ROOT/'scripts/build_extraction_data.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)

class ExtractionDataTests(unittest.TestCase):
    def test_generated_data_reproduces_checked_in_files(self):
        rows,fixture,excluded=builder.build()
        for split in ['train','dev']:
            stored=[json.loads(line) for line in (ROOT/f'training/extraction_{split}.jsonl').read_text().splitlines()]
            self.assertEqual(stored,[c for c in rows if c['split']==split])
    def test_no_text_or_isomorphic_graph_overlap(self):
        rows,fixture,excluded=builder.build();report=builder.audit(rows,fixture,excluded)
        self.assertTrue(all(v==0 for v in report['overlap'].values()))
    def test_relabelled_graph_has_same_signature(self):
        a={'tasks':[{'id':'A'},{'id':'B','depends_on':['A']}]}
        b={'tasks':[{'id':'X'},{'id':'Y','depends_on':['X']}]}
        self.assertEqual(builder.graph_signature(a),builder.graph_signature(b))
    def test_duplicate_text_is_rejected(self):
        rows,fixture,excluded=builder.build()
        with self.assertRaises(ValueError):builder.audit(rows+[rows[0]],fixture,excluded)
