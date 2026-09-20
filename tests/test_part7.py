import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
import dashboard
import demo
import mailstore
import trace


class Part7Tests(unittest.TestCase):
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

    def test_dashboard_has_exactly_three_panes_and_grounded_multi_message_commitments(self):
        box = mailstore.load()
        trace.event("hostile_refusal", msg_id="m024", attempted="delete the message", reason="hostile", outcome="refused; flagged and left in place")
        result = dashboard.build(box)

        self.assertEqual(set(result), {"pending_actions", "flagged", "commitments"})
        launch = next(item for item in result["commitments"] if item["title"] == "Product launch")
        board_deck = next(item for item in result["commitments"] if item["title"] == "Board deck circulated")
        self.assertEqual(launch["evidence_ids"], ["m026", "m019"])
        self.assertEqual(board_deck["evidence_ids"], ["m040", "m038"])
        for item in result["commitments"]:
            for message_id in item["evidence_ids"]:
                self.assertIsNotNone(box.by_id(message_id))
        self.assertEqual(result["flagged"][0]["message_id"], "m024")

    def test_pending_action_reads_gate_records(self):
        path = config.STATE_PATH / "gated_actions.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "message_id": "m019",
            "action": "send",
            "proposal": {"reason": "sending is irreversible and requires a human decision"},
            "human_decision": "dry-run",
            "outcome": "not written to outbox",
        }) + "\n", encoding="utf-8")
        result = dashboard.build(mailstore.load())
        self.assertEqual(result["pending_actions"][0]["message_id"], "m019")
        self.assertEqual(result["pending_actions"][0]["action"], "send")

    def test_r6_render_has_three_pane_headers_and_writes_dashboard(self):
        box = mailstore.load()
        result = dashboard.build(box)
        with redirect_stdout(StringIO()) as output:
            dashboard.render(result)
        self.assertEqual(output.getvalue().count("=== "), 3)
        path = dashboard.write(result)
        self.assertEqual(set(json.loads(path.read_text(encoding="utf-8"))), {"pending_actions", "flagged", "commitments"})


if __name__ == "__main__":
    unittest.main()