import importlib.util,json
from pathlib import Path
import unittest
from rio_evidence.extraction_model import encode_example,batch,EOS
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('extraction_trainer',ROOT/'scripts/train_extraction.py')
trainer=importlib.util.module_from_spec(spec);spec.loader.exec_module(trainer)

class ExtractionTrainingTests(unittest.TestCase):
    def test_prompt_positions_are_masked_and_target_includes_eos(self):
        row={'text':'Task A lasts 3 minutes.','target':'ABSTAIN'}
        x,y=encode_example(row);self.assertEqual(len(x),len(y))
        targets=[v for v in y if v!=-100]
        self.assertEqual(targets,list(b'ABSTAIN')+[EOS])
        self.assertGreater(y.count(-100),0)
    def test_nul_and_budget_violations_rejected(self):
        for row in [{'text':'bad\0prompt','target':'ABSTAIN'},{'text':'x'*4096,'target':'ABSTAIN'},
                    {'text':'valid','target':'x'*513}]:
            with self.subTest(row_length=len(row['text'])),self.assertRaises(ValueError):encode_example(row)
    def test_zero_training_steps_rejected(self):
        with self.assertRaises(ValueError):trainer.main(0)

@unittest.skipUnless(importlib.util.find_spec('torch'),'optional torch required')
class ExtractionBatchTests(unittest.TestCase):
    def test_padding_has_no_loss_target(self):
        import torch
        short=encode_example({'text':'A','target':'ABSTAIN'});long=encode_example({'text':'A'*30,'target':'ABSTAIN'})
        x,y=batch(torch,[short,long]);self.assertEqual(x.shape,y.shape)
        self.assertTrue(bool((y[0,len(short[1]):]==-100).all()))
