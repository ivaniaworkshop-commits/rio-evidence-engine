# Security Policy — RÍO Evidence Engine

## Supported and unsupported claims

This repository contains evidence tooling, research, and demonstrations. A passing CI check is not proof of a deployed or secure production system. Financial/payment demonstrations must not be treated as real transactions.

## Responsible vulnerability reporting

Use **Security → Advisories → Report a vulnerability** on GitHub if private vulnerability reporting is enabled for this repository. If it is not enabled, request a private reporting channel from the maintainer without publishing a working exploit, credential, private key, or personal data in a public issue. Ordinary non-sensitive bugs may be reported in GitHub Issues.

Do not submit secrets, customer data, or credentials in pull requests, issue comments, workflow logs, or artifacts.

## Security review principles

- Read-only workflow tokens by default; explicitly minimize permissions for each job.
- No untrusted pull-request code in workflows with write tokens or elevated event authority.
- Use immutable commit SHA pins for third-party actions, with dependency updates reviewed before merging.
- Use independent PR review and fresh passing required checks when enforced by repository rules.
- Do not bypass release HOLD/deny gates to manufacture green CI.
- Record what was observed, what is inferred, and what remains unknown.

Repository protection settings and effective rulesets must be checked in the GitHub UI/API, not inferred from this document.
