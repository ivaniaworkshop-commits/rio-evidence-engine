import hashlib,json,unittest
from rio_evidence.atomic_runtime import WarmRuntime,affected,atomic_matrices,canonical_bytes
from rio_evidence.autoround import priority

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
