"""P6: bounded, repeatable same-input cost audit for exact binary64 comparison.

No network, model weights or hardware-mobile claims. Benchmarks report distributions;
CI uses generous host-specific catastrophe thresholds, not Android certifications.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import resource
import statistics
import struct
import subprocess
import sys
import time
import tracemalloc
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from rio_evidence.core import compare_results
from rio_evidence.json_io import MAX_BYTES, loads

TARGET_BYTES = 1_020_000
SEED = 20261102
# Conservative GitHub-host catastrophe limits, NOT guarantees for real Android hardware.
MAX_HOST_NODE_COMPUTE_MS = 500.0
MAX_HOST_NODE_TOTAL_MS = 2000.0
MAX_HOST_PYTHON_TOTAL_MS = 2500.0
MAX_HOST_RSS_BYTES = 384 * 1024 * 1024
MAX_HOST_PYTHON_TRACED_PEAK_BYTES = 192 * 1024 * 1024
MAX_RELATIVE_COMPUTE = 20.0
MIN_NEAR_INPUT_BYTES = 950_000


def bits(value):
    return struct.pack(">d", float(value)).hex()


def rows():
    """Deterministic heterogeneous mix; large and tiny values, cancellation, benign data."""
    smallest = math.nextafter(0.0, math.inf)
    patterns = [
        (0.0, smallest),
        (0.0, smallest),
        (0.0, 0.0),
        (0.0, 1e308),
        (1e308, 0.0),
        (0.1, 0.2),
        (1e15, 0.0),
        (0.0, 1e15),
        (0.0, 1.0),
        (1.0, 1.0),
        (0.0, 2.2250738585072014e-308),
        (2.2250738585072014e-308, 0.0),
        (0.0, 9007199254740991),
        (9007199254740991, 0.0),
    ]
    for i in range(30000):
        before, after = patterns[(i + SEED) % len(patterns)]
        label = f"synthetic-{i:06d}"
        yield (
            {"case_id": label, "correct": i % 3 == 0, "latency_ms": before},
            {"case_id": label, "correct": i % 5 == 0, "latency_ms": after}
        )


def fixtures():
    """JSON arrays approaching 1 MiB EACH, without exceeding the per-input contract."""
    base_text, candidate_text = [], []
    lengths = [2, 2]  # [ and ] for each array
    snapshots = {}
    limit = TARGET_BYTES
    for i, (base, candidate) in enumerate(rows(), 1):
        chunk_a = json.dumps(base, allow_nan=False, separators=(",", ":"))
        chunk_b = json.dumps(candidate, allow_nan=False, separators=(",", ":"))
        adds = [len(chunk_a.encode()) + (1 if base_text else 0),
                len(chunk_b.encode()) + (1 if candidate_text else 0)]
        if any(lengths[k] + adds[k] > limit for k in range(2)):
            break
        base_text.append(chunk_a)
        candidate_text.append(chunk_b)
        lengths = [lengths[k] + adds[k] for k in range(2)]
        if i in (32, 2048):
            snapshots[i] = (base_text[:], candidate_text[:])
    snapshots["near-1MiB"] = (base_text, candidate_text)
    result = {}
    for name, (aa, bb) in snapshots.items():
        n = len(aa)
        raw_a, raw_b = "[" + ",".join(aa) + "]", "[" + ",".join(bb) + "]"
        lengths = [len(raw_a.encode()), len(raw_b.encode())]
        if any(v > MAX_BYTES for v in lengths):
            raise AssertionError("fixture exceeds JSON per-input decoder limit")
        if name == "near-1MiB" and min(lengths) < MIN_NEAR_INPUT_BYTES:
            raise AssertionError("fixtures did not approach 1 MiB")
        a, b = loads(raw_a), loads(raw_b)
        paired = sorted(zip(a, b), key=lambda p: p[0]["case_id"])
        expected = float(sum((Fraction.from_float(float(y["latency_ms"])) -
                              Fraction.from_float(float(x["latency_ms"])) for x, y in paired),
                             Fraction(0)) / n)
        result[name] = {
            "name": name,
            "count": n,
            "baseline_raw": raw_a,
            "candidate_raw": raw_b,
            "bytes_per_input": lengths,
            "input_sha256": [hashlib.sha256(raw.encode()).hexdigest()
                             for raw in (raw_a, raw_b)],
            "oracle_bits": bits(expected),
            "baseline_correct": sum(r["correct"] for r in a),
            "candidate_correct": sum(r["correct"] for r in b),
        }
    return result


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[math.ceil(fraction * len(ordered)) - 1]


def measure_python(spec, iterations):
    measurements = []
    # Timings without allocation instrumentation. Memory sampled in a separate run.
    for i in range(iterations + 2):
        t0 = time.perf_counter_ns()
        a, b = loads(spec["baseline_raw"]), loads(spec["candidate_raw"])
        t1 = time.perf_counter_ns()
        answer = compare_results(a, b)
        t2 = time.perf_counter_ns()
        if bits(answer["mean_latency_delta_ms"]) != spec["oracle_bits"]:
            raise AssertionError("Python exact comparator differs from rational oracle")
        if answer["n"] != spec["count"]:
            raise AssertionError("Python case count differs")
        if i >= 2:
            measurements.append({
                "parse_ms": (t1-t0)/1e6,
                "compute_ms": (t2-t1)/1e6,
                "total_ms": (t2-t0)/1e6
            })
    tracemalloc.start()
    a, b = loads(spec["baseline_raw"]), loads(spec["candidate_raw"])
    compare_results(a, b)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        **{key + suffix: percentile([row[key] for row in measurements], q)
           for key in ("parse_ms", "compute_ms", "total_ms")
           for suffix, q in (("_median", 0.5), ("_p95", 0.95))},
        "tracemalloc_peak_bytes": peak,
        "max_rss_process_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        "result_bits": spec["oracle_bits"],
    }


def measure_node(spec, iterations):
    payload = {k: spec[k] for k in (
        "baseline_raw", "candidate_raw", "oracle_bits", "count",
        "baseline_correct", "candidate_correct"
    )}
    payload["iterations"] = iterations
    child = subprocess.run(
        ["node", "--expose-gc", str(ROOT / "tests" / "perf_compare_node.js")],
        input=json.dumps(payload), text=True, capture_output=True, timeout=120, cwd=ROOT,
    )
    if child.returncode:
        raise RuntimeError("Node microbenchmark failed: " + child.stderr[-1600:])
    return json.loads(child.stdout)


def bench(iterations=5, enforce=True):
    if iterations < 3 or iterations > 30:
        raise ValueError("iterations must be in [3,30]")
    report = {
        "schema": "RIO_P6_PERFORMANCE_V1",
        "status": "PENDING",
        "scope": "LOCAL_PYTHON_NODE_PERFORMANCE_NOT_ANDROID",
        "seed": SEED,
        "iterations": iterations,
        "host_thresholds": {
            "node_compute_median_ms": MAX_HOST_NODE_COMPUTE_MS,
            "node_total_median_ms": MAX_HOST_NODE_TOTAL_MS,
            "python_total_median_ms": MAX_HOST_PYTHON_TOTAL_MS,
            "max_process_rss_bytes": MAX_HOST_RSS_BYTES,
            "python_peak_tracemalloc_bytes": MAX_HOST_PYTHON_TRACED_PEAK_BYTES,
            "node_compute_slowdown_limit": MAX_RELATIVE_COMPUTE,
            "relative_floor_ms": 50.0,
        },
        "android_actual_device": "UNKNOWN_NOT_TESTED",
        "cases": {},
        "violations": [],
    }
    try:
        for name, fixture in fixtures().items():
            python = measure_python(fixture, iterations)
            node = measure_node(fixture, iterations)
            report["cases"][str(name)] = {
                "count": fixture["count"],
                "bytes_per_input": fixture["bytes_per_input"],
                "sha256_per_input": fixture["input_sha256"],
                "oracle_bits": fixture["oracle_bits"],
                "python": python,
                "node": node,
            }
            for item, actual, threshold in (
                ("node exact median compute ms", node["p5"]["compute_ms_median"], MAX_HOST_NODE_COMPUTE_MS),
                ("node exact median end-to-end ms", node["p5"]["total_ms_median"], MAX_HOST_NODE_TOTAL_MS),
                ("python exact median end-to-end ms", python["total_ms_median"], MAX_HOST_PYTHON_TOTAL_MS),
                ("node process max RSS bytes", node["max_rss_process_bytes"], MAX_HOST_RSS_BYTES),
                ("python process max RSS bytes", python["max_rss_process_bytes"], MAX_HOST_RSS_BYTES),
                ("python traced peak bytes", python["tracemalloc_peak_bytes"], MAX_HOST_PYTHON_TRACED_PEAK_BYTES),
            ):
                if actual > threshold:
                    report["violations"].append({"case": name, "gate": item, "observed": actual,
                                                 "threshold": threshold})
            if name == "near-1MiB":
                limit = max(50.0, MAX_RELATIVE_COMPUTE * node["p4"]["compute_ms_median"])
                if node["p5"]["compute_ms_median"] > limit:
                    report["violations"].append({
                        "case": name, "gate": "P5 compute slower than P4 on same runner",
                        "observed": node["p5"]["compute_ms_median"], "threshold": limit,
                    })
    except Exception as exc:
        report["violations"].append({"case": "execution", "gate": "harness",
                                     "error": str(exc)})
    report["status"] = "PASS_HOST_RESOURCE_GATE" if not report["violations"] else "FAIL_HOST_RESOURCE_GATE"
    report["gate_enforced"] = bool(enforce)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--no-enforce", action="store_true",
                        help="Report measurements without failing performance budgets")
    args = parser.parse_args()
    summary = bench(iterations=args.iterations, enforce=not args.no_enforce)
    print(json.dumps(summary, sort_keys=True))
    if summary["status"] != "PASS_HOST_RESOURCE_GATE" and not args.no_enforce:
        sys.exit(2)
