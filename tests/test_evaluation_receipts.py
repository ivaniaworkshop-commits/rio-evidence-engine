"""Readback consistency tests; CI evidence authenticity requires GitHub logs."""
import json
from pathlib import Path
import unittest
from rio_evidence.power_bounds import probability_at_least,minimum_n_for_power
ROOT=Path(__file__).resolve().parents[1]

class ReadbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r=json.loads((ROOT/"model/EVALUATION_OBSERVATIONS_R001.json").read_text())
        cls.d=json.loads((ROOT/"model/DESCRIPTION.json").read_text())

    def test_h10_h11_h12_history_not_promoted(self):
        v=self.r["checks"]
        self.assertEqual((v["h10"]["h09_exact"],v["h10"]["authored_supported"]),(0,40))
        self.assertEqual(v["h10"]["h09_correct_abstentions"],12)
        self.assertEqual((v["h11"]["identity_candidate_wins"],v["h11"]["identity_candidate_losses"]),(0,0))
        self.assertTrue(all(x["failed"]==x["errors"]==x["skipped"]==0 for x in v.values()))
        self.assertFalse(self.r["candidate_promoted"])
        self.assertFalse(self.r["external_hidden_set_evaluated"])

    def test_h12_math_and_model_description_match_receipt(self):
        h=self.r["checks"]["h12"]
        self.assertAlmostEqual(probability_at_least(30,.1,5),h["exact_detection_probability_n30"],places=13)
        self.assertEqual(minimum_n_for_power(.1),h["minimum_n_for_conditional_power_ge_80pct"])
        self.assertEqual(self.d["latest_strict_suite_observed"]["commit"],h["source_commit"])
        self.assertEqual(self.d["latest_strict_suite_observed"]["tests"],155)
        self.assertFalse(self.d["h12_power_design"]["model_promoted"])
