"""P5: seeded metamorphic and independent rational oracle for paired latency means.

Reference arithmetic: fractions.Fraction applied to exact input binary64 values.
This deliberately does not call either implementation's integer-unit accumulator.
"""
from __future__ import annotations

import json
import math
import random
import struct
import subprocess
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from rio_evidence.core import compare_results
from rio_evidence.json_io import loads

SEED = 20261102
MAX_FAILURES = 25


def binary64_hex(value):
    return struct.pack(">d", value).hex()


def exact_mean(pairs):
    """Mathematical mean of exact binary64 inputs, rounded once to binary64."""
    if not pairs:
        raise ValueError("empty")
    terms = (Fraction.from_float(float(b)) - Fraction.from_float(float(a))
             for a, b in pairs)
    return float(sum(terms, Fraction(0)) / len(pairs))


def source_pairs():
    """Authored adversarial families plus stable pseudo-random exponent mixtures."""
    tiny = math.nextafter(0.0, math.inf)
    big = sys.float_info.max
    unit = math.nextafter(1.0, math.inf)
    two = math.nextafter(unit, math.inf)
    families = {
        "double-underflow": [(0.0, tiny), (0.0, tiny), (0.0, 0.0)],
        "underflow-cancellation": [(0.0, 1e308), (1e308, 0.0), (0.0, tiny),
                                  (0.0, tiny), (0.0, tiny)],
        "large-cancellation": [(0.0, 1e15), (0.0, 1.0), (1e15, 0.0)],
        "decimal-rounding": [(0.0, 0.1), (0.0, 0.2), (0.0, 0.3)],
        "halfway-ties-even-down": [(0.0, 1.0), (0.0, unit)],
        "halfway-ties-even-up": [(0.0, unit), (0.0, two)],
        "max-finite": [(0.0, big), (0.0, big), (0.0, 0.0)],
        "negative-max": [(big, 0.0), (big, 0.0), (0.0, 0.0)],
        "mixed-min-normal": [(0.0, sys.float_info.min),
                              (sys.float_info.min, 0.0), (0.0, tiny)],
        "zero-cancellation": [(0.0, 1e308), (1e308, 0.0), (0.0, 0.0)],
        "subnormal-halfway": [(0.0, tiny), (0.0, 0.0)],
        "three-subnormals": [(0.0, tiny)] * 3,
        "near-2p53": [(0.0, float(2**53 - 1)), (0.0, 1.0)],
        "small-decimals": [(0.1, 0.2), (0.2, 0.3), (0.3, 0.4)],
    }
    rng = random.Random(SEED)
    for i in range(48):
        pairs = []
        for j in range(rng.randint(3, 9)):
            exp = rng.randint(-1074, 1022)
            a = math.ldexp(rng.random(), exp)
            b = math.ldexp(rng.random(), exp)
            pairs.append((a, b))
        if i % 4 == 0:
            pairs.extend([(0.0, 1e15), (1e15, 0.0), (0.0, tiny)])
        if i % 5 == 0:
            pairs.extend([(0.0, 1e308), (1e308, 0.0)])
        families[f"seed-{i:02d}"] = pairs
    return families


def variations(name, pairs):
    """Reorder blocks, interleave groups and duplicate observations without changing the mean."""
    n = len(pairs)
    indices = list(range(n))
    rng = random.Random(SEED + sum(ord(c) for c in name))
    shuffled = indices[:]
    rng.shuffle(shuffled)

    variants = {
        "original": indices,
        "reverse": indices[::-1],
        "by-difference-up": sorted(indices, key=lambda k: (abs(pairs[k][1] - pairs[k][0]), k)),
        "by-difference-down": sorted(indices, key=lambda k: (-abs(pairs[k][1] - pairs[k][0]), k)),
        "shuffle": shuffled,
        "group-block-reverse": [k for start in reversed(range(0, n, 3))
                                for k in range(start, min(start + 3, n))],
        "group-interleave": [k for rem in range(3) for k in indices if k % 3 == rem],
        "group-repeat-2": indices * 2,
        "group-repeat-3": [k for k in indices for _ in range(3)],
    }
    for variant, order in variants.items():
        a, b = [], []
        for ordinal, idx in enumerate(order):
            left, right = pairs[idx]
            key = f"{idx}:{ordinal}"  # no accidental duplicate case IDs after replication
            a.append({"case_id": key, "correct": idx % 2 == 0, "latency_ms": left})
            b.append({"case_id": key, "correct": idx % 3 == 0, "latency_ms": right})
        # Candidate list order is intentionally independent of baseline order.
        if variant in ("group-interleave", "shuffle"):
            b.reverse()
        raw = json.dumps([a, b], allow_nan=False, separators=(",", ":"))
        yield {
            "id": name + "/" + variant,
            "family": name, "variant": variant,
            "raw": raw, "pairs": [pairs[idx] for idx in order],
            "n": len(order),
            "expected_counts": (
                sum(row["correct"] for row in a),
                sum(row["correct"] for row in b)
            ),
        }


