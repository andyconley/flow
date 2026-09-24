"""Explicit recovery of interrupted protocol v8 chartered attempts (ADR 0016)."""

import ast
import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

from delivery_control import change_lead_claim  # noqa: E402
from delivery_recovery import runtime_outcome  # noqa: E402
from delivery_projection import inspect_delivery, inspect_delivery_projection  # noqa: E402
from delivery_gateway import (RecoveryRefused, _resume_chartered, execute_chartered_delivery,  # noqa: E402
                              recover_delivery, resume_delivery)
from execution_gateway import resolve_attempt  # noqa: E402
from execution_contracts import (ContractError as ExecutionContractError, digest, envelope_digest,  # noqa: E402
                                 expected_manager_call_id)
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



class RecoveryHarness(CharteredFixture):
    """Stub MAF that honours restore requests, counting adapters, and kill points."""

    def setUp(self):
        super().setUp()
        self.sends, self.replies, self.adapter_marks, self.resumes = [], {}, [], []
        self.outputs = []
        self.test_calls = 0
        test_patch = patch("delivery_gateway._run_chartered_test", side_effect=self._fake_test)
        test_patch.start()
        self.addCleanup(test_patch.stop)

    def _fake_test(self, worktree, job):
        # A new digest on every call, like the real timing-bearing output.
        self.test_calls += 1
        return {"command": job["test"]["argv"], "status": "passed",
                "output_sha256": hashlib.sha256(f"run-{self.test_calls}".encode()).hexdigest()}

    def _ledger(self):
        return ExecutionLedger(self.run / "execution" / "ledger.sqlite", read_only=True)

    def _worker(self, action, *, envelope, workspace):
        self.sends.append(action["assignment_id"])
        self.adapter_marks.append(self._ledger().snapshot(envelope["attempt_id"])["events"][-1]["seq"])
        if action["assignment_id"] == "editor":
            (workspace / "target.py").write_text("new\n")
            return self._result("codex", "editor-model", "Edited target")
        return self._result("ollama", "local-model", self.outputs.pop(0))

    def _supervisor(self, plan, *, fail_after=None):
        def supervisor(envelope, task, on_manager, on_action, resume=None, **kwargs):
            self.attempt_id = envelope["attempt_id"]
            self.resumes.append(resume)
            start = 1
            if resume is not None:
                sequence = int(resume["request_id"].rsplit("-", 1)[1])
                start = sequence if resume.get("kind") == "pending" else sequence + 1
            for sequence in range(start, len(plan) + 1):
                proposal = self._proposal(envelope, plan[sequence - 1], sequence)
                if not (resume is not None and resume.get("kind") == "pending" and sequence == start):
                    (Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json").write_text(json.dumps(
                        {"checkpoint_id": proposal["checkpoint_id"], "workflow_name": "flow-magentic-delivery-v8",
                         "pending_request_info_events": {f"flow-magentic-action-{sequence}": {}}}))
                self.replies[sequence] = on_action(proposal)
                if fail_after == sequence:
                    raise MafTransportError("simulated transport loss")
            return {"attempt_id": envelope["attempt_id"]}
        return supervisor

    def _start(self, plan, outputs, *, fail_after=None, seal_hook=None):
        self.outputs = list(outputs)
        with patch("delivery_gateway.run_status", return_value=self.state), \
             patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            return execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root,
                                              supervisor=self._supervisor(plan, fail_after=fail_after),
                                              worker_adapter=self._worker, seal_hook=seal_hook)

    def _killed(self, plan, outputs, **kwargs):
        with self.assertRaises(KillPoint):
            self._start(plan, outputs, **kwargs)
        return self.attempt_id

    def _recover(self, attempt_id, plan, *, entry=None, seal_hook=None, supervisor=None):
        kwargs = {"supervisor": supervisor or self._supervisor(plan), "worker_adapter": self._worker}
        with patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])):
            if seal_hook is not None:
                return _resume_chartered("sample", attempt_id, root=self.root.resolve(), seal_hook=seal_hook, **kwargs)
            return (entry or resume_delivery)("sample", attempt_id, root=self.root, **kwargs)

    def _receipt(self, result):
        return json.loads(Path(result["receipt_path"]).read_text())

    def _kill_once(self, name, *, after=False, when=lambda *args, **kwargs: True):
        original = getattr(ExecutionLedger, name)
        state = {"fired": False}

        def wrapper(ledger, *args, **kwargs):
            if not state["fired"] and when(ledger, *args, **kwargs):
                state["fired"] = True
                if after:
                    original(ledger, *args, **kwargs)
                raise KillPoint(name)
            return original(ledger, *args, **kwargs)
        return patch.object(ExecutionLedger, name, wrapper)

    def _assert_recovered_receipt(self, result, *, mode, cause="unmarked_process_exit"):
        receipt = self._receipt(result)
        self.assertEqual(result["mode"], mode)
        self.assertEqual([item["cause"] for item in receipt["recovery"]["interruptions"]], [cause])
        self.assertEqual([(r["expected_generation"], r["generation"], r["mode"]) for r in receipt["recovery"]["recoveries"]],
                         [(1, 2, mode)])
        self.assertEqual(receipt["recovery"]["resolutions"], [])
        self.assertEqual(self._ledger().snapshot(result["attempt_id"])["sealed_receipt_sha256"],
                         hashlib.sha256(Path(result["receipt_path"]).read_bytes()).hexdigest())
        return receipt


