"""Explicit recovery of interrupted protocol v8 chartered attempts (ADR 0016)."""

import ast
import copy
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

from delivery_control import change_lead_claim  # noqa: E402
import runstate  # noqa: E402
from delivery_recovery import runtime_outcome  # noqa: E402
from delivery_projection import inspect_delivery, inspect_delivery_projection  # noqa: E402
from delivery_gateway import (RecoveryRefused, _resume_chartered, execute_chartered_delivery,  # noqa: E402
                              recover_delivery, resume_delivery)
from execution_gateway import resolve_attempt  # noqa: E402
from execution_contracts import (ContractError as ExecutionContractError, digest, envelope_digest,  # noqa: E402
                                 expected_manager_call_id, validate_receipt)
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
        # A lead change now seals the attempt as superseded (AC9.2), so model
        # a started attempt left behind under an older generation directly.
        run = json.loads((self.run / "run.json").read_text())
        run["delivery"]["owner_generation"] = 2
        (self.run / "run.json").write_text(json.dumps(run))
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

    def test_v8_no_dispatch_regrant_is_refused_without_mutation(self):
        attempt_id = self._interrupted_after_producer()
        snapshot = ExecutionLedger(self.run / "execution" / "ledger.sqlite", read_only=True).snapshot(attempt_id)
        before = self._state(attempt_id)
        with self.assertRaises(RecoveryRefused) as raised:
            ExecutionLedger(self.run / "execution" / "ledger.sqlite").regrant_not_dispatched(
                snapshot["envelope"], snapshot["actions"][0]["request"], generation=snapshot["owner_generation"])
        self.assertEqual(raised.exception.reason, "v8_no_dispatch_regrant_unsupported")
        self.assertEqual(self._state(attempt_id), before)



