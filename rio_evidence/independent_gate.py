"""External holdout screening. Output is never an independent certificate.

Compares the *same* sealed cases against source-anchored deterministic baseline.
Exact text overlaps with published project train/dev/evaluation are rejected.
This cannot authenticate an organizer, an evaluator or the candidate's execution.
"""
from datetime import datetime
import json
import math
from pathlib import Path
import re
import statistics

from .graph_copy import extract_graph
from .semantic_gate import canonical, grade

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "RIO_EXTERNAL_HOLDOUT_R001"
PROVENANCE = "EXTERNAL_PROVENANCE_NOT_AUTHENTICATED_BY_THIS_PROGRAM"
MAX_CASES = 500


def _time(raw):
    if not isinstance(raw, str):
        raise ValueError("TIME_MUST_BE_ISO_STRING")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return value


def _known_text(root):
    seen = set()
    for name in ("training/extraction_train.jsonl",
                 "training/extraction_dev.jsonl",
                 "evaluation/semantic_fixture.jsonl"):
        path = Path(root) / name
        if not path.is_file():
            raise ValueError("TRAIN_DEV_REFERENCE_MISSING")
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                obj = json.loads(line)
                if isinstance(obj.get("text"), str):
                    seen.add(" ".join(obj["text"].casefold().split()))
    return seen


def _one_sided_exact_p(wins, losses):
    # Conditional exact paired discordance test, not independent sampling proof.
    n = wins + losses
    return sum(math.comb(n, k) for k in range(wins, n + 1)) / 2**n if n else 1.0


def evaluate(bundle, root=ROOT):
    if bundle is None:
        return {"schema": SCHEMA, "status": "BLOCKED_NO_EXTERNAL_HOLDOUT",
                "independence": PROVENANCE, "candidate_promoted": False}
    if not isinstance(bundle, dict) or set(bundle) != {"schema", "provenance", "cases"} or bundle.get("schema") != SCHEMA:
        raise ValueError("INVALID_EVALUATION_ENVELOPE")
    p = bundle["provenance"]
    expected_provenance = {"candidate_commit", "baseline_commit", "frozen_at_utc",
                           "received_at_utc", "source_type", "source_ref"}
    if not isinstance(p, dict) or set(p) != expected_provenance:
        raise ValueError("INVALID_PROVENANCE_FIELDS")
    if p["source_type"] not in ("EXTERNAL_EVALUATOR", "OFFICIAL_ORGANIZER"):
        raise ValueError("EXTERNAL_SOURCE_REQUIRED")
    for field in ("candidate_commit", "baseline_commit"):
        if not isinstance(p[field], str) or not re.fullmatch(r"[0-9a-f]{40}", p[field]):
            raise ValueError("INVALID_FROZEN_COMMIT")
    if not isinstance(p["source_ref"], str) or not p["source_ref"].strip() or len(p["source_ref"]) > 512:
        raise ValueError("SOURCE_REFERENCE_REQUIRED")
    if _time(p["frozen_at_utc"]) >= _time(p["received_at_utc"]):
        raise ValueError("CANDIDATE_NOT_PRE_FROZEN")
    cases = bundle["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise ValueError("INVALID_CASE_COUNT")
    known = _known_text(root)
    ids = set()
    positive = negative = win = loss = exact_a = exact_b = neg_a = neg_b = 0
    latency_a, latency_b, clusters = [], [], set()
    wrong_negatives_a = wrong_negatives_b = 0
    fields = {"case_id", "cluster", "text", "expected", "candidate_output",
              "baseline_latency_ms", "candidate_latency_ms"}
    for r in cases:
        if not isinstance(r, dict) or set(r) != fields:
            raise ValueError("INVALID_CASE_FIELDS")
        key = r["case_id"]
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", key) or key in ids:
            raise ValueError("MISSING_OR_DUPLICATED_CASE_ID")
        ids.add(key)
        cluster = r["cluster"]
        if not isinstance(cluster, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", cluster):
            raise ValueError("INVALID_CLUSTER")
        clusters.add(cluster)
        text = r["text"]
        if not isinstance(text, str) or not text.strip() or len(text.encode("utf-8")) > 4096:
            raise ValueError("INVALID_INPUT_TEXT")
        if " ".join(text.casefold().split()) in known:
            raise ValueError("EXACT_TRAIN_DEV_EVAL_TEXT_OVERLAP")
        reference = r["expected"]
        if reference is not None:
            if not isinstance(reference, dict):
                raise ValueError("INVALID_REFERENCE_GRAPH")
            canonical(reference)
            positive += 1
        else:
            negative += 1
        for name, record in (("baseline_latency_ms", latency_a), ("candidate_latency_ms", latency_b)):
            number = r[name]
            if type(number) not in (int, float) or not math.isfinite(number) or number < 0:
                raise ValueError("INVALID_MEASURED_LATENCY")
            record.append(number)
        # Baseline output is recomputed, not accepted from the submitter.
        baseline = extract_graph(text)["graph"]
        left = grade(baseline, reference)
        right = grade(r["candidate_output"], reference)
        if reference is None:
            neg_a += bool(left["pass"])
            neg_b += bool(right["pass"])
            wrong_negatives_a += not left["pass"]
            wrong_negatives_b += not right["pass"]
        else:
            exact_a += bool(left["pass"])
            exact_b += bool(right["pass"])
        win += bool(right["pass"] and not left["pass"])
        loss += bool(left["pass"] and not right["pass"])
    median_a = statistics.median(latency_a)
    median_b = statistics.median(latency_b)
    if positive < 30 or negative < 10 or len(clusters) < 5:
        outcome = "INSUFFICIENT_DIVERSITY_OR_DENOMINATOR"
    elif exact_b - exact_a < 5 or win <= loss or _one_sided_exact_p(win, loss) > 0.05:
        outcome = "NO_SIGNIFICANT_PAIRED_EXACT_GAIN"
    elif neg_b < neg_a:
        outcome = "ABSTENTION_REGRESSION"
    elif median_b > max(3 * median_a, median_a + 5):
        outcome = "LATENCY_OVER_BUDGET"
    else:
        outcome = "PROVISIONAL_TECHNICAL_SCREEN_PASS"
    return {
        "schema": SCHEMA, "status": outcome, "independence": PROVENANCE,
        "case_count": len(cases), "supported": positive, "unsupported": negative,
        "cluster_count": len(clusters), "baseline_supported_exact": exact_a,
        "candidate_supported_exact": exact_b, "baseline_correct_abstentions": neg_a,
        "candidate_correct_abstentions": neg_b, "discordant_candidate_wins": win,
        "discordant_candidate_losses": loss, "one_sided_p_descriptive": _one_sided_exact_p(win, loss),
        "baseline_median_ms_submitted": median_a, "candidate_median_ms_submitted": median_b,
        "financial_cost": "UNKNOWN", "candidate_promoted": False,
        "limits": ["Same cases and deterministic reference grades; submitted candidate outputs and timings are not authenticated.",
                   "Exact text nonoverlap cannot rule out paraphrase or development contamination.",
                   "Source type and timestamps are self-reported, not independently authenticated.",
                   "Paired p-value assumes a sampling model; clustered/selected examples may violate it.",
                   "Further authorized external attestation and cost measurement are mandatory before promotion."]
    }


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", nargs="?", help="External JSON bundle, never publish private holdout")
    args = parser.parse_args(argv)
    try:
        bundle = None if args.bundle is None else json.loads(Path(args.bundle).read_text(encoding="utf-8"))
        result = evaluate(bundle)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc), "candidate_promoted": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
