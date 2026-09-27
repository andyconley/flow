"""Cancelled and abandoned v8 attempts: the seal, receipts, scoping, successors (ADR 0019)."""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

from delivery_control import change_lead_claim  # noqa: E402
from delivery_gateway import RecoveryRefused, _resume_chartered, execute_chartered_delivery  # noqa: E402
from delivery_termination import terminal_receipt_renderer  # noqa: E402
from execution_contracts import ContractError, validate_receipt  # noqa: E402
from execution_ledger import ExecutionLedger  # noqa: E402
from tests.test_chartered_delivery_gateway import CharteredFixture, KillPoint  # noqa: E402


class TerminationFixture(CharteredFixture):
    """Stuck v8 attempts built through the real gateway, and a direct terminal seal."""

    def ledger(self, *, read_only=False):
        return ExecutionLedger(self.run / "execution" / "ledger.sqlite", read_only=read_only)

    def attempt_dir(self, attempt_id):
        return self.run / "execution" / attempt_id

    def execute(self, supervisor, worker, **kwargs):
        with patch("delivery_gateway.run_status", return_value=self.state), \
             patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            return execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root,
                                              supervisor=supervisor, worker_adapter=worker, **kwargs)

    def _plan_supervisor(self, plan):
        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            self.attempt_id = envelope["attempt_id"]
            for sequence, assignment_id in enumerate(plan, 1):
                proposal = self._proposal(envelope, assignment_id, sequence)
                (Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json").write_text(json.dumps(
                    {"checkpoint_id": proposal["checkpoint_id"], "workflow_name": "flow-magentic-delivery-v8",
                     "pending_request_info_events": {f"flow-magentic-action-{sequence}": {}}}))
                on_action(proposal)
            return {"attempt_id": envelope["attempt_id"]}
        return supervisor

    def unknown_editor_send(self):
        """The live-run dead end: a paid producer send whose outcome was lost."""
        def worker(action, *, envelope, workspace):
            raise OSError("simulated connection reset during the paid send")

        result = self.execute(self._plan_supervisor(("editor",)), worker)
        self.assertEqual((result["status"], result["reason"]), ("interrupted", "reconciliation_required"))
        return result["attempt_id"]

    def allowed_editor_grant(self):
        """A process death between the grant and its use leaves the row allowed."""
        def die(*args, **kwargs):
            raise KillPoint("before the grant is consumed")

        with patch.object(ExecutionLedger, "consume_grant", die), self.assertRaises(KillPoint):
            self.execute(self._plan_supervisor(("editor",)), lambda *a, **k: None)
        return self.attempt_id

    def seal(self, attempt_id, status, *, cause=None, actor="andy", explanation="stopped by the test",
             expected_generation=None, render=None):
        ledger = self.ledger()
        snapshot = ledger.snapshot(attempt_id)
        cause = cause or ("cancel_request" if status == "cancelled" else "reconciliation_required")
        renderer = render or terminal_receipt_renderer(snapshot["envelope"], self.attempt_dir(attempt_id), status=status,
                                                       actor=actor, explanation=explanation, cause=cause)
        with ledger.send_lock():
            return ledger.seal_terminal_uncertain(
                attempt_id, status, actor=actor, explanation=explanation, cause=cause,
                expected_generation=snapshot["owner_generation"] if expected_generation is None else expected_generation,
                receipt_path=self.attempt_dir(attempt_id) / "receipt.json", build_receipt=renderer)

    def receipt(self, attempt_id):
        return json.loads((self.attempt_dir(attempt_id) / "receipt.json").read_text())