class CharteredRecoveryTests(RecoveryHarness):
    """AC2-AC8, AC10: explicit recovery from the latest bound checkpoint."""

    def test_boundary_b_unconsumed_producer_grant_is_regranted_and_counted_once(self):
        with self._kill_once("consume_grant"):
            attempt_id = self._killed(("editor", "verifier"), [self.PASS])
        self.assertEqual(self.sends, [])
        result = self._recover(attempt_id, ("editor", "verifier"))
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(self.sends, ["editor", "verifier"])
        self.assertEqual(self.resumes[-1]["kind"], "pending")
        self.assertNotIn("result", self.resumes[-1])
        receipt = self._assert_recovered_receipt(result, mode="pending")
        editor = receipt["actions"][0]
        self.assertEqual((editor["status"], editor["reason"]), ("completed", "recovery_regranted"))
        self.assertEqual(receipt["recovery"]["recoveries"][0]["released_action_ids"], [editor["action_id"]])
        self.assertEqual(self.test_calls, 1)
        # AC3: the claim and the call's re-grant both precede the adapter call.
        events = self._ledger().snapshot(attempt_id)["events"]
        claimed = next(item["seq"] for item in events if item["event"] == "recovery_claimed")
        regrant = next(item["seq"] for item in events if item["event"] == "policy_allowed"
                       and item["detail"] == "recovery_regranted")
        self.assertLess(claimed, regrant)
        self.assertLess(regrant, self.adapter_marks[0] + 1)

    def test_boundary_b_unconsumed_verifier_grant_captures_the_test_once(self):
        with self._kill_once("prepare_verifier_send"):
            attempt_id = self._killed(("editor", "verifier"), [self.PASS])
        self.assertEqual((self.sends, self.test_calls), (["editor"], 1))
        result = self._recover(attempt_id, ("editor", "verifier"))
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(self.sends, ["editor", "verifier"])
        receipt = self._assert_recovered_receipt(result, mode="pending")
        self.assertEqual(self.test_calls, 2, "no verifier input existed, so the test is captured once more")
        self.assertEqual(receipt["verifier_usage"], {"maximum": 2, "reserved": 1, "consumed": 1,
                                                     "denied": 0, "retry_eligible": False})
        self.assertEqual(receipt["evidence"]["tests"]["output_sha256"], receipt["verifier_inputs"][0]["test_digest"])

    def test_boundary_d_producer_completed_before_verification_runs_the_test_exactly_once(self):
        with self._kill_once("complete", after=True):
            attempt_id = self._killed(("editor", "verifier"), [self.PASS])
        self.assertEqual((self.sends, self.test_calls), (["editor"], 0))
        result = self._recover(attempt_id, ("editor", "verifier"))
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(self.sends, ["editor", "verifier"])
        self.assertEqual(self.test_calls, 1)
        self.assertEqual(self.resumes[-1]["action_id"], self._receipt(result)["actions"][0]["action_id"])
        self.assertIn("Flow verified the scoped repair", self.resumes[-1]["result"]["summary"])
        self._assert_recovered_receipt(result, mode="answer")

    def test_boundary_f_verifier_completed_but_unevaluated_is_evaluated_without_resend(self):
        with self._kill_once("record_verifier_evaluation"):
            attempt_id = self._killed(("editor", "verifier"), [self.PASS])
        self.assertEqual(self.sends, ["editor", "verifier"])
        result = self._recover(attempt_id, ("editor", "verifier"))
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(self.sends, ["editor", "verifier"])
        receipt = self._assert_recovered_receipt(result, mode="answer")
        self.assertEqual([item["outcome"] for item in receipt["verifier_evaluations"]], ["valid_pass"])
        self.assertEqual(receipt["verifier_evaluations"][0]["owner_generation"], 2)
        self.assertEqual(self.test_calls, 1)

    def test_boundary_g_retry_eligible_fail_recovers_to_one_granted_retry(self):
        with self._kill_once("record_verifier_evaluation", after=True):
            attempt_id = self._killed(("editor", "verifier", "verifier"), [self.FAIL, self.PASS])
        self.assertEqual(self.sends, ["editor", "verifier"])
        result = self._recover(attempt_id, ("editor", "verifier", "verifier"))
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(self.sends, ["editor", "verifier", "verifier"])
        self.assertIn("retry eligible: true", self.resumes[-1]["result"]["summary"])
        receipt = self._assert_recovered_receipt(result, mode="answer")
        self.assertEqual([item["outcome"] for item in receipt["verifier_evaluations"]], ["valid_fail", "valid_pass"])
        self.assertEqual(len({item["test_digest"] for item in receipt["verifier_inputs"]}), 1)
        self.assertEqual(self.test_calls, 1)

    def test_boundary_h_terminal_evaluations_seal_without_any_send(self):
        cases = (("second fail", ("editor", "verifier", "verifier", "verifier"), [self.FAIL, self.FAIL], 2, "failed", 1),
                 ("pass", ("editor", "verifier"), [self.PASS], 1, "completed", 0))
        for label, plan, outputs, nth, status, denied in cases:
            with self.subTest(label=label):
                self.sends.clear()
                self.test_calls = 0
                (self.worktree / "target.py").write_text("old\n")
                count = {"n": 0}

                def nth_call(ledger, *args, target=nth, **kwargs):
                    count["n"] += 1
                    return count["n"] == target

                with self._kill_once("record_verifier_evaluation", after=True, when=nth_call):
                    attempt_id = self._killed(plan, outputs)
                sent = list(self.sends)
                result = self._recover(attempt_id, plan)
                self.assertEqual(result["status"], status, result)
                self.assertEqual(self.sends, sent)
                receipt = self._assert_recovered_receipt(result, mode="answer")
                self.assertEqual(receipt["verifier_usage"]["denied"], denied)
                self.assertEqual(self.test_calls, 1)

    def test_boundary_i_kill_during_sealing_seals_once_without_the_runtime(self):
        for point in ("after-receipt-draft", "before-finish-attempt"):
            with self.subTest(point=point):
                def kill(reached, target=point):
                    if reached == target:
                        raise KillPoint(reached)

                self.sends.clear()
                self.resumes.clear()
                (self.worktree / "target.py").write_text("old\n")
                attempt_id = self._killed(("editor", "verifier"), [self.PASS], seal_hook=kill)
                draft = self.run / "execution" / attempt_id / "receipt.json"
                draft_sha = hashlib.sha256(draft.read_bytes()).hexdigest() if draft.exists() else None
                self.assertEqual(draft_sha is not None, point == "before-finish-attempt")
                result = self._recover(attempt_id, ("editor", "verifier"),
                                       supervisor=lambda *args, **kwargs: self.fail("seal mode must skip MAF"))
                self.assertEqual(result["status"], "completed", result)
                self.assertEqual(self.sends, ["editor", "verifier"])
                receipt = self._assert_recovered_receipt(result, mode="seal")
                self.assertEqual(receipt["recovery"]["replaced_draft_sha256"], draft_sha)
                self.assertEqual(self.test_calls, 1)
                self.test_calls = 0

    def test_seal_mode_after_a_failed_test_seals_failed_without_rerunning_it(self):
        def failing(worktree, job):
            self.test_calls += 1
            raise ExecutionContractError("targeted chartered test failed: boom")

        def kill(point):
            if point == "after-runtime-outcome":
                raise KillPoint(point)

        with patch("delivery_gateway._run_chartered_test", side_effect=failing):
            attempt_id = self._killed(("editor", "verifier"), [self.PASS], seal_hook=kill)
            self.assertEqual((self.sends, self.test_calls), (["editor"], 1))
            result = self._recover(attempt_id, ("editor", "verifier"),
                                   supervisor=lambda *args, **kwargs: self.fail("seal mode must skip MAF"))
        self.assertEqual(result["status"], "failed", result)
        self.assertEqual(self.test_calls, 1, "a recorded failure is sealed, never retested")
        receipt = self._assert_recovered_receipt(result, mode="seal")
        self.assertIsNone(receipt["evidence"]["tests"])
        self.assertIn("targeted chartered test failed", receipt["reason"])

    def test_seal_mode_without_a_recorded_failure_or_verifier_input_never_runs_the_test(self):
        def kill(point):
            if point == "after-runtime-outcome":
                raise KillPoint(point)

        attempt_id = self._killed(("editor",), [], seal_hook=kill)
        self.assertEqual(self.sends, ["editor"])
        snapshot = self._ledger().snapshot(attempt_id)
        self.assertEqual(snapshot.get("verifier_inputs", []), [])
        # The scenario: a recorded, failure-free outcome, so seal mode is not the recorded-failure path.
        self.assertEqual(runtime_outcome(snapshot)["failure"], "")
        before = self.test_calls
        result = self._recover(attempt_id, ("editor",),
                               supervisor=lambda *args, **kwargs: self.fail("seal mode must skip MAF"))
        self.assertEqual(self.test_calls, before, "seal mode records the outcome; it never runs the test")
        self.assertEqual(result["status"], "failed", result)
        receipt = self._assert_recovered_receipt(result, mode="seal")
        self.assertIsNone(receipt["evidence"]["tests"])
        self.assertEqual(self.sends, ["editor"])

    def test_a_live_attempt_mid_send_refuses_as_attempt_running_not_reconciliation(self):
        worker = self._worker

        def in_flight(action, *, envelope, workspace):
            if action["assignment_id"] == "verifier":
                raise KillPoint("verifier send in flight")
            return worker(action, envelope=envelope, workspace=workspace)

        with patch.object(self, "_worker", in_flight):
            attempt_id = self._killed(("editor", "verifier"), [self.PASS])
        before = self._ledger().snapshot(attempt_id)
        self.assertEqual([item["status"] for item in before["actions"]], ["completed", "started"])
        ledger = ExecutionLedger(self.run / "execution" / "ledger.sqlite")
        with ledger.recovery_lock(attempt_id, holder="live"):
            for entry in (resume_delivery, recover_delivery):
                with self.subTest(entry=entry.__name__), self.assertRaises(RecoveryRefused) as raised:
                    self._recover(attempt_id, ("editor", "verifier"), entry=entry)
                self.assertEqual(raised.exception.reason, "attempt_running")
        self.assertEqual(self._ledger().snapshot(attempt_id), before)
        # Once no live run holds the fence, the uncertain send is what refuses.
        with self.assertRaises(RecoveryRefused) as raised:
            self._recover(attempt_id, ("editor", "verifier"))
        self.assertEqual(raised.exception.reason, "reconciliation_required")
        self.assertEqual(self.sends, ["editor"])

    def test_never_sent_manager_grant_is_reissued_on_replay_and_sent_once(self):
        manager_sends = []

        def manager_request(envelope, sequence):
            messages = [{"role": "user", "contents": [{"type": "text", "text": f"progress {sequence}"}]}]
            request = {"schema_version": 1, "attempt_id": envelope["attempt_id"],
                       "envelope_digest": envelope_digest(envelope), "sequence": sequence, "phase": "facts",
                       "manager_round": 1, "prompt_digest": digest(messages)}
            return {**request, "call_id": expected_manager_call_id(request), "messages": messages}

        def supervisor(envelope, task, on_manager, on_action, resume=None, **kwargs):
            self.attempt_id = envelope["attempt_id"]
            self.resumes.append(resume)
            if resume is None:
                proposal = self._proposal(envelope, "editor", 1)
                (Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json").write_text(json.dumps(
                    {"checkpoint_id": proposal["checkpoint_id"], "workflow_name": "flow-magentic-delivery-v8",
                     "pending_request_info_events": {"flow-magentic-action-1": {}}}))
                on_action(proposal)
            # MAF restored after action 1 replays the manager call it made there.
            on_manager(manager_request(envelope, 1))
            proposal = self._proposal(envelope, "verifier", 2)
            (Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json").write_text(json.dumps(
                {"checkpoint_id": proposal["checkpoint_id"], "workflow_name": "flow-magentic-delivery-v8",
                 "pending_request_info_events": {"flow-magentic-action-2": {}}}))
            on_action(proposal)
            return {"attempt_id": envelope["attempt_id"]}

        def manager(message, *, envelope, workspace):
            manager_sends.append(message["call_id"])
            self.adapter_marks.append(self._ledger().snapshot(envelope["attempt_id"])["events"][-1]["seq"])
            return {"output": "Fixture facts", "usage": None}

        self.outputs = [self.PASS]
        with self._kill_once("consume_manager_grant"), \
             patch("delivery_gateway.run_status", return_value=self.state), \
             patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role), \
             self.assertRaises(KillPoint):
            execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root, supervisor=supervisor,
                                       worker_adapter=self._worker, manager_adapter=manager)
        self.assertEqual((self.sends, manager_sends), (["editor"], []))
        with patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])):
            result = resume_delivery("sample", self.attempt_id, root=self.root, supervisor=supervisor,
                                     worker_adapter=self._worker, manager_adapter=manager)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(len(manager_sends), 1)
        self.assertEqual(self.sends, ["editor", "verifier"])
        events = self._ledger().snapshot(self.attempt_id)["events"]
        claimed = next(item["seq"] for item in events if item["event"] == "recovery_claimed")
        reissued = next(item["seq"] for item in events if item["event"] == "manager_policy_allowed"
                        and item["detail"] == "recovery_regranted")
        self.assertLess(claimed, reissued)
        self.assertLessEqual(reissued, self.adapter_marks[-2])
        calls = self._receipt(result)["manager_calls"]
        self.assertEqual([item["status"] for item in calls], ["completed"])

    def test_clean_transport_loss_recovers_from_the_committed_producer(self):
        result = self._start(("editor", "verifier"), [self.PASS], fail_after=1)
        self.assertEqual((result["status"], result["reason"]), ("interrupted", "transport"))
        recovered = self._recover(result["attempt_id"], ("editor", "verifier"), entry=recover_delivery)
        self.assertEqual(recovered["status"], "completed", recovered)
        self.assertEqual(self.sends, ["editor", "verifier"])
        self._assert_recovered_receipt(recovered, mode="answer", cause="transport")

    def test_ac6_killed_after_valid_pass_recovery_never_invokes_the_test_runner(self):
        def kill(point):
            if point == "after-runtime-outcome":
                raise KillPoint(point)

        # Answer mode restores MAF with a verifier input bound, so only the
        # evidence-reuse branch stops a rerun there; seal mode never runs it.
        for mode in ("answer", "seal"):
            with self.subTest(mode=mode):
                self.sends.clear()
                self.test_calls = 0
                (self.worktree / "target.py").write_text("old\n")
                if mode == "answer":
                    with self._kill_once("record_verifier_evaluation", after=True):
                        attempt_id = self._killed(("editor", "verifier"), [self.PASS])
                else:
                    attempt_id = self._killed(("editor", "verifier"), [self.PASS], seal_hook=kill)
                self.assertEqual(self.test_calls, 1)
                result = self._recover(attempt_id, ("editor", "verifier"))
                # The zero-rerun assertion comes first so it is the one a broken
                # reuse guard trips (AC12), not the later stale-evidence status.
                self.assertEqual(self.test_calls, 1, "recovery must reuse the bound test evidence")
                self.assertEqual(result["status"], "completed", result)
                receipt = self._assert_recovered_receipt(result, mode=mode)
                final = receipt["verifier_evaluations"][-1]["evaluation"]
                self.assertEqual(receipt["evidence"]["tests"]["output_sha256"], final["test_evidence_digest"])
                self.assertEqual(final["test_evidence_digest"], receipt["verifier_inputs"][-1]["test_digest"])

    def test_worktree_drift_fails_closed_before_any_send_or_completion(self):
        with self._kill_once("prepare_verifier_send"):
            attempt_id = self._killed(("editor", "verifier"), [self.PASS])
        (self.worktree / "target.py").write_text("drifted\n")
        with self.assertRaises(RecoveryRefused) as raised:
            self._recover(attempt_id, ("editor", "verifier"))
        self.assertEqual(raised.exception.reason, "worktree_drift")
        self.assertEqual(self.sends, ["editor"])
        snapshot = self._ledger().snapshot(attempt_id)
        self.assertEqual(snapshot["status"], "started")
        # Drift refuses before the claim: nothing is fenced or released.
        self.assertEqual([item["status"] for item in snapshot["actions"]], ["completed", "allowed"])
        self.assertEqual((snapshot["recoveries"], snapshot["owner_generation"]), ([], 1))
        self.assertEqual(self.resumes, [None], "drift refuses before any restore")

    def test_stale_unbound_checkpoint_is_quarantined_not_sealed_failed(self):
        with self._kill_once("prepare_verifier_send"):
            attempt_id = self._killed(("editor", "verifier"), [self.PASS])
        stray = self.run / "execution" / attempt_id / "checkpoints" / "stray.json"
        stray.write_text('{"checkpoint_id":"stray"}')
        stray_sha = hashlib.sha256(stray.read_bytes()).hexdigest()
        result = self._recover(attempt_id, ("editor", "verifier"))
        self.assertEqual(result["status"], "completed", result)
        self.assertFalse(stray.exists())
        recovery = self._ledger().snapshot(attempt_id)["recoveries"][0]
        self.assertEqual(recovery["quarantined"], [{"name": "stray.json", "sha256": stray_sha}])
        self.assertTrue((self.run / "execution" / attempt_id / "checkpoints-quarantine" / recovery["recovery_id"] / "stray.json").is_file())

    def test_recovery_is_exclusive_and_refuses_a_live_attempt(self):
        with self._kill_once("consume_grant"):
            attempt_id = self._killed(("editor", "verifier"), [self.PASS])
        ledger = ExecutionLedger(self.run / "execution" / "ledger.sqlite")
        for holder, reason in (("recovery", "recovery_in_progress"), ("live", "attempt_running")):
            with self.subTest(holder=holder), ledger.recovery_lock(attempt_id, holder=holder):
                with self.assertRaises(RecoveryRefused) as raised:
                    self._recover(attempt_id, ("editor", "verifier"))
                self.assertEqual(raised.exception.reason, reason)
        self.assertEqual(self._ledger().snapshot(attempt_id)["recoveries"], [])
        self.assertEqual(self.sends, [])

    def test_reinvoking_after_a_completed_recovery_returns_state_without_mutation(self):
        with self._kill_once("consume_grant"):
            attempt_id = self._killed(("editor", "verifier"), [self.PASS])
        first = self._recover(attempt_id, ("editor", "verifier"))
        receipt_bytes = Path(first["receipt_path"]).read_bytes()
        before = self._ledger().snapshot(attempt_id)
        sends = list(self.sends)
        again = self._recover(attempt_id, ("editor", "verifier"))
        self.assertEqual((again["status"], again["receipt_path"], again["replayed"]),
                         ("completed", first["receipt_path"], True))
        self.assertEqual(Path(first["receipt_path"]).read_bytes(), receipt_bytes)
        self.assertEqual(self._ledger().snapshot(attempt_id), before)
        self.assertEqual(self.sends, sends)

    def test_ac8_regranted_unconsumed_action_counts_once_against_chartered_limits(self):
        self.intent["delegation_matrix"]["max_delegations"] = 2
        self.intent["budget_safety_envelope"]["enforceable"].update(max_paid_worker_calls=1, max_concurrent=1)
        (self.run / "shaper-intent.json").write_text(json.dumps(self.intent))
        self._write_delivery_authority()
        with self._kill_once("consume_grant"):
            attempt_id = self._killed(("editor", "verifier"), [self.PASS])
        limits = self._ledger().snapshot(attempt_id)["envelope"]["limits"]
        self.assertEqual((limits["max_paid_worker_calls"], limits["max_delegations"]), (1, 2))
        result = self._recover(attempt_id, ("editor", "verifier"))
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(self.sends, ["editor", "verifier"])
        self.assertEqual([item["status"] for item in self._receipt(result)["actions"]], ["completed", "completed"])

    def test_ac8_verifier_retry_after_a_pass_is_denied_before_any_adapter_call(self):
        with self._kill_once("record_verifier_evaluation", after=True):
            attempt_id = self._killed(("editor", "verifier", "verifier"), [self.PASS, self.PASS])
        result = self._recover(attempt_id, ("editor", "verifier", "verifier"))
        self.assertEqual(self.sends, ["editor", "verifier"])
        self.assertEqual(self.replies[3]["status"], "denied")
        receipt = self._receipt(result)
        self.assertEqual(receipt["actions"][-1]["reason"], "verifier_retry_denied")
        self.assertEqual(result["status"], "completed")

    def test_recovered_receipt_rejects_a_changed_generation_and_a_removed_marker(self):
        from execution_contracts import validate_receipt

        with self._kill_once("consume_grant"):
            attempt_id = self._killed(("editor", "verifier"), [self.PASS])
        result = self._recover(attempt_id, ("editor", "verifier"))
        receipt = self._receipt(result)
        envelope = self._ledger().snapshot(attempt_id)["envelope"]
        validate_receipt(envelope, receipt)
        for label, mutate, message in (
                ("generation changed", lambda r: r["recovery"]["recoveries"][0].update(generation=3), "generation chain"),
                ("recovery marker removed", lambda r: r.pop("recovery"), "lacks its recovery block")):
            with self.subTest(label=label):
                changed = copy.deepcopy(receipt)
                mutate(changed)
                with self.assertRaisesRegex(ExecutionContractError, message):
                    validate_receipt(envelope, changed)


