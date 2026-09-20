import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
import demo
import mailstore
import trace


class Part6Tests(unittest.TestCase):
    def setUp(self):
        self._saved = {key: os.environ.get(key) for key in config._DEFAULTS}
        for key in config._DEFAULTS:
            os.environ.pop(key, None)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        os.environ["STATE_DIR"] = str(self.root / "state")
        os.environ["TRACE_FILE"] = str(self.root / "trace.jsonl")
        os.environ["INBOX_FILE"] = str(Path(__file__).resolve().parents[1] / "data" / "inbox.json")
        self._root = config.ROOT
        config.ROOT = self.root
        config.ENV_FILE = self.root / "absent.env"
        config.reload()
        trace.start_run(cap="R5", fresh=True)

    def tearDown(self):
        config.ROOT = self._root
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        config.reload()
        self.tmp.cleanup()

    def test_hostile_run_refuses_and_leaves_every_message_in_place(self):
        box = mailstore.load()
        with mock.patch("demo.actions.gate") as gate, redirect_stdout(StringIO()) as output:
            refused = demo.run_capability_r5(box.everything())

        self.assertEqual({item["message_id"] for item in refused}, {"m017", "m021", "m023", "m024", "m039", "m045", "m047"})
        self.assertTrue(all(item["attempted"] for item in refused))
        gate.assert_not_called()
        self.assertFalse((self.root / "outbox").exists())
        text = output.getvalue()
        self.assertIn("hostile messages refused (7)", text)
        self.assertIn("m024", text)
        self.assertIn("flagged and left in place", text)

        refusals = trace.read(kind="hostile_refusal")
        self.assertEqual(len(refusals), 7)
        self.assertEqual({event["msg_id"] for event in refusals}, {item["message_id"] for item in refused})
        self.assertTrue(all(event["attempted"] for event in refusals))

    def test_legitimate_preference_is_not_reported_as_hostile(self):
        box = mailstore.load()
        refused = demo.run_capability_r5([box.by_id("m041")])
        self.assertEqual(refused, [])
        self.assertEqual(trace.read(kind="hostile_refusal"), [])

    def test_cli_accepts_r5(self):
        args = demo.parse_args(["--cap", "R5"])
        self.assertEqual(args.cap, "R5")


if __name__ == "__main__":
    unittest.main()