"""Complete-suite gate: dependencies mandatory, skips and empty discovery fail."""
import importlib.util,json,shutil,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def main():
    missing=[]
    if importlib.util.find_spec('torch') is None:missing.append('torch: install model/requirements-cpu.txt with this interpreter')
    if shutil.which('node') is None:missing.append('node: required for dashboard parity checks')
    for name in ('byte_gru.pt','extraction_gru.pt','weighted_extraction_gru.pt'):
        if not (ROOT/'model'/name).is_file():missing.append('checkpoint: '+name)
    if missing:
        print(json.dumps({'status':'BLOCKED_MISSING_TEST_DEPENDENCIES','missing':missing,'tests_executed':False}));return 2
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    status='PASS_NO_SKIPS' if result.testsRun>0 and result.wasSuccessful() and not result.skipped else 'FAIL_OR_SKIPPED'
    print(json.dumps({'status':status,'tests_run':result.testsRun,'failed':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped)}))
    return 0 if status=='PASS_NO_SKIPS' else 2
if __name__=='__main__':raise SystemExit(main())
