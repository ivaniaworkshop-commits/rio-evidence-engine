#!/usr/bin/env python3
"""R038: review-state-safe, fail-closed governance preflight for Primer Cobro PR #41.

Inputs are snapshots. Trust in provenance requires an authenticated GitHub API
retrieval on the runner; this parser does not authenticate supplied JSON.
Neither a passing policy readback nor an independent approval authorizes a
production deployment, release, payment or historical-data remediation.
"""
import argparse
import json
from pathlib import Path
import re
import sys

SCHEMA = 'RIO_R038_GOVERNANCE_PREFLIGHT_V1'
REPO = 'ivaniaworkshop-commits/rio-evidence-engine'
TARGET = 'refs/heads/candidate/primer-cobro-r035-atomic-clean-20261106'
BASE = 'review-base/primer-cobro-r026-preincident-20261106'
RULESET_NAME = 'RIO_PRIMER_COBRO_CANDIDATE_R038'
BASE_RULESET_NAME = 'RIO_PRIMER_COBRO_REVIEW_BASE_R038'
BASE_REF = 'refs/heads/' + BASE
BASE_SHA = '5ee14ce6ca1a7e76a23d94e9804dabd4911f88dc'
APP_ID = 15368  # GitHub Actions, verified from actual GitHub check-runs
CHECKS = ('verify', 'strict-torch', 'independent-history')
RULESET_CHECKS = CHECKS + ('r038-policy-hold',)
PIN = re.compile(r'^[0-9a-f]{40}$')

class GateError(ValueError):
    pass


def no_duplicate_json_keys(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise GateError('DUPLICATE_JSON_KEY')
        out[key] = value
    return out


def blueprint(ref=TARGET, name=RULESET_NAME):
    return {
        'name': name, 'target': 'branch', 'enforcement': 'active',
        'bypass_actors': [],
        'conditions': {'ref_name': {'include': [ref], 'exclude': []}},
        'rules': [
            {'type': 'deletion'}, {'type': 'non_fast_forward'},
            {'type': 'pull_request', 'parameters': {
                'required_approving_review_count': 1,
                'dismiss_stale_reviews_on_push': True,
                'require_last_push_approval': True,
                'required_review_thread_resolution': True,
                'required_reviewers': [],
                'require_code_owner_review': False,
                'require_extra_approval_for_unattributed_changes': True,
                'allowed_merge_methods': ['merge', 'squash', 'rebase']}},
            {'type': 'required_status_checks', 'parameters': {
                'strict_required_status_checks_policy': True,
                'required_status_checks': [
                    {'context': name, 'integration_id': APP_ID}
                    for name in RULESET_CHECKS]}}
        ]}


def ruleset_matches(item, ref=TARGET, name=RULESET_NAME):
    if not isinstance(item, dict):
        return False
    if item.get('name') != name or item.get('target') != 'branch' or item.get('enforcement') != 'active':
        return False
    if item.get('bypass_actors') != []:
        return False
    refs = (item.get('conditions') or {}).get('ref_name') or {}
    if refs.get('include') != [ref] or refs.get('exclude') != []:
        return False
    rules = item.get('rules')
    if not isinstance(rules, list):
        return False
    bytype = {}
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get('type'), str):
            return False
        if rule['type'] in bytype:
            return False
        bytype[rule['type']] = rule.get('parameters', {})
    if not {'deletion', 'non_fast_forward', 'pull_request', 'required_status_checks'} <= set(bytype):
        return False
    review, status = bytype['pull_request'], bytype['required_status_checks']
    if not isinstance(review, dict) or not isinstance(status, dict):
        return False
    if type(review.get('required_approving_review_count')) is not int or review['required_approving_review_count'] < 1:
        return False
    if review.get('dismiss_stale_reviews_on_push') is not True or review.get('require_last_push_approval') is not True:
        return False
    if review.get('required_review_thread_resolution') is not True:
        return False
    if status.get('strict_required_status_checks_policy') is not True:
        return False
    wanted = {(name, APP_ID) for name in RULESET_CHECKS}
    checks = status.get('required_status_checks')
    if not isinstance(checks, list):
        return False
    try:
        observed = {(c['context'], c['integration_id']) for c in checks if isinstance(c, dict)
                    and isinstance(c.get('context'), str)
                    and type(c.get('integration_id')) is int}
    except (TypeError, KeyError):
        return False
    return wanted <= observed


