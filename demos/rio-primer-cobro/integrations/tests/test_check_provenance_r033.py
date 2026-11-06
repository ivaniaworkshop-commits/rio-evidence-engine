import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from attest_check_provenance_r033 import audit,AuditError,SMOKE_SHA,REQUIRED,APP_ID
from release_readiness_r031 import TARGET_REF,EXPECTED_REPO
def fixture():
    repo={"full_name":EXPECTED_REPO}
    return [
        {"ref":TARGET_REF,"object":{"sha":"a"*40}},
        {"number":39,"state":"closed","merged_at":None,
         "head":{"sha":SMOKE_SHA,"ref":"test/r032-required-checks-20261106","repo":repo},
         "base":{"ref":TARGET_REF.removeprefix("refs/heads/"),"repo":repo}},
        {"check_runs":[{"id":i+10,"name":n,"head_sha":SMOKE_SHA,
          "app":{"id":APP_ID,"slug":"github-actions"},"status":"completed",
          "conclusion":"success"} for i,n in enumerate(REQUIRED)]},
        []
    ]
class CheckReadback(unittest.TestCase):
    def test_complete_readback_still_blocks_release(self):
        out=audit(*fixture());self.assertFalse(out["release_authorized"])
        self.assertEqual(out["check_run_ids_verified"],3)
    def test_wrong_branch(self):
        a=fixture();a[0]["ref"]="refs/heads/main"
        with self.assertRaises(AuditError):audit(*a)
    def test_bad_candidate_commit(self):
        a=fixture();a[0]["object"]["sha"]="wrong"
        with self.assertRaises(AuditError):audit(*a)
    def test_smoke_pr_must_be_closed(self):
        a=fixture();a[1]["state"]="open"
        with self.assertRaises(AuditError):audit(*a)
    def test_smoke_pr_must_not_be_merged(self):
        a=fixture();a[1]["merged_at"]="present"
        with self.assertRaises(AuditError):audit(*a)
    def test_smoke_sha_must_match(self):
        a=fixture();a[1]["head"]["sha"]="b"*40
        with self.assertRaises(AuditError):audit(*a)
    def test_foreign_repo_rejected(self):
        a=fixture();a[1]["head"]["repo"]={"full_name":"untrusted/fork"}
        with self.assertRaises(AuditError):audit(*a)
    def test_missing_check_rejected(self):
        a=fixture();a[2]["check_runs"].pop()
        with self.assertRaises(AuditError):audit(*a)
    def test_duplicate_check_rejected(self):
        a=fixture();a[2]["check_runs"].append(copy.deepcopy(a[2]["check_runs"][0]))
        with self.assertRaises(AuditError):audit(*a)
    def test_failing_check_rejected(self):
        a=fixture();a[2]["check_runs"][0]["conclusion"]="failure"
        with self.assertRaises(AuditError):audit(*a)
    def test_foreign_check_producer_rejected(self):
        a=fixture();a[2]["check_runs"][0]["app"]["id"]=999
        with self.assertRaises(AuditError):audit(*a)
    def test_wrong_check_commit_rejected(self):
        a=fixture();a[2]["check_runs"][0]["head_sha"]="b"*40
        with self.assertRaises(AuditError):audit(*a)
    def test_real_ruleset_claim_does_not_authorize(self):
        from ruleset_admin_r032 import blueprint
        a=fixture();a[3]=[blueprint()]
        out=audit(*a)
        self.assertTrue(out["ruleset_contract_observed"])
        self.assertFalse(out["deployment_enabled"])
    def test_main_only_rule_not_candidate_protection(self):
        a=fixture();a[3]=[{"target":"branch","enforcement":"active",
            "conditions":{"ref_name":{"include":["refs/heads/main"],"exclude":[]}},
            "rules":[{"type":"deletion"}]}]
        self.assertFalse(audit(*a)["ruleset_contract_observed"])
if __name__=="__main__":unittest.main()
