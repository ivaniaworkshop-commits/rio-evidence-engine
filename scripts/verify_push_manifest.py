#!/usr/bin/env python3
"""Read-only, opt-in pre-push guard for the full introduced Git commit chain.

Git hooks can be bypassed; server-side branch protections and CI remain required.
This command NEVER pushes, fetches, writes refs, or edits files.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from prepare_staged_manifest import git

ZERO = '0' * 40
DENIED_REMOTE_REFS = {'refs/heads/main', 'refs/heads/deploy/primer-cobro'}
MAX_COMMITS = 64
SHA = re.compile(r'[0-9a-f]{40}\Z')

MAX_BLOB_BYTES = 64 * 1024 * 1024


def committed_snapshot_batched(root, commit, digest_cache):
    """Rebuild exact committed inventory using one persistent Git batch process.

    Content hashes are cached only for the lifetime of one pre-push invocation.
    Git object IDs are used solely as byte-identity cache keys, not as truth.
    Never read files from the working tree when verifying an existing commit.
    """
    excluded = {'.git', '__pycache__', '.venv', 'output'}
    rows = git(root, 'ls-tree', '-r', '-z', '--full-tree', commit)
    entries = []
    missing = []
    pending = set()
    for row in rows.split(b'\0'):
        if not row:
            continue
        header, raw_path = row.split(b'\t', 1)
        mode, kind, oid = header.decode('ascii').split()
        path = raw_path.decode('utf-8', 'strict')
        if path == 'MANIFEST.json' or set(Path(path).parts) & excluded:
            continue
        if mode not in {'100644', '100755'} or kind != 'blob':
            raise ValueError('UNSUPPORTED_COMMITTED_ENTRY:' + path)
        entries.append((path, oid))
        if oid not in digest_cache and oid not in pending:
            missing.append(oid)
            pending.add(oid)
    if missing:
        process = subprocess.Popen(
            ['git', '-C', str(root), 'cat-file', '--batch'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        try:
            for oid in missing:
                process.stdin.write((oid + '\n').encode('ascii'))
                process.stdin.flush()
                header = process.stdout.readline().decode('ascii', 'strict').strip().split()
                if len(header) != 3 or header[0] != oid or header[1] != 'blob':
                    raise ValueError('BATCH_BLOB_IDENTITY_MISMATCH')
                size = int(header[2])
                if size < 0 or size > MAX_BLOB_BYTES:
                    raise ValueError('BATCH_BLOB_SIZE_LIMIT')
                remaining, hash_value = size, hashlib.sha256()
                while remaining:
                    chunk = process.stdout.read(min(1048576, remaining))
                    if not chunk:
                        raise ValueError('BATCH_BLOB_TRUNCATED')
                    hash_value.update(chunk)
                    remaining -= len(chunk)
                if process.stdout.read(1) != b'\n':
                    raise ValueError('BATCH_BLOB_DELIMITER_MISSING')
                digest_cache[oid] = (size, hash_value.hexdigest())
            process.stdin.close()
            if process.wait(timeout=10) != 0:
                raise ValueError('GIT_CAT_FILE_FAILED')
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()
    result = [dict(path=path, bytes=digest_cache[oid][0], sha256=digest_cache[oid][1])
              for path, oid in entries]
    result.sort(key=lambda item: item['path'])
    return (json.dumps({'scope': 'SOURCE_BYTES_NOT_TRUTH_OR_AUTHENTICITY',
                        'files': result}, indent=2) + '\n').encode('utf-8')



def verify_ref_update(root, remote, local_ref, local_sha, remote_ref, remote_sha, digest_cache=None):
    if digest_cache is None:
        digest_cache = {}
    if local_sha == ZERO:
        raise ValueError('REMOTE_DELETION_DENIED')
    if not local_ref.startswith('refs/heads/') or not remote_ref.startswith('refs/heads/'):
        raise ValueError('BRANCH_REFS_ONLY')
    if remote_ref in DENIED_REMOTE_REFS:
        raise ValueError('PROTECTED_TARGET_DENIED:' + remote_ref)
    if not SHA.fullmatch(local_sha) or not SHA.fullmatch(remote_sha):
        raise ValueError('INVALID_SHA')
    if git(root, 'rev-parse', '--verify', local_sha + '^{commit}').decode().strip() != local_sha:
        raise ValueError('LOCAL_COMMIT_UNAVAILABLE')
    if remote_sha != ZERO:
        git(root, 'rev-parse', '--verify', remote_sha + '^{commit}')
        ok = subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor',
                             remote_sha, local_sha], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
        if ok.returncode != 0:
            raise ValueError('NON_FAST_FORWARD_OR_UNAVAILABLE_REMOTE_SHA')
        base = remote_sha
    else:
        # A new branch must have an independently fetched remote main anchor.
        # Never guess its origin or treat an empty range as proof of validity.
        anchor = 'refs/remotes/' + remote + '/main'
        git(root, 'rev-parse', '--verify', anchor + '^{commit}')
        base = git(root, 'merge-base', local_sha, anchor).decode().strip()
    introduced = [x.decode('ascii') for x in git(root, 'rev-list', '--reverse',
                                                  local_sha, '^' + base).splitlines()]
    if not introduced:
        raise ValueError('NO_NEW_COMMITS_TO_VERIFY')
    if len(introduced) > MAX_COMMITS:
        raise ValueError('COMMIT_RANGE_LIMIT_EXCEEDED')
    for commit in introduced:
        try:
            actual = git(root, 'show', commit + ':MANIFEST.json')
            expected = committed_snapshot_batched(root, commit, digest_cache)
        except (OSError, ValueError, UnicodeError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise ValueError('COMMIT_MANIFEST_UNREADABLE:' + commit[:12]) from exc
        if actual != expected:
            raise ValueError('COMMIT_MANIFEST_MISMATCH:' + commit[:12])
    return len(introduced)


def verify_stream(root, remote, stream):
    if not remote or '/' in remote or remote.startswith('-'):
        raise ValueError('INVALID_REMOTE_NAME')
    result = []
    digest_cache = {}
    for line in stream:
        parts = line.strip().split()
        if len(parts) != 4:
            raise ValueError('INVALID_PRE_PUSH_LINE')
        local_ref, local_sha, remote_ref, remote_sha = parts
        count = verify_ref_update(root, remote, local_ref, local_sha,
                                  remote_ref, remote_sha, digest_cache)
        result.append({'local_ref': local_ref, 'remote_ref': remote_ref,
                       'introduced_commits_verified': count})
    if not result:
        raise ValueError('NO_REF_UPDATES')
    return {'status': 'LOCAL_PRE_PUSH_PREFLIGHT_PASS', 'refs': result,
            'push_executed': False, 'production_authorized': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--remote', required=True)
    args = parser.parse_args()
    try:
        root = Path(git(Path.cwd(), 'rev-parse', '--show-toplevel').decode().strip())
        outcome = verify_stream(root, args.remote, sys.stdin)
        print(json.dumps(outcome, sort_keys=True))
        return 0
    except (OSError, ValueError, UnicodeError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'status': 'LOCAL_PRE_PUSH_DENIED',
                          'reason': str(exc), 'push_executed': False}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
