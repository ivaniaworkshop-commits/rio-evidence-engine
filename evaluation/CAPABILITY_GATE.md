# Proposed capability: English task descriptions to exact task graphs

## Why this capability

The current engine requires structured JSON. It does not interpret task prose.
The current neural model was trained on answer text, not this extraction task.
A useful neural contribution would be recovering explicit durations and
predecessors across wording variants, then letting code calculate the schedule.
It must never silently infer unspecified dependencies or invent durations.

## Input/output contract

Input: an English description of tasks A–D, explicit nonnegative durations in
minutes and explicit predecessor constraints. Output: one JSON object containing
only tasks and durations, following examples/schedule.json. Task order and
predecessor order do not matter. Missing/ambiguous constraints, invalid graphs
and off-task instructions require ABSTAIN. No external tools or execution may
be authorized by the task description. Generated JSON must pass strict parsing,
graph validation and exact task/duration/edge comparison with the reference.
Correct critical-path totals alone are insufficient: different wrong graphs
can produce the same total.

## Public pretraining fixture

28 authored cases: 24 supported (three wording families, four topologies, two
duration variants) and four negative/unsupported inputs. All are published in
semantic_fixture.jsonl. References are authored from graph definitions and their
validity checked using the engine. They are NOT examples of actual users or
organizer hidden tests. They were not used to update the existing model weights.
Use other examples for future training; this public fixture cannot alone prove
unseen generalization. A later evaluation needs separately generated/frozen data.

## Comparators and acceptance target

1. Structured-only existing engine: no natural-language extraction interface.
2. Full-match rule baseline: supports the plain family; abstains otherwise.
3. Current byte GRU: instructed to return the graph without reference answers.

A candidate must achieve at least 23/24 exact supported graphs, 4/4 correct
abstentions and at least four additional supported matches over the rule
baseline. These are explicit engineering targets, not confidence bounds or
proof of general ability. Report latency, memory, invalid-output rate and prompt
truncation. Gain in next-byte loss is not acceptance for this capability.

## Current result and next gate

SEMANTIC_GATE_RESULT.json records actual model outputs and rule results. The pre-fix
inference kept only the last 128 prompt bytes, dropping earlier content.
The current implementation rejects budgets exceeding 128 UTF-8 bytes, including
the requested continuation, before model loading. That is a context/interface limitation, so failure cannot
be attributed solely to learned weights. No retraining is justified before a
lossless input path and adequate context are implemented and tested.

Context safety is now implemented. SEMANTIC_CONTEXT_GATE.json records
28 explicit context rejections; these are not semantic abstentions.
Next delta: define an architecture/context budget that covers the whole input. Re-evaluate the contract, then choose a model
architecture/context budget and separate training/evaluation data if a learnable
advantage remains. Do not inflate this small GRU into an LLM claim.

Reproduce: `python scripts/build_semantic_fixture.py` and
`python scripts/evaluate_semantic_gate.py` (optional torch required for the latter).

## Full-prefill experiment

STREAMING_GATE_RESULT.json evaluates the unchanged weights with a separate
full recurrent prefill path: all 28 prompts processed, 0/24 exact graphs,
0/4 correct abstentions. Lack of extraction ability remains after mechanical
truncation is removed. The next training experiment must use a separate task-
specific training corpus and preserve this evaluation fixture as evaluation
only; architecture, output constraints and acceptance must be defined first.
