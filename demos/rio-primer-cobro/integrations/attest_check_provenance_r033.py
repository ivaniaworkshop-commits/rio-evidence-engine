#!/usr/bin/env python3
"""R033 read-only attestation of real check provenance, not a deployment grant."""
import argparse,json,re,sys
from pathlib import Path
from release_readiness_r031 import assess,TARGET_REF,EXPECTED_REPO
SMOKE_SHA="3c67d0a08b822bc88c7a4e239cf2df0dfc764fb9"
REQUIRED=("verify","strict-torch","candidate-readiness")
APP_ID=15368
SCHEMA="RIO_R033_REAL_CHECK_ATTESTATION_V1"
class AuditError(ValueError):pass
def need(value,reason):
    if not value:raise AuditError(reason)
def dict_only(x,name):
    need(type(x) is dict,name+"_INVALID")
    return x
def audit(branch,pr,checks,rules):
    branch=dict_only(branch,"BRANCH");pr=dict_only(pr,"PR")
    checks=dict_only(checks,"CHECKS")
    need(type(rules) is list,"RULESET_LIST_INVALID")
    need(branch.get("ref")==TARGET_REF,"WRONG_CANDIDATE_REF")
    current=dict_only(branch.get("object"),"BRANCH_OBJECT").get("sha")
    need(type(current) is str and re.fullmatch("[0-9a-f]{40}",current),"BAD_CANDIDATE_HEAD")
    need(pr.get("number")==39 and pr.get("state")=="closed" and pr.get("merged_at") is None,"SMOKE_PR_NOT_CLOSED_UNMERGED")
    base=dict_only(pr.get("base"),"BASE")
    head=dict_only(pr.get("head"),"HEAD")
    need(base.get("ref")==TARGET_REF.removeprefix("refs/heads/"),"SMOKE_TARGET_WRONG")
    need(head.get("sha")==SMOKE_SHA and head.get("ref")=="test/r032-required-checks-20261106","SMOKE_SHA_OR_REF_WRONG")
    need(dict_only(base.get("repo"),"BASE_REPO").get("full_name")==EXPECTED_REPO and
         dict_only(head.get("repo"),"HEAD_REPO").get("full_name")==EXPECTED_REPO,"SMOKE_REPOSITORY_WRONG")
    runs=checks.get("check_runs")
    need(type(runs) is list and len(runs)<=100,"CHECK_RUNS_INVALID")
    matched=[]
    for item in runs:
        need(type(item) is dict,"CHECK_RUN_INVALID")
        if item.get("name") not in REQUIRED:continue
        need(item.get("head_sha")==SMOKE_SHA,"CHECK_SHA_WRONG")
        app=dict_only(item.get("app"),"CHECK_PRODUCER")
        need(type(app.get("id")) is int and app["id"]==APP_ID and app.get("slug")=="github-actions","FOREIGN_CHECK_PRODUCER")
        need(item.get("status")=="completed" and item.get("conclusion")=="success","CHECK_NOT_SUCCESS")
        need(type(item.get("id")) is int and item["id"]>0,"CHECK_ID_INVALID")
        matched.append(item)
    need(len(matched)==3 and {x["name"] for x in matched}==set(REQUIRED),"CHECK_SET_MISSING_OR_DUPLICATE")
    need(len({x["id"] for x in matched})==3,"DUPLICATE_CHECK_ID")
    policy=assess(rules)
    return {
        "schema":SCHEMA,"result":"PASS_REAL_CHECK_IDENTITY_WITH_BLOCKED_RELEASE",
        "candidate_ref":TARGET_REF,"candidate_sha_observed":current,
        "smoke_pr":39,"smoke_sha":SMOKE_SHA,"smoke_closed_unmerged":True,
        "check_contexts":list(REQUIRED),"github_actions_app_id":APP_ID,
        "check_run_ids_verified":3,"ruleset_result":policy["result"],
        "ruleset_contract_observed":policy["rule_contract_observed"],
        "smoke_checks_prove_current_head_release_ready":False,
        "independent_review_observed":False,"environment_protected_observed":False,
        "release_authorized":False,"deployment_enabled":False,"production_write":False,
        "real_bank_payment":False,"historic_privacy_incident_closed":False}
def unique(pairs):
    result={}
    for k,v in pairs:
        need(k not in result,"DUPLICATE_JSON_KEY")
        result[k]=v
    return result
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    for key in ("branch","pr","checks","rules","output"):parser.add_argument("--"+key,required=True)
    a=parser.parse_args()
    try:
        vals=[]
        for key in ("branch","pr","checks","rules"):
            raw=Path(getattr(a,key)).read_text(encoding="utf-8")
            need(len(raw)<2000000,"API_METADATA_TOO_LARGE")
            vals.append(json.loads(raw,object_pairs_hook=unique))
        result=audit(*vals)
        out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
        print("R033_READBACK_PASS_RELEASE_BLOCKED")
    except (AuditError,ValueError,KeyError,TypeError,UnicodeError,OSError) as exc:
        print(json.dumps({"result":"FAIL_CLOSED","reason":str(exc)[:120],"deployment_enabled":False}),file=sys.stderr)
        sys.exit(2)
