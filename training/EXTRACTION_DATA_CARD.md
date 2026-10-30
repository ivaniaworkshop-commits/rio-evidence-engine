# Extraction training/dev data

Status: generated and audited, NOT used for weight updates. Existing model and
its observed failures remain unchanged. The old neural train command still
trains on answer_matrix.jsonl; it must not be mistaken for extraction training.

424 authored synthetic examples: train 330 (282 supported, 48 unsupported), dev
94 (78 supported, 16 unsupported). Targets are canonical graph JSON or ABSTAIN.
Three wording templates express explicit tasks and dependencies. Negative cases
cover unspecified duration, unspecified predecessors, cycles and conflicting
durations. Dev conflict examples are held out by negative-reason family.

## Separation

Positive examples are partitioned by graph-isomorphism signature (all 24
relabelings of four-task graphs), excluding every positive topology in the
existing 28-case evaluation fixture. Train has 21 structural groups; dev has six.
No normalized text overlap, no isomorphic positive graph overlap and no duplicate
generated text were found. Evaluation bytes were checked unchanged. Audit
includes hashes for both datasets and the evaluation fixture.

This is NOT proof of statistical independence or natural-language diversity.
Word families share vocabulary/templates; all references are project-authored.
Isomorphism ignores durations and task labels. Dataset size is not a measure of
real users, language coverage, model quality or competition performance.

## Reproduce

```sh
python scripts/build_extraction_data.py
python -m unittest discover -s tests -v
```

The builder uses standard-library code and local project validation. It does not
fetch data, train models, activate agents or modify the evaluation fixture.
No third-party source dataset or private conversation content is included.

## Next training gate

Use a dedicated task-training entrypoint and separate checkpoint; mask prompt
loss so updates target graph JSON/ABSTAIN, retain train/dev separation, record
initial/final losses and exact graph/abstention metrics. Evaluate dev before the
public fixture. Keep the original checkpoint and deterministic baseline for
comparison; improve capability rather than only next-byte loss. No successful
extraction training or generalization is claimed by this data preparation.
