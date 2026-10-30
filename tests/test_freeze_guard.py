"""H14 freeze guard tests; local digest comparison not external authentication."""
import json
from pathlib import Path
import tempfile
import unittest
from rio_evidence.freeze_guard import FILES,RECEIPT,ROOT,verify_freeze

class FreezeGuardTests(unittest.TestCase):
    def test_current_frozen_code_and_receipt_match(self):
        report=verify_freeze()
        self.assertEqual(report["status"],"FROZEN_SOURCE_BYTES_MATCH_LOCAL_RECEIPT")
        self.assertFalse(report["candidate_promoted"])
        self.assertFalse(report["external_evaluator_authenticated"])

    def _copy(self,d):
        temp=Path(d)
        for relative in list(FILES.values())+[RECEIPT]:
            (temp/relative).parent.mkdir(parents=True,exist_ok=True)
            (temp/relative).write_bytes((ROOT/relative).read_bytes())
        return temp

    def test_detect_candidate_code_byte_drift(self):
        with tempfile.TemporaryDirectory() as d:
            root=self._copy(d)
            path=root/FILES["candidate"]
            path.write_bytes(path.read_bytes()+b"\n# drift")
            with self.assertRaisesRegex(ValueError,"FROZEN_SOURCE_BYTE_DRIFT:candidate"):
                verify_freeze(root)

    def test_detect_baseline_code_byte_drift(self):
        with tempfile.TemporaryDirectory() as d:
            root=self._copy(d)
            path=root/FILES["baseline"]
            path.write_bytes(path.read_bytes()+b"\n# drift")
            with self.assertRaisesRegex(ValueError,"FROZEN_SOURCE_BYTE_DRIFT:baseline"):
                verify_freeze(root)

    def test_reject_false_external_holdout_claim(self):
        with tempfile.TemporaryDirectory() as d:
            root=self._copy(d)
            path=root/RECEIPT
            record=json.loads(path.read_text())
            record["independent_holdout_available_at_freeze"]=True
            path.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError,"FALSE_EXTERNAL_HOLDOUT_CLAIM"):
                verify_freeze(root)
