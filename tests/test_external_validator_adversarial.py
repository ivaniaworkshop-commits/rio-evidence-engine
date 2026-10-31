"""Adversarial technical-screen controls. Fixtures are not external evidence."""
import copy,importlib.util,json,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('external_screen',ROOT/'external_validator/validate.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
G={'tasks':[{'id':'A','depends_on':[]}],'durations':{'A':2}}
def fixture():
    cases=[];a=[];b=[]
    for i in range(40):
        positive=i<30;key=str(i);cases.append({'case_id':key,'cluster':'cluster'+str(i%5),'text':'authored fixture '+str(i),'expected':G if positive else None})
        result={'case_id':key,'kind':'GRAPH' if positive else 'ABSTAIN','graph':copy.deepcopy(G) if positive else None,'latency_ms':.01}
        b.append(copy.deepcopy(result));a.append(copy.deepcopy(result))
        if i<5:a[-1].update(kind='ABSTAIN',graph=None)
    return cases,a,b
class TechnicalScreenAdversarial(unittest.TestCase):
    def test_positive_control_can_pass_technical_screen(self):
        r=v.compare(*fixture());self.assertTrue(r['technical_screen_pass']);self.assertEqual(r['wins'],5);self.assertEqual(r['screen_blockers'],[])
    def test_baseline_crashes_cannot_create_capability_screen_pass(self):
        cases,a,b=fixture()
        for row in a[:5]:row.update(kind='RUNTIME_ERROR',graph=None)
        r=v.compare(cases,a,b);self.assertEqual(r['wins'],5);self.assertEqual(r['baseline_errors'],5)
        self.assertFalse(r['technical_screen_pass']);self.assertIn('BASELINE_EXECUTION_OR_INTERFACE_ERROR',r['screen_blockers'])
    def test_invalid_baseline_graph_blocks_screen(self):
        cases,a,b=fixture()
        for row in a[:5]:row.update(kind='GRAPH',graph={'tasks':[],'durations':{}})
        r=v.compare(cases,a,b);self.assertEqual(r['baseline_errors'],5);self.assertFalse(r['technical_screen_pass'])
    def test_candidate_runtime_error_is_not_safe_abstention(self):
        cases,a,b=fixture();b[-1].update(kind='RUNTIME_ERROR',graph=None)
        r=v.compare(cases,a,b);self.assertFalse(r['technical_screen_pass']);self.assertEqual(r['candidate_abstentions'],9);self.assertEqual(r['candidate_errors'],1)
    def test_per_case_wins_concentrated_in_one_cluster_do_not_pass(self):
        cases,a,b=fixture()
        for row in cases[:5]:row['cluster']='single_winning_cluster'
        r=v.compare(cases,a,b);self.assertEqual(r['wins'],5);self.assertEqual(r['cluster_wins'],1);self.assertFalse(r['technical_screen_pass'])
    def test_four_wins_are_below_predeclared_threshold(self):
        cases,a,b=fixture();a[4]=copy.deepcopy(b[4]);r=v.compare(cases,a,b)
        self.assertEqual(r['wins'],4);self.assertFalse(r['technical_screen_pass'])
    def test_abstention_regression_blocks_screen(self):
        cases,a,b=fixture();b[-1].update(kind='GRAPH',graph=G)
        r=v.compare(cases,a,b);self.assertEqual(r['candidate_abstentions'],9);self.assertFalse(r['technical_screen_pass'])
    def test_excess_latency_blocks_screen(self):
        cases,a,b=fixture()
        for row in b:row['latency_ms']=6.
        self.assertFalse(v.compare(cases,a,b)['technical_screen_pass'])
    def test_negative_graph_cannot_masquerade_as_abstention(self):
        cases,a,b=fixture();b[-1].update(kind='ABSTAIN',graph=G)
        r=v.compare(cases,a,b);self.assertEqual(r['candidate_errors'],1);self.assertFalse(r['technical_screen_pass'])

class WorkerFailureControls(unittest.TestCase):
    def checkout(self,parent,body):
        root=Path(parent)/'repo';root.mkdir();(root/'rio_evidence').mkdir();(root/'rio_evidence/__init__.py').write_text('')
        (root/'rio_evidence/extended_graph.py').write_text('def extract_extended_graph(text):\n'+body)
        subprocess.run(['git','-C',str(root),'init'],capture_output=True,check=True)
        subprocess.run(['git','-C',str(root),'add','.'],capture_output=True,check=True)
        subprocess.run(['git','-C',str(root),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','Authored control'],capture_output=True,check=True)
        sha=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip();return root,sha
    def test_worker_source_mutation_is_detected_after_execution(self):
        with tempfile.TemporaryDirectory() as d:
            root,sha=self.checkout(d," open(__file__,'a').write('\\n# drift')\n return {'status':'ABSTAIN','graph':None}\n")
            with self.assertRaisesRegex(ValueError,'DIRTY'):v.execute(root,sha,'h09',[{'case_id':'n','text':'fixture'}])
    def test_worker_timeout_is_not_a_successful_result(self):
        with tempfile.TemporaryDirectory() as d:
            root,sha=self.checkout(d," import time\n time.sleep(2)\n return {'status':'ABSTAIN','graph':None}\n")
            with self.assertRaises(subprocess.TimeoutExpired):v.execute(root,sha,'h09',[{'case_id':'n','text':'fixture'}],timeout=.05)
