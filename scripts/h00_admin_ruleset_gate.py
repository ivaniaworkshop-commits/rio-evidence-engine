"""Fail-closed GitHub ruleset readback; enforcement belongs to GitHub itself.

GitHub API data and runner context are not independent review or promotion.
No GitHub mutation is implemented by this module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = "ivaniaworkshop-commits/rio-evidence-engine"
RULESET_ID = 26688691
ACTIONS_APP_ID = 15368
# Only executable PR evidence checks belong in GitHub's merge-enforced set.
# The admin policy reader currently lacks complete bypass visibility with its
# unprivileged PR token. Requiring its own check would deadlock reviews.
DIAGNOSTIC_CONTEXT = "H00 admin policy gate (read-only)"
REQUIRED_CONTEXTS = (
    "verify",
    "strict-torch",
    "H00 cross-audit receipts (read-only)",
)
PASS = "ACTIVE_ADMIN_POLICY_VERIFIED"
BLOCK = "BLOCKED_ADMIN_POLICY"
SCHEMA = "RIO_H00_ADMIN_POLICY_READBACK/1.0"
MAX_BYTES = 131072


def unique_pairs(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError("DUPLICATE_JSON_FIELD")
        output[key] = value
    return output


def reject_nonfinite(value):
    raise ValueError("NONFINITE_JSON_VALUE")


def parse_policy(raw: bytes) -> dict:
    if len(raw) > MAX_BYTES:
        raise ValueError("POLICY_TOO_LARGE")
    obj = json.loads(raw, object_pairs_hook=unique_pairs,
                     parse_constant=reject_nonfinite)
    if not isinstance(obj, dict):
        raise ValueError("POLICY_NOT_OBJECT")
    return obj


def verify_ruleset(policy: dict) -> dict:
    """Require an exact, fail-closed administrative policy shape."""
    if not isinstance(policy, dict):
        return {"policy_is_object": False}
    rules = policy.get("rules")
    if not isinstance(rules, list):
        rules = []
    selected = {
        kind: [x for x in rules if isinstance(x, dict) and x.get("type") == kind]
        for kind in ("deletion", "non_fast_forward", "pull_request",
                     "required_status_checks")
    }
    pr = (selected["pull_request"][0].get("parameters", {})
          if len(selected["pull_request"]) == 1 else {})
    if not isinstance(pr, dict):
        pr = {}
    checks_rule = (selected["required_status_checks"][0].get("parameters", {})
                   if len(selected["required_status_checks"]) == 1 else {})
    if not isinstance(checks_rule, dict):
        checks_rule = {}
    definitions = checks_rule.get("required_status_checks")
    valid_definitions = isinstance(definitions, list) and all(
        isinstance(x, dict) and isinstance(x.get("context"), str)
        and type(x.get("integration_id")) is int
        for x in definitions
    )
    names = [x["context"] for x in definitions] if valid_definitions else []
    ids = [x["integration_id"] for x in definitions] if valid_definitions else []
    conditions = policy.get("conditions", {})
    if not isinstance(conditions, dict):
        conditions = {}
    ref = conditions.get("ref_name", {})
    if not isinstance(ref, dict):
        ref = {}
    review_count = pr.get("required_approving_review_count")
    return {
        "repository_identity": (
            policy.get("id") == RULESET_ID
            and policy.get("name") == "RIO_MAIN_PROTECTION_R001"
            and policy.get("source") == REPO
            and policy.get("source_type") == "Repository"
            and policy.get("target") == "branch"
        ),
        "active": policy.get("enforcement") == "active",
        "main_only": (
            ref.get("include") == ["refs/heads/main"]
            and ref.get("exclude") == []
        ),
        "no_bypass": (policy["bypass_actors"] == []
                      if "bypass_actors" in policy else None),
        "no_deletion": len(selected["deletion"]) == 1,
        "no_force_push": len(selected["non_fast_forward"]) == 1,
        "review_rule_unique": len(selected["pull_request"]) == 1,
        "one_independent_approval_required": (
            type(review_count) is int and review_count >= 1
        ),
        "stale_approvals_dismissed": pr.get("dismiss_stale_reviews_on_push") is True,
        "last_push_approval_required": pr.get("require_last_push_approval") is True,
        "required_status_checks_present": len(selected["required_status_checks"]) == 1,
        "required_check_contexts_exact": (
            valid_definitions and len(names) == len(REQUIRED_CONTEXTS)
            and set(names) == set(REQUIRED_CONTEXTS)
        ),
        "diagnostic_excluded_from_required_checks": (
            valid_definitions and DIAGNOSTIC_CONTEXT not in names
        ),
        "required_checks_pinned_to_github_actions": (
            valid_definitions and len(ids) == len(REQUIRED_CONTEXTS)
            and all(i == ACTIONS_APP_ID for i in ids)
        ),
        "require_updated_base": (
            checks_rule.get("strict_required_status_checks_policy") is True
        ),
        "no_create_bypass": checks_rule.get("do_not_enforce_on_create") is not True,
    }


def get_policy(token: str) -> tuple[dict, str]:
    if not token:
        raise ValueError("TOKEN_MISSING")
    url = ("https://api.github.com/repos/" + REPO + "/rulesets/"
           + str(RULESET_ID))
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json",
                 "Authorization": "Bearer " + token,
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "RIO-H00-Policy-Readback/1.0"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        raw = response.read(MAX_BYTES + 1)
    policy = parse_policy(raw)
    return policy, hashlib.sha256(raw).hexdigest()


def audit(env: dict, fetch=get_policy) -> dict:
    result = {
        "schema": SCHEMA, "status": BLOCK,
        "authority": "GITHUB_API_READBACK_NOT_INDEPENDENT_ATTESTATION",
        "repository": env.get("GITHUB_REPOSITORY"),
        "run_id": env.get("GITHUB_RUN_ID"),
        "attempt": env.get("GITHUB_RUN_ATTEMPT"),
        "ruleset_id": RULESET_ID, "policy_sha256": None,
        "bypass_readback_visibility": "NOT_OBSERVED",
        "required_status_checks": list(REQUIRED_CONTEXTS),
        "diagnostic_job_not_merge_required": DIAGNOSTIC_CONTEXT,
        "required_approvals": 1,
        "checks": {}, "failure_codes": [],
        "external_holdout_authenticated": False,
        "independent_approval_observed": False,
        "candidate_promoted": False, "production_ready": False,
    }
    context_ok = (
        env.get("GITHUB_REPOSITORY") == REPO
        and env.get("GITHUB_EVENT_NAME") == "pull_request"
        and env.get("GITHUB_REF", "").startswith("refs/pull/")
        and str(env.get("GITHUB_RUN_ID", "")).isdigit()
        and str(env.get("GITHUB_RUN_ATTEMPT", "")).isdigit()
    )
    result["checks"]["runner_pr_context_valid"] = context_ok
    if not context_ok:
        result["failure_codes"].append("INVALID_RUN_CONTEXT")
        return result
    try:
        policy, digest = fetch(env.get("GITHUB_TOKEN", ""))
        result["policy_sha256"] = digest
        result["bypass_readback_visibility"] = (
            "PRESENT" if "bypass_actors" in policy else "NOT_RETURNED"
        )
        result["checks"].update(verify_ruleset(policy))
    except (urllib.error.URLError, OSError, ValueError, TypeError,
            TimeoutError, OverflowError):
        result["failure_codes"].append("RULESET_READBACK_FAILED")
        return result
    result["failure_codes"].extend(
        k for k, ok in result["checks"].items() if ok is not True
    )
    if not result["failure_codes"]:
        result["status"] = PASS
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    opts = parser.parse_args(argv)
    report = audit(dict(os.environ))
    opts.output.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2)
            + "\n").encode("utf-8")
    opts.output.write_bytes(data)
    print(json.dumps({"schema": SCHEMA, "status": report["status"],
                      "failure_codes": report["failure_codes"],
                      "sha256": hashlib.sha256(data).hexdigest()},
                     sort_keys=True))
    return 0 if report["status"] == PASS else 2


if __name__ == "__main__":
    sys.exit(main())
