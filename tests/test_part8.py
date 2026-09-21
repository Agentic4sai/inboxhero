import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
import mailstore
import part8


class Part8Tests(unittest.TestCase):
    def setUp(self):
        self._saved = {key: os.environ.get(key) for key in config._DEFAULTS}
        for key in config._DEFAULTS:
            os.environ.pop(key, None)
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        inbox = Path(__file__).resolve().parents[1] / "data" / "inbox.json"
        os.environ["INBOX_FILE"] = str(inbox)
        os.environ["STATE_DIR"] = str(root / "state")
        os.environ["TRACE_FILE"] = str(root / "trace.jsonl")
        config.reload()
        self.box = mailstore.load()

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        config.reload()
        self.tmp.cleanup()

    def test_x1_lists_only_unread_messages_for_sender(self):
        result = part8.unread_from(self.box, "PRIYA@PAPERJET.IO")
        self.assertTrue(result)
        self.assertTrue(all(item["sender"] == "priya@paperjet.io" for item in result))
        self.assertNotIn("m019", {item["message_id"] for item in result})

    def test_x2_orders_thread_and_reports_only_real_questions(self):
        result = part8.thread_open_questions(self.box, self.box.by_id("m030"))
        self.assertEqual(result["thread_id"], "t-launch")
        self.assertEqual(result["messages"][0]["message_id"], "m026")
        self.assertEqual(result["messages"][-1]["message_id"], "m036")
        self.assertTrue(result["open_questions"])
        self.assertTrue(all(item["text"].endswith("?") for item in result["open_questions"]))

    def test_x3_finds_unanswered_owner_message_but_not_replied_or_self_messages(self):
        candidates = part8.follow_up_candidates(self.box, datetime.fromisoformat("2026-09-10T17:20:00"))
        ids = {item["message_id"] for item in candidates}
        self.assertIn("m044", ids)
        self.assertNotIn("m003", ids)
        self.assertNotIn("m041", ids)

    def test_x3_proposal_is_json_serializable(self):
        candidates = part8.follow_up_candidates(self.box, datetime.fromisoformat("2026-09-10T17:20:00"))
        payload = [{"message_id": item["message_id"], "days_waiting": item["days_waiting"], "proposal": item["proposal"].as_dict()} for item in candidates]
        json.dumps(payload)


if __name__ == "__main__":
    unittest.main()
