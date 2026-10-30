"""Paired dev comparison: same candidate weights, different decoding only."""
import hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rio_evidence.constrained_extraction import ConstrainedExtractor
from rio_evidence.semantic_gate import grade,canonical
previous=json.loads((ROOT/'model/EXTRACTION_TRAINING_RESULT.json').read_text())
checkpoint=ROOT/'model/extraction_gru.pt'
if hashlib.sha256(checkpoint.read_bytes()).hexdigest()!=previous['candidate_checkpoint_sha256']:raise ValueError('checkpoint differs')
if hashlib.sha256((ROOT/'training/extraction_dev.jsonl').read_bytes()).hexdigest()!=previous['dev_data_sha256']:raise ValueError('dev differs')
baseline={r['case_id']:r for r in previous['dev_outputs']}
model=ConstrainedExtractor(checkpoint);rows=[];begin=time.perf_counter()
for line in (ROOT/'training/extraction_dev.jsonl').read_text().splitlines():
    case=json.loads(line);output=model.generate(case['text']);result=grade(output['text'],case['expected'])
    valid_graph=False
    if output['text']!='ABSTAIN':canonical(json.loads(output['text']));valid_graph=True
    duration_correct=0;dependency_correct=0
    if case['expected'] is not None and valid_graph:
        observed=canonical(json.loads(output['text']));expected=canonical(case['expected'])
        duration_correct=sum(observed['durations'][k]==v for k,v in expected['durations'].items())
        dependency_correct=sum(a['depends_on']==b['depends_on'] for a,b in zip(observed['tasks'],expected['tasks']))
    rows.append({'case_id':case['case_id'],'kind':case['kind'],'baseline_grade':baseline[case['case_id']]['grade'],
      'constrained_grade':result,'structurally_valid_graph':valid_graph,'duration_fields_correct':duration_correct,'dependency_sets_correct':dependency_correct,'generation':output})
if set(baseline)!={r['case_id'] for r in rows}:raise ValueError('unpaired dev')
supported=[r for r in rows if r['kind']=='supported'];negative=[r for r in rows if r['kind']=='unsupported']
report={'scope':'CODE_CONSTRAINED_DECODING_NOT_NEW_TRAINING_OR_LEARNED_SYNTAX',
 'checkpoint_sha256':previous['candidate_checkpoint_sha256'],'dev_data_sha256':previous['dev_data_sha256'],
 'cases':len(rows),'baseline_invalid_outputs':previous['invalid_outputs'],
 'constrained_invalid_outputs':sum(r['constrained_grade']['status']=='INVALID_GRAPH_OUTPUT' for r in rows),
 'structurally_valid_graphs':sum(r['structurally_valid_graph'] for r in rows),
 'constrained_abstentions':sum(r['generation']['text']=='ABSTAIN' for r in rows),
 'supported_exact_matches':sum(r['constrained_grade']['status']=='EXACT_GRAPH_MATCH' for r in supported),'supported_cases':len(supported),
 'correct_abstentions':sum(r['constrained_grade']['status']=='CORRECT_ABSTENTION' for r in negative),'negative_cases':len(negative),
 'duration_fields_correct':sum(r['duration_fields_correct'] for r in supported),'duration_fields_total':4*len(supported),
 'dependency_sets_correct':sum(r['dependency_sets_correct'] for r in supported),'dependency_sets_total':4*len(supported),
 'grammar_completions':sum(r['generation']['grammar_completed'] for r in rows),
 'elapsed_seconds':time.perf_counter()-begin,'candidate_promoted':False,'rows':rows,
 'limits':['Closed ontology A-D, integer durations 1..24, alphabetically forward edges only.',
  'Code guarantees bounded grammar completion; model chooses slots, not free JSON syntax.',
  'Semantic metrics remain exact graph/abstention comparison.','Same public dev, not hidden or independent evaluation.',
  'Original weights and failed free-generation record remain unchanged.']}
(ROOT/'model/CONSTRAINED_EXTRACTION_RESULT.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['cases','baseline_invalid_outputs','constrained_invalid_outputs','structurally_valid_graphs','constrained_abstentions','supported_exact_matches','correct_abstentions','grammar_completions','duration_fields_correct','duration_fields_total','dependency_sets_correct','dependency_sets_total']},indent=2))
