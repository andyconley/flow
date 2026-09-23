"""Local Ollama adapter behavior for ordinary and structured-verifier calls."""

import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

from local_worker import call_local  # noqa: E402


ENVELOPE = {"provider": "ollama", "model": "local-model", "instructions": "verify", "task": "task", "attempt_id": "a"}


def payload(content, model="local-model"):
    return {"model": model, "message": {"role": "assistant", "content": content}}


class StructuredVerifierAdapterTests(unittest.TestCase):
    def call(self, response, *, structured):
        return call_local(ENVELOPE, transport=lambda _: response, structured_verifier=structured)

    def test_ordinary_calls_keep_existing_refusals_and_bound(self):
        with self.assertRaisesRegex(RuntimeError, "empty response"):
            self.call(payload(""), structured=False)
        with self.assertRaisesRegex(RuntimeError, "different model"):
            self.call(payload("ok", model="other"), structured=False)
        self.assertEqual(len(self.call(payload("x" * 5000), structured=False)["output"]), 4096)

    def test_received_empty_content_is_a_completed_observation(self):
        result = self.call(payload(""), structured=True)
        self.assertEqual((result["status"], result["output"]), ("completed", ""))
        self.assertEqual(result["output_sha256"], hashlib.sha256(b"").hexdigest())

    def test_reported_model_is_retained_for_flow_binding_check(self):
        self.assertEqual(self.call(payload("ok", model="other"), structured=True)["model"], "other")
        self.assertEqual(self.call(payload("ok", model=None), structured=True)["model"], "unreported")

    def test_output_is_not_cut_at_the_ordinary_bound(self):
        text = "x" * 20000
        result = self.call(payload(text), structured=True)
        self.assertEqual(result["output"], text)
        self.assertEqual(result["output_sha256"], hashlib.sha256(text.encode()).hexdigest())
        self.assertEqual(len(self.call(payload("x" * 70000), structured=True)["output"]), 64 * 1024)


if __name__ == "__main__":
    unittest.main()
