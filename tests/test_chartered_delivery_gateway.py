"""Contract preparation and provider routes for chartered Delivery Lead jobs."""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

from delivery_gateway import (ContractError, _default_worker_adapter,
                              execute_chartered_delivery, prepare_chartered_delivery)
from execution_contracts import envelope_digest, expected_magentic_action_id
from maf_supervisor import MafTransportError


class CharteredPreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run = self.root / ".flow" / "runs" / "sample"
        self.run.mkdir(parents=True)
        self.worktree = self.root / "worktree"
        self.worktree.mkdir()
        subprocess.run(["git", "init", "-q", str(self.worktree)], check=True)
        subprocess.run(["git", "-C", str(self.worktree), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.worktree), "config", "user.name", "Test"], check=True)
        (self.worktree / "target.py").write_text("old\n")
        (self.worktree / "tests").mkdir()
        (self.worktree / "tests" / "test_target.py").write_text("import unittest\n\n\nclass TargetTests(unittest.TestCase):\n    def test_target(self):\n        self.assertTrue(True)\n")
        subprocess.run(["git", "-C", str(self.worktree), "add", "target.py", "tests/test_target.py"], check=True)
        subprocess.run(["git", "-C", str(self.worktree), "commit", "-qm", "source"], check=True)
        self.commit = subprocess.check_output(["git", "-C", str(self.worktree), "rev-parse", "HEAD"], text=True).strip()
        self.charter = {"task": "Edit target.py", "read_paths": ["target.py"], "write_paths": ["target.py"],
                        "test": {"argv": ["/opt/homebrew/bin/python3.12", "-m", "unittest", "discover", "-s", "tests", "-p", "test_target.py"], "timeout_seconds": 30},
                        "producer_instance_ids": ["editor"], "verifier_instance_ids": ["verifier"],
                        "baseline": {"kind": "clean", "diff_sha256": hashlib.sha256(b"").hexdigest()}}
        self.manifest = {"assignments": [
            {"id": "magentic-manager", "lane": "implement", "role": "delivery-lead", "execution": {"provider": "claude", "model": "manager"}},
            {"id": "editor", "lane": "implement", "role": "lead-developer", "execution": {"provider": "codex", "model": "editor-model"}, "read_only": False, "write_scopes": ["target.py"]},
            {"id": "verifier", "lane": "implement", "role": "test-engineer", "execution": {"provider": "ollama", "model": "local-model"}, "read_only": True, "write_scopes": []}]}
        (self.run / "requirements.md").write_text("requirements")
        (self.run / "acceptance.md").write_text("acceptance")
        self.state = {"state": "implementing", "protocol_revision": 2, "artifacts": {
            "job_charter": ".flow/runs/sample/job-charter.json", "orchestration_manifest": ".flow/runs/sample/orchestration.json",
            "requirements": ".flow/runs/sample/requirements.md", "acceptance_criteria": ".flow/runs/sample/acceptance.md"}}
        self._write_inputs()

    def _write_inputs(self):
        (self.run / "job-charter.json").write_text(json.dumps(self.charter))
        (self.run / "orchestration.json").write_text(json.dumps(self.manifest))

    def prepare(self):
        with patch("delivery_gateway.run_status", return_value=self.state), patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            return prepare_chartered_delivery("sample", self.worktree, self.commit, root=self.root)

    def test_clean_job_pins_roster_and_contract(self):
        envelope, task, attempt_dir, ledger = self.prepare()
        self.assertEqual(envelope["execution_protocol_version"], 6)
        self.assertEqual(envelope["job_contract"]["task"], task)
        self.assertEqual([r["capabilities"] for r in envelope["roster"]], [["read", "edit"], ["read"]])
        self.assertTrue((attempt_dir / "job-charter.snapshot.json").is_file())
        self.assertEqual(ledger.snapshot(envelope["attempt_id"])["status"], "started")

    def test_rejects_unapproved_charter_or_provider_permission_mismatch(self):
        self.state["artifacts"].pop("job_charter")
        with self.assertRaisesRegex(ContractError, "approved job charter"):
            self.prepare()
        self.manifest["assignments"][0]["input_evidence"] = [".flow/runs/sample/job-charter.json"]
        self._write_inputs()
        self.assertEqual(self.prepare()[0]["execution_protocol_version"], 6)
        self.state["artifacts"]["job_charter"] = ".flow/runs/sample/job-charter.json"
        self.manifest["assignments"][1]["read_only"] = True
        self._write_inputs()
        with self.assertRaisesRegex(ContractError, "permissions"):
            self.prepare()

    def test_rejects_unsafe_test_and_dirty_baseline(self):
        self.charter["test"]["argv"] = ["sh", "-c", "true"]
        self._write_inputs()
        with self.assertRaisesRegex(ContractError, "test argv"):
            self.prepare()
        self.charter["test"]["argv"] = ["/opt/homebrew/bin/python3.12", "-m", "unittest", "discover", "-s", "tests", "-p", "test_target.py"]
        self._write_inputs()
        (self.worktree / "target.py").write_text("changed\n")
        with self.assertRaisesRegex(ContractError, "not clean"):
            self.prepare()

    def test_no_actions_yields_linked_failed_receipt(self):
        with patch("delivery_gateway.run_status", return_value=self.state), patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            result = execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root,
                                                supervisor=lambda envelope, task, on_manager, on_action, **kwargs: {"attempt_id": envelope["attempt_id"]})
        self.assertEqual(result["status"], "failed")
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(receipt["execution_protocol_version"], 6)

    def _proposal(self, envelope, assignment_id, sequence):
        assignment = next(item for item in envelope["roster"] if item["assignment_id"] == assignment_id)
        checkpoint_id = f"checkpoint-{sequence}"
        action = {"schema_version": 1, "kind": "delegate", "attempt_id": envelope["attempt_id"],
                  "envelope_digest": envelope_digest(envelope), "sequence": sequence,
                  "assignment_id": assignment_id, "definition_digest": assignment["definition_digest"],
                  "instance_id": assignment["instance_id"], "role": assignment["role"],
                  "provider": assignment["provider"], "model": assignment["model"],
                  "manager_turn": sequence, "task": "Edit target.py" if sequence == 1 else "Verify target.py",
                  "rationale": "The selected specialist is eligible for this bounded task.",
                  "parent_action_id": None if sequence == 1 else "a" * 64,
                  "checkpoint_id": checkpoint_id}
        action["task_digest"] = hashlib.sha256(action["task"].encode()).hexdigest()
        action["action_id"] = expected_magentic_action_id(action)
        return action

    @staticmethod
    def _result(provider, model, output):
        return {"schema_version": 1, "status": "completed", "provider": provider, "model": model,
                "physical_call": True,
                "evidence_level": {"codex": "flow_observed_codex_cli_completed_turn",
                                   "ollama": "flow_observed_local_http_response"}[provider],
                "output": output, "output_sha256": hashlib.sha256(output.encode()).hexdigest(), "usage": None}

    def test_v6_gateway_seals_producer_verifier_receipt_after_flow_observes_edit_and_test(self):
        calls = []

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            for sequence, assignment_id in enumerate(("editor", "verifier"), 1):
                proposal = self._proposal(envelope, assignment_id, sequence)
                checkpoint = Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json"
                checkpoint.write_text(json.dumps({"checkpoint_id": proposal["checkpoint_id"],
                                                  "workflow_name": "flow-magentic-delivery-v6",
                                                  "pending_request_info_events": {
                                                      f"flow-magentic-action-{sequence}": {}}}))
                on_action(proposal)
            return {"attempt_id": envelope["attempt_id"]}

        def worker(action, *, envelope, workspace):
            calls.append(action["assignment_id"])
            if action["assignment_id"] == "editor":
                (workspace / "target.py").write_text("new\n")
                return self._result("codex", "editor-model", "Edited target")
            self.assertIn("Flow-verified complete bounded diff", action["provider_task"])
            self.assertIn("Targeted test: passed", action["provider_task"])
            return self._result("ollama", "local-model", "Verified target")

        with patch("delivery_gateway.run_status", return_value=self.state), patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            result = execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root,
                                                supervisor=supervisor, worker_adapter=worker)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(calls, ["editor", "verifier"])
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(receipt["execution_protocol_version"], 6)
        self.assertEqual([item["status"] for item in receipt["actions"]], ["completed", "completed"])
        self.assertEqual(receipt["evidence"]["tests"]["command"], self.charter["test"]["argv"])
        self.assertTrue(receipt["checkpoints"])

    def test_v6_verifier_before_observed_edit_refuses_without_provider_send(self):
        calls = []

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            proposal = self._proposal(envelope, "verifier", 1)
            on_action(proposal)
            return {"attempt_id": envelope["attempt_id"]}

        def worker(*args, **kwargs):
            calls.append(True)
            self.fail("ineligible verifier must not reach provider dispatch")

        with patch("delivery_gateway.run_status", return_value=self.state), patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            result = execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root,
                                                supervisor=supervisor, worker_adapter=worker)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(calls, [])
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(receipt["actions"], [])

    def test_v6_transport_loss_after_producer_seals_nonresumable_receipt(self):
        calls = []

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            proposal = self._proposal(envelope, "editor", 1)
            checkpoint = Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json"
            checkpoint.write_text(json.dumps({"checkpoint_id": proposal["checkpoint_id"],
                                              "workflow_name": "flow-magentic-delivery-v6",
                                              "pending_request_info_events": {"flow-magentic-action-1": {}}}))
            on_action(proposal)
            raise MafTransportError("simulated transport loss after committed producer")

        def worker(action, *, envelope, workspace):
            calls.append(action["assignment_id"])
            (workspace / "target.py").write_text("new\n")
            return self._result("codex", "editor-model", "Edited target")

        with patch("delivery_gateway.run_status", return_value=self.state), \
             patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            result = execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root,
                                                supervisor=supervisor, worker_adapter=worker)
        self.assertEqual(calls, ["editor"])
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result.get("resume_available", False))
        receipt_path = Path(result["receipt_path"])
        self.assertTrue(receipt_path.is_file())
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual([action["status"] for action in receipt["actions"]], ["completed"])
        self.assertEqual(receipt["evidence"]["tests"]["status"], "passed")

    def test_v6_editor_head_drift_halts_after_one_send(self):
        calls = []

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            proposal = self._proposal(envelope, "editor", 1)
            checkpoint = Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json"
            checkpoint.write_text(json.dumps({"checkpoint_id": proposal["checkpoint_id"],
                                              "workflow_name": "flow-magentic-delivery-v6",
                                              "pending_request_info_events": {"flow-magentic-action-1": {}}}))
            on_action(proposal)
            return {"attempt_id": envelope["attempt_id"]}

        def worker(action, *, envelope, workspace):
            calls.append(action["assignment_id"])
            (workspace / "target.py").write_text("new\n")
            subprocess.run(["git", "-C", str(workspace), "commit", "--allow-empty", "-qm", "unapproved HEAD drift"], check=True)
            return self._result("codex", "editor-model", "Edited target")

        with patch("delivery_gateway.run_status", return_value=self.state), \
             patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            result = execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root,
                                                supervisor=supervisor, worker_adapter=worker)
        self.assertEqual(calls, ["editor"])
        self.assertEqual(result["status"], "unknown")
        self.assertIn("pinned source commit", json.loads(Path(result["receipt_path"]).read_text())["failure_detail"])

    def test_v6_second_producer_is_denied_without_second_send(self):
        self.manifest["assignments"].insert(2, {
            "id": "editor-2", "lane": "implement", "role": "architect",
            "execution": {"provider": "codex", "model": "second-model"},
            "read_only": False, "write_scopes": ["target.py"],
        })
        self.charter["producer_instance_ids"].append("editor-2")
        self._write_inputs()
        calls = []

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            first = self._proposal(envelope, "editor", 1)
            checkpoint = Path(envelope["checkpoint_dir"]) / f"{first['checkpoint_id']}.json"
            checkpoint.write_text(json.dumps({"checkpoint_id": first["checkpoint_id"],
                                              "workflow_name": "flow-magentic-delivery-v6",
                                              "pending_request_info_events": {"flow-magentic-action-1": {}}}))
            self.assertEqual(on_action(first)["status"], "completed")
            second = self._proposal(envelope, "editor-2", 2)
            denied = on_action(second)
            self.assertEqual(denied["status"], "denied")
            self.assertEqual(denied["reason"], "producer_already_completed")
            return {"attempt_id": envelope["attempt_id"]}

        def worker(action, *, envelope, workspace):
            calls.append(action["assignment_id"])
            if action["assignment_id"] != "editor":
                self.fail("second producer must not reach a provider")
            (workspace / "target.py").write_text("new\n")
            return self._result("codex", "editor-model", "Edited target")

        with patch("delivery_gateway.run_status", return_value=self.state), \
             patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            result = execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root,
                                                supervisor=supervisor, worker_adapter=worker)
        self.assertEqual(calls, ["editor"])
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual([action["status"] for action in receipt["actions"]], ["completed", "denied"])


class ProviderRouteTests(unittest.TestCase):
    def test_codex_and_claude_direct_routes(self):
        with tempfile.TemporaryDirectory() as dirname:
            workspace = Path(dirname)
            roster = [{"assignment_id": "editor", "instructions": "do task", "model": "pinned"}]
            envelope = {"execution_protocol_version": 6, "roster": roster}
            action = {"assignment_id": "editor", "provider": "codex", "task": "edit"}
            with patch("delivery_gateway.call_codex", return_value={"provider": "codex"}) as codex:
                self.assertEqual(_default_worker_adapter(action, envelope=envelope, workspace=workspace)["provider"], "codex")
                codex.assert_called_once()
            action["provider"] = "claude"
            with patch("delivery_gateway.call_claude_edit", return_value={"provider": "claude"}) as claude:
                self.assertEqual(_default_worker_adapter(action, envelope=envelope, workspace=workspace)["provider"], "claude")
                claude.assert_called_once()


if __name__ == "__main__":
    unittest.main()
