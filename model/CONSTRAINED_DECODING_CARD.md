# Constrained extraction decoding — experimental, not promoted

Same task-SFT checkpoint as the failed free-generation run. No weight updates.
Code restricts output to ABSTAIN or a closed graph grammar with exactly four
unique task IDs A-D, integer durations 1..24 and dependencies on earlier IDs
only. Forced delimiters, unique IDs and bounded slots guarantee closure and
prevent cycles and repeated task objects. The model chooses the initial branch
and finite slot alternatives; grammar-valid bytes are partly constructed by code.
Slot alternatives are ranked by mean byte log likelihood, not truth confidence.

## Observed paired development results

94 identical dev cases and the same checkpoint as free generation. Invalid
outputs: 94 before, 0 after. All 94 constrained outputs were structurally valid
graphs; none were ABSTAIN. Exact supported graphs: 0/78. Correct negative-case
abstentions: 0/16. Individual durations: 12/312 correct. Dependency sets:
138/312 correct. Grammar completion is therefore NOT extraction success.

The closed grammar can force a plausible graph even when input is unsupported.
Outputs remain semantically UNVERIFIED and are never authorized for task
execution. This decoder does not support arbitrary IDs, task counts, durations,
or backward-labelled dependencies; it is a diagnostic experiment, not a general
natural-language parser. The deterministic scheduling engine and defaults are
unchanged. The candidate remains NOT PROMOTED.

## Reproduce and evidence

`python scripts/evaluate_constrained_extraction.py` records raw outputs, slot
choices and paired grades in CONSTRAINED_EXTRACTION_RESULT.json. Optional torch
CPU runtime and model/extraction_gru.pt are required.

`python -m rio_evidence.constrained_extraction input.json` accepts a JSON object
containing only text. Its output explicitly identifies the unverified candidate
and closed scope. No reference answer is passed to the decoder. Dev labels are
used only afterward for scoring. Public evaluation fixture is not used.

## Next useful gate

12/312 duration fields are correct despite code-guaranteed syntax. Prioritize
faithful recovery of explicit input values and unsupported-input detection,
comparing a transparent rule/copy baseline against model-only slot selection.
Measure exact values, edges, abstentions and end-to-end graphs separately.
Do not spend more training steps merely to improve teacher-forced loss or
count forced grammar as learned semantic ability.
