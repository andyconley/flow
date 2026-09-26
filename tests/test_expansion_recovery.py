"""Resuming an expansion pause replays the paused proposal under its decision (ADR 0017)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

import delivery_gateway  # noqa: E402
from delivery_recovery import RecoveryRefused  # noqa: E402
from execution_contracts import digest, envelope_digest, expected_manager_call_id  # noqa: E402
from tests.test_expansion_gateway import ExpansionGatewayFixture  # noqa: E402


class ExpansionRecoveryFixture(ExpansionGatewayFixture):
    def patched(self):
        return (patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])),
                patch("delivery_gateway.run_status", return_value=self.state),
                patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role))

    def decide(self, attempt, request, *, approve):
        generation = self.ledger().snapshot(attempt)["owner_generation"]
        with self.patched()[0]:
            return delivery_gateway.decide_expansion("sample", attempt, request, approve=approve,
                                                     expected_generation=generation, actor="andy",
                                                     explanation="bounded extra unit", root=self.root)

    def recover(self, attempt, supervisor, *, worker=None, manager=None):
        first, second, third = self.patched()
        with first, second, third:
            return delivery_gateway.recover_delivery("sample", attempt, root=self.root, supervisor=supervisor,
                                                     worker_adapter=worker, manager_adapter=manager)

    def checkpoint(self, envelope, proposal):
        path = Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json"
        path.write_text(json.dumps({"checkpoint_id": proposal["checkpoint_id"], "workflow_name": "flow-magentic-delivery-v8",
                                    "pending_request_info_events": {f"flow-magentic-action-{proposal['sequence']}": {}}}))


class WorkerExpansionRecoveryTests(ExpansionRecoveryFixture):
    def setUp(self):
        super().setUp()
        self.sends: list[str] = []
        supervisor, self.worker = self.worker_plan(self.sends)
        paused = self.execute(supervisor, worker=self.worker)
        self.attempt, self.request = paused["attempt_id"], paused["request_id"]
        self.paused_action = self.ledger().snapshot(self.attempt)["actions"][2]["request"]

    def resume_plan(self, replies, *, then=()):
        """Re-emit the paused proposal in pending mode, then propose ``then`` sequences."""
        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            self.assertEqual((kwargs["resume"]["kind"], kwargs["resume"]["action_id"]),
                             ("pending", self.paused_action["action_id"]))
            replies.append(on_action(dict(self.paused_action)))
            for sequence in then:
                proposal = self._proposal(envelope, "verifier", sequence)
                self.checkpoint(envelope, proposal)
                replies.append(on_action(proposal))
            return {"attempt_id": envelope["attempt_id"]}
        return supervisor

    # AC6 (and M5, M7): the paused proposal runs once under the grant with its original identity.
    def test_approval_replays_the_paused_proposal_once_under_its_grant(self):
        self.decide(self.attempt, self.request, approve=True)
        replies: list[dict] = []
        result = self.recover(self.attempt, self.resume_plan(replies), worker=self.worker)
        self.assertEqual((result["mode"], result["status"]), ("pending", "completed"), result)
        self.assertEqual(self.sends, ["editor", "verifier", "verifier"], "no completed action is sent again")
        self.assertEqual(replies[0]["action_id"], self.paused_action["action_id"])
        ledger = self.ledger()
        row = ledger.snapshot(self.attempt)["actions"][2]
        self.assertEqual((row["action_id"], row["status"]), (self.paused_action["action_id"], "completed"))
        events = [item for item in ledger.snapshot(self.attempt)["events"] if item["action_id"] == row["action_id"]]
        self.assertIn(("policy_denied", "delegation_cap"), [(item["event"], item["detail"]) for item in events],
                      "the denial stays recorded")
        self.assertIn(("policy_allowed", "expansion_granted"), [(item["event"], item["detail"]) for item in events])
        state = ledger.expansion_state(self.attempt)
        [request] = state["requests"]
        self.assertEqual((request["grant"]["status"], request["grant"]["consumed_by"]), ("consumed", row["action_id"]))
        self.assertEqual(state["effective_limits"]["delegations"], 3, "effective limit is base plus consumed grants")

    # AC6 and M5: a grant is consumed once; a second replay under it is refused.
    def test_a_consumed_grant_cannot_allow_the_proposal_again(self):
        self.decide(self.attempt, self.request, approve=True)
        refusals = []

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            on_action(dict(self.paused_action))
            ledger = self.ledger()
            generation = ledger.snapshot(self.attempt)["owner_generation"]
            for tamper in (False, True):
                if tamper:
                    # Even if the row were denied again, the used grant stays used.
                    import sqlite3
                    with sqlite3.connect(ledger.path) as db:
                        db.execute("UPDATE actions SET status='denied' WHERE action_id=?", (self.paused_action["action_id"],))
                try:
                    ledger.regrant_expanded_action(envelope, dict(self.paused_action), generation=generation)
                except RecoveryRefused as exc:
                    refusals.append(exc.reason)
                if tamper:
                    with sqlite3.connect(ledger.path) as db:
                        db.execute("UPDATE actions SET status='completed' WHERE action_id=?", (self.paused_action["action_id"],))
            return {"attempt_id": envelope["attempt_id"]}

        self.recover(self.attempt, supervisor, worker=self.worker)
        self.assertEqual(refusals, ["expansion_grant_consumed", "expansion_grant_consumed"])
        self.assertEqual(self.sends, ["editor", "verifier", "verifier"])

    # AC7: a denial is reported to the manager; a later proposal of the same kind escalates anew.
    def test_denial_is_reported_to_the_manager_and_a_new_proposal_escalates_again(self):
        self.decide(self.attempt, self.request, approve=False)
        replies: list[dict] = []
        result = self.recover(self.attempt, self.resume_plan(replies, then=(4,)), worker=self.worker)
        self.assertEqual(replies[0], {"status": "denied", "action_id": self.paused_action["action_id"],
                                      "reason": "delegation_cap", "summary": "Flow denied this specialist call"})
        self.assertEqual(self.sends, ["editor", "verifier"], "nothing is sent for a denied expansion")
        self.assertEqual(result["status"], "expansion_paused")
        requests = self.ledger().expansion_state(self.attempt)["requests"]
        self.assertEqual([item["status"] for item in requests], ["denied", "pending"])
        with self.assertRaises(RecoveryRefused) as raised:
            self.decide(self.attempt, self.request, approve=True)
        self.assertEqual(raised.exception.reason, "expansion_already_decided")

    def test_denial_then_the_attempt_seals_within_the_charter(self):
        # With the retry refused, the only verdict is the earlier failing review:
        # the attempt finishes as a sealed, valid failed receipt, not a pause.
        self.decide(self.attempt, self.request, approve=False)
        result = self.recover(self.attempt, self.resume_plan([]), worker=self.worker)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.ledger().snapshot(self.attempt)["status"], "failed")
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(receipt["expansion"]["requests"][0]["status"], "denied")

    # Q2: a seal closes an approved grant the run never used.
    def test_a_failed_resume_seals_and_lapses_the_unused_grant(self):
        self.decide(self.attempt, self.request, approve=True)

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            raise RuntimeError("the restored child failed before replaying the proposal")

        result = self.recover(self.attempt, supervisor, worker=self.worker)
        self.assertEqual(result["status"], "failed", result)
        [request] = self.ledger().expansion_state(self.attempt)["requests"]
        self.assertEqual((request["status"], request["grant"]["status"]), ("granted", "lapsed"))
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(receipt["expansion"]["requests"][0]["grant"]["status"], "lapsed")

    # AC6/M7: an undecided pause is not resumable.
    def test_a_pending_request_refuses_recovery(self):
        before = self.ledger().snapshot(self.attempt)
        with self.assertRaises(RecoveryRefused) as raised:
            self.recover(self.attempt, self.resume_plan([]), worker=self.worker)
        self.assertEqual(raised.exception.reason, "expansion_decision_required")
        self.assertEqual(self.ledger().snapshot(self.attempt), before)


class ManagerExpansionRecoveryTests(ExpansionRecoveryFixture):
    limits = {"max_concurrent": 1, "max_paid_worker_calls": 1, "max_manager_calls": 1}

    def manager_message(self, envelope, sequence):
        messages = [{"role": "user", "contents": [{"type": "text", "text": f"facts {sequence}"}]}]
        request = {"schema_version": 1, "attempt_id": envelope["attempt_id"], "envelope_digest": envelope_digest(envelope),
                   "sequence": sequence, "phase": "facts", "manager_round": 1, "prompt_digest": digest(messages)}
        return {**request, "call_id": expected_manager_call_id(request), "messages": messages}

    def run_manager(self, envelope, on_manager, sequences):
        for sequence in sequences:
            on_manager(self.manager_message(envelope, sequence))

    def pause_before_any_action(self, sends):
        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            self.run_manager(envelope, on_manager, (1, 2))
            return {"attempt_id": envelope["attempt_id"]}

        def manager(message, *, envelope, workspace):
            sends.append(message["sequence"])
            return {"output": f"Fixture facts {message['sequence']}"}

        paused = self.execute(supervisor, manager=manager)
        self.assertEqual(paused["status"], "expansion_paused")
        return paused, manager

    # AC6 (restart mode): before any worker checkpoint the child restarts and replays.
    def test_approved_manager_call_restarts_and_replays_earlier_calls_from_the_ledger(self):
        sends: list[int] = []
        paused, manager = self.pause_before_any_action(sends)
        self.decide(paused["attempt_id"], paused["request_id"], approve=True)
        seen = {}

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            seen["resume"] = kwargs.get("resume")
            self.run_manager(envelope, on_manager, (1, 2))
            return {"attempt_id": envelope["attempt_id"]}

        result = self.recover(paused["attempt_id"], supervisor, manager=manager)
        self.assertEqual(result["mode"], "restart")
        self.assertIsNone(seen["resume"], "restart sends a fresh start on the same envelope")
        self.assertEqual(sends, [1, 2], "call 1 replays from the ledger; call 2 is sent once")
        [request] = self.ledger().expansion_state(paused["attempt_id"])["requests"]
        self.assertEqual(request["grant"]["status"], "consumed")

    # AC7 (E5 a): a denied manager call seals the attempt failed with the limit as the reason.
    def test_denied_manager_call_seals_the_attempt_failed(self):
        sends: list[int] = []
        paused, manager = self.pause_before_any_action(sends)
        self.decide(paused["attempt_id"], paused["request_id"], approve=False)

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            raise AssertionError("a denied manager call is never replayed")

        result = self.recover(paused["attempt_id"], supervisor, manager=manager)
        self.assertEqual((result["mode"], result["status"]), ("seal", "failed"))
        self.assertIn("manager_call_cap", result["reason"])
        self.assertEqual(sends, [1])

    # Q1: a hard worker denial binds its position, so a later manager pause resumes from it.
    def test_manager_pause_after_a_hard_worker_denial_resumes_in_answer_mode(self):
        sends: list[int] = []
        replies: list[dict] = []

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            self.run_manager(envelope, on_manager, (1,))
            for sequence in (1, 2):  # the editor again after completing: producer_already_completed
                proposal = self._proposal(envelope, "editor", sequence)
                self.checkpoint(envelope, proposal)
                replies.append(on_action(proposal))
            self.run_manager(envelope, on_manager, (2,))
            return {"attempt_id": envelope["attempt_id"]}

        def manager(message, *, envelope, workspace):
            sends.append(message["sequence"])
            return {"output": "Fixture facts"}

        def worker(action, *, envelope, workspace):
            (workspace / "target.py").write_text("new\n")
            return self._result("codex", "editor-model", "Edited target")

        paused = self.execute(supervisor, worker=worker, manager=manager)
        self.assertEqual(paused["status"], "expansion_paused", paused)
        self.assertEqual(replies[1]["reason"], "producer_already_completed")
        self.decide(paused["attempt_id"], paused["request_id"], approve=True)
        seen = {}

        def resumed(envelope, task, on_manager, on_action, **kwargs):
            seen["resume"] = kwargs["resume"]
            self.run_manager(envelope, on_manager, (2,))
            return {"attempt_id": envelope["attempt_id"]}

        result = self.recover(paused["attempt_id"], resumed, worker=worker, manager=manager)
        self.assertEqual(result["mode"], "answer")
        self.assertEqual(seen["resume"]["result"], {"status": "denied", "action_id": replies[1]["action_id"],
                                                    "reason": "producer_already_completed",
                                                    "summary": "Flow denied this specialist call"})
        self.assertEqual(sends, [1, 2])

    # AC6 (answer mode): after a worker checkpoint, restore from it and replay the denied call.
    def test_approved_manager_call_after_a_worker_checkpoint_resumes_in_answer_mode(self):
        sends: list[int] = []
        worker_sends: list[str] = []

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            self.run_manager(envelope, on_manager, (1,))
            proposal = self._proposal(envelope, "editor", 1)
            self.checkpoint(envelope, proposal)
            on_action(proposal)
            self.run_manager(envelope, on_manager, (2,))
            return {"attempt_id": envelope["attempt_id"]}

        def manager(message, *, envelope, workspace):
            sends.append(message["sequence"])
            return {"output": f"Fixture facts {message['sequence']}"}

        def worker(action, *, envelope, workspace):
            worker_sends.append(action["assignment_id"])
            (workspace / "target.py").write_text("new\n")
            return self._result("codex", "editor-model", "Edited target")

        paused = self.execute(supervisor, worker=worker, manager=manager)
        self.assertEqual(paused["status"], "expansion_paused")
        self.decide(paused["attempt_id"], paused["request_id"], approve=True)
        seen = {}

        def resumed(envelope, task, on_manager, on_action, **kwargs):
            seen["resume"] = kwargs["resume"]
            self.run_manager(envelope, on_manager, (2,))
            return {"attempt_id": envelope["attempt_id"]}

        result = self.recover(paused["attempt_id"], resumed, worker=worker, manager=manager)
        self.assertEqual(result["mode"], "answer")
        self.assertEqual(seen["resume"]["manager_calls_committed"], 1)
        self.assertEqual(sends, [1, 2])
        self.assertEqual(worker_sends, ["editor"], "the completed action is answered, not resent")


if __name__ == "__main__":
    import unittest

    unittest.main()