class LeadChangeFenceTests(CharteredFixture):
    """AC9.2-9.4: a lead change seals, or refuses on uncertainty or a live run."""

    _state = CharteredRecoveryRefusalTests._state
    _assert_refused_without_mutation = CharteredRecoveryRefusalTests._assert_refused_without_mutation

    def _killed_before_bind(self):
        def die(*args, **kwargs):
            raise KillPoint("before the first checkpoint bind")

        with patch.object(ExecutionLedger, "bind_magentic_checkpoint", die), self.assertRaises(KillPoint):
            self._run_v8([self.PASS])
        return next((self.run / "execution").glob("*/envelope.json")).parent.name

    def _uncertain_verifier_send(self):
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
        return result["attempt_id"]

    def _v7_started_row(self, attempt_id):
        envelope = json.loads((self.run / "execution" / attempt_id / "envelope.json").read_text())
        legacy = copy.deepcopy(envelope)
        legacy["attempt_id"] = "b" * 32
        legacy["execution_protocol_version"] = 7
        legacy["limits"].pop("max_verifier_calls")
        legacy["checkpoint_dir"] = str(self.run / "execution" / legacy["attempt_id"] / "checkpoints")
        ExecutionLedger(self.run / "execution" / "ledger.sqlite").create_attempt(legacy)
        return legacy["attempt_id"]

    def _authority(self):
        """Every byte a lead change may write: run.json, claim files, and the ledger."""
        files = {str(path.relative_to(self.run)): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in sorted(self.run.rglob("*")) if path.is_file() and not path.name.endswith(".lock")}
        ledger = ExecutionLedger(self.run / "execution" / "ledger.sqlite", read_only=True)
        attempts = [path.parent.name for path in sorted((self.run / "execution").glob("*/envelope.json"))]
        return files, [ledger.snapshot(attempt_id) for attempt_id in attempts]

    def _assert_seals(self, action):
        attempt_id = self._killed_before_bind()
        v7_id = self._v7_started_row(attempt_id)
        v7_before = ExecutionLedger(self.run / "execution" / "ledger.sqlite", read_only=True).snapshot(v7_id)
        changed, run, errors = change_lead_claim("sample", action, root=self.root, owner="replacement")
        self.assertTrue(changed, errors)
        self.assertEqual(run["delivery"]["owner_generation"], 2)
        ledger = ExecutionLedger(self.run / "execution" / "ledger.sqlite", read_only=True)
        snapshot = ledger.snapshot(attempt_id)
        self.assertEqual(snapshot["status"], "superseded")
        self.assertEqual(json.loads(snapshot["reason"]),
                         {"action": action, "lead_generation": 1, "successor_generation": 2})
        self.assertIsNone(snapshot["receipt_path"])
        self.assertEqual((snapshot["owner_generation"], snapshot["owner_actor"]), (2, "superseded"))
        self.assertEqual([(item["status"], item["reason"], item["grant_id"]) for item in snapshot["actions"]],
                         [("not_dispatched", "superseded_unconsumed_grant", None)])
        self.assertEqual([item["event"] for item in snapshot["events"]][-2:],
                         ["superseded_grant_released", "attempt_superseded"])
        self.assertEqual(v7_before["status"], "started")
        self.assertEqual(ledger.snapshot(v7_id), v7_before, "the v8-only seal must leave a v7 row untouched")
        self._assert_refused_without_mutation(attempt_id, "attempt_terminal")

    def test_lead_resume_seals_the_old_attempt_as_superseded(self):
        self._assert_seals("resume")

    def test_lead_supersede_seals_the_old_attempt_as_superseded(self):
        self._assert_seals("supersede")

    def test_lead_resume_or_supersede_is_refused_while_any_action_is_unknown(self):
        attempt_id = self._uncertain_verifier_send()
        before = self._authority()
        for action in ("resume", "supersede"):
            with self.subTest(action=action):
                changed, _, errors = change_lead_claim("sample", action, root=self.root, owner="replacement")
                self.assertFalse(changed)
                self.assertTrue(errors[0].startswith("reconciliation_required"), errors)
        self.assertEqual(self._authority(), before)
        self.assertEqual(ExecutionLedger(self.run / "execution" / "ledger.sqlite", read_only=True)
                         .snapshot(attempt_id)["status"], "started")

    def test_an_uncertain_v7_send_blocks_a_lead_change_with_no_v8_attempt_to_seal(self):
        # With no started v8 attempt there is no seal transaction to re-check,
        # so the read-only guard alone must refuse, for a send still in
        # flight (started) and for one whose outcome is lost (unknown).
        envelope = self._run_v8([self.PASS])[3]["envelope"]
        v7_id = self._v7_started_row(envelope["attempt_id"])
        ledger = ExecutionLedger(self.run / "execution" / "ledger.sqlite")
        legacy = ledger.snapshot(v7_id)["envelope"]
        proposal = self._proposal(legacy, "editor", 1)
        grant = ledger.decide(legacy, proposal, generation=1)
        self.assertTrue(ledger.consume_grant(proposal["action_id"], grant["grant_id"], generation=1))
        for status in ("started", "unknown"):
            with self.subTest(status=status):
                if status == "unknown":
                    ledger.mark_unknown(proposal["action_id"], "transport_lost", generation=1)
                self.assertEqual(ledger.snapshot(v7_id)["actions"][0]["status"], status)
                before = self._authority()
                changed, _, errors = change_lead_claim("sample", "resume", root=self.root, owner="replacement")
                self.assertFalse(changed)
                self.assertTrue(errors[0].startswith("reconciliation_required"), errors)
                self.assertEqual(self._authority(), before)

    def test_an_unknown_manager_call_alone_blocks_a_lead_change(self):
        messages = [{"role": "user", "contents": [{"type": "text", "text": "progress 1"}]}]

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            request = {"schema_version": 1, "attempt_id": envelope["attempt_id"],
                       "envelope_digest": envelope_digest(envelope), "sequence": 1, "phase": "facts",
                       "manager_round": 1, "prompt_digest": digest(messages)}
            on_manager({**request, "call_id": expected_manager_call_id(request), "messages": messages})
            return {"attempt_id": envelope["attempt_id"]}

        def manager(message, *, envelope, workspace):
            raise OSError("simulated connection reset during the manager send")

        with patch("delivery_gateway.run_status", return_value=self.state), \
             patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            result = execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root,
                                                supervisor=supervisor, manager_adapter=manager)
        snapshot = ExecutionLedger(self.run / "execution" / "ledger.sqlite", read_only=True).snapshot(result["attempt_id"])
        self.assertEqual(([item["status"] for item in snapshot["manager_calls"]], snapshot["actions"]), (["unknown"], []))
        before = self._authority()
        for action in ("resume", "supersede"):
            with self.subTest(action=action):
                changed, _, errors = change_lead_claim("sample", action, root=self.root, owner="replacement")
                self.assertFalse(changed)
                self.assertTrue(errors[0].startswith("reconciliation_required"), errors)
                self.assertEqual(self._authority(), before)

    def test_the_seal_refuses_attempts_that_were_not_probed(self):
        attempt_id = self._killed_before_bind()
        ledger = ExecutionLedger(self.run / "execution" / "ledger.sqlite")
        before = self._authority()
        with self.assertRaises(RecoveryRefused) as raised:
            ledger.seal_superseded_attempts("sample", lead_generation=1, successor_generation=2,
                                            action="supersede", expected=[])
        self.assertEqual(raised.exception.reason, "recovery_in_progress")
        self.assertEqual(self._authority(), before)
        self.assertEqual(ledger.snapshot(attempt_id)["status"], "started")

    def test_a_lost_or_symlinked_ledger_is_never_read_as_empty(self):
        self.prepare()
        ledger_path = self.run / "execution" / "ledger.sqlite"
        moved = self.run / "ledger.moved"
        ledger_path.rename(moved)
        for label in ("missing with attempts", "symlink"):
            with self.subTest(label=label):
                if label == "symlink":
                    ledger_path.symlink_to(moved)
                before = (self.run / "run.json").read_bytes()
                changed, _, errors = change_lead_claim("sample", "supersede", root=self.root, owner="replacement")
                self.assertFalse(changed)
                self.assertEqual(errors, ["lead_guard_ledger_unreadable"])
                self.assertEqual((self.run / "run.json").read_bytes(), before)

    def test_lead_change_fails_closed_on_an_unreadable_ledger(self):
        self.prepare()
        (self.run / "execution" / "ledger.sqlite").write_bytes(b"not a sqlite database" * 64)
        before = self._authority_files()
        changed, _, errors = change_lead_claim("sample", "supersede", root=self.root, owner="replacement")
        self.assertFalse(changed)
        self.assertEqual(errors, ["lead_guard_ledger_unreadable"])
        self.assertEqual(self._authority_files(), before)

    def _authority_files(self):
        return {str(path.relative_to(self.run)): path.read_bytes()
                for path in sorted(self.run.rglob("*")) if path.is_file() and not path.name.endswith(".lock")}

    def test_lead_change_refuses_attempt_running_while_a_live_run_holds_the_lock(self):
        envelope, _, _, ledger = self.prepare()
        before = self._authority()
        with ledger.recovery_lock(envelope["attempt_id"], holder="live"):
            changed, _, errors = change_lead_claim("sample", "supersede", root=self.root, owner="replacement")
        self.assertFalse(changed)
        self.assertEqual(errors, ["attempt_running"])
        self.assertEqual(self._authority(), before)

    def test_abandonment_succeeds_while_actions_are_unknown(self):
        attempt_id = self._uncertain_verifier_send()
        changed, run, errors = change_lead_claim("sample", "release", root=self.root)
        self.assertTrue(changed, errors)
        self.assertEqual(run["delivery"]["owner_status"], "released")
        blocked, run, errors = runstate.apply_transition("sample", "block", note="abandoned: unknown verifier send",
                                                         root=self.root.resolve())
        self.assertTrue(blocked, errors)
        self.assertEqual(run["state"], "blocked")
        # Abandonment fences no ledger row; the uncertain send stays visible.
        self.assertEqual(ExecutionLedger(self.run / "execution" / "ledger.sqlite", read_only=True)
                         .snapshot(attempt_id)["status"], "started")


