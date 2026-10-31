"""Synchronize current model descriptions from observed, versioned evidence."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def sync():
    training=json.loads((ROOT/'model/TRAINING_RESULT.json').read_text())
    validation=json.loads((ROOT/'VALIDATION.json').read_text())
    context=json.loads((ROOT/'model/SEMANTIC_CONTEXT_GATE.json').read_text())
    runs=[r for r in validation['checks'] if 'unittest' in r['command']]
    if len(runs)!=1 or runs[0]['exit_code']!=0:raise ValueError('successful test evidence required')
    match=re.search(r'Ran (\d+) tests?',runs[0]['stderr'])
    if not match:raise ValueError('test count unavailable')
    checkpoint_hash=hashlib.sha256((ROOT/'model/byte_gru.pt').read_bytes()).hexdigest()
    if checkpoint_hash!=training['checkpoint_sha256']:raise ValueError('training description does not match checkpoint')
    if context['checkpoint_sha256'] != checkpoint_hash:
        raise ValueError('context evaluation describes a different checkpoint')
    ablation=json.loads((ROOT/'model/MODE_ABLATION.json').read_text())
    ablation_current=ablation['checkpoint_sha256']==checkpoint_hash
    d={'schema':'OBSERVED_MODEL_DESCRIPTION_V1','name':'Río ByteGRU','kind':'SMALL_NEURAL_LANGUAGE_MODEL_NOT_LLM',
       'architecture':training['architecture'],'parameters':training['parameters'],'training_steps':training['steps'],
       'checkpoint_sha256':checkpoint_hash,'checkpoint_status':'TRAINED_SAVED_RELOADED',
       'free_generation_context_policy':'NONEMPTY_UTF8_PROMPT_PLUS_REQUESTED_OUTPUT_AT_MOST_128_BYTES',
       'semantic_extraction_status':'BLOCKED_BY_CONTEXT_BUDGET',
       'current_context_rejections':context['summary']['neural']['context_rejections'],
       'context_rejections_are_semantic_abstentions':False,'project_tests_passed':int(match.group(1)),
       'hybrid_role':'OPTIONAL_RANKING_OF_DETERMINISTIC_EXPLANATIONS',
       'observed_neural_value':('NO_OUTPUT_BENEFIT_IN_42_CASE_PAIRED_ABLATION' if ablation_current else 'NOT_EVALUATED_FOR_CURRENT_CHECKPOINT'),
       'historical_task_probe':'0/26 extractable durations before context safety fix',
       'historical_semantic_probe':'0/24 exact graphs before context safety fix',
       'historical_loss':{'initial':training['initial_holdout_loss'],'final':training['final_holdout_loss'],
                          'scope':'PUBLIC_SHARED_TEMPLATE_EVALUATION_NOT_TASK_ACCURACY'},
       'sources':['model/TRAINING_RESULT.json','model/SEMANTIC_CONTEXT_GATE.json','model/MODE_ABLATION.json','VALIDATION.json'],
       'limits':['No LLM, production reliability, human mastery or independent validation claimed.',
                 'Context acceptance preserves bytes, not demonstrated semantic retention.',
                 'Training metrics remain historical until actual retraining.']}
    stream_path=ROOT/'model/STREAMING_GATE_RESULT.json'
    if stream_path.exists():
        stream=json.loads(stream_path.read_text())
        if stream['checkpoint_sha256'] != checkpoint_hash:
            raise ValueError('streaming evaluation describes a different checkpoint')
        d['experimental_streaming']={k:stream[k] for k in ['cases','full_prompt_bytes_processed','supported_exact_graph_matches','supported_cases','correct_abstentions','negative_cases']}
        d['experimental_streaming']['max_prompt_bytes']=4096
        d['experimental_streaming']['max_output_bytes']=512
        d['semantic_extraction_status']='NOT_DEMONSTRATED_WITH_FULL_RECURRENT_PREFILL'
        d['sources'].append('model/STREAMING_GATE_RESULT.json')
    data_path=ROOT/'training/EXTRACTION_DATA_AUDIT.json'
    if data_path.exists():
        audit=json.loads(data_path.read_text())
        d['extraction_training_data']={'status':'PREPARED_NOT_TRAINED','rows':audit['rows'],'counts':audit['counts'],'overlap':audit['overlap']}
        d['sources'].append('training/EXTRACTION_DATA_AUDIT.json')
    candidate_path=ROOT/'model/EXTRACTION_TRAINING_RESULT.json'
    if candidate_path.exists():
        candidate=json.loads(candidate_path.read_text())
        actual=hashlib.sha256((ROOT/'model/extraction_gru.pt').read_bytes()).hexdigest()
        if actual!=candidate['candidate_checkpoint_sha256'] or candidate['base_checkpoint_sha256']!=checkpoint_hash:
            raise ValueError('candidate training evidence mismatches checkpoints')
        d['extraction_candidate']={k:candidate[k] for k in ['status','steps','parameters','initial_dev_masked_loss','final_dev_masked_loss','dev_exact_graph_matches','dev_supported_cases','dev_correct_abstentions','dev_negative_cases','invalid_outputs']}
        d['extraction_candidate']['checkpoint_sha256']=actual
        d['extraction_training_data']['status']='USED_FOR_SEPARATE_CANDIDATE_NOT_PROMOTED'
        d['sources'].append('model/EXTRACTION_TRAINING_RESULT.json')
    constrained_path=ROOT/'model/CONSTRAINED_EXTRACTION_RESULT.json'
    if constrained_path.exists():
        constrained=json.loads(constrained_path.read_text())
        if constrained['checkpoint_sha256']!=d['extraction_candidate']['checkpoint_sha256']:
            raise ValueError('constrained decoding evaluation mismatches candidate')
        d['extraction_candidate']['constrained_decoding']={k:constrained[k] for k in ['cases','constrained_invalid_outputs','structurally_valid_graphs','supported_exact_matches','supported_cases','correct_abstentions','negative_cases','duration_fields_correct','duration_fields_total','dependency_sets_correct','dependency_sets_total']}
        d['sources'].append('model/CONSTRAINED_EXTRACTION_RESULT.json')
    copied_path=ROOT/'model/DURATION_COPY_RESULT.json'
    if copied_path.exists():
        copied=json.loads(copied_path.read_text())
        if copied['checkpoint_sha256']!=d['extraction_candidate']['checkpoint_sha256']:
            raise ValueError('duration-copy evaluation mismatches candidate')
        d['extraction_candidate']['duration_copy']={k:copied[k] for k in ['cases','duration_fields_correct','duration_fields_total','supported_exact_graph_matches','supported_cases','correct_code_abstentions','negative_cases','invalid_outputs']}
        d['sources'].append('model/DURATION_COPY_RESULT.json')
    value_path=ROOT/'model/NETWORK_VALUE_RESULT.json'
    if value_path.exists():
        value=json.loads(value_path.read_text())
        if value['checkpoint_sha256']!=d['extraction_candidate']['checkpoint_sha256']:
            raise ValueError('network value evaluation mismatches candidate checkpoint')
        d['current_accuracy_first_comparison']={k:value[k] for k in ['cases','code_correct_task_decisions','neural_pipeline_correct_task_decisions','code_median_ms','neural_pipeline_median_ms','network_earns_its_cost','fixed_seed_replay_equal']}
        d['sources'].extend(['model/GRAPH_COPY_RESULT.json','model/NETWORK_VALUE_RESULT.json'])
    search_path=ROOT/'model/WEIGHT_SEARCH_RESULT.json'
    if search_path.exists():
        search=json.loads(search_path.read_text())
        if search['base_checkpoint_sha256']!=d['extraction_candidate']['checkpoint_sha256']:
            raise ValueError('weight search base mismatches candidate')
        actual=hashlib.sha256((ROOT/'model/weighted_extraction_gru.pt').read_bytes()).hexdigest()
        if actual!=search['candidate_checkpoint_sha256']:
            raise ValueError('programmed weight-search checkpoint mismatches report')
        d['weight_search_candidate']={k:search[k] for k in ['trial_count','base_train_subset_loss','best_train_subset_loss','chosen_multipliers','dev_exact_graph_matches','dev_supported_cases','dev_correct_abstentions','dev_negative_cases','invalid_outputs','candidate_promoted']}
        d['weight_search_candidate']['checkpoint_sha256']=actual
        d['sources'].append('model/WEIGHT_SEARCH_RESULT.json')
    auto_path=ROOT/'runtime/AUTO_ROUND_RESULT.json'
    if auto_path.exists():
        auto=json.loads(auto_path.read_text())
        d['runtime_support']={'status':'BOUNDED_LOCAL_ROUNDS_OBSERVED','round_statuses':[r['status'] for r in auto['rounds']], 'benchmark':auto['rounds'][0]['benchmark'], 'weight_changes':False, 'antivirus_activation':False}
        d['sources'].append('runtime/AUTO_ROUND_RESULT.json')
    h15_path=ROOT/'runtime/H15_OBJECTIVE_RECALCULATION.json'
    if h15_path.exists():
        prior=json.loads((ROOT/'model/DESCRIPTION.json').read_text())
        d['h15_declared_inventory']=prior['h15_declared_inventory']
        d['sources'].extend(['runtime/H15_OBJECTIVE_RECALCULATION.json','runtime/H15_VALIDATION.json'])
    h16_path=ROOT/'runtime/H16_SPANISH_RESULT.json'
    if h16_path.exists():
        h16=json.loads(h16_path.read_text())
        d['h16_spanish_development']={k:h16[k] for k in ['supported_cases','baseline_exact','candidate_exact','candidate_correct_abstentions','paired_wins','paired_losses','weights_changed','candidate_promoted','independent_data']}
        d['sources'].extend(['runtime/H16_SPANISH_RESULT.json','runtime/H16_VALIDATION.json'])
    strict_path=ROOT/'runtime/STRICT_TEST_REPAIR_RESULT.json'
    registry_path=ROOT/'runtime/WEIGHT_REGISTRY_RESULT.json'
    if strict_path.exists():
        current=json.loads(strict_path.read_text())['current_suite']
        d['current_strict_verification']={**current,'scope':'LOCAL_NOT_REMOTE_CI','evidence':'runtime/STRICT_TEST_REPAIR_RESULT.json'}
        d['project_tests_passed']=current['tests_run']-current['skipped']-current['failed']-current['errors']
        d['sources'].append('runtime/STRICT_TEST_REPAIR_RESULT.json')
    if registry_path.exists():
        d['weight_registry']=json.loads(registry_path.read_text())
        d['sources'].append('runtime/WEIGHT_REGISTRY_RESULT.json')
    h17_path=ROOT/'runtime/H17_RECONCILED_PROGRAM.json'
    if h17_path.exists():
        previous=json.loads((ROOT/'model/DESCRIPTION.json').read_text())
        d['h17_reconciled_program']=previous['h17_reconciled_program']
        current=json.loads((ROOT/'runtime/H17_VALIDATION.json').read_text())['current_suite']
        d['current_strict_verification']={**current,'scope':'LOCAL_NOT_REMOTE_CI','evidence':'runtime/H17_VALIDATION.json'}
        d['project_tests_passed']=current['tests_run']-current['skipped']-current['failed']-current['errors']
        d['sources'].extend(['runtime/H17_RECONCILED_PROGRAM.json','runtime/H17_REJECTION_LATENCY.json','runtime/H17_VALIDATION.json'])
    (ROOT/'model/DESCRIPTION.json').write_text(json.dumps(d,indent=2)+'\n')
    value_statement=('Optional neural ranking showed no output benefit in the paired 42-case comparison.' if ablation_current else 'The current checkpoint has no matching paired utility evaluation.')
    block=('<!-- MODEL_STATUS_START -->\n## Current model status (evidence synchronized)\n\n'
       f"Río ByteGRU is a **small neural language model, not an LLM**: {d['parameters']:,} parameters, "
       f"{d['training_steps']} observed training steps. Checkpoint saved and reloaded. "
       f"Project suite: {d['project_tests_passed']} passing local tests.\n\n"
       'Current free generation rejects prompt-plus-output budgets above 128 UTF-8 bytes. '
       f"The extraction fixture has {d['current_context_rejections']} context rejections, not semantic abstentions. "
       'Neural extraction is not established. Hybrid arithmetic remains deterministic. '
       +value_statement+' '
       'Earlier low loss and failed raw-generation probes are historical, not current capability certificates.\n'
       +('Experimental recurrent prefill processes up to 4096 prompt bytes; observed full processing in 28/28 cases, but 0/24 exact graphs and 0/4 correct abstentions. No weights changed.\n' if 'experimental_streaming' in d else '')
       +(f"Separate extraction candidate: {d['extraction_candidate']['steps']} steps; {d['extraction_candidate']['dev_exact_graph_matches']}/{d['extraction_candidate']['dev_supported_cases']} exact graphs, {d['extraction_candidate']['dev_correct_abstentions']}/{d['extraction_candidate']['dev_negative_cases']} correct abstentions, {d['extraction_candidate']['invalid_outputs']} invalid outputs. Status: {d['extraction_candidate']['status']}. Original model unchanged.\n" if 'extraction_candidate' in d else ('Extraction corpus prepared but not trained.\n' if 'extraction_training_data' in d else ''))
       +('Separate closed-grammar decoding: 94/94 structurally valid outputs, but 0/78 exact graphs and 0/16 correct abstentions. Code-forced validity is not learned semantics.\n' if 'constrained_decoding' in d.get('extraction_candidate',{}) else '')
       +(f"Code-grounded durations: {d['extraction_candidate']['duration_copy']['duration_fields_correct']}/{d['extraction_candidate']['duration_copy']['duration_fields_total']} fields correct, but exact graphs {d['extraction_candidate']['duration_copy']['supported_exact_graph_matches']}/{d['extraction_candidate']['duration_copy']['supported_cases']}. Code abstentions are not learned neural ability.\n" if 'duration_copy' in d.get('extraction_candidate',{}) else '')
       +(f"Current accuracy-first paired comparison: code {d['current_accuracy_first_comparison']['code_correct_task_decisions']}/{d['current_accuracy_first_comparison']['cases']} correct decisions vs neural pipeline {d['current_accuracy_first_comparison']['neural_pipeline_correct_task_decisions']}/{d['current_accuracy_first_comparison']['cases']}. Network value: {d['current_accuracy_first_comparison']['network_earns_its_cost']}. No new weights or promotion.\n" if 'current_accuracy_first_comparison' in d else '')
       +(f"A separate weight-scaling candidate was programmed from {d['weight_search_candidate']['trial_count']} seeded trials; loss improved but dev exact graphs remain {d['weight_search_candidate']['dev_exact_graph_matches']}/{d['weight_search_candidate']['dev_supported_cases']}. Not promoted; no demonstrated neural utility gain.\n" if 'weight_search_candidate' in d else '')
       +('Bounded warm-cache/atomic-round support is observed. It changes runtime reuse, not neural weights, semantic accuracy or antivirus activation.\n' if 'runtime_support' in d else '')
       +'<!-- MODEL_STATUS_END -->')
    for name in ['README.md','model/MODEL_CARD.md']:
        path=ROOT/name;text=path.read_text()
        if '<!-- MODEL_STATUS_START -->' in text:
            text=re.sub(r'<!-- MODEL_STATUS_START -->.*?<!-- MODEL_STATUS_END -->',block,text,flags=re.S)
        else:text+='\n'+block+'\n'
        path.write_text(text)
    return d

if __name__=='__main__':
    print(json.dumps({'description_synchronized':True,'model':sync()['name']}))
