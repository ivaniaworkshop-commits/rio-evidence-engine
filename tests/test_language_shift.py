"""Fixture validity only, not hidden performance evidence."""
import unittest
from evaluation.language_shift_probe import rows
from rio_evidence.semantic_gate import canonical
from rio_evidence.independent_gate import _known_text
from pathlib import Path
class LanguageShiftTests(unittest.TestCase):
    def test_count_and_unique_ids(self):
        self.assertEqual(len(rows()),52)
        self.assertEqual(len(set(x["case_id"] for x in rows())),52)
    def test_supported_labels(self):
        pos=[x for x in rows() if x["kind"]=="supported"]
        self.assertEqual(len(pos),40)
        self.assertEqual(len(set(x["family"] for x in pos)),8)
        for x in pos:self.assertEqual(len(canonical(x["expected"])["tasks"]),4)
    def test_negative_labels(self):
        neg=[x for x in rows() if x["kind"]=="unsupported"]
        self.assertEqual(len(neg),12)
        self.assertTrue(all(x["expected"] is None for x in neg))
    def test_no_direct_training_text_overlap(self):
        seen=_known_text(Path(__file__).resolve().parents[1])
        self.assertTrue(all(" ".join(x["text"].casefold().split()) not in seen for x in rows()))
