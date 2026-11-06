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
