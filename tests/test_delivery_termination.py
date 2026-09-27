"""Cancelled and abandoned v8 attempts: the seal, receipts, scoping, successors (ADR 0019)."""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

import contextlib  # noqa: E402
import io  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import fcntl  # noqa: E402

import flow  # noqa: E402
import process_identity  # noqa: E402
from delivery_control import change_lead_claim  # noqa: E402
from delivery_gateway import RecoveryRefused, _resume_chartered, execute_chartered_delivery  # noqa: E402
from delivery_projection import inspect_delivery  # noqa: E402
from delivery_termination import abandon_delivery, stuck_attempts, terminal_receipt_renderer  # noqa: E402
from execution_contracts import ContractError, validate_receipt  # noqa: E402
from execution_ledger import ExecutionLedger  # noqa: E402
from tests.test_chartered_delivery_gateway import CharteredFixture, KillPoint  # noqa: E402
from tests.test_expansion_gateway import ExpansionGatewayFixture  # noqa: E402
from tests.test_expansion_ledger import v8 as expansion_envelope  # noqa: E402


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


def _sleeper():
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], start_new_session=True)


def _stop(process):
    if process.poll() is None:
        process.kill()
    process.wait()


class AbandonFixture(TerminationFixture):
    def abandon(self, attempt_id, *, generation=None, actor="andy", explanation="the attempt is stuck"):
        if generation is None:
            generation = self.ledger(read_only=True).snapshot(attempt_id)["owner_generation"]
        return abandon_delivery("sample", attempt_id, actor=actor, explanation=explanation,
                                expected_generation=generation, root=self.root)

    def lead(self, action, owner=None):
        changed, run, errors = change_lead_claim("sample", action, root=self.root, owner=owner)
        self.assertTrue(changed, errors)
        self.state = run
        return run

    def assert_abandoned(self, attempt_id, *, cause, unknown=0):
        snapshot = self.ledger(read_only=True).snapshot(attempt_id)
        receipt = self.receipt(attempt_id)
        self.assertEqual((snapshot["status"], receipt["status"], receipt["termination"]["cause"]),
                         ("abandoned", "abandoned", cause))
        self.assertEqual(sum(item["status"] == "unknown" for item in receipt["actions"] + receipt["manager_calls"]), unknown)
        self.assertFalse(any(item["status"] == "allowed" for item in receipt["actions"]))
        validate_receipt(snapshot["envelope"], receipt)
        return snapshot, receipt


