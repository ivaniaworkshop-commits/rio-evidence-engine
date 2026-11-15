"""Browser comparator parity on authored cases; Node is optional for core users."""
import hashlib
import json
import shutil
import subprocess
import unittest
from pathlib import Path
from rio_evidence.core import compare_results
ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(shutil.which('node'), 'Node required only for dashboard parity checks')
class DashboardParity(unittest.TestCase):
    def browser(self,a,b):
        program="const compare=require('./docs/compare.js');let s='';process.stdin.on('data',x=>s+=x);process.stdin.on('end',()=>{try{const [a,b]=JSON.parse(s);console.log(JSON.stringify(compare(a,b)));}catch(e){console.log(JSON.stringify({error:e.message}));}});"
        r=subprocess.run(['node','-e',program],cwd=ROOT,input=json.dumps([a,b]),text=True,capture_output=True,check=True)
        return json.loads(r.stdout)

    def test_pairing_order_and_metrics_match_python(self):
        a=[dict(case_id='a',correct=False,latency_ms=20),dict(case_id='b',correct=True,latency_ms=10)]
        b=[dict(case_id='b',correct=False,latency_ms=15),dict(case_id='a',correct=True,latency_ms=5)]
        expected=compare_results(a,b);actual=self.browser(a,b)
        for key in expected:
            if key!='scope':self.assertEqual(expected[key],actual[key])

    def test_unpaired_cases_rejected(self):
        a=[dict(case_id='a',correct=True,latency_ms=1)]
        b=[dict(case_id='b',correct=True,latency_ms=1)]
        self.assertIn('error',self.browser(a,b))

    def test_duplicates_and_extra_fields_rejected(self):
        a=[dict(case_id='a',correct=True,latency_ms=1)]
        for b in [a+a,[dict(a[0],secret='not-accepted')]]:
            with self.subTest(b=b):self.assertIn('error',self.browser(a,b))

    def browser_parse(self, raw):
        program=("const p=require('./docs/compare.js').parseStrict;let s='';"
                 "process.stdin.on('data',x=>s+=x);"
                 "process.stdin.on('end',()=>{try{p(s);console.log('ACCEPTED')}"
                 "catch(e){console.log(e.message)}});")
        result=subprocess.run(['node','-e',program],cwd=ROOT,input=raw,
                              text=True,capture_output=True,check=True)
        return result.stdout.strip()

    def test_frontend_rejects_duplicate_json_members_at_any_depth(self):
        examples=[
            '{"a":1,"a":2}',
            '{"outer":{"a":1,"\\u0061":2}}',
            '[{"case_id":"x","case_id":"y"}]',
            '{"outer":[{"a":1,"a":2}]}',
        ]
        for raw in examples:
            with self.subTest(raw=raw):
                self.assertIn('duplicate JSON key',self.browser_parse(raw))

    def test_frontend_allows_same_key_in_separate_objects(self):
        self.assertEqual(self.browser_parse('[{"a":1},{"a":2}]'),'ACCEPTED')

    def test_frontend_rejects_malformed_and_oversize_json(self):
        self.assertNotEqual(self.browser_parse('{"a":1,}'),'ACCEPTED')
        self.assertIn('1 MiB',self.browser_parse(' '*(1048576+1)))

    def test_frontend_integrates_strict_parser_for_all_json_inputs(self):
        app=(ROOT/'docs/app.js').read_text(encoding='utf-8')
        self.assertIn("rioCompare.parseStrict($('baseline').value)",app)
        self.assertIn("rioCompare.parseStrict($('candidate').value)",app)
        self.assertIn('rioCompare.parseStrict(await r.text())',app)

    def browser_raw_compare(self, raw):
        program=("const compare=require('./docs/compare.js');let s='';"
                 "process.stdin.on('data',x=>s+=x);"
                 "process.stdin.on('end',()=>{try{const [a,b]=compare.parseStrict(s);"
                 "console.log(JSON.stringify(compare(a,b)))}"
                 "catch(e){console.log(JSON.stringify({error:e.message}))}});")
        result=subprocess.run(['node','-e',program],cwd=ROOT,input=raw,
                              text=True,capture_output=True,check=True)
        return json.loads(result.stdout)

    def python_raw_compare(self, raw):
        from rio_evidence.json_io import loads
        try:
            baseline,candidate=loads(raw)
            return compare_results(baseline,candidate)
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            return {'error':str(error)}

    def test_numeric_paired_parity_for_safe_integers_rounding_and_limits(self):
        import math
        scenarios={
            'max-safe-int':[(0,9007199254740991)],
            'decimal-rounding':[(0.1,0.2),(0.2,0.3),(0.3,0.4)],
            'cancellation':[(0,1e15),(0,1),(1e15,0)],
            'subnormal':[(0,5e-324)],
            'high-finite':[(0,1e308),(0,1e308)],
            'high-cancellation':[(1e308,0),(0,1e308)],
            'negative-zero':[(0.0,-0.0)],
            'tiny-differences':[(0,1e-15),(0,2e-15),(0,3e-15)],
        }
        for name,pairs in scenarios.items():
            baseline=[dict(case_id=str(i),correct=i%2==0,latency_ms=a)
                      for i,(a,b) in enumerate(pairs)]
            candidate=[dict(case_id=str(i),correct=i%3==0,latency_ms=b)
                       for i,(a,b) in enumerate(pairs)]
            raw=json.dumps([baseline,candidate],allow_nan=False)
            with self.subTest(name=name):
                python=self.python_raw_compare(raw)
                browser=self.browser_raw_compare(raw)
                self.assertNotIn('error',python)
                self.assertNotIn('error',browser)
                for field in ('n','baseline_correct','candidate_correct','correct_delta'):
                    self.assertEqual(python[field],browser[field],(name,field))
                self.assertTrue(math.isclose(
                    python['mean_latency_delta_ms'],browser['mean_latency_delta_ms'],
                    rel_tol=1e-12,abs_tol=0), (name,python,browser))
                if name=='cancellation':
                    self.assertAlmostEqual(browser['mean_latency_delta_ms'],1/3,places=12)

    def test_numeric_rejection_parity_for_unsafe_integer_and_overflow(self):
        for token in ('9007199254740992','9007199254740993',
                      '-9007199254740992','1e309','-1e309'):
            raw=('[[{"case_id":"x","correct":true,"latency_ms":0}],'
                 '[{"case_id":"x","correct":true,"latency_ms":'+token+'}]]')
            with self.subTest(token=token):
                self.assertIn('error',self.python_raw_compare(raw))
                self.assertIn('error',self.browser_raw_compare(raw))

    def test_number_lexing_does_not_misinterpret_quoted_digits(self):
        self.assertEqual(self.browser_parse('{"payload":"9007199254740993"}'),'ACCEPTED')
        self.assertEqual(self.browser_parse('{"n":9007199254740991}'),'ACCEPTED')
        self.assertIn('unsafe JSON integer',self.browser_parse('{"n":9007199254740992}'))
        self.assertEqual(self.browser_parse('{"n":9007199254740992.0}'),'ACCEPTED')
        self.assertIn('finite binary64',self.browser_parse('{"n":1e309}'))

    def test_snapshot_and_delta_ledger_are_identical(self):
        self.assertEqual(json.loads((ROOT/'DELTAS.json').read_text()),json.loads((ROOT/'docs/data.json').read_text()))

    def test_snapshot_links_current_and_historical_suite_to_separate_evidence(self):
        snapshot = json.loads((ROOT/'docs/data.json').read_text())
        validation = json.loads((ROOT/'VALIDATION.json').read_text())
        self.assertIn('dashboard_release', validation, 'dashboard needs a source-bound release record')
        release = validation['dashboard_release']
        self.assertEqual(snapshot['dashboard_release'], release)
        self.assertEqual(snapshot['tests'], release['strict_suite']['tests_run'])
        self.assertEqual(snapshot['provenance']['core_sha256'], release['core_sha256'])
        historical = release['historical_local_suite']
        historical_bytes = (ROOT/historical['path']).read_bytes()
        self.assertEqual(hashlib.sha256(historical_bytes).hexdigest(), historical['sha256'])
        self.assertEqual(json.loads(historical_bytes)['current_suite']['tests_run'], historical['tests_run'])
        self.assertEqual(hashlib.sha256((ROOT/'docs/compare.js').read_bytes()).hexdigest(),
                         release['comparator_sha256'])

        page = (ROOT/'docs/index.html').read_text()
        repo = 'https://github.com/ivaniaworkshop-commits/rio-evidence-engine'
        current = release['main_ci']
        self.assertIn(f'{repo}/actions/runs/{current["run_id"]}/job/{current["job_id"]}#step:{current["step"]}:1', page)
        self.assertIn(f'{repo}/blob/{historical["commit"]}/{historical["path"]}', page)
