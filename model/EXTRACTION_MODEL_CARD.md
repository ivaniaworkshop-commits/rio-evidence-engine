# Extraction SFT candidate — NOT PROMOTED

Architecture: same 17,344-parameter byte GRU as the original; initialized from
the original checkpoint, fine-tuned for 500 optimizer steps on the dedicated
330-row train corpus. Prompt and padding positions are masked from the loss;
only target graph JSON/ABSTAIN plus EOS byte 0 receive next-byte loss.

## Actual result

Development masked loss: 4.970211 -> 0.163218. Reloaded checkpoint produces the
same local loss. But free generation on the structurally separate 94-row dev
set produces 0/78 exact graphs, 0/16 correct abstentions and 94 invalid outputs.
Inspected outputs repeat task B rather than terminate a valid graph. The loss
uses correct preceding target bytes (teacher forcing); rollout consumes its own
previous output. Lower teacher-forced loss did not establish rollout correctness.

This candidate is rejected for use as a graph extractor. It is neither a large
language model nor a functioning semantic parser. The original checkpoint,
strict default, deterministic engine and public evaluation fixture are preserved.
The 28-case public evaluation was not accessed by this training script and is
not run against the failed candidate. Dev is not a hidden or independent test.

## Artifacts and reproducibility

- extraction_gru.pt: separate candidate checkpoint, never automatic promotion.
- EXTRACTION_TRAINING_RESULT.json: settings, data hashes, losses and all dev outputs.
- EXTRACTION_READBACK.json: checkpoint/data identity and frozen evaluation checks.

Optional CPU runtime: `python -m pip install -r model/requirements-cpu.txt`.
Run `python scripts/train_extraction.py` to reproduce a 500-step experiment.
It intentionally overwrites the candidate checkpoint/report, not the original.
Same-seed results across hardware/library versions are not guaranteed.

A diagnostic CLI exists: `python -m rio_evidence.extraction_model input.json`,
where input.json contains only a text field. Invalid outputs are rejected, and
schema-valid outputs remain semantically UNVERIFIED; no task execution occurs.
No private data or third-party training corpus was used.

## Next gate

Before adding steps or parameters, test bounded/constrained decoding against the
observed repeated-id/nontermination failure and separately evaluate exact graph
semantics. Structural validity is not extraction accuracy. A grammar may prevent
a repeated B loop without teaching the model the correct durations or edges;
it must not be presented as learned semantic success.