class AbandonTests(AbandonFixture):
    """R4, AC3, AC7: abandon each kind of stuck attempt, then continue the work id."""

    def test_the_dead_end_is_abandoned_under_every_lead_status_without_touching_the_claim(self):
        for lead_status in ("active", "attention_required", "released"):
            with self.subTest(lead=lead_status):
                attempt_id = self.unknown_editor_send()
                if lead_status != "active":
                    self.lead("attention")
                if lead_status == "released":
                    self.lead("release")
                claim_before = (self.run / "run.json").read_bytes()
                generation = self.ledger(read_only=True).snapshot(attempt_id)["owner_generation"]
                worktree_before = subprocess.check_output(["git", "-C", str(self.worktree), "status", "--porcelain"])
                with patch("delivery_gateway._run_chartered_test", side_effect=AssertionError("abandon ran a test")):
                    result = self.abandon(attempt_id)
                self.assertEqual((result["status"], result["owner_generation"], result["cause"]),
                                 ("abandoned", generation + 1, "reconciliation_required"))
                self.assert_abandoned(attempt_id, cause="reconciliation_required", unknown=1)
                self.assertEqual((self.run / "run.json").read_bytes(), claim_before, "abandon never changes the claim")
                self.assertEqual(subprocess.check_output(["git", "-C", str(self.worktree), "status", "--porcelain"]),
                                 worktree_before)
                if lead_status != "active":
                    self.lead("resume", owner=f"lead-after-{lead_status}")

    def test_a_successor_completes_after_the_abandoned_dead_end(self):
        attempt_id = self.unknown_editor_send()
        self.abandon(attempt_id)
        result, sends, _, captured = self._run_v8([self.PASS])
        self.assertEqual((result["status"], sends), ("completed", ["editor", "verifier"]))
        self.assertEqual([item["terminal_status"] for item in captured["envelope"]["predecessors"]], ["abandoned"])

    def test_a_runtime_cap_interruption_is_abandoned_and_its_successor_completes(self):
        self.intent["budget_safety_envelope"]["enforceable"]["runtime_seconds"] = 2
        (self.run / "shaper-intent.json").write_text(json.dumps(self.intent))
        self._write_delivery_authority()
        fake = self.root / "silent-maf"
        fake.write_text(f"#!{sys.executable}\nimport sys, time\nsys.stdin.readline()\ntime.sleep(600)\n")
        fake.chmod(0o700)
        with patch.dict(os.environ, {"FLOW_MAF_PYTHON": str(fake)}), \
             patch("delivery_gateway.run_status", return_value=self.state), \
             patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            interrupted = execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root)
        self.assertEqual((interrupted["status"], interrupted["reason"]), ("interrupted", "transport"))
        attempt_dir = self.attempt_dir(interrupted["attempt_id"])
        [record] = process_identity.records(attempt_dir)
        self.assertEqual([group["kind"] for group in record["groups"]], ["maf"])
        self.assertFalse(process_identity.group_alive(record["groups"][0]), "the launcher killed its group")
        result = self.abandon(interrupted["attempt_id"])
        self.assertEqual(result["reaped"], [{"owner_generation": 1, "pgid": record["groups"][0]["pgid"],
                                             "kind": "maf", "action": "gone", "members": []}])
        self.assert_abandoned(interrupted["attempt_id"], cause="transport")
        successor, sends, _, _ = self._run_v8([self.PASS])
        self.assertEqual((successor["status"], sends), ("completed", ["editor", "verifier"]))

    def test_an_interrupted_recovery_is_abandoned_with_its_recovery_block(self):
        attempt_id = self.allowed_editor_grant()
        def die(*args, **kwargs):
            raise KillPoint("recovery dies before its regrant")
        with patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch.object(ExecutionLedger, "regrant_recovered_action", die), self.assertRaises(KillPoint):
            _resume_chartered("sample", attempt_id, root=self.root.resolve(),
                              supervisor=self._plan_supervisor(("editor",)), worker_adapter=lambda *a, **k: None)
        self.assertEqual(self.ledger(read_only=True).snapshot(attempt_id)["owner_generation"], 2)
        self.abandon(attempt_id)
        _, receipt = self.assert_abandoned(attempt_id, cause="unmarked_process_exit")
        self.assertEqual([item["generation"] for item in receipt["recovery"]["recoveries"]], [2])
        self.assertEqual(receipt["termination"]["owner_generation"], 2)

    def test_damaged_evidence_does_not_stop_an_abandon(self):
        attempt_id = self.unknown_editor_send()
        (self.attempt_dir(attempt_id) / "baseline.json").unlink()
        self.abandon(attempt_id)
        _, receipt = self.assert_abandoned(attempt_id, cause="reconciliation_required", unknown=1)
        self.assertEqual(receipt["evidence_damage"], [{"kind": "baseline_missing"}])


class PausedAbandonTests(AbandonFixture, ExpansionGatewayFixture):
    """AC3(d), AC7: an expansion-paused attempt is abandoned and its request closed."""

    limits = {"max_concurrent": 1, "max_paid_worker_calls": 2}

    def test_a_paused_attempt_is_abandoned_its_request_cancelled_and_a_successor_completes(self):
        sends: list[str] = []
        supervisor, worker = self.worker_plan(sends)
        paused = self.execute(supervisor, worker=worker)
        self.assertEqual(paused["status"], "expansion_paused")
        result = self.abandon(paused["attempt_id"])
        self.assertEqual(result["cause"], "expansion_paused")
        snapshot, receipt = self.assert_abandoned(paused["attempt_id"], cause="expansion_paused")
        self.assertEqual([(item["request_id"], item["status"]) for item in receipt["expansion"]["requests"]],
                         [(paused["request_id"], "cancelled")])
        events = [json.loads(item["detail"]) for item in snapshot["events"] if item["event"] == "expansion_cancelled"]
        self.assertEqual(events, [{"request_id": paused["request_id"], "cause": "abandoned"}])
        self.assertEqual(stuck_attempts(self.root), [])
        subprocess.run(["git", "-C", str(self.worktree), "checkout", "-q", "--", "target.py"], check=True)
        successor, sends, _, captured = self._run_v8([self.PASS])
        self.assertEqual((successor["status"], sends), ("completed", ["editor", "verifier"]))
        self.assertEqual(captured["envelope"]["predecessors"][0]["terminal_status"], "abandoned")


