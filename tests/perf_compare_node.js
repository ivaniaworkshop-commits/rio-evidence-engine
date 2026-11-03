"use strict";
/* P6: same-process, same-input P4 vs P5 cost isolation; Node measurements only. */
const { performance } = require("node:perf_hooks");
const legacy = require("./fixtures/p4_compare_baseline.js");
const exact = require("../docs/compare.js");

function bits(value) {
  const bytes = new DataView(new ArrayBuffer(8));
  bytes.setFloat64(0, value, false);
  return bytes.getBigUint64(0, false).toString(16).padStart(16, "0");
}
function percentile(values, fraction) {
  const ordered = [...values].sort((a, b) => a - b);
  return ordered[Math.ceil(fraction * ordered.length) - 1];
}
function one(impl, baselineRaw, candidateRaw) {
  const start = performance.now();
  const a = impl.parseStrict(baselineRaw);
  const b = impl.parseStrict(candidateRaw);
  const afterParse = performance.now();
  const result = impl(a, b);
  const end = performance.now();
  const mem = process.memoryUsage();
  return {
    parse_ms: afterParse - start,
    compute_ms: end - afterParse,
    total_ms: end - start,
    heap_used_sample_bytes: mem.heapUsed,
    rss_sample_bytes: mem.rss,
    result_bits: bits(result.mean_latency_delta_ms),
    count: result.n,
    baseline_correct: result.baseline_correct,
    candidate_correct: result.candidate_correct
  };
}
function run(spec) {
  if (!spec || typeof spec !== "object" ||
      typeof spec.baseline_raw !== "string" ||
      typeof spec.candidate_raw !== "string" ||
      typeof spec.oracle_bits !== "string" ||
      !Number.isInteger(spec.iterations) || spec.iterations < 3 || spec.iterations > 30)
    throw Error("Invalid benchmark specification");
  const measured = { p4: [], p5: [] };
  const warmups = 2;
  for (let i = -warmups; i < spec.iterations; i++) {
    const ordering = (i & 1) ? [["p5", exact], ["p4", legacy]] :
                               [["p4", legacy], ["p5", exact]];
    for (const [name, impl] of ordering) {
      if (typeof global.gc === "function") global.gc();
      const result = one(impl, spec.baseline_raw, spec.candidate_raw);
      if (result.count !== spec.count ||
          result.baseline_correct !== spec.baseline_correct ||
          result.candidate_correct !== spec.candidate_correct)
        throw Error(name + ": paired discrete count mismatch");
      if (name === "p5" && result.result_bits !== spec.oracle_bits)
        throw Error("P5 differs from independent oracle: " + result.result_bits +
                    " != " + spec.oracle_bits);
      if (i >= 0) measured[name].push(result);
    }
  }
  const stats = rows => ({
    parse_ms_median: percentile(rows.map(r => r.parse_ms), 0.5),
    parse_ms_p95: percentile(rows.map(r => r.parse_ms), 0.95),
    compute_ms_median: percentile(rows.map(r => r.compute_ms), 0.5),
    compute_ms_p95: percentile(rows.map(r => r.compute_ms), 0.95),
    total_ms_median: percentile(rows.map(r => r.total_ms), 0.5),
    total_ms_p95: percentile(rows.map(r => r.total_ms), 0.95),
    heap_used_sample_max_bytes: Math.max(...rows.map(r => r.heap_used_sample_bytes)),
    rss_sample_max_bytes: Math.max(...rows.map(r => r.rss_sample_bytes)),
    result_bits: rows[0].result_bits
  });
  const p4 = stats(measured.p4);
  const p5 = stats(measured.p5);
  return {
    runtime: "NODE_NOT_ANDROID",
    iterations: spec.iterations,
    warmups,
    node_version: process.version,
    bytes_per_input: [Buffer.byteLength(spec.baseline_raw), Buffer.byteLength(spec.candidate_raw)],
    p4,
    p5,
    compute_slowdown_ratio: p4.compute_ms_median > 0 ?
      p5.compute_ms_median / p4.compute_ms_median : null,
    max_rss_process_bytes: process.resourceUsage().maxRSS * 1024
  };
}
let text = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", chunk => { text += chunk; });
process.stdin.on("end", () => {
  try {
    const payload = JSON.parse(text);
    console.log(JSON.stringify(run(payload)));
  } catch (error) {
    console.error(JSON.stringify({error: String(error.message)}));
    process.exitCode = 2;
  }
});
