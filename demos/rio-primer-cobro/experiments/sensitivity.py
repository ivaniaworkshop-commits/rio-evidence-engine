"""Explicitly synthetic sensitivity model. Rates are not empirical or hackathon win probabilities."""
import csv, json, random, pathlib
N=20000;SEED=20261105;root=pathlib.Path(__file__).resolve().parents[1]
scenarios={
 'benefit_hypothesis': {'baseline_completion':0.55,'guided_delta':0.10,'label':'Hipótesis de mejora del flujo'},
 'null_effect':{'baseline_completion':0.55,'guided_delta':0.00,'label':'La guía no agrega valor'},
 'confusing_guidance':{'baseline_completion':0.55,'guided_delta':-0.08,'label':'La guía empeora por confusión'},
 'low_base_completion':{'baseline_completion':0.35,'guided_delta':0.10,'label':'Dificultad de interfaz en el proceso, no de las personas'},
 'high_base_completion':{'baseline_completion':0.85,'guided_delta':0.10,'label':'La tarea ya es sencilla sin guía'},
 'weak_gain':{'baseline_completion':0.55,'guided_delta':0.025,'label':'Beneficio pequeño'}
}
rows=[]
for idx,(key,s) in enumerate(scenarios.items()):
 rng=random.Random(SEED+idx);p0=s['baseline_completion'];p1=max(0,min(1,p0+s['guided_delta']));a=b=0
 for i in range(N):
  u=rng.random();a+=u<p0;b+=u<p1
 rows.append({'scenario':key,'label':s['label'],'n_pairs':N,'seed':SEED+idx,'baseline_model':p0,'guidance_delta_assumed':s['guided_delta'],'base_completion_synthetic':round(a/N,4),'guided_completion_synthetic':round(b/N,4),'delta_pp_synthetic':round(100*(b-a)/N,3),'type':'SYNTHETIC_NOT_USER_MEASURED'})
(root/'reports'/'sensitivity.json').write_text(json.dumps({'schema':'RIO_R010_SYNTHETIC_SENSITIVITY','assumptions':scenarios,'not_probabilities_of_real_world_benefit':True,'pairs_per_scenario':N,'results':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with (root/'reports'/'sensitivity.csv').open('w',encoding='utf-8',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
print(json.dumps(rows,ensure_ascii=False,indent=2))
