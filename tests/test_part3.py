import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
import demo
import mailstore
from retrieval import retrieve_evidence


class Part3Tests(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in config._DEFAULTS}
        for key in config._DEFAULTS:
            os.environ.pop(key, None)
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["STATE_DIR"] = self.tmp.name
        os.environ["TRACE_FILE"] = str(Path(self.tmp.name) / "trace.jsonl")
        self._env_file = config.ENV_FILE
        config.ENV_FILE = Path(self.tmp.name) / "absent.env"
        config.reload()
        self.box = mailstore.load()

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        config.ENV_FILE = self._env_file
        config.reload()
        self.tmp.cleanup()

    def test_same_thread_walk_returns_prior_message_evidence(self):
        message = self.box.by_id("m008")
        evidence = retrieve_evidence(self.box, message, "amqp url staging queue creds")
        ids = [hit["message_id"] for hit in evidence["same_thread"]]
        self.assertIn("m003", ids)
        self.assertIn("m001", ids)

    def test_keyword_search_can_find_cross_thread_fact(self):
        message = self.box.by_id("m019")
        evidence = retrieve_evidence(self.box, message, "launch date product launch event")
        ids = [hit["message_id"] for hit in evidence["cross_thread"]]
        self.assertTrue(any(msg_id in ids for msg_id in ("m026", "m036")))

    def test_retrieval_rejects_missing_evidence(self):
        message = self.box.by_id("m019")
        evidence = retrieve_evidence(self.box, message, "this is not in any email")
        self.assertEqual(evidence["same_thread"], [])
        self.assertEqual(evidence["cross_thread"], [])

    def test_r2_returns_a_grounded_answer_with_authorized_citations(self):
        class StubAgent:
            def handle_message(self, prompt, **kwargs):
                self.prompt = prompt
                return '{"answer":"The launch is on September 20.","evidence_ids":["m026","m036"]}'

        message = self.box.by_id("m019")
        result = demo.run_capability_r2(
            self.box,
            message,
            query="launch date product launch event",
            agent=StubAgent(),
        )
        self.assertEqual(result["draft"]["evidence_ids"], ["m026", "m036"])

    def test_r2_rejects_a_citation_not_returned_by_retrieval(self):
        class StubAgent:
            def handle_message(self, prompt, **kwargs):
                return '{"answer":"The launch is confirmed.","evidence_ids":["m999"]}'

        message = self.box.by_id("m019")
        result = demo.run_capability_r2(
            self.box,
            message,
            query="launch date product launch event",
            agent=StubAgent(),
        )
        self.assertIsNone(result["draft"])
        self.assertIn("not returned by retrieval", result["error"])


if __name__ == "__main__":
    unittest.main()
