# RÍO Primer Cobro R021 — Rehearsal and gated promotion

## Observed baseline
- Source branch: `deploy/primer-cobro`, PR #30 draft, not merged into `main`.
- GitHub rulesets visible in R021: `[]`; production auto-deploy remains blocked.
- R020 candidate Vercel: `dpl_C5PkJHxVuhJEx4qSVm9tzjJg5q9r`, `READY` and exact 2/2 via Vercel connector.
- Existing R019 E2E on production: 33/33 PASS on hosted Chrome, not Android physical.

## R021 functional improvement
- Production job now reruns the full browser checkout on the **exact staged candidate** after binary readback and before `vercel promote`. This closes a test-to-release gap.
- E2E test accepts a tightly validated `RIO_TEST_BASE_URL`, restricted to the known public host and deployment host pattern for this Vercel project; no cookies or bank credentials.
- Frozen candidate rehearsal workflow `.github/workflows/rio-r021-candidate-rehearsal.yml` triggers only when `R021_TRIGGER.txt` changes and checks 2/2 HTML bytes plus the complete 33-step browser scenario from GitHub runner. Results remain UNKNOWN until its GitHub Actions run completes.
- The candidate is a **staging** URL, not a promotion to production. GitHub ruleset and environment secret must still be configured separately for automatic promotion.

## Authority and limits
`PLAN != EXECUTION`. The production job is currently blocked because GitHub branch protection rules are not observed. The PR remains in DRAFT. QR is educational `NO_PAGABLE`; payments and Android physical testing remain `NOT_OBSERVED`.

## Next delta
If the rehearsal passes, retain the exact-byte and E2E gates, then implement a production post-promotion incident/rollback decision with concurrency fencing and independently verify GitHub policy before any activation.
