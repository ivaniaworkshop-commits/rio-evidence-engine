"""Bind dashboard metrics to an existing local unittest execution record."""
import hashlib
import json
import re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def main():
    validation = json.loads((ROOT/'VALIDATION.json').read_text())
    checks = validation['checks']
    runs = [c for c in checks if 'unittest' in c['command']]
    if len(runs) != 1 or runs[0]['exit_code'] != 0:
        raise ValueError('one successful unittest run is required')
    log = runs[0]['stderr']
    match = re.search(r'Ran (\d+) tests?', log)
    if not match or not re.search(r'^OK$', log, re.M):
        raise ValueError('complete passing suite required; skips are not counted as passes')
    data = json.loads((ROOT/'DELTAS.json').read_text())
    if 'source_commit' in data:
        data['benchmark_source_commit'] = data.pop('source_commit')
    data['tests'] = int(match.group(1))
    data['provenance'] = {
        'core_sha256': hashlib.sha256((ROOT/'rio_evidence/core.py').read_bytes()).hexdigest(),
        'validation_sha256': hashlib.sha256((ROOT/'VALIDATION.json').read_bytes()).hexdigest(),
        'scope': 'LOCAL_EXECUTION_RECORD_BOUND_TO_SOURCE_BYTES_NOT_REMOTE_CI',
    }
    model_path = ROOT/'model/TRAINING_RESULT.json'
    if model_path.exists():
        result=json.loads(model_path.read_text())
        data['model']={k:result[k] for k in ['status','parameters','steps','initial_holdout_loss','final_holdout_loss']}
    ablation_path=ROOT/'model/MODE_ABLATION.json'
    if ablation_path.exists():
        ab=json.loads(ablation_path.read_text())
        data['ablation']={k:ab[k] for k in ['cases','comparison','warm_timings','decision']}
    semantic_path=ROOT/'model/SEMANTIC_GATE_RESULT.json'
    if semantic_path.exists():
        sem=json.loads(semantic_path.read_text())
        data['semantic_gate']={'summary':sem['summary'],'decision':sem['decision']}
    context_path=ROOT/'model/SEMANTIC_CONTEXT_GATE.json'
    if context_path.exists():
        ctx=json.loads(context_path.read_text())
        data['context_gate']={'rejections':ctx['summary']['neural']['context_rejections'],'capacity_bytes':128,'scope':'REJECTION_NOT_SEMANTIC_ABSTENTION'}
    description_path=ROOT/'model/DESCRIPTION.json'
    if description_path.exists():
        data['model_description']=json.loads(description_path.read_text())
    stream_path=ROOT/'model/STREAMING_GATE_RESULT.json'
    if stream_path.exists():
        stream=json.loads(stream_path.read_text())
        data['streaming_gate']={k:stream[k] for k in ['cases','full_prompt_bytes_processed','supported_exact_graph_matches','correct_abstentions']}
    extraction_path=ROOT/'training/EXTRACTION_DATA_AUDIT.json'
    if extraction_path.exists():
        audit=json.loads(extraction_path.read_text())
        data['extraction_data']={'status':'PREPARED_NOT_TRAINED','rows':audit['rows'],'counts':audit['counts']}
    candidate_path=ROOT/'model/EXTRACTION_TRAINING_RESULT.json'
    if candidate_path.exists():
        cand=json.loads(candidate_path.read_text())
        data['extraction_candidate']={k:cand[k] for k in ['status','steps','initial_dev_masked_loss','final_dev_masked_loss','dev_exact_graph_matches','dev_supported_cases','dev_correct_abstentions','dev_negative_cases','invalid_outputs']}
        data['extraction_data']['status']='USED_FOR_SEPARATE_CANDIDATE_NOT_PROMOTED'
    constrained_path=ROOT/'model/CONSTRAINED_EXTRACTION_RESULT.json'
    if constrained_path.exists():
        constrained=json.loads(constrained_path.read_text())
        data['constrained_candidate']={k:constrained[k] for k in ['cases','constrained_invalid_outputs','structurally_valid_graphs','supported_exact_matches','supported_cases','correct_abstentions','negative_cases','duration_fields_correct','duration_fields_total']}
    encoded = json.dumps(data, indent=2)+'\n'
    for name in ['DELTAS.json','docs/data.json']:
        (ROOT/name).write_text(encoded)

if __name__ == '__main__':
    main()
