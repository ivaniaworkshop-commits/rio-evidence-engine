"""Paired local ablation. Timing is observed; prose preference and financial cost are not."""
import hashlib,json,platform,statistics,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rio_evidence.hybrid import solve,NeuralRanker


def percentile(values,p):
    ordered=sorted(values);position=(len(ordered)-1)*p
    lo=int(position);hi=min(lo+1,len(ordered)-1)
    return ordered[lo]+(ordered[hi]-ordered[lo])*(position-lo)


def cold(mode):
    code="""import json,resource,time
from pathlib import Path
start=time.perf_counter()
from rio_evidence.hybrid import solve,NeuralRanker
case=json.loads(Path('examples/schedule.json').read_text())
ranker=NeuralRanker(Path('model/byte_gru.pt')) if MODE else None
r=solve(case,ranker)
print(json.dumps({'import_load_and_one_answer_ms':(time.perf_counter()-start)*1000,
 'peak_process_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
 'selection_status':r['selection']['status']}))""".replace('MODE',repr(mode))
    r=subprocess.run([sys.executable,'-c',code],cwd=ROOT,capture_output=True,text=True,check=True)
    return json.loads(r.stdout)


def main():
    evaluated=json.loads((ROOT/'model/HYBRID_EVALUATION.json').read_text())
    cases=[]
    for line in (ROOT/'training/answer_matrix.jsonl').read_text().splitlines():
        case=json.loads(line)
        if case['split']=='holdout':cases.append(case)
    for i in range(16):
        cases.append({'case_id':f'NEW-DAG-{i:02d}','tasks':[{'id':'input'},{'id':'left','depends_on':['input']},
          {'id':'right','depends_on':['input']},{'id':'merge','depends_on':['left','right']},
          {'id':'audit','depends_on':['left']},{'id':'finish','depends_on':['merge','audit']}],
          'durations':dict(input=2+i,left=7+i,right=19-i,merge=3,audit=11,finish=5)})
    oracle={r['case_id']:r['oracle_minutes'] for r in evaluated['rows']}
    if set(oracle)!={c['case_id'] for c in cases}:raise ValueError('evaluation cases differ')
    startup={'deterministic':[cold(False) for _ in range(3)],'neural':[cold(True) for _ in range(3)]}
    start=time.perf_counter();ranker=NeuralRanker(ROOT/'model/byte_gru.pt');load_ms=(time.perf_counter()-start)*1000
    solve(cases[0]);solve(cases[0],ranker) # warm-up excluded from measurements
    times={'deterministic':[],'neural':[]};rows=[]
    for i,c in enumerate(cases):
        measurements={'deterministic':[],'neural':[]};outputs={}
        for repetition in range(5):
            order=['deterministic','neural'] if (i+repetition)%2==0 else ['neural','deterministic']
            for mode in order:
                begin=time.perf_counter();r=solve(c,ranker if mode=='neural' else None)
                elapsed=(time.perf_counter()-begin)*1000
                measurements[mode].append(elapsed);times[mode].append(elapsed);outputs[mode]=r
        a,b=outputs['deterministic'],outputs['neural']
        rows.append({'case_id':c['case_id'],'deterministic_pass':a['schedule']['minutes']==oracle[c['case_id']] and a['schedule']['single_worker_minutes']==sum(c['durations'].values()),
         'neural_pass':b['schedule']['minutes']==oracle[c['case_id']] and b['schedule']['single_worker_minutes']==sum(c['durations'].values()),
         'schedules_equal':a['schedule']==b['schedule'],'explanations_equal':a['explanation']==b['explanation'],
         'selected_candidate':b['selection']['candidate_index'],'ranking_status':b['selection']['status'],
         'timings_ms':measurements})
    summaries={mode:{'samples':len(v),'median_ms':statistics.median(v),'p95_ms':percentile(v,.95)} for mode,v in times.items()}
    report={'scope':'PAIRED_LOCAL_SYSTEM_ABLATION_NOT_NEURAL_LEARNING_OR_HUMAN_PREFERENCE',
      'observed_at_utc':datetime.now(timezone.utc).isoformat(),'python':platform.python_version(),'platform':platform.platform(),'cases':len(cases),'repetitions_per_case':5,
      'checkpoint_sha256':hashlib.sha256((ROOT/'model/byte_gru.pt').read_bytes()).hexdigest(),
      'comparison':{'deterministic_passes':sum(r['deterministic_pass'] for r in rows),
       'neural_passes':sum(r['neural_pass'] for r in rows),'identical_schedules':sum(r['schedules_equal'] for r in rows),
       'identical_explanations':sum(r['explanations_equal'] for r in rows),
       'ranking_observed':sum(r['ranking_status']=='NEURAL_TEMPLATE_RANKING_OBSERVED' for r in rows)},
      'warm_timings':summaries,'neural_to_deterministic_median_ratio':summaries['neural']['median_ms']/summaries['deterministic']['median_ms'],
      'in_process_model_import_and_load_ms':load_ms,'cold_subprocess_runs':startup,
      'checkpoint_bytes':(ROOT/'model/byte_gru.pt').stat().st_size,'financial_cost':'UNKNOWN_NO_ACCOUNT_METER',
      'human_prose_preference':'NOT_MEASURED','rows':rows,
      'decision':'KEEP_DETERMINISTIC_DEFAULT_NEURAL_EXPERIMENTAL_OPT_IN',
      'limits':['Local hardware/load-sensitive timings; no cross-platform latency claim.',
       'RSS is the entire fresh Python process, not isolated tensor allocation; Linux KiB.',
       'Cold elapsed times include imports, model load and one response, excluding interpreter launch.',
       'Different template selection would not establish superior prose without separate evaluation.',
       'This does not measure general neural-model usefulness beyond the tested task.']}
    (ROOT/'model/MODE_ABLATION.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['comparison','warm_timings','neural_to_deterministic_median_ratio','cold_subprocess_runs','decision']},indent=2))

if __name__=='__main__':main()
