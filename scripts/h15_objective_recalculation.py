"""Rebase-anchored objective ranking and public declared-count regression probe."""
import hashlib,json,random,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rio_evidence.candidate_v1 import extract_candidate_v1
from rio_evidence.counted_graph import extract_counted_graph
MATRIX=[
 ['independent_external_evaluation',5,5,5,4,.1,False,'External authenticated input not available'],
 ['declared_count_guard',4,4,4,2,.05,True,'Documented terminal-omission ambiguity'],
 ['new_wording_extension',4,3,4,6,.2,True,'Public development only'],
 ['more_neural_training',2,3,4,12,.6,True,'No demonstrated task gain'],
 ['more_cache_tuning',1,1,1,3,.1,True,'Repeated-input savings already measured']]
def rank(completed=(),seed=20261030,samples=10000):
    rows=[r for r in MATRIX if r[6] and r[0] not in completed];rng=random.Random(seed);wins={r[0]:0 for r in rows}
    for _ in range(samples):
        weights=[rng.uniform(.5,1.5) for _ in range(3)];scores=[]
        for _,a,u,e,c,risk,_,_ in rows:
            utility=sum(w*rng.triangular(max(0,v-1),min(5,v+1),v) for w,v in zip(weights,(a,u,e)))
            scores.append(utility*(1-risk)/rng.triangular(.7*c,1.5*c,c))
        wins[rows[max(range(len(rows)),key=lambda i:scores[i])][0]]+=1
    return {'seed':seed,'samples':samples,'completed_excluded':list(completed),'top_frequency':{k:v/samples for k,v in wins.items()}}
def run():
    positive=0;omissions=0
    for n in range(1,9):
        text='task,duration,predecessors\n'+'\n'.join(f'{k},1,none' for k in 'ABCDEFGH'[:n])
        assert extract_counted_graph(text,n)['graph']==extract_candidate_v1(text)['graph'];positive+=1
        if n>1:
            short=text.rsplit('\n',1)[0]
            assert extract_candidate_v1(short)['graph'] is not None
            assert extract_counted_graph(short,n)['graph'] is None;omissions+=1
    first=rank()
    return {'schema':'RIO_OBJECTIVE_RECALCULATION_H15','rebase_commit':'656a5cd11888597887b83ec051a4d7701f7495dc',
      'objectives':['correct_answers','uncertainty_reduction','evidence','justified_cost'],
      'columns':['candidate','accuracy_ordinal','uncertainty_ordinal','evidence_ordinal','relative_effort','assumed_risk','eligible','reason'],
      'matrix':MATRIX,'formula':'weighted(accuracy,uncertainty,evidence)*(1-risk)/effort',
      'simulation':first,'fixed_seed_replay_equal':first==rank(),
      'executed_delta':'declared_count_guard','after_execution':rank(completed=('declared_count_guard',)),
      'observed_public_development':{'complete_csv_graphs_preserved':positive,'declared_terminal_omissions_rejected':omissions},
      'frozen_h14_sha256':hashlib.sha256((ROOT/'rio_evidence/candidate_v1.py').read_bytes()).hexdigest(),
      'next_executable_delta':'new_wording_extension_with_separate_development_contract',
      'highest_external_dependency':'authenticated_independent_evaluation_not_available',
      'weights_changed':False,'model_promoted':False,
      'limits':['Judgment-driven Monte Carlo is sensitivity, not measured ROI or success probability.',
                'Authored development cases are not independent generalization evidence.',
                'Correct count cannot detect substitution, wrong durations or an incorrect caller declaration.',
                'Optional wrapper does not change H14 frozen source or registered H11 candidate.']}
if __name__=='__main__':print(json.dumps(run(),indent=2))
