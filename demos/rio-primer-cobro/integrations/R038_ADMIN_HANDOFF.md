# RÍO Primer Cobro — R038 governance hardening and denied-release preflight

**R038 is NOT production authorization.** Current GitHub connector can read active rulesets and checks, but cannot create or modify administrative rulesets. No admin operations or denied writes by restricted credentials have been performed.

## Delta and defect reconciled
- R037 counted any historical APPROVED review, even if later dismissed or superseded. R038 replays review records ordered by immutable numeric IDs and uses each reviewer's latest decisive state. An outstanding `CHANGES_REQUESTED` blocks even if another reviewer approved. Review data is fetched with `gh api --paginate --slurp`, bounded to 500 records, and source/merge-base identities are pinned.
- R037 read-only diagnostic workflow succeeded while its verdict was `BLOCKED`, creating a confusing green CI. R038 adds a **separate** `r038-policy-hold` GitHub check: this fails closed until prerequisites are demonstrably met. Its red state is EXPECTED under the present governance configuration, not a broken test suite.
- The proposed administrative rulesets target **both** PR #41's candidate branch and `review-base/primer-cobro-r026-preincident-20261106`; each also requires the `r038-policy-hold` check (pinned to GitHub Actions app ID `15368`), in addition to the prior `verify`, `strict-torch`, and `independent-history` checks. The `r038-policy-hold` predicate checks the three core checks only; it does **not** depend on its own check, avoiding circular dependency.
- Synthetic policy tests and GitHub API readbacks are not an external owner-identity proof, nor proof of immutable trusted CI source. A GitHub Actions app ID pins the producer, **not** the trusted workflow content. Independent host and workflow provenance require separate evidence.

## Operator admin handoff (future, authorized)
1. In GitHub repository Settings → Rules → Rulesets, a repository administrator with proper separate credentials can create the **two** exact active policies from `r038_governance.py --plan`; verify target refs, matching existing policies, reviews, no bypass actors, and required four checks. Do not paste tokens or secrets into the PR or this chat.
2. Perform live GET readbacks for both rulesets by numeric ID and run R038's read-only evaluator. A plan file, unit test and green diagnostic do **not** establish `RULESET_ACTIVE`.
3. Obtain independent human code review on the current SHA. Keep PR in draft until independent security/environment criteria are met; changing to ready-for-review is **not** itself approval to merge.
4. On a separately authorized, genuinely restricted GitHub identity, attempt a safely scoped unauthorized operation against the protected branch and record GitHub's **actual** denial. Owner or simulated failure is not evidence of this control.
5. Re-run the R038 workflow after administrative and review updates. Its `r038-policy-hold` must change from failing to passing on the current SHA; the old failed run remains as historical evidence. Release remains blocked until protected deployment environment, historical data treatment, human ownership, and payment-specific security requirements are validated.

**Status as of implementation:** R037 live readback revealed only main ruleset; PR #41 draft; independent approvals 0. R038 intentionally introduces `FAIL_CLOSED` CI until those external blockers change. No merge, no release, no real payments.
