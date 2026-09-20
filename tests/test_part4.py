import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import actions
import config
import demo
import trace


class Part4Tests(unittest.TestCase):
    def setUp(self):
        self._saved = {key: os.environ.get(key) for key in config._DEFAULTS}
        for key in config._DEFAULTS:
            os.environ.pop(key, None)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        os.environ["STATE_DIR"] = str(self.root / "state")
        os.environ["TRACE_FILE"] = str(self.root / "trace.jsonl")
        self._root = config.ROOT
        config.ROOT = self.root
        config.ENV_FILE = self.root / "absent.env"
        config.reload()
        trace.start_run(cap="R3", fresh=True)
        self.proposal = actions.ActionProposal(
            message_id="m019",
            action="send",
            to="venue@example.com",
            subject="Re: Venue availability",
            body="The launch is on September 20.",
            evidence_ids=("m026", "m036"),
            reason="sending is irreversible",
        )

    def tearDown(self):
        config.ROOT = self._root
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        config.reload()
        self.tmp.cleanup()

    def test_action_classification(self):
        self.assertEqual(actions.action_type("archive"), "reversible")
        self.assertEqual(actions.action_type("send"), "irreversible")
        self.assertEqual(actions.action_type("delete"), "irreversible")

    def test_dry_run_does_not_write_outbox(self):
        result = actions.gate(self.proposal, "dry-run")
        self.assertEqual(result["human_decision"], "dry-run")
        self.assertFalse((self.root / "outbox").exists())
        self.assertEqual(trace.read(kind="gate")[-1]["outcome"], "not written to outbox")

    def test_approval_writes_one_structured_message(self):
        result = actions.gate(self.proposal, "approve")
        path = self.root / "outbox" / "m019.json"
        self.assertEqual(result["outcome"], "written to outbox")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["evidence_ids"], ["m026", "m036"])
        self.assertEqual(list((self.root / "outbox").glob("*.json")), [path])

    def test_duplicate_approval_does_not_overwrite(self):
        actions.gate(self.proposal, "approve")
        result = actions.gate(self.proposal, "approve")
        self.assertIn("already exists", result["outcome"])

    def test_missing_decision_refuses_to_send(self):
        result = actions.gate(self.proposal, "missing")
        self.assertEqual(result["human_decision"], "missing")
        self.assertFalse((self.root / "outbox").exists())

    def test_delete_is_never_performed(self):
        delete = actions.ActionProposal("m024", "delete", "", "", "", reason="hostile request")
        result = actions.gate(delete, "approve")
        self.assertEqual(result["human_decision"], "refused")
        self.assertIn("unsupported", result["outcome"])
        self.assertFalse((self.root / "outbox").exists())

    def test_gate_log_contains_proposal_decision_and_outcome(self):
        actions.gate(self.proposal, "dry-run")
        log = self.root / "state" / "gated_actions.jsonl"
        record = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(record["proposal"]["message_id"], "m019")
        self.assertEqual(record["human_decision"], "dry-run")
        self.assertEqual(record["outcome"], "not written to outbox")

    def test_approval_requires_one_message(self):
        with self.assertRaises(demo.Usage):
            demo.parse_args(["--cap", "R3", "--approve"])


if __name__ == "__main__":
    unittest.main()
