import hashlib,importlib.util,json
from pathlib import Path
import unittest
from rio_evidence.constrained_extraction import ConstrainedExtractor
from rio_evidence.neural_lm import ContextBudgetError
from rio_evidence.semantic_gate import canonical
ROOT=Path(__file__).resolve().parents[1]

class ConstrainedBudgetTests(unittest.TestCase):
    def test_nonstandard_budget_rejected_before_model_use(self):
        decoder=object.__new__(ConstrainedExtractor)
        with self.assertRaises(ValueError):decoder.generate('task description',64)
    def test_oversize_prompt_rejected_before_model_use(self):
        decoder=object.__new__(ConstrainedExtractor)
        with self.assertRaises(ContextBudgetError):decoder.generate('x'*4097)

@unittest.skipUnless(importlib.util.find_spec('torch'),'optional torch required')
class ConstrainedRuntimeTests(unittest.TestCase):
    def test_output_completes_once_without_duplicate_tasks(self):
        checkpoint=ROOT/'model/extraction_gru.pt';before=hashlib.sha256(checkpoint.read_bytes()).hexdigest()
        decoder=ConstrainedExtractor(checkpoint)
        result=decoder.generate('Task A lasts 3 minutes. Task B lasts 7 minutes. Task C lasts 11 minutes. Task D lasts 2 minutes.')
        self.assertTrue(result['grammar_completed']);self.assertLessEqual(result['generated_bytes'],512)
        if result['text']!='ABSTAIN':
            graph=canonical(json.loads(result['text']))
            self.assertEqual([t['id'] for t in graph['tasks']],list('ABCD'))
            self.assertTrue(all(1<=n<=24 for n in graph['durations'].values()))
        self.assertEqual(hashlib.sha256(checkpoint.read_bytes()).hexdigest(),before)
