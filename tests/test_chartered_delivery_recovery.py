"""Explicit recovery of interrupted protocol v8 chartered attempts (ADR 0016)."""

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

from delivery_control import change_lead_claim  # noqa: E402
from delivery_gateway import (RecoveryRefused, execute_chartered_delivery,  # noqa: E402
                              recover_delivery, resume_delivery)
from execution_gateway import resolve_attempt  # noqa: E402
from execution_ledger import ExecutionLedger  # noqa: E402
from maf_supervisor import MafTransportError  # noqa: E402
from tests.test_chartered_delivery_gateway import CharteredFixture, KillPoint  # noqa: E402


class CharteredRecoveryRefusalTests(CharteredFixture):
    """AC1: out-of-scope and blocked attempts refuse before any mutation."""

    def _state(self, attempt_id):
        execution = self.run / "execution"
        files = {str(path.relative_to(execution)): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in sorted(execution.rglob("*")) if path.is_file() and not path.name.endswith(".lock")}
        snapshot = ExecutionLedger(execution / "ledger.sqlite", read_only=True).snapshot(attempt_id)
        return files, snapshot

    def _assert_refused_without_mutation(self, attempt_id, reason, call=None):
        before = self._state(attempt_id)
        calls = []
        adapters = {"worker_adapter": lambda *a, **k: calls.append("worker"),
                    "manager_adapter": lambda *a, **k: calls.append("manager"),
                    "supervisor": lambda *a, **k: calls.append("supervisor"),
                    "test_runner": lambda *a, **k: calls.append("test")}
        with patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])):
            for label, entry in (("resume", resume_delivery), ("recover", recover_delivery)):
                with self.subTest(entry=label):
                    with self.assertRaises(RecoveryRefused) as raised:
                        (call or entry)("sample", attempt_id, root=self.root, **adapters)
                    self.assertEqual(raised.exception.reason, reason)
                    self.assertTrue(str(raised.exception).startswith(reason))
        self.assertEqual(calls, [])
        self.assertEqual(self._state(attempt_id), before)

    def _legacy_attempt(self, protocol):
        envelope, _, attempt_dir, ledger = self.prepare()
        legacy = copy.deepcopy(envelope)
        legacy["attempt_id"] = "b" * 32
        legacy["execution_protocol_version"] = protocol
        legacy["checkpoint_dir"] = str(attempt_dir.parent / legacy["attempt_id"] / "checkpoints")
        if protocol == 7:
            legacy["limits"].pop("max_verifier_calls")
        else:
            legacy["limits"] = {"max_delegations": 6, "max_concurrent": 3, "max_replans": 2,
                                "max_manager_calls": 12, "max_manager_rounds": 6, "max_paid_worker_calls": 1}
        legacy_dir = attempt_dir.parent / legacy["attempt_id"]
        (legacy_dir / "checkpoints").mkdir(parents=True)
        (legacy_dir / "envelope.json").write_text(json.dumps(legacy))
        (legacy_dir / "baseline.json").write_text((attempt_dir / "baseline.json").read_text())
        ledger.create_attempt(legacy)
        return legacy["attempt_id"]

    def test_recovery_refuses_a_v6_attempt_without_mutation(self):
        self._assert_refused_without_mutation(self._legacy_attempt(6), "v6_inspection_only")

    def test_recovery_refuses_a_v7_attempt_without_mutation(self):
        self._assert_refused_without_mutation(self._legacy_attempt(7), "v7_not_recoverable")

    def test_recovery_refuses_a_terminal_v8_attempt_without_mutation(self):
        result, _, _, _ = self._run_v8([self.PASS])
        self.assertEqual(result["status"], "completed")
        self._assert_refused_without_mutation(result["attempt_id"], "attempt_terminal")

    def test_recovery_fails_closed_with_no_restorable_checkpoint_when_none_is_bound(self):
        def die(*args, **kwargs):
            raise KillPoint("before the first checkpoint bind")

        with patch.object(ExecutionLedger, "bind_magentic_checkpoint", die), self.assertRaises(KillPoint):
            self._run_v8([self.PASS])
        attempt_id = next((self.run / "execution").glob("*/envelope.json")).parent.name
        snapshot = self._state(attempt_id)[1]
        self.assertEqual([item["status"] for item in snapshot["actions"]], ["allowed"])
        self.assertEqual(snapshot["magentic_checkpoints"], [])
        self._assert_refused_without_mutation(attempt_id, "no_restorable_checkpoint")

    def test_recovery_refuses_an_uncertain_send_with_reconciliation_required(self):
        def worker(action, *, envelope, workspace):
            if action["assignment_id"] == "editor":
                (workspace / "target.py").write_text("new\n")
                return self._result("codex", "editor-model", "Edited target")
            raise OSError("simulated connection reset during verifier send")

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            for sequence, assignment_id in enumerate(("editor", "verifier"), 1):
                proposal = self._proposal(envelope, assignment_id, sequence)
                (Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json").write_text(json.dumps(
                    {"checkpoint_id": proposal["checkpoint_id"], "workflow_name": "flow-magentic-delivery-v8",
                     "pending_request_info_events": {f"flow-magentic-action-{sequence}": {}}}))
                on_action(proposal)
            return {"attempt_id": envelope["attempt_id"]}

        with patch("delivery_gateway.run_status", return_value=self.state), \
             patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            result = execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root,
                                                supervisor=supervisor, worker_adapter=worker)
        self.assertEqual(result["reason"], "reconciliation_required")
        self._assert_refused_without_mutation(result["attempt_id"], "reconciliation_required")

    def _interrupted_after_producer(self):
        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            proposal = self._proposal(envelope, "editor", 1)
            (Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json").write_text(json.dumps(
                {"checkpoint_id": proposal["checkpoint_id"], "workflow_name": "flow-magentic-delivery-v8",
                 "pending_request_info_events": {"flow-magentic-action-1": {}}}))
            on_action(proposal)
            raise MafTransportError("simulated transport loss")

        def worker(action, *, envelope, workspace):
            (workspace / "target.py").write_text("new\n")
            return self._result("codex", "editor-model", "Edited target")

        with patch("delivery_gateway.run_status", return_value=self.state), \
             patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            result = execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root,
                                                supervisor=supervisor, worker_adapter=worker)
        self.assertEqual(result["status"], "interrupted")
        return result["attempt_id"]

    def test_recovery_refuses_once_lead_claim_generation_is_no_longer_active(self):
        attempt_id = self._interrupted_after_producer()
        changed, _, errors = change_lead_claim("sample", "supersede", root=self.root, owner="replacement")
        self.assertTrue(changed, errors)
        self._assert_refused_without_mutation(attempt_id, "lead_generation_inactive")

    def test_v8_refuses_continuation_epochs_and_resolve_execution(self):
        attempt_id = self._interrupted_after_producer()
        before = self._state(attempt_id)
        with self.assertRaises(RecoveryRefused) as raised:
            resume_delivery("sample", attempt_id, root=self.root, continuation_epoch_id="epoch")
        self.assertEqual(raised.exception.reason, "continuation_epochs_v5_only")
        evidence = self.run / "execution" / attempt_id / "evidence.json"
        with self.assertRaises(RecoveryRefused) as raised:
            resolve_attempt("sample", attempt_id, "a" * 64, "operator", "resolved_completed", "x", str(evidence), root=self.root)
        self.assertEqual(raised.exception.reason, "v8_resolution_requires_chunk_2")
        self.assertEqual(self._state(attempt_id), before)


if __name__ == "__main__":
    unittest.main()
