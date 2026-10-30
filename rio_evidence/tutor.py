"""Grounded scheduling tutor. Deterministic answers are not LLM inference."""
import argparse
import json
import subprocess
import sys
from .core import critical_path


def answer(case):
    result = critical_path(case['tasks'], case['durations'])
    path = result['path']
    return {'case_id': case['case_id'], 'critical_path_minutes': result['minutes'],
            'single_worker_minutes': result['single_worker_minutes'], 'path': path,
            'explanation': ('The critical path is '+ ' -> '.join(path)+
                ', taking '+str(result['minutes'])+' minutes. Total single-worker work is '+
                str(result['single_worker_minutes'])+' minutes. The critical-path result assumes '
                'enough workers for independent tasks, fixed durations and no coordination overhead. '
                'It is a lower bound, not a production-time guarantee.'),
            'scope': 'AUTHORED_SCENARIO_DETERMINISTIC_REFERENCE_NOT_USER_MASTERY'}


def prompt(case):
    expected = answer(case)
    return ('You are a scheduling tutor. Explain the supplied task graph in English. '
            'Use only the supplied computed evidence; do not invent users, tests, results or authority. '
            'Return one JSON object with case_id, critical_path_minutes, single_worker_minutes, '
            'path and explanation. A correct generated answer does not establish human mastery.\n'+
            json.dumps({'case': case, 'computed_evidence': expected}, ensure_ascii=False))


def validate_generated(case, generated):
    expected = answer(case)
    if not isinstance(generated, dict):
        raise ValueError('generator must return an object')
    for key in ('case_id','critical_path_minutes','single_worker_minutes','path'):
        if generated.get(key) != expected[key] or isinstance(generated.get(key), bool):
            raise ValueError('generated field differs from reference: '+key)
    if not isinstance(generated.get('explanation'), str) or not generated['explanation'].strip():
        raise ValueError('explanation missing')
    return {'numeric_and_path_contract': 'PASS',
            'explanation_semantics': 'NOT_INDEPENDENTLY_VALIDATED',
            'human_mastery': 'NOT_OBSERVED'}


def generate(case, command, timeout=30):
    """Explicit local subprocess contract; no shell, networking or bundled weights."""
    if not command:
        raise ValueError('a model runner command is required')
    r = subprocess.run(command, input=prompt(case), text=True, capture_output=True,
                       timeout=timeout, check=False)
    if r.returncode:
        raise ValueError('model runner exited unsuccessfully')
    output = json.loads(r.stdout)
    return {'generated': output, 'validation': validate_generated(case, output)}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['answer','prompt','generate'])
    p.add_argument('cases', help='JSONL matrix file')
    p.add_argument('case_id')
    p.add_argument('--runner', nargs=argparse.REMAINDER,
                   help='Explicitly trusted local model command; receives prompt on stdin')
    args = p.parse_args(argv)
    try:
        with open(args.cases, encoding='utf-8') as f:
            rows = [json.loads(line) for line in f if line.strip()]
        matches = [row for row in rows if row.get('case_id') == args.case_id]
        if len(matches) != 1:
            raise ValueError('exactly one matching case is required')
        case = matches[0]
        if args.mode == 'answer':
            print(json.dumps(answer(case), allow_nan=False))
        elif args.mode == 'prompt':
            print(prompt(case))
        else:
            print(json.dumps(generate(case,args.runner), allow_nan=False))
        return 0
    except (ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired) as e:
        print(json.dumps({'error': str(e)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
