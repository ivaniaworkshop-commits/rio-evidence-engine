"""Fail-closed receipts are metadata, not external verification."""
import json
import tempfile
import unittest
from pathlib import Path

from scripts.h00_ci_receipt import VERIFY_FILES, _load_json, build_receipt


ENV = {"GITHUB_REPOSITORY": "ivaniaworkshop-commits/rio-evidence-engine",
       "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "123",
       "GITHUB_RUN_ATTEMPT": "1", "GITHUB_EVENT_NAME": "pull_request",
       "GITHUB_REF": "refs/pull/26/merge"}


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
        self.env = dict(ENV)
        self.event = {
            "number": 26, "repository": {"full_name": ENV["GITHUB_REPOSITORY"]},
            "pull_request": {
                "number": 26, "merge_commit_sha": "a" * 40,
                "head": {"sha": "b" * 40, "ref": "feature",
                         "repo": {"full_name": ENV["GITHUB_REPOSITORY"]}},
                "base": {"sha": "c" * 40, "ref": "main",
                         "repo": {"full_name": ENV["GITHUB_REPOSITORY"]}},
            },
        }
        self.event_path = self.root / "github-event.json"
        self.env["GITHUB_EVENT_PATH"] = str(self.event_path)
        self._save_event()
        self.pr_checkout_path = self.root / "pr-checkout.json"
        self.pr_proof = {
            "schema": "RIO_H00_PR_PARENT_BINDING/1.0",
            "status": "RUNNER_GIT_PARENT_BINDING_PASS",
            "reason_code": None,
            "authority": "RUNNER_GIT_OBJECT_AND_EVENT_NOT_INDEPENDENT",
            "run_id": self.env["GITHUB_RUN_ID"],
            "attempt": self.env["GITHUB_RUN_ATTEMPT"],
            "checkout_sha": self.env["GITHUB_SHA"],
            "pr_number": 26,
            "head_sha": "b" * 40, "base_sha": "c" * 40,
            "parent_shas": ["c" * 40, "b" * 40],
            "event_merge_matches_checkout": True,
            "candidate_promoted": False,
            "production_ready": False,
            "external_holdout_authenticated": False,
        }
        self._save_proof()

    def _save_proof(self):
        self.pr_checkout_path.write_text(json.dumps(self.pr_proof), encoding="utf-8")


    def _save_event(self):
        self.event_path.write_text(json.dumps(self.event), encoding="utf-8")

    def test_complete_verify_is_still_not_production(self):
        r = build_receipt("verify", "success", self.root, env=self.env)
        self.assertEqual(r["status"], "COMPLETE_LOCAL_CI_RECEIPT")
        self.assertFalse(r["candidate_promoted"])
        self.assertFalse(r["external_holdout_authenticated"])
        self.assertEqual(len(r["input_records"]), 9)
        self.assertTrue(r["checks"]["pr_checkout_parent_binding"])
        self.assertEqual(r["run"]["pull_request"]["checkout_parent_binding"],
                         "RUNNER_REPORT_CONSISTENT_NOT_INDEPENDENT")
        self.assertEqual(r["run"]["pull_request"]["parent_binding_report_sha256"],
                         r["input_records"]["pr_checkout"]["sha256"])


    def test_pr_head_and_merge_checkout_are_distinct(self):
        report = build_receipt("verify", "success", self.root, env=self.env)
        self.assertEqual(report["status"], "COMPLETE_LOCAL_CI_RECEIPT")
        self.assertTrue(report["checks"]["github_pr_context_consistent"])
        self.assertEqual(report["run"]["sha"], "a" * 40)
        self.assertEqual(report["run"]["pull_request"]["head_sha"], "b" * 40)
        self.assertEqual(report["run"]["pull_request"]["base_sha"], "c" * 40)
        self.assertEqual(report["run"]["pull_request"]["checkout_kind"],
                         "GITHUB_PR_SYNTHETIC_MERGE")

    def test_pr_missing_event_payload_fails_closed(self):
        self.env.pop("GITHUB_EVENT_PATH")
        result = build_receipt("verify", "success", self.root, env=self.env)
        self.assertEqual(result["status"], "INCOMPLETE_OR_FAILED")
        self.assertFalse(result["checks"]["github_pr_context_consistent"])

    def test_pr_wrong_number_or_ref_fails_closed(self):
        self.event["number"] = 27
        self._save_event()
        result = build_receipt("verify", "success", self.root, env=self.env)
        self.assertEqual(result["status"], "INCOMPLETE_OR_FAILED")
        self.event["number"] = 26
        self.env["GITHUB_REF"] = "refs/pull/25/merge"
        self._save_event()
        result = build_receipt("verify", "success", self.root, env=self.env)
        self.assertEqual(result["status"], "INCOMPLETE_OR_FAILED")

    def test_pr_wrong_base_repository_fails_closed(self):
        self.event["pull_request"]["base"]["repo"]["full_name"] = "different/repo"
        self._save_event()
        report = build_receipt("verify", "success", self.root, env=self.env)
        self.assertFalse(report["checks"]["github_pr_context_consistent"])

    def test_pr_invalid_head_or_base_sha_fails_closed(self):
        for label in ("head", "base"):
            with self.subTest(label=label):
                self.event["pull_request"][label]["sha"] = "not-a-sha"
                self._save_event()
                result = build_receipt("verify", "success", self.root, env=self.env)
                self.assertEqual(result["status"], "INCOMPLETE_OR_FAILED")
                self.event["pull_request"][label]["sha"] = ("b" if label == "head" else "c") * 40

    def test_pr_event_merge_checkout_difference_is_advisory(self):
        self.event["pull_request"]["merge_commit_sha"] = "d" * 40
        self.pr_proof["event_merge_matches_checkout"] = False
        self._save_proof()
        self._save_event()
        report = build_receipt("verify", "success", self.root, env=self.env)
        self.assertEqual(report["status"], "COMPLETE_LOCAL_CI_RECEIPT")
        self.assertFalse(report["run"]["pull_request"]["event_merge_matches_checkout"])
        self.assertTrue(report["checks"]["pr_checkout_parent_binding"])
        self.assertEqual(report["run"]["pull_request"]["checkout_parent_binding"],
                         "RUNNER_REPORT_CONSISTENT_NOT_INDEPENDENT")

    def test_pr_duplicate_event_json_key_fails_closed(self):
        self.event_path.write_text('{"number":26,"number":27}', encoding="utf-8")
        self.assertEqual(build_receipt("verify", "success", self.root, env=self.env)["status"],
                         "INCOMPLETE_OR_FAILED")

    def test_fork_pr_preserves_head_repository_without_granting_trust(self):
        self.event["pull_request"]["head"]["repo"]["full_name"] = "forkuser/fork"
        self._save_event()
        report = build_receipt("verify", "success", self.root, env=self.env)
        self.assertEqual(report["status"], "COMPLETE_LOCAL_CI_RECEIPT")
        self.assertEqual(report["run"]["pull_request"]["head_repository"], "forkuser/fork")
        self.assertFalse(report["external_holdout_authenticated"])

    def test_non_pr_has_no_fabricated_pr_identity(self):
        env = {**self.env, "GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/main"}
        env.pop("GITHUB_EVENT_PATH")
        report = build_receipt("verify", "success", self.root, env=env)
        self.assertIsNone(report["run"]["pull_request"])
        self.assertNotIn("github_pr_context_consistent", report["checks"])


    def test_missing_parent_proof_fails_both_jobs(self):
        self.pr_checkout_path.unlink()
        for job in ("verify", "strict-torch"):
            if job == "strict-torch":
                self._write_strict_log()
            with self.subTest(job=job):
                result = build_receipt(job, "success", self.root, env=self.env)
                self.assertEqual(result["status"], "INCOMPLETE_OR_FAILED")
                self.assertFalse(result["checks"]["pr_checkout_parent_binding"])
                self.assertTrue(result["input_records"]["pr_checkout"]["missing_or_invalid"])

    def _write_strict_log(self):
        (self.root / "h00_strict_tests.log").write_text(
            json.dumps({"status": "PASS_NO_SKIPS", "tests_run": 287,
                        "failed": 0, "errors": 0, "skipped": 0}) + "\n",
            encoding="utf-8")

    def test_parent_proof_recorded_in_strict_receipt(self):
        self._write_strict_log()
        report = build_receipt("strict-torch", "success", self.root, env=self.env)
        self.assertEqual(report["status"], "COMPLETE_LOCAL_CI_RECEIPT")
        self.assertIn("sha256", report["input_records"]["pr_checkout"])
        self.assertTrue(report["checks"]["pr_checkout_parent_binding"])

    def test_parent_proof_rejects_false_authority_or_status(self):
        for field, value in (
            ("authority", "INDEPENDENT_EVALUATOR"),
            ("status", "BLOCKED"),
            ("reason_code", "UNEXPECTED"),
            ("candidate_promoted", True),
            ("production_ready", True),
            ("external_holdout_authenticated", True),
            ("schema", "FAKE_SCHEMA"),
        ):
            with self.subTest(field=field):
                original = self.pr_proof[field]
                self.pr_proof[field] = value
                self._save_proof()
                result = build_receipt("verify", "success", self.root, env=self.env)
                self.assertEqual(result["status"], "INCOMPLETE_OR_FAILED")
                self.assertFalse(result["checks"]["pr_checkout_parent_binding"])
                self.pr_proof[field] = original

    def test_parent_proof_rejects_stale_run_checkout_or_pr(self):
        for field, value in (
            ("run_id", "4321"), ("attempt", "2"),
            ("checkout_sha", "d" * 40), ("pr_number", 25),
            ("head_sha", "f" * 40), ("base_sha", "e" * 40),
            ("parent_shas", ["b" * 40, "c" * 40]),
            ("event_merge_matches_checkout", False),
        ):
            with self.subTest(field=field):
                original = self.pr_proof[field]
                self.pr_proof[field] = value
                self._save_proof()
                result = build_receipt("verify", "success", self.root, env=self.env)
                self.assertEqual(result["status"], "INCOMPLETE_OR_FAILED")
                self.assertFalse(result["checks"]["pr_checkout_parent_binding"])
                self.pr_proof[field] = original

    def test_parent_proof_rejects_duplicate_keys_and_nonfinite(self):
        for bad in ('{"status":"PASS","status":"BLOCKED"}',
                    '{"status":NaN}'):
            with self.subTest(bad=bad):
                self.pr_checkout_path.write_text(bad, encoding="utf-8")
                result = build_receipt("verify", "success", self.root, env=self.env)
                self.assertEqual(result["status"], "INCOMPLETE_OR_FAILED")
                self.assertTrue(result["input_records"]["pr_checkout"]["missing_or_invalid"])

    def test_push_does_not_fabricate_parent_binding(self):
        env = {**self.env, "GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/main"}
        self.pr_checkout_path.unlink()
        result = build_receipt("verify", "success", self.root, env=env)
        self.assertEqual(result["status"], "COMPLETE_LOCAL_CI_RECEIPT")
        self.assertNotIn("pr_checkout", result["input_records"])
        self.assertNotIn("pr_checkout_parent_binding", result["checks"])

    def test_parent_proof_with_wrong_shape_fails_closed(self):
        for value in (None, [], "RUNNER_GIT_PARENT_BINDING_PASS"):
            with self.subTest(value=value):
                self.pr_checkout_path.write_text(json.dumps(value), encoding="utf-8")
                result = build_receipt("verify", "success", self.root, env=self.env)
                self.assertEqual(result["status"], "INCOMPLETE_OR_FAILED")
                self.assertFalse(result["checks"]["pr_checkout_parent_binding"])

    def test_parent_proof_explicit_override_path(self):
        destination = self.root / "evidence" / "parent.json"
        destination.parent.mkdir()
        self.pr_checkout_path.rename(destination)
        self.assertEqual(
            build_receipt("verify", "success", self.root, env=self.env)["status"],
            "INCOMPLETE_OR_FAILED")
        result = build_receipt("verify", "success", self.root, env=self.env,
                               pr_checkout_path=destination)
        self.assertEqual(result["status"], "COMPLETE_LOCAL_CI_RECEIPT")

    def test_missing_input_fails_closed(self):
        (self.root / "h08.json").unlink()
        self.assertEqual(build_receipt("verify", "success", self.root, env=self.env)["status"], "INCOMPLETE_OR_FAILED")

    def test_fake_external_success_fails_closed(self):
        f = self.root / "h08.json"
        f.write_text(json.dumps({"status": "PROMOTED", "candidate_promoted": True}), encoding="utf-8")
        r = build_receipt("verify", "success", self.root, env=self.env)
        self.assertFalse(r["checks"]["h08_independence_fail_closed"])
        self.assertEqual(r["status"], "INCOMPLETE_OR_FAILED")

    def test_failure_collects_without_green_claim(self):
        self.assertEqual(build_receipt("verify", "failure", self.root, env=self.env)["status"], "INCOMPLETE_OR_FAILED")

    def test_no_git_sha_fails_closed(self):
        self.assertEqual(build_receipt("verify", "success", self.root, env={})["status"], "INCOMPLETE_OR_FAILED")

    def test_strict_summary(self):
        f = self.root / "h00_strict_tests.log"
        f.write_text('Ran 265 tests\n' + json.dumps({"status": "PASS_NO_SKIPS", "tests_run": 265,
            "failed": 0, "errors": 0, "skipped": 0}) + '\n', encoding="utf-8")
        r = build_receipt("strict-torch", "success", self.root, env=self.env)
        self.assertEqual(r["status"], "COMPLETE_LOCAL_CI_RECEIPT")
        self.assertEqual(r["strict_suite"]["tests_run"], 265)

    def test_strict_skip_fails_closed(self):
        f = self.root / "h00_strict_tests.log"
        f.write_text(json.dumps({"status": "FAIL_OR_SKIPPED", "tests_run": 3,
            "failed": 0, "errors": 0, "skipped": 1}) + '\n', encoding="utf-8")
        self.assertEqual(build_receipt("strict-torch", "success", self.root, env=self.env)["status"], "INCOMPLETE_OR_FAILED")

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(ValueError):
            _load_json(b'{"status":"A","status":"B"}')

    def test_large_invalid_json_fails_closed(self):
        (self.root / "h12.json").write_text('{"bad":NaN}', encoding="utf-8")
        self.assertEqual(build_receipt("verify", "success", self.root, env=self.env)["status"], "INCOMPLETE_OR_FAILED")


