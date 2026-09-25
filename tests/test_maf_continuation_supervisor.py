"""Focused action-3 restore readiness across separate pinned MAF children."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli"))
sys.path.insert(0, str(ROOT / "tests"))

from maf_supervisor import MafProtocolError, run_maf_action3_continuation, run_maf_multiturn  # noqa: E402
from test_execution import ExecutionFixture  # noqa: E402

from maf_env import MAF_PYTHON as PINNED_PYTHON, requires_maf  # noqa: E402


@requires_maf
class MafContinuationSupervisorTests(ExecutionFixture):
    def _pending(self):
        envelope, _, _ = self.prepare()
        envelope = {**envelope, "execution_protocol_version": 2}
        captured = {}

        def interrupted(proposal):
            captured.update(proposal)
            raise RuntimeError("controlled interruption before response")

        with self.assertRaisesRegex(RuntimeError, "controlled interruption"):
            run_maf_multiturn(envelope, interrupted, lambda _: {}, phase="action3", python_path=str(PINNED_PYTHON))
        resume = {"schema_version": 2, "checkpoint_id": captured["checkpoint_id"],
                  "request_id": "flow-action-3", "action_id": captured["action_id"]}
        return envelope, resume

    def test_restores_pending_checkpoint_before_flow_response(self):
        envelope, resume = self._pending()
        ready = []

        def on_ready(proposal):
            ready.append(proposal)
            self.assertEqual(proposal["checkpoint_id"], resume["checkpoint_id"])
            self.assertEqual(proposal["request_id"], "flow-action-3")
            return {"status": "completed", "action_id": resume["action_id"], "output": "stored result"}

        terminal = run_maf_action3_continuation(envelope, resume, on_ready, python_path=str(PINNED_PYTHON))
        self.assertEqual(len(ready), 1)
        self.assertEqual(terminal["reason"], "action-3-complete")

    def test_wrong_action_identity_never_reaches_flow_callback(self):
        envelope, resume = self._pending()
        resume["action_id"] = "foreign"
        with self.assertRaisesRegex(RuntimeError, "invalid action-3 continuation identity"):
            run_maf_action3_continuation(envelope, resume, lambda _: self.fail("not ready"), python_path=str(PINNED_PYTHON))

    def test_wrong_checkpoint_never_reaches_flow_callback(self):
        envelope, resume = self._pending()
        resume["checkpoint_id"] = "foreign"
        with self.assertRaisesRegex(RuntimeError, "continuation checkpoint"):
            run_maf_action3_continuation(envelope, resume, lambda _: self.fail("not ready"), python_path=str(PINNED_PYTHON))


if __name__ == "__main__":
    unittest.main()
