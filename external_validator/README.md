# Standalone external validation instrument

This stdlib-only script can be copied to an external evaluator's machine. The parent grader imports none of Río's scoring/parsing modules. It checks two clean Git checkouts at exact commit IDs, then starts a separate isolated-mode Python interpreter for each registered system. The workers receive only case IDs and input text, not expected labels. The parent validates labels, grades exact graph equality, counts errors separately from abstentions, measures worker call latency, and computes descriptive paired and cluster sign screens.

**READY INSTRUMENT != INDEPENDENT VALIDATION.** Execution by the project author is not an external evaluation. No code in this tool authenticates the evaluator, origin of texts, collection timestamps or adjudicators. All reports keep independence_verified=false and candidate_promoted=false, even if the technical screen passes. Separate processes are not a security sandbox; the operator must review the trusted source before executing it. A separate machine, independent data custody, independent label adjudication and verifiable identity/evidence are still external obligations.

## Use

Use Python 3.10+ and Git. Keep the instrument, datasets, output, virtual environments and Python caches outside the two checkouts. Checkouts must contain no tracked changes, untracked or ignored files. Git commits and hashes identify bytes, not truth or authorship. No network fetch, checkout, training, mutation or publication is performed by the validator.

```sh
python /reviewed/validate.py \
  --bundle /private/holdout.json \
  --known-texts /private/disclosed_project_texts.json \
  --baseline-checkout /frozen/h09 \
  --baseline-commit 3d047f369059877ce0dec30bd297e6cf1a17ed99 \
  --candidate-checkout /frozen/candidate \
  --candidate-commit cd0e14a043ac19797a089c85d62c9a79f760e445 \
  --candidate spanish \
  --output /private/new_report.json
```

The command above selects the opt-in Spanish parser at H17, not a neural checkpoint. `--candidate structured_v1` selects the frozen structured parser; its historical candidate source commit is 178783ac678b898d369caceaefb1b22dbd76a6ce. Never modify a frozen candidate after collecting its holdout. The tool does not evaluate the neural checkpoints, switch defaults or merge weights.

`--known-texts` is a nonempty JSON array of disclosed training/development/evaluation input strings. The evaluator must obtain a complete disclosure independently. Exact normalized text screening does not establish absence of paraphrase or structural leakage. The script does not certify that the disclosure is complete.

Input envelope (illustrative schema, not an external test dataset):

```json
{
  "schema": "RIO_EXTERNAL_VALIDATOR_INPUT_V1",
  "provenance": {
    "source_ref": "Externally verifiable reference, not a self-certification",
    "frozen_at_utc": "2026-01-01T00:00:00Z",
    "collected_at_utc": "2026-01-02T00:00:00Z"
  },
  "cases": [
    {
      "case_id": "case-001",
      "cluster": "source-cluster-001",
      "text": "Private source text supplied by the external evaluator",
      "expected": null
    }
  ]
}
```

`expected=null` means the independently adjudicated correct result is abstention. Otherwise it must contain exactly `tasks` (id/depends_on) and `durations`, an acyclic graph of 1..8 task IDs in A..H, integer minutes 0..1,000,000. No candidate outputs or submitted latencies are accepted. All case IDs and normalized texts must be unique. The bundle is limited to 500 cases / 4 MiB; disclosed text JSON to 16 MiB. Limits apply to accepted data; trusted worker output is checked after subprocess capture, not by an OS resource sandbox.

## Interpretation and custody

Technical screen: >=30 supported, >=10 unsupported, >=5 declared clusters; >=5 extra exact graphs; one-sided descriptive paired p<=0.05; >=5 winning clusters with cluster sign p<=0.05; no abstention regression or baseline/candidate interface/runtime/invalid-graph errors; candidate median call latency <=max(3*baseline, baseline+5ms). Cluster independence and random sampling are not verified. The screen is neither a generalization certificate nor a promotion decision. Single-pass worker timings exclude process startup and are hardware/load sensitive.

Reports omit source texts, labels, raw predictions and case identifiers. They include aggregate metrics, commit IDs and hashes of input bytes. Output must be outside both frozen checkouts and must not exist; permissions are 0600. Treat aggregates and hashes as potentially sensitive and keep reports private until reviewed. Existing reports are never overwritten. No report is uploaded automatically.

No bundle: BLOCKED_NO_EXTERNAL_DATA, exit 2. Rejected input/checkout/worker: REJECTED, exit 2. A successfully recorded technical comparison exits 0 even if its technical screen fails; consumers must inspect the flags, and independence always remains unverified by this instrument.

Authored tests cover end-to-end CLI execution with temporary Git fixture repositories, commit mismatch, dirty/ignored files, strict JSON, label validation, exact overlap, time ordering, error-vs-abstention, no-data blocking, private report creation and overwrite rejection. These validate the instrument, not external model accuracy.

## Adversarial screening correction

A baseline crash is an invalid reference execution and cannot establish a capability gain. Raw wins/losses remain in the report for audit, but any baseline error now blocks the technical screen, as do candidate errors. See runtime/PROOF_DELTA_RESULT.json for the reproducible old-pass/new-reject counterexample and surviving valid positive control. New regression tests also exercise concentration by cluster, latency budget, source changes during execution and worker timeouts.
