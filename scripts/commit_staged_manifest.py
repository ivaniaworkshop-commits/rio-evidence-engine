#!/usr/bin/env python3
"""Opt-in local producer: seal staged files and commit without pushing.

Uses Git's index as authority. Never stages arbitrary source files, never
rewrites history, and checks commit parent and manifest after the commit.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from prepare_staged_manifest import git, process, staged_snapshot


class PostCommitIntegrityError(ValueError):
    """A local commit already exists, but must not be pushed or trusted."""

    def __init__(self, reason, commit):
        super().__init__(reason)
        self.commit = commit


def committed_snapshot(root, commit):
    """Independently rebuild the source inventory from actual Git commit blobs."""
    excluded = {'.git', '__pycache__', '.venv', 'output'}
    raw = git(root, 'ls-tree', '-r', '-z', '--full-tree', commit)
    files = []
    for row in raw.split(b'\0'):
        if not row:
            continue
        header, name = row.split(b'\t', 1)
        mode, object_type, blob = header.decode('ascii').split()
        path = name.decode('utf-8', 'strict')
        if path == 'MANIFEST.json' or set(Path(path).parts) & excluded:
            continue
        if object_type != 'blob' or mode not in {'100644', '100755'}:
            raise ValueError('UNSUPPORTED_COMMITTED_ENTRY:' + path)
        content = git(root, 'cat-file', 'blob', blob)
        files.append({'path': path, 'bytes': len(content),
                      'sha256': hashlib.sha256(content).hexdigest()})
    files.sort(key=lambda item: item['path'])
    return (json.dumps({'scope': 'SOURCE_BYTES_NOT_TRUTH_OR_AUTHENTICITY',
                        'files': files}, indent=2) + '\n').encode('utf-8')


def commit_staged(root, message, expected_head=None):
    root = Path(root).resolve()
    if not message or not message.strip():
        raise ValueError('EMPTY_COMMIT_MESSAGE')
    current = git(root, 'rev-parse', 'HEAD').decode().strip()
    if expected_head is not None and expected_head != current:
        raise ValueError('STALE_HEAD')
    before = git(root, 'diff', '--cached', '--name-only', '-z').split(b'\0')
    if not any(path and path != b'MANIFEST.json' for path in before):
        raise ValueError('NO_STAGED_SOURCE_DELTA')
    prepared = process(root, prepare=True)
    expected_manifest, _ = staged_snapshot(root)
    if git(root, 'show', ':MANIFEST.json') != expected_manifest:
        raise ValueError('STAGED_MANIFEST_MISMATCH')
    subprocess.run(['git', '-C', str(root), 'commit', '-m', message],
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    new_head = git(root, 'rev-parse', 'HEAD').decode().strip()
    try:
        parent = git(root, 'rev-parse', 'HEAD^').decode().strip()
        committed = git(root, 'show', 'HEAD:MANIFEST.json')
    except (OSError, subprocess.CalledProcessError, UnicodeError) as exc:
        raise PostCommitIntegrityError('POST_COMMIT_READBACK_FAILED: ' + str(exc), new_head) from exc
    if parent != current:
        raise PostCommitIntegrityError('POST_COMMIT_PARENT_CHANGED', new_head)
    if committed != expected_manifest:
        raise PostCommitIntegrityError('POST_COMMIT_MANIFEST_CHANGED', new_head)
    # Hooks or concurrent writers can alter the Git index during git commit.
    # A matching MANIFEST alone does not prove the committed tree matches it.
    try:
        actual_tree_manifest = committed_snapshot(root, new_head)
    except (ValueError, UnicodeError, subprocess.CalledProcessError) as exc:
        raise PostCommitIntegrityError('POST_COMMIT_TREE_UNVERIFIABLE: ' + str(exc), new_head) from exc
    if actual_tree_manifest != committed:
        raise PostCommitIntegrityError('POST_COMMIT_TREE_MANIFEST_MISMATCH', new_head)
    return {'status': 'LOCAL_COMMIT_READBACK_PASS', 'parent': parent,
            'commit': new_head, 'files': prepared['files'],
            'push': False, 'scope': 'LOCAL_INDEX_AND_COMMIT_ONLY'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--message', required=True)
    parser.add_argument('--expected-head', default=None)
    args = parser.parse_args()
    try:
        print(json.dumps(commit_staged(Path(__file__).resolve().parents[1],
                                       args.message, args.expected_head), sort_keys=True))
        return 0
    except PostCommitIntegrityError as exc:
        print(json.dumps({'status': 'POST_COMMIT_INVALID_LOCAL_COMMIT',
                          'reason': str(exc), 'commit': exc.commit,
                          'push': False, 'manual_review_required': True}), file=sys.stderr)
        return 2
    except (OSError, ValueError, subprocess.CalledProcessError, UnicodeError) as exc:
        print(json.dumps({'status': 'FAIL_CLOSED', 'reason': str(exc)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