class SuccessorLineageTests(CharteredFixture):
    """A successor links every earlier v8 attempt and shares its charter caps (R4)."""

    def _reset_worktree(self):
        subprocess.run(["git", "-C", str(self.worktree), "checkout", "-q", "--", "target.py"], check=True)

    def _ledger(self):
        return ExecutionLedger(self.run / "execution" / "ledger.sqlite", read_only=True)

    def _seal_caps(self, **limits):
        self.intent["budget_safety_envelope"]["enforceable"].update(limits)
        (self.run / "shaper-intent.json").write_text(json.dumps(self.intent))
        self._write_delivery_authority()

    def test_first_attempt_has_no_predecessors_and_a_started_sibling_blocks_prepare(self):
        envelope, _, _, _ = self.prepare()
        self.assertNotIn("predecessors", envelope)
        with self.assertRaises(RecoveryRefused) as raised:
            self.prepare()
        self.assertEqual(raised.exception.reason, "sibling_attempt_not_terminal")
        self.assertEqual(len(list((self.run / "execution").glob("*/envelope.json"))), 1)

    def test_successor_after_supersede_lists_the_superseded_predecessor(self):
        first, _, _, _ = self.prepare()
        changed, run, errors = change_lead_claim("sample", "supersede", root=self.root, owner="replacement")
        self.assertTrue(changed, errors)
        self.state = run
        second, _, _, _ = self.prepare()
        self.assertEqual(second["delivery_lead_claim"]["generation"], 2)
        self.assertEqual(second["predecessors"], [{"attempt_id": first["attempt_id"], "terminal_status": "superseded",
                                                   "receipt_sha256": None, "lead_generation": 1}])

    def test_create_attempt_requires_the_exact_lineage(self):
        result, _, _, captured = self._run_v8([self.FAIL], plan=("editor", "verifier"))
        self.assertEqual(result["status"], "failed")
        link = {"attempt_id": result["attempt_id"], "terminal_status": "failed",
                "receipt_sha256": hashlib.sha256(Path(result["receipt_path"]).read_bytes()).hexdigest(),
                "lead_generation": 1}
        ledger = ExecutionLedger(self.run / "execution" / "ledger.sqlite")

        def candidate(attempt_id, predecessors):
            envelope = copy.deepcopy(captured["envelope"])
            envelope["attempt_id"] = attempt_id
            envelope["checkpoint_dir"] = str(self.run / "execution" / attempt_id / "checkpoints")
            if predecessors is None:
                envelope.pop("predecessors", None)
            else:
                envelope["predecessors"] = predecessors
            return envelope

        def at_generation_two(attempt_id, predecessors):
            # Well formed for a generation-2 successor, so only the ledger,
            # which records generation 1, can refuse the forged link.
            envelope = candidate(attempt_id, predecessors)
            envelope["delivery_lead_claim"]["generation"] = 2
            return envelope

        cases = {"dropped": (candidate, None, False),
                 "added": (candidate, [link, {**link, "attempt_id": "c" * 32}], False),
                 "altered status": (candidate, [{**link, "terminal_status": "completed"}], True),
                 "altered generation": (at_generation_two, [{**link, "lead_generation": 2}], True),
                 "altered digest": (candidate, [{**link, "receipt_sha256": "0" * 64}], True)}
        for index, (label, (build, predecessors, ledger_only)) in enumerate(cases.items()):
            with self.subTest(label=label):
                # The envelope validator or the ledger's exact-lineage check
                # refuses, depending on whether the forged link is well formed.
                with self.assertRaisesRegex(ExecutionContractError, "predecessor") as raised:
                    ledger.create_attempt(build(f"{index:032x}", predecessors))
                if ledger_only or isinstance(raised.exception, RecoveryRefused):
                    self.assertIsInstance(raised.exception, RecoveryRefused)
                    self.assertEqual(raised.exception.reason, "predecessor_link_invalid")
        self.assertEqual(self._ledger().v8_lineage("sample"), ([link], []))
        ledger.create_attempt(candidate("d" * 32, [link]))
        self.assertEqual(self._ledger().snapshot("d" * 32)["status"], "started")

    def test_successor_paid_and_verifier_limits_count_predecessor_sends(self):
        # Verifier cap: two predecessor verifier sends exhaust the sealed cap of two.
        first, sends, _, _ = self._run_v8([self.FAIL, self.FAIL], plan=("editor", "verifier", "verifier"))
        self.assertEqual((first["status"], sends), ("failed", ["editor", "verifier", "verifier"]))
        self._reset_worktree()
        second, sends, _, captured = self._run_v8([self.PASS], plan=("editor", "verifier"))
        self.assertEqual(sends, ["editor"], "the verifier cap must deny before the verifier adapter")
        self.assertEqual(captured["envelope"]["predecessors"][0]["attempt_id"], first["attempt_id"])
        actions = self._ledger().snapshot(second["attempt_id"])["actions"]
        self.assertEqual([(item["status"], item["reason"]) for item in actions][-1], ("denied", "verifier_call_cap"))
        receipt = json.loads(Path(second["receipt_path"]).read_text())
        self.assertEqual(receipt["lineage_usage"], {"predecessor_paid_calls": 1, "predecessor_verifier_sends": 2})
        self.assertFalse(receipt["verifier_usage"]["retry_eligible"])
        validate_receipt(captured["envelope"], receipt)
        self.assertEqual(self._regrant_limit_reason(second["attempt_id"], actions[-1]), "verifier_call_cap")

        # Paid cap: a new delivery whose charter seals one paid worker call.
        shutil.rmtree(self.run / "execution")
        self._reset_worktree()
        self._seal_caps(max_paid_worker_calls=1)
        first, sends, _, _ = self._run_v8([self.FAIL], plan=("editor", "verifier"))
        self.assertEqual((first["status"], sends), ("failed", ["editor", "verifier"]))
        self._reset_worktree()
        second, sends, _, _ = self._run_v8([self.PASS], plan=("editor", "verifier"))
        self.assertEqual(sends, [], "the paid cap must deny before the producer adapter")
        actions = self._ledger().snapshot(second["attempt_id"])["actions"]
        self.assertEqual([(item["status"], item["reason"]) for item in actions], [("denied", "paid_call_cap")])
        self.assertEqual(self._regrant_limit_reason(second["attempt_id"], actions[0]), "paid_call_cap")

    def _regrant_limit_reason(self, attempt_id, action):
        """The limit rule a recovery regrant applies, which must count the lineage too.

        Predecessors are immutable, so an honest regrant always sees the same
        lineage its ``decide`` saw; the rule is pinned directly instead.
        """
        envelope = self._ledger().snapshot(attempt_id)["envelope"]
        with sqlite3.connect(self.run / "execution" / "ledger.sqlite") as db:
            return ExecutionLedger._v8_limit_reason(db, envelope, action["request"], exclude=action["action_id"])

    def test_successor_first_verifier_is_not_a_retry(self):
        first, _, _, _ = self._run_v8([self.FAIL], plan=("editor", "verifier"))
        self.assertEqual(first["status"], "failed")
        self._reset_worktree()
        second, sends, _, captured = self._run_v8([self.PASS], plan=("editor", "verifier"))
        self.assertEqual((second["status"], sends), ("completed", ["editor", "verifier"]))
        self.assertIn(f"Predecessor attempt {first['attempt_id']} ended failed under lead generation 1; "
                      "its evidence is not reused.", captured["task"])
        envelope = captured["envelope"]
        receipt = json.loads(Path(second["receipt_path"]).read_text())
        self.assertEqual(receipt["lineage_usage"], {"predecessor_paid_calls": 1, "predecessor_verifier_sends": 1})
        validate_receipt(envelope, receipt)
        tampered = {"removed": lambda r: r.pop("lineage_usage"),
                    "negative": lambda r: r["lineage_usage"].update(predecessor_paid_calls=-1),
                    "extra key": lambda r: r["lineage_usage"].update(note=1),
                    "exceeds the verifier cap": lambda r: r["lineage_usage"].update(predecessor_verifier_sends=2)}
        for label, mutate in tampered.items():
            with self.subTest(label=label):
                forged = copy.deepcopy(receipt)
                mutate(forged)
                with self.assertRaises(ExecutionContractError):
                    validate_receipt(envelope, forged)
        first_receipt = json.loads(Path(first["receipt_path"]).read_text())
        first_receipt["lineage_usage"] = {"predecessor_paid_calls": 0, "predecessor_verifier_sends": 0}
        first_envelope = json.loads((self.run / "execution" / first["attempt_id"] / "envelope.json").read_text())
        with self.assertRaisesRegex(ExecutionContractError, "lineage usage requires predecessors"):
            validate_receipt(first_envelope, first_receipt)


