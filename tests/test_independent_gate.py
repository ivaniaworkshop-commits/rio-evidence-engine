"""Synthetic tests of the external gate. They are NOT an independent dataset."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import unittest

from rio_evidence.independent_gate import evaluate

ROOT = Path(__file__).resolve().parents[1]


class ExternalGateTests(unittest.TestCase):
    def bundle(self, positive=30, negative=10):
        good = {"tasks": [{"id": "A", "depends_on": []}], "durations": {"A": 3}}
        start = datetime(2026, 10, 20, tzinfo=timezone.utc)
        rows = []
        for i in range(positive + negative):
            is_positive = i < positive
            rows.append({
                "case_id": "EX-" + str(i), "cluster": "C" + str(i % 6),
                "text": "A novel externally submitted request {} with wording outside project grammar.".format(i),
                "expected": copy.deepcopy(good) if is_positive else None,
                "candidate_output": copy.deepcopy(good) if is_positive else "ABSTAIN",
                "baseline_latency_ms": 1.0, "candidate_latency_ms": 1.0
            })
        return {"schema": "RIO_EXTERNAL_HOLDOUT_R001",
                "provenance": {"candidate_commit": "a" * 40, "baseline_commit": "b" * 40,
                               "frozen_at_utc": start.isoformat(),
                               "received_at_utc": (start + timedelta(days=1)).isoformat(),
                               "source_type": "EXTERNAL_EVALUATOR",
                               "source_ref": "Illustrative only, no actual external evaluator"},
                "cases": rows}

    def test_missing_external_set_blocks(self):
        self.assertEqual(evaluate(None)["status"], "BLOCKED_NO_EXTERNAL_HOLDOUT")

    def test_synthetic_technical_pass_cannot_promote(self):
        result = evaluate(self.bundle())
        self.assertEqual(result["status"], "PROVISIONAL_TECHNICAL_SCREEN_PASS")
        self.assertFalse(result["candidate_promoted"])
        self.assertIn("NOT_AUTHENTICATED", result["independence"])
        self.assertEqual(result["candidate_supported_exact"], 30)

    def test_insufficient_supported_cases(self):
        self.assertEqual(evaluate(self.bundle(29, 10))["status"], "INSUFFICIENT_DIVERSITY_OR_DENOMINATOR")

    def test_duplicate_case_rejected(self):
        data = self.bundle()
        data["cases"][1]["case_id"] = data["cases"][0]["case_id"]
        with self.assertRaisesRegex(ValueError, "DUPLICATED"):
            evaluate(data)

    def test_exact_dev_text_overlap_rejected(self):
        data = self.bundle()
        dev = json.loads((ROOT / "training/extraction_dev.jsonl").read_text().splitlines()[0])
        data["cases"][0]["text"] = dev["text"]
        with self.assertRaisesRegex(ValueError, "OVERLAP"):
            evaluate(data)

    def test_freeze_after_data_rejected(self):
        data = self.bundle()
        data["provenance"]["frozen_at_utc"] = data["provenance"]["received_at_utc"]
        with self.assertRaisesRegex(ValueError, "PRE_FROZEN"):
            evaluate(data)

    def test_invalid_reference_graph_rejected(self):
        data = self.bundle()
        data["cases"][0]["expected"] = {"tasks": [{"id": "A", "depends_on": ["Z"]}], "durations": {"A": 3}}
        with self.assertRaises((ValueError, KeyError)):
            evaluate(data)

    def test_abstention_regression_blocks(self):
        data = self.bundle()
        for row in data["cases"][30:]:
            row["candidate_output"] = {"tasks": [{"id": "A", "depends_on": []}], "durations": {"A": 3}}
        self.assertEqual(evaluate(data)["status"], "ABSTENTION_REGRESSION")

    def test_slow_candidate_blocks(self):
        data = self.bundle()
        for row in data["cases"]:
            row["candidate_latency_ms"] = 100
        self.assertEqual(evaluate(data)["status"], "LATENCY_OVER_BUDGET")

    def test_nonfinite_latency_rejected(self):
        data = self.bundle()
        data["cases"][0]["candidate_latency_ms"] = float("nan")
        with self.assertRaisesRegex(ValueError, "INVALID_MEASURED_LATENCY"):
            evaluate(data)

    def test_wrong_envelope_rejected(self):
        data = self.bundle()
        data["schema"] = "UNVERIFIED"
        with self.assertRaisesRegex(ValueError, "INVALID_EVALUATION_ENVELOPE"):
            evaluate(data)

    def test_extra_claim_field_rejected(self):
        data = self.bundle()
        data["independent_verified"] = True
        with self.assertRaisesRegex(ValueError, "INVALID_EVALUATION_ENVELOPE"):
            evaluate(data)
