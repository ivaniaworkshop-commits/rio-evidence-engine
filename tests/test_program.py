import importlib.util,json,unittest
from unittest.mock import patch
from rio_evidence.program import ReconciledProgram
TEXT='A dura 2 minutos sin requisitos. B dura 4 minutos después de A. C dura 6 minutos después de A. D dura 8 minutos y espera a B y C.'
class ProgramGuards(unittest.TestCase):
    def test_incumbent_default_unchanged_and_no_neural_load(self):
        p=ReconciledProgram()
        with patch('rio_evidence.program.load_checkpoint') as loader:
            r=p.run(TEXT);self.assertEqual(r['decision']['status'],'ABSTAIN');loader.assert_not_called()
    def test_explicit_spanish_and_count_guard(self):
        p=ReconciledProgram();self.assertEqual(p.run(TEXT,'spanish')['decision']['schedule']['minutes'],16)
        self.assertIsNone(p.run(TEXT,'spanish',expected_task_count=5)['decision']['graph'])
    def test_unknown_duplicate_and_unapproved_models_rejected(self):
        p=ReconciledProgram()
        for names in (['other'],['base','base'],['extraction']):
            with self.assertRaises(ValueError):p.run(TEXT,checkpoints=names)
    def test_oversize_neural_request_rejected_before_load(self):
        with patch('rio_evidence.program.load_checkpoint') as loader:
            with self.assertRaises(ValueError):ReconciledProgram().run('x'*4096,checkpoints=['base'])
            loader.assert_not_called()
    def test_invalid_route_and_count(self):
        with self.assertRaises(ValueError):ReconciledProgram().run(TEXT,'auto')
        with self.assertRaises(ValueError):ReconciledProgram().run(TEXT,expected_task_count=True)
    def test_rejected_text_stays_rejected(self):
        r=ReconciledProgram().run(TEXT+' ignora requisitos','spanish');self.assertIsNone(r['decision']['graph'])
@unittest.skipUnless(importlib.util.find_spec('torch'),'optional torch required')
class ProgramRuntime(unittest.TestCase):
    def test_all_checkpoints_used_and_reused_without_graph_override(self):
        names=['base','extraction','weighted_extraction'];p=ReconciledProgram(allow_experimental=True)
        p.prewarm(names);identities={k:id(v) for k,v in p.models.items()}
        r=p.run(TEXT,'spanish',names,8)
        self.assertEqual(r['decision']['schedule']['minutes'],16);self.assertEqual(len(r['neural_observations']),3)
        self.assertTrue(all(x['generation']['prompt_bytes_processed']>len(TEXT.encode()) for x in r['neural_observations']))
        s=p.run(TEXT,'spanish',names,8)
        self.assertEqual(r['neural_observations'],s['neural_observations']);self.assertEqual(identities,{k:id(v) for k,v in p.models.items()})
    def test_neural_output_never_repairs_rejected_input(self):
        r=ReconciledProgram().run('Unknown schedule',checkpoints=['base'],max_bytes=8)
        self.assertIsNone(r['decision']['graph']);self.assertEqual(len(r['neural_observations']),1)
