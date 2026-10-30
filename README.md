# Río Evidence Engine

[Open the public dashboard](https://rio-evidence-engine.ivaniaworkshop.chatgpt.site) · [Inspect the delta ledger](DELTAS.json)

A small, offline Python prototype for reproducible task dependencies, paired evaluation and evidence journals. Extracted from AI-assisted preparation work in the Río project. This repository exposes a bounded engineering component; it does not expose the private Río knowledge corpus.

## Run

Python 3.10+ syntax; verified here on Python 3.12.14. The demo and CLI require no third-party dependencies or API credentials. The optional array branch of `triangular_ppf` requires NumPy, which is not bundled or covered by the standard-library test suite.

```sh
python demo.py
python -m unittest discover -s tests -v
```

## What it does

- Checks a dependency graph for missing nodes, duplicates and cycles.
- Reports critical-path duration separately from total single-worker work.
- Compares baseline and candidate results only when case identifiers match.
- Validates a closed event-metadata schema and maintains a single-writer hash-linked journal.
- Separates local work-unit limits from unknown account credit balances.

## Decisions and tradeoffs

The core uses the standard library to reduce setup requirements. Graph scheduling is deliberately limited: the critical path assumes unlimited workers and is not a resource-constrained scheduler. Evaluation requires paired case identities so changing the denominator cannot masquerade as an improvement. A local journal makes evidence inspectable without a database, but is suitable only for a single writer.

## Verification

One hundred five tests (including four optional Node-based dashboard checks) cover graph scheduling, paired metrics, numeric boundaries, budget reserve, schema limits, journal consistency and incomplete-line handling. Actual execution results are recorded in VALIDATION.json. Regression tests include malformed inputs, CLI subprocesses, and dependency invariants across 64 seeded synthetic graphs. The demo uses authored synthetic values; it is not a benchmark or evidence of real-world performance improvement.

## Limits

A hash chain checks internal byte consistency. It does not prove the truth of an event, authority, authorship, completeness, protection against truncation or a coherently rewritten history. A syntactically allowed metadata value may still contain sensitive information: callers must supply appropriate identifiers. There is no active antivirus, autonomous agent runtime, independent AI protector, fine-tuning or production deployment.

## Contribution and provenance

The project owner directed the goals and evidence requirements. AI assistance was used for implementation, review and tests. The exported module and tests originated in the project’s FRONTIER preparation, not an official competition challenge. There is no claim of external users or independent certification. No third-party source implementation is intentionally included. Public licensing is not asserted by this preparation package.

## Use with your own JSON

From the repository root:

```sh
python -m rio_evidence schedule examples/schedule.json
python -m rio_evidence compare examples/compare.json
python -m rio_evidence verify-journal path/to/events.jsonl
```

Success writes JSON to stdout and exits 0. Input or journal validation failures
write a JSON error to stderr and exit 2. Invalid command usage is handled by
argparse and also exits 2. Example schedules are in minutes; comparison latency
is in milliseconds. The example comparison is synthetic, not a user study.

`schedule` expects `tasks` and `durations`; `compare` expects `baseline` and
`candidate`. See the checked-in examples for complete payloads. Dependencies
must be lists of unique ids. Traversal is deterministic and uses a heap-based
Kahn algorithm; unrelated task ordering may differ from the first version.
`verify-journal` checks internal consistency and rejects duplicate JSON keys
and incomplete final lines. It does not authenticate the writer.

## Performance evidence

BENCHMARK.json records three local runs per implementation on the same authored
2,000-node chain. It is a narrow measurement, sensitive to hardware and load;
it does not establish performance for arbitrary graphs or production workloads.

## Development

Run `python -m unittest discover -s tests -v` and `python demo.py` before a
change. See CHANGELOG.md for fixes and compatibility notes. The journal remains
single-writer, reads the full history on append, and has no locking or durable
transaction guarantee. CLI commands read local files only; no model API or
service is started.

## Public dashboard

The main visual interface is in `docs/`: a static evidence dashboard with linked
receipts, a synthetic browser-local comparator, delta filters and explicit
snapshot dates. It reads bundled `data.json`, not live Python execution.
Reload refreshes the deployed snapshot; it does not run tests or trigger an
automation. Browser examples stay local and make no model calls.

Run the full suite with Python and Node available to include comparator parity
checks. Without Node, four dashboard tests are explicitly skipped. See
RECALCULATION.md for the bounded improvement policy and scheduled review roles.

Numeric boundaries: latency averages scale each paired delta before summation to
avoid a spurious intermediate infinity. Unrepresentable schedule totals raise
ValueError. Snapshot provenance records SHA-256 of the tested core and validation
record; benchmark_source_commit identifies the older measured benchmark, not the
current dashboard version. File hashes identify bytes, not correctness.

## Observed assisted use

[VALIDATION_ACCOUNT.json](VALIDATION_ACCOUNT.json) records a user-requested
execution from the current ChatGPT session: actual repository manifest checking,
30 local tests, and journal append/readback using the engine. It checked 22
manifest-listed files from commit dc51bd7330d47cb2f4aaa30ba4c424521663e4a4.
This is assisted operational use, not a study of simulated people. Session
context is not cryptographic account attestation. It does not establish external
adoption, manual execution by the owner, or independent validation.

## Competition readiness

[Acceptance audit](competition/ACCEPTANCE.md) separates prototype evidence from
missing official obligations. [Design](competition/DESIGN.md) and
[debrief rehearsal](competition/DEBRIEF.md) support technical explanation.
They are preparation, not competition acceptance.

Run `python scripts/verify_manifest.py` to verify byte identity and inventory.
It rejects changed, missing, extra and escaping paths. This is not an
authenticity or correctness certificate.

## Grounded English tutor

[128-case answer matrix](training/ANSWER_MATRIX.md) · [Model status and runner contract](training/MODEL_CARD.md).
The deterministic tutor computes reference answers; an optional trusted local
runner can generate explanations grounded in those answers. A small byte GRU is now trained and included separately; it is not an LLM.
The grounded adapter and deterministic references remain distinct from neural output.

## Research and decision evidence

[Requirements review](research/REQUIREMENTS_REVIEW.md) · [Source retrieval record](research/SOURCES.json) · [Monte Carlo assumptions and results](research/DELTA_MONTE_CARLO.json).
Reproduce the ranking with `python scripts/prioritize_deltas.py`. Ranking
frequencies are assumption sensitivity, not observed ROI or win probabilities.
Local schedule/compare JSON inputs are capped at 1 MiB and reject duplicate
keys and nonstandard numeric constants. This does not bound every input surface.

## Trained small neural language model

[Model card](model/MODEL_CARD.md) · [Observed training result](model/TRAINING_RESULT.json).
17,344 parameters, 250 optimizer steps, checkpoint reload verified. Generated
text is repetitive and not a reliable answer; next-byte loss is not task accuracy.
Optional PyTorch CPU is required only for neural commands. See the model card
for exact train/inference commands and evaluation limits.

Observed neural task probe: 0/26 durations extractable in the specified format;
0 exact numeric matches. See model/TASK_EVALUATION.json. Training-loss reduction
did not translate into demonstrated scheduling-answer ability.

## Functional bounded hybrid interface

```sh
python -m rio_evidence.hybrid examples/schedule.json
python -m rio_evidence.hybrid examples/schedule.json --neural
python scripts/evaluate_hybrid.py
```

Deterministic code calculates numbers and constructs three grounded explanations.
The optional trained model ranks those candidates; failure falls back to a
known template. [Hybrid evaluation](model/HYBRID_EVALUATION.json) separates that
system behavior from the unchanged failed free-generation probe. It does not
show that neural ranking improves accuracy or explanation quality over code alone.

## Measured neural value

[Paired comparison](model/MODE_ABLATION.md): both modes produced identical
schedules and explanations in 42 authored cases. Neural ranking added local
time and process memory without observed output benefit. Deterministic mode
remains the default; `--neural` is experimental and optional. Financial cost and
human prose preference were not measured.

## Next neural capability gate

[English-to-graph contract](evaluation/CAPABILITY_GATE.md) · [Observed pretraining comparison](model/SEMANTIC_GATE_RESULT.json).
Current model: 0/24 exact graphs and 0/4 correct abstentions. Narrow rule baseline:
8/24 exact graphs and 4/4 abstentions. The current 128-byte input window silently
loses context; fix or explicitly reject that input loss before training more.
No new weights were trained for this capability.

## Explicit context budget

Neural free generation now requires nonempty input and `UTF8(prompt) bytes +
requested output bytes <= 128`. Oversized requests return CONTEXT_REJECTED
before importing/loading the neural runtime; no silent slicing remains in this
generation path. Default output is 64 bytes. Existing historical raw-generation
reports are retained; current context rejection reports are separate files.
See model/SEMANTIC_CONTEXT_GATE.json and model/TASK_CONTEXT_EVALUATION.json.
Context refusal is not correct semantic abstention and does not pass extraction.

<!-- MODEL_STATUS_START -->
## Current model status (evidence synchronized)

Río ByteGRU is a **small neural language model, not an LLM**: 17,344 parameters, 250 observed training steps. Checkpoint saved and reloaded. Project suite: 105 passing local tests.

Current free generation rejects prompt-plus-output budgets above 128 UTF-8 bytes. The extraction fixture has 28 context rejections, not semantic abstentions. Neural extraction is not established. Hybrid arithmetic remains deterministic. Optional neural ranking showed no output benefit in the paired 42-case comparison. Earlier low loss and failed raw-generation probes are historical, not current capability certificates.
Experimental recurrent prefill processes up to 4096 prompt bytes; observed full processing in 28/28 cases, but 0/24 exact graphs and 0/4 correct abstentions. No weights changed.
Separate extraction candidate: 500 steps; 0/78 exact graphs, 0/16 correct abstentions, 94 invalid outputs. Status: EXTRACTION_SFT_CANDIDATE_NOT_PROMOTED. Original model unchanged.
Separate closed-grammar decoding: 94/94 structurally valid outputs, but 0/78 exact graphs and 0/16 correct abstentions. Code-forced validity is not learned semantics.
Code-grounded durations: 312/312 fields correct, but exact graphs 0/78. Code abstentions are not learned neural ability.
Current accuracy-first paired comparison: code 94/94 correct decisions vs neural pipeline 16/94. Network value: NO_ON_THIS_SCOPE_WITH_CURRENT_WEIGHTS. No new weights or promotion.
A separate weight-scaling candidate was programmed from 96 seeded trials; loss improved but dev exact graphs remain 0/78. Not promoted; no demonstrated neural utility gain.
Bounded warm-cache/atomic-round support is observed. It changes runtime reuse, not neural weights, semantic accuracy or antivirus activation.
<!-- MODEL_STATUS_END -->

## Experimental full recurrent prefill

```sh
python -m rio_evidence.streaming --prompt "Case: parallel" --max-bytes 64
python scripts/evaluate_streaming_gate.py
```

Opt-in streaming accepts up to 4096 UTF-8 prompt bytes and 512 output bytes,
processes every prompt byte in order and carries the GRU hidden state. It does
not guarantee semantic retention in that fixed-size state. The default strict
128-byte combined-budget interface is unchanged.

[Observed evaluation](model/STREAMING_GATE_RESULT.json): 28/28 prompts processed
fully, 0/24 exact graphs and 0/4 correct abstentions. No new training occurred.
Removing the interface truncation did not demonstrate extraction capability.

## Dedicated extraction data (not trained)

[Dataset card](training/EXTRACTION_DATA_CARD.md) · [Separation audit](training/EXTRACTION_DATA_AUDIT.json).
424 synthetic examples: 330 train, 94 dev. Text duplicates and positive-graph
isomorphism overlap with each other and the public evaluation were checked.
The existing evaluation fixture is unchanged. Model weights were not updated.

## Extraction SFT candidate: failed capability gate

[Candidate card](model/EXTRACTION_MODEL_CARD.md) · [Training and dev outputs](model/EXTRACTION_TRAINING_RESULT.json).
A separate checkpoint received 500 response-only SFT steps. Dev loss dropped
4.970 -> 0.163 but rollout produced 0/78 exact graphs, 0/16 correct abstentions
and 94 invalid outputs. Candidate NOT PROMOTED. Original weights and evaluation
fixture unchanged. Lower teacher-forced loss did not establish task capability.

## Constrained decoding: validity without accuracy

[Decoder card](model/CONSTRAINED_DECODING_CARD.md) · [Paired dev evidence](model/CONSTRAINED_EXTRACTION_RESULT.json).
The same candidate checkpoint now yields 94/94 well-formed closed-grammar
graphs, but still 0/78 exact graphs and 0/16 correct abstentions. Durations are
correct in 12/312 fields; dependency sets in 138/312. Code forces bounded syntax;
this is not learned semantic improvement. Candidate remains unpromoted.

## Source-grounded duration values

[Duration recovery card](model/DURATION_COPY_CARD.md) · [Paired dev result](model/DURATION_COPY_RESULT.json).
Narrow code rules with source spans recover 312/312 duration fields vs 12/312
model-selected fields, and abstain on 16/16 dev duration conflicts before neural
inference. Exact graphs remain 0/78: dependency semantics are unresolved.
No weights changed, no candidate promotion and no learned-comprehension claim.

## Accuracy-first network value gate

[Current value comparison](model/NETWORK_VALUE_CARD.md) · [Raw paired matrix and simulation](model/NETWORK_VALUE_RESULT.json).
Complete closed-pattern graph recovery gets 78/78 exact dev graphs and 16/16
correct abstentions with source spans. The neural dependency pipeline gets
0/78 exact graphs plus the same 16 code abstentions, at higher local latency.
Seeded Monte Carlo explores explicit abstract cost assumptions; it does not
create neural benefit or prove future ROI. No model promotion or retraining.

## Weight-group experiment: not promoted

[Weight search card](model/WEIGHT_SEARCH_CARD.md) · [All trials and outcomes](model/WEIGHT_SEARCH_RESULT.json).
Seven ablated groups and 96 seeded scaling vectors were evaluated; selected
factors were saved to a separate checkpoint and reloaded. Train loss improved
0.1510 -> 0.1451, but dev remains 0/78 exact graphs and 0/16 correct abstentions.
No new default, task benefit, positive ROI or LLM success is claimed.

## Warmup, public precomputation and bounded automatic rounds

[Automation card](runtime/AUTOMATION_CARD.txt) · [Observed rounds](runtime/AUTO_ROUND_RESULT.json) · [Atomic Q6](runtime/ATOMIC_Q6.txt).

```sh
python -m rio_evidence.autoround --rounds 3 --max-actions 3
python -m rio_evidence.warm_session --max-requests 1000
```

Automatic rounds recalculate the queue around every allowlisted derived action.
The persistent JSONL session fills a bounded LRU on demand; optional
`--prewarm-public` loads only the published synthetic precompute. Returned results
are isolated copies. Invalidating duration-parser atoms preserves unrelated
numeric-cache entries. No arbitrary commands, code/weight changes, publication
or network calls are accepted from runtime input.

Local cache median was 0.0163 ms vs 0.0417 ms direct; bootstrap/prewarm
was 23.48 ms, with an estimated break-even of 925 reuses.
This is repeated-input evidence, not an unconditional end-to-end speedup. Memory cache lasts per process; public
precomputed artifacts can be reused across processes with matching revisions.
Guards borrow the fail-closed evidence principle; no antivirus runtime is active.

After authorized source changes: validate; run `python scripts/build_public_precompute.py`
if parser revisions changed; synchronize descriptions/snapshot; then run
`python scripts/refresh_manifest.py`. The runtime never repairs a failed
manifest automatically.

## Reproducibility and official-criteria boundary (H00/H01/H07)

CI on main (commit 79971e88bbb82ef68a0e529c35a7721b45d654df):
105 unit tests passed, zero skipped, with optional PyTorch 2.15.0+cpu installed.
Evidence: https://github.com/ivaniaworkshop-commits/rio-evidence-engine/actions/runs/41129448556

Official FRONTIER challenge acceptance, hidden scoring and submission contract
are NOT independently verified. The owner-supplied BOG/26 excerpts and
historical project rubric are preparation, not organizer-certified rules.
See competition/ACCEPTANCE_AUTHORITY_R001.json.

H07: scripts/h07_audit.py checks the identity and paired outcomes of
model/NETWORK_VALUE_RESULT.json; the torch CI workstream re-runs
scripts/evaluate_network_value.py. Dev cases are authored and correlated.
Cost in dollars and independent generalization remain UNKNOWN.
No added parameters or neural promotion is implied.

## External evaluation gate (H08)

`python -m rio_evidence.independent_gate` gives an explicit
BLOCKED_NO_EXTERNAL_HOLDOUT result until external cases and evaluator evidence
exist. Synthetic unit tests verify validation logic but are NOT independent
neural-capability evidence. No automatic promotion is possible. Read
evaluation/H08_INDEPENDENT_GATE_R001.md. The full CI suite now includes the
H08 contract tests; historical 105-test counts remain attributable to the
older commits, not silently rewritten.

## H09 deterministic capability extension
Use python -m rio_evidence.extended_graph input.json for strict explicit
task-description extraction. The legacy parser remains unchanged.
A project-authored 4096-case forward-DAG exhaustive test proves only bounded
new grammar coverage. This is not a neural improvement or hidden independent test.
See evaluation/H09_CAPABILITY.md for the scope and negative cases.

### H09 observed engineering result
GitHub Actions on main commit bea424e7cf888d118249cf3b7e95ec204711e8c1
recorded 4096/4096 exact matches on new four-format, five-task authored
enumeration vs 0/4096 for the old parser, preserving 94 existing cases.
The new code was slower in that runner. No neural improvement is claimed.
Evidence and limits: model/H09_RESULT.json.

## H10 wording-shift diagnostic
Run `python scripts/evaluate_language_shift.py`; 40 positive and 12 negative cases are authored by this project and are NOT an independent benchmark. H08 baseline is corrected to the current H09 parser. No external model success or promotion is claimed.

## H11 paired evaluation instrument
python scripts/h11_run_paired.py --diagnostic --candidate h09 runs both registered systems locally on the same H10 public cases; --candidate legacy is an adverse control. Source independence and frozen-revision attestation remain unavailable. No weight change or autonomous deployment.

## H12 conditional sample-size analysis
Run python scripts/h12_power.py for exact binomial and seeded Monte Carlo estimates under explicit independent-win/no-loss assumptions. H11 screening now checks cluster-level wins too; neither proves source independence. See evaluation/H12_POWER_DESIGN.md.

## H13 historical evidence receipts
Read model/EVALUATION_OBSERVATIONS_R001.json for GitHub Actions source commits/runs and observed H10-H12 states. Its new tests check only receipt consistency; they cannot authenticate original external source. H08 still blocked.
