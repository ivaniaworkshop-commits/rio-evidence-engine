"""Synthetic bridge tests: no real external evidence or authority asserted."""
import copy
import hashlib
import json
import unittest

from rio_evidence.sphere_consumer import (
    CANDIDATE_SOURCE_COMMIT, RESULT_SCHEMA, screen_bridge,
)


def fixture():
    payload = {"count": 2, "project": "synthetic"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return {
        "source_commit": CANDIDATE_SOURCE_COMMIT,
        "engine": {
            "schema": "RIO_SPHERE_ENGINE_RECEIPT/1.0",
            "engine_id": "sphere-engine",
            "payload": payload,
            "payload_sha256": digest,
            "action_performed": False,
        },
        "evidence": {
            "subject_sha256": digest,
            "verifier_id": "evidence-engine",
            "source_ref": "SYNTHETIC_FIXTURE_ONLY",
            "result": "PASS",
        },
        "authority": {
            "subject_sha256": digest,
            "issuer_id": "fixture-issuer",
            "approval_ref": "SYNTHETIC_FIXTURE_ONLY",
            "operation": "propose-pr",
            "target": "synthetic/demo",
            "decision": "APPROVE",
        },
    }


class SphereConsumerTests(unittest.TestCase):
    def test_consistent_fixture_still_requires_trusted_host(self):
        envelope = fixture()
        before = copy.deepcopy(envelope)
        result = screen_bridge(envelope)
        self.assertEqual(result["schema"], RESULT_SCHEMA)
        self.assertEqual(result["status"], "HOST_VERIFICATION_REQUIRED")
        for field in ("source_revision_authenticated", "source_executed_attested",
                      "evidence_authenticated", "authority_authenticated", "write_allowed",
                      "action_performed", "candidate_promoted", "production_ready"):
            self.assertIs(result[field], False)
        self.assertIs(result["external_host_required"], True)
        self.assertEqual(envelope, before)

    def test_missing_envelope_fields_hold(self):
        value = fixture()
        value.pop("authority")
        self.assertEqual(screen_bridge(value)["reason"], "ENVELOPE_FIELDS_INVALID")

    def test_extra_claim_field_does_not_bypass(self):
        value = fixture()
        value["independent_verified"] = True
        self.assertEqual(screen_bridge(value)["status"], "HOLD")

    def test_wrong_commit_is_rejected(self):
        value = fixture()
        value["source_commit"] = "f" * 40
        self.assertEqual(screen_bridge(value)["reason"], "SOURCE_REVISION_UNPINNED")

    def test_invalid_schema_rejected(self):
        value = fixture()
        value["engine"]["schema"] = "CUSTOM"
        self.assertEqual(screen_bridge(value)["status"], "HOLD")

    def test_tampered_payload_digest_rejected(self):
        value = fixture()
        value["engine"]["payload"]["count"] = 3
        self.assertEqual(screen_bridge(value)["reason"], "ENGINE_DIGEST_MISMATCH")

    def test_nan_payload_rejected(self):
        value = fixture()
        value["engine"]["payload"]["count"] = float("nan")
        self.assertEqual(screen_bridge(value)["reason"], "ENGINE_PAYLOAD_INVALID")

    def test_evidence_replay_for_other_subject_rejected(self):
        value = fixture()
        value["evidence"]["subject_sha256"] = "0" * 64
        self.assertEqual(screen_bridge(value)["reason"], "EVIDENCE_SUBJECT_MISMATCH")

    def test_same_engine_and_verifier_rejected(self):
        value = fixture()
        value["evidence"]["verifier_id"] = "sphere-engine"
        self.assertEqual(screen_bridge(value)["reason"], "VERIFIER_NOT_DISTINCT")

    def test_evidence_fail_holds(self):
        value = fixture()
        value["evidence"]["result"] = "FAIL"
        self.assertEqual(screen_bridge(value)["status"], "HOLD")

    def test_declared_deny_is_not_overridden(self):
        value = fixture()
        value["authority"]["decision"] = "DENY"
        self.assertEqual(screen_bridge(value)["status"], "DENY")

    def test_missing_authority_scope_holds(self):
        value = fixture()
        value["authority"]["target"] = ""
        self.assertEqual(screen_bridge(value)["reason"], "AUTHORITY_SCOPE_MISSING")

    def test_actor_ids_distinct(self):
        value = fixture()
        value["authority"]["issuer_id"] = "evidence-engine"
        self.assertEqual(screen_bridge(value)["reason"], "ACTOR_IDS_NOT_DISTINCT")

    def test_bogus_trusted_flags_do_not_authorize(self):
        value = fixture()
        value["authority"].update({"signature_verified": True, "owner_authenticated": True})
        value["evidence"]["external_verified"] = True
        result = screen_bridge(value)
        self.assertEqual(result["status"], "HOST_VERIFICATION_REQUIRED")
        self.assertFalse(result["write_allowed"])

    def test_input_must_be_mapping(self):
        with self.assertRaisesRegex(ValueError, "ENVELOPE"):
            screen_bridge("wrong type")


if __name__ == "__main__":
    unittest.main()
