#!/usr/bin/env python3
"""R020 deploy authority gate: fail closed unless a GitHub ruleset protects release branch.

Facts: checks only a supplied GitHub ruleset response, NOT effective GitHub policy by itself.
The workflow obtains the JSON from GitHub immediately before publishing.
"""
import argparse
import fnmatch
import json
import sys

RELEASE_REF = "refs/heads/deploy/primer-cobro"
NEEDED = {"pull_request", "deletion", "non_fast_forward"}

def applies(ruleset, ref=RELEASE_REF):
    if ruleset.get("target") != "branch" or ruleset.get("enforcement") != "active":
        return False
    cond = (ruleset.get("conditions") or {}).get("ref_name") or {}
    includes = cond.get("include") or []
    excludes = cond.get("exclude") or []
    def match(pattern):
        if pattern == "~ALL":
            return True
        if pattern == "~DEFAULT_BRANCH":
            return False
        return fnmatch.fnmatchcase(ref, pattern)
    return any(match(p) for p in includes) and not any(match(p) for p in excludes)

def assess(rulesets, ref=RELEASE_REF):
    if not isinstance(rulesets, list):
        raise ValueError("RULESET_DATA_INVALID")
    eligible = [r for r in rulesets if isinstance(r, dict) and applies(r, ref)]
    if not eligible:
        raise ValueError("NO_ACTIVE_RULESET_FOR_RELEASE_BRANCH")
    protections = set()
    for rule in eligible:
        if rule.get("bypass_actors"):
            raise ValueError("RULESET_BYPASS_ACTORS_PRESENT")
        for item in rule.get("rules") or []:
            if not isinstance(item, dict):
                continue
            kind = item.get("type")
            if kind == "pull_request":
                params = item.get("parameters") or {}
                if int(params.get("required_approving_review_count", 0)) >= 1:
                    protections.add(kind)
            elif kind in ("deletion", "non_fast_forward"):
                protections.add(kind)
    missing = sorted(NEEDED - protections)
    if missing:
        raise ValueError("BRANCH_GUARDS_MISSING:" + ",".join(missing))
    return {"schema": "RIO_R020_RELEASE_AUTHORITY_V1",
            "result": "PASS_RULESET_POLICY_CONTRACT",
            "release_ref": ref,
            "active_matching_rulesets": len(eligible),
            "required_rules": sorted(protections),
            "credential_verified": False,
            "runtime_activation": "NOT_DETERMINED"}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--rulesets", required=True, help="combined detailed repo ruleset JSON, read from GitHub in current workflow")
    args = p.parse_args()
    try:
        data = json.load(open(args.rulesets, encoding="utf-8"))
        print(json.dumps(assess(data), sort_keys=True))
    except (ValueError, OSError, TypeError) as e:
        print(json.dumps({"schema": "RIO_R020_RELEASE_AUTHORITY_V1",
                          "result": "FAIL_CLOSED", "reason": str(e)}), file=sys.stderr)
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
