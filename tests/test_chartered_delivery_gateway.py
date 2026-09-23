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
from execution_contracts import (ContractError as ExecutionContractError, envelope_digest,
                                 expected_magentic_action_id, validate_action, validate_envelope,
                                 validate_receipt)
from delivery_contracts import build_delivery_charter, build_shaper_contract, digest as delivery_digest
from delivery_control import change_lead_claim
from maf_supervisor import MafTransportError
from tests.shaper_intent_fixture import shaper_intent
from execution_ledger import ExecutionLedger
from verifier_contracts import VERIFIER_CONTRACT_INSTRUCTION, digest as verifier_digest, evaluate_candidate
import delivery_gateway


class KillPoint(BaseException):
    """Simulated process death; escapes the gateway's ``except Exception`` handlers."""


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
        self.assertEqual(envelope["execution_protocol_version"], 8)
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
                         "max_runtime_seconds": 300, "max_verifier_calls": 2})

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
                                              "workflow_name": "flow-magentic-delivery-v8",
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
        self.assertEqual(self.prepare()[0]["execution_protocol_version"], 8)
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
        self.assertEqual(receipt["execution_protocol_version"], 8)

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
        if envelope["execution_protocol_version"] in {7, 8}:
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
        captured = {}

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            captured["envelope"] = envelope
            self.assertEqual(kwargs["timeout_s"], 300)
            for sequence, assignment_id in enumerate(("editor", "verifier"), 1):
                proposal = self._proposal(envelope, assignment_id, sequence)
                checkpoint = Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json"
                checkpoint.write_text(json.dumps({"checkpoint_id": proposal["checkpoint_id"],
                                                  "workflow_name": "flow-magentic-delivery-v8",
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
            return self._result("ollama", "local-model", '{"schema_version":1,"decision":"pass","summary":"Verified target","findings":[]}')

        with patch("delivery_gateway.run_status", return_value=self.state), patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            result = execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root,
                                                supervisor=supervisor, worker_adapter=worker)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(calls, ["editor", "verifier"])
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(receipt["execution_protocol_version"], 8)
        self.assertEqual([item["status"] for item in receipt["actions"]], ["completed", "completed"])
        self.assertEqual(receipt["evidence"]["tests"]["command"], self.charter["test"]["argv"])
        self.assertTrue(receipt["checkpoints"])
        for field, value in (("consumed", 0), ("denied", 1), ("retry_eligible", True)):
            with self.subTest(field=field):
                tampered = copy.deepcopy(receipt)
                tampered["verifier_usage"][field] = value
                with self.assertRaisesRegex(ExecutionContractError, "usage differs"):
                    validate_receipt(captured["envelope"], tampered)
        tampered = copy.deepcopy(receipt)
        tampered["verifier_inputs"][0]["diff_digest"] = "0" * 64
        with self.assertRaisesRegex(ExecutionContractError, "binding"):
            validate_receipt(captured["envelope"], tampered)

    def test_v7_claude_producer_runs_under_flow_grant_before_verifier(self):
        self.manifest["assignments"][1]["execution"] = {"provider": "claude", "model": "claude-model"}
        self._write_inputs()
        calls = []

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            for sequence, assignment_id in enumerate(("editor", "verifier"), 1):
                proposal = self._proposal(envelope, assignment_id, sequence)
                checkpoint = Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json"
                checkpoint.write_text(json.dumps({"checkpoint_id": proposal["checkpoint_id"],
                                                  "workflow_name": "flow-magentic-delivery-v8",
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
            return self._result("ollama", "local-model", '{"schema_version":1,"decision":"pass","summary":"Verified target","findings":[]}')

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

    def test_v8_first_fail_then_explicit_retry_pass_completes(self):
        calls = []

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            for sequence, assignment_id in enumerate(("editor", "verifier", "verifier"), 1):
                proposal = self._proposal(envelope, assignment_id, sequence)
                checkpoint = Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json"
                checkpoint.write_text(json.dumps({"checkpoint_id": proposal["checkpoint_id"],
                                                  "workflow_name": "flow-magentic-delivery-v8",
                                                  "pending_request_info_events": {
                                                      f"flow-magentic-action-{sequence}": {}}}))
                reply = on_action(proposal)
                self.assertEqual(reply["status"], "completed")
                if sequence == 2:
                    self.assertIn("valid_fail", reply["summary"])
                    self.assertIn("retry eligible: true", reply["summary"])
            return {"attempt_id": envelope["attempt_id"]}

        def worker(action, *, envelope, workspace):
            calls.append(action["assignment_id"])
            if action["assignment_id"] == "editor":
                (workspace / "target.py").write_text("new\n")
                return self._result("codex", "editor-model", "Edited target")
            decision = "fail" if calls.count("verifier") == 1 else "pass"
            findings = '[{"severity":"blocking","summary":"repair","evidence":"test"}]' if decision == "fail" else "[]"
            return self._result("ollama", "local-model",
                                f'{{"schema_version":1,"decision":"{decision}","summary":"review","findings":{findings}}}')

        with patch("delivery_gateway.run_status", return_value=self.state), \
             patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            result = execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root,
                                                supervisor=supervisor, worker_adapter=worker)
        self.assertEqual(result["status"], "completed")
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual([item["outcome"] for item in receipt["verifier_evaluations"]], ["valid_fail", "valid_pass"])
        self.assertEqual(receipt["verifier_usage"], {"maximum": 2, "reserved": 2, "consumed": 2,
                                                     "denied": 0, "retry_eligible": False})

    def test_v8_two_nonpasses_are_terminal_and_third_proposal_is_denied(self):
        sends = []

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            for sequence, assignment_id in enumerate(("editor", "verifier", "verifier", "verifier"), 1):
                proposal = self._proposal(envelope, assignment_id, sequence)
                checkpoint = Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json"
                checkpoint.write_text(json.dumps({"checkpoint_id": proposal["checkpoint_id"],
                                                  "workflow_name": "flow-magentic-delivery-v8",
                                                  "pending_request_info_events": {
                                                      f"flow-magentic-action-{sequence}": {}}}))
                reply = on_action(proposal)
                if sequence == 4:
                    self.assertEqual(reply["status"], "denied")
            return {"attempt_id": envelope["attempt_id"]}

        def worker(action, *, envelope, workspace):
            sends.append(action["assignment_id"])
            if action["assignment_id"] == "editor":
                (workspace / "target.py").write_text("new\n")
                return self._result("codex", "editor-model", "Edited target")
            return self._result("ollama", "local-model", '{"schema_version":1,"decision":"fail","summary":"repair","findings":[{"severity":"blocking","summary":"bad","evidence":"test"}]}')

        with patch("delivery_gateway.run_status", return_value=self.state), \
             patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            result = execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root,
                                                supervisor=supervisor, worker_adapter=worker)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(sends, ["editor", "verifier", "verifier"])
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(receipt["verifier_usage"]["denied"], 1)

    def test_v8_provider_mismatch_is_unusable_then_retry_can_pass(self):
        verifier_calls = 0

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            for sequence, assignment_id in enumerate(("editor", "verifier", "verifier"), 1):
                proposal = self._proposal(envelope, assignment_id, sequence)
                checkpoint = Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json"
                checkpoint.write_text(json.dumps({"checkpoint_id": proposal["checkpoint_id"],
                                                  "workflow_name": "flow-magentic-delivery-v8",
                                                  "pending_request_info_events": {
                                                      f"flow-magentic-action-{sequence}": {}}}))
                reply = on_action(proposal)
                if sequence == 2:
                    self.assertIn("unusable", reply["summary"])
                    self.assertIn("provider_binding_mismatch", reply["summary"])
            return {"attempt_id": envelope["attempt_id"]}

        def worker(action, *, envelope, workspace):
            nonlocal verifier_calls
            if action["assignment_id"] == "editor":
                (workspace / "target.py").write_text("new\n")
                return self._result("codex", "editor-model", "Edited target")
            verifier_calls += 1
            result = self._result("ollama", "local-model", '{"schema_version":1,"decision":"pass","summary":"ok","findings":[]}')
            if verifier_calls == 1:
                result["provider"] = "claude"
            return result

        with patch("delivery_gateway.run_status", return_value=self.state), \
             patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            result = execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root,
                                                supervisor=supervisor, worker_adapter=worker)
        self.assertEqual(result["status"], "completed")
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual([item["outcome"] for item in receipt["verifier_evaluations"]], ["unusable", "valid_pass"])

    PASS = '{"schema_version":1,"decision":"pass","summary":"ok","findings":[]}'
    FAIL = '{"schema_version":1,"decision":"fail","summary":"repair","findings":[{"severity":"blocking","summary":"bad","evidence":"test"}]}'

    def _run_v8(self, verifier_outputs, *, plan=("editor", "verifier"), on_reply=None, repeat=None, seal_hook=None):
        """Drive one v8 attempt; ``repeat`` re-proposes that sequence once after an error."""
        sends, replies, captured = [], {}, {}
        outputs = list(verifier_outputs)

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            captured["envelope"] = envelope
            for sequence, assignment_id in enumerate(plan, 1):
                proposal = self._proposal(envelope, assignment_id, sequence)
                checkpoint = Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json"
                checkpoint.write_text(json.dumps({"checkpoint_id": proposal["checkpoint_id"],
                                                  "workflow_name": "flow-magentic-delivery-v8",
                                                  "pending_request_info_events": {f"flow-magentic-action-{sequence}": {}}}))
                try:
                    replies[sequence] = on_action(proposal)
                except Exception as exc:
                    if sequence != repeat:
                        raise
                    captured["first_error"] = str(exc)
                    replies[sequence] = on_action(proposal)
            return {"attempt_id": envelope["attempt_id"]}

        def worker(action, *, envelope, workspace):
            sends.append(action["assignment_id"])
            if action["assignment_id"] == "editor":
                (workspace / "target.py").write_text("new\n")
                return self._result("codex", "editor-model", "Edited target")
            captured.setdefault("provider_tasks", []).append(action["provider_task"])
            return self._result("ollama", "local-model", outputs.pop(0))

        with patch("delivery_gateway.run_status", return_value=self.state), \
             patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            result = execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root,
                                                supervisor=supervisor, worker_adapter=worker, seal_hook=seal_hook)
        return result, sends, replies, captured

    def test_v8_seal_hook_reaches_each_sealing_boundary_after_the_runtime_outcome(self):
        points = []
        result, _, _, captured = self._run_v8([self.PASS], seal_hook=points.append)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(points, ["after-runtime-outcome", "after-receipt-draft", "before-finish-attempt"])
        attempt_dir = Path(result["receipt_path"]).parent
        snapshot = ExecutionLedger(attempt_dir.parent / "ledger.sqlite", read_only=True).snapshot(result["attempt_id"])
        outcomes = [json.loads(item["detail"]) for item in snapshot["events"] if item["event"] == "runtime_outcome_recorded"]
        self.assertEqual(outcomes, [{"failure": "", "generation": 1, "transport": False}])
        self.assertEqual(snapshot["sealed_receipt_sha256"],
                         hashlib.sha256(Path(result["receipt_path"]).read_bytes()).hexdigest())

    def test_v8_kill_before_finish_leaves_an_unsealed_draft_and_a_started_attempt(self):
        def kill(point):
            if point == "before-finish-attempt":
                raise KillPoint(point)

        with self.assertRaises(KillPoint):
            self._run_v8([self.PASS], seal_hook=kill)
        attempt_dir = next((self.run / "execution").glob("*/envelope.json")).parent
        snapshot = ExecutionLedger(attempt_dir.parent / "ledger.sqlite", read_only=True).snapshot(attempt_dir.name)
        self.assertEqual(snapshot["status"], "started")
        self.assertIsNone(snapshot["sealed_receipt_sha256"])
        self.assertTrue((attempt_dir / "receipt.json").is_file())

    def test_v8_verifier_input_carries_the_flow_output_contract(self):
        result, _, _, captured = self._run_v8([self.PASS])
        self.assertEqual(result["status"], "completed")
        self.assertTrue(captured["provider_tasks"][0].endswith(VERIFIER_CONTRACT_INSTRUCTION))
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertTrue(receipt["verifier_inputs"][0]["input"]["provider_task"].endswith(VERIFIER_CONTRACT_INSTRUCTION))
        validate_receipt(captured["envelope"], receipt)

    def test_v8_completed_verifier_without_evaluation_is_reevaluated_on_replay_without_resend(self):
        original = ExecutionLedger.record_verifier_evaluation
        calls = []

        def crash_once(ledger, *args, **kwargs):
            calls.append(True)
            if len(calls) == 1:
                raise RuntimeError("simulated crash after provider completion")
            return original(ledger, *args, **kwargs)

        with patch.object(ExecutionLedger, "record_verifier_evaluation", crash_once):
            result, sends, replies, captured = self._run_v8([self.PASS], repeat=2)
        self.assertEqual(captured["first_error"], "simulated crash after provider completion")
        self.assertEqual(sends, ["editor", "verifier"])
        self.assertIn("valid_pass", replies[2]["summary"])
        self.assertEqual(result["status"], "completed")
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual([item["outcome"] for item in receipt["verifier_evaluations"]], ["valid_pass"])

    def test_v8_receipt_rejects_each_tampered_verifier_binding(self):
        result, _, _, captured = self._run_v8([self.FAIL, self.PASS], plan=("editor", "verifier", "verifier"))
        envelope = captured["envelope"]
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        validate_receipt(envelope, receipt)

        def reseal(evaluation):
            body = {key: value for key, value in evaluation.items() if key != "evaluation_digest"}
            return {**body, "evaluation_digest": verifier_digest(body)}

        def forged_pass(r):
            # A self-consistent pass sealed over the first call's real fail output.
            item = r["verifier_evaluations"][0]
            item["evaluation"] = reseal({**item["evaluation"], "disposition": "valid_pass", "reason": "accepted_pass",
                                         "candidate": json.loads(self.PASS)})
            item["evaluation_digest"], item["outcome"] = item["evaluation"]["evaluation_digest"], "valid_pass"

        def rebind_diff(r):
            for binding, item in zip(r["verifier_inputs"], r["verifier_evaluations"]):
                binding["diff_digest"] = "f" * 64
                item["evaluation"] = reseal({**item["evaluation"], "diff_digest": "f" * 64})
                item["evaluation_digest"] = item["evaluation"]["evaluation_digest"]

        def rebind_evaluation_only(r):
            # The binding stays true; only the evaluation's sealed copy moves.
            item = r["verifier_evaluations"][0]
            item["evaluation"] = reseal({**item["evaluation"], "diff_digest": "f" * 64})
            item["evaluation_digest"] = item["evaluation"]["evaluation_digest"]

        def strip_contract(r):
            binding = r["verifier_inputs"][1]
            binding["input"]["provider_task"] = binding["input"]["provider_task"].replace(VERIFIER_CONTRACT_INSTRUCTION, "")
            binding["input_digest"] = verifier_digest(binding["input"])

        mutations = {
            "forged pass over fail output": forged_pass,
            "diff rebound consistently": rebind_diff,
            "evaluation diff rebound only": rebind_evaluation_only,
            "test evidence changed": lambda r: r["evidence"]["tests"].update(output_sha256="f" * 64),
            "evaluation removed": lambda r: r["verifier_evaluations"].pop(0),
            "contract stripped from input": strip_contract,
            "input digest changed": lambda r: r["verifier_inputs"][0].update(input_digest="f" * 64),
            "evaluation action changed": lambda r: r["verifier_evaluations"][1]["evaluation"].update(action_id="other"),
            "consumed counter changed": lambda r: r["verifier_usage"].update(consumed=1),
            "maximum counter changed": lambda r: r["verifier_usage"].update(maximum=1),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                changed = copy.deepcopy(receipt)
                mutate(changed)
                with self.assertRaises(ExecutionContractError):
                    validate_receipt(envelope, changed)

    def test_v8_receipt_recovery_block_is_required_and_bound_to_its_evidence(self):
        result, _, _, captured = self._run_v8([self.PASS])
        envelope = captured["envelope"]
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        validate_receipt(envelope, receipt)
        editor = receipt["actions"][0]["action_id"]
        recovered = copy.deepcopy(receipt)
        recovered["actions"][0]["reason"] = "recovery_regranted"
        for item in recovered["verifier_inputs"] + recovered["verifier_evaluations"]:
            item["owner_generation"] = 2
        recovered["recovery"] = {
            "schema_version": 1, "resolutions": [], "replaced_draft_sha256": None,
            "interruptions": [{"interruption_id": "i1", "cause": "unmarked_process_exit",
                               "owner_generation": 1, "recorded_at": "2026-09-23T00:00:00+00:00"}],
            "recoveries": [{"recovery_id": "r1", "expected_generation": 1, "generation": 2, "lead_generation": 1,
                            "actor": "flow-chartered-resume", "mode": "pending",
                            "released_action_ids": [editor], "claimed_at": "2026-09-23T00:00:01+00:00"}]}
        validate_receipt(envelope, recovered)
        mutations = {
            "recovery generation changed": lambda r: r["recovery"]["recoveries"][0].update(generation=3),
            "recovery marker removed": lambda r: r.pop("recovery"),
            "lead generation changed": lambda r: r["recovery"]["recoveries"][0].update(lead_generation=2),
            "released grant removed": lambda r: r["recovery"]["recoveries"][0].update(released_action_ids=[]),
            "evaluation generation outside chain": lambda r: r["verifier_evaluations"][0].update(owner_generation=5),
            "interruption cause invented": lambda r: r["recovery"]["interruptions"][0].update(cause="timeout"),
            "resolution added": lambda r: r["recovery"].update(resolutions=["extra"]),
            "draft digest malformed": lambda r: r["recovery"].update(replaced_draft_sha256="draft"),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                changed = copy.deepcopy(recovered)
                mutate(changed)
                with self.assertRaises(ExecutionContractError):
                    validate_receipt(envelope, changed)
        marker_only = copy.deepcopy(receipt)
        marker_only["verifier_evaluations"][0]["owner_generation"] = 2
        with self.assertRaisesRegex(ExecutionContractError, "lacks its recovery block"):
            validate_receipt(envelope, marker_only)

    def test_v8_predecessor_links_are_validated_only_for_v8(self):
        envelope, _, _, _ = self.prepare()
        envelope = copy.deepcopy(envelope)
        envelope["delivery_lead_claim"]["generation"] = 2
        valid = {"attempt_id": "a" * 32, "terminal_status": "superseded", "receipt_sha256": None, "lead_generation": 1}
        envelope["predecessors"] = [valid]
        validate_envelope(envelope)
        cases = {
            "empty list": [],
            "current generation": [{**valid, "lead_generation": 2}],
            "non-terminal status": [{**valid, "terminal_status": "started"}],
            "missing sealed digest": [{**valid, "terminal_status": "failed"}],
            "duplicate": [valid, valid],
            "self link": [{**valid, "attempt_id": envelope["attempt_id"]}],
            "extra field": [{**valid, "note": "x"}],
        }
        for label, predecessors in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(ExecutionContractError):
                    validate_envelope({**envelope, "predecessors": predecessors})

    def test_completed_v7_receipt_keeps_its_original_validation_semantics(self):
        result, _, _, captured = self._run_v8([self.PASS])
        envelope = copy.deepcopy(captured["envelope"])
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        # Re-derive a genuine v7 receipt from the same facts: v7 carries no
        # verifier allowance, inputs, evaluations, or usage.
        envelope["execution_protocol_version"] = 7
        envelope["limits"].pop("max_verifier_calls")
        receipt["execution_protocol_version"] = 7
        for field in ("verifier_inputs", "verifier_evaluations", "verifier_usage"):
            receipt.pop(field)
        receipt["envelope_digest"] = envelope_digest(envelope)
        for item in receipt["actions"]:
            item["request"]["envelope_digest"] = receipt["envelope_digest"]
            item["request"]["action_id"] = item["action_id"] = expected_magentic_action_id(item["request"])
        for item in receipt.get("manager_calls", []):
            self.assertEqual(item, None, "stub supervisor makes no manager calls")
        self.assertEqual(receipt["status"], "completed")
        validate_receipt(envelope, receipt)
        receipt["evidence"]["tests"]["status"] = "failed"
        with self.assertRaisesRegex(ExecutionContractError, "chartered test evidence is invalid"):
            validate_receipt(envelope, receipt)

    def test_v8_refuses_a_charter_that_never_sealed_the_verifier_cap(self):
        original = delivery_gateway._sealed_delivery_authority

        def legacy(*args, **kwargs):
            authority = copy.deepcopy(original(*args, **kwargs))
            authority["charter"]["limits"].pop("max_verifier_calls")
            return authority

        with patch("delivery_gateway._sealed_delivery_authority", side_effect=legacy):
            with self.assertRaisesRegex(ContractError, "seals max_verifier_calls"):
                self.prepare()

    def test_v8_refused_send_preparation_releases_the_untouched_grant(self):
        def refuse(*args, **kwargs):
            raise ExecutionContractError("simulated preparation refusal")

        with patch.object(ExecutionLedger, "prepare_verifier_send", refuse):
            result, sends, _, _ = self._run_v8([self.PASS])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(sends, ["editor"])
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        verifier = [item for item in receipt["actions"] if item["request"]["assignment_id"] == "verifier"]
        self.assertEqual([item["status"] for item in verifier], ["not_dispatched"])
        self.assertEqual((receipt["verifier_usage"]["reserved"], receipt["verifier_usage"]["consumed"]), (0, 0))

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
                                              "workflow_name": "flow-magentic-delivery-v8",
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

    def test_v8_transport_loss_after_producer_records_a_resumable_interruption(self):
        # Formerly test_v7_transport_loss_after_producer_seals_nonresumable_receipt:
        # the gateway always mints v8, and v8 now records an interruption
        # instead of sealing a non-resumable failed receipt.
        calls = []
        captured = {}

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            captured["envelope"] = envelope
            proposal = self._proposal(envelope, "editor", 1)
            checkpoint = Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json"
            checkpoint.write_text(json.dumps({"checkpoint_id": proposal["checkpoint_id"],
                                              "workflow_name": "flow-magentic-delivery-v8",
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
        self.assertEqual((result["status"], result["reason"]), ("interrupted", "transport"))
        self.assertTrue(result["resume_available"])
        self.assertEqual(result["blocking"], [])
        self.assertIsNone(result["receipt_path"])
        attempt_dir = Path(captured["envelope"]["checkpoint_dir"]).parent
        self.assertFalse((attempt_dir / "receipt.json").exists())
        snapshot = ExecutionLedger(attempt_dir.parent / "ledger.sqlite", read_only=True).snapshot(result["attempt_id"])
        self.assertEqual(snapshot["status"], "started")
        self.assertEqual([item["cause"] for item in snapshot["interruptions"]], ["transport"])
        self.assertEqual([action["status"] for action in snapshot["actions"]], ["completed"])

    def test_v8_uncertain_send_records_reconciliation_interruption_not_unknown_receipt(self):
        def worker(action, *, envelope, workspace):
            if action["assignment_id"] == "editor":
                (workspace / "target.py").write_text("new\n")
                return self._result("codex", "editor-model", "Edited target")
            raise OSError("simulated connection reset during verifier send")

        captured = {}

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            captured["envelope"] = envelope
            for sequence, assignment_id in enumerate(("editor", "verifier"), 1):
                proposal = self._proposal(envelope, assignment_id, sequence)
                checkpoint = Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json"
                checkpoint.write_text(json.dumps({"checkpoint_id": proposal["checkpoint_id"],
                                                  "workflow_name": "flow-magentic-delivery-v8",
                                                  "pending_request_info_events": {f"flow-magentic-action-{sequence}": {}}}))
                on_action(proposal)
            return {"attempt_id": envelope["attempt_id"]}

        with patch("delivery_gateway.run_status", return_value=self.state), \
             patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            result = execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root,
                                                supervisor=supervisor, worker_adapter=worker)
        self.assertEqual((result["status"], result["reason"]), ("interrupted", "reconciliation_required"))
        self.assertFalse(result["resume_available"])
        self.assertEqual(len(result["blocking"]), 1)
        attempt_dir = Path(captured["envelope"]["checkpoint_dir"]).parent
        self.assertFalse((attempt_dir / "receipt.json").exists())
        ledger = ExecutionLedger(attempt_dir.parent / "ledger.sqlite")
        snapshot = ledger.snapshot(result["attempt_id"])
        self.assertEqual(snapshot["status"], "started")
        self.assertEqual([item["status"] for item in snapshot["actions"]], ["completed", "unknown"])
        with self.assertRaisesRegex(ExecutionContractError, "never seals an unknown"):
            ledger.finish_attempt(result["attempt_id"], "unknown", "reconciliation_required",
                                  str(attempt_dir / "receipt.json"), generation=1)

    def test_v7_editor_head_drift_halts_after_one_send(self):
        calls = []

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            proposal = self._proposal(envelope, "editor", 1)
            checkpoint = Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json"
            checkpoint.write_text(json.dumps({"checkpoint_id": proposal["checkpoint_id"],
                                              "workflow_name": "flow-magentic-delivery-v8",
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
                                              "workflow_name": "flow-magentic-delivery-v8",
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
