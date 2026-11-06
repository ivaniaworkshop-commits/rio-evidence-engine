"""R021 isolated adversarial regressions; generate all fixtures in memory."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.h00_cross_artifact_audit import AuditError, SUCCESS, digest, inspect, repack_directory


class CrossArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.proof = {
            "schema": "RIO_H00_PR_PARENT_BINDING/1.0",
            "status": "RUNNER_GIT_PARENT_BINDING_PASS",
            "authority": "RUNNER_GIT_OBJECT_AND_EVENT_NOT_INDEPENDENT",
            "reason_code": None,
            "checkout_sha": "a" * 40, "head_sha": "b" * 40,
            "base_sha": "c" * 40, "parent_shas": ["c" * 40, "b" * 40],
            "run_id": "123", "attempt": "1", "pr_number": 26,
            "event_merge_matches_checkout": False,
            "candidate_promoted": False, "production_ready": False,
            "external_holdout_authenticated": False,
        }
        self.run = {
            "event": "pull_request", "id": "123", "attempt": "1", "sha": "a" * 40,
            "pull_request": {
                "number": 26, "checkout_sha": "a" * 40,
                "head_sha": "b" * 40, "base_sha": "c" * 40,
                "checkout_parent_binding": "RUNNER_REPORT_CONSISTENT_NOT_INDEPENDENT",
                "parent_binding_report_sha256": None,
            },
        }
        self._prepare()

    @staticmethod
    def enc(x):
        return (json.dumps(x, sort_keys=True) + "\n").encode()

    def _prepare(self):
        raw = self.enc(self.proof)
        self.run["pull_request"]["parent_binding_report_sha256"] = digest(raw)
        def receipt(stage):
            return {
                "schema": "RIO_H00_CI_RECEIPT/1.0", "stage": stage,
                "status": "COMPLETE_LOCAL_CI_RECEIPT",
                "evidence_authority": "CI_RUNNER_SELF_REPORTED_NOT_EXTERNAL_ATTESTATION",
                "ci_job_status_reported": "success", "run": self.run,
                "checks": {"pr_checkout_parent_binding": True, "github_context_present": True},
                "input_records": {"pr_checkout": {"bytes": len(raw), "sha256": digest(raw)}},
                "strict_suite": ({"status": "PASS_NO_SKIPS", "tests_run": 295,
                                  "failed": 0, "errors": 0, "skipped": 0}
                                 if stage == "strict-torch" else None),
                "candidate_promoted": False, "production_ready": False,
                "external_holdout_authenticated": False,
                "source_class_verified_externally": False,
            }
        self.archive = {
            "verify": {
                "root/output/h00/pr-checkout.json": raw,
                "root/output/h00/verify-receipt.json": self.enc(receipt("verify")),
            },
            "strict": {
                "root/output/h00/pr-checkout.json": raw,
                "root/output/h00/strict-receipt.json": self.enc(receipt("strict-torch")),
            },
        }
        self._write()

    def _write(self):
        self.verify = self.root / "verify.zip"
        self.strict = self.root / "strict.zip"
        for name, path in (("verify", self.verify), ("strict", self.strict)):
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
                for filename, raw in self.archive[name].items():
                    z.writestr(filename, raw)

    def _update_receipt(self, which, fn):
        filename = f"root/output/h00/{'verify' if which == 'verify' else 'strict'}-receipt.json"
        d = json.loads(self.archive[which][filename])
        fn(d)
        self.archive[which][filename] = self.enc(d)
        self._write()

    def reject(self, code):
        with self.assertRaises(AuditError) as cm:
            inspect(self.verify, self.strict)
        self.assertTrue(str(cm.exception).startswith(code), str(cm.exception))

    def test_valid_pair_consistent_but_not_independent(self):
        r = inspect(self.verify, self.strict, expected_run_id="123", expected_head_sha="b" * 40)
        self.assertEqual(r["status"], SUCCESS)
        self.assertFalse(r["independent_pr_review"])
        self.assertEqual(r["strict_tests"], 295)

    def test_expected_github_archive_digests(self):
        self.assertEqual(inspect(self.verify, self.strict,
                expected_verify_zip_sha256=digest(self.verify.read_bytes()),
                expected_strict_zip_sha256=digest(self.strict.read_bytes()))["status"], SUCCESS)
        with self.assertRaises(AuditError):
            inspect(self.verify, self.strict, expected_verify_zip_sha256="f" * 64)

    def test_wrong_run_pin(self):
        self.reject_expected(lambda: inspect(self.verify, self.strict, expected_run_id="777"),
                             "EXPECTED_RUN_ID_MISMATCH")

    def reject_expected(self, thunk, expected):
        with self.assertRaises(AuditError) as cm:
            thunk()
        self.assertEqual(str(cm.exception), expected)

    def test_wrong_head_pin(self):
        self.reject_expected(lambda: inspect(self.verify, self.strict, expected_head_sha="d" * 40),
                             "EXPECTED_HEAD_SHA_MISMATCH")

    def test_checkout_sha_pin(self):
        self.assertEqual(inspect(self.verify, self.strict,
                expected_checkout_sha="a" * 40)["status"], SUCCESS)
        self.reject_expected(lambda: inspect(self.verify, self.strict,
                expected_checkout_sha="f" * 40), "EXPECTED_CHECKOUT_SHA_MISMATCH")

    def test_proof_bytes_differ(self):
        self.archive["strict"]["root/output/h00/pr-checkout.json"] += b" "
        self._write()
        self.reject("PARENT_PROOF_BYTES_DIFFER")

    def test_absent_proof_fails(self):
        del self.archive["verify"]["root/output/h00/pr-checkout.json"]
        self._write()
        self.reject("REQUIRED_ZIP_MEMBER_MISSING")

    def test_receipt_parent_digest_wrong(self):
        self._update_receipt("verify", lambda v: v["input_records"]["pr_checkout"].update(sha256="f" * 64))
        self.reject("PARENT_PROOF_DIGEST_MISMATCH")

    def test_receipt_run_swapped(self):
        self._update_receipt("strict", lambda v: v["run"].update(id="456"))
        self.reject("PR_RUN_IDENTITY_MISMATCH")

    def test_receipt_falsely_promoted(self):
        self._update_receipt("strict", lambda v: v.update(candidate_promoted=True))
        self.reject("RECEIPT_UNEARNED_PROMOTION")

    def test_receipt_mislabels_stage(self):
        self._update_receipt("verify", lambda v: v.update(stage="strict-torch"))
        self.reject("RECEIPT_STAGE_INVALID")

    def test_strict_summary_has_skip(self):
        self._update_receipt("strict", lambda v: v["strict_suite"].update(skipped=1))
        self.reject("STRICT_SUITE_SUMMARY_NOT_PASS")

    def test_repack_directory_roundtrip(self):
        folder = self.root / "artifact-dir"
        (folder / "root" / "output" / "h00").mkdir(parents=True)
        (folder / "root" / "output" / "h00" / "pr-checkout.json").write_bytes(
            self.archive["verify"]["root/output/h00/pr-checkout.json"])
        repack_directory(folder, self.root / "repacked.zip")
        with zipfile.ZipFile(self.root / "repacked.zip") as z:
            self.assertEqual(z.namelist(), ["root/output/h00/pr-checkout.json"])

    def test_repack_rejects_symlink(self):
        folder = self.root / "dir-symlink"
        folder.mkdir()
        (folder / "link").symlink_to(self.verify)
        with self.assertRaisesRegex(AuditError, "ARTIFACT_DIRECTORY_UNSAFE_ENTRY"):
            repack_directory(folder, self.root / "repacked.zip")

    def test_repack_rejects_large_file(self):
        folder = self.root / "oversized-dir"
        folder.mkdir()
        with (folder / "oversized.bin").open("wb") as f:
            f.truncate(4_000_001)
        with self.assertRaisesRegex(AuditError, "ARTIFACT_DIRECTORY_MEMBER_SIZE_LIMIT"):
            repack_directory(folder, self.root / "repacked.zip")

    def test_archive_container_size_limit(self):
        with open(self.verify, "ab") as fp:
            fp.write(b"x" * 16_000_001)
        self.reject("ZIP_CONTAINER_SIZE_LIMIT")

    def test_zip_traversal(self):
        self.archive["verify"]["../outside.txt"] = b"bad"
        self._write()
        self.reject("UNSAFE_OR_DUPLICATE_ZIP_PATH")

    def test_duplicate_zip_path(self):
        with zipfile.ZipFile(self.verify, "a") as z:
            with self.assertWarns(UserWarning):
                z.writestr("root/output/h00/pr-checkout.json", b"bad")
        self.reject("UNSAFE_OR_DUPLICATE_ZIP_PATH")

    def test_nonfinite_json(self):
        self.archive["verify"]["root/output/h00/verify-receipt.json"] = b'{"status":NaN}'
        self._write()
        self.reject("INVALID_JSON")

    def test_duplicate_json_key(self):
        self.archive["verify"]["root/output/h00/verify-receipt.json"] = b'{"status":"x","status":"y"}'
        self._write()
        self.reject("INVALID_JSON")

    def test_parent_authority_forgery(self):
        self.proof["authority"] = "EXTERNAL_ATTESTATION"
        self._prepare()
        self.reject("PARENT_PROOF_AUTHORITY_INVALID")

    def test_forged_proof_true_but_wrong_parent(self):
        self.proof["parent_shas"] = ["b" * 40, "c" * 40]
        self._prepare()
        self.reject("PR_PARENTS_MISMATCH")


if __name__ == "__main__":
    unittest.main()
