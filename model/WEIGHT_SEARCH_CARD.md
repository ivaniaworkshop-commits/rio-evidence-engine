# Weight-group search: programmed candidate, no task benefit

A bounded experiment on the existing extraction GRU, not access to any hosted
assistant's private model weights. All seven parameter groups were inspected.
Group ablation zeros one group at a time while holding the others fixed. It
measures conditional loss sensitivity, not additive causal attribution, neuron
importance percentages, or task utility.

## Reproducible dice and selection

Seed 7301; seven dimensions with faces 0.90, 0.95, 1.00, 1.05, 1.10. Sample 96
vectors out of 78,125 possible grid combinations. This is not an exhaustive or
globally optimal search. Repeated vector generation matches exactly. Selection
uses masked loss on a fixed 16-example TRAIN subset (12 supported, 4 unsupported),
not dev loss or dev answer scores. Dev is reported afterward and has been used
repeatedly across project exploration; it is not an independent final test.

Largest zero-ablation loss increases: embedding.weight and gru.weight_ih_l0,
both +5.815858; output.weight +4.966382; gru.weight_hh_l0 +1.917409. These effects
are conditional and overlapping, not independent shares of useful intelligence.

Selected multipliers actually applied and saved:

| Group | Multiplier |
| --- | ---: |
| embedding.weight | 0.95 |
| gru.weight_ih_l0 | 1.10 |
| gru.weight_hh_l0 | 1.10 |
| gru.bias_ih_l0 | 0.95 |
| gru.bias_hh_l0 | 0.95 |
| output.weight | 1.10 |
| output.bias | 0.95 |

Train-subset masked loss: 0.151030 -> 0.145070. Checkpoint reload reproduces that
loss locally. Dev outcomes: 0/78 exact graphs, 0/16 correct abstentions, 94 invalid
outputs. Therefore this weight change does NOT demonstrate a useful answer gain
or positive ROI. Candidate is NOT PROMOTED. Original and previous SFT checkpoints
are preserved. No automatic routing to the weighted candidate is enabled.

## Artifacts and reproduction

- weighted_extraction_gru.pt: programmed candidate, never default.
- WEIGHT_SEARCH_RESULT.json: all 96 vectors/losses, ablation ranking, selected
  factors, hashes and 94 raw dev outputs.
- `python scripts/search_weight_groups.py`: reproduces a bounded experiment;
  intentionally overwrites only this experimental candidate/report.

Optional CPU torch runtime is required. No paid API or external data is used.
Same-seed vector replay is guaranteed by the recorded algorithm/runtime test;
cross-platform neural loss equality is not established.

## Why the answer cannot be forced to yes

The current equivalent code baseline already gets all 94 task decisions right.
Accuracy cannot exceed 100% on the same fixture. A meaningful yes requires
matching it at a lower total cost or adding correct capability beyond its scope
on separately defined evaluation. The recorded PyTorch paths are slower and
less correct. Lower loss and more trials do not remove that evidence.

Stop promoting changes selected only by loss. Define the next capability or cost
criterion first; preserve failures and publish paired outcome/cost evidence.
Monte Carlo cannot manufacture an observed neural benefit or validate unknown
language coverage. This report is a negative research result, not completion of
a functional extractor or an LLM.
