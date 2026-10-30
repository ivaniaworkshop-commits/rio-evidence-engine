import unittest
from unittest.mock import Mock
from rio_evidence.duration_copy import extract_durations,grounded_generate
from rio_evidence.constrained_extraction import ConstrainedExtractor

class DurationCopyTests(unittest.TestCase):
    def text(self):return ('Task A lasts 3 minutes. Prerequisites: none.\n'
      '[B] duration=7 minutes; requires=A.\n'
      'Before starting C (duration 11 minutes), finish A.\n'
      'D runs for 2 minutes and may begin without waiting for another task.')
    def test_multiple_recognized_wordings_recover_exact_values(self):
        r=extract_durations(self.text());self.assertEqual(r['status'],'EXPLICIT_DURATIONS_RECOVERED')
        self.assertEqual(r['durations'],dict(A=3,B=7,C=11,D=2))
    def test_conflict_does_not_choose_last_value(self):
        r=extract_durations(self.text()+'\nTask A also has duration 9 minutes.')
        self.assertEqual(r['status'],'ABSTAIN');self.assertIn('CONFLICTING_DURATIONS',r['issues'])
        self.assertNotIn('A',r['durations'])
    def test_missing_duration_is_not_invented(self):
        r=extract_durations('Task A lasts 3 minutes.')
        self.assertEqual(r['status'],'ABSTAIN');self.assertEqual(r['durations'],{'A':3})
    def test_unicode_offsets_recover_actual_source(self):
        text='é\n'+self.text();r=extract_durations(text)
        for e in r['evidence']:
            self.assertEqual(text[e['number_start']:e['number_end']],e['number_text'])
            self.assertEqual(text[e['source_start']:e['source_end']],e['source_text'])
    def test_unsupported_id_is_explicit(self):
        r=extract_durations(self.text()+'\nTask E lasts 5 minutes.')
        self.assertEqual(r['status'],'ABSTAIN');self.assertIn('UNSUPPORTED_TASK_ID',r['issues'])
    def test_abstention_never_calls_neural_decoder(self):
        decoder=Mock();r=grounded_generate('Task A lasts 3 minutes.',decoder)
        decoder.generate.assert_not_called();self.assertFalse(r['neural_inference'])
    def test_invalid_override_rejected_before_inference(self):
        decoder=object.__new__(ConstrainedExtractor)
        with self.assertRaises(ValueError):decoder.generate('tasks',duration_values=dict(A=True,B=2,C=3,D=4))
