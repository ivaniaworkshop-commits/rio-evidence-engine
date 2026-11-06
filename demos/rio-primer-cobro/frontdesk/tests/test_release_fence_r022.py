"""R022 synthetic fixtures; no actual Vercel writes, network calls, or rollback."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from release_fence_r022 import (
    ALIAS, PROJECT, FenceError, alias_deployment, baseline_record,
    candidate_deployment, confirm_fence, fence_record, incident_record,
    validate_candidate_url,
)

COMMIT = "a" * 40
OLD = "dpl_OldLegitimate123"
NEW = "dpl_NewCandidate321"
OTHER = "dpl_AnotherWriter999"
URL = "https://rio-primer-cobro-frontdesk-o6k25ltke-ivaniaworkshop-6855.vercel.app"


def alias_fixture(deployment=OLD, project=PROJECT, deleted=None):
    return {"alias": ALIAS, "projectId": project, "deletedAt": deleted,
            "deploymentId": deployment}


def candidate_fixture(target="production", project=PROJECT, state="READY",
                      url=URL, deployment=NEW):
    return {"deployment": {"id": deployment, "project": {"id": project},
             "state": state, "target": target, "url": url.split("://", 1)[1]}}


class ReleaseFenceR022(unittest.TestCase):
    def setUp(self):
        self.before = baseline_record(OLD, COMMIT)
        self.fence = fence_record(self.before, OLD, NEW, URL, COMMIT)

    def test_realistic_alias_fixture(self):
        self.assertEqual(alias_deployment({"result": alias_fixture()}), OLD)

    def test_alias_identity_wrong_project(self):
        with self.assertRaisesRegex(FenceError, "PROJECT_MISMATCH"):
            alias_deployment(alias_fixture(project="prj_Unrelated"))

    def test_alias_deleted_rejected(self):
        with self.assertRaisesRegex(FenceError, "ALIAS_NOT_VERIFIED"):
            alias_deployment(alias_fixture(deleted=123456789))

    def test_alias_without_deployment_rejected(self):
        with self.assertRaisesRegex(FenceError, "ALIAS_DEPLOYMENT_UNRESOLVED"):
            alias_deployment(alias_fixture(deployment=""))

    def test_candidate_ready_production(self):
        self.assertEqual(candidate_deployment(candidate_fixture(), URL), NEW)

    def test_preview_candidate_not_promotable(self):
        with self.assertRaisesRegex(FenceError, "CANDIDATE_NOT_READY"):
            candidate_deployment(candidate_fixture(target=None), URL)

    def test_candidate_wrong_project_rejected(self):
        with self.assertRaisesRegex(FenceError, "CANDIDATE_NOT_READY"):
            candidate_deployment(candidate_fixture(project="prj_Evil"), URL)

    def test_candidate_pending_rejected(self):
        with self.assertRaisesRegex(FenceError, "CANDIDATE_NOT_READY"):
            candidate_deployment(candidate_fixture(state="BUILDING"), URL)

    def test_candidate_url_mismatch_rejected(self):
        with self.assertRaisesRegex(FenceError, "URL_IDENTITY"):
            candidate_deployment(candidate_fixture(url="https://other.vercel.app"), URL)

    def test_candidate_domain_not_whitelisted(self):
        with self.assertRaisesRegex(FenceError, "CANDIDATE_URL_NOT_ALLOWED"):
            validate_candidate_url("https://other-project.vercel.app")

    def test_known_candidate_domain(self):
        self.assertEqual(validate_candidate_url(URL), URL)

    def test_public_alias_is_not_immutable_candidate(self):
        with self.assertRaisesRegex(FenceError, "CANDIDATE_URL_NOT_IMMUTABLE"):
            validate_candidate_url("https://rio-primer-cobro-frontdesk.vercel.app")

    def test_valid_baseline(self):
        self.assertEqual(self.before["previous_deployment_id"], OLD)

    def test_baseline_invalid_commit(self):
        with self.assertRaisesRegex(FenceError, "BASELINE_INVALID_IDENTITY"):
            baseline_record(OLD, "wrong")

    def test_guard_valid_with_provenance(self):
        self.assertEqual(self.fence["candidate_deployment_id"], NEW)
        self.assertEqual(self.fence["previous_deployment_id"], OLD)
        self.assertFalse(self.fence["automatic_rollback"])

    def test_alias_changed_before_promote_fails(self):
        with self.assertRaisesRegex(FenceError, "CONCURRENT_ALIAS_CHANGE"):
            fence_record(self.before, OTHER, NEW, URL, COMMIT)

    def test_stale_commit_fails(self):
        with self.assertRaisesRegex(FenceError, "STALE_OR_INVALID"):
            fence_record(self.before, OLD, NEW, URL, "b" * 40)

    def test_candidate_is_already_published_fails(self):
        with self.assertRaisesRegex(FenceError, "CANDIDATE_NOT_DISTINCT"):
            fence_record(self.before, OLD, OLD, URL, COMMIT)

    def test_confirmation_after_promote(self):
        result = confirm_fence(self.fence, NEW, COMMIT)
        self.assertEqual(result["result"], "ALIAS_POINTS_TO_TESTED_CANDIDATE")
        self.assertEqual(result["public_html_readback"], "SEPARATE_CHECK_REQUIRED")

    def test_alias_overridden_after_promote_fails(self):
        with self.assertRaisesRegex(FenceError, "CONCURRENT_OR_FAILED_PROMOTION"):
            confirm_fence(self.fence, OTHER, COMMIT)

    def test_confirm_old_commit_fails(self):
        with self.assertRaisesRegex(FenceError, "STALE_OR_INVALID"):
            confirm_fence(self.fence, NEW, "b" * 40)

    def test_incident_observed_foreign_writer_no_rollback(self):
        result = incident_record(self.fence, OTHER, "mismatch")
        self.assertEqual(result["result"], "INCIDENT_OPEN")
        self.assertEqual(result["classification"], "ALIAS_CHANGED_OR_PROMOTION_NOT_APPLIED_NO_ROLLBACK")
        self.assertFalse(result["automatic_rollback"])
        self.assertEqual(result["next_action"], "HUMAN_REVIEW_AND_REBASE")

    def test_incident_own_alias_but_bad_bytes(self):
        result = incident_record(self.fence, NEW, "public readback differs")
        self.assertEqual(result["classification"], "CANDIDATE_OWNS_ALIAS_BUT_POSTCHECK_FAILED")
        self.assertFalse(result["automatic_rollback"])

    def test_incident_alias_unavailable(self):
        result = incident_record(self.fence, None, "vercel unreachable")
        self.assertEqual(result["classification"], "ALIAS_UNKNOWN_MANUAL_REVIEW")
        self.assertFalse(result["automatic_rollback"])

    def test_incident_no_valid_fence(self):
        result = incident_record(None, OLD, "fence missing")
        self.assertEqual(result["classification"], "FENCE_UNKNOWN_MANUAL_REVIEW")
        self.assertFalse(result["automatic_rollback"])


if __name__ == "__main__":
    unittest.main()
