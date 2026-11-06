#!/usr/bin/env python3
"""Opt-in local producer: seal staged files and commit without pushing.

Uses Git's index as authority. Never stages arbitrary source files, never
rewrites history, and checks commit parent and manifest after the commit.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from prepare_staged_manifest import git, process, staged_snapshot


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
    parent = git(root, 'rev-parse', 'HEAD^').decode().strip()
    if parent != current:
        raise ValueError('POST_COMMIT_PARENT_CHANGED')
    committed = git(root, 'show', 'HEAD:MANIFEST.json')
    if committed != expected_manifest:
        raise ValueError('POST_COMMIT_MANIFEST_CHANGED')
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
    except (OSError, ValueError, subprocess.CalledProcessError, UnicodeError) as exc:
        print(json.dumps({'status': 'FAIL_CLOSED', 'reason': str(exc)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
