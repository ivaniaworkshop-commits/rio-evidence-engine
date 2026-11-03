"use strict";
/* Independent Node entrypoint: invokes the public browser comparator without DOM. */
const compare = require("../docs/compare.js");

function bits(value) {
  const buffer = new ArrayBuffer(8);
  const view = new DataView(buffer);
  view.setFloat64(0, value, false);
  return view.getBigUint64(0, false).toString(16).padStart(16, "0");
}

function evaluate(spec) {
  try {
    const [baseline, candidate] = compare.parseStrict(spec.raw);
    const metrics = compare(baseline, candidate);
    return {
      id: spec.id, accepted: true,
      baseline_bits: baseline.map(row => bits(row.latency_ms)),
      candidate_bits: candidate.map(row => bits(row.latency_ms)),
      metrics,
    };
  } catch (error) {
    return {id: spec.id, accepted: false, error: String(error.message)};
  }
}

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", chunk => { input += chunk; });
process.stdin.on("end", () => {
  try {
    const cases = JSON.parse(input);
    if (!Array.isArray(cases)) throw Error("Expected array");
    process.stdout.write(JSON.stringify(cases.map(evaluate)) + "\n");
  } catch (error) {
    process.stderr.write(JSON.stringify({error: String(error.message)}) + "\n");
    process.exitCode = 2;
  }
});