class H00WorkflowTrustBoundaryTests(unittest.TestCase):
    """Static fail-closed guard: a PR may run CI but must never mint an attestation."""

    GUARD = "    if: ${{ github.event_name == 'push' && github.ref == 'refs/heads/main' && github.ref_protected == true }}"

    @classmethod
    def setUpClass(cls):
        import re
        cls.source = (Path(__file__).resolve().parents[1] /
                      ".github/workflows/h00-integrity.yml").read_text(encoding="utf-8")
        parts = list(re.finditer(r"(?m)^  ([A-Za-z][A-Za-z0-9_-]*):\s*$", cls.source))
        cls.jobs = {m.group(1): cls.source[m.start():parts[i+1].start() if i+1 < len(parts)
                                             else len(cls.source)]
                    for i, m in enumerate(parts)}

    def test_signer_main_protected_push_only(self):
        signer = self.jobs["attest-receipts"]
        self.assertEqual([line for line in signer.splitlines() if line.startswith("    if: ")],
                         [self.GUARD])
        self.assertIn("    needs: [verify, strict-torch]", signer)
        self.assertIn("      id-token: write", signer)
        self.assertIn("      attestations: write", signer)

    def test_verification_is_post_merge_only(self):
        verifier = self.jobs["verify-attestation"]
        self.assertEqual([line for line in verifier.splitlines() if line.startswith("    if: ")],
                         [self.GUARD])
        self.assertIn("    needs: [attest-receipts]", verifier)
        self.assertNotIn("      id-token: write", verifier)
        self.assertNotIn("      attestations: write", verifier)

    def test_only_signer_has_signature_permissions(self):
        for name, block in self.jobs.items():
            if name != "attest-receipts":
                self.assertNotIn("      id-token: write", block, name)
                self.assertNotIn("      attestations: write", block, name)


    def test_main_push_guard_is_first_step_in_both_required_jobs(self):
        for name in ("verify", "strict-torch"):
            job = self.jobs[name]
            self.assertEqual(job.count("      - name: H00 reject green CI for unprotected main push"), 1)
            self.assertLess(job.index("      - name: H00 reject green CI for unprotected main push"),
                            job.index("      - uses: actions/checkout@"))
            self.assertIn("        if: ${{ github.event_name == 'push' && github.ref == 'refs/heads/main' }}", job)
            self.assertIn("          RIO_MAIN_REF_PROTECTED: ${{ github.ref_protected }}", job)
            self.assertIn('if [ "$RIO_MAIN_REF_PROTECTED" != "true" ]; then', job)
            self.assertIn("UNPROTECTED_MAIN_PUSH", job)
            self.assertIn("            exit 2", job)

    def test_pre_merge_signing_remains_guarded(self):
        signer = self.jobs["attest-receipts"]
        verifier = self.jobs["verify-attestation"]
        for job in (signer, verifier):
            self.assertEqual([x for x in job.splitlines() if x.startswith("    if: ")], [self.GUARD])
        self.assertIn("      attestations: write", signer)
        self.assertNotIn("      attestations: write", verifier)


    @staticmethod
    def _actual_main_guard_script(job):
        """Extract the Bash run block from the checked-in workflow, not a copied fixture."""
        marker = "      - name: H00 reject green CI for unprotected main push"
        parts = job.split(marker)
        if len(parts) != 2:
            raise AssertionError("GUARD_STEP_AMBIGUOUS")
        block = parts[1].split("\n      - ", 1)[0].splitlines()
        try:
            start = block.index("        run: |") + 1
        except ValueError as exc:
            raise AssertionError("GUARD_SCRIPT_MISSING") from exc
        lines = block[start:]
        if not lines or any(not line.startswith("          ") for line in lines if line.strip()):
            raise AssertionError("GUARD_SCRIPT_INDENTATION_INVALID")
        script = "\n".join(line[10:] for line in lines) + "\n"
        if "UNPROTECTED_MAIN_PUSH" not in script or "exit 2" not in script:
            raise AssertionError("GUARD_SCRIPT_UNEXPECTED")
        return script

    def _execute_guard(self, job_name, value):
        """Run actual YAML Bash with isolated environment and no repository writes."""
        import os
        import subprocess
        script = self._actual_main_guard_script(self.jobs[job_name])
        env = {"PATH": os.defpath}
        if value is not None:
            env["RIO_MAIN_REF_PROTECTED"] = value
        with tempfile.TemporaryDirectory() as workdir:
            return subprocess.run(
                ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", script],
                cwd=workdir, env=env, capture_output=True, text=True, timeout=5,
                check=False,
            )

    def test_actual_guard_rejects_unprotected_or_unknown_context(self):
        for job in ("verify", "strict-torch"):
            for value in ("false", "", None, "0", "TRUE", "true "):
                with self.subTest(job=job, protected=value):
                    result = self._execute_guard(job, value)
                    self.assertEqual(result.returncode, 2, (result.stdout, result.stderr))
                    self.assertIn("UNPROTECTED_MAIN_PUSH", result.stdout)

    def test_actual_guard_accepts_exact_protected_true(self):
        for job in ("verify", "strict-torch"):
            with self.subTest(job=job):
                result = self._execute_guard(job, "true")
                self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
                self.assertNotIn("UNPROTECTED_MAIN_PUSH", result.stdout)

    def test_pre_merge_jobs_remain_available(self):
        self.assertIn("  pull_request:", self.source)
        self.assertIn("    branches: [main]", self.source)
        for name in ("verify", "strict-torch"):
            self.assertIn(name, self.jobs)
            self.assertNotIn("      attestations: write", self.jobs[name])


if __name__ == "__main__":
    unittest.main()
