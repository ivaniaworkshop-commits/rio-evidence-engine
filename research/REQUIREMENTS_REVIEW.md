# Requirements review and evidence

Date: 2026-10-30. Coverage: eight selected official documentation endpoints,
six retrieved and inspected for the relevant sections, two unavailable (403).
This is a bounded review, not an exhaustive review of the internet. Search
service queries failed; direct official-page retrieval supplied the evidence.
SOURCES.json records timestamps, HTTP results, redirects, byte counts and hashes.
Hashes identify retrieved bytes, not factual truth. Full third-party pages are
not republished. Requirements below are engineering inferences from the sources.

## Findings integrated or retained

| Requirement | Existing implementation or delta | Evidence / residual gap |
| --- | --- | --- |
| Portable numeric JSON | CLI output rejects nonfinite JSON | Python JSON documentation supports explicit strict handling |
| Unambiguous bounded inputs | NEW: 1 MiB JSON input cap; reject duplicate keys and NaN/Infinity | tests/test_json_io.py; only schedule/compare CLI covered, not all parsers |
| Numeric precision | Exact integer totals retained; fsum for float totals | core and integer regression; triangular extremes remain unresolved |
| Explicit subprocess execution | Runner arguments passed without shell; timeout | tutor adapter; not a sandbox, output capture is not memory-bounded |
| Language-model training | Needs actual model/tokenizer, processed data, optimizer/trainer and changed weights | No training runtime or weights configured; corpus/adapter are not an LLM |
| Dataset partitions | Authored practice/evaluation partition exists | Public holdout is contaminated for independent future claims |
| Model evaluation | Requires recorded model identity, outputs and held-out metrics | Adapter tested with stub only; no inference or perplexity observed |
| Model card | Intended use, limitations, data and current state recorded | Training parameters/results cannot be supplied until execution |
| Reproducibility | Fixed-seed matrix, command logs, source manifests | Same-environment replay is not cross-platform bitwise reproducibility |
| CI supply chain | Official GitHub guidance recommends restricted permissions and pinned actions | No workflow added; remote CI remains NOT_OBSERVED |
| Prompt-injection defenses | Computed references and explicit trusted runner contract | OWASP page was unavailable; not claimed reviewed or implemented in full |
| Competition readiness | Acceptance matrix separates preparation and official evidence | Brief/starter, service, video, incident, hidden tests and debrief pending |

## Sources inspected

- [Python JSON](https://docs.python.org/3/library/json.html): strict-number options, duplicate-key behavior, and warning to limit untrusted input size.
- [Python math](https://docs.python.org/3/library/math.html): floating-point summation semantics; this does not imply arbitrary-precision integer sums.
- [Python subprocess](https://docs.python.org/3/library/subprocess.html): argument sequence, executable resolution and timeout behavior.
- [Hugging Face causal language modeling](https://huggingface.co/docs/transformers/tasks/language_modeling): dataset split, tokenization/collation, training and evaluation workflow.
- [Hugging Face model cards](https://huggingface.co/docs/hub/model-cards): model use, limitations, training data/parameters and evaluation disclosures.
- [GitHub secure use](https://docs.github.com/en/actions/reference/security/secure-use): minimal token permissions and action pinning.

Unavailable: PyTorch randomness notes and OWASP prompt-injection cheat sheet;
see SOURCES.json. Do not infer their contents from retrieval failure.

## Monte Carlo and matrix interpretation

DELTA_MONTE_CARLO.json contains a 5-by-6 candidate matrix (including candidate
identity), a 5-by-5 pairwise frequency matrix and 20,000 draws per scenario.
Base, correctness-first and learning-first profiles total 60,000 scenario draws.
The base scenario was replayed once and compared exactly (20,000 more draws).
Input scores, effort and risk are explicit subjective assumptions, not measured
ROI. Scores combine ordinal judgments, so ranking is decision support, not a
physical quantity. Candidate omission and correlations can reverse conclusions.

The base scenario splits top rank between individual debrief and strict JSON;
training gets no top ranks under the assigned high effort and risk. That result
reflects these assumptions and does not show that training has no long-term
value. Inspect the sensitivity profiles before choosing a route. Replay equality
only verifies this calculation with this seed/runtime. It does not establish
LLM determinism, predictive validity, human mastery or odds of winning.

Executed delta: bounded strict JSON for local schedule/compare input, with
negative tests and preserved integer identity. Remaining priority: obtain the
actual challenge and assess individual understanding. Further model work needs
runtime, weights, license review, resource budget and actual evaluation.
