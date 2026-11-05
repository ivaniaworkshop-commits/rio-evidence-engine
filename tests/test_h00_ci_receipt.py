"""Fail-closed receipts are metadata, not external verification."""
import json
import tempfile
import unittest
from pathlib import Path

from scripts.h00_ci_receipt import VERIFY_FILES, _load_json, build_receipt


ENV = {"GITHUB_REPOSITORY": "ivaniaworkshop-commits/rio-evidence-engine",
       "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "123",
       "GITHUB_RUN_ATTEMPT": "1", "GITHUB_EVENT_NAME": "pull_request"}


class H00ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        fixtures = {
            "h08_independent_gate": {"status": "BLOCKED_NO_EXTERNAL_HOLDOUT", "candidate_promoted": False},
            "h11_blocked": {"status": "BLOCKED_NO_EVALUATION_INPUT"},
            "h11_h09": {"candidate_promoted": False},
            "h11_legacy": {"source_class_verified": False},
            "h12_power": {"candidate_promoted": False},
            "h14_development": {"candidate_promoted": False},
            "h14_paired": {"candidate_promoted": False, "source_class_verified": False},
            "h14_freeze": {"status": "FROZEN_SOURCE_BYTES_MATCH_LOCAL_RECEIPT",
                           "candidate_promoted": False, "external_evaluator_authenticated": False},
        }
        for key, filename in VERIFY_FILES.items():
            (self.root / filename).write_text(json.dumps(fixtures[key]), encoding="utf-8")

    def test_complete_verify_is_still_not_production(self):
        r = build_receipt("verify", "success", self.root, env=ENV)
        self.assertEqual(r["status"], "COMPLETE_LOCAL_CI_RECEIPT")
        self.assertFalse(r["candidate_promoted"])
        self.assertFalse(r["external_holdout_authenticated"])
        self.assertEqual(len(r["input_records"]), 8)

    def test_missing_input_fails_closed(self):
        (self.root / "h08.json").unlink()
        self.assertEqual(build_receipt("verify", "success", self.root, env=ENV)["status"], "INCOMPLETE_OR_FAILED")

    def test_fake_external_success_fails_closed(self):
        f = self.root / "h08.json"
        f.write_text(json.dumps({"status": "PROMOTED", "candidate_promoted": True}), encoding="utf-8")
        r = build_receipt("verify", "success", self.root, env=ENV)
        self.assertFalse(r["checks"]["h08_independence_fail_closed"])
        self.assertEqual(r["status"], "INCOMPLETE_OR_FAILED")

    def test_failure_collects_without_green_claim(self):
        self.assertEqual(build_receipt("verify", "failure", self.root, env=ENV)["status"], "INCOMPLETE_OR_FAILED")

    def test_no_git_sha_fails_closed(self):
        self.assertEqual(build_receipt("verify", "success", self.root, env={})["status"], "INCOMPLETE_OR_FAILED")

    def test_strict_summary(self):
        f = self.root / "h00_strict_tests.log"
        f.write_text('Ran 265 tests\n' + json.dumps({"status": "PASS_NO_SKIPS", "tests_run": 265,
            "failed": 0, "errors": 0, "skipped": 0}) + '\n', encoding="utf-8")
        r = build_receipt("strict-torch", "success", self.root, env=ENV)
        self.assertEqual(r["status"], "COMPLETE_LOCAL_CI_RECEIPT")
        self.assertEqual(r["strict_suite"]["tests_run"], 265)

    def test_strict_skip_fails_closed(self):
        f = self.root / "h00_strict_tests.log"
        f.write_text(json.dumps({"status": "FAIL_OR_SKIPPED", "tests_run": 3,
            "failed": 0, "errors": 0, "skipped": 1}) + '\n', encoding="utf-8")
        self.assertEqual(build_receipt("strict-torch", "success", self.root, env=ENV)["status"], "INCOMPLETE_OR_FAILED")

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(ValueError):
            _load_json(b'{"status":"A","status":"B"}')

    def test_large_invalid_json_fails_closed(self):
        (self.root / "h12.json").write_text('{"bad":NaN}', encoding="utf-8")
        self.assertEqual(build_receipt("verify", "success", self.root, env=ENV)["status"], "INCOMPLETE_OR_FAILED")


if __name__ == "__main__":
    unittest.main()