class SuccessorLineageTamperTests(CharteredFixture):
    """Receipt lineage_usage alone is checked against the caps and retry rule."""

    _reset_worktree = SuccessorLineageTests._reset_worktree

    def test_tampering_only_lineage_usage_fails_receipt_validation(self):
        first, _, _, _ = self._run_v8([self.FAIL], plan=("editor", "verifier"))
        self._reset_worktree()
        second, _, _, captured = self._run_v8([self.FAIL], plan=("editor", "verifier"))
        self.assertEqual(second["status"], "failed")
        receipt = json.loads(Path(second["receipt_path"]).read_text())
        # One own send plus one predecessor send exhausts the cap of two, so
        # the lineage alone is what makes this valid_fail not retry-eligible.
        self.assertEqual(receipt["lineage_usage"], {"predecessor_paid_calls": 1, "predecessor_verifier_sends": 1})
        self.assertFalse(receipt["verifier_usage"]["retry_eligible"])
        validate_receipt(captured["envelope"], receipt)
        for label, field, value, message in (
                ("hidden verifier send", "predecessor_verifier_sends", 0, "structured verifier usage differs"),
                ("inflated verifier sends", "predecessor_verifier_sends", 2, "exceeds the charter caps"),
                ("inflated paid calls", "predecessor_paid_calls", 6, "exceeds the charter caps")):
            with self.subTest(label=label):
                forged = copy.deepcopy(receipt)
                forged["lineage_usage"][field] = value
                with self.assertRaisesRegex(ExecutionContractError, message):
                    validate_receipt(captured["envelope"], forged)

    def test_the_seal_refuses_understated_lineage_usage_that_receipt_validation_accepts(self):
        first, _, _, _ = self._run_v8([self.FAIL], plan=("editor", "verifier"))
        self._reset_worktree()
        understated = {"predecessor_paid_calls": 0, "predecessor_verifier_sends": 0}
        envelope = {}
        original = ExecutionLedger.create_attempt

        def capture(ledger, candidate):
            envelope.update(candidate)
            return original(ledger, candidate)

        with patch.object(ExecutionLedger, "lineage_usage", return_value=understated), \
             patch.object(ExecutionLedger, "create_attempt", capture), \
             self.assertRaisesRegex(ExecutionContractError, "lineage usage differs from the ledger"):
            self._run_v8([self.PASS], plan=("editor", "verifier"))
        attempt_id = envelope["attempt_id"]
        receipt = json.loads((self.run / "execution" / attempt_id / "receipt.json").read_text())
        # A valid_pass successor: hiding the predecessor's sends changes neither
        # the cap bound nor retry eligibility, so only the ledger can catch it.
        self.assertEqual(receipt["lineage_usage"], understated)
        validate_receipt(envelope, receipt)
        snapshot = ExecutionLedger(self.run / "execution" / "ledger.sqlite", read_only=True).snapshot(attempt_id)
        self.assertEqual((snapshot["status"], snapshot["sealed_receipt_sha256"]), ("started", None))
        self.assertEqual(ExecutionLedger(self.run / "execution" / "ledger.sqlite", read_only=True)
                         .lineage_usage(attempt_id), {"predecessor_paid_calls": 1, "predecessor_verifier_sends": 1})
        self.assertEqual(first["status"], "failed")

    def test_prepare_refuses_a_claim_that_changed_before_the_attempt_was_created(self):
        run = json.loads((self.run / "run.json").read_text())
        run["delivery"]["owner_generation"] = 2
        (self.run / "run.json").write_text(json.dumps(run))
        with self.assertRaisesRegex(Exception, "generation is stale"):
            self.prepare()
        self.assertFalse((self.run / "execution" / "ledger.sqlite").exists()
                         and ExecutionLedger(self.run / "execution" / "ledger.sqlite", read_only=True).v8_lineage("sample")[1])


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
                # Each case is a separate delivery; a same-work successor
                # would inherit the earlier case's verifier sends.
                shutil.rmtree(self.run / "execution", ignore_errors=True)
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


