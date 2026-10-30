# H09 - Bounded deterministic extraction capability

Review anchor: main at 5d78b18482d53243a94e713f8eff593afca19c92.
The existing general Python scheduler accepts arbitrary DAG nodes, but
graph_copy.py reads only four fixed surface schemas and IDs A-D.
Earlier reported 94/94 is in-domain, so cannot be improved in place.
A neural dependency extractor did not earn its runtime cost there.

H09 adds extended_graph.py, an opt-in additive parser that accepts:
- Required "Tasks: N" header for N=1..8 tasks A through N.
- Four new full-line formats, including "Step A takes 3 minutes after none."
- Heterogeneous formats, exact source character offsets, full graph and schedule.
- Strict refusal for missing/duplicate/unknown declarations, cycles, appended
  instructions, invalid durations, repeated dependencies and long input.
- Legacy graph_copy behavior preserved and called first when supported.
- No neural calls, model parameter changes, protection activation or LLM claim.

The project-authored test enumerates every one of the 2^10=1024 possible
forward-edge DAGs among five ordered tasks A-E, encoded in four formats:
4096 paired cases. The labels are constructed directly from the enumerated
adjacency sets, not from parsed results. Original 94 dev-case outcomes are
paired and checked for regression. Additional negative tests exercise
rejection behavior. A runner prints actual medians and success counts.

This is new *bounded format coverage*, not general human-language
understanding, hidden test performance or independent source evidence.
H08 remains BLOCKED_NO_EXTERNAL_HOLDOUT. Do not infer a statistical
confidence interval for external accuracy from exhaustive authored cases.
Reproduce with: python scripts/evaluate_extended_graph.py

## Observed commit evidence
Source run 41135727554 on main bea424e7cf888d118249cf3b7e95ec204711e8c1
succeeded with 129/129 tests; 4096/4096 new-format matches vs 0/4096,
94/94 legacy grades preserved. Details in model/H09_RESULT.json.
One/eight task boundaries are added as subsequent CI-gated tests; do not
extrapolate the exhaustive five-task graph enumeration to arbitrary input.
