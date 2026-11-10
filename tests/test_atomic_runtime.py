import hashlib,json,unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from rio_evidence.atomic_runtime import WarmRuntime,affected,atomic_matrices,canonical_bytes
from rio_evidence.autoround import persist_rounds, priority, verify_history

TEXT=('Task A lasts 3 minutes. Prerequisites: none.\nTask B lasts 7 minutes. Prerequisites: A.\n'
      'Task C lasts 11 minutes. Prerequisites: A.\nTask D lasts 2 minutes. Prerequisites: B and C.')

class AtomicRuntimeTests(unittest.TestCase):
    def test_cache_hit_isolated_from_caller_mutation(self):
        engine=WarmRuntime('v1');a=engine.graph(TEXT);a['graph']['durations']['A']=999
        b=engine.graph(TEXT);self.assertEqual(b['graph']['durations']['A'],3)
        self.assertEqual(engine.stats()['hits'],1)
    def test_selective_invalidation_preserves_numeric_cache(self):
        engine=WarmRuntime('v1');graph=engine.graph(TEXT)['graph'];engine.schedule(graph)
        result=engine.invalidate(['duration_parser']);self.assertEqual(result['entries_invalidated'],1)
        hits=engine.hits;engine.schedule(graph);self.assertEqual(engine.hits,hits+1)
    def test_precompute_tampering_rejected(self):
        engine=WarmRuntime('v1');package={'source_revision':'v1','records':[],'records_sha256':'bad'}
        with self.assertRaises(ValueError):engine.load_public_precompute(package)
        self.assertEqual(engine.stats()['entries'],0)
    def test_precompute_invalid_provenance_is_atomic(self):
        rows=[{'text_sha256':'a','result':{},'status':'OBSERVED_PUBLIC_AUTHORED_CASE'},
              {'text_sha256':'b','result':{},'status':'UNKNOWN'}]
        package={'source_revision':'v1','records':rows,'records_sha256':hashlib.sha256(canonical_bytes(rows)).hexdigest()}
        engine=WarmRuntime('v1')
        with self.assertRaises(ValueError):engine.load_public_precompute(package)
        self.assertEqual(engine.stats()['entries'],0)
    def test_capacity_is_bounded(self):
        engine=WarmRuntime('v1',capacity=2)
        for n in [3,4,5]:engine.graph(TEXT.replace('A lasts 3','A lasts '+str(n)))
        self.assertEqual(engine.stats()['entries'],2);self.assertEqual(engine.stats()['evictions'],1)
    def test_matrix_paths_agree_with_reachability(self):
        m=atomic_matrices();ids=m['atoms'];a=ids.index('duration_parser');b=ids.index('public_precompute')
        self.assertEqual(m['A2'][a][b],1)
        self.assertIn('graph_cache',affected(['duration_parser']))
        self.assertNotIn('schedule_cache',affected(['duration_parser']))
    def test_prewarm_repeat_only_hits(self):
        engine=WarmRuntime('v1');engine.prewarm([TEXT]);misses=engine.misses
        engine.prewarm([TEXT]);self.assertEqual(engine.misses,misses)
    def test_priority_is_finite_and_rejects_invalid_inputs(self):
        self.assertGreater(priority(1,1,1,1,1,.1),priority(1,1,1,1,2,.1))
        with self.assertRaises(ValueError):priority(1,1,1,1,0,.1)

class AutomaticBoundaryTests(unittest.TestCase):
    def test_unlisted_action_is_rejected(self):
        from rio_evidence.autoround import RoundController
        controller=object.__new__(RoundController)
        with self.assertRaises(ValueError):controller.execute('RUN_ARBITRARY_COMMAND')
    def test_source_change_stops_round_before_cached_reuse(self):
        from pathlib import Path
        from unittest.mock import patch
        from rio_evidence.autoround import RoundController
        controller=object.__new__(RoundController);controller.root=Path('.');controller.revision='old'
        with patch('rio_evidence.autoround.source_fingerprint',return_value='new'):
            with self.assertRaisesRegex(ValueError,'source revision changed'):controller.run(1)

