"""The pre-grant token check (ADR 0020): AC10, AC11, AC12, AC12b, AC12c and AC13 at the ledger.

Every grant path that can lead to a paid send checks the lineage charge
first. A shortfall one tranche can clear expands under ADR 0017: automatic
within headroom, otherwise a pause for ``decide-expansion`` (including at
zero headroom, as amended). A shortfall needing more than one tranche, or a
tranche past the absolute ceiling, is a hard refusal. Regrants and reissues
never expand.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "cli"))
sys.path.insert(0, str(REPO_ROOT / "tests"))
from execution_contracts import ContractError, token_usage_block  # noqa: E402
from execution_ledger import ExecutionLedger  # noqa: E402
from tests.test_expansion_ledger import manager_request, v8  # noqa: E402
from tests.test_structured_verifier_ledger import _action  # noqa: E402

M, T, U = 10_000, 5_000, 2_000


def budget(headroom=None, *, manager="claude", attempt="gate", concurrent=1, paid=4, delegations=6, **limits):
    env = v8({"max_paid_worker_calls": paid, "max_delegations": delegations, "max_concurrent": concurrent,
              "max_lineage_tokens": M, "token_tranche": T, "unobserved_send_tokens": U, **limits},
             headroom, manager=manager, attempt=attempt)
    return env


def claude_result(action, charged):
    output = "done"
    return {"schema_version": 1, "status": "completed", "provider": "claude", "model": action["model"],
            "physical_call": True, "evidence_level": "flow_observed_claude_cli_completed_turn", "output": output,
            "output_sha256": hashlib.sha256(output.encode()).hexdigest(), "session_id": "s",
            "usage": {"input_tokens": charged, "output_tokens": 0}}


class GateFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.ledger = ExecutionLedger(Path(self.temporary.name) / "ledger.sqlite")

    def start(self, env):
        env["checkpoint_dir"] = str(Path(self.temporary.name) / env["attempt_id"] / "checkpoints")
        self.ledger.create_attempt(env)
        self.env = env
        self.sequence = self.manager_sequence = 0
        return env

    def producer(self):
        self.sequence += 1
        return _action(self.env, self.sequence, self.env["roster"][1], f"Produce {self.sequence}.")

    def spend(self, charged):
        """One completed paid manager call that reports ``charged`` tokens (a producer completes only once)."""
        self.manager_sequence += 1
        request = manager_request(self.env, self.manager_sequence)
        grant = self.ledger.decide_manager_call(self.env, request, generation=1)
        self.assertTrue(grant["allowed"], grant)
        self.assertTrue(self.ledger.consume_manager_grant(request["call_id"], grant["grant_id"], generation=1))
        self.ledger.observe_manager_response(request["call_id"], {
            "status": "completed", "output": "x", "output_sha256": hashlib.sha256(b'"x"').hexdigest(),
            "usage": {"input_tokens": charged, "output_tokens": 0}}, generation=1)
        return request

    def spend_producer(self, charged):
        """The attempt's one completed paid producer call, reporting ``charged`` tokens."""
        action = self.producer()
        grant = self.ledger.decide(self.env, action, generation=1)
        self.assertTrue(grant["allowed"], grant)
        self.assertTrue(self.ledger.consume_grant(action["action_id"], grant["grant_id"], generation=1))
        result = claude_result(action, charged)
        self.ledger.observe_response(action["action_id"], result, generation=1)
        self.ledger.complete(action["action_id"], result, generation=1)
        return action

    def charged(self):
        with sqlite3.connect(self.ledger.path) as db:
            return ExecutionLedger._lineage_charged(db, self.env)

    def requests(self):
        return self.ledger.expansion_state(self.env["attempt_id"])["requests"]

    def set_row(self, table, key, row_id, **values):
        with sqlite3.connect(self.ledger.path) as db:
            assignments = ",".join(f"{name}=?" for name in values)
            db.execute(f"UPDATE {table} SET {assignments} WHERE {key}=?", (*values.values(), row_id))

    def bind_checkpoint(self, action):
        """Bind the paused proposal's restore position, as the gateway does before a pause."""
        directory = Path(self.env["checkpoint_dir"])
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{action['checkpoint_id']}.json"
        path.write_text(json.dumps({"checkpoint_id": action["checkpoint_id"], "workflow_name": "flow-magentic-delivery-v8",
                                    "pending_request_info_events": {f"flow-magentic-action-{action['sequence']}": {}}}))
        with sqlite3.connect(self.ledger.path) as db:
            seq = db.execute("SELECT COALESCE(MAX(seq),0) FROM events WHERE attempt_id=?", (self.env["attempt_id"],)).fetchone()[0]
        self.ledger.bind_magentic_checkpoint(self.env["attempt_id"], action["checkpoint_id"], "worker", action["action_id"],
                                             seq, str(path), generation=1)

    def activate_recovery(self, generation=1):
        with sqlite3.connect(self.ledger.path) as db:
            db.execute("INSERT INTO attempt_recoveries VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                       ("r" * 32, self.env["attempt_id"], generation, generation, 1, "andy", "pending", None, "[]",
                        "[]", "[]", "2026-09-27T00:00:00+00:00"))


