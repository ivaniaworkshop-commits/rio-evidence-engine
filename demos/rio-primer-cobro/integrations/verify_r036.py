#!/usr/bin/env python3
"""R036 independent, read-only Git ancestry/source audit. No deployment authority.

Checks the trusted R026 anchor, the immutable R035 checkpoint and *every*
subsequent commit. Does not claim to scan deleted refs, caches, forks or clones.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ANCHOR = '5ee14ce6ca1a7e76a23d94e9804dabd4911f88dc'
CHECKPOINT = '21d8f33f0c51e872e8a4f77ec9288c62feabc1c7'
CHECKPOINT_TREE = '5bb08d469e613ed8cf29affb630db882d7cb45b6'
FIXTURE = 'demos/rio-primer-cobro/tests/test_pey_r026.mjs'
FIXTURE_BLOB = '70e4972f9ae003b9a54c77e98e683d64760814f1'
SENSITIVE = (
    'demos/rio-primer-cobro/integrations/pey_evidence_r027.mjs',
    'demos/rio-primer-cobro/tests/test_pey_r027.mjs',
    'demos/rio-primer-cobro/integrations/R027_PEY_PROVIDER_RECONCILIATION.md',
    'demos/rio-primer-cobro/integrations/pey_emulated_r026.mjs',
    FIXTURE,
)
DIGITS18 = re.compile(rb'(?<![0-9])[0-9]{18}(?![0-9])')
HEX40 = re.compile(r'^[0-9a-f]{40}$')
MAX_COMMITS = 16
MAX_FILES = 1000
MAX_BYTES = 20_000_000
MAX_FILE_BYTES = 2_000_000

class AuditError(Exception):
    pass


def git(root, *args):
    p = subprocess.run(['git', '-C', str(root), *args], capture_output=True, timeout=20)
    if p.returncode:
        raise AuditError('GIT_UNAVAILABLE_OR_BAD_HISTORY')
    return p.stdout


def no_dupes(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise AuditError('DUPLICATE_JSON_KEY')
        d[k] = v
    return d


def tree_files(repo, commit):
    paths = {}
    for entry in git(repo, 'ls-tree', '-r', '-z', commit).split(b'\0'):
        if not entry:
            continue
        try:
            meta, name = entry.split(b'\t', 1)
            mode, kind, oid = meta.split(b' ')
            path = name.decode('utf-8', errors='strict')
        except (ValueError, UnicodeError):
            raise AuditError('INVALID_TREE_ENTRY') from None
        if (mode != b'100644' or kind != b'blob' or
            not path or '\\' in path or path.startswith('/') or
            any(p in ('.', '..', '') for p in path.split('/')) or path in paths):
            raise AuditError('INVALID_TREE_PATH_OR_MODE')
        paths[path] = oid.decode('ascii')
    if not 1 <= len(paths) <= MAX_FILES or 'MANIFEST.json' not in paths:
        raise AuditError('INVALID_TREE_INVENTORY')
    return paths


def verify_snapshot(repo, commit, fixture_blob=FIXTURE_BLOB, sensitive=SENSITIVE):
    tree = tree_files(repo, commit)
    try:
        manifest = json.loads(git(repo, 'show', commit + ':MANIFEST.json'),
                              object_pairs_hook=no_dupes)
        entries = manifest['files']
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise AuditError('INVALID_MANIFEST') from None
    if not isinstance(entries, list):
        raise AuditError('INVALID_MANIFEST')
    declared = {}
    for e in entries:
        if not isinstance(e, dict):
            raise AuditError('INVALID_MANIFEST_ENTRY')
        p = e.get('path')
        if not isinstance(p, str) or p == 'MANIFEST.json' or p in declared:
            raise AuditError('DUPLICATE_OR_INVALID_MANIFEST_PATH')
        if (not isinstance(e.get('bytes'), int) or isinstance(e['bytes'], bool)
            or e['bytes'] < 0 or e['bytes'] > MAX_FILE_BYTES
            or not isinstance(e.get('sha256'), str)
            or not re.fullmatch(r'[0-9a-f]{64}', e['sha256'])):
            raise AuditError('INVALID_MANIFEST_ENTRY')
        declared[p] = e
    if set(declared) != set(tree) - {'MANIFEST.json'}:
        raise AuditError('MANIFEST_TREE_MISMATCH')
    total = 0
    inspected = 0
    for path, oid in tree.items():
        if path == 'MANIFEST.json':
            continue
        data = git(repo, 'cat-file', 'blob', oid)
        total += len(data)
        if total > MAX_BYTES or len(data) > MAX_FILE_BYTES:
            raise AuditError('BYTES_OUTSIDE_BOUNDS')
        if len(data) != declared[path]['bytes'] or hashlib.sha256(data).hexdigest() != declared[path]['sha256']:
            raise AuditError('MANIFEST_SOURCE_MISMATCH')
        if path in sensitive:
            inspected += 1
            if path == FIXTURE and oid == fixture_blob:
                continue  # explicitly reviewed legacy negative test, unchanged bytes
            if DIGITS18.search(data):
                raise AuditError('SELECTED_PAYMENT_IDENTIFIER_FOUND')
    return {'inventory_files': len(declared), 'sensitive_files_scanned': inspected}


def audit(repo, anchor=ANCHOR, checkpoint=CHECKPOINT,
          checkpoint_tree=CHECKPOINT_TREE, fixture_blob=FIXTURE_BLOB,
          sensitive=SENSITIVE):
    repo = Path(repo).resolve()
    if not all(HEX40.fullmatch(x) for x in (anchor, checkpoint, checkpoint_tree)):
        raise AuditError('INVALID_PIN')
    head = git(repo, 'rev-parse', 'HEAD').decode().strip()
    for pin in (anchor, checkpoint):
        git(repo, 'cat-file', '-e', pin + '^{commit}')
        git(repo, 'merge-base', '--is-ancestor', pin, head)
    parents = git(repo, 'rev-list', '--parents', '-n', '1', checkpoint).decode().split()
    if len(parents) != 2 or parents[1] != anchor:
        raise AuditError('CHECKPOINT_NOT_DIRECT_CHILD_OF_ANCHOR')
    if git(repo, 'rev-parse', checkpoint + '^{tree}').decode().strip() != checkpoint_tree:
        raise AuditError('CHECKPOINT_TREE_MISMATCH')
    tail = git(repo, 'rev-list', '--reverse', checkpoint + '..HEAD').decode().splitlines()
    if len(tail) > MAX_COMMITS:
        raise AuditError('TOO_MANY_POST_CHECKPOINT_COMMITS')
    prior = checkpoint
    for commit in tail:
        ps = git(repo, 'rev-list', '--parents', '-n', '1', commit).decode().split()
        if len(ps) != 2 or ps[1] != prior:
            raise AuditError('NONLINEAR_HISTORY')
        prior = commit
    if prior != head:
        raise AuditError('HEAD_NOT_LINEAR')
    observations = [verify_snapshot(repo, commit, fixture_blob, sensitive)
                    for commit in [anchor, checkpoint, *tail]]
    return {
        'schema': 'RIO_R036_INDEPENDENT_GENEALOGY_AUDIT_V1',
        'status': 'PASS_BOUNDED_GIT_SOURCE_HISTORY',
        'anchor': anchor, 'checkpoint': checkpoint, 'head': head,
        'commits_since_anchor': 1 + len(tail),
        'checked_snapshots': len(observations),
        'minimum_files_per_snapshot': min(x['inventory_files'] for x in observations),
        'sensitive_file_snapshots': sum(x['sensitive_files_scanned'] for x in observations),
        'history_remediated_globally': False,
        'external_review_completed': False,
        'ruleset_verified': False,
        'production_authorized': False,
        'bank_operations': False,
        'scope': 'ANCHORED_REACHABLE_HISTORY_AND_SELECTED_PAYMENT_FILES_ONLY'
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--repo', default='.')
    p.add_argument('--output')
    a = p.parse_args()
    try:
        result = audit(a.repo)
        if a.output:
            path = Path(a.output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        print(json.dumps(result, sort_keys=True))
        return 0
    except (AuditError, OSError, ValueError, TypeError, UnicodeError, subprocess.TimeoutExpired):
        print(json.dumps({'schema': 'RIO_R036_INDEPENDENT_GENEALOGY_AUDIT_V1',
                          'status': 'FAIL_CLOSED', 'sensitive_values_logged': False,
                          'production_authorized': False}), file=sys.stderr)
        return 2

if __name__ == '__main__':
    sys.exit(main())
