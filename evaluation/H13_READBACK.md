# H13 — Audited readback of H10, H11, H12

This ledger preserves observed GitHub Actions receipts from commits BEFORE
this ledger's creation, avoiding circular self-certification. Scope is
historical CI result consistency, not external evaluation or authorship proof.

H10 main run 41137455826: 137 tests, no failures/skip; the project-authored
language shift diagnostic returned H09 exact 0/40 and appropriate abstention
12/12. Same for older deterministic baseline. This rejected a generic
language understanding claim.

H11 main run 41139172694: 149 strict tests, no failures/skip; two trusted
registered systems executed the same 52 public authored samples. The H09
identity control produced 0 wins/0 losses. Runtime was actually measured,
but third-party provenance, signed frozen model and cost are NOT established.

H12 main run 41139621169: 155 strict tests, no failures/skip. Exact conditional
binomial power at 30 cases and p=0.10 is 0.17549487903389516, versus a
20,000-draw fixed-seed Monte Carlo value 0.1779. Under the hypothetical,
independent, ZERO-loss case model, n=66 is needed to attain >=80% power for
the five-win threshold. A five-win single-cluster adversarial case was
rejected by the cluster-level sign screen.

All sources: model/EVALUATION_OBSERVATIONS_R001.json, with run URLs and source
commits. SHA256 of a dataset establishes bytes, NOT independent sampling or
correctness of labels. CI and the deterministic manifest can recheck internal
consistency but cannot authenticate the external source. No outside corpus
has been received and issue #8 remains open.

H13 receipt validation tests assert limited internal consistency only;
the newest test count changes after adding tests to the repo and must not
retroactively modify historic 155-test evidence.
