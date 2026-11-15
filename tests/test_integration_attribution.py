"""Integration evidence is source-bound, not a combined-suite certificate."""
import json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class IntegrationAttribution(unittest.TestCase):
    def test_sources_and_receipts(self):
        x=json.loads((ROOT/'VALIDATION.json').read_text())['integration_candidate']
        self.assertEqual(x['source_base'],'e85b1e808081510a8267457c9b4aafeca064cb36')
        self.assertEqual([x['components'][s]['head'] for s in ('p43','p45','p46')],['8c0134de3d2fd5d5e310c71b3feb4999d64b87c5','ed5a15d0186923304481ca7b69a9f455386cb04a','35f176cb946b78487412d7757c8cc6a4a646c8d8'])
        self.assertEqual([x['components'][s]['historical_tests'] for s in ('p43','p45','p46')],[252,250,251])
        self.assertEqual(x['combined_suite_status'],'NOT_EXECUTED_IN_SOURCE_RECEIPT')
        self.assertFalse(x['runtime_active'] or x['independence_verified'])
    def test_precompute_package_revision(self):
        v=json.loads((ROOT/'VALIDATION.json').read_text())['public_precompute']
        p=json.loads((ROOT/'runtime/PUBLIC_PRECOMPUTE.json').read_text())
        self.assertEqual(p['source_revision'],v['validated_source_revision'])
        self.assertEqual(p['source_data_sha256'],v['public_dev_sha256'])
    def test_dashboard_has_separate_component_evidence(self):
        v=json.loads((ROOT/'VALIDATION.json').read_text())
        d=json.loads((ROOT/'DELTAS.json').read_text())
        self.assertEqual(d,json.loads((ROOT/'docs/data.json').read_text()))
        self.assertEqual(d['dashboard_release'],v['dashboard_release'])
        self.assertEqual(d['integration_candidate'],v['integration_candidate'])
        self.assertEqual(d['tests_scope'],'PR46_HISTORICAL_COMPONENT_NOT_COMBINED')

    def test_regeneration_preserves_component_attribution(self):
        """Run both generators in a disposable source copy, never mutate checkout."""
        import shutil,subprocess,sys,tempfile
        with tempfile.TemporaryDirectory(prefix='rio-tri-pr-regen-') as temp:
            target=Path(temp)/'source'
            shutil.copytree(ROOT,target,ignore=shutil.ignore_patterns('.git','.venv','__pycache__','output'))
            for script in ('scripts/sync_model_description.py','scripts/refresh_snapshot.py'):
                completed=subprocess.run([sys.executable,script],cwd=target,
                                         capture_output=True,text=True,timeout=45)
                self.assertEqual(completed.returncode,0,(script,completed.stdout,completed.stderr))
            v=json.loads((target/'VALIDATION.json').read_text())
            d=json.loads((target/'model/DESCRIPTION.json').read_text())
            snapshot=json.loads((target/'DELTAS.json').read_text())
            self.assertEqual(snapshot,json.loads((target/'docs/data.json').read_text()))
            self.assertEqual(d['integration_candidate'],v['integration_candidate'])
            self.assertEqual(d['current_strict_verification']['scope'],'PR46_HISTORICAL_COMPONENT_NOT_COMBINED')
            self.assertEqual(d['dashboard_source_verification']['source_commit'],
                             v['dashboard_release']['source_commit'])
            self.assertEqual(d['public_precompute_source_verification']['validated_source_revision'],
                             v['public_precompute']['validated_source_revision'])
            self.assertEqual(snapshot['tests_scope'],'PR46_HISTORICAL_COMPONENT_NOT_COMBINED')
            self.assertEqual(snapshot['dashboard_release'],v['dashboard_release'])
            self.assertEqual(snapshot['integration_candidate'],v['integration_candidate'])
