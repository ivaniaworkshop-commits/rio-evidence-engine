#!/usr/bin/env python3
"""Seal Git's staged source snapshot, not untrusted working-tree changes.

Explicit producer-side helper. CI must independently reject mismatched manifests.
No commit, push, merge, or deployment occurs here.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

EXCLUDED = {'.git', '__pycache__', '.venv', 'output'}


def git(root, *args, input_bytes=None, check=True):
    return subprocess.run(['git', '-C', str(root), *args], input=input_bytes,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          check=check).stdout


def staged_snapshot(root):
    rows = git(root, 'ls-files', '--stage', '-z').split(b'\0')
    files = []
    for row in rows:
        if not row:
            continue
        header, raw_path = row.split(b'\t', 1)
        mode, blob, stage = header.decode('ascii').split()
        if stage != '0':
            raise ValueError('UNMERGED_INDEX_ENTRY')
        path = raw_path.decode('utf-8', 'strict')
        if path == 'MANIFEST.json' or set(Path(path).parts) & EXCLUDED:
            continue
        if mode not in {'100644', '100755'}:
            raise ValueError('UNSUPPORTED_GIT_FILE_MODE:' + path)
        content = git(root, 'cat-file', 'blob', blob)
        files.append({'path': path, 'bytes': len(content),
                      'sha256': hashlib.sha256(content).hexdigest()})
    files.sort(key=lambda x: x['path'])
    return (json.dumps({'scope': 'SOURCE_BYTES_NOT_TRUTH_OR_AUTHENTICITY',
                        'files': files}, indent=2) + '\n').encode('utf-8'), len(files)


def process(root, prepare=False):
    root = Path(root).resolve()
    top = Path(git(root, 'rev-parse', '--show-toplevel').decode().strip()).resolve()
    if root != top:
        raise ValueError('NOT_REPOSITORY_ROOT')
    expected, count = staged_snapshot(root)
    if prepare:
        # Preserve any preexisting unstaged edits to the manifest.
        diff = subprocess.run(['git', '-C', str(root), 'diff', '--quiet', '--', 'MANIFEST.json'])
        if diff.returncode != 0:
            raise ValueError('UNSTAGED_MANIFEST_CHANGES')
        (root / 'MANIFEST.json').write_bytes(expected)
        git(root, 'add', '--', 'MANIFEST.json')
    try:
        actual = git(root, 'show', ':MANIFEST.json')
    except subprocess.CalledProcessError:
        raise ValueError('MANIFEST_NOT_STAGED') from None
    if actual != expected:
        raise ValueError('STAGED_MANIFEST_MISMATCH')
    return {'status': 'MANIFEST_PREPARED' if prepare else 'STAGED_MANIFEST_PASS',
            'files': count, 'scope': 'STAGED_GIT_BYTES_ONLY_NO_TRUTH_CLAIM'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare', action='store_true', help='Explicitly stage the manifest for the staged source snapshot')
    args = parser.parse_args()
    try:
        print(json.dumps(process(Path(__file__).resolve().parents[1], args.prepare), sort_keys=True))
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError, UnicodeError) as exc:
        print(json.dumps({'status': 'FAIL_CLOSED', 'reason': str(exc)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