class InitialGrantTests(GateFixture):
    def test_at_the_cap_a_paid_action_pauses_for_a_decision_before_any_send(self):
        self.start(budget())
        self.spend(M)
        action = self.producer()
        decision = self.ledger.decide(self.env, action, generation=1)
        self.assertEqual((decision["allowed"], decision["reason"]), (False, "token_cap"))
        self.assertEqual(decision["expansion"]["status"], "pending", "zero headroom pauses, as amended")
        [request] = self.requests()
        self.assertEqual((request["limits"], request["denied_row_id"]), (["tokens"], action["action_id"]))

    def test_at_the_cap_a_paid_manager_call_pauses_and_an_unpaid_one_is_granted(self):
        self.start(budget(manager="claude"))
        self.spend(M)
        decision = self.ledger.decide_manager_call(self.env, manager_request(self.env, 2), generation=1)
        self.assertEqual((decision["allowed"], decision["reason"], decision["expansion"]["status"]),
                         (False, "token_cap", "pending"))
        unpaid = self.start(budget(attempt="unpaid", manager="ollama"))
        self.spend_producer(M)
        self.assertTrue(self.ledger.decide_manager_call(unpaid, manager_request(unpaid, 1), generation=1)["allowed"])

    def test_the_verifier_is_never_token_checked(self):
        self.start(budget())
        self.spend(M)
        verifier = _action(self.env, self.sequence + 1, self.env["roster"][0], "Verify.")
        self.assertTrue(self.ledger.decide(self.env, verifier, generation=1)["allowed"])


class JustUnderTests(GateFixture):
    def test_one_under_is_allowed_then_the_observed_call_closes_the_gate(self):
        self.start(budget())
        self.spend(M - 1)
        self.spend(4_000)  # allowed at M - 1; observed usage passes the cap
        self.assertEqual(self.charged()["total"], M - 1 + 4_000)
        refused = self.ledger.decide(self.env, self.producer(), generation=1)
        self.assertEqual(refused["reason"], "token_cap")
        snapshot = self.ledger.snapshot(self.env["attempt_id"])
        block = token_usage_block(self.env, snapshot["actions"], snapshot["manager_calls"], predecessor_charged=0,
                                  tranches_granted=0)
        self.assertEqual(block["overshoot"], M - 1 + 4_000 - M)