class CharteredRecoveryEntryTests(unittest.TestCase):
    """AC2: recovery runs only from the operator commands, never from a timer, expiry, or exit."""

    ENTRY_POINTS = {"resume_delivery", "recover_delivery", "_resume_chartered", "claim_chartered_recovery"}
    ALLOWED = {
        "claim_chartered_recovery": {"cli/delivery_gateway.py:_resume_chartered"},
        "_resume_chartered": {"cli/delivery_gateway.py:resume_delivery", "cli/delivery_gateway.py:recover_delivery"},
        "resume_delivery": {"cli/delivery_gateway.py:recover_delivery", "cli/flow.py:main"},
        "recover_delivery": {"cli/flow.py:main"},
    }

    def _references(self):
        repo = Path(__file__).resolve().parents[1]
        found: dict[str, set[str]] = {}
        self.counts: dict[str, int] = {}
        for path in sorted([*(repo / "cli").rglob("*.py"), *(repo / "runtime").rglob("*.py")]):
            label = path.relative_to(repo).as_posix()

            def walk(node, function):
                for child in ast.iter_child_nodes(node):
                    inner = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else function
                    # Any load, not only a call: a callable handed to a timer,
                    # signal, or atexit hook is a reference too.
                    name = (child.id if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)
                            else child.attr if isinstance(child, ast.Attribute) else None)
                    if name in self.ENTRY_POINTS:
                        site = f"{label}:{function}"
                        found.setdefault(name, set()).add(site)
                        self.counts[f"{name}@{site}"] = self.counts.get(f"{name}@{site}", 0) + 1
                    walk(child, inner)

            walk(ast.parse(path.read_text()), "<module>")
        return found

    def test_recovery_entry_points_are_referenced_only_from_the_operator_commands(self):
        self.assertEqual(self._references(), self.ALLOWED)
        # main is allowed as a whole, so each entry may be loaded there only once:
        # a second load (a timer or atexit hook inside main) fails here.
        for name in ("resume_delivery", "recover_delivery"):
            self.assertEqual(self.counts[f"{name}@cli/flow.py:main"], 1, name)

    def test_the_cli_reaches_recovery_only_through_its_two_named_subcommands(self):
        source = (Path(__file__).resolve().parents[1] / "cli" / "flow.py").read_text()
        for command, entry in (("resume-delivery-lead", "resume_delivery("), ("recover-delivery-lead", "recover_delivery(")):
            with self.subTest(command=command):
                branch = source.index(f'args.run_target == "{command}"')
                following = source.index("\n    if args.command", branch)
                self.assertEqual(source.count(entry), 1)
                self.assertTrue(branch < source.index(entry) < following)


