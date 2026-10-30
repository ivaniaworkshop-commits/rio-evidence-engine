# H11 — Instrumented paired execution (not independent external test)

The H08 JSON screen trusted submitter-provided candidate outputs and latencies;
a favorable numerical screen was therefore not direct execution evidence.
H11 implements a separate runner that executes the H09 incumbent and a
registered candidate callable on exactly the same labeled inputs.

The evaluator records actual Python perf_counter_ns wall times, interleaves
order over three runs, verifies repeated deterministic outputs, grades exact
full graphs and appropriate abstentions, and treats crashes as errors rather
than correct abstentions. It rejects submitted outputs/timings and raw
unregistered plugin imports. It never promotes a model.

Run: python scripts/h11_run_paired.py --diagnostic --candidate h09
or --candidate legacy (negative control). These use H10 public, project-authored
data, NOT an independent holdout. With no arguments it reports
BLOCKED_NO_EVALUATION_INPUT. Private inputs can be provided with --bundle
/private/file.json, containing an object with a cases array; each case has
case_id, cluster, text and expected (graph or null). No private bundle is
checked into this public repository.

An adversarial synthetic test uses a memorizer with access to its own gold
labels; it can pass a statistical engineering screen but CANNOT certify source
provenance, frozen model revision, generalization or production acceptance.
No new neural candidate is registered: the two controls are h09 and legacy.

For genuine independent evaluation, an authenticated evaluator must freeze
actual source revisions and model weights BEFORE obtaining unseen third-party
inputs, withhold them from development, independently adjudicate labels,
execute both authorized revisions and retain attestable readback and cost.
Local runtime is not a sandbox for untrusted code. No source independence
is inferred, financial cost stays UNKNOWN, and H08 issue #8 stays OPEN.
