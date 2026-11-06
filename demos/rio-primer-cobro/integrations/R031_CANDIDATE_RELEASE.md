# R031 · Candidate release branch preparation — NO production deployment

## Purpose
The R028/R030 sanitized PR #36 is the source. A separate candidate branch
`candidate/primer-cobro-r031-clean-20261106` is created from verified CI
and inherits the clean R030 ancestry. The candidate name is **not**
proof of GitHub protection or approval.

The R031 read-only workflow:
- Verifies the SHA-256 inventory and the R030 commit ancestry.
- Runs 18 synthetic, independent branch-ruleset policy tests.
- Fetches active GitHub rulesets using Actions read-only credentials.
- Checks a future exact branch ruleset for 1+ independent approval, deletion
  protection, non-fast-forward rejection, both `verify` and `strict-torch`
  required checks produced by GitHub Actions integration ID `15368`, and no bypass.
- Writes a receipt. Even if rules match, it explicitly leaves protected
  environment, secrets, user identity, review and Vercel activation UNKNOWN/OFF.
- Never accesses the Vercel token or calls `vercel deploy`, `promote`,
  branch rewrite, deletion or payment APIs.

## Administrative configuration pending
The connector lacks authorized GitHub ruleset/environment mutation operations.
An authorized repository administrator must establish an **active** branch ruleset
for the exact candidate ref, require PR review, deletion/non-FF restrictions,
and reviewed status checks. Protect credentials in an approved GitHub environment
and enforce environment reviewers before any future workflow can deploy.

Do not mark `PROTECTED` until the R031 readback shows a ruleset that applies.
An arbitrary required check name, just one check or an unverified check producer
does not satisfy the release contract. Both check contexts must be required on
the candidate PR, and source-only contract verification is not a review.
Do not mark `ACTIVE` merely because the policy gate passes—host identity,
secret state, review and Vercel deployment must be independently observed.

The old `deploy/primer-cobro` workflow has `deploy: if: false`, but historical
reachable commits also exist on `rio/omniretro-r003-release-status-a896efcd`.
Legacy PRs #30/#35 closed without merge; historical objects/caches/forks/clones
are NOT purged. No bank account is registered and Pey remains unverified.
