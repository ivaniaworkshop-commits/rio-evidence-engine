"""Probe generated critical-path durations without providing reference answers."""
import hashlib,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rio_evidence.neural_lm import generate,ContextBudgetError
rows=[]
for line in (ROOT/'training/answer_matrix.jsonl').read_text().splitlines():
 c=json.loads(line)
 if c['split']!='holdout':continue
 prompt='Case: '+c['topology']+' '+json.dumps(c['durations'],sort_keys=True)+'\nAnswer: '
 try:
  output=generate(ROOT,prompt,160);rejection=None
 except ContextBudgetError as error:
  output='';rejection=str(error)
 matches=re.findall(r'taking\s+(\d+(?:\.\d+)?)\s+minutes',output)
 observed=float(matches[0]) if matches else None
 rows.append({'case_id':c['case_id'],'reference_minutes':c['reference']['critical_path_minutes'],
              'extracted_minutes':observed,'exact_numeric_match':observed==c['reference']['critical_path_minutes'],
              'generated_text':output,'context_rejection':rejection})
report={'scope':'AUTHORED_PUBLIC_SHARED_TEMPLATE_TASK_PROBE_NOT_UNSEEN_GENERALIZATION',
        'checkpoint_sha256':hashlib.sha256((ROOT/'model/byte_gru.pt').read_bytes()).hexdigest(),
        'cases':len(rows),'extractable':sum(r['extracted_minutes'] is not None for r in rows),
        'exact_numeric_matches':sum(r['exact_numeric_match'] for r in rows),
        'context_rejections':sum(r['context_rejection'] is not None for r in rows),'results':rows,
        'limits':['Extraction failure does not measure all possible semantic correctness.',
                  'Prompt format is authored, not an official competition protocol.',
                  'No reference answer is supplied in these inference prompts.']}
(ROOT/'model/TASK_CONTEXT_EVALUATION.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['cases','extractable','exact_numeric_matches']}))