class CharteredRecoveryInspectionTests(RecoveryHarness):
    """AC11: inspection reports eligibility, blockers, evidence needed, and the sealed digest."""

    def test_inspection_reports_blockers_with_the_evidence_each_needs(self):
        def worker(action, *, envelope, workspace):
            if action["assignment_id"] == "verifier":
                raise OSError("simulated connection reset during verifier send")
            return self._worker(action, envelope=envelope, workspace=workspace)

        self.outputs = [self.PASS]
        with patch("delivery_gateway.run_status", return_value=self.state), \
             patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            result = execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root,
                                                supervisor=self._supervisor(("editor", "verifier")), worker_adapter=worker)
        view = inspect_delivery("sample", result["attempt_id"], root=self.root)["attempt"]
        self.assertTrue(view["executable"])
        self.assertFalse(view["resumable"])
        self.assertEqual((view["recovery"]["recoverable"], view["recovery"]["reason"]), (False, "reconciliation_required"))
        # Inspection cannot see the live-run fence; it says so rather than implying a command verdict.
        self.assertEqual((view["recovery"]["decided_from"], view["recovery"]["checked_by_command"]),
                         ("ledger", ["live_run_fence", "worktree_drift", "envelope_file"]))
        blocker = view["recovery"]["blockers"][0]
        self.assertEqual((blocker["kind"], blocker["status"]), ("action", "unknown"))
        self.assertIn("resolve-execution", blocker["evidence_needed"])
        self.assertEqual([item["cause"] for item in view["interruptions"]], ["reconciliation_required"])
        self.assertTrue(view["sealed_receipt"]["consistent"])

    def test_seal_mode_receipt_without_its_block_is_caught_only_by_the_sealed_digest(self):
        from execution_contracts import validate_receipt

        def kill(point):
            if point == "after-runtime-outcome":
                raise KillPoint(point)

        attempt_id = self._killed(("editor", "verifier"), [self.PASS], seal_hook=kill)
        recovered = self._recover(attempt_id, ("editor", "verifier"))
        self.assertEqual(recovered["mode"], "seal")
        receipt = self._receipt(recovered)
        receipt.pop("recovery")
        # R2: a seal-mode receipt carries no generation above the claim, so the
        # receipt alone still validates; the ledger's sealed digest decides.
        validate_receipt(self._ledger().snapshot(attempt_id)["envelope"], receipt)
        Path(recovered["receipt_path"]).write_text(json.dumps(receipt))
        sealed = inspect_delivery("sample", attempt_id, root=self.root)["attempt"]["sealed_receipt"]
        self.assertEqual((sealed["matches"], sealed["recovery_block_present"], sealed["consistent"]), (False, False, False))

    def test_inspection_shows_a_recoverable_mode_then_a_consistent_sealed_receipt(self):
        result = self._start(("editor", "verifier"), [self.PASS], fail_after=1)
        view = inspect_delivery("sample", result["attempt_id"], root=self.root)["attempt"]
        self.assertEqual((view["resumable"], view["recovery"]["mode"]), (True, "answer"))
        recovered = self._recover(result["attempt_id"], ("editor", "verifier"))
        view = inspect_delivery("sample", result["attempt_id"], root=self.root)["attempt"]
        self.assertFalse(view["executable"])
        self.assertEqual(len(view["recoveries"]), 1)
        sealed = view["sealed_receipt"]
        self.assertEqual((sealed["matches"], sealed["recovery_block_present"], sealed["consistent"]), (True, True, True))
        receipt = self._receipt(recovered)
        receipt.pop("recovery")
        Path(recovered["receipt_path"]).write_text(json.dumps(receipt))
        sealed = inspect_delivery("sample", result["attempt_id"], root=self.root)["attempt"]["sealed_receipt"]
        self.assertEqual((sealed["matches"], sealed["recovery_block_present"], sealed["consistent"]), (False, False, False))

    def test_a_recovered_started_attempt_is_executable_under_its_active_lead(self):
        envelope = self.prepare()[0]
        snapshot = {"attempt_id": envelope["attempt_id"], "execution_protocol_version": 8, "status": "started",
                    "owner_generation": 2, "actions": [], "manager_calls": [], "events": [],
                    "verifier_evaluations": [], "verifier_usage": None, "recoveries": [{"generation": 2}]}
        self.assertFalse(inspect_delivery_projection(envelope, snapshot)["executable"])
        view = inspect_delivery_projection(envelope, snapshot, lead_active=True)
        self.assertTrue(view["executable"])
        self.assertEqual(view["delivery_lead"]["current_generation"], 2)
        self.assertFalse(inspect_delivery_projection(envelope, snapshot, lead_active=False)["executable"])
        self.assertEqual(view["recovery"]["reason"], "no_restorable_checkpoint")
        self.assertTrue(view["recovery"]["blockers"][0]["evidence_needed"].startswith("none; abandon"))


if __name__ == "__main__":
    unittest.main()