class TerminalSealTests(TerminationFixture):
    """R5, AC5: the seal keeps uncertainty, releases grants, and checks its rows."""

    def test_an_abandoned_seal_keeps_the_unknown_send_and_bumps_the_generation(self):
        attempt_id = self.unknown_editor_send()
        result = self.seal(attempt_id, "abandoned", actor="shaper")
        snapshot = self.ledger(read_only=True).snapshot(attempt_id)
        self.assertEqual((snapshot["status"], snapshot["owner_generation"], snapshot["owner_actor"]), ("abandoned", 2, "shaper"))
        self.assertEqual([item["status"] for item in snapshot["actions"]], ["unknown"])
        receipt_bytes = (self.attempt_dir(attempt_id) / "receipt.json").read_bytes()
        self.assertEqual(snapshot["sealed_receipt_sha256"], hashlib.sha256(receipt_bytes).hexdigest())
        self.assertEqual(result["sealed_receipt_sha256"], snapshot["sealed_receipt_sha256"])
        self.assertEqual(snapshot["events"][-1]["event"], "attempt_abandoned")
        receipt = self.receipt(attempt_id)
        self.assertEqual(receipt["termination"], {"actor": "shaper", "explanation": "stopped by the test",
                                                  "cause": "reconciliation_required", "owner_generation": 1,
                                                  "lead_generation": 1})
        self.assertEqual(receipt["evidence_damage"], [])
        self.assertNotIn("lineage_usage", receipt)
        validate_receipt(snapshot["envelope"], receipt)
        with self.assertRaises(RecoveryRefused) as raised:
            self.seal(attempt_id, "abandoned", expected_generation=2)
        self.assertEqual(raised.exception.reason, "attempt_not_started")

    def test_the_validator_accepts_uncertain_rows_only_when_cancelled_or_abandoned(self):
        attempt_id = self.unknown_editor_send()
        self.seal(attempt_id, "cancelled")
        envelope = self.ledger(read_only=True).snapshot(attempt_id)["envelope"]
        receipt = self.receipt(attempt_id)
        validate_receipt(envelope, receipt)
        forged_abandoned = copy.deepcopy(receipt)
        forged_abandoned.update(status="abandoned", reason="unmarked_process_exit")
        forged_abandoned["termination"]["cause"] = "unmarked_process_exit"
        validate_receipt(envelope, forged_abandoned)

        def without_termination(forged):
            forged.pop("termination")
            forged.pop("evidence_damage")

        cases = {
            "failed with an unknown send": (lambda r: (r.update(status="failed"), without_termination(r)),
                                            "only a cancelled or abandoned receipt"),
            "v8 unknown": (lambda r: r.update(status="unknown"), "status or protocol is invalid"),
            "failed keeping termination": (lambda r: (r.update(status="failed"),
                                                      r["actions"][0].update(status="failed")),
                                           "termination evidence requires"),
            "cancelled without the cancel cause": (lambda r: r["termination"].update(cause="operator"),
                                                   "termination is invalid"),
            "missing termination": (lambda r: r.pop("termination"), "termination is invalid"),
            "stale lead generation": (lambda r: r["termination"].update(lead_generation=2), "termination is invalid"),
            "unknown damage kind": (lambda r: r["evidence_damage"].append({"kind": "lost"}), "evidence damage is invalid"),
            "damage is not a list": (lambda r: r.update(evidence_damage={}), "evidence damage is invalid"),
        }
        for label, (mutate, message) in cases.items():
            with self.subTest(label=label):
                forged = copy.deepcopy(receipt)
                mutate(forged)
                with self.assertRaisesRegex(ContractError, message):
                    validate_receipt(envelope, forged)

    def test_the_seal_releases_grants_and_closes_expansions_before_rendering(self):
        attempt_id = self.allowed_editor_grant()
        ledger = self.ledger()
        action = ledger.snapshot(attempt_id)["actions"][0]
        self.assertEqual(action["status"], "allowed")
        # A synthetic open request on the same row: the seal must close it
        # inside the transaction whose snapshot the receipt is rendered from.
        with sqlite3.connect(self.run / "execution" / "ledger.sqlite") as db:
            db.execute("INSERT INTO expansion_requests VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                       ("exp-open", attempt_id, attempt_id, 1, "delegate", action["action_id"], '["delegations"]',
                        1, "0" * 64, "more room", "pending", "2026-09-27T00:00:00+00:00"))
        self.seal(attempt_id, "cancelled")
        receipt = self.receipt(attempt_id)
        self.assertEqual([(item["status"], item["reason"], item["grant_id"]) for item in receipt["actions"]],
                         [("not_dispatched", "cancelled_unconsumed_grant", None)])
        self.assertEqual([(item["request_id"], item["status"]) for item in receipt["expansion"]["requests"]],
                         [("exp-open", "cancelled")])
        snapshot = self.ledger(read_only=True).snapshot(attempt_id)
        self.assertIn("cancelled_grant_released", [item["event"] for item in snapshot["events"]])
        cancelled = [json.loads(item["detail"]) for item in snapshot["events"] if item["event"] == "expansion_cancelled"]
        self.assertEqual(cancelled, [{"request_id": "exp-open", "cause": "cancelled"}])

    def test_the_seal_refuses_a_receipt_whose_rows_differ_from_the_ledger(self):
        attempt_id = self.unknown_editor_send()
        envelope = self.ledger(read_only=True).snapshot(attempt_id)["envelope"]
        honest = terminal_receipt_renderer(envelope, self.attempt_dir(attempt_id), status="abandoned", actor="andy",
                                           explanation="stopped by the test", cause="reconciliation_required")

        def forged_rows(snapshot, blocks):
            receipt = json.loads(honest(snapshot, blocks))
            receipt["actions"][0]["status"] = "failed"
            return json.dumps(receipt).encode()

        def dropped_row(snapshot, blocks):
            receipt = json.loads(honest(snapshot, blocks))
            receipt["actions"] = []
            return json.dumps(receipt).encode()

        before = self.ledger(read_only=True).snapshot(attempt_id)
        for label, render in (("changed status", forged_rows), ("dropped row", dropped_row)):
            with self.subTest(label=label):
                with self.assertRaisesRegex(ContractError, "rows differ from the ledger"):
                    self.seal(attempt_id, "abandoned", render=render)
                self.assertEqual(self.ledger(read_only=True).snapshot(attempt_id), before)
        with self.assertRaises(RecoveryRefused) as raised:
            self.seal(attempt_id, "abandoned", expected_generation=5)
        self.assertEqual(raised.exception.reason, "owner_generation_stale")
        self.assertEqual(self.ledger(read_only=True).snapshot(attempt_id), before)

    def test_damaged_evidence_is_recorded_rather_than_refused(self):
        attempt_id = self.unknown_editor_send()
        attempt_dir = self.attempt_dir(attempt_id)
        (attempt_dir / "baseline.json").unlink()
        trace = b"x" * (1024 * 1024 + 1)
        (attempt_dir / "claude-implementer.debug.log").write_bytes(trace)
        draft = b'{"draft": true}\n'
        (attempt_dir / "receipt.json").write_bytes(draft)
        self.seal(attempt_id, "abandoned")
        receipt = self.receipt(attempt_id)
        self.assertIsNone(receipt["evidence"]["baseline"])
        self.assertNotIn("diagnostic_trace", receipt["evidence"])
        self.assertEqual(receipt["evidence_damage"], [
            {"kind": "baseline_missing"},
            {"kind": "trace_oversized", "path": "claude-implementer.debug.log",
             "sha256": hashlib.sha256(trace).hexdigest(), "bytes": len(trace)},
            {"kind": "draft_receipt_replaced", "sha256": hashlib.sha256(draft).hexdigest()}])