class ConsumedGrantInheritanceTests(unittest.TestCase):
    """AC7 after AC3(d): a successor inherits consumed grants only, never a cancelled request."""

    def test_only_the_consumed_grant_raises_the_successors_lineage_limit(self):
        from tests.test_expansion_ledger import ExpansionLedgerTests
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            ledger = ExecutionLedger(root / "ledger.sqlite")
            env = expansion_envelope({"max_delegations": 1}, {"delegations": 1, "paid_worker_calls": 1})
            ledger.create_attempt(env)
            producer = lambda sequence: ExpansionLedgerTests.producer(None, env, sequence)
            ledger.decide(env, producer(1), generation=1)
            automatic = ledger.decide(env, producer(2), generation=1)
            self.assertEqual(automatic["expansion"]["status"], "granted")
            escalated = ledger.decide(env, producer(3), generation=1)
            self.assertEqual(escalated["expansion"]["status"], "pending")
            attempt_dir = root / env["attempt_id"]
            attempt_dir.mkdir()
            render = terminal_receipt_renderer(env, attempt_dir, status="abandoned", actor="andy",
                                               explanation="paused too long", cause="expansion_paused")
            with ledger.send_lock():
                ledger.seal_terminal_uncertain(env["attempt_id"], "abandoned", expected_generation=1, actor="andy",
                                               explanation="paused too long", cause="expansion_paused",
                                               receipt_path=attempt_dir / "receipt.json", build_receipt=render)
            requests = {item["request_id"]: (item["status"], (item["grant"] or {}).get("status"))
                        for item in ledger.expansion_state(env["attempt_id"])["requests"]}
            self.assertEqual(sorted(requests.values()), [("cancelled", None), ("granted", "consumed")])
            successor = expansion_envelope({"max_delegations": 1}, {"delegations": 1, "paid_worker_calls": 1},
                                           attempt="successor")
            successor["work_id"] = env["work_id"]
            successor["predecessors"] = ledger.v8_lineage(env["work_id"])[0]
            ledger.create_attempt(successor)
            state = ledger.expansion_state("successor")
            self.assertEqual(state["effective_limits"]["paid_worker_calls"], 2, "base 1 plus the one consumed grant")
            self.assertEqual(state["headroom_remaining"]["paid_worker_calls"], 0)


