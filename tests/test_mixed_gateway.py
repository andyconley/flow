"""Behavior boundary for the isolated Codex fixture."""

import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

from execution_gateway import _verified_greet_source, execute_mixed  # noqa: E402
from execution_ledger import ExecutionLedger  # noqa: E402
from maf_supervisor import PINNED_MAF_CORE_VERSION  # noqa: E402
from test_mixed_execution_contract import action, envelope, result  # noqa: E402


class MixedFixtureBehaviorTests(unittest.TestCase):
    def test_accepts_only_the_approved_behavior(self) -> None:
        self.assertTrue(_verified_greet_source(b'def greet() -> str:\n    return "Hello, Flow!"\n'))
        self.assertFalse(_verified_greet_source(b'def greet() -> str:\n    return "hello"\n'))

    def test_rejects_side_effects_and_obscured_behavior(self) -> None:
        self.assertFalse(_verified_greet_source(b'import os\ndef greet():\n    return "Hello, Flow!"\n'))
        self.assertFalse(_verified_greet_source(b'def greet():\n    print("side effect")\n    return "Hello, Flow!"\n'))
        self.assertFalse(_verified_greet_source(b'def greet():\n    return "Hello, " + "Flow!"\n'))
        self.assertFalse(_verified_greet_source(b'def greet():\n    return "Hello, Flow!"\ndef extra(): pass\n'))


class MixedGatewayDenialTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.attempt_dir = root / "attempt"
        (self.attempt_dir / "checkpoints").mkdir(parents=True)
        self.fixture = root / "fixture"
        self.fixture.mkdir()
        (self.fixture / "greet.py").write_text('def greet() -> str:\n    return "hello"\n')
        self.env = {**envelope(), "attempt_id": uuid4().hex,
                    "checkpoint_dir": str(self.attempt_dir / "checkpoints"),
                    "fixture_dir": str(self.fixture)}
        self.ledger = ExecutionLedger(root / "ledger.sqlite")
        self.ledger.create_attempt(self.env)
        self.calls = {"local": 0, "codex": 0}

    def proposal(self, sequence: int) -> dict:
        checkpoint_id = str(uuid4())
        checkpoint = {"checkpoint_id": checkpoint_id,
                      "workflow_name": "flow-maf-mixed-provider-v3",
                      "pending_request_info_events": {f"flow-mixed-action-{sequence}": {"request": "opaque"}}}
        (self.attempt_dir / "checkpoints" / f"{checkpoint_id}.json").write_text(json.dumps(checkpoint))
        return {**action(self.env, sequence), "checkpoint_id": checkpoint_id,
                "runtime_version": PINNED_MAF_CORE_VERSION, "request_id": f"flow-mixed-action-{sequence}"}

    def run_gateway(self, proposed: list[dict]) -> dict:
        def local_adapter(*args, **kwargs):
            self.calls["local"] += 1
            return result(self.env["assignments"][0])

        def codex_adapter(**kwargs):
            self.calls["codex"] += 1
            return result(self.env["assignments"][1])

        def supervisor(env, on_action, **kwargs):
            for proposal in proposed:
                on_action(proposal)
            return {"attempt_id": env["attempt_id"], "reason": "mixed-job-complete"}

        with patch("execution_gateway.prepare_mixed", return_value=(self.env, self.attempt_dir, self.ledger)):
            return execute_mixed(self.env["work_id"], "local.md", "codex.md",
                                 local_adapter=local_adapter, codex_adapter=codex_adapter,
                                 supervisor=supervisor)

    def test_changed_identity_and_payload_never_send(self) -> None:
        proposed = {**self.proposal(1), "task_digest": "f" * 64}
        outcome = self.run_gateway([proposed])
        self.assertEqual(outcome["status"], "failed")
        self.assertEqual(self.calls, {"local": 0, "codex": 0})
        self.assertFalse(any(e["event"] == "adapter_send_started"
                             for e in self.ledger.snapshot(self.env["attempt_id"])["events"]))

    def test_out_of_order_proposal_never_sends(self) -> None:
        outcome = self.run_gateway([self.proposal(2)])
        self.assertEqual(outcome["status"], "failed")
        self.assertEqual(self.calls, {"local": 0, "codex": 0})

    def test_extra_proposal_after_local_completion_never_sends_to_codex(self) -> None:
        outcome = self.run_gateway([self.proposal(1), self.proposal(1)])
        self.assertEqual(outcome["status"], "failed")
        self.assertEqual(self.calls, {"local": 1, "codex": 0})
        sends = [event for event in self.ledger.snapshot(self.env["attempt_id"])["events"]
                 if event["event"] == "adapter_send_started"]
        self.assertEqual(len(sends), 1)

    def test_grant_rejection_prevents_provider_send(self) -> None:
        with patch.object(self.ledger, "consume_grant", return_value=False):
            outcome = self.run_gateway([self.proposal(1)])
        self.assertEqual(outcome["status"], "failed")
        self.assertEqual(self.calls, {"local": 0, "codex": 0})
        self.assertFalse(any(e["event"] == "adapter_send_started"
                             for e in self.ledger.snapshot(self.env["attempt_id"])["events"]))


if __name__ == "__main__":
    unittest.main()
