# H07 - reproducible paired value and uncertainty gate (R001)

Baseline anchor: H00 strict-suite merge on main, commit 79971e88bbb82ef68a0e529c35a7721b45d654df.
Data: model/NETWORK_VALUE_RESULT.json, training/extraction_dev.jsonl and model/extraction_gru.pt.
The CI runner first audits the archived report without torch, and the strict CPU-torch runner
then repeats the paired comparison in 94 authored dev cases with three alternated-order runs per mode.

Acceptance rules:
- Pair by unique case_id and kind, reject missing/duplicate/changed ids.
- Check dataset and candidate checkpoint SHA256, correct grades, timings and 94x4 matrix.
- Compare supported exact graphs and unsupported correct abstentions as SEPARATE denominators.
- Report latency as machine-specific wall time; financial cost remains UNKNOWN.
- Reject neural promotion unless a separately frozen and independently evaluated dataset
  demonstrates incremental exact answers or appropriate abstentions against equivalent code,
  plus measured acceptable cost. Teacher-forced loss or syntactic grammar alone never qualifies.
- Simulation is conditional on authored cases and assumed loss; it is not a confidence
  probability over unseen users, competition scoring or financial returns.

Previously recorded authored-dev comparison: code 94/94 correct task decisions
(78/78 supported exact graphs; 16/16 unsupported appropriate abstentions).
Neural pipeline 16/94 correct task decisions (0/78 exact graphs; 16/16 unsupported
abstentions supplied by deterministic code conflict guards, not learned neural gains).
Prior medians: code 0.068338 ms, pipeline 15.955322 ms; machine-dependent.
Prior model import/load ~1029.7 ms excluded from per-call medians.
The resulting neural advantage in exact supported tasks is ZERO, not positive.
The strict job must execute scripts/evaluate_network_value.py and scripts/h07_audit.py
again; persist/claim only the observed new runner outcome.
