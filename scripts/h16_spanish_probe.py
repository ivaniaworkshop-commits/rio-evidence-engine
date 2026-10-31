"""Public development comparison and seeded enumerated Spanish grammar regression."""
import hashlib,itertools,json,random,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.language_shift_probe import rows
from rio_evidence.spanish_graph import extract_spanish_graph
from rio_evidence.candidate_v1 import extract_candidate_v1
from rio_evidence.semantic_gate import canonical
from rio_evidence.core import critical_path

def run():
    records=[];wins=losses=baseline=candidate=negatives=0
    for row in rows():
        expected=canonical(row['expected']) if row['expected'] is not None else None
        b=extract_candidate_v1(row['text'])['graph']==expected
        c=extract_spanish_graph(row['text'])['graph']==expected
        wins+=c and not b;losses+=b and not c
        if expected is not None:baseline+=b;candidate+=c
        else:negatives+=c
        records.append({'case_id':row['case_id'],'family':row['family'],'baseline_correct':b,'candidate_correct':c})
    rng=random.Random(20261030);checked=0
    for _ in range(64):
        tasks=[];durations={};sentences=[]
        for i,key in enumerate('ABCD'):
            deps=[k for k in 'ABCD'[:i] if rng.random()<.5];n=rng.randint(0,1000000)
            tasks.append({'id':key,'depends_on':deps});durations[key]=n
            sentences.append(f'{key} dura {n} minutos '+('después de '+' y '.join(deps) if deps else 'sin requisitos')+'.')
        expected=canonical({'tasks':tasks,'durations':durations});plan=critical_path(tasks,durations)
        for order in itertools.permutations(sentences):
            text='\r\n'.join(order);actual=extract_spanish_graph(text)
            assert actual['graph']==expected and actual['schedule']==plan
            for e in actual['evidence']:
                assert text[e['source_start']:e['source_end']]==e['source_text']
                assert int(text[e['duration_start']:e['duration_end']])==durations[e['task_id']]
            checked+=1
    assert (baseline,candidate,negatives,wins,losses)==(5,10,12,5,0)
    return {'schema':'RIO_H16_SPANISH_DEVELOPMENT','rebase_commit':'65a692008ac4abe295e6bc327044992b6a794b89',
      'scope':'PROJECT_AUTHORED_PUBLIC_DEVELOPMENT_NOT_INDEPENDENT_EVALUATION',
      'supported_cases':40,'baseline_exact':baseline,'candidate_exact':candidate,'negative_cases':12,'candidate_correct_abstentions':negatives,
      'paired_wins':wins,'paired_losses':losses,'new_language_family':'CLOSED_SPANISH_EXPLICIT',
      'seed':20261030,'synthetic_graphs':64,'order_crlf_variants_checked':checked,'records':records,
      'frozen_h14_sha256':hashlib.sha256((ROOT/'rio_evidence/candidate_v1.py').read_bytes()).hexdigest(),
      'weights_changed':False,'candidate_promoted':False,'independent_data':False,
      'next_delta':'latency_and_rejection_coverage_audit_before_any_default_change',
      'limits':['Five public Spanish examples informed grammar design; gains are development results.',
                'Fixed A-D four-task grammar is not general Spanish understanding.',
                'Synthetic permutations are correlated and are not 1536 independent samples.',
                'Incumbent/H11 frozen registration is unchanged; opt-in route only.']}
if __name__=='__main__':print(json.dumps(run(),indent=2))
