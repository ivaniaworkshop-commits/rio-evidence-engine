"""Standard-library, offline tests for the H04 scenario calculator."""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# This test works from a clean repository root without package installation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis.h04_economic_sensitivity import analyze, main  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "analysis" / "h04_economic_sensitivity.py"


def sample():
    return {
        "scenario_id": "owner-relayed-2026-10-30",
        "baseline": {
            "ltv_mxn": "606", "cac_mxn": "1000",
            "purchase_mxn": "1115", "gross_savings_mxn": "46.63"
        },
        "scenarios": [
            {"name": "base", "ltv_multiplier": "1", "cac_multiplier": "1", "incremental_cost_mxn": "0"},
            {"name": "rounded_1_650", "ltv_multiplier": "1.650", "cac_multiplier": "1", "incremental_cost_mxn": "0"},
            {"name": "below_exact_threshold", "ltv_multiplier": "1.650165", "cac_multiplier": "1", "incremental_cost_mxn": "50"},
            {"name": "above_exact_threshold", "ltv_multiplier": "1.650166", "cac_multiplier": "1", "incremental_cost_mxn": "0"},
            {"name": "cac_cut_39_4_pct", "ltv_multiplier": "1", "cac_multiplier": "0.606", "incremental_cost_mxn": "0"},
        ],
    }


class H04Tests(unittest.TestCase):
    def test_baseline_exact_and_display(self):
        out = analyze(sample())
        self.assertEqual(out["baseline"]["ltv_cac_ratio_display"], "0.606000000000")
        self.assertEqual(out["baseline"]["minimum_ltv_multiplier_display"], "1.650165016502")
        self.assertEqual(out["baseline"]["minimum_cac_reduction_pct_display"], "39.400000000000")
        self.assertEqual(out["baseline"]["gross_savings_rate_pct_display"], "4.182062780269")
        self.assertFalse(out["baseline"]["meets_ltv_cac_one_gate"])

    def test_rounding_never_changes_gate(self):
        cases = analyze(sample())["scenarios"]
        self.assertEqual([x["meets_ltv_cac_one_gate"] for x in cases], [False, False, False, True, True])

    def test_savings_not_profit_claim(self):
        out = analyze(sample())
        assert out["scenarios"][2]["savings_less_incremental_cost_mxn"] == "-3.37"
        self.assertFalse(out["scenarios"][2]["savings_cover_incremental_cost"])
        self.assertIn("NOT_PROFITABILITY", out["evidence_boundary"])

    def test_input_not_mutated_and_repeatable(self):
        inp = sample()
        before = copy.deepcopy(inp)
        self.assertEqual(analyze(inp), analyze(inp))
        self.assertEqual(inp, before)

    def test_zero_cost_not_magic_profitability(self):
        inp = sample()
        inp["baseline"]["gross_savings_mxn"] = "0"
        out = analyze(inp)
        self.assertEqual(out["baseline"]["gross_savings_rate_pct_display"], "0.000000000000")
        self.assertFalse(out["baseline"]["meets_ltv_cac_one_gate"])

    def test_reject_invalid_decimals(self):
        for bad in ["NaN", "Infinity", "1e3", "-0.1", "01", "1.1234567", 606, 1.1, None, True]:
            with self.subTest(bad=bad):
                inp = sample()
                inp["baseline"]["ltv_mxn"] = bad
                with self.assertRaises(ValueError):
                    analyze(inp)

    def test_reject_zero_denominators(self):
        for key in ("ltv_mxn", "cac_mxn", "purchase_mxn"):
            with self.subTest(key=key):
                inp = sample()
                inp["baseline"][key] = "0"
                with self.assertRaises(ValueError):
                    analyze(inp)

    def test_reject_invalid_savings_and_names(self):
        inp = sample()
        inp["baseline"]["gross_savings_mxn"] = "1116"
        with self.assertRaises(ValueError):
            analyze(inp)
        inp = sample()
        inp["scenarios"][1]["name"] = "base"
        with self.assertRaises(ValueError):
            analyze(inp)

    def test_reject_unexpected_fields(self):
        for obj in ["root", "base", "scenario"]:
            inp = sample()
            target = {"root": inp, "base": inp["baseline"], "scenario": inp["scenarios"][0]}[obj]
            target["secret"] = "do-not-accept"
            with self.subTest(obj=obj), self.assertRaises(ValueError):
                analyze(inp)

    def test_reject_invalid_scenarios(self):
        for value in [[], "x", [sample()["scenarios"][0]] * 31]:
            inp = sample()
            inp["scenarios"] = value
            with self.subTest(value=str(value)[:10]), self.assertRaises(ValueError):
                analyze(inp)

    def test_reject_zero_cac_multiplier(self):
        inp = sample()
        inp["scenarios"][0]["cac_multiplier"] = "0"
        with self.assertRaises(ValueError):
            analyze(inp)

    def test_cli_valid_json_and_invalid_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input.json"
            path.write_text(json.dumps(sample()), encoding="utf-8")
            run = subprocess.run([sys.executable, str(SCRIPT), str(path)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout)["status"], "CALCULATED_FROM_USER_SUPPLIED_ASSUMPTIONS")
            path.write_text('{"scenario_id":"a","scenario_id":"b"}', encoding="utf-8")
            run = subprocess.run([sys.executable, str(SCRIPT), str(path)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(run.returncode, 2)
            self.assertEqual(json.loads(run.stderr)["status"], "HOLD")

    def test_cli_extreme_depth_returns_hold_without_traceback(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "nested.json"
            path.write_text("[" * 10000 + "0" + "]" * 10000, encoding="utf-8")
            run = subprocess.run([sys.executable, str(SCRIPT), str(path)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(run.returncode, 2, run.stderr[:150])
            self.assertEqual(json.loads(run.stderr)["status"], "HOLD")
            self.assertNotIn("Traceback", run.stderr)

    def test_cli_never_uses_unbounded_read_bytes(self):
        from unittest.mock import patch
        from contextlib import redirect_stderr
        from io import StringIO
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "oversized.json"
            path.write_bytes(b" " * 65537)
            err = StringIO()
            with patch.object(Path, "read_bytes", side_effect=AssertionError("unbounded read")), redirect_stderr(err):
                ret = main([str(path)])
            self.assertEqual(ret, 2)
            self.assertEqual(json.loads(err.getvalue())["status"], "HOLD")

    def test_cli_oversized_input_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "large.json"
            path.write_bytes(b" " * 65537)
            run = subprocess.run([sys.executable, str(SCRIPT), str(path)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(run.returncode, 2)
            self.assertIn("65536", run.stderr)


if __name__ == "__main__":
    unittest.main()
