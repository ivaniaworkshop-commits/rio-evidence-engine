#!/usr/bin/env python3
"""R023 deterministic classification matrix; SYNTHETIC evidence, no Vercel access."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from incident_reconcile_r023 import reconcile, ABSENT, INVALID, VALID
from release_fence_r022 import baseline_record, fence_record

SHA = "a"*40
OLD = "dpl_MatrixPrevious0001"
NEW = "dpl_MatrixCandidate002"
FOREIGN = "dpl_MatrixForeign0003"
CANDIDATE_URL = "https://rio-primer-cobro-frontdesk-o6k25ltke-ivaniaworkshop-6855.vercel.app"
BASE = baseline_record(OLD, SHA)
FENCE = fence_record(BASE, OLD, NEW, CANDIDATE_URL, SHA)


def run():
    scenarios = [
        ("pre_fence_unmodified", BASE, VALID, None, ABSENT, OLD, "skipped", "PRE_PROMOTION_ABORT_ALIAS_UNCHANGED"),
        ("pre_fence_concurrent", BASE, VALID, None, ABSENT, FOREIGN, "skipped", "EXTERNAL_ALIAS_CHANGE_OR_RACE_NO_ROLLBACK"),
        ("post_fence_unmodified", BASE, VALID, FENCE, VALID, OLD, "skipped", "PRE_PROMOTION_ABORT_ALIAS_UNCHANGED"),
        ("post_fence_concurrent", BASE, VALID, FENCE, VALID, FOREIGN, "failure", "EXTERNAL_ALIAS_CHANGE_OR_RACE_NO_ROLLBACK"),
        ("promote_unconfirmed_candidate_live", BASE, VALID, FENCE, VALID, NEW, "failure", "CANDIDATE_LIVE_WITHOUT_CONFIRMED_PROMOTION"),
        ("promote_success_bad_readback", BASE, VALID, FENCE, VALID, NEW, "success", "POST_PROMOTION_CHECK_FAILED_CANDIDATE_STILL_LIVE"),
        ("promote_success_foreign_alias", BASE, VALID, FENCE, VALID, FOREIGN, "success", "POST_PROMOTION_ALIAS_DIFFERENT_NO_ROLLBACK"),
        ("no_receipts_no_alias", None, ABSENT, None, ABSENT, None, "unknown", "ALIAS_UNKNOWN_MANUAL_REVIEW"),
        ("no_receipts_alias_seen", None, ABSENT, None, ABSENT, FOREIGN, "unknown", "INSUFFICIENT_BASELINE_EVIDENCE"),
        ("malformed_fence", BASE, VALID, None, INVALID, OLD, "skipped", "EVIDENCE_CORRUPT_MANUAL_REVIEW"),
        ("contradictory_genealogy", BASE, VALID, dict(FENCE, previous_deployment_id=FOREIGN), VALID, OLD, "skipped", "CONTRADICTORY_RECEIPTS_MANUAL_REVIEW"),
        ("promote_success_no_fence", BASE, VALID, None, ABSENT, OLD, "success", "PROMOTION_REPORTED_SUCCESS_FENCE_MISSING"),
        ("alias_api_unavailable_after_promotion", BASE, VALID, FENCE, VALID, None, "success", "ALIAS_UNKNOWN_MANUAL_REVIEW"),
    ]
    results = []
    for name, baseline, bstate, fence, fstate, alias, promote, expected in scenarios:
        rec = reconcile(baseline, bstate, fence, fstate, alias, promote, SHA)
        if (rec["classification"] != expected or rec["result"] != "INCIDENT_OPEN"
                or rec["automatic_rollback"] is not False
                or rec["production_write"] is not False or rec["incident_closed"] is not False):
            raise AssertionError("R023_MATRIX_DRIFT:" + name)
        results.append({"scenario": name, "classification": rec["classification"],
                        "rollback": False, "production_write": False,
                        "evidence": "SYNTHETIC_FIXTURE"})
    return {
        "schema": "RIO_R023_INCIDENT_MATRIX_V1",
        "result": "PASS_SYNTHETIC_ONLY",
        "scenarios_total": len(results),
        "scenarios_pass": len(results),
        "real_vercel_api_called": False,
        "bank_payment": False,
        "android_physical": "NOT_OBSERVED",
        "automatic_rollback": False,
        "scenarios": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        report = run()
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"result": report["result"], "scenarios_pass": report["scenarios_pass"]}))
    except (AssertionError, ValueError, OSError) as e:
        print(json.dumps({"result": "FAIL", "reason": type(e).__name__}), file=sys.stderr)
        sys.exit(2)
