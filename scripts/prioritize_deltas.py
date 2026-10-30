"""Assumption-driven Monte Carlo ranking; not measured ROI or win probability."""
import hashlib
import json
import random
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
# Matrix columns: practical benefit, defect evidence, learning value (ordinal 0..5),
# effort (relative units), implementation risk (0..1). All scores are judgments.
MATRIX=[
 ['strict_json',4,5,3,1,.1],
 ['private_holdout_design',4,3,5,2,.15],
 ['actual_model_training',4,1,5,12,.65],
 ['triangular_extremes',1,5,2,2,.2],
 ['individual_debrief',5,2,5,1,.05],
]

def calculate(seed=20261030,samples=20000,weights_scale=(1,1,1)):
    rng=random.Random(seed);wins=[0]*len(MATRIX);pairwise=[[0]*len(MATRIX) for _ in MATRIX]
    for _ in range(samples):
        weights=[rng.uniform(.5,1.5)*scale for scale in weights_scale]
        scores=[]
        for _,benefit,evidence,learning,effort,risk in MATRIX:
            values=[rng.triangular(max(0,v-1),min(5,v+1),v) for v in [benefit,evidence,learning]]
            cost=rng.triangular(effort*.7,effort*1.5,effort)
            scores.append(sum(w*v for w,v in zip(weights,values))*(1-risk)/cost)
        wins[max(range(len(scores)),key=lambda i:scores[i])]+=1
        for i in range(len(scores)):
            for j in range(len(scores)):
                pairwise[i][j]+=scores[i]>scores[j]
    return {'seed':seed,'samples':samples,'scope':'ASSUMPTION_SENSITIVITY_NOT_REAL_ROI_OR_WIN_PROBABILITY',
            'matrix_columns':['candidate','benefit_ordinal','defect_evidence_ordinal','learning_ordinal','effort_relative','risk_assumed'],
            'matrix':MATRIX,'formula':'weighted ordinal benefit * (1-risk) / effort',
            'top_rank_frequency':{row[0]:wins[i]/samples for i,row in enumerate(MATRIX)},
            'pairwise_greater_frequency':[[n/samples for n in row] for row in pairwise],
            'limitations':['All input distributions are judgments, not fitted empirical probabilities.',
             'Independent draws omit real-world correlations.','Ranking is sensitive to candidate selection and subjective utility.',
             'No model training, human mastery or hackathon success is predicted by this calculation.']}

if __name__=='__main__':
    first=calculate();second=calculate();assert first==second
    encoded=json.dumps(first,sort_keys=True,separators=(',',':')).encode()
    first['replay_sha256']=hashlib.sha256(encoded).hexdigest()
    first['replay_equal']=True
    first['sensitivity']={name:calculate(weights_scale=scale)['top_rank_frequency'] for name,scale in {'correctness_first':(1,3,.5),'learning_first':(.7,.3,3)}.items()}
    (ROOT/'research/DELTA_MONTE_CARLO.json').write_text(json.dumps(first,indent=2)+'\n')
    print(json.dumps({'ranking':first['top_rank_frequency'],'replay_equal':True,'sha256':first['replay_sha256']}))
