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
