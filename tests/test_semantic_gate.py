import importlib.util,json
from pathlib import Path
import unittest
from rio_evidence.semantic_gate import canonical,grade,rule_baseline
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('semantic_fixture_builder',ROOT/'scripts/build_semantic_fixture.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)

class SemanticGateTests(unittest.TestCase):
    def test_reordered_equivalent_graph_is_accepted(self):
        c=builder.build()[0];observed=json.loads(json.dumps(c['expected']));observed['tasks'].reverse()
        self.assertEqual(grade(observed,c['expected'])['status'],'EXACT_GRAPH_MATCH')
    def test_same_total_does_not_hide_wrong_durations(self):
        expected={'tasks':[{'id':'A'},{'id':'B','depends_on':['A']}],'durations':{'A':10,'B':20}}
        changed={'tasks':expected['tasks'],'durations':{'A':20,'B':10}}
        self.assertEqual(grade(changed,expected)['status'],'WRONG_GRAPH')
    def test_rule_abstains_on_incomplete_language(self):
        self.assertIsNone(rule_baseline('A takes some time, then B.'))
        self.assertEqual(grade(None,None)['status'],'CORRECT_ABSTENTION')
    def test_fixture_reproduces_and_references_validate(self):
        stored=[json.loads(s) for s in (ROOT/'evaluation/semantic_fixture.jsonl').read_text().splitlines()]
        self.assertEqual(stored,builder.build());self.assertEqual(len(stored),28)
        for c in stored:
            if c['expected'] is not None:canonical(c['expected'])
