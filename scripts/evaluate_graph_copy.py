"""Exact graph/abstention evaluation of closed-pattern code, no model or training."""
import hashlib,json,statistics,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rio_evidence.graph_copy import extract_graph
from rio_evidence.semantic_gate import grade
previous=json.loads((ROOT/'model/DURATION_COPY_RESULT.json').read_text());baseline={r['case_id']:r for r in previous['rows']}
rows=[];timings=[]
for line in (ROOT/'training/extraction_dev.jsonl').read_text().splitlines():
    c=json.loads(line);values=[]
    for _ in range(5):
        start=time.perf_counter();out=extract_graph(c['text']);values.append((time.perf_counter()-start)*1000)
    timings.extend(values)
    for e in out['dependency_evidence']:
        if c['text'][e['source_start']:e['source_end']]!=e['source_text']:raise ValueError('dependency span mismatch')
    for e in out['duration_evidence']:
        if c['text'][e['number_start']:e['number_end']]!=e['number_text']:raise ValueError('duration span mismatch')
    result=grade(out['graph'],c['expected'])
    rows.append({'case_id':c['case_id'],'kind':c['kind'],'grade':result,'previous_grade':baseline[c['case_id']]['grade'],
       'result':out,'timings_ms':values})
if set(baseline)!={r['case_id'] for r in rows}:raise ValueError('unpaired cases')
supported=[r for r in rows if r['kind']=='supported'];negative=[r for r in rows if r['kind']=='unsupported']
report={'scope':'CODE_CLOSED_PATTERN_EXTRACTION_NOT_NEURAL_ACCURACY_GAIN','cases':len(rows),
 'supported_exact_graph_matches':sum(r['grade']['status']=='EXACT_GRAPH_MATCH' for r in supported),'supported_cases':len(supported),
 'correct_code_abstentions':sum(r['grade']['status']=='CORRECT_ABSTENTION' for r in negative),'negative_cases':len(negative),
 'previous_exact_graph_matches':previous['supported_exact_graph_matches'],
 'median_ms':statistics.median(timings),'timed_calls':len(timings),'neural_calls':0,'all_source_spans_matched':True,
 'dev_data_sha256':hashlib.sha256((ROOT/'training/extraction_dev.jsonl').read_bytes()).hexdigest(),'rows':rows,
 'limits':['Public authored dev and recognized wording templates, not hidden/general language evaluation.',
 'Code recovers explicit declarations; no model weights or learned semantic gain.','Abstention is not a calibrated probability.',
 'No neural uplift can be inferred from this code-only result.','Timings are local and load sensitive.']}
(ROOT/'model/GRAPH_COPY_RESULT.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['supported_exact_graph_matches','supported_cases','correct_code_abstentions','negative_cases','median_ms','neural_calls']},indent=2))
