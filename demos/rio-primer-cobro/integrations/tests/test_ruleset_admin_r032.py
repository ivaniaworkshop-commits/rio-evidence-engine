import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ruleset_admin_r032 import (
  blueprint,plan,apply,validate_observed_ruleset,AdminGateError,
  NAME,CI,TARGET_REF,EXPECTED_REPO)
from release_readiness_r031 import assess

SHA="a"*40
def readback():
    return {"id":444,**blueprint()}
class AdminRulesetR032(unittest.TestCase):
    def test_plan_offline_never_activates_production(self):
        result=plan()
        self.assertEqual(result["state"],"PLAN_ONLY_NOT_APPLIED")
        self.assertFalse(result["write_executed"])
        self.assertFalse(result["deployment_enabled"])
    def test_spec_exact_branch_only(self):
        x=blueprint()
        self.assertEqual(x["conditions"]["ref_name"]["include"],[TARGET_REF])
        self.assertEqual(x["conditions"]["ref_name"]["exclude"],[])
    def test_no_bypass(self):
        self.assertEqual(blueprint()["bypass_actors"],[])
    def test_all_three_producer_pinned_checks(self):
        checks=blueprint()["rules"][-1]["parameters"]["required_status_checks"]
        self.assertEqual({c["context"] for c in checks},set(CI))
        self.assertEqual({c["integration_id"] for c in checks},{15368})
    def test_stale_reviews_dismissed(self):
        self.assertIs(blueprint()["rules"][2]["parameters"]["dismiss_stale_reviews_on_push"],True)
    def test_last_pusher_not_sole_approver(self):
        self.assertIs(blueprint()["rules"][2]["parameters"]["require_last_push_approval"],True)
    def test_strict_status_freshness(self):
        self.assertIs(blueprint()["rules"][-1]["parameters"]["strict_required_status_checks_policy"],True)
    def test_spec_passes_readonly_evaluator_but_not_deployed(self):
        self.assertTrue(assess([blueprint()])["rule_contract_observed"])
        self.assertFalse(assess([blueprint()])["deployment_enabled"])
    def test_valid_readback(self):
        self.assertEqual(validate_observed_ruleset(readback())["result"],"ACTIVE_RULESET_CONTRACT_READBACK")
    def test_wrong_name_rejected(self):
        with self.assertRaises(AdminGateError):
            validate_observed_ruleset({**readback(),"name":"OTHER"})
    def test_foreign_check_producer_rejected(self):
        x=readback()
        x["rules"][-1]["parameters"]["required_status_checks"][1]["integration_id"]=999
        with self.assertRaises(Exception):validate_observed_ruleset(x)
    def test_missing_candidate_check_rejected(self):
        x=readback();x["rules"][-1]["parameters"]["required_status_checks"].pop()
        with self.assertRaises(Exception):validate_observed_ruleset(x)
    def test_non_strict_rule_rejected(self):
        x=readback();x["rules"][-1]["parameters"]["strict_required_status_checks_policy"]=False
        with self.assertRaises(Exception):validate_observed_ruleset(x)
    def test_bypass_rejected(self):
        x=readback();x["bypass_actors"]=[{"actor_id":1}]
        with self.assertRaises(Exception):validate_observed_ruleset(x)
    def test_apply_needs_explicit_branch_confirmation(self):
        with self.assertRaisesRegex(AdminGateError,"CONFIRMATION"):
            apply("wrong",SHA)
    def test_apply_needs_commit_lease(self):
        with self.assertRaisesRegex(AdminGateError,"EXPECTED_SHA"):
            apply(TARGET_REF,"not-a-sha")
    def test_apply_needs_token_without_network(self):
        with patch.dict(os.environ,{"GH_TOKEN":"","RIO_R032_ADMIN_APPROVAL":"approved"}):
            with patch("ruleset_admin_r032.api",side_effect=AssertionError("SHOULD_NOT_CALL")):
                with self.assertRaisesRegex(AdminGateError,"GH_TOKEN"):
                    apply(TARGET_REF,SHA)
    def test_apply_needs_approval_without_network(self):
        with patch.dict(os.environ,{"GH_TOKEN":"synthetic","RIO_R032_ADMIN_APPROVAL":"no"}):
            with patch("ruleset_admin_r032.api",side_effect=AssertionError("SHOULD_NOT_CALL")):
                with self.assertRaisesRegex(AdminGateError,"ADMIN_APPROVAL"):
                    apply(TARGET_REF,SHA)
    def test_apply_rejects_concurrent_branch_head_before_write(self):
        with patch.dict(os.environ,{"GH_TOKEN":"synthetic","RIO_R032_ADMIN_APPROVAL":"approved"}):
            with patch("ruleset_admin_r032.api",return_value={"commit":{"sha":"b"*40}}) as api:
                with self.assertRaisesRegex(AdminGateError,"CONCURRENT_BRANCH_CHANGE"):
                    apply(TARGET_REF,SHA)
                self.assertEqual(api.call_count,1)
    def test_apply_mocks_create_and_independent_readback(self):
        calls=[]
        def fake_api(path,method="GET",payload=None):
            calls.append((path,method,payload))
            if "/branches/" in path:return {"commit":{"sha":SHA},"protected":True}
            if path.endswith("/rulesets") and method=="GET":return []
            if path.endswith("/rulesets") and method=="POST":return {"id":444}
            if path.endswith("/rulesets/444"):return readback()
            raise AssertionError("unexpected api call")
        with patch.dict(os.environ,{"GH_TOKEN":"synthetic","RIO_R032_ADMIN_APPROVAL":"approved"}):
            with patch("ruleset_admin_r032.api",side_effect=fake_api):
                receipt=apply(TARGET_REF,SHA)
        self.assertEqual(receipt["operation"],"CREATED")
        self.assertFalse(receipt["deployment_enabled"])
        self.assertEqual(sum(1 for x in calls if x[1]=="POST"),1)
    def test_apply_idempotent_with_readback_no_post(self):
        calls=[]
        def fake_api(path,method="GET",payload=None):
            calls.append(method)
            if "/branches/" in path:return {"commit":{"sha":SHA},"protected":True}
            if path.endswith("/rulesets"):return [{"id":444,"name":NAME}]
            if path.endswith("/rulesets/444"):return readback()
            raise AssertionError("unknown path")
        with patch.dict(os.environ,{"GH_TOKEN":"synthetic","RIO_R032_ADMIN_APPROVAL":"approved"}):
            with patch("ruleset_admin_r032.api",side_effect=fake_api):
                result=apply(TARGET_REF,SHA)
        self.assertEqual(result["operation"],"ALREADY_ACTIVE_VERIFIED")
        self.assertNotIn("POST",calls)
    def test_apply_rejects_postwrite_branch_still_unprotected(self):
        calls=[]
        def fake_api(path,method="GET",payload=None):
            calls.append(method)
            if "/branches/" in path:return {"commit":{"sha":SHA},"protected":False}
            if path.endswith("/rulesets") and method=="GET":return []
            if path.endswith("/rulesets") and method=="POST":return {"id":444}
            if path.endswith("/rulesets/444"):return readback()
            raise AssertionError("unexpected API call")
        with patch.dict(os.environ,{"GH_TOKEN":"synthetic","RIO_R032_ADMIN_APPROVAL":"approved"}):
            with patch("ruleset_admin_r032.api",side_effect=fake_api):
                with self.assertRaisesRegex(AdminGateError,"POST_WRITE_BRANCH_NOT_PROTECTED"):
                    apply(TARGET_REF,SHA)
        self.assertEqual(calls.count("POST"),1)
    def test_apply_rejects_postwrite_missing_protection_readback(self):
        count=[0]
        def fake_api(path,method="GET",payload=None):
            if "/branches/" in path:
                count[0]+=1
                return {"commit":{"sha":SHA},"protected":False} if count[0]==1 else {"commit":{"sha":SHA}}
            if path.endswith("/rulesets") and method=="GET":return []
            if path.endswith("/rulesets") and method=="POST":return {"id":444}
            if path.endswith("/rulesets/444"):return readback()
            raise AssertionError("unexpected API call")
        with patch.dict(os.environ,{"GH_TOKEN":"synthetic","RIO_R032_ADMIN_APPROVAL":"approved"}):
            with patch("ruleset_admin_r032.api",side_effect=fake_api):
                with self.assertRaisesRegex(AdminGateError,"POST_WRITE_BRANCH_NOT_PROTECTED"):
                    apply(TARGET_REF,SHA)
        self.assertEqual(count[0],2)
    def test_cli_plan_no_token(self):
        script=Path(__file__).resolve().parents[1]/"ruleset_admin_r032.py"
        with tempfile.TemporaryDirectory() as d:
            output=Path(d)/"plan.json"
            env={k:v for k,v in os.environ.items() if k!="GH_TOKEN"}
            call=subprocess.run([sys.executable,str(script),"--plan","--output",str(output)],
                capture_output=True,text=True,timeout=10,env=env)
            self.assertEqual(call.returncode,0,call.stderr)
            self.assertIn("PLAN_ONLY_NOT_APPLIED",output.read_text(encoding="utf-8"))
if __name__=="__main__":unittest.main()
