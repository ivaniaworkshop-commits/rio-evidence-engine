import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from release_readiness_r031 import (assess,matching,ReleaseGateError,
    TARGET_REF,EXPECTED_REPO,R030_ANCHOR)

def ruleset(**kwargs):
    base={
      "target":"branch","enforcement":"active",
      "conditions":{"ref_name":{"include":[TARGET_REF],"exclude":[]}},
      "bypass_actors":[],
      "rules":[
         {"type":"pull_request","parameters":{"required_approving_review_count":1}},
         {"type":"deletion"},
         {"type":"non_fast_forward"},
         {"type":"required_status_checks","parameters":{"required_status_checks":[{"context":"verify"}]}}
      ]
    }
    base.update(kwargs)
    return base

class CandidateGate(unittest.TestCase):
    def test_empty_rule_list_denies(self):
        self.assertEqual(assess([])["result"],"BLOCKED_NO_EXACT_ACTIVE_RELEASE_RULESET")
    def test_main_protection_does_not_protect_candidate(self):
        x=ruleset(conditions={"ref_name":{"include":["refs/heads/main"],"exclude":[]}})
        self.assertFalse(matching(x,TARGET_REF))
        self.assertEqual(assess([x])["deployment_enabled"],False)
    def test_inactive_rule_not_a_protection(self):
        self.assertEqual(assess([ruleset(enforcement="evaluate")])["result"],
                         "BLOCKED_NO_EXACT_ACTIVE_RELEASE_RULESET")
    def test_global_wildcard_not_explicit_target(self):
        x=ruleset(conditions={"ref_name":{"include":["~ALL"],"exclude":[]}})
        self.assertFalse(matching(x,TARGET_REF))
    def test_exact_branch_excluded(self):
        x=ruleset(conditions={"ref_name":{"include":[TARGET_REF],"exclude":[TARGET_REF]}})
        self.assertFalse(matching(x,TARGET_REF))
    def test_bypass_never_allowed(self):
        x=ruleset(bypass_actors=[{"actor_id":1,"bypass_mode":"always"}])
        with self.assertRaisesRegex(ReleaseGateError,"BYPASS"):assess([x])
    def test_review_count_zero_blocks(self):
        x=ruleset()
        x["rules"][0]["parameters"]["required_approving_review_count"]=0
        self.assertEqual(assess([x])["result"],"BLOCKED_INCOMPLETE_RELEASE_RULESET")
    def test_review_bool_not_valid_int(self):
        x=ruleset()
        x["rules"][0]["parameters"]["required_approving_review_count"]=True
        self.assertEqual(assess([x])["result"],"BLOCKED_INCOMPLETE_RELEASE_RULESET")
    def test_missing_status_checks_blocks(self):
        x=ruleset()
        x["rules"]=x["rules"][:3]
        self.assertIn("required_status_checks",assess([x])["missing_required_rule_types"])
    def test_empty_status_checks_blocks(self):
        x=ruleset()
        x["rules"][3]["parameters"]["required_status_checks"]=[]
        self.assertEqual(assess([x])["result"],"BLOCKED_INCOMPLETE_RELEASE_RULESET")
    def test_multiple_partial_rulesets_do_not_combine(self):
        a=ruleset();a["rules"]=a["rules"][:2]
        b=ruleset();b["rules"]=b["rules"][2:]
        self.assertEqual(assess([a,b])["result"],"BLOCKED_INCOMPLETE_RELEASE_RULESET")
    def test_valid_mock_never_activates_release(self):
        r=assess([ruleset()])
        self.assertEqual(r["result"],"RULESET_CONTRACT_VERIFIED_ENVIRONMENT_UNVERIFIED")
        self.assertFalse(r["deployment_enabled"])
        self.assertFalse(r["vercel_token_verified"])
        self.assertFalse(r["host_identity_authorized"])
        self.assertEqual(r["source_ancestor_required"],R030_ANCHOR)
    def test_different_repository_rejected(self):
        with self.assertRaisesRegex(ReleaseGateError,"IDENTITY"):
            assess([ruleset()],repository="untrusted/other")
    def test_different_branch_rejected(self):
        with self.assertRaisesRegex(ReleaseGateError,"IDENTITY"):
            assess([ruleset()],branch="refs/heads/main")
    def test_nonlist_fails_closed(self):
        with self.assertRaisesRegex(ReleaseGateError,"LIST"):assess({})
    def test_cli_enforce_empty_exits_two_with_safe_result(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"rules.json";p.write_text("[]",encoding="utf-8")
            script=Path(__file__).resolve().parents[1]/"release_readiness_r031.py"
            run=subprocess.run([sys.executable,str(script),"--rulesets",str(p),"--enforce"],
                capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,2)
            self.assertFalse(json.loads(run.stdout)["deployment_enabled"])
    def test_cli_observe_empty_is_explicit_blocked(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"rules.json";p.write_text("[]",encoding="utf-8")
            script=Path(__file__).resolve().parents[1]/"release_readiness_r031.py"
            run=subprocess.run([sys.executable,str(script),"--rulesets",str(p)],
                capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,0)
            self.assertEqual(json.loads(run.stdout)["result"],"BLOCKED_NO_EXACT_ACTIVE_RELEASE_RULESET")
    def test_cli_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"rules.json";p.write_text('{"a":1,"a":2}',encoding="utf-8")
            script=Path(__file__).resolve().parents[1]/"release_readiness_r031.py"
            run=subprocess.run([sys.executable,str(script),"--rulesets",str(p)],
                capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,2)
            self.assertIn("FAIL_CLOSED",run.stderr)

if __name__=="__main__":unittest.main()
