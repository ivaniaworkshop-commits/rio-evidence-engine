import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from rio_evidence.core import topological_order, wilson_interval, read_events, validate_event

ROOT = Path(__file__).resolve().parents[1]

class Regressions(unittest.TestCase):
    def test_graph_rejects_ambiguous_dependency_containers(self):
        for deps in ['a', None, {}, ['a', 'a'], [True]]:
            with self.subTest(deps=deps), self.assertRaises(ValueError):
                topological_order([{'id':'a'}, {'id':'b','depends_on':deps}])

    def test_invalid_graph_shapes(self):
        for tasks in [None, {}, [None], [7]]:
            with self.subTest(tasks=tasks), self.assertRaises(ValueError):
                topological_order(tasks)

    def test_wilson_rejects_fractional_counts_and_bad_confidence(self):
        for successes,n,z in [(0.5,1,1.96),(True,1,1.96),(1,True,1.96),(1,2,-1),(1,2,float('nan'))]:
            with self.subTest(args=(successes,n,z)), self.assertRaises(ValueError):
                wilson_interval(successes,n,z)

    def test_read_rejects_unterminated_journal(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'journal';p.write_text('{}')
            with self.assertRaisesRegex(ValueError,'terminal newline'):
                read_events(p)

    def test_read_rejects_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'journal';p.write_text('{"event":{},"event":{}}\n')
            with self.assertRaisesRegex(ValueError,'duplicate JSON key'):
                read_events(p)

    def test_fractional_telemetry_count_rejected(self):
        event=dict(event_id='E1',task_id='T1',phase='TEST',status='PASS',evidence_ref='test',version='v1',calls=0.5)
        with self.assertRaises(ValueError):validate_event(event)

    def test_seeded_graphs_preserve_every_dependency(self):
        rng=random.Random(731)
        for size in range(1,65):
            tasks=[{'id':str(i),'depends_on':[str(j) for j in range(i) if rng.random()<0.1]} for i in range(size)]
            rng.shuffle(tasks)
            order=topological_order(tasks);positions={key:i for i,key in enumerate(order)}
            self.assertEqual(len(order),size)
            for task in tasks:
                for dep in task['depends_on']:self.assertLess(positions[dep],positions[task['id']])

    def run_cli(self,*args):
        return subprocess.run([sys.executable,'-m','rio_evidence',*args],cwd=ROOT,text=True,capture_output=True)

    def test_cli_schedule(self):
        result=self.run_cli('schedule','examples/schedule.json')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['minutes'],30)
        self.assertEqual(json.loads(result.stdout)['single_worker_minutes'],40)

    def test_cli_compare(self):
        result=self.run_cli('compare','examples/compare.json')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['correct_delta'],1)

    def test_cli_reports_missing_input_as_json(self):
        result=self.run_cli('schedule','examples/missing.json')
        self.assertEqual(result.returncode,2)
        self.assertIn('error',json.loads(result.stderr))

    def test_cli_verifies_empty_journal_without_claiming_truth(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'journal';p.touch()
            result=self.run_cli('verify-journal',str(p))
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout),{'events':0,'head_sha256':None,'scope':'INTERNAL_CONSISTENCY_ONLY'})

class NumericRegression(unittest.TestCase):
    def test_large_finite_latencies_have_finite_mean(self):
        from rio_evidence.core import compare_results
        a=[dict(case_id=str(i),correct=False,latency_ms=0) for i in range(2)]
        b=[dict(row,latency_ms=1e308) for row in a]
        self.assertEqual(compare_results(a,b)['mean_latency_delta_ms'],1e308)

    def test_unrepresentable_total_duration_is_rejected(self):
        from rio_evidence.core import critical_path
        with self.assertRaises(ValueError):
            critical_path([{'id':'a'},{'id':'b'}],{'a':1e308,'b':1e308})

    def test_large_latency_cli_emits_portable_json(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'input.json'
            a=[dict(case_id=str(i),correct=False,latency_ms=0) for i in range(2)]
            path.write_text(json.dumps({'baseline':a,'candidate':[dict(row,latency_ms=1e308) for row in a]}))
            r=subprocess.run([sys.executable,'-m','rio_evidence','compare',str(path)],cwd=ROOT,text=True,capture_output=True)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertNotIn('Infinity',r.stdout)
            self.assertEqual(json.loads(r.stdout)['mean_latency_delta_ms'],1e308)
