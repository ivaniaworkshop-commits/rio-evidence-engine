# Changes

## Input validation and usable command line

- Reject ambiguous dependency containers, duplicate edges, and malformed task objects.
- Replace repeated graph scans with deterministic heap-based Kahn traversal.
- Reject fractional and boolean Wilson counts, invalid confidence values, and fractional telemetry counts.
- Reject non-object results and blank case ids; detect critical-path overflow.
- Reject duplicate JSON keys and incomplete final lines when reading journals.
- Add JSON CLI commands for schedules, paired comparisons, and journal verification.
- Add runnable examples and regression coverage, including 64 seeded DAGs.
- Refresh local validation and manifest; record a bounded synthetic benchmark.

Compatibility: unrelated graph nodes may have a different deterministic ordering.
Previously accepted malformed inputs now raise ValueError. CLI syntax errors use
argparse formatting; data errors use JSON. No user adoption or production claim
is introduced. Existing hash serialization is preserved.

## Public interface

Add a static dashboard with evidence receipts, synthetic comparator and filters;
add four browser-comparator parity checks and an explicit bounded recalculation
policy. Five daily tasks are enabled; first execution has not yet been observed.

## Numeric boundaries and evidence provenance

Three new regressions reproduce and fix a spurious infinite latency mean, JSON
CLI failure for finite data, and acceptance of an overflowing schedule total.
Dashboard provenance now separates the benchmark source from tested core bytes.

## Acceptance gaps and reproducibility

Add explicit BOG/26 acceptance audit, prototype design and individual rehearsal.
Add safe manifest inventory verification with four regressions. Execute the
suite, demo and schedule CLI from a fresh temporary source copy. Official
service, incident, video, hidden tests, debrief and submission remain unverified.

## Computed curriculum and tutor adapter

Preserve exact integer schedule totals; add a 128-case English answer matrix,
exhaustive path-oracle checks, prompt exporter and explicit local-runner adapter.
Adapter smoke test uses a stub, not a model. LLM runtime/weights remain absent.

## Scoped research and decision sensitivity

Inspect six retrieved official documentation pages; record two unavailable
sources. Integrate strict bounded CLI JSON with four tests. Add reproducible
Monte Carlo candidate ranking, explicit judgment matrix and weight sensitivity.
No LLM training or observed prediction accuracy is claimed.

## Actual small neural model training

Train a 17,344-parameter byte GRU on the public practice corpus, evaluate shared-template
holdout, save/reload checkpoint and observe generation. Include optional runtime
requirements and three additional tests. Output is unreliable; no LLM claim.

## Grounded hybrid inference

Add exact schedule answering with optional learned ranking of three grounded
English candidates. Preserve deterministic fallback and invalid-graph rejection.
Add four tests and 42 authored graph evaluations against an exhaustive oracle.
No new training or improvement in free neural arithmetic is claimed.

## Paired neural ablation

Measure 42 paired cases, five warm repetitions and three fresh-process starts
per mode. Identical outputs; neural latency/memory overhead observed. Preserve
deterministic default and label neural ranking experimental. Publish raw data,
method and limits; no additional training performed.

## New-capability acceptance gate

Define exact English-to-graph extraction with abstention. Publish 28 authored
cases, rule/model baselines, raw neural outputs and four contract tests. Current
model demonstrates no extraction ability; silent 128-byte input truncation is a
blocking interface limitation. No new model training.

## Explicit neural context rejection

Require nonempty UTF-8 prompt plus continuation to fit 128 bytes. Reject before
runtime load; remove both prompt suffix and generation sliding-window slicing.
CLI emits structured context error and exit 2; default generation is 64 bytes.
Six new boundary/UTF-8/preflight/CLI tests pass. Current context reports preserve
historical failed-generation reports. No checkpoint changes or retraining.

## Synchronized model descriptions

Generate model/DESCRIPTION.json and current-state blocks in README/model card
from observed training, checkpoint identity, context gate and local test record.
Retain historical measurements separately; scheduled updates must synchronize
all current descriptions before manifest and publication.

## Bounded full recurrent prefill

Add experimental 4096-byte prompt / 512-byte output path with cached GRU state.
Test byte accounting, early rejection, UTF-8 boundaries and greedy equivalence
to full-prefix inference. Process all 28 fixture prompts but observe no exact
graphs or correct abstentions. No retraining; strict default unchanged.

## Structurally separated extraction data

Prepare 424 authored examples for graph JSON/ABSTAIN, partitioned by topology
signature with evaluation topology exclusion. Check normalized text duplicates
and isomorphism overlap; freeze evaluation bytes. Add four data tests and data
card. No weight updates or model-quality improvement claimed.

## Response-only extraction SFT experiment

Initialize a separate candidate from original weights; train 500 steps with
prompt/padding loss masked and EOS target. Dev loss falls but 0/78 exact graphs,
0/16 correct abstentions and 94 invalid rollouts prevent promotion. Preserve
original model and evaluation fixture. Add four mask/budget/batch tests and
artifact readback evidence. No successful extractor or LLM claim.
