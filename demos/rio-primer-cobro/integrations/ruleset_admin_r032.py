#!/usr/bin/env python3
"""R032: fail-closed GitHub candidate ruleset PLAN; optional explicit ADMIN apply.

Default --plan is pure, has no network or credentials, and cannot mutate GitHub.
--apply requires an operator-supplied GH_TOKEN, RIO_R032_ADMIN_APPROVAL=approved,
--confirm equal to the exact branch ref, and --expected-head SHA for a readback.
Never prints credentials, headers or API response bodies on failure.
Actual ruleset enforcement is independently checked after any privileged write.
This is NOT permission to deploy, merge, handle bank accounts, or move main.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote
from release_readiness_r031 import assess,TARGET_REF,EXPECTED_REPO,TRUSTED_CHECK_INTEGRATION_ID

SCHEMA="RIO_R032_ADMIN_RULESET_V1"
NAME="RIO_PRIMER_COBRO_CANDIDATE_R032"
CI=("verify","strict-torch","candidate-readiness")

class AdminGateError(RuntimeError):
    pass

def require(ok,why):
    if not ok:raise AdminGateError(why)

def blueprint():
    return {
        "name":NAME,
        "target":"branch",
        "enforcement":"active",
        "bypass_actors":[],
        "conditions":{"ref_name":{"include":[TARGET_REF],"exclude":[]}},
        "rules":[
            {"type":"deletion"},
            {"type":"non_fast_forward"},
            {"type":"pull_request","parameters":{
                "required_approving_review_count":1,
                "dismiss_stale_reviews_on_push":True,
                "required_reviewers":[],
                "require_code_owner_review":False,
                "require_last_push_approval":True,
                "required_review_thread_resolution":False,
                "require_extra_approval_for_unattributed_changes":True,
                "allowed_merge_methods":["merge","squash","rebase"]}},
            {"type":"required_status_checks","parameters":{
                "strict_required_status_checks_policy":True,
                "required_status_checks":[
                    {"context":name,"integration_id":TRUSTED_CHECK_INTEGRATION_ID}
                    for name in CI]}}
        ]}

def validate_observed_ruleset(value):
    require(isinstance(value,dict),"RULESET_READBACK_NOT_OBJECT")
    require(value.get("name")==NAME,"RULESET_NAME_MISMATCH")
    result=assess([value])
    require(result["rule_contract_observed"],"REQUIRED_BRANCH_GUARDS_NOT_OBSERVED")
    wanted=blueprint()
    actual_rules=value.get("rules")
    require(isinstance(actual_rules,list),"RULES_UNREADABLE")
    pull=next((v.get("parameters") for v in actual_rules
       if isinstance(v,dict) and v.get("type")=="pull_request"),None)
    required=next((v.get("parameters") for v in actual_rules
       if isinstance(v,dict) and v.get("type")=="required_status_checks"),None)
    require(isinstance(pull,dict) and isinstance(required,dict),"RULE_PARAMETERS_UNREADABLE")
    require(pull.get("dismiss_stale_reviews_on_push") is True
        and pull.get("require_last_push_approval") is True,"REVIEW_FRESHNESS_UNVERIFIED")
    require(required.get("strict_required_status_checks_policy") is True,
            "STATUS_FRESHNESS_UNVERIFIED")
    want_checks=wanted["rules"][-1]["parameters"]["required_status_checks"]
    checks=required.get("required_status_checks")
    require(isinstance(checks,list),"STATUS_CHECK_LIST_UNREADABLE")
    require(sorted((c.get("context"),c.get("integration_id")) for c in checks
        if isinstance(c,dict))==sorted((c["context"],c["integration_id"]) for c in want_checks),
        "STATUS_PRODUCERS_MISMATCH")
    return {"schema":SCHEMA,"result":"ACTIVE_RULESET_CONTRACT_READBACK",
        "ruleset_id":value.get("id"),"rule_contract_observed":True,
        "verified_check_contexts":list(CI),"integration_id":TRUSTED_CHECK_INTEGRATION_ID,
        "deployment_enabled":False,"production_write":False,
        "environment_reviewed":False,"secrets_verified":False,
        "payment_operations":False}

def api(path,method="GET",payload=None):
    args=["gh","api","-X",method,path]
    if payload is not None:args.extend(["--input","-"])
    raw=None if payload is None else json.dumps(payload,separators=(",",":"))
    proc=subprocess.run(args,input=raw,text=True,capture_output=True,
        timeout=30,check=False)
    require(proc.returncode==0,"GITHUB_API_REJECTED")
    try:
        data=json.loads(proc.stdout)
    except ValueError as exc:
        raise AdminGateError("GITHUB_API_NOT_JSON") from exc
    return data

def plan():
    spec=blueprint()
    require(assess([spec])["rule_contract_observed"],"PLAN_DOES_NOT_MEET_POLICY")
    return {"schema":SCHEMA,"state":"PLAN_ONLY_NOT_APPLIED",
        "repository":EXPECTED_REPO,"candidate_ref":TARGET_REF,
        "ruleset_name":NAME,"write_executed":False,
        "active_ruleset_observed":False,"deployment_enabled":False,
        "required_app_id":TRUSTED_CHECK_INTEGRATION_ID,
        "required_ci_contexts":list(CI),
        "requires_admin_action":True,"requested_ruleset":spec}

def apply(confirm,expected_head):
    require(confirm==TARGET_REF,"EXACT_BRANCH_CONFIRMATION_REQUIRED")
    require(isinstance(expected_head,str) and re.fullmatch(r"[a-f0-9]{40}",expected_head),
            "EXPECTED_SHA_REQUIRED")
    require(os.environ.get("GH_TOKEN","")!="","GH_TOKEN_REQUIRED")
    require(os.environ.get("RIO_R032_ADMIN_APPROVAL")=="approved","ADMIN_APPROVAL_REQUIRED")
    base="/repos/"+EXPECTED_REPO
    branch=api(base+"/branches/"+quote(TARGET_REF.removeprefix("refs/heads/"),safe=""))
    require(isinstance(branch,dict),"BRANCH_READBACK_INVALID")
    sha=((branch.get("commit") or {}).get("sha"))
    require(sha==expected_head,"CONCURRENT_BRANCH_CHANGE")
    found=api(base+"/rulesets")
    require(isinstance(found,list),"RULESET_LIST_UNAVAILABLE")
    existing=[r for r in found if isinstance(r,dict) and r.get("name")==NAME]
    require(len(existing)<=1,"DUPLICATE_RULESET_NAMES")
    action="CREATED"
    if existing:
        ident=existing[0].get("id")
        require(type(ident) is int and ident>0,"RULESET_ID_INVALID")
        detail=api(base+"/rulesets/"+str(ident))
        result=validate_observed_ruleset(detail)
        action="ALREADY_ACTIVE_VERIFIED"
    else:
        created=api(base+"/rulesets",method="POST",payload=blueprint())
        require(isinstance(created,dict) and type(created.get("id")) is int,
                "RULESET_CREATION_NO_ID")
        detail=api(base+"/rulesets/"+str(created["id"]))
        result=validate_observed_ruleset(detail)
    second=api(base+"/branches/"+quote(TARGET_REF.removeprefix("refs/heads/"),safe=""))
    require(((second.get("commit") or {}).get("sha"))==expected_head,
            "POST_WRITE_CONCURRENT_BRANCH_CHANGE")
    # A valid ruleset JSON is insufficient: GitHub must report the actual ref protected.
    require(second.get("protected") is True,"POST_WRITE_BRANCH_NOT_PROTECTED")
    return {**result,"operation":action,
       "expected_head":expected_head,"write_authorized_by_operator":True,
       "release_authorization":"STILL_BLOCKED_PENDING_ENVIRONMENT_AND_REVIEW"}

def main():
    p=argparse.ArgumentParser()
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan",action="store_true")
    mode.add_argument("--apply",action="store_true")
    p.add_argument("--confirm",default="")
    p.add_argument("--expected-head",default="")
    p.add_argument("--output")
    a=p.parse_args()
    try:
        value=plan() if a.plan else apply(a.confirm,a.expected_head)
        if a.output:
            dest=Path(a.output);dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_text(json.dumps(value,sort_keys=True,indent=2)+"\n",encoding="utf-8")
        print(json.dumps({k:v for k,v in value.items() if k!="requested_ruleset"},sort_keys=True))
        return 0
    except (AdminGateError,ValueError,OSError,TypeError,subprocess.TimeoutExpired):
        print(json.dumps({"schema":SCHEMA,"result":"FAIL_CLOSED",
            "production_write":False,"secrets_disclosed":False,
            "ruleset_state":"UNKNOWN_UNLESS_INDEPENDENT_READBACK"}),file=sys.stderr)
        return 2
if __name__=="__main__":sys.exit(main())