class AbandonRefusalTests(AbandonFixture):
    """AC4: refusals change nothing and signal nothing; reaping is identity-checked."""

    def _recorded_sleeper(self, attempt_id, generation):
        sleeper = _sleeper()
        self.addCleanup(_stop, sleeper)
        with process_identity.control_scope(self.attempt_dir(attempt_id), generation, attempt_id=attempt_id) as scope:
            scope.register(sleeper.pid, "provider")
        return sleeper

    def _assert_refused(self, attempt_id, reason, *, generation=None, sleeper=None):
        before = self.ledger(read_only=True).snapshot(attempt_id)
        with self.assertRaises(RecoveryRefused) as raised:
            self.abandon(attempt_id, generation=generation)
        self.assertEqual(raised.exception.reason, reason)
        self.assertEqual(self.ledger(read_only=True).snapshot(attempt_id), before)
        if sleeper is not None:
            self.assertIsNone(sleeper.poll(), "a refused abandon must signal nothing")

    def test_a_live_holder_refuses_as_attempt_running(self):
        attempt_id = self.unknown_editor_send()
        sleeper = self._recorded_sleeper(attempt_id, 5)
        with self.ledger().recovery_lock(attempt_id, holder="live"):
            self._assert_refused(attempt_id, "attempt_running", sleeper=sleeper)

    def test_a_recovery_or_decision_in_flight_refuses_as_recovery_in_progress(self):
        attempt_id = self.unknown_editor_send()
        sleeper = self._recorded_sleeper(attempt_id, 5)
        cli = str(Path(__file__).resolve().parents[1] / "cli")
        for holder in ("recovery", "decide"):
            with self.subTest(holder=holder):
                child = subprocess.Popen(
                    [sys.executable, "-c",
                     f"import sys; sys.path.insert(0, {cli!r}); from execution_ledger import ExecutionLedger\n"
                     f"with ExecutionLedger({str(self.run / 'execution' / 'ledger.sqlite')!r}, read_only=True)"
                     f".recovery_lock({attempt_id!r}, holder={holder!r}):\n"
                     "    print('held', flush=True); sys.stdin.readline()\n"],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
                self.assertEqual(child.stdout.readline().strip(), "held")
                try:
                    self._assert_refused(attempt_id, "recovery_in_progress", sleeper=sleeper)
                finally:
                    child.stdin.write("done\n")
                    child.stdin.close()
                    child.wait()
                    child.stdout.close()

    def test_stale_generation_terminal_attempt_unsafe_directory_and_unreadable_ledger(self):
        attempt_id = self.unknown_editor_send()
        sleeper = self._recorded_sleeper(attempt_id, 5)
        self._assert_refused(attempt_id, "owner_generation_stale", generation=7, sleeper=sleeper)
        link = self.run / "execution" / ("f" * 32)
        link.symlink_to(self.attempt_dir(attempt_id))
        with self.assertRaises(RecoveryRefused) as raised:
            abandon_delivery("sample", "f" * 32, actor="a", explanation="e", expected_generation=1, root=self.root)
        self.assertEqual(raised.exception.reason, "attempt_dir_unsafe")
        link.unlink()
        self.abandon(attempt_id)
        with self.assertRaises(RecoveryRefused) as raised:
            self.abandon(attempt_id, generation=2)
        self.assertEqual(raised.exception.reason, "attempt_not_started")
        ledger_path = self.run / "execution" / "ledger.sqlite"
        ledger_path.rename(self.run / "moved.sqlite")
        ledger_path.symlink_to(self.run / "moved.sqlite")
        with self.assertRaises(RecoveryRefused) as raised:
            self.abandon(attempt_id, generation=2)
        self.assertEqual(raised.exception.reason, "lead_guard_ledger_unreadable")

    def test_abandon_reaps_every_generation_by_identity_before_sealing(self):
        attempt_id = self.unknown_editor_send()
        alive = _sleeper()
        mismatched = _sleeper()
        self.addCleanup(_stop, alive)
        self.addCleanup(_stop, mismatched)
        orphan_leader = subprocess.Popen(
            [sys.executable, "-c", "import subprocess, sys\n"
             "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
             "print(child.pid, flush=True); sys.stdin.readline()\n"],
            start_new_session=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        member = int(orphan_leader.stdout.readline())
        self.addCleanup(lambda: process_identity.pid_alive(member) and os.kill(member, 9))
        attempt_dir = self.attempt_dir(attempt_id)
        with process_identity.control_scope(attempt_dir, 5, attempt_id=attempt_id) as scope:
            scope.register(alive.pid, "provider")
            scope.register(orphan_leader.pid, "maf")
        with process_identity.control_scope(attempt_dir, 6, attempt_id=attempt_id) as scope:
            scope.register(mismatched.pid, "test")
        groups = attempt_dir / "control-g6.groups.jsonl"
        entry = json.loads(groups.read_text())
        entry["leader_start"] = entry["leader_start"].rsplit(".", 1)[0][:-1] + "0.000000" \
            if entry["leader_start"].startswith("darwin:") else "linux:x:1"
        groups.write_text(json.dumps(entry) + "\n")
        orphan_leader.stdin.write("exit\n")
        orphan_leader.stdin.close()
        orphan_leader.wait()
        orphan_leader.stdout.close()
        result = self.abandon(attempt_id)
        self.assertEqual([(item["owner_generation"], item["kind"], item["action"]) for item in result["reaped"]],
                         [(5, "provider", "killed_group"), (5, "maf", "killed_members"), (6, "test", "skipped_identity_mismatch")])
        alive.wait(timeout=10)
        self.assertIsNone(mismatched.poll(), "an identity mismatch is reported, never signalled")
        self.assertEqual(self.ledger(read_only=True).snapshot(attempt_id)["status"], "abandoned")


class ProbeTests(TerminationFixture):
    """A8: the liveness probe never creates the lock and never fails a live acquisition."""

    def test_the_probe_is_read_only_and_a_live_run_outlasts_it(self):
        envelope, _, _, ledger = self.prepare()
        attempt_id = envelope["attempt_id"]
        lock_path = self.run / "execution" / f"recovery-{attempt_id}.lock"
        self.assertEqual(ledger.probe_recovery_lock(attempt_id), "absent")
        self.assertFalse(lock_path.exists(), "the probe never creates the lock file")
        with ledger.recovery_lock(attempt_id, holder="live"):
            self.assertEqual(ledger.probe_recovery_lock(attempt_id), "held")
        self.assertEqual(ledger.probe_recovery_lock(attempt_id), "free")
        # A probe holding the lock for an instant, as a concurrent probe would.
        fd = os.open(lock_path, os.O_RDONLY)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        release = threading.Timer(0.05, lambda: (fcntl.flock(fd, fcntl.LOCK_UN), os.close(fd)))
        release.start()
        with ledger.recovery_lock(attempt_id, holder="live"):
            pass
        release.join()


class LeadCliTests(AbandonFixture):
    """R8, AC9: ``flow run delivery-lead`` and ``abandon-delivery`` through the CLI entry."""

    def cli(self, *argv):
        out = io.StringIO()
        with patch.object(sys, "argv", ["flow", "run", *argv, "--project-root", str(self.root)]), \
             contextlib.redirect_stdout(out):
            code = flow.main()
        return code, out.getvalue()

    def test_all_four_lead_actions_and_their_refusal_codes(self):
        self.prepare()
        self.assertEqual(self.cli("delivery-lead", "sample", "attention", "--expected-generation", "1"),
                         (0, "lead: attention_required\ngeneration: 1\n"))
        self.assertEqual(self.cli("delivery-lead", "sample", "attention", "--expected-generation", "1"),
                         (2, "refused: lead_status_invalid: only an active Delivery Lead can require attention\n"))
        self.assertEqual(self.cli("delivery-lead", "sample", "release", "--expected-generation", "1")[0], 0)
        self.assertEqual(self.cli("delivery-lead", "sample", "resume", "--expected-generation", "1"),
                         (2, "refused: owner_required: resume or supersede requires an explicit owner identity\n"))
        self.assertEqual(self.cli("delivery-lead", "sample", "resume", "--expected-generation", "3", "--owner", "x"),
                         (2, "refused: lead_generation_stale: stale delivery owner generation\n"))
        self.assertEqual(self.cli("delivery-lead", "sample", "resume", "--expected-generation", "1", "--owner", "x"),
                         (0, "lead: active\ngeneration: 2\n"))
        self.assertEqual(self.cli("delivery-lead", "sample", "supersede", "--expected-generation", "2", "--owner", "y"),
                         (0, "lead: active\ngeneration: 3\n"))

    def test_an_uncertain_send_refuses_a_lead_resume_until_it_is_abandoned(self):
        attempt_id = self.unknown_editor_send()
        code, out = self.cli("delivery-lead", "sample", "resume", "--expected-generation", "1", "--owner", "x", "--json")
        self.assertEqual((code, json.loads(out)["code"]), (2, "reconciliation_required"))
        code, out = self.cli("abandon-delivery", "sample", attempt_id, "--actor", "shaper", "--explanation", "dead end",
                             "--expected-generation", "3")
        self.assertEqual((code, out.split(":")[0:2]), (2, ["refused", " owner_generation_stale"]))
        code, out = self.cli("abandon-delivery", "sample", attempt_id, "--actor", "shaper", "--explanation", "dead end",
                             "--expected-generation", "1", "--json")
        self.assertEqual((code, json.loads(out)["status"]), (0, "abandoned"))
        self.assertEqual(self.cli("delivery-lead", "sample", "resume", "--expected-generation", "1", "--owner", "x")[0], 0)


class DiagnosticsTests(AbandonFixture):
    """R9, AC10: inspect-delivery and ``flow run stuck`` name the state and the next command."""

    def test_inspect_shows_each_attempt_status_its_stopper_and_the_next_command(self):
        started = self.unknown_editor_send()
        view = inspect_delivery("sample", started, root=self.root)["attempt"]
        self.assertEqual((view["attempt_status"], view["expansion_status"], view["control"]["parent"]),
                         ("started", "none", "closed"))
        self.assertEqual(view["pending_unknowns"], [self.ledger(read_only=True).snapshot(started)["actions"][0]["action_id"]])
        self.assertEqual(view["next_command"], f"flow run abandon-delivery sample {started} --actor NAME "
                                               "--explanation TEXT --expected-generation 1")
        self.assertEqual([record["verdict"] for record in view["control"]["records"]], ["closed"])
        self.seal(started, "cancelled", actor="shaper")
        cancelled = inspect_delivery("sample", started, root=self.root)["attempt"]
        self.assertEqual((cancelled["attempt_status"], cancelled["termination"]["actor"], cancelled["termination"]["cause"],
                          cancelled["evidence_damage"], cancelled["next_command"]),
                         ("cancelled", "shaper", "cancel_request", [], None))
        second = self.unknown_editor_send()
        (self.attempt_dir(second) / "baseline.json").unlink()
        self.abandon(second)
        abandoned = inspect_delivery("sample", second, root=self.root)["attempt"]
        self.assertEqual((abandoned["attempt_status"], abandoned["termination"]["actor"], abandoned["evidence_damage"]),
                         ("abandoned", "andy", [{"kind": "baseline_missing"}]))

    def test_stuck_lists_exactly_the_started_attempts_with_one_next_command_each(self):
        stuck_id = self.unknown_editor_send()
        template = self.ledger(read_only=True).snapshot(stuck_id)["envelope"]
        sleeper = _sleeper()
        self.addCleanup(_stop, sleeper)

        def attempt_in(work_id, attempt_id):
            run_dir = self.root / ".flow" / "runs" / work_id
            (run_dir / "execution" / attempt_id).mkdir(parents=True)
            (run_dir / "run.json").write_bytes((self.run / "run.json").read_bytes())
            envelope = copy.deepcopy(template)
            envelope.update(work_id=work_id, attempt_id=attempt_id,
                            checkpoint_dir=str(run_dir / "execution" / attempt_id / "checkpoints"))
            ledger = ExecutionLedger(run_dir / "execution" / "ledger.sqlite")
            ledger.create_attempt(envelope)
            return run_dir, ledger, envelope

        live_dir, _, live_env = attempt_in("live", "1" * 32)
        with process_identity.control_scope(live_dir / "execution" / live_env["attempt_id"], 1,
                                            attempt_id=live_env["attempt_id"]):
            pass
        record_path = live_dir / "execution" / live_env["attempt_id"] / "control-g1.json"
        record = json.loads(record_path.read_text())
        record.update(pid=sleeper.pid, start_time=process_identity.start_time(sleeper.pid))
        record_path.write_text(json.dumps(record))
        (live_dir / "execution" / live_env["attempt_id"] / "control-g1.closed").unlink()
        paused_dir, paused_ledger, paused_env = attempt_in("paused", "2" * 32)
        action = self._proposal(paused_env, "editor", 1)
        with sqlite3.connect(paused_dir / "execution" / "ledger.sqlite") as db:
            db.execute("INSERT INTO expansion_requests VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                       ("exp-wait", paused_env["attempt_id"], paused_env["attempt_id"], 1, "delegate",
                        action["action_id"], '["delegations"]', 1, "0" * 64, "more", "pending", "2026-09-27T00:00:00+00:00"))
        done_dir, _, done_env = attempt_in("done", "3" * 32)
        with sqlite3.connect(done_dir / "execution" / "ledger.sqlite") as db:
            db.execute("UPDATE attempts SET status='completed' WHERE attempt_id=?", (done_env["attempt_id"],))
        before = {path: path.read_bytes() for path in sorted(self.root.joinpath(".flow").rglob("*")) if path.is_file()}
        found = {item["work_id"]: item for item in stuck_attempts(self.root)}
        self.assertEqual(sorted(found), ["live", "paused", "sample"])
        self.assertTrue(found["live"]["live"])
        self.assertTrue(found["live"]["next_command"].startswith("flow run cancel-delivery live " + "1" * 32))
        self.assertTrue(found["paused"]["next_command"].startswith(f"flow run decide-expansion paused {'2' * 32} exp-wait"))
        self.assertEqual(found["paused"]["open_expansion"], "exp-wait")
        self.assertTrue(found["sample"]["next_command"].startswith(f"flow run abandon-delivery sample {stuck_id}"))
        self.assertEqual(found["sample"]["uncertain"], {"started": 0, "unknown": 1})
        after = {path: path.read_bytes() for path in sorted(self.root.joinpath(".flow").rglob("*")) if path.is_file()}
        self.assertEqual(after, before, "stuck is read-only")
        out = io.StringIO()
        with patch.object(sys, "argv", ["flow", "run", "stuck", "--project-root", str(self.root)]), \
             contextlib.redirect_stdout(out):
            self.assertEqual(flow.main(), 0)
        self.assertEqual(out.getvalue().count("  next: flow run "), 3)
