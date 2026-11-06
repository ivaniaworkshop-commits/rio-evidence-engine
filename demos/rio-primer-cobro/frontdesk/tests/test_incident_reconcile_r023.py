"""R023 incident drill. Entirely synthetic; no Vercel writes or production rollback."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from release_fence_r022 import baseline_record, fence_record
from incident_reconcile_r023 import ABSENT, INVALID, VALID, reconcile, read_receipt, SCHEMA

COMMIT = "a"*40
PREVIOUS = "dpl_Original777"
CANDIDATE = "dpl_Proposed888"
UNRELATED = "dpl_Concurrent999"
URL = "https://rio-primer-cobro-frontdesk-o6k25ltke-ivaniaworkshop-6855.vercel.app"


class IncidentR023(unittest.TestCase):
    def setUp(self):
        self.baseline = baseline_record(PREVIOUS, COMMIT)
        self.fence = fence_record(self.baseline, PREVIOUS, CANDIDATE, URL, COMMIT)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def classify(self, alias=PREVIOUS, promote="skipped", baseline_state=VALID, fence_state=VALID,
                 baseline=True, fence=True):
        r = reconcile(self.baseline if baseline else None, baseline_state,
                      self.fence if fence else None, fence_state,
                      alias, promote, COMMIT)
        self.assertEqual(r["result"], "INCIDENT_OPEN")
        self.assertIs(r["automatic_rollback"], False)
        self.assertIs(r["production_write"], False)
        self.assertIs(r["incident_closed"], False)
        return r["classification"]

    def test_pre_promotion_fence_created_alias_unchanged(self):
        self.assertEqual(self.classify(), "PRE_PROMOTION_ABORT_ALIAS_UNCHANGED")

    def test_concurrent_alias_writer_before_promotion(self):
        self.assertEqual(self.classify(alias=UNRELATED), "EXTERNAL_ALIAS_CHANGE_OR_RACE_NO_ROLLBACK")

    def test_candidate_live_despite_skipped_promote(self):
        self.assertEqual(self.classify(alias=CANDIDATE), "CANDIDATE_LIVE_WITHOUT_CONFIRMED_PROMOTION")

    def test_candidate_live_despite_failed_promote_command(self):
        self.assertEqual(self.classify(alias=CANDIDATE, promote="failure"),
                         "CANDIDATE_LIVE_WITHOUT_CONFIRMED_PROMOTION")

    def test_promotion_success_candidate_live_postcheck_bad(self):
        self.assertEqual(self.classify(alias=CANDIDATE, promote="success"),
                         "POST_PROMOTION_CHECK_FAILED_CANDIDATE_STILL_LIVE")

    def test_promotion_success_foreign_alias(self):
        self.assertEqual(self.classify(alias=UNRELATED, promote="success"),
                         "POST_PROMOTION_ALIAS_DIFFERENT_NO_ROLLBACK")

    def test_promotion_success_missing_fence(self):
        self.assertEqual(self.classify(fence=False, fence_state=ABSENT, promote="success"),
                         "PROMOTION_REPORTED_SUCCESS_FENCE_MISSING")

    def test_pre_fence_failure_with_valid_baseline(self):
        self.assertEqual(self.classify(fence=False, fence_state=ABSENT),
                         "PRE_PROMOTION_ABORT_ALIAS_UNCHANGED")

    def test_before_baseline_failure(self):
        self.assertEqual(self.classify(baseline=False, fence=False, baseline_state=ABSENT,
                                       fence_state=ABSENT), "INSUFFICIENT_BASELINE_EVIDENCE")

    def test_alias_api_unavailable(self):
        self.assertEqual(self.classify(alias=None), "ALIAS_UNKNOWN_MANUAL_REVIEW")

    def test_missing_baseline_but_fence_created(self):
        self.assertEqual(self.classify(baseline=False, baseline_state=ABSENT,
                                      alias=UNRELATED), "INSUFFICIENT_BASELINE_EVIDENCE")

    def test_corrupt_fence_not_replaced_with_fake_valid_receipt(self):
        self.assertEqual(self.classify(fence=False, fence_state=INVALID),
                         "EVIDENCE_CORRUPT_MANUAL_REVIEW")

    def test_corrupt_baseline(self):
        self.assertEqual(self.classify(baseline=False, baseline_state=INVALID),
                         "EVIDENCE_CORRUPT_MANUAL_REVIEW")

    def test_contradictory_receipt_genealogy(self):
        changed = dict(self.fence, previous_deployment_id="dpl_DifferentFirst")
        r = reconcile(self.baseline, VALID, changed, VALID, PREVIOUS, "skipped", COMMIT)
        self.assertEqual(r["classification"], "CONTRADICTORY_RECEIPTS_MANUAL_REVIEW")
        self.assertIs(r["automatic_rollback"], False)

    def test_invalid_commit_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "BAD_COMMIT_SHA"):
            reconcile(self.baseline, VALID, self.fence, VALID, PREVIOUS, "skipped", "bad")

    def test_invalid_promote_outcome_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "BAD_PROMOTION_OUTCOME"):
            reconcile(self.baseline, VALID, self.fence, VALID, PREVIOUS, "maybe", COMMIT)

    def test_invalid_observed_deployment_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "BAD_OBSERVED_ALIAS"):
            reconcile(self.baseline, VALID, self.fence, VALID, "../../etc/passwd", "skipped", COMMIT)

    def test_missing_receipt_path_status_absent(self):
        value, status = read_receipt(str(Path(self.tmp.name)/"missing.json"), self.baseline["schema"], COMMIT)
        self.assertIsNone(value)
        self.assertEqual(status, ABSENT)

    def test_corrupt_json_receipt_status_invalid(self):
        path = Path(self.tmp.name)/"corrupt.json"
        path.write_text("{broken", encoding="utf-8")
        self.assertEqual(read_receipt(str(path), self.baseline["schema"], COMMIT)[1], INVALID)

    def test_receipt_from_other_commit_invalid(self):
        path = Path(self.tmp.name)/"stale.json"
        path.write_text(json.dumps(self.baseline), encoding="utf-8")
        self.assertEqual(read_receipt(str(path), self.baseline["schema"], "b"*40)[1], INVALID)

    def test_valid_baseline_receipt_readback(self):
        path = Path(self.tmp.name)/"baseline.json"
        path.write_text(json.dumps(self.baseline), encoding="utf-8")
        value, state = read_receipt(str(path), self.baseline["schema"], COMMIT)
        self.assertEqual(state, VALID)
        self.assertEqual(value["previous_deployment_id"], PREVIOUS)

    def test_fake_fence_enabling_rollback_invalid(self):
        path = Path(self.tmp.name)/"fence.json"
        path.write_text(json.dumps(dict(self.fence, automatic_rollback=True)), encoding="utf-8")
        self.assertEqual(read_receipt(str(path), self.fence["schema"], COMMIT)[1], INVALID)

    def test_cli_without_credentials_still_writes_typed_incident(self):
        path = Path(self.tmp.name)/"incident.json"
        env = {k:v for k,v in os.environ.items() if k != "VERCEL_TOKEN"}
        env["GITHUB_SHA"] = COMMIT
        proc = subprocess.run([sys.executable, str(ROOT/"incident_reconcile_r023.py"),
            "--baseline", str(Path(self.tmp.name)/"missing-baseline.json"),
            "--fence", str(Path(self.tmp.name)/"missing-fence.json"),
            "--promote-outcome", "skipped", "--output", str(path)],
            capture_output=True, text=True, env=env, timeout=15)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        artifact = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(artifact["schema"], SCHEMA)
        self.assertEqual(artifact["classification"], "ALIAS_UNKNOWN_MANUAL_REVIEW")
        self.assertFalse(artifact["automatic_rollback"])
        self.assertEqual(artifact["baseline_receipt"], ABSENT)
        self.assertEqual(artifact["fence_receipt"], ABSENT)

    def test_cli_with_corrupt_receipt_creates_open_incident(self):
        base = Path(self.tmp.name)/"bad.json"
        base.write_text("bad", encoding="utf-8")
        output = Path(self.tmp.name)/"out.json"
        env = {k:v for k,v in os.environ.items() if k != "VERCEL_TOKEN"}
        env["GITHUB_SHA"] = COMMIT
        proc = subprocess.run([sys.executable, str(ROOT/"incident_reconcile_r023.py"),
            "--baseline", str(base), "--fence", str(base),
            "--promote-outcome", "failure", "--output", str(output)],
            capture_output=True, text=True, env=env, timeout=15)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        doc = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(doc["classification"], "EVIDENCE_CORRUPT_MANUAL_REVIEW")
        self.assertEqual(doc["baseline_receipt"], INVALID)
        self.assertEqual(doc["fence_receipt"], INVALID)
        self.assertFalse(doc["automatic_rollback"])


if __name__ == "__main__":
    unittest.main()