class TrancheTests(GateFixture):
    def test_one_tranche_is_granted_automatically_and_raises_the_cap_by_a_tranche(self):
        self.start(budget({"tokens": 1}))
        self.spend(M)
        action = self.producer()
        decision = self.ledger.decide(self.env, action, generation=1)
        self.assertEqual((decision["allowed"], decision["reason"]), (True, "expansion_granted"))
        [request] = self.requests()
        self.assertEqual((request["grant"]["authority"], request["grant"]["consumed_by"]),
                         ("charter_headroom", action["action_id"]))
        with sqlite3.connect(self.ledger.path) as db:
            effective = ExecutionLedger._effective_limits(db, self.env)
        self.assertEqual(effective["tokens"], 1)
        self.assertTrue(self.ledger.consume_grant(action["action_id"], decision["grant_id"], generation=1))
        result = claude_result(action, T - 1)
        self.ledger.observe_response(action["action_id"], result, generation=1)
        self.ledger.complete(action["action_id"], result, generation=1)
        # M + (T - 1) is under M + T; the next paid call is still allowed.
        self.assertTrue(self.ledger.decide_manager_call(self.env, manager_request(self.env, 2), generation=1)["allowed"])

    def test_the_second_hit_beyond_headroom_pauses_for_the_engineer(self):
        self.start(budget({"tokens": 1}))
        self.spend(M)
        self.spend(T)  # the first hit: granted from headroom, then observed
        [automatic] = self.requests()
        self.assertEqual(automatic["grant"]["authority"], "charter_headroom")
        decision = self.ledger.decide(self.env, self.producer(), generation=1)
        self.assertEqual((decision["reason"], decision["expansion"]["status"]), ("token_cap", "pending"))


class MoreThanOneTrancheTests(GateFixture):
    def assert_hard(self):
        action = self.producer()
        decision = self.ledger.decide(self.env, action, generation=1)
        self.assertEqual((decision["allowed"], decision["reason"]), (False, "token_cap"))
        self.assertNotIn("expansion", decision)
        self.assertEqual(self.requests(), [], "no expansion request is created")

    def test_a_shortfall_of_a_whole_tranche_is_hard_with_headroom_available(self):
        self.start(budget({"tokens": 3}))
        self.spend(M + T)  # needs two tranches
        self.assert_hard()

    def test_a_shortfall_of_a_whole_tranche_is_hard_with_no_headroom(self):
        self.start(budget())
        self.spend(M + T + 1)
        self.assert_hard()

    def test_a_tranche_past_the_absolute_ceiling_is_hard(self):
        # 1,999,000 + one 2,000 tranche would pass the 2,000,000 ceiling.
        self.start(budget(attempt="ceiling", max_lineage_tokens=1_999_000, token_tranche=2_000,
                          unobserved_send_tokens=2_000))
        self.spend(1_999_000)
        self.assert_hard()


class ConcurrentOvershootTests(GateFixture):
    def test_two_outstanding_grants_can_overshoot_by_at_most_both_calls(self):
        self.start(budget(concurrent=2))
        self.spend(M - 1)
        first = self.producer()
        first_grant = self.ledger.decide(self.env, first, generation=1)
        second = self.producer()
        second_grant = self.ledger.decide(self.env, second, generation=1)
        self.assertTrue(first_grant["allowed"] and second_grant["allowed"], "neither is observed yet")
        for action, grant, charged in ((first, first_grant, 3_000), (second, second_grant, 4_000)):
            self.assertTrue(self.ledger.consume_grant(action["action_id"], grant["grant_id"], generation=1))
            result = claude_result(action, charged)
            self.ledger.observe_response(action["action_id"], result, generation=1)
            self.ledger.complete(action["action_id"], result, generation=1)
        refused = self.ledger.decide_manager_call(self.env, manager_request(self.env, self.manager_sequence + 1), generation=1)
        self.assertEqual(refused["reason"], "token_cap")
        snapshot = self.ledger.snapshot(self.env["attempt_id"])
        overshoot = token_usage_block(self.env, snapshot["actions"], snapshot["manager_calls"], predecessor_charged=0,
                                      tranches_granted=0)["overshoot"]
        self.assertLessEqual(overshoot, 3_000 + 4_000)
        self.assertEqual(overshoot, M - 1 + 7_000 - M)


