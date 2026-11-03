"""P6: test fixture contract and independent oracle bits before timing promotion."""
import json
import shutil
import unittest

from scripts.benchmark_exact_sum import (
    MAX_BYTES, MIN_NEAR_INPUT_BYTES, TARGET_BYTES, bits, fixtures, measure_node
)
from rio_evidence.core import compare_results
from rio_evidence.json_io import loads


class BenchmarkFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.samples = fixtures()

    def test_sizes_deterministic_and_near_true_limit(self):
        samples = self.samples
        self.assertEqual(set(samples), {32, 2048, "near-1MiB"})
        high = samples["near-1MiB"]
        self.assertGreater(high["count"], 2048)
        self.assertEqual(high["count"], len(loads(high["baseline_raw"])))
        for size in high["bytes_per_input"]:
            self.assertGreaterEqual(size, MIN_NEAR_INPUT_BYTES)
            self.assertLessEqual(size, TARGET_BYTES)
            self.assertLessEqual(size, MAX_BYTES)
        self.assertEqual(samples, fixtures())

    def test_all_data_exact_oracle_matches_p5_core(self):
        for name, record in self.samples.items():
            with self.subTest(name=name):
                a = loads(record["baseline_raw"])
                b = loads(record["candidate_raw"])
                answer = compare_results(a, b)
                self.assertEqual(bits(answer["mean_latency_delta_ms"]), record["oracle_bits"])
                self.assertEqual(answer["n"], record["count"])
                self.assertEqual(answer["baseline_correct"], record["baseline_correct"])
                self.assertEqual(answer["candidate_correct"], record["candidate_correct"])

    @unittest.skipUnless(shutil.which("node"), "Node required for P4/P5 measured comparison")
    def test_node_real_comparators_on_small_fixture(self):
        r = measure_node(self.samples[32], 3)
        self.assertEqual(r["p5"]["result_bits"], self.samples[32]["oracle_bits"])
        self.assertEqual(r["iterations"], 3)
        self.assertTrue(r["p5"]["total_ms_median"] >= 0)
        self.assertTrue(r["p4"]["total_ms_median"] >= 0)
        self.assertEqual(r["bytes_per_input"], self.samples[32]["bytes_per_input"])