def effective_review_state(reviews, author, head):
    """Replay all GitHub reviews by immutable numeric ID, not any historic approval.

    Requires an exhaustive paginated readback by the caller. A dismissed
    approval or subsequent CHANGES_REQUESTED overrides older APPROVED.
    """
    seen = set()
    chronological = []
    for review in reviews:
        if not isinstance(review, dict) or type(review.get('id')) is not int or review['id'] <= 0:
            raise GateError('MALFORMED_REVIEW_ID')
        if review['id'] in seen:
            raise GateError('DUPLICATE_REVIEW_ID')
        seen.add(review['id'])
        user = (review.get('user') or {}).get('login')
        state = review.get('state')
        if not isinstance(user, str) or not user.strip() or not isinstance(state, str):
            raise GateError('MALFORMED_REVIEW')
        if state not in ('APPROVED', 'CHANGES_REQUESTED', 'COMMENTED', 'DISMISSED', 'PENDING'):
            raise GateError('UNKNOWN_REVIEW_STATE')
        chronological.append((review['id'], user.casefold(), state, review.get('commit_id')))
    latest = {}
    for _, user, state, sha in sorted(chronological):
        # Commented and pending do not cancel a prior final review.
        if state not in ('COMMENTED', 'PENDING'):
            latest[user] = (state, sha)
    approved = {user for user, (state, sha) in latest.items()
                if user != author and state == 'APPROVED' and sha == head}
    outstanding = {user for user, (state, _) in latest.items() if state == 'CHANGES_REQUESTED'}
    return approved, outstanding


