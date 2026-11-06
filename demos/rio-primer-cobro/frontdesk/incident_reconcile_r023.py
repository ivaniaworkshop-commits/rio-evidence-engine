#!/usr/bin/env python3
"""R023: deterministic fail-closed incident reconciliation. READ ONLY; never rollback."""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
from release_fence_r022 import (
    ALIAS, PROJECT, BASELINE_SCHEMA, FENCE_SCHEMA, COMMIT, DEPLOY_ID,
    read_alias, write_json,
)

SCHEMA = "RIO_RELEASE_INCIDENT_R023_V1"
ALLOWED_PROMOTE = {"success", "failure", "skipped", "unknown"}
ABSENT = "ABSENT"
INVALID = "INVALID"
VALID = "VALID"


def read_receipt(path: str | None, schema: str, commit: str) -> tuple[dict | None, str]:
    """Distinguish missing receipt from malformed/untrusted receipt; never assume a missing file is valid."""
    if not path:
        return None, ABSENT
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, ABSENT
    except (OSError, UnicodeError, ValueError):
        return None, INVALID
    if (not isinstance(value, dict) or value.get("schema") != schema
            or value.get("project") != PROJECT or value.get("alias") != ALIAS
            or value.get("commit") != commit):
        return None, INVALID
    identity = ("previous_deployment_id",) if schema == BASELINE_SCHEMA else (
        "previous_deployment_id", "candidate_deployment_id")
    if any(not isinstance(value.get(k), str) or not DEPLOY_ID.fullmatch(value[k]) for k in identity):
        return None, INVALID
    if schema == FENCE_SCHEMA and value.get("automatic_rollback") is not False:
        return None, INVALID
    return value, VALID


def reconcile(
    baseline: dict | None, baseline_state: str,
    fence: dict | None, fence_state: str,
    observed_alias: str | None, promote_outcome: str,
    commit: str,
) -> dict:
    if not COMMIT.fullmatch(commit):
        raise ValueError("BAD_COMMIT_SHA")
    if promote_outcome not in ALLOWED_PROMOTE:
        raise ValueError("BAD_PROMOTION_OUTCOME")
    if baseline_state not in {ABSENT, INVALID, VALID} or fence_state not in {ABSENT, INVALID, VALID}:
        raise ValueError("BAD_EVIDENCE_STATE")
    if baseline_state == VALID and (not isinstance(baseline, dict) or baseline.get("commit") != commit):
        raise ValueError("BAD_BASELINE_PROVENANCE")
    if fence_state == VALID and (not isinstance(fence, dict) or fence.get("commit") != commit):
        raise ValueError("BAD_FENCE_PROVENANCE")
    if observed_alias is not None and (not isinstance(observed_alias, str)
                                       or not DEPLOY_ID.fullmatch(observed_alias)):
        raise ValueError("BAD_OBSERVED_ALIAS")
    old = baseline.get("previous_deployment_id") if baseline_state == VALID else None
    candidate = fence.get("candidate_deployment_id") if fence_state == VALID else None
    previous_from_fence = fence.get("previous_deployment_id") if fence_state == VALID else None

    if INVALID in (baseline_state, fence_state):
        classification = "EVIDENCE_CORRUPT_MANUAL_REVIEW"
    elif old is not None and previous_from_fence is not None and old != previous_from_fence:
        classification = "CONTRADICTORY_RECEIPTS_MANUAL_REVIEW"
    elif observed_alias is None:
        classification = "ALIAS_UNKNOWN_MANUAL_REVIEW"
    elif promote_outcome == "success":
        if candidate is None:
            classification = "PROMOTION_REPORTED_SUCCESS_FENCE_MISSING"
        elif observed_alias == candidate:
            classification = "POST_PROMOTION_CHECK_FAILED_CANDIDATE_STILL_LIVE"
        else:
            classification = "POST_PROMOTION_ALIAS_DIFFERENT_NO_ROLLBACK"
    elif candidate is not None and observed_alias == candidate:
        classification = "CANDIDATE_LIVE_WITHOUT_CONFIRMED_PROMOTION"
    elif old is not None and observed_alias == old:
        classification = "PRE_PROMOTION_ABORT_ALIAS_UNCHANGED"
    elif old is not None:
        classification = "EXTERNAL_ALIAS_CHANGE_OR_RACE_NO_ROLLBACK"
    else:
        classification = "INSUFFICIENT_BASELINE_EVIDENCE"

    return {
        "schema": SCHEMA,
        "result": "INCIDENT_OPEN",
        "classification": classification,
        "commit": commit,
        "alias": ALIAS,
        "project": PROJECT,
        "baseline_receipt": baseline_state,
        "fence_receipt": fence_state,
        "promotion_step_outcome": promote_outcome,
        "alias_observation": "OBSERVED" if observed_alias is not None else "UNKNOWN",
        "previous_deployment_id": old,
        "candidate_deployment_id": candidate,
        "observed_deployment_id": observed_alias,
        "automatic_rollback": False,
        "production_write": False,
        "incident_closed": False,
        "required_next_action": "REBASE_AND_AUTHORIZED_MANUAL_REVIEW",
        "observation_scope": "POST_FAILURE_DIAGNOSTIC_NOT_AUTOMATIC_REMEDIATION",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline")
    parser.add_argument("--fence")
    parser.add_argument("--promote-outcome", choices=sorted(ALLOWED_PROMOTE), default="unknown")
    parser.add_argument("--commit", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        baseline, bs = read_receipt(args.baseline, BASELINE_SCHEMA, args.commit)
        fence, fs = read_receipt(args.fence, FENCE_SCHEMA, args.commit)
        try:
            observed = read_alias()
        except (ValueError, OSError, AttributeError):
            observed = None
        report = reconcile(baseline, bs, fence, fs, observed, args.promote_outcome, args.commit)
        write_json(args.output, report)
        return 0
    except (ValueError, OSError, TypeError, AttributeError) as exc:
        print(json.dumps({"schema": SCHEMA, "result": "FAIL_CLOSED",
                          "error": type(exc).__name__,
                          "automatic_rollback": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
