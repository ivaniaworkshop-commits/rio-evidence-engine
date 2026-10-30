# Does the network earn its cost? Accuracy-first gate

Answer for the current weights and evaluated closed formats: **NO**. A stronger
code reference now recovers both explicit durations and predecessor sets, validates
all lines/IDs/cycles and provides source spans. It achieves 78/78 exact supported
graphs and 16/16 correct code abstentions on authored dev. This is not a claim
of general English understanding, real-world accuracy or learned neural ability.

## Same cases, same scoring, actual costs

NETWORK_VALUE_RESULT.json compares 94 paired dev cases, three alternating-order
runs per mode, excluding one warm-up each. Code obtains 94/94 correct task
decisions; the duration-copy-plus-neural-dependency pipeline obtains 16/94.
Those 16 are code conflict abstentions, not learned improvements. Current local
median latency: code 0.068338 ms, neural pipeline 15.955322 ms. Model import/load
cost is recorded separately. Financial cost is UNKNOWN; no account meter exists.

GRAPH_COPY_RESULT.json records exact graphs, raw source spans and five local
repetitions per case. A structured graph is produced only if every nonblank line
matches a recognized full-line pattern, IDs A-D are complete and unique, values
agree and the graph validates. Unknown text, duplicates, conflicts and cycles
abstain explicitly. Syntax acceptance is not a universal semantic confidence.

## Matrices, Monte Carlo and determinism

The value report includes a 94-by-4 paired matrix: correctness and median latency
for both modes. Monte Carlo resamples paired cases and varies abstract wrong-answer
and latency penalties for 10,000 draws. A second same-seed run matches exactly.
The network-preferred frequency is 0 under these assumptions. This is NOT a
future accuracy probability, monetized ROI, independent validation or odds of
winning. Templates are correlated and authored by this project; the result is
conditional on these cases and the stated loss function.

Observed uncertainty reduction is narrowly supported: the earlier pipeline's
78 wrong supported graphs become 78 exact graphs with source evidence. No
calibrated uncertainty probability or entropy reduction is asserted. Statistical
uncertainty about unknown wording, people and the official challenge remains.

## How a future network could earn a yes

A future candidate must add correct answers or appropriate abstentions on a
separately specified task beyond this equivalent code baseline, not a weaker
obsolete baseline, while its measured overhead is acceptable. Freeze examples,
compare outcomes pairwise, measure coverage/error/abstention, keep provenance,
and publish failures. Another loss reduction alone is insufficient. Current
weights are retained for research; no promotion or new training occurred.

Reproduce: `python scripts/evaluate_graph_copy.py` and
`python scripts/evaluate_network_value.py`. Code-only interface:
`python -m rio_evidence.graph_copy input.json`, where input.json contains text.
Optional torch is required only for the paired neural comparison. The 28-case
public evaluation is unchanged and was not used by these evaluators.
