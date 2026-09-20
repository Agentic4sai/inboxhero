import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Part5Tests(unittest.TestCase):
    def test_preference_survives_process_restart_and_changes_later_decision(self):
        with tempfile.TemporaryDirectory() as temp:
            env = os.environ.copy()
            env["STATE_DIR"] = temp
            env["TRACE_FILE"] = str(Path(temp) / "trace.jsonl")
            env.pop("GEMINI_API_KEY", None)

            stored = subprocess.run(
                [sys.executable, "demo.py", "--cap", "R4", "--msg", "m041"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("stored preference", stored.stdout)
            memory_path = Path(temp) / "preferences.json"
            self.assertTrue(memory_path.exists())
            self.assertEqual(json.loads(memory_path.read_text(encoding="utf-8"))["calendar_rule"]["source"], "m041")

            applied = subprocess.run(
                [sys.executable, "demo.py", "--cap", "R4", "--msg", "m043"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("do not accept 9:00am; offer 11:00am or later", applied.stdout)
            self.assertIn('"event": "preference_applied"', (Path(temp) / "trace.jsonl").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
