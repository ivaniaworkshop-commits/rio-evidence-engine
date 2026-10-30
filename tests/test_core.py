import copy
import json
import tempfile
import unittest
from pathlib import Path

from rio_evidence.core import (WorkLimit,append_event,compare_results,critical_path,
                                 read_events,topological_order,triangular_ppf,validate_event,wilson_interval)


class FunctionalTests(unittest.TestCase):
    def test_fork_join_and_serial_work_are_distinct(self):
        tasks=[{'id':'a'},{'id':'b','depends_on':['a']},{'id':'c','depends_on':['a']},
               {'id':'d','depends_on':['b','c']}]
        result=critical_path(tasks,dict(a=3,b=8,c=5,d=2))
        self.assertEqual(result,{'minutes':13,'path':['a','b','d'],'single_worker_minutes':18})

    def test_invalid_dependency_structures(self):
        for tasks in [[{'id':'x'},{'id':'x'}],[{'id':'x','depends_on':['z']}],
                      [{'id':'x','depends_on':['y']},{'id':'y','depends_on':['x']}],[{'id':''}]]:
            with self.subTest(tasks=tasks),self.assertRaises(ValueError):topological_order(tasks)

    def test_invalid_duration_does_not_create_fake_schedule(self):
        for duration in [-1,float('nan'),True]:
            with self.subTest(duration=duration),self.assertRaises(ValueError):
                critical_path([{'id':'x'}],{'x':duration})

    def test_triangular_known_quantiles_and_degenerate_case(self):
        self.assertEqual(triangular_ppf(0,1,2,3),1)
        self.assertEqual(triangular_ppf(.5,1,2,3),2)
        self.assertEqual(triangular_ppf(1,1,2,3),3)
        self.assertEqual(triangular_ppf(.3,7,7,7),7)

    def test_invalid_triangular_inputs(self):
        for args in [(-.1,1,2,3),(.5,3,2,1),(.5,1,float('nan'),3)]:
            with self.subTest(args=args),self.assertRaises(ValueError):triangular_ppf(*args)

    def test_sampling_interval_contains_proportion(self):
        for successes in [0,5,10]:
            lo,hi=wilson_interval(successes,10)
            self.assertLessEqual(lo,successes/10+1e-15)
            self.assertGreaterEqual(hi+1e-15,successes/10)
        with self.assertRaises(ValueError):wilson_interval(0,0)

    def test_paired_delta_and_denominator(self):
        a=[{'case_id':'1','correct':False,'latency_ms':20},{'case_id':'2','correct':True,'latency_ms':10}]
        b=[{'case_id':'2','correct':True,'latency_ms':5},{'case_id':'1','correct':True,'latency_ms':15}]
        delta=compare_results(a,b)
        self.assertEqual(delta['correct_delta'],1)
        self.assertEqual(delta['mean_latency_delta_ms'],-5)
        with self.assertRaises(ValueError):compare_results(a,b[:1])
        with self.assertRaises(ValueError):compare_results(a,a+a)

    def test_unknown_credits_never_become_zero_or_work_units(self):
        budget=WorkLimit(max_units=5,reserve_units=2)
        self.assertTrue(budget.reserve(3))
        self.assertFalse(budget.reserve())
        self.assertIsNone(budget.state()['remaining_credits'])
        self.assertEqual(budget.state()['spendable_units_remaining'],0)
        self.assertEqual(budget.state()['delivery_reserve_units'],2)
        with self.assertRaises(ValueError):WorkLimit(max_units=1,reserve_units=2)

    def event(self,key='EV1'):
        return dict(event_id=key,task_id='F001',phase='PREP',status='PASS',elapsed_ms=1,
                    attempt=1,evidence_ref='evidence/test.json',version='R001',calls=0,
                    tokens_in=None,tokens_out=None,cost_usd=None)

    def test_closed_telemetry_schema_and_path_limits(self):
        validate_event(self.event())
        for extra in [{'prompt':'raw'},{'api_key':'value'},{'evidence_ref':'../outside'},
                      {'evidence_ref':'/absolute'},{'elapsed_ms':float('nan')}]:
            with self.subTest(extra=extra),self.assertRaises(ValueError):
                validate_event(dict(self.event(),**extra))

    def test_event_journal_append_readback_and_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'events.jsonl'
            append_event(path,self.event())
            append_event(path,self.event('EV2'))
            self.assertEqual(len(read_events(path)),2)
            with self.assertRaises(ValueError):append_event(path,self.event())

    def test_incomplete_journal_is_not_modified(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'events.jsonl';append_event(path,self.event())
            path.write_bytes(path.read_bytes().rstrip(b'\n'));before=path.read_bytes()
            with self.assertRaises(ValueError):append_event(path,self.event('EV2'))
            self.assertEqual(path.read_bytes(),before)

    def test_changed_bytes_do_not_pass_journal_consistency_check(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'events.jsonl';append_event(path,self.event())
            row=json.loads(path.read_text());row['event']['status']='FAIL'
            path.write_text(json.dumps(row)+'\n')
            with self.assertRaises(ValueError):read_events(path)



if __name__ == "__main__": unittest.main()
