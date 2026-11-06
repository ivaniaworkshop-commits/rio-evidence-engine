#!/usr/bin/env python3
"""R031 read-only candidate release protection gate, never a deployment authority.
A ruleset can be observed; protected environment, secrets, effective identity
and an actual deployment require independent authorized evidence.
"""
from __future__ import annotations
import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path

TARGET_REF="refs/heads/candidate/primer-cobro-r031-clean-20261106"
EXPECTED_REPO="ivaniaworkshop-commits/rio-evidence-engine"
R030_ANCHOR="9be2a37a1873c11ef0b98266e5cb39285363a2b1"
REQUIRED={"pull_request","deletion","non_fast_forward","required_status_checks"}
SCHEMA="RIO_R031_RELEASE_CANDIDATE_GATE_V1"

class ReleaseGateError(ValueError):
    pass

def reject(reason):
    raise ReleaseGateError(reason)

def matching(rule,branch):
    if not isinstance(rule,dict) or rule.get("target")!="branch" or rule.get("enforcement")!="active":
        return False
    conditions=rule.get("conditions")
    if not isinstance(conditions,dict) or not isinstance(conditions.get("ref_name"),dict):
        return False
    refs=conditions["ref_name"]
    # Require this branch to be listed *exactly*; a wildcard/global rule is not
    # accepted as evidence of a deliberately protected payment release branch.
    includes=refs.get("include")
    excludes=refs.get("exclude")
    return isinstance(includes,list) and branch in includes and (
      isinstance(excludes,list) and all(
        isinstance(pattern,str) and pattern!="~ALL" and
        not fnmatch.fnmatchcase(branch,pattern)
        for pattern in excludes
      )
    )

def assess(rulesets, branch=TARGET_REF, repository=EXPECTED_REPO):
    if branch!=TARGET_REF or repository!=EXPECTED_REPO:
        reject("UNEXPECTED_RELEASE_IDENTITY")
    if not isinstance(rulesets,list):
        reject("RULESETS_MUST_BE_LIST")
    active=[x for x in rulesets if matching(x,branch)]
    if not active:
        return report("BLOCKED_NO_EXACT_ACTIVE_RELEASE_RULESET",0,[],sorted(REQUIRED))
    found=set()
    # Require the complete protection contract to be in one release ruleset
    # rather than mixing controls from unrelated, less-specific rulesets.
    for ruleset in active:
        if ruleset.get("bypass_actors"):
            reject("RELEASE_RULESET_BYPASS")
        rules=ruleset.get("rules")
        if not isinstance(rules,list):
            reject("MALFORMED_RELEASE_RULES")
        per=set()
        for rule in rules:
            if not isinstance(rule,dict):
                reject("MALFORMED_RULE")
            kind=rule.get("type")
            if kind in ("deletion","non_fast_forward"):
                per.add(kind)
            elif kind=="pull_request":
                params=rule.get("parameters")
                if not isinstance(params,dict):
                    reject("REVIEW_PARAMETERS_MISSING")
                count=params.get("required_approving_review_count")
                if type(count) is int and count>=1:
                    per.add(kind)
            elif kind=="required_status_checks":
                params=rule.get("parameters")
                if not isinstance(params,dict):
                    reject("STATUS_CHECK_PARAMETERS_MISSING")
                checks=params.get("required_status_checks")
                if not isinstance(checks,list):
                    reject("STATUS_CHECK_LIST_MISSING")
                if any(isinstance(c,dict) and isinstance(c.get("context"),str) and c["context"].strip() for c in checks):
                    per.add(kind)
        if REQUIRED.issubset(per):
            return report("RULESET_CONTRACT_VERIFIED_ENVIRONMENT_UNVERIFIED",len(active),sorted(per),[])
        found|=per
    return report("BLOCKED_INCOMPLETE_RELEASE_RULESET",len(active),sorted(found),sorted(REQUIRED-found))

def report(result,matched,found,missing):
    return {
        "schema":SCHEMA,"result":result,"candidate_ref":TARGET_REF,
        "repository":EXPECTED_REPO,"source_ancestor_required":R030_ANCHOR,
        "active_exact_matching_rulesets":matched,
        "verified_rule_types":found,"missing_required_rule_types":missing,
        "rule_contract_observed":result=="RULESET_CONTRACT_VERIFIED_ENVIRONMENT_UNVERIFIED",
        "host_identity_authorized":False,"github_environment_verified":False,
        "vercel_token_verified":False,"review_completed":False,
        "deployment_enabled":False,"production_write":False,
        "bank_operations":False,
        "interpretation":"POLICY_READBACK_ONLY_NOT_PRODUCTION_AUTHORIZATION",
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--rulesets",required=True)
    parser.add_argument("--output")
    parser.add_argument("--enforce",action="store_true",
                       help="Return exit 2 unless full ruleset contract is observed")
    args=parser.parse_args()
    try:
        content=Path(args.rulesets).read_text(encoding="utf-8")
        def no_duplicate(pairs):
            out={}
            for key,val in pairs:
                if key in out: reject("DUPLICATE_JSON_KEY")
                out[key]=val
            return out
        value=json.loads(content,object_pairs_hook=no_duplicate)
        outcome=assess(value)
        serial=json.dumps(outcome,sort_keys=True)
        if args.output:
            p=Path(args.output);p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text(json.dumps(outcome,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        print(serial)
        if args.enforce and not outcome["rule_contract_observed"]:
            return 2
        return 0
    except (ReleaseGateError,ValueError,TypeError,OSError,UnicodeError) as e:
        print(json.dumps({"schema":SCHEMA,"result":"FAIL_CLOSED",
              "error":str(e)[:150],"deployment_enabled":False}),file=sys.stderr)
        return 2

if __name__=="__main__":
    sys.exit(main())
