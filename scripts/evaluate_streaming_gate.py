"""Full-prompt recurrent extraction evaluation with unchanged weights."""
import hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rio_evidence.streaming import generate_streaming
from rio_evidence.semantic_gate import grade
rows=[];begin=time.perf_counter()
for line in (ROOT/'evaluation/semantic_fixture.jsonl').read_text().splitlines():
    c=json.loads(line)
    prompt=('Convert the task description to JSON with tasks and durations. Each task has id and depends_on. '
            'Return ABSTAIN if duration or dependencies are unspecified or invalid.\n'+c['text']+'\nJSON:')
    output=generate_streaming(ROOT,prompt,512)
    rows.append({'case_id':c['case_id'],'family':c['family'],'grade':grade(output['generated_untrusted_text'],c['expected']),'inference':output})
supported=[r for r in rows if r['family']!='unsupported_or_invalid'];negative=[r for r in rows if r['family']=='unsupported_or_invalid']
report={'scope':'FULL_PREFILL_INTERFACE_EVALUATION_NOT_NEW_TRAINING','cases':len(rows),
 'full_prompt_bytes_processed':sum(r['inference']['prompt_bytes']==r['inference']['processed_prompt_bytes'] for r in rows),
 'supported_exact_graph_matches':sum(r['grade']['status']=='EXACT_GRAPH_MATCH' for r in supported),
 'supported_cases':len(supported),'correct_abstentions':sum(r['grade']['status']=='CORRECT_ABSTENTION' for r in negative),
 'negative_cases':len(negative),'invalid_outputs':sum(r['grade']['status']=='INVALID_GRAPH_OUTPUT' for r in rows),
 'checkpoint_sha256':hashlib.sha256((ROOT/'model/byte_gru.pt').read_bytes()).hexdigest(),
 'elapsed_seconds':time.perf_counter()-begin,'rows':rows,
 'limits':['No weights changed.','Prefill processes all prompt bytes; hidden-state compression can still lose meaning.',
 'Public authored fixture, not organizer evaluation.','Strict 128-byte generation remains the default separate interface.']}
(ROOT/'model/STREAMING_GATE_RESULT.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['cases','full_prompt_bytes_processed','supported_exact_graph_matches','correct_abstentions','invalid_outputs']}))