class RegrantAndReissueTests(GateFixture):
    """Regrants and reissues check the token cap too, and never expand."""

    def test_a_recovered_action_regrant_is_denied_hard(self):
        self.start(budget())
        waiting = self.producer()
        self.assertTrue(self.ledger.decide(self.env, waiting, generation=1)["allowed"])
        self.set_row("actions", "action_id", waiting["action_id"], status="not_dispatched",
                     reason="recovery_unconsumed_grant", grant_id=None)
        self.spend(M)
        self.activate_recovery()
        decision = self.ledger.regrant_recovered_action(self.env, waiting, generation=1)
        self.assertEqual((decision["allowed"], decision["reason"]), (False, "token_cap"))
        self.assertEqual(self.requests(), [])

    def test_an_expanded_action_regrant_still_over_the_cap_rolls_back(self):
        self.start(budget(paid=1))
        spent = self.producer()
        grant = self.ledger.decide(self.env, spent, generation=1)
        self.ledger.consume_grant(spent["action_id"], grant["grant_id"], generation=1)
        self.set_row("actions", "action_id", spent["action_id"], status="failed")
        paused = self.producer()
        decision = self.ledger.decide(self.env, paused, generation=1)
        self.assertEqual(decision["reason"], "paid_call_cap")
        self.bind_checkpoint(paused)
        self.ledger.decide_expansion(self.env["attempt_id"], decision["expansion"]["request_id"], approve=True,
                                     expected_generation=1, actor="andy", explanation="one more")
        self.spend(M)  # the lineage spends past the cap meanwhile
        self.activate_recovery()
        with self.assertRaisesRegex(ContractError, "still denied: token_cap"):
            self.ledger.regrant_expanded_action(self.env, paused, generation=1)
        self.assertEqual(self.ledger.snapshot(self.env["attempt_id"])["actions"][-1]["status"], "denied")

    def test_a_recovered_manager_reissue_checks_every_limit_and_excludes_its_own_row(self):
        self.start(budget(manager="claude", max_manager_calls=1))
        request = manager_request(self.env, 1)
        self.assertTrue(self.ledger.decide_manager_call(self.env, request, generation=1)["allowed"])
        self.activate_recovery()
        # Its own allowed row is excluded: one call against a cap of one is fine.
        rotated = self.ledger.reissue_recovered_manager_grant(request["call_id"], generation=1)
        self.assertTrue(rotated["allowed"], rotated)
        self.spend_producer(M)
        denied = self.ledger.reissue_recovered_manager_grant(request["call_id"], generation=1)
        self.assertEqual((denied["allowed"], denied["reason"]), (False, "token_cap"))
        [call] = self.ledger.snapshot(self.env["attempt_id"])["manager_calls"]
        self.assertEqual((call["status"], call["grant_id"]), ("denied", None))
        with sqlite3.connect(self.ledger.path) as db:
            ops = [json.loads(detail)["op"] for (detail,) in db.execute(
                "SELECT detail FROM events WHERE event='grant_changed' AND action_id=? ORDER BY seq", (request["call_id"],))]
        self.assertEqual(ops, ["issue", "rotate", "deny"])

    def test_a_recovered_manager_reissue_enforces_the_round_cap(self):
        self.start(budget(manager="claude", max_manager_rounds=1))
        request = manager_request(self.env, 1, manager_round=1)
        self.assertTrue(self.ledger.decide_manager_call(self.env, request, generation=1)["allowed"])
        self.set_row("manager_calls", "call_id", request["call_id"],
                     request_json=json.dumps({**request, "manager_round": 2}, sort_keys=True, separators=(",", ":")))
        self.activate_recovery()
        denied = self.ledger.reissue_recovered_manager_grant(request["call_id"], generation=1)
        self.assertEqual(denied["reason"], "manager_round_cap")


