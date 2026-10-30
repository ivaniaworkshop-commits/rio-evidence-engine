"""JSON command line interface; no network or model calls."""
import argparse
import json
import sys
from .core import critical_path, compare_results, read_events
from .json_io import load


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['schedule', 'compare', 'verify-journal'])
    parser.add_argument('input', help='UTF-8 JSON file, or JSONL journal')
    args = parser.parse_args(argv)
    try:
        if args.command == 'verify-journal':
            rows = read_events(args.input)
            result = {'events': len(rows), 'head_sha256': rows[-1]['sha256'] if rows else None,
                      'scope': 'INTERNAL_CONSISTENCY_ONLY'}
        else:
            data = load(args.input)
            if not isinstance(data, dict):
                raise ValueError('input must be an object')
            if args.command == 'schedule':
                result = critical_path(data['tasks'], data['durations'])
            else:
                result = compare_results(data['baseline'], data['candidate'])
        print(json.dumps(result, allow_nan=False, sort_keys=True))
        return 0
    except (ValueError, TypeError, KeyError, OSError, OverflowError) as error:
        print(json.dumps({'error': str(error)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