def evaluate(rulesets, pr, reviews, checks, head):
    if not isinstance(rulesets, list) or not isinstance(pr, dict) or not isinstance(reviews, list) or not isinstance(checks, dict):
        raise GateError('INVALID_INPUT_TYPE')
    if not isinstance(head, str) or not PIN.fullmatch(head):
        raise GateError('INVALID_HEAD_SHA')
    if len(rulesets) > 100 or len(reviews) > 500 or len(checks.get('check_runs', [])) > 1000:
        raise GateError('INPUT_OUT_OF_BOUNDS')
    if not isinstance(checks.get('check_runs'), list) or type(checks.get('total_count')) is not int:
        raise GateError('INVALID_CHECKS_SHAPE')
    reasons = []
    matched = [v for v in rulesets if ruleset_matches(v)]
    matched_base = [v for v in rulesets if ruleset_matches(v, BASE_REF, BASE_RULESET_NAME)]
    if len(matched) != 1:
        reasons.append('NO_UNIQUE_EXACT_ACTIVE_CANDIDATE_RULESET')
    if len(matched_base) != 1:
        reasons.append('NO_UNIQUE_EXACT_ACTIVE_REVIEW_BASE_RULESET')
    if (pr.get('state') != 'open' or pr.get('draft') is not False or
        pr.get('merged') is not False or
        (pr.get('head') or {}).get('ref') != TARGET.removeprefix('refs/heads/') or
        (pr.get('head') or {}).get('sha') != head or
        ((pr.get('head') or {}).get('repo') or {}).get('full_name') != REPO or
        (pr.get('base') or {}).get('ref') != BASE or
        (pr.get('base') or {}).get('sha') != BASE_SHA or
        ((pr.get('base') or {}).get('repo') or {}).get('full_name') != REPO or
        pr.get('number') != 41):
        reasons.append('PR_NOT_READY_OR_IDENTITY_MISMATCH')
    author = ((pr.get('user') or {}).get('login') or '').casefold()
    if not author:
        reasons.append('PR_AUTHOR_UNKNOWN')
    approved, outstanding = effective_review_state(reviews, author, head)
    if not approved:
        reasons.append('INDEPENDENT_REVIEW_NOT_OBSERVED')
    if outstanding:
        reasons.append('CHANGES_REQUESTED_OUTSTANDING')
    if checks['total_count'] > len(checks['check_runs']):
        reasons.append('TRUNCATED_CHECK_RUNS')
    for name in CHECKS:
        candidates = [c for c in checks['check_runs']
                      if isinstance(c, dict) and c.get('name') == name and
                      c.get('head_sha') == head and
                      (c.get('app') or {}).get('id') == APP_ID]
        if not candidates or any(c.get('status') != 'completed' or c.get('conclusion') != 'success' for c in candidates):
            reasons.append('TRUSTED_CI_NOT_ALL_SUCCESS_' + name.upper().replace('-', '_'))
    reasons = sorted(set(reasons))
    return {
        'schema': SCHEMA,
        'result': 'POLICY_AND_REVIEW_PREREQUISITES_OBSERVED' if not reasons else 'BLOCKED',
        'pr_number': 41, 'repository': REPO, 'candidate_ref': TARGET,
        'checked_head': head,
        'ruleset_contract_observed': len(matched) == 1 and len(matched_base) == 1,
        'candidate_ruleset_observed': len(matched) == 1,
        'review_base_ruleset_observed': len(matched_base) == 1,
        'approved_independent_reviewers_count': len(approved),
        'outstanding_changes_requested_count': len(outstanding),
        'review_history_complete_verified_by_parser': False,  # caller must paginate
        'workflow_source_integrity_independently_verified': False,
        'required_ci_contexts': list(CHECKS),
        'required_policy_hold_context': 'r038-policy-hold',
        'trusted_check_integration_id': APP_ID,
        'blockers': reasons,
        'github_api_provenance_authenticated_by_parser': False,
        'trusted_contact_or_identity_binding_verified': False,
        'independent_host_denial_observed': False,
        'protected_deployment_environment_verified': False,
        'historical_privacy_incident_closed': False,
        'production_authorized': False, 'payment_operations_authorized': False,
        'interpretation': 'READONLY_PREREQUISITES_NOT_RELEASE_AUTHORIZATION'
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', action='store_true', help='Print exact admin ruleset proposal; no write')
    parser.add_argument('--rulesets')
    parser.add_argument('--pr')
    parser.add_argument('--reviews')
    parser.add_argument('--checks')
    parser.add_argument('--head')
    parser.add_argument('--output')
    parser.add_argument('--require-prerequisites', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.plan:
            result = {'schema': SCHEMA, 'state': 'PLAN_ONLY_NO_ADMIN_WRITE',
                      'write_executed': False, 'rulesets': [blueprint(), blueprint(BASE_REF, BASE_RULESET_NAME)],
                      'production_authorized': False}
        else:
            if not all((args.rulesets, args.pr, args.reviews, args.checks, args.head)):
                raise GateError('MISSING_READBACK_INPUT')
            def load(path):
                return json.loads(Path(path).read_text(encoding='utf-8'),
                                  object_pairs_hook=no_duplicate_json_keys)
            result = evaluate(load(args.rulesets), load(args.pr), load(args.reviews),
                              load(args.checks), args.head)
        if args.output:
            out = Path(args.output)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result, sort_keys=True))
        if args.require_prerequisites and not (not args.plan and result['result'] == 'POLICY_AND_REVIEW_PREREQUISITES_OBSERVED'):
            return 2
        return 0
    except (GateError, ValueError, TypeError, KeyError, OSError, UnicodeError) as exc:
        print(json.dumps({'schema': SCHEMA, 'result': 'FAIL_CLOSED',
                          'error_code': str(exc)[:72], 'production_authorized': False}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
