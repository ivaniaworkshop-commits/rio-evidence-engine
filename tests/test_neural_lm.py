import importlib.util
import json
from pathlib import Path
import unittest
from rio_evidence.neural_lm import corpus,generate,train
ROOT=Path(__file__).resolve().parents[1]

class NeuralCorpusTests(unittest.TestCase):
    def test_corpus_partition_has_no_empty_bytes(self):
        groups=corpus(ROOT/'training/answer_matrix.jsonl')
        self.assertGreater(len(groups['practice']),len(groups['holdout']))
        self.assertIn(b'Answer:',groups['practice'])

    def test_zero_steps_cannot_claim_training(self):
        with self.assertRaises(ValueError):train(ROOT,0)

@unittest.skipUnless(importlib.util.find_spec('torch'), 'optional torch required')
class NeuralRuntimeTests(unittest.TestCase):
    def test_checkpoint_inference_repeats_exactly_locally(self):
        if not (ROOT/'model/byte_gru.pt').exists():self.skipTest('trained checkpoint not present')
        a=generate(ROOT,'Case: parallel',20);b=generate(ROOT,'Case: parallel',20)
        self.assertEqual(a,b)
        self.assertIsInstance(a,str)