class UncertaintyScopingTests(TerminationFixture):
    """R6, AC8: only a cancelled or abandoned attempt stops blocking a lead change."""

    def test_a_lead_resume_succeeds_once_the_only_uncertainty_is_sealed(self):
        attempt_id = self.unknown_editor_send()
        self.assertEqual(self.ledger(read_only=True).lead_change_blocker(),
                         self.ledger(read_only=True).snapshot(attempt_id)["actions"][0]["action_id"])
        self.seal(attempt_id, "abandoned")
        self.assertIsNone(self.ledger(read_only=True).lead_change_blocker())
        changed, run, errors = change_lead_claim("sample", "resume", root=self.root, owner="replacement")
        self.assertTrue(changed, errors)
        self.assertEqual(run["delivery"]["owner_generation"], 2)
        self.assertEqual(self.ledger(read_only=True).snapshot(attempt_id)["status"], "abandoned")

    def test_a_v7_attempt_sealed_unknown_still_blocks(self):
        attempt_id = self.unknown_editor_send()
        self.seal(attempt_id, "abandoned")
        envelope = copy.deepcopy(self.ledger(read_only=True).snapshot(attempt_id)["envelope"])
        envelope.update(attempt_id="b" * 32, execution_protocol_version=7,
                        checkpoint_dir=str(self.run / "execution" / ("b" * 32) / "checkpoints"))
        envelope["limits"].pop("max_verifier_calls")
        envelope.pop("predecessors", None)
        ledger = self.ledger()
        ledger.create_attempt(envelope)
        proposal = self._proposal(envelope, "editor", 1)
        grant = ledger.decide(envelope, proposal, generation=1)
        self.assertTrue(ledger.consume_grant(proposal["action_id"], grant["grant_id"], generation=1))
        ledger.mark_unknown(proposal["action_id"], "transport_lost", generation=1)
        ledger.finish_attempt(envelope["attempt_id"], "unknown", "reconciliation_required", "", generation=1)
        self.assertEqual(ledger.snapshot(envelope["attempt_id"])["status"], "unknown")
        self.assertEqual(ledger.lead_change_blocker(), proposal["action_id"])
        changed, _, errors = change_lead_claim("sample", "resume", root=self.root, owner="replacement")
        self.assertFalse(changed)
        self.assertTrue(errors[0].startswith("reconciliation_required"), errors)


