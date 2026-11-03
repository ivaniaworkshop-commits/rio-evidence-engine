"""Reproducible, bounded Python-vs-Node IEEE-754 differential gate (synthetic inputs)."""
from __future__ import annotations

import json
import math
import random
import struct
import subprocess
import sys
from collections import Counter
from decimal import Decimal, localcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from rio_evidence.core import compare_results
from rio_evidence.json_io import loads

SEED = 7542026
MAX_ULPS = 1


def _bits(number):
    return struct.pack(">d", float(number)).hex()


def _ordered_bits(number):
    raw = struct.unpack(">Q", struct.pack(">d", float(number)))[0]
    return (~raw & ((1 << 64) - 1)) if raw >> 63 else (raw | (1 << 63))


def _ulp_distance(a, b):
    if a == b == 0.0:
        return 0  # +/-0 is a numerical tie; input bits are independently checked
    return abs(_ordered_bits(a) - _ordered_bits(b))


def make_cases():
    """No external data; deterministic enumerated boundaries plus seeded adjacent floats."""
    cases = []

    def add(name, baseline, candidate, category="boundary", expect=True):
        a = [{"case_id": str(i), "correct": i % 2 == 0, "latency_ms": value}
             for i, value in enumerate(baseline)]
        b = [{"case_id": str(i), "correct": i % 3 == 0, "latency_ms": value}
             for i, value in enumerate(candidate)]
        cases.append({"id": name, "raw": json.dumps([a, b], allow_nan=False),
                      "expect": expect, "category": category})

    def token(name, literal, expect, category, expected_bits=None):
        raw = ('[[{"case_id":"one","correct":false,"latency_ms":0}],'
               '[{"case_id":"one","correct":true,"latency_ms":' + literal + '}]]')
        spec = {"id": name, "raw": raw, "expect": expect, "category": category}
        if expected_bits is not None:
            spec["expected_bits"] = expected_bits
        cases.append(spec)

    smallest_subnormal = math.nextafter(0.0, math.inf)
    anchors = [
        0.0, smallest_subnormal, 2 * smallest_subnormal,
        sys.float_info.min, math.nextafter(sys.float_info.min, 0.0),
        0.1, 0.5, 1.0, 1.5, 2.0, 10.0,
        float((1 << 52) - 1), float(1 << 52),
        float((1 << 53) - 1), float(1 << 53),
        1e15, 1e16, 1e100, 1e308, sys.float_info.max
    ]
    for i, anchor in enumerate(anchors):
        for side, direction in (("below", 0.0), ("above", math.inf)):
            adjacent = math.nextafter(anchor, direction)
            if adjacent >= 0 and math.isfinite(adjacent):
                add(f"boundary-{i}-{side}", [anchor], [adjacent], "nextafter")

    with localcontext() as ctx:
        ctx.prec = 1500
        halfway_one = Decimal(1) + Decimal(2) ** -53
        tiny_one = Decimal("1e-70")
        halfway_zero = Decimal(2) ** -1075
        tiny_zero = Decimal("1e-1150")
        decimals = [
            ("one-below-midpoint", halfway_one - tiny_one, True, "3ff0000000000000"),
            ("one-exact-midpoint", halfway_one, True, "3ff0000000000000"),
            ("one-above-midpoint", halfway_one + tiny_one, True, "3ff0000000000001"),
            ("subnormal-below-midpoint", halfway_zero - tiny_zero, False, None),
            ("subnormal-exact-midpoint", halfway_zero, False, None),
            ("subnormal-above-midpoint", halfway_zero + tiny_zero, True, "0000000000000001"),
        ]
        for name, value, accepted, expected_hex in decimals:
            token(name, format(value, "f"), accepted, "decimal-ties", expected_hex)

    for name, literal, accepted, category in [
        ("max-safe-integer", "9007199254740991", True, "integer-boundary"),
        ("just-outside-safe-integer", "9007199254740992", False, "integer-boundary"),
        ("rounded-unsafe-integer", "9007199254740993", False, "integer-boundary"),
        ("negative-unsafe-integer", "-9007199254740993", False, "integer-boundary"),
        ("float-over-safe-integer", "9007199254740992.0", True, "integer-boundary"),
        ("signed-integer-zero", "-0", False, "signed-zero"),
        ("signed-float-zero", "-0.0", True, "signed-zero"),
        ("positive-integer-zero", "0", True, "signed-zero"),
        ("positive-zero-exponent", "0e-9000", True, "signed-zero"),
        ("minimum-subnormal", "5e-324", True, "subnormal"),
        ("just-underflow", "1e-324", False, "underflow"),
        ("underflow-negative", "-1e-400", False, "underflow"),
        ("underflow-long", "0.000000000000000000001e-9000", False, "underflow"),
        ("minimum-normal", "2.2250738585072014e-308", True, "normal-boundary"),
        ("just-below-normal", "2.225073858507201e-308", True, "normal-boundary"),
        ("max-finite", "1.7976931348623157e308", True, "overflow"),
        ("near-max-finite", "1.7976931348623158e308", True, "overflow"),
        ("overflow", "1.7976931348623159e308", False, "overflow"),
        ("positive-exponent-overflow", "1e309", False, "overflow"),
        ("negative-exponent-overflow", "-1e309", False, "overflow"),
        ("nonstandard-nan", "NaN", False, "nonstandard"),
        ("nonstandard-infinity", "Infinity", False, "nonstandard"),
    ]:
        token(name, literal, accepted, category)

    add("rounding-0.1-0.2", [0.1, 0.2, 0.3], [0.2, 0.3, 0.4], "arithmetic")
    add("cancellation-triad", [0.0, 0.0, 1e15], [1e15, 1.0, 0.0], "arithmetic")
    add("cancellation-1e308", [0.0, 1e308, 0.0], [1e308, 0.0, 1e-15], "arithmetic")
    add("tiny-subnormal-sum", [0.0, 0.0, 0.0], [smallest_subnormal] * 3, "arithmetic")
    add("cancelling-normal-neighbors", [1.0, 1.0, 1.0],
        [math.nextafter(1.0, math.inf), math.nextafter(1.0, 0.0), 1.0], "arithmetic")

    rng = random.Random(SEED)
    for i in range(192):
        exp = rng.randint(-1074, 1023)
        significand = 1.0 + rng.random()
        try:
            anchor = math.ldexp(significand, exp)
        except OverflowError:
            continue
        if not 0 < anchor < math.inf:
            continue
        neighbor = math.nextafter(anchor, math.inf if i % 2 else 0.0)
        if not math.isfinite(neighbor) or neighbor < 0:
            continue
        add(f"seed-{i:03d}", [anchor], [neighbor], "seeded-nextafter")

    return cases


