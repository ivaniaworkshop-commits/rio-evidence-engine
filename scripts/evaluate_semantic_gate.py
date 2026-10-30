"""Observe current neural capability before any training on the new task."""
import hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rio_evidence.semantic_gate import grade,rule_baseline
from rio_evidence.neural_lm import generate,ContextBudgetError
rows=[];start=time.perf_counter()
for line in (ROOT/'evaluation/semantic_fixture.jsonl').read_text().splitlines():
    case=json.loads(line)
    prompt=('Convert the task description to JSON with tasks and durations. Each task has id and depends_on. '
            'Return ABSTAIN if duration or dependencies are unspecified or invalid.\n'+case['text']+'\nJSON:')
    try:
        output=generate(ROOT,prompt,512)
        neural_result=grade(output,case['expected'])
        rejection=None
    except ContextBudgetError as error:
        output=None;rejection=str(error)
        neural_result={'status':'CONTEXT_REJECTED','pass':False}
    baseline=rule_baseline(case['text'])
    rows.append({'case_id':case['case_id'],'family':case['family'],
     'neural':neural_result,'context_rejection':rejection,'rule':grade(baseline,case['expected']),
     'raw_neural_output':output,'full_prompt_bytes':len(prompt.encode()),'effective_prompt_limit_bytes':128})
summary={}
for mode in ['neural','rule']:
    supported=[r for r in rows if r['family']!='unsupported_or_invalid'];negative=[r for r in rows if r['family']=='unsupported_or_invalid']
    summary[mode]={'exact_graph_matches':sum(r[mode]['status']=='EXACT_GRAPH_MATCH' for r in supported),
       'supported_cases':len(supported),'correct_abstentions':sum(r[mode]['status']=='CORRECT_ABSTENTION' for r in negative),
       'negative_cases':len(negative),'invalid_outputs':sum(r[mode]['status']=='INVALID_GRAPH_OUTPUT' for r in rows),
       'context_rejections':sum(r[mode]['status']=='CONTEXT_REJECTED' for r in rows)}
report={'scope':'PUBLIC_AUTHORED_PRETRAINING_TASK_GATE_NOT_HIDDEN_EVALUATION','summary':summary,'rows':rows,
 'elapsed_seconds':time.perf_counter()-start,'checkpoint_sha256':hashlib.sha256((ROOT/'model/byte_gru.pt').read_bytes()).hexdigest(),
 'fixture_sha256':hashlib.sha256((ROOT/'evaluation/semantic_fixture.jsonl').read_bytes()).hexdigest(),
 'acceptance_target_not_observed':{'exact_graph_matches_minimum':23,'supported_cases':24,'required_correct_abstentions':4,
  'required_gain_over_rule_matches':4},
 'decision':'CONTEXT_SAFETY_FIXED_TASK_CAPABILITY_BLOCKED',
 'limits':['Thresholds are design targets, not statistical proof.','Public synthetic fixture is not independent of this project.',
 'Oversized requests are explicitly rejected before inference. Context rejection is not semantic abstention.',
 'Expected graphs are never supplied to inference.','No model training is performed by this evaluator.']}
(ROOT/'model/SEMANTIC_CONTEXT_GATE.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'summary':summary,'decision':report['decision']},indent=2))