class ObservedReconcileLedgerTests(RecoveryHarness):
    """Chunk 2: a v8 action is resolved only from Flow's stored response observation."""

    _state = CharteredRecoveryRefusalTests._state

    def _interrupted(self, role, *, how="killed"):
        """Leave the producer (first) or verifier (second) action observed but not completed."""
        target = 1 if role == "producer" else 2
        calls = {"n": 0}

        def when(ledger, *args, **kwargs):
            calls["n"] += 1
            return calls["n"] == target

        if how == "killed":
            with self._kill_once("complete", when=when):
                return self._killed(("editor", "verifier"), [self.PASS])
        original = ExecutionLedger.complete

        def complete(ledger, *args, **kwargs):
            if when(ledger):
                raise ExecutionContractError("simulated failure after the response was observed")
            return original(ledger, *args, **kwargs)

        with patch.object(ExecutionLedger, "complete", complete):
            result = self._start(("editor", "verifier"), [self.PASS])
        self.assertEqual(result["reason"], "reconciliation_required", result)
        return result["attempt_id"]

    def _action(self, attempt_id, role):
        return self._ledger().snapshot(attempt_id)["actions"][0 if role == "producer" else 1]

    def _resolve(self, attempt_id, action_id, **kwargs):
        options = {"expected_generation": self._ledger().snapshot(attempt_id)["owner_generation"], **kwargs}
        return ExecutionLedger(self.run / "execution" / "ledger.sqlite").resolve_observed_v8(
            attempt_id, action_id, "operator", "stored response observed before completion", **options)

    def test_an_observed_started_or_unknown_action_resolves_at_the_current_generation(self):
        for role in ("producer", "verifier"):
            for how, status in (("killed", "started"), ("raised", "unknown")):
                with self.subTest(role=role, status=status):
                    shutil.rmtree(self.run / "execution", ignore_errors=True)
                    subprocess.run(["git", "-C", str(self.worktree), "checkout", "-q", "--", "target.py"], check=True)
                    attempt_id = self._interrupted(role, how=how)
                    action = self._action(attempt_id, role)
                    self.assertEqual(action["status"], status)
                    resolution = self._resolve(attempt_id, action["action_id"])
                    self.assertEqual((resolution["owner_generation"], resolution["replayed"]), (1, False))
                    snapshot = self._ledger().snapshot(attempt_id)
                    resolved = self._action(attempt_id, role)
                    self.assertEqual((resolved["status"], resolved["reason"]), ("completed", "operator_resolved_completed"))
                    self.assertEqual((snapshot["status"], snapshot["owner_generation"]), ("started", 1))
                    [row] = snapshot["resolutions"]
                    observation = next(item for item in snapshot["response_observations"]
                                       if item["action_id"] == action["action_id"])
                    self.assertEqual((row["action_id"], row["owner_generation"], row["evidence"]),
                                     (action["action_id"], 1, [{"kind": "flow_response_observation",
                                                                "path": f"ledger:response_observations/{action['action_id']}",
                                                                "sha256": observation["result_digest"]}]))
                    self.assertTrue(self._resolve(attempt_id, action["action_id"])["replayed"])
                    before = self._state(attempt_id)
                    with self.assertRaises(RecoveryRefused) as raised:
                        ExecutionLedger(self.run / "execution" / "ledger.sqlite").resolve_observed_v8(
                            attempt_id, action["action_id"], "operator", "a different explanation", expected_generation=1)
                    self.assertEqual(raised.exception.reason, "item_not_unresolved")
                    self.assertEqual(self._state(attempt_id), before)

    def test_reconcile_refuses_without_mutation(self):
        attempt_id = self._interrupted("producer")
        action_id = self._action(attempt_id, "producer")["action_id"]
        high_water = self._ledger().snapshot(attempt_id)["events"][-1]["seq"]
        for label, kwargs, reason in (("stale generation", {"expected_generation": 2}, "owner_generation_stale"),
                                      ("moved events", {"expected_event_seq": high_water - 1}, "recovery_in_progress")):
            with self.subTest(case=label):
                before = self._state(attempt_id)
                with self.assertRaises(RecoveryRefused) as raised:
                    self._resolve(attempt_id, action_id, **kwargs)
                self.assertEqual(raised.exception.reason, reason)
                self.assertEqual(self._state(attempt_id), before)
        with self.subTest(case="tampered observation"):
            with sqlite3.connect(self.run / "execution" / "ledger.sqlite") as db:
                db.execute("UPDATE response_observations SET result_digest=? WHERE action_id=?", ("0" * 64, action_id))
            before = self._state(attempt_id)
            with self.assertRaises(RecoveryRefused) as raised:
                self._resolve(attempt_id, action_id)
            self.assertEqual(raised.exception.reason, "evidence_invalid")
            self.assertEqual(self._state(attempt_id), before)

    def test_reconcile_refuses_an_unobserved_action_and_a_terminal_attempt(self):
        with self._kill_once("observe_response"):
            attempt_id = self._killed(("editor", "verifier"), [self.PASS])
        action_id = self._action(attempt_id, "producer")["action_id"]
        before = self._state(attempt_id)
        with self.assertRaises(RecoveryRefused) as raised:
            self._resolve(attempt_id, action_id)
        self.assertEqual(raised.exception.reason, "evidence_insufficient")
        self.assertEqual(self._state(attempt_id), before)
        shutil.rmtree(self.run / "execution")
        subprocess.run(["git", "-C", str(self.worktree), "checkout", "-q", "--", "target.py"], check=True)
        result = self._start(("editor", "verifier"), [self.PASS])
        self.assertEqual(result["status"], "completed", result)
        before = self._state(result["attempt_id"])
        with self.assertRaises(RecoveryRefused) as raised:
            self._resolve(result["attempt_id"], self._action(result["attempt_id"], "producer")["action_id"])
        self.assertEqual(raised.exception.reason, "attempt_terminal")
        self.assertEqual(self._state(result["attempt_id"]), before)


if __name__ == "__main__":
    unittest.main()
