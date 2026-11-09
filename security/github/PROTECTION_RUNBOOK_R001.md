# GitHub protection rollout — ivaniaworkshop-commits/rio-evidence-engine

**State:** proposed repository files on `security/github-protection-bundle-20261109`, **NOT APPLIED as new GitHub rulesets**. Readback date: 2026-11-09.

## Observed platform enforcement

- `main.protected=true`; active ruleset `RIO_MAIN_PROTECTION_R001` (ID `26688691`) with three effective rule types: `deletion`, `non_fast_forward`, and `pull_request`. Review requires one approval, stale review dismissal, last-push approval, and an extra approval for unattributed changes. `require_code_owner_review=false` and no required status checks in this observed ruleset. The intentional R038 HOLD remains in effect.

## Native GitHub files staged in the pull request

1. `.github/CODEOWNERS` — ownership routing for critical paths. **Not an enforced owner-approval gate** until a ruleset explicitly requires it.
2. `.github/dependabot.yml` — weekly, bounded GitHub Actions dependency update PRs, **only after landing on the default branch**.
3. `SECURITY.md` — security-reporting and disclosure policy, not a mandatory CI gate.
4. `.github/pull_request_template.md` — review checklist, not a required approval.

## GitHub ruleset blueprints: four, all UNINSTALLED

| JSON | API rule types | Preconditions before administrative application |
|---|---|---|
| `main-review.json` | deletion, non_fast_forward, pull_request | Ensure independent reviewer; raises discussion-thread resolution. `require_code_owner_review` remains false until independent code owners exist |
| `main-ci.json` | required_status_checks | Observe fresh successful checks and bind contexts to trusted GitHub App, not merely text labels; runners must work |
| `main-verified-history.json` | required_signatures, required_linear_history | Verify existing signing tooling and select compatible merge methods first; may block automation |
| `immutable-tags.json` | deletion, non_fast_forward for `refs/tags/v*` | Confirm release naming and administrative ruleset permissions |

**Eight proposed scoped rule instances; six unique API rule types.** This is not eight rules already enforced.

## Expanded protection checklist (classification, not an enforcement claim)

| # | Desired security behavior | Control plane | Status |
|---|---|---|---|
| 01 | Reject deleting `main` | GitHub branch ruleset | ACTIVE_OBSERVED |
| 02 | Reject force-push on `main` | GitHub branch ruleset | ACTIVE_OBSERVED |
| 03 | Require PR into `main` | GitHub branch ruleset | ACTIVE_OBSERVED |
| 04 | Require at least one approval | GitHub PR ruleset parameter | ACTIVE_OBSERVED |
| 05 | Dismiss stale approvals after updates | GitHub PR ruleset parameter | ACTIVE_OBSERVED |
| 06 | Independently approve latest push | GitHub PR ruleset parameter | ACTIVE_OBSERVED |
| 07 | Extra approval for unattributed changes | GitHub PR ruleset parameter | ACTIVE_OBSERVED |
| 08 | Resolve review conversations before merge | GitHub PR ruleset parameter | NOT_APPLIED |
| 09 | Require code-owner approval | GitHub PR ruleset parameter | FUTURE_INDEPENDENT_OWNER_REQUIRED |
| 10 | Require trusted `main` CI checks | GitHub status-check ruleset | NOT_APPLIED |
| 11 | Require up-to-date branch before merge | GitHub status-check ruleset parameter | NOT_APPLIED |
| 12 | Bind check contexts to a trusted App | GitHub status-check integration ID | NOT_VERIFIED |
| 13 | Require cryptographically signed commits | GitHub signature ruleset | NOT_APPLIED |
| 14 | Require linear commit history | GitHub history ruleset | NOT_APPLIED |
| 15 | Forbid deleting release tags `v*` | GitHub tag ruleset | NOT_APPLIED |
| 16 | Forbid force-updating release tags `v*` | GitHub tag ruleset | NOT_APPLIED |
| 17 | No ruleset bypass actors | GitHub ruleset bypass list | ACTIVE_OBSERVED_MAIN |
| 18 | Restrict accepted merge methods after audit | GitHub PR ruleset parameter | NOT_APPLIED |
| 19 | Require approved deployment environment | GitHub deployment ruleset | NOT_CONFIGURED; NEED_REAL_ENVIRONMENT |
| 20 | Require code scanning | GitHub code-scanning rule | CAPABILITY_AND_PASS_CHECK_REQUIRED |
| 21 | Block exposed secrets on push | GitHub push-protection feature | SETTINGS_AND_ENTITLEMENT_UNKNOWN |
| 22 | Secret-scanning alerts | GitHub security settings | SETTINGS_UNKNOWN |
| 23 | Dependabot version-update PRs | GitHub-native `dependabot.yml` | STAGED_NOT_EFFECTIVE |
| 24 | Dependabot security alerts/updates | GitHub security settings | SETTINGS_UNKNOWN |
| 25 | Private vulnerability reports | GitHub security settings | SETTINGS_UNKNOWN |
| 26 | Route sensitive changes to owners | GitHub `CODEOWNERS` | STAGED_NOT_EFFECTIVE |
| 27 | Default `GITHUB_TOKEN` read-only | GitHub Actions settings and workflow YAML | REPOSITORY_SETTING_UNKNOWN |
| 28 | Require manual approval for outside contributions | GitHub Actions settings | SETTINGS_UNKNOWN |
| 29 | Limit reusable Actions sources/versions | GitHub Actions settings + SHA-pinned workflow usage | POLICY_UNVERIFIED |
| 30 | Reject risky untrusted workflows | Repository antivirus CI | NOT_AN_ENFORCED_MERGE_GATE_UNTIL_REQUIRED_CHECK |
| 31 | Use documented security disclosures | GitHub `SECURITY.md` | STAGED |
| 32 | Use PR security-evidence checklist | GitHub PR template | STAGED; ADVISORY_ONLY |

## Authorized administrative operation and readback

These JSON files are **API payload examples**. GitHub does NOT auto-apply repository-committed JSON in `security/github/ruleset-proposals`.

1. Ensure the requested GitHub plan and administrator credentials are present; never paste credentials into issues, chat messages or workflows.
2. Restore runner availability and observe genuine green CI before activating `main-ci.json`.
3. Confirm independent human reviewer capacity before enabling stricter review; a single owner's `CODEOWNERS` entry is not an independent approval.
4. Inspect existing rulesets first. Keep existing active ruleset ID 26688691 intact; use additive, separately named rules if appropriate.
5. From an authorized terminal with authenticated `gh`, create a *reviewed* new ruleset using `gh api -X POST repos/ivaniaworkshop-commits/rio-evidence-engine/rulesets --input security/github/ruleset-proposals/immutable-tags.json` only after release-tag requirements are confirmed.
6. GET the new ruleset and branch/tag protection status. Record actual rule IDs, `enforcement=active`, exact conditions, no bypass, and affected refs. Only then classify `OBSERVED_ENFORCED`.
7. Never add `R038` (intentionally failing release HOLD) as a mandatory passing check. Never convert HOLD to PASS by skipping its tests.

### Safety / next verification

`WRITE_FILE != RULESET_APPLIED`. `PR_CREATED != MERGED`. `CI_PENDING_OR_FAILED != PASS`. `CONTEXT_NAME != TRUSTED_PRODUCER`. `CANON!=RUNTIME`. Rebase on the current `main` before any merge and preserve existing security HOLD and deny gates.
