# Grounded tutor: model and corpus status

This project now has a computed answer corpus, reference-answer engine, prompt
builder and an optional local model-runner adapter. It does NOT include trained
LLM weights, tokenizer, transformer implementation, model server or observed LLM
inference. Runtime availability in the building environment: torch, transformers,
llama_cpp, ollama and llama-cli were not available. No training was performed.

## Corpus and use

128 authored scheduling scenarios cover four dependency topologies and varied
durations. 102 are practice cases and 26 are a fixed evaluation partition.
Reference answers and explanations are English. An exhaustive path oracle checks
the numeric answers separately from the scheduling implementation. These are
synthetic cases, not people, customer usage or the official challenge dataset.
The published holdout is inspectable and cannot establish unseen generalization.

```sh
python scripts/build_answer_matrix.py
python -m rio_evidence.tutor answer training/answer_matrix.jsonl SCHED-001
python -m rio_evidence.tutor prompt training/answer_matrix.jsonl SCHED-001
```

`answer` is deterministic, not model inference. `prompt` exports the case and
computed evidence to ground a model explanation. This deliberately supplies the
answer: it tests faithful explanation, not independent problem solving.

## Optional LLM runner contract

```sh
python -m rio_evidence.tutor generate training/answer_matrix.jsonl SCHED-001 --runner /absolute/path/to/trusted-model-runner
```

Configure an explicitly trusted executable yourself. It receives a prompt on
stdin and must return one JSON object on stdout with case_id,
critical_path_minutes, single_worker_minutes, path, explanation. The adapter
uses no shell and has a 30-second timeout. It executes the chosen command with
the invoking user's ordinary process permissions; it is NOT a sandbox and it
must never receive an untrusted executable or command from corpus content.
No weights or runtime are downloaded automatically; no credentials or paid API
are included. Runner failures or reference mismatches fail closed. Canonical
path matching is strict; an equally long alternative path is not accepted by
this format. The adapter test uses a Python echo stub, NOT an LLM.

## Evaluation limits

Numbers and canonical path are checked against the deterministic reference.
Explanation semantics, English quality, human understanding and external model
quality are not independently established. More eloquent output is not proof
of better reasoning. Never use this curriculum to invent application experience.

## Next model gate

Choose a model with suitable license, size, memory and CPU/GPU support; provide
an authorized runtime with actual weights; run the 26 evaluation cases; record
model identity, configuration, per-case outputs, latency, failures and cost.
Only after observing inference may the project claim a working LLM integration.
Training a model from scratch is a separate, unevaluated scope.
