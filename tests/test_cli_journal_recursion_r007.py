"""R007: full CLI bounded-decode regression for deeply nested JSON journals.

Tests actual package entrypoints in separate processes; no external services.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class JournalRecursionCliRegression(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def test_verify_journal_deep_recursion_fails_closed_without_traceback(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "deep.jsonl"
            path.write_text("[" * 20000 + "0" + "]" * 20000 + "\n", encoding="utf-8")
            result = self.run_cli("rio_evidence", "verify-journal", str(path))
            self.assertEqual(result.returncode, 2, (result.stdout, result.stderr))
            self.assertEqual(result.stdout, "")
            self.assertNotIn("Traceback", result.stderr)
            self.assertIn("nesting", json.loads(result.stderr)["error"])

    def test_program_deep_recursion_fails_closed_without_traceback(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "deep.json"
            path.write_text("[" * 20000 + "0" + "]" * 20000, encoding="utf-8")
            result = self.run_cli("rio_evidence.program", str(path), "--route", "spanish")
            self.assertEqual(result.returncode, 2, (result.stdout, result.stderr))
            self.assertNotIn("Traceback", result.stdout + result.stderr)
            record = json.loads(result.stdout)
            self.assertEqual(record["status"], "HOLD")
            self.assertIn("nesting", record["error"].lower())

    def test_verify_journal_empty_control_succeeds(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "empty.jsonl"
            path.write_bytes(b"")
            result = self.run_cli("rio_evidence", "verify-journal", str(path))
            self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
            record = json.loads(result.stdout)
            self.assertEqual(record["events"], 0)
            self.assertEqual(record["scope"], "INTERNAL_CONSISTENCY_ONLY")
            self.assertIsNone(record["head_sha256"])


if __name__ == "__main__":
    unittest.main()
