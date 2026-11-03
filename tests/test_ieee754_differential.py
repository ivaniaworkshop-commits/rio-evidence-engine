"""Checks for the reproducible IEEE-754 Python/JavaScript differential contract."""
import shutil
import unittest

from scripts.ieee754_differential import make_cases, run_gate, _ulp_distance


class DifferentialFixtures(unittest.TestCase):
    def test_generator_is_seeded_bounded_and_covers_adversarial_families(self):
        a = make_cases()
        b = make_cases()
        self.assertEqual(a, b)
        self.assertEqual(len({x["id"] for x in a}), len(a))
        self.assertGreaterEqual(len(a), 200)
        categories = {x["category"] for x in a}
        self.assertTrue({
            "nextafter", "decimal-ties", "integer-boundary",
            "underflow", "normal-boundary", "overflow",
            "arithmetic", "seeded-nextafter", "signed-zero"
        }.issubset(categories))
        self.assertTrue(any(not x["expect"] for x in a))
        self.assertTrue(any(x["expect"] for x in a))

    def test_ulp_distance_ignores_signed_zero_but_not_adjacent_subnormals(self):
        from math import nextafter, inf
        self.assertEqual(_ulp_distance(-0.0, +0.0), 0)
        self.assertEqual(_ulp_distance(0.0, nextafter(0.0, inf)), 1)
        self.assertEqual(_ulp_distance(1.0, nextafter(1.0, inf)), 1)


@unittest.skipUnless(shutil.which("node"), "Node required for binary64 differential execution")
class DifferentialRuntime(unittest.TestCase):
    def test_cross_runtime_adversarial_gate(self):
        report = run_gate()
        self.assertEqual(report["status"], "PASS_PARITY_GATE", report["failures"])
        self.assertEqual(report["failure_count"], 0)
        self.assertEqual(report["generated_cases"], report["accepted"] + report["rejected"])
        self.assertGreaterEqual(report["accepted"], 190)
        self.assertGreaterEqual(report["rejected"], 10)
        self.assertLessEqual(report["max_observed_ulp_distance"], 1)
