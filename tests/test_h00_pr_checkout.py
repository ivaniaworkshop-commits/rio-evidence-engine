"""R016 executable Git parent-binding regressions; no remote mutations."""
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.h00_pr_checkout import PASS, verify_checkout

REPO_NAME = "ivaniaworkshop-commits/rio-evidence-engine"


class ParentBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sandbox = tempfile.TemporaryDirectory()
        cls.repo = Path(cls.sandbox.name) / "repo"
        cls.repo.mkdir()
        cls.git_env = dict(os.environ, GIT_AUTHOR_NAME="Río CI Regression",
                           GIT_AUTHOR_EMAIL="ci@example.invalid",
                           GIT_COMMITTER_NAME="Río CI Regression",
                           GIT_COMMITTER_EMAIL="ci@example.invalid")

        def git(*args):
            return subprocess.run(
                ["git", "-C", str(cls.repo), *args],
                check=True, env=cls.git_env, capture_output=True,
                text=True, timeout=15,
            ).stdout.strip()

        git("init", "-q", "-b", "main")
        git("commit", "--allow-empty", "-qm", "seed")
        git("checkout", "-qb", "feature")
        git("commit", "--allow-empty", "-qm", "head")
        cls.head = git("rev-parse", "HEAD")
        git("checkout", "-q", "main")
        git("commit", "--allow-empty", "-qm", "base")
        cls.base = git("rev-parse", "HEAD")
        git("merge", "--no-ff", "-qm", "integration", "feature")
        cls.checkout = git("rev-parse", "HEAD")

    @classmethod
    def tearDownClass(cls):
        cls.sandbox.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.event_path = Path(self.temp.name) / "event.json"
        self.event = {
            "number": 26, "repository": {"full_name": REPO_NAME},
            "pull_request": {
                "number": 26, "merge_commit_sha": "f" * 40,
                "head": {"sha": self.head, "ref": "feature",
                         "repo": {"full_name": REPO_NAME}},
                "base": {"sha": self.base, "ref": "main",
                         "repo": {"full_name": REPO_NAME}},
            },
        }
        self.env = {
            "GITHUB_REPOSITORY": REPO_NAME,
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_EVENT_PATH": str(self.event_path),
            "GITHUB_REF": "refs/pull/26/merge",
            "GITHUB_HEAD_REF": "feature",
            "GITHUB_BASE_REF": "main",
            "GITHUB_SHA": self.checkout,
            "GITHUB_RUN_ID": "1234",
            "GITHUB_RUN_ATTEMPT": "1",
        }
        self._write_event()

    def _write_event(self):
        self.event_path.write_text(json.dumps(self.event), encoding="utf-8")

    def test_two_parent_merge_passes_despite_stale_event_sha(self):
        result = verify_checkout(self.repo, self.env)
        self.assertEqual(result["status"], PASS, result)
        self.assertEqual(result["parent_shas"], [self.base, self.head])
        self.assertFalse(result["event_merge_matches_checkout"])
        self.assertFalse(result["candidate_promoted"])

    def test_rejects_wrong_head(self):
        self.event["pull_request"]["head"]["sha"] = "a" * 40
        self._write_event()
        self.assertEqual(verify_checkout(self.repo, self.env)["reason_code"],
                         "SECOND_PARENT_NOT_HEAD")

    def test_rejects_wrong_base(self):
        self.event["pull_request"]["base"]["sha"] = "b" * 40
        self._write_event()
        self.assertEqual(verify_checkout(self.repo, self.env)["reason_code"],
                         "FIRST_PARENT_NOT_BASE")

    def test_rejects_runner_checkout_mismatch(self):
        self.env["GITHUB_SHA"] = "c" * 40
        self.assertEqual(verify_checkout(self.repo, self.env)["reason_code"],
                         "CHECKOUT_SHA_MISMATCH")

    def test_rejects_swapped_parents(self):
        self.event["pull_request"]["head"]["sha"] = self.base
        self.event["pull_request"]["base"]["sha"] = self.head
        self._write_event()
        self.assertEqual(verify_checkout(self.repo, self.env)["reason_code"],
                         "FIRST_PARENT_NOT_BASE")

    def test_rejects_missing_event_payload(self):
        self.event_path.unlink()
        self.assertEqual(verify_checkout(self.repo, self.env)["reason_code"],
                         "INVALID_PR_EVENT_CONTEXT")

    def test_rejects_mismatched_pr_ref(self):
        self.env["GITHUB_REF"] = "refs/pull/25/merge"
        self.assertEqual(verify_checkout(self.repo, self.env)["reason_code"],
                         "INVALID_PR_EVENT_CONTEXT")

    def test_non_pr_event_cannot_pass(self):
        self.env["GITHUB_EVENT_NAME"] = "push"
        self.assertNotEqual(verify_checkout(self.repo, self.env)["status"], PASS)

    def test_shallow_clone_preserves_raw_commit_parents(self):
        clone = Path(self.temp.name) / "shallow"
        subprocess.run(
            ["git", "clone", "-q", "--depth", "1", self.repo.resolve().as_uri(), str(clone)],
            check=True, capture_output=True, timeout=15,
        )
        result = verify_checkout(clone, self.env)
        self.assertEqual(result["status"], PASS, result)

    def test_single_parent_commit_is_rejected(self):
        single = Path(self.temp.name) / "single"
        subprocess.run(
            ["git", "-C", str(self.repo), "worktree", "add", "--detach", "-q",
             str(single), self.head],
            check=True, capture_output=True, timeout=15,
        )
        self.env["GITHUB_SHA"] = self.head
        self.event["pull_request"]["merge_commit_sha"] = self.head
        self._write_event()
        self.assertEqual(verify_checkout(single, self.env)["reason_code"],
                         "PR_MERGE_PARENT_COUNT_INVALID")

    def test_both_pr_jobs_require_runner_parent_check(self):
        yaml = (Path(__file__).resolve().parents[1] /
                ".github/workflows/h00-integrity.yml").read_text(encoding="utf-8")
        parts = list(re.finditer(r"(?m)^  ([A-Za-z][A-Za-z0-9_-]*):\s*$", yaml))
        jobs = {m.group(1): yaml[m.start():parts[i + 1].start()
                                if i + 1 < len(parts) else len(yaml)]
                for i, m in enumerate(parts)}
        name = "      - name: H00 verify PR checkout parent binding"
        condition = "        if: " + chr(36) + "{{ github.event_name == 'pull_request' }}"
        for job_name, inventory_step in (
            ("verify", "Verify complete source inventory and byte hashes"),
            ("strict-torch", "Verify source before installing dependencies"),
        ):
            with self.subTest(job=job_name):
                body = jobs[job_name]
                self.assertEqual(body.count(name), 1)
                self.assertIn(condition, body)
                self.assertIn("python3 -m scripts.h00_pr_checkout", body)
                self.assertLess(body.index("      - uses: actions/checkout@"),
                                body.index(name))
                self.assertLess(body.index(name), body.index(inventory_step))


if __name__ == "__main__":
    unittest.main()