class SnapshotIsolationTests(unittest.TestCase):
    def test_matrix_metadata_cannot_mutate_global_atoms(self):
        from rio_evidence.atomic_runtime import atomic_matrices
        a=atomic_matrices();a['atoms'].clear();a['edges'].clear()
        self.assertEqual(len(atomic_matrices()['atoms']),9)
        self.assertGreater(len(atomic_matrices()['edges']),0)
    def test_old_round_report_does_not_grow_on_next_round(self):
        from pathlib import Path
        from unittest.mock import patch
        from rio_evidence.autoround import RoundController
        c=object.__new__(RoundController);c.root=Path('.');c.revision='v1';c.guard={}
        c.engine=WarmRuntime('v1');c.engine.warm=True;c.package={};c.benchmark={};c.actions=[];c.rankings=[]
        with patch('rio_evidence.autoround.source_fingerprint',return_value='v1'):
            first=c.run(1);length=len(first['rankings_recomputed']);c.run(1)
        self.assertEqual(len(first['rankings_recomputed']),length)
        self.assertEqual(length,2)


class RoundHistoryTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.latest = self.root / 'output/AUTO_ROUND.json'
        self.history = self.latest.parent / 'autoround-history'
        self.latest.parent.mkdir()
        self.previous = b'{"rounds":[]}\r\n'
        self.latest.write_bytes(self.previous)
        self.previous_sha = hashlib.sha256(self.previous).hexdigest()
        self.rounds = [{'status': 'NO_MATERIAL_DELTA'}]

    def read_receipt(self, saved):
        data = (self.root / saved['receipt']).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), saved['receipt_sha256'])
        return json.loads(data)

    def test_preserves_legacy_bytes_and_distinguishes_identical_runs(self):
        first = persist_rounds(self.root, self.rounds)
        second = persist_rounds(self.root, self.rounds)
        self.assertEqual((self.history / f'{self.previous_sha}.json').read_bytes(), self.previous)
        first_receipt = self.read_receipt(first)
        second_receipt = self.read_receipt(second)
        self.assertEqual(first_receipt['previous_sha256'], self.previous_sha)
        self.assertEqual(second_receipt['previous_sha256'], first['receipt_sha256'])
        self.assertNotEqual(first_receipt['run_id'], second_receipt['run_id'])
        self.assertEqual(second_receipt['rounds'], self.rounds)
        self.assertEqual(self.latest.read_bytes(), (self.root / second['receipt']).read_bytes())
        self.assertEqual(len(list(self.history.glob('*.json'))), 3)

    def test_conflicting_archive_keeps_both_existing_files(self):
        self.history.mkdir()
        conflict = self.history / f'{self.previous_sha}.json'
        conflict.write_bytes(b'different bytes')
        with self.assertRaisesRegex(ValueError, 'conflicts with its SHA-256'):
            persist_rounds(self.root, self.rounds)
        self.assertEqual(conflict.read_bytes(), b'different bytes')
        self.assertEqual(self.latest.read_bytes(), self.previous)

    def test_concurrent_runs_keep_every_receipt_and_predecessor(self):
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(persist_rounds, self.root, self.rounds) for _ in range(8)]
            receipts = [future.result() for future in futures]
        hashes = {saved['receipt_sha256'] for saved in receipts}
        self.assertEqual(len(hashes), 8)
        self.assertEqual(len(list(self.history.glob('*.json'))), 9)
        self.assertIn(hashlib.sha256(self.latest.read_bytes()).hexdigest(), hashes)
        for saved in receipts:
            previous = self.read_receipt(saved)['previous_sha256']
            self.assertIn(previous, hashes | {self.previous_sha})
            self.assertNotEqual(previous, saved['receipt_sha256'])

    def test_failed_latest_update_leaves_a_readable_archive(self):
        with patch.object(Path, 'replace', side_effect=OSError('simulated latest write failure')):
            with self.assertRaisesRegex(OSError, 'simulated latest write failure'):
                persist_rounds(self.root, self.rounds)
        self.assertEqual(self.latest.read_bytes(), self.previous)
        archived = list(self.history.glob('*.json'))
        self.assertEqual(len(archived), 2)
        for path in archived:
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), path.stem)

    def test_audit_keeps_forks_and_checks_an_expected_leaf(self):
        first = persist_rounds(self.root, self.rounds)
        self.latest.write_bytes(self.previous)
        second = persist_rounds(self.root, self.rounds)
        before = {path: path.read_bytes() for path in self.history.glob('*.json')}
        before[self.latest] = self.latest.read_bytes()

        expected = first['receipt_sha256']
        report = verify_history(self.root, expected_receipt=expected)
        self.assertEqual(report['status'], 'HISTORY_VERIFIED')
        self.assertEqual(report['hash_verified_receipts'], 3)
        self.assertEqual(report['legacy_bytes_only'], 1)
        self.assertEqual(report['latest_sha256'], second['receipt_sha256'])
        self.assertEqual(report['forks'], {self.previous_sha: sorted([expected, second['receipt_sha256']])})
        self.assertEqual({path: path.read_bytes() for path in before}, before)

        (self.root / first['receipt']).rename(self.root / 'retained-leaf.json')
        self.assertEqual(verify_history(self.root)['status'], 'HISTORY_VERIFIED')
        anchored = verify_history(self.root, expected_receipt=expected)
        self.assertEqual(anchored['status'], 'HOLD')
        self.assertEqual(anchored['issues'], [{'code': 'EXPECTED_RECEIPT_MISSING', 'sha256': expected}])

    def test_audit_reports_altered_bytes_and_missing_predecessor(self):
        first, second, third, fourth = [persist_rounds(self.root, self.rounds) for _ in range(4)]
        first_path = self.root / first['receipt']
        (self.root / 'retained-first.json').write_bytes(first_path.read_bytes())
        first_path.write_bytes(b'synthetic changed bytes')
        (self.root / third['receipt']).rename(self.root / 'retained-third.json')

        report = verify_history(self.root)
        self.assertEqual(report['status'], 'HOLD')
        self.assertEqual(report['latest_sha256'], fourth['receipt_sha256'])
        self.assertEqual(report['hash_verified_receipts'], 3)
        self.assertCountEqual(report['issues'], [
            {'code': 'HASH_MISMATCH', 'sha256': first['receipt_sha256']},
            {'code': 'UNVERIFIED_PREDECESSOR', 'sha256': first['receipt_sha256'], 'referenced_by': [second['receipt_sha256']]},
            {'code': 'MISSING_PREDECESSOR', 'sha256': third['receipt_sha256'], 'referenced_by': [fourth['receipt_sha256']]},
        ])
        self.assertEqual(first_path.read_bytes(), b'synthetic changed bytes')
        self.assertEqual(self.latest.read_bytes(), (self.root / fourth['receipt']).read_bytes())

    def test_audit_distinguishes_empty_history_and_unarchived_latest(self):
        empty_root = self.root / 'empty'
        self.assertEqual(verify_history(empty_root)['status'], 'NO_HISTORY')
        self.assertFalse(empty_root.exists())
        unarchived = verify_history(self.root)
        self.assertEqual(unarchived['status'], 'HOLD')
        self.assertEqual(unarchived['issues'], [{'code': 'LATEST_UNARCHIVED', 'sha256': self.previous_sha}])
        self.assertFalse(self.history.exists())

    def test_audit_rejects_ambiguous_lineage_even_if_the_hash_matches(self):
        data = b'{"rounds":[],"run_id":"fixture","recorded_at_utc":"fixture","previous_sha256":null,"previous_sha256":null}'
        digest = hashlib.sha256(data).hexdigest()
        self.history.mkdir()
        (self.history / f'{digest}.json').write_bytes(data)
        self.latest.write_bytes(data)

        report = verify_history(self.root)
        self.assertEqual(report['status'], 'HOLD')
        self.assertEqual(report['hash_verified_receipts'], 1)
        self.assertEqual([(issue['code'], issue['sha256']) for issue in report['issues']], [('INVALID_LINEAGE', digest)])

    def test_audit_holds_when_latest_changes_during_readback(self):
        persist_rounds(self.root, self.rounds)
        current = self.latest.read_bytes()
        with patch('rio_evidence.autoround._read_latest', side_effect=[current, b'new observation']):
            report = verify_history(self.root)
        self.assertEqual(report['status'], 'HOLD')
        self.assertEqual(report['issues'], [{'code': 'CONCURRENT_CHANGE'}])