class TerminalityTests(TerminationFixture):
    """AC6 (ledger half): a cancelled or abandoned attempt refuses every way back in."""

    def _refusals(self, attempt_id):
        ledger = self.ledger()
        snapshot = ledger.snapshot(attempt_id)
        reasons = {}
        for label, call in (
                ("claim", lambda: ledger.claim_chartered_recovery(
                    attempt_id, expected_generation=snapshot["owner_generation"],
                    expected_event_seq=snapshot["events"][-1]["seq"], lead_generation=1, actor="x", mode="seal",
                    checkpoint=None, quarantined=[])),
                ("resolve", lambda: ledger.resolve_observed_v8(attempt_id, snapshot["actions"][0]["action_id"], "x",
                                                               "y", expected_generation=snapshot["owner_generation"])),
                ("decide", lambda: ledger.decide_expansion(attempt_id, "exp-none", approve=True,
                                                           expected_generation=snapshot["owner_generation"],
                                                           actor="x", explanation="y")),
                ("resume", lambda: _resume_chartered("sample", attempt_id, root=self.root.resolve()))):
            with self.assertRaises(RecoveryRefused) as raised:
                with patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])):
                    call()
            reasons[label] = raised.exception.reason
        return reasons

    def test_every_route_back_in_refuses_a_sealed_attempt(self):
        for status in ("cancelled", "abandoned"):
            with self.subTest(status=status):
                attempt_id = self.unknown_editor_send()
                self.seal(attempt_id, status)
                before = self.ledger(read_only=True).snapshot(attempt_id)
                self.assertEqual(self._refusals(attempt_id), dict.fromkeys(("claim", "resolve", "decide", "resume"),
                                                                           "attempt_terminal"))
                self.assertEqual(self.ledger(read_only=True).snapshot(attempt_id), before)
                change_lead_claim("sample", "resume", root=self.root, owner=f"next-{status}")
                self.state = json.loads((self.run / "run.json").read_text())

    def test_a_sealed_attempt_that_had_a_recovery_refuses_instead_of_replaying(self):
        attempt_id = self.allowed_editor_grant()
        with patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway._run_chartered_test",
                   return_value={"command": ["t"], "status": "passed", "output_sha256": "0" * 64}):
            def die(*args, **kwargs):
                raise KillPoint("recovery dies before its regrant")
            with patch.object(ExecutionLedger, "regrant_recovered_action", die), self.assertRaises(KillPoint):
                _resume_chartered("sample", attempt_id, root=self.root.resolve(),
                                  supervisor=self._plan_supervisor(("editor",)), worker_adapter=lambda *a, **k: None)
        self.assertTrue(self.ledger(read_only=True).snapshot(attempt_id)["recoveries"])
        self.seal(attempt_id, "abandoned", cause="unmarked_process_exit")
        receipt = self.receipt(attempt_id)
        self.assertEqual(len(receipt["recovery"]["recoveries"]), 1)
        with patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             self.assertRaises(RecoveryRefused) as raised:
            _resume_chartered("sample", attempt_id, root=self.root.resolve())
        self.assertEqual(raised.exception.reason, "attempt_terminal")


class SuccessorTests(TerminationFixture):
    """R7, AC7 (lineage half): a successor links the sealed attempt and counts its spend."""

    def test_a_successor_after_an_abandoned_dead_end_completes_and_counts_the_unknown_send(self):
        attempt_id = self.unknown_editor_send()
        self.seal(attempt_id, "abandoned")
        digest = self.ledger(read_only=True).snapshot(attempt_id)["sealed_receipt_sha256"]
        result, sends, _, captured = self._run_v8([self.PASS])
        self.assertEqual((result["status"], sends), ("completed", ["editor", "verifier"]))
        self.assertEqual(captured["envelope"]["predecessors"],
                         [{"attempt_id": attempt_id, "terminal_status": "abandoned", "receipt_sha256": digest,
                           "lead_generation": 1}])
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(receipt["lineage_usage"], {"predecessor_paid_calls": 1, "predecessor_verifier_sends": 0})
        self.assertIn(f"Predecessor attempt {attempt_id} ended abandoned", captured["task"])
