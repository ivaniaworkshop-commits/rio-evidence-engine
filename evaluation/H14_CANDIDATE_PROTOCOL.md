# H14 — Strict structured-serialization candidate (freeze pending)

**Design scope.** A deterministic, opt-in candidate adds complete-document
CSV with the exact header task,duration,predecessors and full JSON graph
objects (tasks/durations) on top of the unchanged H09 graph extractor.
Task IDs must be consecutive A..H, 1..8 entries, integer durations 0..1M,
acyclic dependencies and complete explicitly stated nodes. CSV predecessor
lists use the literal | delimiter, with none for an independent task.
Rejected partial/malformed/cyclic/duplicate/unknown input is an abstention;
no inference from incomplete prose, no network, no neural weights.

**Development evidence ONLY.** H10 publicly exposes five authored CSV
examples and 35 other supported non-CSV wordings. The new parser is designed
after that publication; testing H10 is *development regression*, not an
independent capability confirmation. H10 has 12 authored negatives.
Run python scripts/h14_development_probe.py and the full unittest suite.
For independent evaluation freeze this exact candidate and H09 baseline
source commits and executable interface BEFORE a third-party evaluator
collects unseen source texts. Do not change the frozen candidate once
collection begins. Commit hashes identify code bytes, not accuracy.

**Uncertainty.** Correct full-graph output versus safe abstention is measured.
No calibrated confidence probabilities or entropy reduction is claimed.
No automatic model promotion is authorized. The evaluator H11 runs the same
cases against current H09, and tracks time; external authenticated provenance
and financial/energy costs are still UNKNOWN. Source data must remain private,
labels independently adjudicated, and the independent holdout must not be
reused in model development. H08 issue #8 is open.
