"""R004: exercise the real workflow's policy shell without network or credentials."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/rio-primer-cobro-deploy.yml'


def extract_policy_script():
    content = WORKFLOW.read_text(encoding='utf-8')
    marker = '      - id: policy\n'
    if content.count(marker) != 1:
        raise AssertionError('Expected precisely one policy step')
    section = content.split(marker, 1)[1]
    if '\n  deploy:\n' not in section:
        raise AssertionError('Missing deploy job boundary')
    section = section.split('\n  deploy:\n', 1)[0]
    delimiter = '        run: |\n'
    if section.count(delimiter) != 1:
        raise AssertionError('Expected exactly one shell run block')
    block = section.split(delimiter, 1)[1]
    lines = block.splitlines()
    if not lines or any(line and not line.startswith('          ') for line in lines):
        raise AssertionError('Unexpected policy shell indentation')
    return '\n'.join(line[10:] if line else '' for line in lines) + '\n'


MOCK_GH = '''#!/usr/bin/env python3
import json
import os
import sys
mode = os.environ['RIO_R004_MOCK_MODE']
if len(sys.argv) < 3 or sys.argv[1] != 'api':
    sys.exit(77)
endpoint = sys.argv[2]
if endpoint.endswith('/rulesets?includes_parents=true'):
    if mode == 'list_error':
        sys.exit(17)
    if mode != 'empty':
        print('17')
    sys.exit(0)
if endpoint.endswith('/rulesets/17'):
    if mode == 'detail_error':
        sys.exit(18)
    valid = {
        'target': 'branch', 'enforcement': 'active',
        'conditions': {'ref_name': {'include': ['refs/heads/deploy/primer-cobro'], 'exclude': []}},
        'bypass_actors': [],
        'rules': [{'type': 'pull_request', 'parameters': {'required_approving_review_count': 1}},
                  {'type': 'deletion'}, {'type': 'non_fast_forward'}]
    }
    if mode == 'invalid_policy':
        valid['rules'] = [{'type': 'deletion'}]
    print(json.dumps(valid))
    sys.exit(0)
sys.exit(79)
'''


class ReleaseAuthorityContractTests(unittest.TestCase):
    def invoke(self, mode):
        with tempfile.TemporaryDirectory(prefix='rio-r004-') as tmp:
            p = Path(tmp)
            b = p / 'bin'
            b.mkdir()
            gh = b / 'gh'
            gh.write_text(MOCK_GH, encoding='utf-8')
            gh.chmod(0o700)
            output = p / 'output.txt'
            summary = p / 'summary.txt'
            output.write_text('', encoding='utf-8')
            summary.write_text('', encoding='utf-8')
            env = os.environ.copy()
            env.update({
                'RIO_R004_MOCK_MODE': mode, 'GITHUB_REPOSITORY': 'mock/project',
                'GITHUB_OUTPUT': str(output), 'GITHUB_STEP_SUMMARY': str(summary),
                'GH_TOKEN': 'not-a-real-credential', 'PATH': str(b) + os.pathsep + env['PATH'],
            })
            run = subprocess.run(['bash', '--noprofile', '--norc', '-c', extract_policy_script()],
                                 cwd=ROOT, env=env, capture_output=True, text=True, timeout=10)
            values = [ln for ln in output.read_text(encoding='utf-8').splitlines() if ln.startswith('authorized=')]
            self.assertTrue(values, 'Workflow must emit authorized output')
            return run.returncode, values[-1], summary.read_text(encoding='utf-8'), run.stderr

    def assert_denied(self, mode, reason):
        code, auth, summary, _ = self.invoke(mode)
        self.assertEqual(code, 2, mode)
        self.assertEqual(auth, 'authorized=false', mode)
        self.assertIn('RELEASE_AUTHORITY=' + reason, summary, mode)

    def test_api_unavailable_denies(self):
        self.assert_denied('list_error', 'UNKNOWN_API_UNAVAILABLE')

    def test_no_rulesets_denies(self):
        self.assert_denied('empty', 'BLOCKED_NO_ACTIVE_RULESETS')

    def test_detail_read_failure_denies(self):
        self.assert_denied('detail_error', 'UNKNOWN_RULESET_READ')

    def test_invalid_policy_denies(self):
        self.assert_denied('invalid_policy', 'BLOCKED_POLICY_CHECK')

    def test_valid_mock_ruleset_allows_only_local_gate(self):
        code, auth, summary, _ = self.invoke('valid')
        self.assertEqual(code, 0)
        self.assertEqual(auth, 'authorized=true')
        self.assertIn('RELEASE_AUTHORITY=VERIFIED_RULESET_GUARDS', summary)


if __name__ == '__main__':
    unittest.main()