def _python_evaluate(spec):
    try:
        a, b = loads(spec["raw"])
        return {"accepted": True, "metrics": compare_results(a, b)}
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        return {"accepted": False, "error": str(error)}


def run_gate():
    families = source_pairs()
    cases = [s for name, pairs in families.items() for s in variations(name, pairs)]
    payload = [{"id": spec["id"], "raw": spec["raw"]} for spec in cases]
    proc = subprocess.run(
        ["node", str(ROOT / "tests" / "ieee754_probe.js")],
        input=json.dumps(payload, allow_nan=False), cwd=ROOT, text=True,
        capture_output=True, timeout=30,
    )
    if proc.returncode:
        raise RuntimeError("Node probe failed: " + proc.stderr[:2000])
    browser = json.loads(proc.stdout)
    if len(browser) != len(cases):
        raise AssertionError("not all probes returned")
    failures, accepted = [], 0
    category_counts = Counter()
    observed_max = 0

    def failure(spec, description):
        failures.append({"id": spec["id"], "reason": description})

    for spec, js in zip(cases, browser):
        category_counts[spec["variant"]] += 1
        python = _python_evaluate(spec)
        if js.get("id") != spec["id"]:
            failure(spec, "case identity differs")
            continue
        if not js.get("accepted") or not python.get("accepted"):
            failure(spec, "unexpected rejection: Python=" + str(python.get("error")) +
                    "; JavaScript=" + str(js.get("error")))
            continue
        accepted += 1
        reference = exact_mean(spec["pairs"])
        ref_bits = binary64_hex(reference)
        for label, actual in (("Python", python["metrics"]["mean_latency_delta_ms"]),
                              ("JavaScript", js["metrics"]["mean_latency_delta_ms"])):
            if binary64_hex(actual) != ref_bits:
                failure(spec, label + " differs from independently rounded rational oracle: " +
                        repr(actual) + " vs " + repr(reference))
        for label, metrics in (("Python", python["metrics"]), ("JavaScript", js["metrics"])):
            if metrics["n"] != spec["n"]:
                failure(spec, label + " denominator changed")
            if (metrics["baseline_correct"], metrics["candidate_correct"]) != spec["expected_counts"]:
                failure(spec, label + " numerator changed")
        if "error" in js or "error" in python:
            failure(spec, "unexpected error payload")

    for name, pairs in families.items():
        base_bits = binary64_hex(exact_mean(pairs))
        for spec in variations(name, pairs):
            if binary64_hex(exact_mean(spec["pairs"])) != base_bits:
                failure(spec, "metamorphic mutation changed exact reference mean")

    # Guard the test itself: the former per-term division method fails this fixture.
    old_bug = [(0.0, math.nextafter(0.0, math.inf)),
               (0.0, math.nextafter(0.0, math.inf)), (0.0, 0.0)]
    oracle_exposes_old_bug = (
        exact_mean(old_bug) !=
        math.fsum((b - a) / len(old_bug) for a, b in old_bug)
    )
    if not oracle_exposes_old_bug:
        failures.append({"id": "oracle-sensitivity", "reason": "old shared error not detectable"})

    return {
        "status": "PASS_EXACT_METAMORPHIC_GATE" if not failures else "FAIL_EXACT_METAMORPHIC_GATE",
        "scope": "LOCAL_SYNTHETIC_PYTHON_NODE_EXACT_FRACTION_REFERENCE",
        "seed": SEED, "families": len(families),
        "cases": len(cases), "accepted": accepted,
        "permutation_and_grouping_variants": sorted(category_counts.items()),
        "reference": "fractions.Fraction.from_float exact rational, round once",
        "contract": "exact binary64 output bits (0 ULP), exact discrete counts, no unexpected rejection",
        "old_shared_bug_detected": oracle_exposes_old_bug,
        "max_observed_error_ulp": observed_max,
        "failure_count": len(failures), "failures": failures[:MAX_FAILURES],
    }


if __name__ == "__main__":
    try:
        result = run_gate()
        print(json.dumps(result, sort_keys=True))
        if result["status"] != "PASS_EXACT_METAMORPHIC_GATE":
            raise SystemExit(2)
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as error:
        print(json.dumps({"status": "ERROR", "error": str(error)}), file=sys.stderr)
        raise SystemExit(2) from error
