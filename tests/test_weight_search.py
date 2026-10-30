import importlib.util
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('weight_search',ROOT/'scripts/search_weight_groups.py')
search=importlib.util.module_from_spec(spec);spec.loader.exec_module(search)

class WeightVectorTests(unittest.TestCase):
    def test_same_seed_replays_vectors(self):
        a=search.draw_vectors(['a','b'],seed=1,count=10)
        self.assertEqual(a,search.draw_vectors(['a','b'],seed=1,count=10))
        self.assertNotEqual(a,search.draw_vectors(['a','b'],seed=2,count=10))
    def test_invalid_or_missing_multiplier_rejected(self):
        for multipliers in [{},{'a':float('nan')},{'a':True},{'a':3}]:
            with self.subTest(multipliers=multipliers),self.assertRaises(ValueError):
                search.scaled_state({'a':1},multipliers)

@unittest.skipUnless(importlib.util.find_spec('torch'),'optional torch required')
class WeightScalingTests(unittest.TestCase):
    def test_scaling_does_not_mutate_source(self):
        import torch
        base={'a':torch.tensor([2.,4.])};scaled=search.scaled_state(base,{'a':.5})
        self.assertEqual(scaled['a'].tolist(),[1.,2.]);self.assertEqual(base['a'].tolist(),[2.,4.])
    def test_identity_preserves_values(self):
        import torch
        base={'a':torch.tensor([2.,4.])}
        self.assertTrue(torch.equal(base['a'],search.scaled_state(base,{'a':1.})['a']))