class LineageGateTests(GateFixture):
    def test_a_successor_gate_counts_its_predecessors_charges(self):
        first = self.start(budget(attempt="first"))
        unknown = self.producer()
        grant = self.ledger.decide(first, unknown, generation=1)
        self.ledger.consume_grant(unknown["action_id"], grant["grant_id"], generation=1)
        self.ledger.mark_unknown(unknown["action_id"], "lost", generation=1)
        with sqlite3.connect(self.ledger.path) as db:
            db.execute("UPDATE attempts SET status='abandoned',sealed_receipt_sha256=? WHERE attempt_id=?",
                       ("f" * 64, "first"))
        second = budget(attempt="second")
        second["work_id"] = first["work_id"]
        second["predecessors"] = [{"attempt_id": "first", "terminal_status": "abandoned", "receipt_sha256": "f" * 64,
                                   "lead_generation": 1}]
        self.start(second)
        self.assertEqual(self.charged(), {"predecessor_charged": U, "own": 0, "total": U})


if __name__ == "__main__":
    unittest.main()


import tests.test_expansion_recovery as expansion_recovery  # noqa: E402  (module import: its tests are not re-collected)
from tests.manager_stub import manager_reply  # noqa: E402


class TokenEscalationRecoveryTests(expansion_recovery.ExpansionRecoveryFixture):
    """AC12 end to end: the second hit pauses, nothing is sent until the decision, answer mode resumes."""

    limits = {"max_concurrent": 1, "max_paid_worker_calls": 1, "max_manager_calls": 6,
              "max_lineage_tokens": 10_000, "token_tranche": 5_000, "unobserved_send_tokens": 2_000}
    manager_message = expansion_recovery.ManagerExpansionRecoveryTests.manager_message
    run_manager = expansion_recovery.ManagerExpansionRecoveryTests.run_manager

    def test_a_token_pause_resumes_in_answer_mode_and_sends_the_call_once(self):
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
            return manager_reply(message, f"Fixture facts {message['sequence']}",
                                 usage={"input_tokens": 8_000, "output_tokens": 0})

        def worker(action, *, envelope, workspace):
            worker_sends.append(action["assignment_id"])
            (workspace / "target.py").write_text("new\n")
            return self._result("codex", "editor-model", "Edited target")  # no usage: the sealed 2,000

        paused = self.execute(supervisor, worker=worker, manager=manager)
        self.assertEqual(paused["status"], "expansion_paused", paused)
        self.assertEqual(sends, [1], "the call over the cap is never sent before the decision")
        snapshot = self.ledger().snapshot(paused["attempt_id"])
        denied = snapshot["manager_calls"][-1]
        self.assertEqual((denied["status"], denied["reason"]), ("denied", "token_cap"))
        [request] = self.ledger().expansion_state(paused["attempt_id"])["requests"]
        self.assertEqual((request["limits"], request["status"]), (["tokens"], "pending"))
        self.decide(paused["attempt_id"], paused["request_id"], approve=True)
        events = self.ledger().snapshot(paused["attempt_id"])["events"]
        requested = next(e["seq"] for e in events if e["event"] == "expansion_requested")
        decided = next(e["seq"] for e in events if e["event"] == "expansion_decided")
        self.assertFalse([e for e in events if requested < e["seq"] < decided
                          and e["event"] in {"manager_send_started", "worker_dispatched", "verifier_send_claimed"}])

        def resumed(envelope, task, on_manager, on_action, **kwargs):
            self.run_manager(envelope, on_manager, (2,))
            return {"attempt_id": envelope["attempt_id"]}

        result = self.recover(paused["attempt_id"], resumed, worker=worker, manager=manager)
        self.assertEqual(result["mode"], "answer")
        self.assertEqual(sends, [1, 2], "the paused call is sent exactly once, after the decision")
        self.assertEqual(worker_sends, ["editor"])
        [request] = self.ledger().expansion_state(paused["attempt_id"])["requests"]
        self.assertEqual(request["grant"]["status"], "consumed")
