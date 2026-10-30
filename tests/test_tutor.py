import importlib.util
import json
from pathlib import Path
import sys
import unittest
from rio_evidence.core import critical_path
from rio_evidence.tutor import answer,generate,prompt,validate_generated
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('matrix_builder',ROOT/'scripts/build_answer_matrix.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)

class TutorTests(unittest.TestCase):
    def test_matrix_matches_exhaustive_path_oracle(self):
        cases=builder.build();self.assertEqual(len(cases),128)
        for c in cases:
            tasks={t['id']:t for t in c['tasks']};dur=c['durations']
            def paths(key):
                deps=tasks[key].get('depends_on',[])
                return [[key]] if not deps else [p+[key] for dep in deps for p in paths(dep)]
            longest=max(sum(dur[k] for k in p) for key in tasks for p in paths(key))
            with self.subTest(case=c['case_id']):
                self.assertEqual(c['reference']['critical_path_minutes'],longest)
                self.assertEqual(c['reference']['single_worker_minutes'],sum(dur.values()))

    def test_checked_in_corpus_is_reproducible(self):
        stored=[json.loads(s) for s in (ROOT/'training/answer_matrix.jsonl').read_text().splitlines()]
        self.assertEqual(stored,builder.build())
        self.assertEqual(sum(c['split']=='holdout' for c in stored),26)

    def test_false_generated_numbers_rejected(self):
        c=builder.build()[0];a=answer(c);a['critical_path_minutes']+=1
        with self.assertRaises(ValueError):validate_generated(c,a)

    def test_model_adapter_contract_with_stub_not_llm(self):
        c=builder.build()[0]
        code='import sys,json; s=sys.stdin.read(); evidence=json.loads(s.split("\\n",1)[1]); print(json.dumps(evidence["computed_evidence"]))'
        r=generate(c,[sys.executable,'-c',code]);self.assertEqual(r['validation']['numeric_and_path_contract'],'PASS')
        self.assertEqual(r['validation']['explanation_semantics'],'NOT_INDEPENDENTLY_VALIDATED')

    def test_prompt_discloses_limits(self):
        self.assertIn('does not establish human mastery',prompt(builder.build()[0]))

    def test_integer_duration_total_preserves_exact_precision(self):
        n=9007199254740993;r=critical_path([{'id':'x'}],{'x':n})
        self.assertEqual(r['single_worker_minutes'],n)
        self.assertIs(type(r['single_worker_minutes']),int)
