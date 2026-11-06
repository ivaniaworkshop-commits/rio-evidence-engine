"""Batch optimization must preserve exact byte-level behavior of original guard."""
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from commit_staged_manifest import committed_snapshot as baseline
from verify_push_manifest import committed_snapshot_batched,MAX_BLOB_BYTES
import test_verify_push_manifest as fixture

class BatchParityTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.PushGuardTests('test_valid_new_branch_push_accepted')
        self.f.setUp()
    def tearDown(self):self.f.tearDown()

    def test_binary_and_unicode_paths_match_original(self):
        for path,data in [('bin.dat',b'\x00\xff\x80binary\n'),('café.txt','Río\n'.encode('utf-8'))]:
            (self.f.repo/path).write_bytes(data)
        self.f.git('add','.')
        self.f.prepare()
        self.f.git('commit','-qm','binary-and-unicode')
        sha=self.f.git('rev-parse','HEAD').stdout.strip()
        actual=committed_snapshot_batched(self.f.repo,sha,{})
        self.assertEqual(actual,baseline(self.f.repo,sha))
        doc=json.loads(actual)
        names={e['path'] for e in doc['files']}
        self.assertIn('café.txt',names)
        self.assertEqual(next(e for e in doc['files'] if e['path']=='bin.dat')['sha256'],hashlib.sha256(b'\x00\xff\x80binary\n').hexdigest())

    def test_cache_reuses_objects_across_commits(self):
        a=self.f.make_commit('first',True)
        b=self.f.make_commit('second',True)
        cache={}
        self.assertEqual(committed_snapshot_batched(self.f.repo,a,cache),baseline(self.f.repo,a))
        size=len(cache)
        self.assertEqual(committed_snapshot_batched(self.f.repo,b,cache),baseline(self.f.repo,b))
        self.assertGreaterEqual(len(cache),size)
        self.assertEqual(committed_snapshot_batched(self.f.repo,b,cache),baseline(self.f.repo,b))

    def test_symbolic_link_is_rejected(self):
        (self.f.repo/'link').symlink_to('app.txt')
        self.f.git('add','link')
        self.f.git('-c','core.hooksPath=/dev/null','commit','-qm','symlink')
        sha=self.f.git('rev-parse','HEAD').stdout.strip()
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_COMMITTED_ENTRY'):
            committed_snapshot_batched(self.f.repo,sha,{})

    def test_artificial_blob_limit_enforced_fail_closed(self):
        self.f.make_commit('limit',True)
        sha=self.f.git('rev-parse','HEAD').stdout.strip()
        import verify_push_manifest as module
        original=module.MAX_BLOB_BYTES
        try:
            module.MAX_BLOB_BYTES=1
            with self.assertRaisesRegex(ValueError,'BATCH_BLOB_SIZE_LIMIT'):
                committed_snapshot_batched(self.f.repo,sha,{})
        finally:
            module.MAX_BLOB_BYTES=original

if __name__=='__main__':unittest.main()
