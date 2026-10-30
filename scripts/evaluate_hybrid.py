"""Evaluate hybrid calculations against an exhaustive path oracle on authored graphs."""
from pathlib import Path
import json,sys,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rio_evidence.hybrid import solve,NeuralRanker
ranker=NeuralRanker(ROOT/'model/byte_gru.pt');cases=[]
for line in (ROOT/'training/answer_matrix.jsonl').read_text().splitlines():
 c=json.loads(line)
 if c['split']=='holdout':cases.append(c)
for i in range(16):
 cases.append({'case_id':f'NEW-DAG-{i:02d}', 'tasks':[{'id':'input'}, {'id':'left','depends_on':['input']},
  {'id':'right','depends_on':['input']},{'id':'merge','depends_on':['left','right']},
  {'id':'audit','depends_on':['left']},{'id':'finish','depends_on':['merge','audit']}],
  'durations':dict(input=2+i,left=7+i,right=19-i,merge=3,audit=11,finish=5)})
rows=[]
for c in cases:
 tasks={t['id']:t for t in c['tasks']};d=c['durations']
 def paths(k):
  deps=tasks[k].get('depends_on',[])
  return [[k]] if not deps else [p+[k] for dep in deps for p in paths(dep)]
 expected=max(sum(d[k] for k in p) for k in tasks for p in paths(k))
 r=solve(c,ranker)
 passed=r['schedule']['minutes']==expected and r['schedule']['single_worker_minutes']==sum(d.values())
 rows.append({'case_id':c['case_id'],'oracle_minutes':expected,'observed':r,'numeric_oracle_pass':passed})
report={'scope':'HYBRID_SYSTEM_NOT_NEURAL_ARITHMETIC','checkpoint_sha256':hashlib.sha256((ROOT/'model/byte_gru.pt').read_bytes()).hexdigest(),
 'authored_cases':len(rows),'numeric_oracle_passes':sum(r['numeric_oracle_pass'] for r in rows),
 'neural_ranking_observed':sum(r['observed']['selection']['status']=='NEURAL_TEMPLATE_RANKING_OBSERVED' for r in rows),
 'reference_holdout_cases':26,'new_authored_graphs':16,'rows':rows,
 'limits':['Deterministic code supplies numbers and candidate text; neural model only ranks candidates.',
 'Not comparable to prior free-generation probe as a neural learning improvement.',
 'New graphs are authored locally, not organizer hidden tests.','Prose preference is not independently evaluated.']}
(ROOT/'model/HYBRID_EVALUATION.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['authored_cases','numeric_oracle_passes','neural_ranking_observed']}))
