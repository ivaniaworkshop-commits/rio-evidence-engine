# Explicit-duration recovery with source evidence

Scope: narrow, code-based recovery of integer-minute values for fixed IDs A-D
from recognized authored wording patterns. Each observed value stores matched
text plus start/end offsets for the number and full source fragment. Offsets
are Python Unicode character indices, not UTF-8 byte positions. All returned
spans are checked against the original text in dev evaluation.

Missing, contradictory or unsupported values/IDs cause code abstention; partial
observations remain evidence only. Repeated identical values are not conflicts.
The component does not parse dependencies, prove complete instruction coverage,
or understand general English. Text input is capped at 4096 UTF-8 bytes.

## Paired dev result, unchanged candidate weights

94 matching dev cases: 78 supported descriptions and 16 conflicting-duration
negatives. Duration fields correct: 12/312 with model slot selection, 312/312
with code recovery. All 16 dev conflicts correctly abstain before neural
inference. No invalid outputs, but exact graphs remain 0/78 because dependencies
are still selected by the neural candidate. Candidate remains NOT PROMOTED.

The successful abstentions come from code rules and these dev negatives cover
only duration conflicts; do not claim learned abstention or universal detection
of missing/ambiguous/cyclic instructions. Other failure modes require separate
contracts and tests.

## Integration and reproducibility

`python -m rio_evidence.duration_copy input.json` accepts a JSON object containing
only text and returns values/evidence without model loading. `grounded_generate`
composes this narrow component with the optional constrained candidate, copying
values into grammar slots and leaving dependency semantics unverified. The
closed candidate accepts copied durations only in 1..24; larger recovered values
cause explicit decoder-scope abstention, not clamping or model guessing.

`python scripts/evaluate_duration_copy.py` reuses the same dev IDs/checkpoint,
compares with CONSTRAINED_EXTRACTION_RESULT.json and writes DURATION_COPY_RESULT.json.
No new training, checkpoint update or evaluation-fixture access occurs.

Next useful delta: recover explicit predecessor constraints with source spans,
validate missing/ambiguous/cyclic dependencies, and compare exact graphs against
the neural dependency choices. Attribute any code success to code, not learned
language-model comprehension.
