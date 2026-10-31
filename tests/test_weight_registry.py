import importlib.util,json,tempfile,unittest
from pathlib import Path
from rio_evidence.weight_registry import CHECKPOINTS,ROOT,metadata,load_checkpoint,prewarm_all
class WeightRegistryGuards(unittest.TestCase):
    def test_all_three_hashes_match_existing_evidence(self):
        self.assertEqual(len(CHECKPOINTS),3)
        for name in CHECKPOINTS:self.assertEqual(len(metadata(name)['sha256']),64)
    def test_unknown_and_unapproved_candidate_rejected(self):
        with self.assertRaises(ValueError):load_checkpoint('../other')
        for name in ('extraction','weighted_extraction'):
            with self.assertRaisesRegex(ValueError,'OPT_IN'):load_checkpoint(name)
        with self.assertRaisesRegex(ValueError,'OPT_IN'):prewarm_all()
    def test_byte_drift_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'model').mkdir()
            (root/'model/byte_gru.pt').write_bytes(b'drift')
            (root/'model/TRAINING_RESULT.json').write_bytes((ROOT/'model/TRAINING_RESULT.json').read_bytes())
            with self.assertRaisesRegex(ValueError,'EVIDENCE_MISMATCH'):load_checkpoint('base',root)
@unittest.skipUnless(importlib.util.find_spec('torch'),'optional torch required')
class WeightRegistryRuntime(unittest.TestCase):
    def test_all_existing_groups_load_with_exact_parameter_counts(self):
        models,records=prewarm_all(allow_experimental=True)
        self.assertEqual(set(models),set(CHECKPOINTS))
        self.assertEqual([r['groups_loaded'] for r in records],[7,7,7])
        self.assertEqual([r['parameters_loaded'] for r in records],[17344]*3)
    def test_nonfinite_candidate_rejected_even_with_matching_receipt(self):
        import torch,hashlib
        from rio_evidence.neural_lm import make_model
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'model').mkdir();state=make_model(torch).state_dict()
            state['output.bias'][0]=float('nan');path=root/'model/byte_gru.pt';torch.save({'state_dict':state},path)
            (root/'model/TRAINING_RESULT.json').write_text(json.dumps({'checkpoint_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}))
            with self.assertRaisesRegex(ValueError,'INVALID_WEIGHT_TENSOR'):load_checkpoint('base',root)
