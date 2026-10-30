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

    def test_snapshot_and_delta_ledger_are_identical(self):
        self.assertEqual(json.loads((ROOT/'DELTAS.json').read_text()),json.loads((ROOT/'docs/data.json').read_text()))
