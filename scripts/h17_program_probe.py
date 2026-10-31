"""Observe the single-program API/CLI and persistent checkpoint reuse, no promotion."""
import json,statistics,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rio_evidence.program import ReconciledProgram
TEXT='A dura 2 minutos sin requisitos. B dura 4 minutos después de A. C dura 6 minutos después de A. D dura 8 minutos y espera a B y C.'
def run():
    names=['base','extraction','weighted_extraction'];program=ReconciledProgram(allow_experimental=True)
    start=time.perf_counter_ns();records=program.prewarm(names);prewarm_ms=(time.perf_counter_ns()-start)/1e6
    identities={n:id(m) for n,m in program.models.items()};times=[];first=None
    for i in range(5):
        start=time.perf_counter_ns();result=program.run(TEXT,'spanish',names,8,4);times.append((time.perf_counter_ns()-start)/1e6)
        if first is None:first=result
        assert result['neural_observations']==first['neural_observations']
        assert result['decision']['schedule']['minutes']==16
        assert identities=={n:id(m) for n,m in program.models.items()}
    fixture=ROOT/'examples/reconciled_spanish.json'
    command=[sys.executable,'-m','rio_evidence.program',str(fixture),'--route','spanish','--all-checkpoints','--allow-experimental','--max-bytes','8']
    cli=subprocess.run(command,cwd=ROOT,capture_output=True,text=True);assert cli.returncode==0,cli.stderr
    cli_result=json.loads(cli.stdout);assert cli_result['decision']==first['decision'] and cli_result['neural_observations']==first['neural_observations']
    for row in records:row.pop('path',None)
    return {'schema':'RIO_H17_RECONCILED_PROGRAM_OBSERVATION','checkpoints':records,'prewarm_with_torch_import_ms':prewarm_ms,
      'warm_all_three_generation_8_bytes':{'repetitions':5,'median_ms':statistics.median(times),'samples_ms':times},
      'api_cli_outputs_equal':True,'same_process_models_reused':True,'same_process_neural_generation_repeat_equal':True,
      'decision':first['decision'],'neural_observations':first['neural_observations'],
      'weights_merged':False,'candidate_promoted':False,'default_changed':False,
      'limits':['One process-local load per checkpoint; not a background service.','Neural text is recorded separately and never accepted as the authoritative graph.',
                'Prewarm includes this process torch import and checkpoint validation, not full interpreter startup.',
                'No throughput, monetary cost or semantic accuracy improvement is established.']}
if __name__=='__main__':print(json.dumps(run(),indent=2))
