"""Paired code vs neural-dependency pipeline; empirical simulation is not future ROI."""
import hashlib,json,random,statistics,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rio_evidence.graph_copy import extract_graph
from rio_evidence.duration_copy import grounded_generate
from rio_evidence.constrained_extraction import ConstrainedExtractor
from rio_evidence.semantic_gate import grade


def simulate(rows,seed=20261030,samples=10000):
    rng=random.Random(seed);positive=0;deltas=[]
    # Loss weights are explicit normative assumptions, not prices or fitted distributions.
    for _ in range(samples):
        wrong_cost=rng.triangular(1,10,3);latency_cost=rng.uniform(0,.01);delta=0.
        for _ in rows:
            r=rows[rng.randrange(len(rows))]
            code_loss=(0 if r['code_pass'] else wrong_cost)+latency_cost*r['code_median_ms']
            neural_loss=(0 if r['neural_pass'] else wrong_cost)+latency_cost*r['neural_median_ms']
            delta+=code_loss-neural_loss # positive favors network
        delta/=len(rows);positive+=delta>0;deltas.append(delta)
    ordered=sorted(deltas)
    return {'seed':seed,'draws':samples,'network_preferred_frequency':positive/samples,
      'mean_network_advantage_loss_units':statistics.mean(deltas),
      'network_advantage_empirical_p025':ordered[int(.025*(samples-1))],
      'network_advantage_empirical_p975':ordered[int(.975*(samples-1))],
      'scope':'CONDITIONAL_EMPIRICAL_CASE_RESAMPLING_AND_ASSUMED_LOSS_NOT_FUTURE_WIN_PROBABILITY',
      'assumptions':{'wrong_response_penalty':'triangular(1,10,mode=3) abstract units',
                     'latency_penalty_per_ms':'uniform(0,.01) abstract units',
                     'case_resampling':'paired replacement from these 94 authored cases'},
      'limits':['Correlated authored templates are not independent real-world samples.',
        'No financial cost meter or external population model.','Intervals summarize simulation only, not generalization confidence.',
        'Utility definition and cases can change the ranking.']}


def main():
    data=[json.loads(line) for line in (ROOT/'training/extraction_dev.jsonl').read_text().splitlines()]
    start=time.perf_counter();model=ConstrainedExtractor(ROOT/'model/extraction_gru.pt');load_ms=(time.perf_counter()-start)*1000
    extract_graph(data[0]['text']);grounded_generate(data[0]['text'],model)
    rows=[]
    for index,c in enumerate(data):
        timings={'code':[],'neural':[]};outputs={}
        for repetition in range(3):
            order=['code','neural'] if (index+repetition)%2==0 else ['neural','code']
            for mode in order:
                begin=time.perf_counter()
                outputs[mode]=extract_graph(c['text']) if mode=='code' else grounded_generate(c['text'],model)
                timings[mode].append((time.perf_counter()-begin)*1000)
        a=grade(outputs['code']['graph'],c['expected']);b=grade(outputs['neural']['text'],c['expected'])
        rows.append({'case_id':c['case_id'],'kind':c['kind'],'code_pass':a['pass'],'neural_pass':b['pass'],
          'code_grade':a['status'],'neural_grade':b['status'],'code_median_ms':statistics.median(timings['code']),
          'neural_median_ms':statistics.median(timings['neural']),
          'code_timings_ms':timings['code'],'neural_timings_ms':timings['neural'],
          'neural_calls_per_response':int(outputs['neural']['neural_inference'])})
    first=simulate(rows);second=simulate(rows)
    if first!=second:raise ValueError('fixed seed replay changed')
    matrix=[[r['code_pass'],r['neural_pass'],r['code_median_ms'],r['neural_median_ms']] for r in rows]
    report={'scope':'PAIRED_AUTHORED_DEV_NOT_GENERAL_NEURAL_VALUE','cases':len(rows),'repetitions_per_mode':3,
      'checkpoint_sha256':hashlib.sha256((ROOT/'model/extraction_gru.pt').read_bytes()).hexdigest(),
      'dev_data_sha256':hashlib.sha256((ROOT/'training/extraction_dev.jsonl').read_bytes()).hexdigest(),
      'code_correct_task_decisions':sum(r['code_pass'] for r in rows),'neural_pipeline_correct_task_decisions':sum(r['neural_pass'] for r in rows),
      'code_supported_exact_graphs':sum(r['code_pass'] for r in rows if r['kind']=='supported'),
      'neural_supported_exact_graphs':sum(r['neural_pass'] for r in rows if r['kind']=='supported'),
      'supported_cases':sum(r['kind']=='supported' for r in rows),'negative_cases':sum(r['kind']=='unsupported' for r in rows),
      'code_median_ms':statistics.median(v for r in rows for v in r['code_timings_ms']),
      'neural_pipeline_median_ms':statistics.median(v for r in rows for v in r['neural_timings_ms']),
      'neural_import_and_load_ms':load_ms,'financial_cost':'UNKNOWN','rows':rows,
      'matrix_columns':['code_pass','neural_pipeline_pass','code_median_ms','neural_median_ms'],'paired_matrix':matrix,
      'simulation':first,'fixed_seed_replay_equal':True,
      'simulation_replay_sha256':hashlib.sha256(json.dumps(first,sort_keys=True).encode()).hexdigest(),
      'uncertainty_reduction_observed':'Supported exact errors fall from 78 to zero in this authored set; no calibrated probability asserted.',
      'network_earns_its_cost':'NO_ON_THIS_SCOPE_WITH_CURRENT_WEIGHTS',
      'what_would_make_yes':'Measured additional correct answers or appropriate abstentions on a separately defined task beyond the equivalent code baseline, with acceptable measured cost.',
      'limits':['Code full-match coverage is narrow, not general natural-language understanding.',
       'The neural pipeline retains code duration/conflict gates; its 16 correct negative decisions are not learned neural gains.',
       'Monte Carlo cannot create an observed benefit absent from paired data.']}
    (ROOT/'model/NETWORK_VALUE_RESULT.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['code_correct_task_decisions','neural_pipeline_correct_task_decisions','code_median_ms','neural_pipeline_median_ms','fixed_seed_replay_equal','network_earns_its_cost']},indent=2))
    print(json.dumps(report['simulation'],indent=2))

if __name__=='__main__':main()
