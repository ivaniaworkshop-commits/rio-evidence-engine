"""H07 fail-closed audit of an existing 94-case authored development comparison.

Checks identities, source hashes, paired outcomes and replay digests.
This is not a hidden-test evaluation, true financial cost or neural promotion.
"""
import hashlib
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def audit(root=ROOT):
    root = Path(root)
    report = json.loads((root / 'model/NETWORK_VALUE_RESULT.json').read_text())
    source = (root / 'training/extraction_dev.jsonl').read_bytes()
    cases = [json.loads(line) for line in source.splitlines() if line.strip()]
    rows = report['rows']
    if report['dev_data_sha256'] != hashlib.sha256(source).hexdigest():
        raise ValueError('H07_SOURCE_HASH_MISMATCH')
    model_hash = hashlib.sha256((root / 'model/extraction_gru.pt').read_bytes()).hexdigest()
    if report['checkpoint_sha256'] != model_hash:
        raise ValueError('H07_CHECKPOINT_HASH_MISMATCH')
    if len(rows) != len(cases) or len(cases) != report['cases'] or not cases:
        raise ValueError('H07_CASE_COUNT_MISMATCH')
    expected_ids = [case['case_id'] for case in cases]
    observed_ids = [row['case_id'] for row in rows]
    if expected_ids != observed_ids or len(set(observed_ids)) != len(rows):
        raise ValueError('H07_UNPAIRED_OR_DUPLICATED_CASE_IDS')
    code_ok = neural_ok = exact_code = exact_neural = neg_code = neg_neural = supported = negative = 0
    code_times = []
    neural_times = []
    for case, row in zip(cases, rows):
        if case['kind'] != row['kind']:
            raise ValueError('H07_CASE_KIND_MISMATCH')
        if type(row['code_pass']) is not bool or type(row['neural_pass']) is not bool:
            raise ValueError('H07_INVALID_OUTCOME_TYPE')
        for mode, times in [('code', code_times), ('neural', neural_times)]:
            triple = row[mode + '_timings_ms']
            median = row[mode + '_median_ms']
            if len(triple) != report['repetitions_per_mode'] or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in triple):
                raise ValueError('H07_INVALID_LATENCY')
            if not math.isclose(statistics.median(triple), median, abs_tol=1e-8):
                raise ValueError('H07_LATENCY_MEDIAN_MISMATCH')
            times.extend(triple)
        code_ok += row['code_pass']
        neural_ok += row['neural_pass']
        if case['kind'] == 'supported':
            supported += 1
            if row['code_pass'] != (row['code_grade'] == 'EXACT_GRAPH_MATCH'):
                raise ValueError('H07_CODE_GRADE_DISCORD')
            if row['neural_pass'] != (row['neural_grade'] == 'EXACT_GRAPH_MATCH'):
                raise ValueError('H07_NEURAL_GRADE_DISCORD')
            exact_code += row['code_pass']
            exact_neural += row['neural_pass']
        elif case['kind'] == 'unsupported':
            negative += 1
            if row['code_pass'] != (row['code_grade'] == 'CORRECT_ABSTENTION'):
                raise ValueError('H07_CODE_ABSTENTION_DISCORD')
            if row['neural_pass'] != (row['neural_grade'] == 'CORRECT_ABSTENTION'):
                raise ValueError('H07_NEURAL_ABSTENTION_DISCORD')
            neg_code += row['code_pass']
            neg_neural += row['neural_pass']
        else:
            raise ValueError('H07_UNKNOWN_CASE_KIND')
    expected = {
        'code_correct_task_decisions': code_ok,
        'neural_pipeline_correct_task_decisions': neural_ok,
        'code_supported_exact_graphs': exact_code,
        'neural_supported_exact_graphs': exact_neural,
        'supported_cases': supported,
        'negative_cases': negative
    }
    if any(report[k] != v for k, v in expected.items()):
        raise ValueError('H07_AGGREGATE_MISMATCH')
    for key, values in [('code_median_ms', code_times), ('neural_pipeline_median_ms', neural_times)]:
        if not math.isclose(report[key], statistics.median(values), abs_tol=1e-8):
            raise ValueError('H07_GLOBAL_LATENCY_MISMATCH')
    paired = [[r['code_pass'], r['neural_pass'], r['code_median_ms'], r['neural_median_ms']] for r in rows]
    if paired != report['paired_matrix'] or len(paired) != report['cases']:
        raise ValueError('H07_MATRIX_MISMATCH')
    simulation_digest = hashlib.sha256(json.dumps(report['simulation'], sort_keys=True).encode()).hexdigest()
    if not report['fixed_seed_replay_equal'] or simulation_digest != report['simulation_replay_sha256']:
        raise ValueError('H07_REPLAY_RECORD_MISMATCH')
    if report['financial_cost'] != 'UNKNOWN':
        raise ValueError('H07_UNSUPPORTED_FINANCIAL_COST')
    if exact_neural > exact_code or neg_neural > neg_code:
        decision = 'NEW_VALUE_MUST_BE_INVESTIGATED'
    else:
        decision = 'NO_DEMONSTRATED_NEURAL_VALUE_ON_AUTHORED_DEV'
    return {
        'scope': 'PAIRED_PROJECT_AUTHORED_DEV_REAUDIT_NOT_INDEPENDENT_HIDDEN_TEST',
        'cases': len(rows),
        'supported_cases': supported,
        'negative_cases': negative,
        'code_exact_graphs': exact_code,
        'neural_exact_graphs': exact_neural,
        'code_correct_abstentions': neg_code,
        'neural_correct_abstentions': neg_neural,
        'code_correct_decisions': code_ok,
        'neural_correct_decisions': neural_ok,
        'delta_neural_minus_code_decisions': neural_ok - code_ok,
        'code_median_ms': report['code_median_ms'],
        'neural_median_ms': report['neural_pipeline_median_ms'],
        'latency_ratio_neural_to_code': report['neural_pipeline_median_ms'] / report['code_median_ms'],
        'model_checkpoint_sha256': model_hash,
        'dev_sha256': report['dev_data_sha256'],
        'simulated_replay_digest_verified': True,
        'financial_cost': 'UNKNOWN',
        'uncertainty': 'Errors are observed on authored cases; calibration and external generalization UNKNOWN.',
        'decision': decision,
        'candidate_promoted': False
    }


if __name__ == '__main__':
    print(json.dumps(audit(), sort_keys=True, indent=2))
