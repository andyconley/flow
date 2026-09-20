"""The v4 gateway sends only the approved, checkpointed pair."""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

from claude_gateway import execute_claude
from claude_worker import build_prompt
from execution_ledger import ExecutionLedger
from maf_supervisor import PINNED_MAF_CORE_VERSION
from test_claude_execution_contract import action, envelope


class ClaudeGatewayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.attempt_dir = root / "attempt"
        (self.attempt_dir / "checkpoints").mkdir(parents=True)
        for item in envelope()["source_files"]:
            source = self.attempt_dir / "source" / item["path"]
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("# source\n")
            item["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        self.env = {**envelope(), "attempt_id": uuid4().hex,
                    "checkpoint_dir": str(self.attempt_dir / "checkpoints")}
        self.env["source_files"] = [
            {**item, "sha256": hashlib.sha256((self.attempt_dir / "source" / item["path"]).read_bytes()).hexdigest()}
            for item in self.env["source_files"]]
        self.ledger = ExecutionLedger(root / "ledger.sqlite")
        self.ledger.create_attempt(self.env)
        self.calls = {"local": 0, "claude": 0}

    def proposal(self, sequence):
        checkpoint_id = str(uuid4())
        (self.attempt_dir / "checkpoints" / f"{checkpoint_id}.json").write_text(json.dumps({
            "checkpoint_id": checkpoint_id, "workflow_name": "flow-maf-claude-review-v4",
            "pending_request_info_events": {f"flow-mixed-action-{sequence}": {"request": "opaque"}}}))
        return {**action(self.env, sequence), "checkpoint_id": checkpoint_id,
                "runtime_version": PINNED_MAF_CORE_VERSION, "request_id": f"flow-mixed-action-{sequence}"}

    def run_job(self, proposals, *, fail_claude=False):
        def local_adapter(*args, **kwargs):
            self.calls["local"] += 1
            output = "Check auth and subprocess timeout."
            return {"schema_version": 1, "status": "completed", "provider": "ollama",
                    "model": self.env["assignments"][0]["model"], "physical_call": True,
                    "evidence_level": "flow_observed_local_http_response", "output": output,
                    "output_sha256": hashlib.sha256(output.encode()).hexdigest(), "usage": None}

        def claude_adapter(**kwargs):
            self.calls["claude"] += 1
            if fail_claude:
                raise TimeoutError("provider outcome uncertain")
            output = "No findings in the supplied source."
            return {"schema_version": 1, "status": "completed", "provider": "claude",
                    "model": kwargs["model"], "physical_call": True,
                    "evidence_level": "flow_observed_claude_cli_completed_turn", "output": output,
                    "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
                    "input_sha256": hashlib.sha256(build_prompt(kwargs["instructions"], kwargs["task"])).hexdigest(),
                    "usage": {"input_tokens": 10}, "session_id": "session-1"}

        def supervisor(env, on_action, **kwargs):
            for proposal in proposals:
                on_action(proposal)
            return {"attempt_id": env["attempt_id"], "reason": "mixed-job-complete"}

        with patch("claude_gateway.prepare_claude", return_value=(self.env, self.attempt_dir, self.ledger)):
            return execute_claude(self.env["work_id"], "local.md", "claude.md",
                                  local_adapter=local_adapter, claude_adapter=claude_adapter, supervisor=supervisor)

    def test_completed_pair_has_linked_review(self):
        outcome = self.run_job([self.proposal(1), self.proposal(2)])
        self.assertEqual(outcome["status"], "completed", outcome)
        self.assertEqual(self.calls, {"local": 1, "claude": 1})
        receipt = json.loads(Path(outcome["receipt_path"]).read_text())
        self.assertEqual(receipt["review_artifact"]["plan_sha256"],
                         hashlib.sha256((self.attempt_dir / "test-plan.md").read_bytes()).hexdigest())

    def test_bad_action_never_sends(self):
        proposal = {**self.proposal(1), "provider": "claude"}
        outcome = self.run_job([proposal])
        self.assertEqual(outcome["status"], "failed", outcome)
        self.assertEqual(self.calls, {"local": 0, "claude": 0})

    def test_wrong_order_never_sends(self):
        outcome = self.run_job([self.proposal(2)])
        self.assertEqual(outcome["status"], "failed", outcome)
        self.assertEqual(self.calls, {"local": 0, "claude": 0})

    def test_extra_action_never_sends_claude(self):
        outcome = self.run_job([self.proposal(1), self.proposal(1)])
        self.assertEqual(outcome["status"], "failed", outcome)
        self.assertEqual(self.calls, {"local": 1, "claude": 0})

    def test_rejected_grant_never_sends(self):
        with patch.object(self.ledger, "consume_grant", return_value=False):
            outcome = self.run_job([self.proposal(1)])
        self.assertEqual(outcome["status"], "failed", outcome)
        self.assertEqual(self.calls, {"local": 0, "claude": 0})

    def test_reused_claude_grant_never_sends(self):
        original = self.ledger.consume_grant

        def consume(action_id, grant_id, generation):
            if self.calls["local"]:
                return False
            return original(action_id, grant_id, generation=generation)

        with patch.object(self.ledger, "consume_grant", side_effect=consume):
            outcome = self.run_job([self.proposal(1), self.proposal(2)])
        self.assertEqual(outcome["status"], "failed", outcome)
        self.assertEqual(self.calls, {"local": 1, "claude": 0})

    def test_exhausted_claude_cap_never_sends(self):
        prior = {**self.env, "attempt_id": "prior-attempt"}
        self.ledger.create_attempt(prior)
        local = action(prior, 1)
        grant = self.ledger.decide(prior, local, generation=1)
        self.assertTrue(self.ledger.consume_grant(local["action_id"], grant["grant_id"], generation=1))
        self.ledger.observe_send(local["action_id"], 1)
        output = "prior plan"
        result = {"schema_version": 1, "status": "completed", "provider": "ollama",
                  "model": prior["assignments"][0]["model"], "physical_call": True,
                  "evidence_level": "flow_observed_local_http_response", "output": output,
                  "output_sha256": hashlib.sha256(output.encode()).hexdigest(), "usage": None}
        self.ledger.observe_response(local["action_id"], result, 1)
        self.ledger.complete(local["action_id"], result, generation=1)
        self.assertTrue(self.ledger.decide(prior, action(prior, 2), generation=1)["allowed"])
        outcome = self.run_job([self.proposal(1), self.proposal(2)])
        self.assertEqual(outcome["status"], "failed", outcome)
        self.assertEqual(self.calls, {"local": 1, "claude": 0})

    def test_post_send_uncertainty_stays_unknown(self):
        outcome = self.run_job([self.proposal(1), self.proposal(2)], fail_claude=True)
        self.assertEqual(outcome["status"], "unknown", outcome)
        self.assertEqual(self.calls, {"local": 1, "claude": 1})


if __name__ == "__main__":
    unittest.main()
