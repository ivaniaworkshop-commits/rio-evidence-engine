"""Opt-in declared-count guard. H14 frozen parser and its protocol stay unchanged."""
from .candidate_v1 import extract_candidate_v1


def extract_counted_graph(text, expected_task_count):
    if type(expected_task_count) is not int or not 1 <= expected_task_count <= 8:
        raise ValueError('EXPECTED_TASK_COUNT_MUST_BE_INTEGER_1_TO_8')
    result = extract_candidate_v1(text)
    metadata = {'expected_task_count': expected_task_count,
                'authority': 'CALLER_DECLARATION_NOT_AUTHENTICATED_INTENT',
                'scope': 'COUNT_CONSISTENCY_NOT_TASK_IDENTITY_OR_COMPLETENESS_PROOF'}
    if result['graph'] is not None:
        metadata['observed_task_count'] = len(result['graph']['tasks'])
        if metadata['observed_task_count'] != expected_task_count:
            return {'status': 'ABSTAIN', 'graph': None, 'schedule': None,
                    'issues': ['DECLARED_TASK_COUNT_MISMATCH'],
                    'neural_calls': 0, 'inventory_evidence': metadata}
    return dict(result, inventory_evidence=metadata)
