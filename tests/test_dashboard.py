"""Browser comparator parity on authored cases; Node is optional for core users."""
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

    def test_snapshot_and_delta_ledger_are_identical(self):
        self.assertEqual(json.loads((ROOT/'DELTAS.json').read_text()),json.loads((ROOT/'docs/data.json').read_text()))
