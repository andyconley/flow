"""Contract preparation and provider routes for chartered Delivery Lead jobs."""

import copy
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
                              _execute_prepared_delivery, execute_chartered_delivery,
                              prepare_chartered_delivery)
from execution_contracts import ContractError as ExecutionContractError, envelope_digest, expected_magentic_action_id, validate_action
from delivery_contracts import build_delivery_charter, build_shaper_contract, digest as delivery_digest
from delivery_control import change_lead_claim
from maf_supervisor import MafTransportError
from tests.shaper_intent_fixture import shaper_intent


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
                        "test": {"argv": ["python3", "-m", "unittest", "discover", "-s", "tests", "-p", "test_target.py"], "timeout_seconds": 30},
                        "producer_instance_ids": ["editor"], "verifier_instance_ids": ["verifier"],
                        "baseline": {"kind": "clean", "diff_sha256": hashlib.sha256(b"").hexdigest()}}
        self.manifest = {"assignments": [
            {"id": "magentic-manager", "lane": "implement", "role": "delivery-lead", "execution": {"provider": "claude", "model": "manager"}},
            {"id": "editor", "lane": "implement", "role": "lead-developer", "execution": {"provider": "codex", "model": "editor-model"}, "read_only": False, "write_scopes": ["target.py"]},
            {"id": "verifier", "lane": "implement", "role": "test-engineer", "execution": {"provider": "ollama", "model": "local-model"}, "read_only": True, "write_scopes": []}]}
        (self.run / "requirements.md").write_text("requirements")
        (self.run / "acceptance.md").write_text("acceptance")
        definition_digests = {
            role: delivery_digest({"role": role, "instructions": "instructions for " + role})
            for role in ("lead-developer", "quality-reviewer", "test-engineer")
        }
        self.intent = shaper_intent(definition_digests)
        (self.run / "shaper-intent.json").write_text(json.dumps(self.intent))
        self.state = {"state": "implementing", "protocol_revision": 2, "artifacts": {
            "job_charter": ".flow/runs/sample/job-charter.json", "orchestration_manifest": ".flow/runs/sample/orchestration.json",
            "requirements": ".flow/runs/sample/requirements.md", "acceptance_criteria": ".flow/runs/sample/acceptance.md",
            "shaper_intent": ".flow/runs/sample/shaper-intent.json"}}
        self._write_inputs()
        self._write_delivery_authority()

    def _write_inputs(self):
        (self.run / "job-charter.json").write_text(json.dumps(self.charter))
        (self.run / "orchestration.json").write_text(json.dumps(self.manifest))

    def _write_delivery_authority(self):
        sources = {
            "requirements": {"path": ".flow/runs/sample/requirements.md", "sha256": hashlib.sha256((self.run / "requirements.md").read_bytes()).hexdigest()},
            "acceptance_criteria": {"path": ".flow/runs/sample/acceptance.md", "sha256": hashlib.sha256((self.run / "acceptance.md").read_bytes()).hexdigest()},
            "shaper_intent": {"path": ".flow/runs/sample/shaper-intent.json", "sha256": hashlib.sha256((self.run / "shaper-intent.json").read_bytes()).hexdigest()},
        }
        shaper = build_shaper_contract("sample", sources, self.intent)
        charter = build_delivery_charter(shaper)
        handoff = {"schema_version": 1, "kind": "definition_to_delivery_handoff", "run_id": "sample",
                   "shaper_contract_id": shaper["shaper_contract_id"], "shaper_contract_digest": shaper["digest"],
                   "delivery_charter_id": charter["charter_id"], "delivery_charter_digest": charter["digest"],
                   "source_digests": sources, "transition": "start-plan"}
        handoff["digest"] = delivery_digest(handoff)
        claim = {"schema_version": 1, "kind": "delivery_lead_claim", "logical_delivery_attempt_id": "logical-test",
                 "owner": "delivery-lead", "generation": 1, "status": "active", "charter_digest": charter["digest"], "supersedes": None}
        claim["digest"] = delivery_digest(claim)
        artifact_rel = f"delivery/{charter['digest']}"
        delivery_dir = self.run / artifact_rel
        delivery_dir.mkdir(parents=True, exist_ok=True)
        for name, payload in (("shaper-contract.json", shaper), ("delivery-charter.json", charter),
                              ("handoff.json", handoff), ("lead-claim.json", claim)):
            (delivery_dir / name).write_text(json.dumps(payload))
        self.state["delivery"] = {"shaper_contract_digest": shaper["digest"], "charter_digest": charter["digest"],
                                  "handoff_digest": handoff["digest"], "lead_claim_digest": claim["digest"],
                                  "lead_claim_path": f"{artifact_rel}/lead-claim.json",
                                  "delivery_artifact_dir": artifact_rel, "owner_generation": 1,
                                  "owner_status": "active", "source_digests": sources,
                                  "logical_delivery_attempt_id": "logical-test"}
        (self.run / "run.json").write_text(json.dumps(self.state))

    def prepare(self):
        with patch("delivery_gateway.run_status", return_value=self.state), patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            return prepare_chartered_delivery("sample", self.worktree, self.commit, root=self.root)

    def test_clean_job_pins_roster_and_contract(self):
        envelope, task, attempt_dir, ledger = self.prepare()
        self.assertEqual(envelope["execution_protocol_version"], 7)
        self.assertEqual(envelope["job_contract"]["task"], task)
        self.assertEqual([r["capabilities"] for r in envelope["roster"]], [["read", "edit"], ["read"]])
        self.assertTrue((attempt_dir / "job-charter.snapshot.json").is_file())
        self.assertEqual(ledger.snapshot(envelope["attempt_id"])["status"], "started")

    def test_changed_effective_specialist_definition_is_outside_sealed_charter(self):
        with patch("delivery_gateway.run_status", return_value=self.state), \
             patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "changed instructions for " + role):
            with self.assertRaisesRegex(ContractError, "expands the sealed Delivery Charter"):
                prepare_chartered_delivery("sample", self.worktree, self.commit, root=self.root)

    def test_read_only_approved_role_cannot_be_projected_as_editor(self):
        for specialist in self.intent["allowed_specialists"]:
            if specialist["role"] == "lead-developer":
                specialist["capabilities"] = ["read-only-review"]
        (self.run / "shaper-intent.json").write_text(json.dumps(self.intent))
        self._write_delivery_authority()
        with self.assertRaisesRegex(ContractError, "expands the sealed Delivery Charter"):
            self.prepare()

    def test_runtime_limits_are_projected_from_the_sealed_charter(self):
        self.intent["delegation_matrix"]["max_delegations"] = 2
        enforceable = self.intent["budget_safety_envelope"]["enforceable"]
        enforceable.update(max_concurrent=1, max_replans=0, max_paid_worker_calls=2)
        (self.run / "shaper-intent.json").write_text(json.dumps(self.intent))
        self._write_delivery_authority()
        envelope, _, _, _ = self.prepare()
        self.assertEqual(envelope["limits"], {"max_delegations": 2, "max_concurrent": 1,
                         "max_replans": 0, "max_manager_calls": 12,
                         "max_manager_rounds": 6, "max_paid_worker_calls": 2,
                         "max_runtime_seconds": 300})

    def test_v7_projects_ownership_and_requires_auditable_provider_choice(self):
        envelope, _, _, _ = self.prepare()
        self.assertEqual(envelope["delivery_lead_claim"], {"lead_id": "delivery-lead", "generation": 1})
        for field in ("shaper_contract_digest", "delivery_charter_digest", "handoff_digest", "delivery_lead_claim_digest"):
            self.assertEqual(len(envelope[field]), 64)
        action = self._proposal(envelope, "editor", 1)
        validate_action(envelope, action)
        invalid = copy.deepcopy(action)
        invalid["provider_choice"].pop("rejection_reasons")
        invalid["action_id"] = expected_magentic_action_id(invalid)
        with self.assertRaisesRegex(ExecutionContractError, "provider choice"):
            validate_action(envelope, invalid)

    def test_v7_tampered_sealed_handoff_refuses_before_attempt_or_send(self):
        handoff = self.run / self.state["delivery"]["delivery_artifact_dir"] / "handoff.json"
        value = json.loads(handoff.read_text())
        value["transition"] = "tampered"
        handoff.write_text(json.dumps(value))
        with self.assertRaisesRegex(ContractError, "handoff digest"):
            self.prepare()
        self.assertFalse((self.run / "execution").exists())

    def test_v7_supersede_after_preparation_blocks_worker_and_receipt_seal(self):
        envelope, task, attempt_dir, ledger = self.prepare()
        changed, _, errors = change_lead_claim("sample", "supersede", root=self.root, owner="replacement")
        self.assertTrue(changed, errors)
        calls = []

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            proposal = self._proposal(envelope, "editor", 1)
            checkpoint = Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json"
            checkpoint.write_text(json.dumps({"checkpoint_id": proposal["checkpoint_id"],
                                              "workflow_name": "flow-magentic-delivery-v7",
                                              "pending_request_info_events": {"flow-magentic-action-1": {}}}))
            on_action(proposal)
            return {"attempt_id": envelope["attempt_id"]}

        with self.assertRaisesRegex(Exception, "generation is stale"):
            _execute_prepared_delivery(envelope, task, attempt_dir, ledger, manager_adapter=None,
                                       worker_adapter=lambda *args, **kwargs: calls.append(True),
                                       supervisor=supervisor, test_runner=None, python_path=None,
                                       generation=envelope["delivery_lead_claim"]["generation"])
        self.assertEqual(calls, [])
        self.assertFalse((attempt_dir / "receipt.json").exists())

    def test_rejects_unapproved_charter_or_provider_permission_mismatch(self):
        self.state["artifacts"].pop("job_charter")
        with self.assertRaisesRegex(ContractError, "approved job charter"):
            self.prepare()
        self.manifest["assignments"][0]["input_evidence"] = [".flow/runs/sample/job-charter.json"]
        self._write_inputs()
        self.assertEqual(self.prepare()[0]["execution_protocol_version"], 7)
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
        self.charter["test"]["argv"] = ["python3", "-m", "unittest", "discover", "-s", "tests", "-p", "test_target.py"]
        self._write_inputs()
        (self.worktree / "target.py").write_text("changed\n")
        with self.assertRaisesRegex(ContractError, "not clean"):
            self.prepare()

    def test_invalid_charter_intake_refuses_before_any_provider_send(self):
        original_charter = copy.deepcopy(self.charter)
        original_manifest = copy.deepcopy(self.manifest)
        cases = {
            "unknown_producer": lambda: self.charter.update(producer_instance_ids=["missing"]),
            "duplicate_instance": lambda: self.manifest["assignments"].append(copy.deepcopy(self.manifest["assignments"][1])),
            "roster_expansion": lambda: self.manifest["assignments"].extend(
                {"id": f"reader-{number}", "lane": "implement", "role": "test-engineer",
                 "execution": {"provider": "ollama", "model": "local"}, "read_only": True,
                 "write_scopes": []} for number in range(5)),
            "unsafe_scope": lambda: self.charter.update(write_paths=["../outside.py"]),
            "unsafe_command": lambda: self.charter["test"].update(argv=["sh", "-c", "true"]),
            "provider_permission_mismatch": lambda: self.manifest["assignments"][1].update(read_only=True),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                self.charter = copy.deepcopy(original_charter)
                self.manifest = copy.deepcopy(original_manifest)
                mutate()
                self._write_inputs()
                sends = []
                with patch("delivery_gateway.run_status", return_value=self.state), \
                     patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
                     patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
                    with self.assertRaises(ContractError):
                        execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root,
                                                   worker_adapter=lambda *args, **kwargs: sends.append(True))
                self.assertEqual(sends, [])

        sends = []
        self.charter = copy.deepcopy(original_charter)
        self.manifest = copy.deepcopy(original_manifest)
        self._write_inputs()
        with patch("delivery_gateway.run_status", return_value=self.state), \
             patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            with self.assertRaises(ContractError):
                execute_chartered_delivery("sample", self.worktree, "0" * 40, root=self.root,
                                           worker_adapter=lambda *args, **kwargs: sends.append(True))
        self.assertEqual(sends, [], "a stale source commit must fail before dispatch")

    def test_changed_charter_or_manifest_during_preparation_refuses_before_send(self):
        sends = []

        def snapshot(path, data):
            path.write_bytes(data)
            if path.name == "job-charter.snapshot.json":
                (self.run / "orchestration.json").write_text('{"assignments": []}')

        with patch("delivery_gateway.run_status", return_value=self.state), \
             patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role), \
             patch("delivery_gateway._write_snapshot", side_effect=snapshot):
            with self.assertRaisesRegex(ContractError, "source changed"):
                execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root,
                                           worker_adapter=lambda *args, **kwargs: sends.append(True))
        self.assertEqual(sends, [])

    def test_no_actions_yields_linked_failed_receipt(self):
        with patch("delivery_gateway.run_status", return_value=self.state), patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            result = execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root,
                                                supervisor=lambda envelope, task, on_manager, on_action, **kwargs: {"attempt_id": envelope["attempt_id"]})
        self.assertEqual(result["status"], "failed")
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(receipt["execution_protocol_version"], 7)

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
        if envelope["execution_protocol_version"] == 7:
            eligible_ids = (envelope["job_contract"]["producer_instance_ids"]
                            if assignment_id in envelope["job_contract"]["producer_instance_ids"]
                            else envelope["job_contract"]["verifier_instance_ids"])
            eligible = [{key: next(item for item in envelope["roster"] if item["instance_id"] == instance)[key]
                         for key in ("assignment_id", "definition_digest", "instance_id", "role", "provider", "model")}
                        for instance in eligible_ids]
            action["provider_choice"] = {
                "eligible_candidates": eligible, "selected_candidate": assignment["instance_id"],
                "rationale": {"manager_reason": action["rationale"], "facts": ["approved specialist identity"]},
                "rejection_reasons": {candidate["instance_id"]: {"reason": "Magentic selected another approved candidate.",
                                                                    "facts": ["approved candidate not selected"]}
                                      for candidate in eligible if candidate["instance_id"] != assignment["instance_id"]}}
        action["action_id"] = expected_magentic_action_id(action)
        return action

    @staticmethod
    def _result(provider, model, output):
        return {"schema_version": 1, "status": "completed", "provider": provider, "model": model,
                "physical_call": True,
                "evidence_level": {"codex": "flow_observed_codex_cli_completed_turn",
                                   "claude": "flow_observed_claude_cli_completed_turn",
                                   "ollama": "flow_observed_local_http_response"}[provider],
                "output": output, "output_sha256": hashlib.sha256(output.encode()).hexdigest(), "usage": None}

    def test_v7_gateway_seals_producer_verifier_receipt_after_flow_observes_edit_and_test(self):
        calls = []

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            self.assertEqual(kwargs["timeout_s"], 300)
            for sequence, assignment_id in enumerate(("editor", "verifier"), 1):
                proposal = self._proposal(envelope, assignment_id, sequence)
                checkpoint = Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json"
                checkpoint.write_text(json.dumps({"checkpoint_id": proposal["checkpoint_id"],
                                                  "workflow_name": "flow-magentic-delivery-v7",
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
        self.assertEqual(receipt["execution_protocol_version"], 7)
        self.assertEqual([item["status"] for item in receipt["actions"]], ["completed", "completed"])
        self.assertEqual(receipt["evidence"]["tests"]["command"], self.charter["test"]["argv"])
        self.assertTrue(receipt["checkpoints"])

    def test_v7_claude_producer_runs_under_flow_grant_before_verifier(self):
        self.manifest["assignments"][1]["execution"] = {"provider": "claude", "model": "claude-model"}
        self._write_inputs()
        calls = []

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            for sequence, assignment_id in enumerate(("editor", "verifier"), 1):
                proposal = self._proposal(envelope, assignment_id, sequence)
                checkpoint = Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json"
                checkpoint.write_text(json.dumps({"checkpoint_id": proposal["checkpoint_id"],
                                                  "workflow_name": "flow-magentic-delivery-v7",
                                                  "pending_request_info_events": {
                                                      f"flow-magentic-action-{sequence}": {}}}))
                self.assertEqual(on_action(proposal)["status"], "completed")
            return {"attempt_id": envelope["attempt_id"]}

        def worker(action, *, envelope, workspace):
            calls.append(action["assignment_id"])
            if action["assignment_id"] == "editor":
                (workspace / "target.py").write_text("new\n")
                return {**self._result("claude", "claude-model", "Edited target"),
                        "session_id": "claude-session-1"}
            self.assertIn("Flow-verified complete bounded diff", action["provider_task"])
            return self._result("ollama", "local-model", "Verified target")

        with patch("delivery_gateway.run_status", return_value=self.state), \
             patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            result = execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root,
                                                supervisor=supervisor, worker_adapter=worker)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(calls, ["editor", "verifier"])
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(receipt["actions"][0]["request"]["provider"], "claude")
        self.assertEqual(receipt["actions"][0]["result"]["session_id"], "claude-session-1")
        self.assertEqual([action["status"] for action in receipt["actions"]], ["completed", "completed"])
        self.assertEqual(receipt["evidence"]["tests"]["status"], "passed")

    def test_v7_verifier_before_observed_edit_refuses_without_provider_send(self):
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

    def test_v7_failed_test_keeps_observed_worker_completed(self):
        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            proposal = self._proposal(envelope, "editor", 1)
            checkpoint = Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json"
            checkpoint.write_text(json.dumps({"checkpoint_id": proposal["checkpoint_id"],
                                              "workflow_name": "flow-magentic-delivery-v7",
                                              "pending_request_info_events": {"flow-magentic-action-1": {}}}))
            on_action(proposal)
            return {"attempt_id": envelope["attempt_id"]}

        def worker(action, *, envelope, workspace):
            (workspace / "target.py").write_text("new\n")
            return self._result("codex", "editor-model", "Edited target")

        with patch("delivery_gateway.run_status", return_value=self.state), \
             patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role), \
             patch("delivery_gateway._run_chartered_test", side_effect=ContractError("targeted test failed")):
            result = execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root,
                                                supervisor=supervisor, worker_adapter=worker)
        self.assertEqual(result["status"], "failed")
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual([action["status"] for action in receipt["actions"]], ["completed"])
        self.assertIsNotNone(receipt["evidence"]["edit"])
        self.assertIsNone(receipt["evidence"]["tests"])

    def test_v7_transport_loss_after_producer_seals_nonresumable_receipt(self):
        calls = []

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            proposal = self._proposal(envelope, "editor", 1)
            checkpoint = Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json"
            checkpoint.write_text(json.dumps({"checkpoint_id": proposal["checkpoint_id"],
                                              "workflow_name": "flow-magentic-delivery-v7",
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

    def test_v7_editor_head_drift_halts_after_one_send(self):
        calls = []

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            proposal = self._proposal(envelope, "editor", 1)
            checkpoint = Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json"
            checkpoint.write_text(json.dumps({"checkpoint_id": proposal["checkpoint_id"],
                                              "workflow_name": "flow-magentic-delivery-v7",
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
        self.assertEqual(result["status"], "failed")
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(receipt["actions"][0]["status"], "completed")
        self.assertIn("pinned source commit", receipt["failure_detail"])

    def test_v7_roster_expansion_beyond_sealed_charter_is_rejected_before_send(self):
        self.manifest["assignments"].insert(2, {
            "id": "editor-2", "lane": "implement", "role": "architect",
            "execution": {"provider": "codex", "model": "second-model"},
            "read_only": False, "write_scopes": ["target.py"],
        })
        self.charter["producer_instance_ids"].append("editor-2")
        self._write_inputs()
        with patch("delivery_gateway.run_status", return_value=self.state), \
             patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            with self.assertRaisesRegex(ContractError, "roster expands"):
                execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root,
                                          worker_adapter=lambda *args, **kwargs: self.fail("must not send"))

    def test_v7_duplicate_grant_replays_without_a_second_provider_send(self):
        calls = []

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            proposal = self._proposal(envelope, "editor", 1)
            checkpoint = Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json"
            checkpoint.write_text(json.dumps({"checkpoint_id": proposal["checkpoint_id"],
                                              "workflow_name": "flow-magentic-delivery-v7",
                                              "pending_request_info_events": {"flow-magentic-action-1": {}}}))
            self.assertEqual(on_action(proposal)["status"], "completed")
            self.assertEqual(on_action(proposal)["status"], "completed")
            return {"attempt_id": envelope["attempt_id"]}

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

    def test_v7_provider_substitution_is_rejected_before_send(self):
        calls = []

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            proposal = self._proposal(envelope, "editor", 1)
            proposal["provider"] = "claude"
            with self.assertRaises(ContractError):
                on_action(proposal)
            return {"attempt_id": envelope["attempt_id"]}

        with patch("delivery_gateway.run_status", return_value=self.state), \
             patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            result = execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root,
                                                supervisor=supervisor,
                                                worker_adapter=lambda *args, **kwargs: calls.append(True))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(calls, [])

    def test_v7_unapproved_roster_instance_is_rejected_before_send(self):
        self.manifest["assignments"].append({
            "id": "analyst", "lane": "implement", "role": "test-engineer",
            "execution": {"provider": "ollama", "model": "local-model"}, "read_only": True,
            "write_scopes": [],
        })
        self._write_inputs()
        with patch("delivery_gateway.run_status", return_value=self.state), \
             patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            with self.assertRaisesRegex(ContractError, "roster expands"):
                execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root,
                                          worker_adapter=lambda *args, **kwargs: self.fail("must not send"))


class ProviderRouteTests(unittest.TestCase):
    def test_codex_and_claude_direct_routes(self):
        with tempfile.TemporaryDirectory() as dirname:
            workspace = Path(dirname)
            roster = [{"assignment_id": "editor", "instructions": "do task", "model": "pinned",
                       "provider": "codex"}]
            envelope = {"execution_protocol_version": 7, "attempt_id": "attempt", "roster": roster,
                        "limits": {"max_runtime_seconds": 45}}
            action = {"action_id": "action", "assignment_id": "editor", "provider": "codex", "task": "edit"}
            with patch("delivery_gateway.call_codex", return_value={"provider": "codex"}) as codex:
                self.assertEqual(_default_worker_adapter(action, envelope=envelope, workspace=workspace)["provider"], "codex")
                self.assertEqual(codex.call_args.kwargs["timeout_seconds"], 45)
            action["provider"] = "claude"
            with patch("delivery_gateway.call_claude_edit", return_value={"provider": "claude"}) as claude:
                self.assertEqual(_default_worker_adapter(action, envelope=envelope, workspace=workspace)["provider"], "claude")
                self.assertEqual(claude.call_args.kwargs["timeout_seconds"], 45)
            action["provider"] = "ollama"
            with patch("delivery_gateway.call_local", return_value={"provider": "ollama"}) as ollama:
                self.assertEqual(_default_worker_adapter(action, envelope=envelope, workspace=workspace)["provider"], "ollama")
                self.assertEqual(ollama.call_args.kwargs["timeout_seconds"], 45)


if __name__ == "__main__":
    unittest.main()
