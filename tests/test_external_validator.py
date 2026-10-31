"""Authored tests of the external instrument; no independent data claim."""
import importlib.util,json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('standalone_validator',ROOT/'external_validator/validate.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
G={'tasks':[{'id':'A','depends_on':[]}],'durations':{'A':2}}
def row(expected=G):return {'case_id':'x','cluster':'c','text':'new input','expected':expected}
def bundle():return {'schema':v.SCHEMA,'provenance':{'source_ref':'AUTHORED_FIXTURE_NOT_EXTERNAL','frozen_at_utc':'2026-01-01T00:00:00Z','collected_at_utc':'2026-01-02T00:00:00Z'},'cases':[row()]}
class ExternalGraderTests(unittest.TestCase):
    def test_graph_order_normalization_and_cycle_rejection(self):
        self.assertEqual(v.graph(G),v.graph(json.loads(json.dumps(G))))
        for graph in ({'tasks':[{'id':'A','depends_on':['A']}],'durations':{'A':2}}, {'tasks':G['tasks'],'durations':{'A':True}}):
            with self.assertRaises(ValueError):v.graph(graph)
    def test_no_submitted_candidate_outputs(self):
        b=bundle();b['cases'][0]['candidate_output']=G
        with self.assertRaisesRegex(ValueError,'SUBMITTED'):v.validate_bundle(b,[])
    def test_overlap_and_duplicate_input_rejected(self):
        with self.assertRaisesRegex(ValueError,'KNOWN'):v.validate_bundle(bundle(),[' NEW  INPUT '])
        b=bundle();b['cases'].append(dict(row(),case_id='y'))
        with self.assertRaisesRegex(ValueError,'KNOWN'):v.validate_bundle(b,[])
    def test_collection_must_follow_declared_freeze(self):
        b=bundle();b['provenance']['collected_at_utc']=b['provenance']['frozen_at_utc']
        with self.assertRaises(ValueError):v.validate_bundle(b,[])
    def test_error_does_not_count_as_negative_abstention(self):
        output={'case_id':'x','kind':'RUNTIME_ERROR','graph':None,'latency_ms':1}
        self.assertFalse(v.correct(output,None));r=v.compare([row(None)],[output],[output]);self.assertFalse(r['technical_screen_pass']);self.assertEqual(r['candidate_abstentions'],0)
    def test_strict_json_rejects_duplicate_keys(self):
        with self.assertRaises(ValueError):v.loads('{"a":1,"a":2}')
    def test_no_dataset_is_blocked(self):
        r=subprocess.run([sys.executable,str(ROOT/'external_validator/validate.py')],capture_output=True,text=True)
        self.assertEqual(r.returncode,2);self.assertFalse(json.loads(r.stdout)['independence_verified'])
class FrozenWorkerTests(unittest.TestCase):
    def checkout(self,parent,name):
        root=Path(parent)/name;root.mkdir();(root/'rio_evidence').mkdir();(root/'rio_evidence/__init__.py').write_text('')
        # Fixture refuses labels and submitted outputs; runner only sends id+text.
        code="def extract_extended_graph(text):\n return {'status':'EXPLICIT_GRAPH_RECOVERED','graph':"+repr(G)+"}\n"
        (root/'rio_evidence/extended_graph.py').write_text(code)
        (root/'rio_evidence/candidate_v1.py').write_text(code.replace('extract_extended_graph','extract_candidate_v1'))
        def git(*args):return subprocess.check_output(['git','-C',str(root),*args],text=True,stderr=subprocess.DEVNULL).strip()
        git('init');git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','Authored fixture')
        return root,git('rev-parse','HEAD')
    def test_frozen_process_and_dirty_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            root,sha=self.checkout(d,'repo');out=v.execute(root,sha,'h09',[row()])
            self.assertTrue(v.correct(out[0],G));(root/'drift').write_text('untracked')
            with self.assertRaisesRegex(ValueError,'DIRTY'):v.execute(root,sha,'h09',[row()])
    def test_ignored_file_is_also_dirty(self):
        with tempfile.TemporaryDirectory() as d:
            root,sha=self.checkout(d,'repo')
            (root/'.git/info/exclude').write_text('hidden.py\n')
            (root/'hidden.py').write_text('not in frozen tree')
            with self.assertRaisesRegex(ValueError,'DIRTY'):v.frozen(root,sha)
    def test_wrong_commit_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root,sha=self.checkout(d,'repo')
            with self.assertRaisesRegex(ValueError,'MISMATCH'):v.execute(root,'0'*40,'h09',[row()])
    def test_complete_cli_private_report_and_no_independence_claim(self):
        with tempfile.TemporaryDirectory() as d:
            base,sa=self.checkout(d,'base');cand,sb=self.checkout(d,'candidate');path=Path(d)
            (path/'bundle.json').write_text(json.dumps(bundle()));(path/'known.json').write_text('["different disclosed input"]')
            command=[sys.executable,str(ROOT/'external_validator/validate.py'),'--bundle',str(path/'bundle.json'),'--known-texts',str(path/'known.json'),'--baseline-checkout',str(base),'--candidate-checkout',str(cand),'--baseline-commit',sa,'--candidate-commit',sb,'--output',str(path/'private-report.json')]
            r=subprocess.run(command,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            report=json.loads((path/'private-report.json').read_text());self.assertEqual(report['metrics']['candidate_exact'],1)
            self.assertEqual((path/'private-report.json').stat().st_mode & 0o777,0o600)
            self.assertFalse(report['independence_verified']);self.assertFalse(report['candidate_promoted']);self.assertNotIn('cases',report)
            again=subprocess.run(command,capture_output=True,text=True);self.assertEqual(again.returncode,2)
