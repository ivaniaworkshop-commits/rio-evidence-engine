"""P5: metamorphic invariance against a rational oracle independent of both runtimes."""
import math
import shutil
import unittest

from scripts.metamorphic_exact_sum import (
    SEED, exact_grouped_mean, exact_mean, run_gate, source_pairs, variations,
)
from rio_evidence.core import compare_results


class OracleSensitivity(unittest.TestCase):
    def test_two_subnormals_divided_across_three_terms_exposes_shared_error(self):
        tiny = math.nextafter(0.0, math.inf)
        pairs = [(0.0, tiny), (0.0, tiny), (0.0, 0.0)]
        self.assertEqual(exact_mean(pairs), tiny)
        self.assertEqual(math.fsum((b-a)/3 for a,b in pairs), 0.0)
        a = [dict(case_id=str(i), correct=False, latency_ms=x) for i,(x,y) in enumerate(pairs)]
        b = [dict(case_id=str(i), correct=True, latency_ms=y) for i,(x,y) in enumerate(pairs)]
        self.assertEqual(compare_results(a,b)["mean_latency_delta_ms"], tiny)

    def test_ties_to_even_oracle_and_runtime(self):
        unit = math.nextafter(1.0, math.inf)
        upper = math.nextafter(unit, math.inf)
        self.assertEqual(exact_mean([(0.0,1.0),(0.0,unit)]),1.0)
        self.assertEqual(exact_mean([(0.0,unit),(0.0,upper)]),upper)

    def test_grouping_repetition_and_permutation_preserve_exact_mean(self):
        cases = source_pairs()
        self.assertEqual(cases, source_pairs())
        self.assertEqual(SEED, 20261102)
        for name,pairs in cases.items():
            baseline = exact_mean(pairs)
            variants = list(variations(name,pairs))
            self.assertEqual(len(variants), 9)
            for variant in variants:
                with self.subTest(name=name,variant=variant["variant"]):
                    self.assertEqual(exact_mean(variant["pairs"]), baseline)
                    for group_size in (1,2,3,4):
                        self.assertEqual(exact_grouped_mean(variant["pairs"],group_size), baseline)


@unittest.skipUnless(shutil.which("node"), "Node required for JS/Python oracle evaluation")
class MetamorphicNodeParity(unittest.TestCase):
    def test_cross_runtime_exact_rational_oracle(self):
        report = run_gate()
        self.assertEqual(report["status"], "PASS_EXACT_METAMORPHIC_GATE", report["failures"])
        self.assertEqual(report["failure_count"],0)
        self.assertEqual(report["cases"],report["accepted"])
        self.assertGreaterEqual(report["cases"],500)
        self.assertEqual(report["max_observed_error_ulp"],0)
        self.assertTrue(report["old_shared_bug_detected"])
