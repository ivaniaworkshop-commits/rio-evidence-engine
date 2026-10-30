import subprocess,sys,unittest
from pathlib import Path
from unittest.mock import patch
from rio_evidence.neural_lm import context_budget,generate,ContextBudgetError
ROOT=Path(__file__).resolve().parents[1]

class ContextTests(unittest.TestCase):
    def test_combined_boundary_is_accepted_without_byte_changes(self):
        self.assertEqual(context_budget('x'*127,1),b'x'*127)
    def test_over_budget_rejected_before_runtime(self):
        with patch('rio_evidence.neural_lm.runtime') as runtime:
            with self.assertRaises(ContextBudgetError):generate(ROOT,'x'*128,1)
            runtime.assert_not_called()
    def test_utf8_bytes_not_character_count(self):
        with self.assertRaises(ContextBudgetError):context_budget('é'*64,1)
        self.assertEqual(len(context_budget('é'*63,2)),126)
    def test_requested_continuation_cannot_evict_prompt(self):
        with self.assertRaises(ContextBudgetError):context_budget('Case: parallel',120)
    def test_boolean_length_and_empty_prompt_rejected(self):
        for prompt,amount in [('x',True),('',1),('x',0)]:
            with self.subTest(prompt=prompt,amount=amount),self.assertRaises(ValueError):context_budget(prompt,amount)
    def test_cli_reports_context_rejection_without_traceback(self):
        r=subprocess.run([sys.executable,'-m','rio_evidence.neural_lm','generate','--prompt','x'*128,'--max-bytes','1'],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(r.returncode,2)
        self.assertIn('CONTEXT_REJECTED',r.stdout)
        self.assertNotIn('Traceback',r.stderr)
