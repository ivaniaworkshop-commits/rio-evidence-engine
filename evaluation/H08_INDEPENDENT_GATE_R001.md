# H08 — External capability gate; technical screening != independent acceptance

Status at creation: **BLOCKED_NO_EXTERNAL_HOLDOUT**. No authenticated third-party
holdout was supplied or retrievable from the repository. No new neural
capability has been demonstrated and no weights or automatic promotion change.

The known project-authored 94-case development split has a perfect 94/94
closed-format code baseline. It cannot show an additional code-or-neural
correct-decision gain on the same cases. The next candidate must address NEW,
explicitly defined task structures or phrasings on which the incumbent can fail,
while preventing worse unsupported-case behavior.

Proposed independent experiment (not yet run with independent evidence):
1. Freeze baseline and candidate commits and executable interface *before* an
   external evaluator acquires the hidden test set. Keep test items inaccessible
   to training, examples and prompt construction.
2. An external evaluator obtains, labels and retains at least 30 supported
   task cases and 10 unsupported/ambiguous cases across at least five independent
   source/wording clusters; these sample counts are minimal engineering screens,
   not a power calculation or independence proof.
3. On the SAME fresh cases, run frozen baseline and candidate, log raw outputs,
   runtime versions, per-case wall times, evaluator and collection provenance.
   Grade exact task nodes/durations/dependencies, not only schedule totals.
4. Report paired wins and losses, supported exactness, appropriate abstentions,
   wrong forced answers, measured latency and cost separately. Record zero,
   unknown and missing values distinctly. Trial cases cannot later be called hidden.
5. A descriptive paired exact-binomial discordance screen requires >=5 net
   correct additional cases and p<=0.05, no correct-abstention regression and
   a specified latency budget. This is a **screen**, NOT statistical proof
   under correlated cases, nor a source authenticity check.
6. Authentication of the evaluator, source originality, frozen code,
   execution attestations, economic costs and authorization remain OUTSIDE this
   standalone JSON bundle. No self-reported field can authorize promotion.

Implemented validator: `python -m rio_evidence.independent_gate`
reports BLOCKED_NO_EXTERNAL_HOLDOUT when no evidence is supplied; with a
candidate JSON file it checks format, reference-graph validity, locally
recomputes the incumbent code baseline on the exact text, checks exact overlap
with known train/dev/public evaluation text and computes paired metrics.
It does NOT execute or authenticate candidate claims/timings, prove semantic
non-contamination or independently validate the data labels. It always returns
candidate_promoted=false. Do not publish an externally sealed holdout in the
public repository without explicit authorization.

The CI job treats the missing holdout as **expected BLOCKED** and runs synthetic
gate unit tests as an engineering check, not as a passing independent evaluation.

Financial cost: UNKNOWN until independently measured. Additional parameters
and a lower teacher-forced loss are not acceptance criteria.