def evaluate_python(spec):
    try:
        baseline, candidate = loads(spec["raw"])
        metrics = compare_results(baseline, candidate)
        return {
            "accepted": True,
            "baseline_bits": [_bits(row["latency_ms"]) for row in baseline],
            "candidate_bits": [_bits(row["latency_ms"]) for row in candidate],
            "metrics": metrics,
        }
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        return {"accepted": False, "error": str(error)}


def run_gate():
    cases = make_cases()
    payload = [{"id": spec["id"], "raw": spec["raw"]} for spec in cases]
    proc = subprocess.run(
        ["node", str(ROOT / "tests" / "ieee754_probe.js")],
        input=json.dumps(payload, allow_nan=False),
        text=True, capture_output=True, timeout=20, cwd=ROOT,
    )
    if proc.returncode:
        raise RuntimeError("Node probe failed: " + proc.stderr[:1000])
    javascript = json.loads(proc.stdout)
    if len(javascript) != len(cases):
        raise AssertionError("JavaScript result count differs")
    failures = []
    by_category = Counter()
    accepted = rejected = max_ulp = 0
    for spec, node in zip(cases, javascript):
        python = evaluate_python(spec)
        by_category[spec["category"]] += 1

        def fail(message):
            failures.append({"id": spec["id"], "category": spec["category"], "reason": message})

        if node["id"] != spec["id"]:
            fail("ordered case identity differs")
            continue
        if python["accepted"] != spec["expect"] or node["accepted"] != spec["expect"]:
            fail("incorrect accept/reject decision (Python=" + str(python.get("error", "ACCEPT")) +
                 ", Node=" + str(node.get("error", "ACCEPT")) + ")")
            continue
        if not spec["expect"]:
            rejected += 1
            continue
        accepted += 1
        if python["baseline_bits"] != node["baseline_bits"] or python["candidate_bits"] != node["candidate_bits"]:
            fail("parsed numeric binary64 bit patterns differ")
        if "expected_bits" in spec and (python["candidate_bits"] != [spec["expected_bits"]]
                                        or node["candidate_bits"] != [spec["expected_bits"]]):
            fail("independent decimal midpoint expectation differs")
        for field in ("n", "baseline_correct", "candidate_correct", "correct_delta"):
            if python["metrics"][field] != node["metrics"][field]:
                fail("integer metric differs: " + field)
        a = python["metrics"]["mean_latency_delta_ms"]
        b = node["metrics"]["mean_latency_delta_ms"]
        if not math.isfinite(a) or not math.isfinite(b):
            fail("nonfinite comparison result")
        else:
            ulps = _ulp_distance(a, b)
            max_ulp = max(max_ulp, ulps)
            if ulps > MAX_ULPS:
                fail("mean latency exceeds " + str(MAX_ULPS) + " ULP: " + repr(a) + " vs " + repr(b) +
                     " (" + str(ulps) + " ULP)")
    return {
        "status": "PASS_PARITY_GATE" if not failures else "FAIL_PARITY_GATE",
        "scope": "SEEDED_SYNTHETIC_PYTHON_NODE_NOT_BROWSER_OR_PRODUCTION",
        "seed": SEED, "max_accepted_ulp_distance": MAX_ULPS,
        "generated_cases": len(cases), "accepted": accepted, "rejected": rejected,
        "max_observed_ulp_distance": max_ulp, "categories": dict(sorted(by_category.items())),
        "failures": failures[:20], "failure_count": len(failures),
    }


if __name__ == "__main__":
    try:
        summary = run_gate()
        print(json.dumps(summary, sort_keys=True))
        if summary["status"] != "PASS_PARITY_GATE":
            raise SystemExit(2)
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as error:
        print(json.dumps({"status": "ERROR", "error": str(error)}), file=sys.stderr)
        raise SystemExit(2) from error
