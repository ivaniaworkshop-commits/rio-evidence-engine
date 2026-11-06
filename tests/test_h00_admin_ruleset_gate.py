"""R023 offline regression suite for the read-only administrative ruleset gate."""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import h00_admin_ruleset_gate as gate


def policy_fixture():
    return {
        "id": gate.RULESET_ID,
        "name": "RIO_MAIN_PROTECTION_R001",
        "source": gate.REPO,
        "source_type": "Repository",
        "target": "branch", "enforcement": "active",
        "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
        "bypass_actors": [],
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {"type": "pull_request", "parameters": {
                "required_approving_review_count": 1,
                "dismiss_stale_reviews_on_push": True,
                "require_last_push_approval": True,
            }},
            {"type": "required_status_checks", "parameters": {
                "strict_required_status_checks_policy": True,
                "do_not_enforce_on_create": False,
                "required_status_checks": [
                    {"context": name, "integration_id": gate.ACTIONS_APP_ID}
                    for name in gate.REQUIRED_CONTEXTS
                ],
            }},
        ],
    }


def runner_fixture():
    return {
        "GITHUB_REPOSITORY": gate.REPO,
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_REF": "refs/pull/26/merge",
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_TOKEN": "synthetic-token-not-for-github",
    }


class RulesetGateTests(unittest.TestCase):
    def setUp(self):
        self.policy = policy_fixture()

    def test_valid_policy_passes_without_claiming_independent_review(self):
        checks = gate.verify_ruleset(self.policy)
        self.assertTrue(checks)
        self.assertTrue(all(checks.values()), checks)
        report = gate.audit(runner_fixture(),
                            fetch=lambda token: (self.policy, "f" * 64))
        self.assertEqual(report["status"], gate.PASS)
        self.assertFalse(report["independent_approval_observed"])
        self.assertFalse(report["external_holdout_authenticated"])
        self.assertFalse(report["candidate_promoted"])

    def test_missing_required_status_checks_is_blocked(self):
        self.policy["rules"].pop()
        self.assertFalse(gate.verify_ruleset(self.policy)[
            "required_status_checks_present"])

    def test_legacy_only_two_checks_is_insufficient(self):
        self.policy["rules"][-1]["parameters"]["required_status_checks"] = [
            {"context": x, "integration_id": gate.ACTIONS_APP_ID}
            for x in ("verify", "strict-torch")
        ]
        self.assertFalse(gate.verify_ruleset(self.policy)[
            "required_check_contexts_exact"])

    def test_cross_audit_must_be_required(self):
        self.policy["rules"][-1]["parameters"]["required_status_checks"] = [
            c for c in self.policy["rules"][-1]["parameters"]["required_status_checks"]
            if c["context"] != "H00 cross-audit receipts (read-only)"
        ]
        self.assertFalse(gate.verify_ruleset(self.policy)[
            "required_check_contexts_exact"])

    def test_policy_gate_must_require_itself(self):
        self.policy["rules"][-1]["parameters"]["required_status_checks"] = [
            c for c in self.policy["rules"][-1]["parameters"]["required_status_checks"]
            if c["context"] != "H00 admin policy gate (read-only)"
        ]
        self.assertFalse(gate.verify_ruleset(self.policy)[
            "required_check_contexts_exact"])

    def test_signer_check_must_not_be_required_on_pr(self):
        self.policy["rules"][-1]["parameters"]["required_status_checks"].append(
            {"context": "Attest H00 CI receipts (GitHub OIDC + Sigstore)",
             "integration_id": gate.ACTIONS_APP_ID}
        )
        self.assertFalse(gate.verify_ruleset(self.policy)[
            "required_check_contexts_exact"])

    def test_all_checks_pinned_to_actual_actions_app(self):
        self.policy["rules"][-1]["parameters"]["required_status_checks"][0][
            "integration_id"] = 12345
        self.assertFalse(gate.verify_ruleset(self.policy)[
            "required_checks_pinned_to_github_actions"])

    def test_status_checks_require_updated_base(self):
        self.policy["rules"][-1]["parameters"]["strict_required_status_checks_policy"] = False
        self.assertFalse(gate.verify_ruleset(self.policy)["require_updated_base"])

    def test_no_create_bypass(self):
        self.policy["rules"][-1]["parameters"]["do_not_enforce_on_create"] = True
        self.assertFalse(gate.verify_ruleset(self.policy)["no_create_bypass"])

    def test_reviewer_requirements_are_not_optional(self):
        for key, value, check in (
            ("required_approving_review_count", 0, "one_independent_approval_required"),
            ("required_approving_review_count", True, "one_independent_approval_required"),
            ("dismiss_stale_reviews_on_push", False, "stale_approvals_dismissed"),
            ("require_last_push_approval", False, "last_push_approval_required"),
        ):
            with self.subTest(key=key, value=value):
                obj = policy_fixture()
                obj["rules"][2]["parameters"][key] = value
                self.assertFalse(gate.verify_ruleset(obj)[check])

    def test_absent_bypass_field_is_unknown_and_blocks(self):
        self.policy.pop("bypass_actors")
        checks = gate.verify_ruleset(self.policy)
        self.assertIsNone(checks["no_bypass"])
        report = gate.audit(runner_fixture(),
                            fetch=lambda token: (self.policy, "d" * 64))
        self.assertEqual(report["status"], gate.BLOCK)
        self.assertIsNone(report["checks"]["no_bypass"])
        self.assertEqual(report["bypass_readback_visibility"], "NOT_RETURNED")
        self.assertIn("no_bypass", report["failure_codes"])

    def test_bypass_actors_are_never_acceptable(self):
        self.policy["bypass_actors"] = [
            {"actor_id": 1, "actor_type": "OrganizationAdmin", "bypass_mode": "always"}
        ]
        self.assertFalse(gate.verify_ruleset(self.policy)["no_bypass"])

    def test_only_main_can_be_targeted(self):
        for include, exclude in (
            (["refs/heads/*"], []),
            (["refs/heads/main"], ["refs/heads/old"]),
        ):
            with self.subTest(include=include, exclude=exclude):
                self.policy["conditions"]["ref_name"] = {
                    "include": include, "exclude": exclude,
                }
                self.assertFalse(gate.verify_ruleset(self.policy)["main_only"])

    def test_wrong_repo_or_inactive_fail(self):
        self.policy["source"] = "untrusted/fork"
        self.policy["enforcement"] = "evaluate"
        checks = gate.verify_ruleset(self.policy)
        self.assertFalse(checks["repository_identity"])
        self.assertFalse(checks["active"])

    def test_branch_deletion_and_force_push_controls(self):
        self.policy["rules"] = self.policy["rules"][2:]
        checks = gate.verify_ruleset(self.policy)
        self.assertFalse(checks["no_deletion"])
        self.assertFalse(checks["no_force_push"])

    def test_duplicate_check_rules_rejected(self):
        self.policy["rules"].append(self.policy["rules"][-1].copy())
        self.assertFalse(gate.verify_ruleset(self.policy)[
            "required_status_checks_present"])

    def test_duplicate_check_context_not_accepted(self):
        self.policy["rules"][-1]["parameters"]["required_status_checks"][-1] = (
            self.policy["rules"][-1]["parameters"]["required_status_checks"][0].copy()
        )
        self.assertFalse(gate.verify_ruleset(self.policy)[
            "required_check_contexts_exact"])

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(ValueError):
            gate.parse_policy(b'{"id":1,"id":2}')

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(ValueError):
            gate.parse_policy(b'{"id":NaN}')

    def test_response_size_limit(self):
        with self.assertRaises(ValueError):
            gate.parse_policy(b" " * (gate.MAX_BYTES + 1))

    def test_api_is_strictly_get_read_only_and_digest_is_raw(self):
        raw = json.dumps(self.policy).encode("utf-8")
        inspected = []
        def urlopen(req, timeout):
            inspected.append((req.full_url, req.get_method(), timeout,
                              req.get_header("Authorization")))
            return io.BytesIO(raw)
        with patch.object(gate.urllib.request, "urlopen", side_effect=urlopen):
            obj, digest = gate.get_policy("synthetic-token-not-for-github")
        self.assertEqual(obj["id"], gate.RULESET_ID)
        self.assertEqual(len(digest), 64)
        self.assertEqual(inspected[0][1], "GET")
        self.assertEqual(inspected[0][2], 10)
        self.assertIn("/rulesets/26688691", inspected[0][0])
        self.assertEqual(inspected[0][3], "Bearer synthetic-token-not-for-github")

    def test_no_token_is_not_silent_anonymous_success(self):
        with self.assertRaisesRegex(ValueError, "TOKEN_MISSING"):
            gate.get_policy("")

    def test_missing_token_blocks_audit_without_leaking_token(self):
        report = gate.audit(runner_fixture(),
                            fetch=lambda token: (_ for _ in ()).throw(ValueError("TOKEN_MISSING")))
        self.assertEqual(report["status"], gate.BLOCK)
        self.assertEqual(report["failure_codes"], ["RULESET_READBACK_FAILED"])

    def test_non_pr_context_cannot_pass(self):
        env = runner_fixture()
        env["GITHUB_EVENT_NAME"] = "push"
        calls = []
        def fake_fetch(token):
            calls.append(1)
            return self.policy, "e" * 64
        report = gate.audit(env, fetch=fake_fetch)
        self.assertEqual(report["status"], gate.BLOCK)
        self.assertEqual(calls, [])
        self.assertIn("INVALID_RUN_CONTEXT", report["failure_codes"])

    def test_missing_rule_produces_specific_failure_codes(self):
        self.policy["rules"].pop()
        report = gate.audit(runner_fixture(),
                            fetch=lambda token: (self.policy, "a" * 64))
        self.assertEqual(report["status"], gate.BLOCK)
        self.assertIn("required_status_checks_present", report["failure_codes"])
        self.assertFalse(report["independent_approval_observed"])

    def test_cli_writes_blocked_receipt_and_returns_code_two(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "policy.json"
            with patch.object(gate, "audit", return_value={
                    "schema": gate.SCHEMA, "status": gate.BLOCK,
                    "failure_codes": ["required_status_checks_present"],
                    "candidate_promoted": False}):
                self.assertEqual(gate.main(["--output", str(p)]), 2)
            data = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(data["status"], gate.BLOCK)
            self.assertEqual(data["failure_codes"],
                             ["required_status_checks_present"])

    def test_workflow_wires_policy_as_read_only_job(self):
        wf = (Path(__file__).resolve().parents[1] /
              ".github/workflows/h00-integrity.yml").read_text(encoding="utf-8")
        section = wf.split("\n  admin-policy:\n")
        self.assertEqual(len(section), 2)
        body = section[1].split("\n  attest-receipts:", 1)[0]
        self.assertIn("name: H00 admin policy gate (read-only)", body)
        self.assertIn("contents: read", body)
        self.assertNotIn("contents: write", body)
        self.assertNotIn("attestations: write", body)
        self.assertNotIn("id-token: write", body)
        self.assertIn("python3 -m scripts.h00_admin_ruleset_gate", body)
        self.assertIn("if: always()", body)
        self.assertIn("h00-admin-policy-", body)


if __name__ == "__main__":
    unittest.main()
