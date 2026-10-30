"""Paired dev evaluation: source-grounded durations vs model-selected durations."""
import hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rio_evidence.duration_copy import grounded_generate
from rio_evidence.constrained_extraction import ConstrainedExtractor
from rio_evidence.semantic_gate import grade,canonical
previous=json.loads((ROOT/'model/CONSTRAINED_EXTRACTION_RESULT.json').read_text());checkpoint=ROOT/'model/extraction_gru.pt'
if hashlib.sha256(checkpoint.read_bytes()).hexdigest()!=previous['checkpoint_sha256']:raise ValueError('checkpoint differs')
baseline={r['case_id']:r for r in previous['rows']};model=ConstrainedExtractor(checkpoint);rows=[];begin=time.perf_counter()
for line in (ROOT/'training/extraction_dev.jsonl').read_text().splitlines():
    c=json.loads(line);output=grounded_generate(c['text'],model);result=grade(output['text'],c['expected'])
    for evidence in output['duration_evidence']['evidence']:
        if c['text'][evidence['number_start']:evidence['number_end']]!=evidence['number_text']:raise ValueError('source offset mismatch')
        if c['text'][evidence['source_start']:evidence['source_end']]!=evidence['source_text']:raise ValueError('source text mismatch')
    correct=0
    if c['expected'] is not None and output['text']!='ABSTAIN':
        observed=canonical(json.loads(output['text']));correct=sum(observed['durations'][k]==v for k,v in c['expected']['durations'].items())
    rows.append({'case_id':c['case_id'],'kind':c['kind'],'baseline_grade':baseline[c['case_id']]['constrained_grade'],
       'grade':result,'duration_fields_correct':correct,'output':output})
if set(baseline)!={r['case_id'] for r in rows}:raise ValueError('unpaired cases')
supported=[r for r in rows if r['kind']=='supported'];negative=[r for r in rows if r['kind']=='unsupported']
report={'scope':'CODE_DURATION_RECOVERY_PLUS_NEURAL_DEPENDENCY_SLOTS_NOT_NEW_TRAINING',
 'checkpoint_sha256':previous['checkpoint_sha256'],'dev_data_sha256':previous['dev_data_sha256'],'cases':len(rows),
 'baseline_duration_fields_correct':previous['duration_fields_correct'],'duration_fields_correct':sum(r['duration_fields_correct'] for r in supported),
 'duration_fields_total':4*len(supported),'supported_exact_graph_matches':sum(r['grade']['status']=='EXACT_GRAPH_MATCH' for r in supported),
 'supported_cases':len(supported),'correct_code_abstentions':sum(r['grade']['status']=='CORRECT_ABSTENTION' for r in negative),
 'negative_cases':len(negative),'invalid_outputs':sum(r['grade']['status']=='INVALID_GRAPH_OUTPUT' for r in rows),
 'source_span_checks':'ALL_MATCHED','elapsed_seconds':time.perf_counter()-begin,'candidate_promoted':False,'rows':rows,
 'limits':['Durations and abstention gates come from narrow code rules, not learned neural comprehension.',
 'Dependency slots remain unverified until exact-reference scoring.','Dev negatives are conflicting-duration cases; broader unsupported inputs are not established.',
 'No training or weight changes.','Public authored dev set, not independent or hidden evaluation.']}
(ROOT/'model/DURATION_COPY_RESULT.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['cases','baseline_duration_fields_correct','duration_fields_correct','duration_fields_total','supported_exact_graph_matches','supported_cases','correct_code_abstentions','negative_cases','invalid_outputs']},indent=2))
