"""Ledger expansion requests and automatic grants under sealed headroom (ADR 0017)."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "cli"))
sys.path.insert(0, str(REPO_ROOT / "tests"))
from execution_contracts import digest, envelope_digest, expected_manager_call_id, expected_replan_id  # noqa: E402
from execution_ledger import ExecutionLedger  # noqa: E402
from verifier_contracts import evaluate_candidate  # noqa: E402
from tests.test_chartered_execution_contract import chartered, structured_verifier  # noqa: E402
from tests.test_structured_verifier_ledger import _action, _result  # noqa: E402

FAIL = '{"schema_version":1,"decision":"fail","summary":"repair","findings":[{"severity":"blocking","summary":"bad","evidence":"test"}]}'
PASS = '{"schema_version":1,"decision":"pass","summary":"ok","findings":[]}'


def v8(limits=None, headroom=None, *, manager="ollama", attempt="expansion-attempt"):
    env = structured_verifier()
    env["attempt_id"] = attempt
    env["work_id"] = f"work-{attempt}"
    env["manager"]["provider"] = manager
    if manager == "claude":
        env["manager"]["model"] = "sonnet"
    env["limits"].update({"max_delegations": 1, "max_paid_worker_calls": 1, **(limits or {})})
    if headroom:
        env["expansion_headroom"] = headroom
    return env


def manager_request(env, sequence, *, manager_round=1, phase="facts", replan_sequence=None):
    request = {"schema_version": 1, "attempt_id": env["attempt_id"], "envelope_digest": envelope_digest(env),
               "sequence": sequence, "phase": phase, "manager_round": manager_round,
               "prompt_digest": digest({"messages": [f"prompt {sequence}"]})}
    if replan_sequence is not None:
        request["replan_sequence"] = replan_sequence
        request["replan_id"] = expected_replan_id(env, replan_sequence)
    request["call_id"] = expected_manager_call_id(request)
    return request


class ExpansionLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.ledger = ExecutionLedger(Path(self.temporary.name) / "ledger.sqlite")

    def start(self, env):
        self.ledger.create_attempt(env)
        return env

    def producer(self, env, sequence):
        return _action(env, sequence, env["roster"][1], f"Produce change {sequence}.")

    def verifier(self, env, sequence):
        return _action(env, sequence, env["roster"][0], f"Verify change {sequence}.")

    def rows(self, table):
        with sqlite3.connect(self.ledger.path) as db:
            return db.execute(f"SELECT * FROM {table}").fetchall()

    def verify_once(self, env, proposal, candidate):
        grant = self.ledger.decide(env, proposal, generation=1)
        self.assertTrue(grant["allowed"], grant)
        diff, tests = "d" * 64, "e" * 64
        binding = self.ledger.bind_verifier_input(proposal["action_id"], {"task": "verify", "candidate": candidate}, diff, tests, generation=1)
        self.assertTrue(self.ledger.consume_grant(proposal["action_id"], grant["grant_id"], generation=1))
        self.ledger.claim_verifier_send(proposal["action_id"], generation=1)
        result = _result(proposal, candidate)
        self.ledger.observe_response(proposal["action_id"], result, generation=1)
        self.ledger.complete(proposal["action_id"], result, generation=1)
        evaluation = evaluate_candidate(action_id=proposal["action_id"], verifier_input_digest=binding["input_digest"],
                                        raw_output=candidate, diff_digest=diff, test_evidence_digest=tests)
        self.ledger.record_verifier_evaluation(proposal["action_id"], evaluation, generation=1)

    # AC4
    def test_request_within_headroom_is_granted_inline_and_draws_headroom(self):
        env = self.start(v8(headroom={"delegations": 1}))
        self.assertTrue(self.ledger.decide(env, self.producer(env, 1), generation=1)["allowed"])
        decision = self.ledger.decide(env, self.verifier(env, 2), generation=1)
        self.assertTrue(decision["allowed"])
        self.assertIsNotNone(decision["grant_id"])
        self.assertEqual(decision["reason"], "expansion_granted")
        self.assertEqual(decision["expansion"]["status"], "granted")
        state = self.ledger.expansion_state(env["attempt_id"])
        self.assertEqual(state["effective_limits"]["delegations"], 2)
        self.assertEqual(state["headroom_remaining"]["delegations"], 0)
        [request] = state["requests"]
        self.assertEqual((request["kind"], request["denied_row_id"], request["amount"], request["limits"]),
                         ("delegate", decision["action_id"], 1, ["delegations"]))
        self.assertEqual((request["grant"]["authority"], request["grant"]["status"], request["grant"]["consumed_by"]),
                         ("charter_headroom", "consumed", decision["action_id"]))

    # AC4, and the M1 oracle (T3): exhaustion must escalate, not fail some other way.
    def test_exhausted_headroom_escalates_to_a_pending_request(self):
        env = self.start(v8(headroom={"delegations": 1}))
        self.ledger.decide(env, self.producer(env, 1), generation=1)
        self.ledger.decide(env, self.verifier(env, 2), generation=1)
        proposal = self.producer(env, 3)
        decision = self.ledger.decide(env, proposal, generation=1)
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["reason"], "paid_call_cap")
        self.assertEqual(decision["expansion"]["status"], "pending")
        self.assertEqual(decision["expansion"]["limits"], ["delegations", "paid_worker_calls"])
        state = self.ledger.expansion_state(env["attempt_id"])
        self.assertLess(state["effective_limits"]["delegations"], 6, "the ceiling must not be what refused it")
        self.assertEqual([item["status"] for item in state["requests"]], ["granted", "pending"])
        self.assertIsNone(state["requests"][1]["grant"])

    # AC2
    def test_each_expandable_limit_records_one_unit_request_keyed_on_the_denied_row(self):
        cases = {}
        env = self.start(v8(attempt="delegation"))
        self.ledger.decide(env, self.producer(env, 1), generation=1)
        cases["delegation_cap"] = (env, self.verifier(env, 2), ["delegations"])
        env = self.start(v8({"max_delegations": 2}, attempt="paid"))
        self.ledger.decide(env, self.producer(env, 1), generation=1)
        cases["paid_call_cap"] = (env, self.producer(env, 2), ["paid_worker_calls"])
        env = self.start(v8({"max_delegations": 3, "max_verifier_calls": 1}, attempt="verifier"))
        self.verify_once(env, self.verifier(env, 1), FAIL)
        cases["verifier_call_cap"] = (env, self.verifier(env, 2), ["verifier_calls"])
        for reason, (env, proposal, limits) in cases.items():
            with self.subTest(reason):
                decision = self.ledger.decide(env, proposal, generation=1)
                self.assertEqual((decision["allowed"], decision["reason"]), (False, reason))
                self.assertEqual(decision["expansion"]["limits"], limits)
                [request] = self.ledger.expansion_state(env["attempt_id"])["requests"]
                self.assertEqual((request["denied_row_id"], request["amount"], request["status"]),
                                 (proposal["action_id"], 1, "pending"))
                self.assertEqual(request["rationale"], proposal["rationale"])

    def test_manager_call_and_round_caps_record_requests_and_grant_within_headroom(self):
        env = self.start(v8({"max_manager_calls": 2}, {"manager_calls": 1}, manager="claude"))
        for sequence in (1, 2):
            self.assertTrue(self.ledger.decide_manager_call(env, manager_request(env, sequence), generation=1)["allowed"])
        granted = self.ledger.decide_manager_call(env, manager_request(env, 3), generation=1)
        self.assertEqual((granted["allowed"], granted["reason"], granted["expansion"]["status"]),
                         (True, "expansion_granted", "granted"))
        pending = self.ledger.decide_manager_call(env, manager_request(env, 4), generation=1)
        self.assertEqual((pending["allowed"], pending["reason"], pending["expansion"]["status"]),
                         (False, "manager_call_cap", "pending"))
        rounds = self.start(v8({"max_manager_rounds": 1}, {"manager_rounds": 1}, attempt="rounds"))
        self.assertTrue(self.ledger.decide_manager_call(rounds, manager_request(rounds, 1), generation=1)["allowed"])
        granted = self.ledger.decide_manager_call(rounds, manager_request(rounds, 2, manager_round=2, phase="progress"), generation=1)
        self.assertEqual((granted["reason"], granted["expansion"]["limits"]), ("expansion_granted", ["manager_rounds"]))
        pending = self.ledger.decide_manager_call(rounds, manager_request(rounds, 3, manager_round=3, phase="progress"), generation=1)
        self.assertEqual((pending["reason"], pending["expansion"]["status"]), ("manager_round_cap", "pending"))

    # AC3, including a cap that fails alongside a hard predicate (A3).
    def test_hard_denials_never_create_requests_even_when_a_cap_also_fails(self):
        env = self.start(v8({"max_delegations": 3, "max_verifier_calls": 1}, {"verifier_calls": 1}, attempt="retry"))
        self.verify_once(env, self.verifier(env, 1), PASS)
        retry = self.ledger.decide(env, self.verifier(env, 2), generation=1)
        self.assertEqual((retry["allowed"], retry["reason"]), (False, "verifier_call_cap"))
        self.assertNotIn("expansion", retry)

        env = self.start(v8({"max_concurrent": 1}, {"delegations": 1}, attempt="concurrency"))
        self.ledger.decide(env, self.producer(env, 1), generation=1)
        masked = self.ledger.decide(env, self.verifier(env, 2), generation=1)
        self.assertEqual((masked["allowed"], masked["reason"]), (False, "delegation_cap"))
        self.assertNotIn("expansion", masked)

        env = self.start(v8({"max_manager_calls": 1}, {"manager_calls": 1}, manager="claude", attempt="replan"))
        self.ledger.decide_manager_call(env, manager_request(env, 1), generation=1)
        replan = self.ledger.decide_manager_call(env, manager_request(env, 2, phase="replan_facts", replan_sequence=1), generation=1)
        self.assertFalse(replan["allowed"])
        self.assertNotIn("expansion", replan)

        env = self.start(v8({"max_delegations": 3}, attempt="producer"))
        first = self.producer(env, 1)
        grant = self.ledger.decide(env, first, generation=1)
        self.ledger.consume_grant(first["action_id"], grant["grant_id"], generation=1)
        done = {**_result(first, "done"), "evidence_level": "flow_observed_claude_cli_completed_turn", "session_id": "claude-session-1"}
        self.ledger.observe_response(first["action_id"], done, generation=1)
        self.ledger.complete(first["action_id"], done, generation=1)
        again = self.ledger.decide(env, self.producer(env, 2), generation=1)
        self.assertEqual(again["reason"], "producer_already_completed")
        self.assertNotIn("expansion", again)
        self.assertEqual(self.rows("expansion_requests"), [])

    # AC4
    def test_replaying_a_recorded_row_returns_the_same_request_and_decision(self):
        env = self.start(v8(headroom={"delegations": 1}))
        self.ledger.decide(env, self.producer(env, 1), generation=1)
        proposal = self.verifier(env, 2)
        first = self.ledger.decide(env, proposal, generation=1)
        replay = self.ledger.decide(env, proposal, generation=1)
        self.assertTrue(replay["replayed"])
        self.assertEqual((replay["allowed"], replay["grant_id"], replay["expansion"]), (True, first["grant_id"], first["expansion"]))
        pending = self.producer(env, 3)
        self.assertEqual(self.ledger.decide(env, pending, generation=1)["expansion"],
                         self.ledger.decide(env, pending, generation=1)["expansion"])
        self.assertEqual(len(self.rows("expansion_requests")), 2)
        self.assertEqual(len(self.rows("expansion_grants")), 1)

    # AC4 crash window (T2): request and grant commit together or not at all.
    def test_a_crash_before_commit_leaves_nothing_and_a_rerun_draws_headroom_once(self):
        env = self.start(v8(headroom={"delegations": 1}))
        self.ledger.decide(env, self.producer(env, 1), generation=1)
        proposal = self.verifier(env, 2)
        original = ExecutionLedger._event

        def crash(db, attempt_id, action_id, event, detail):
            if event == "expansion_granted":
                raise OSError("injected crash before commit")
            return original(db, attempt_id, action_id, event, detail)

        with mock.patch.object(ExecutionLedger, "_event", staticmethod(crash)), self.assertRaises(OSError):
            self.ledger.decide(env, proposal, generation=1)
        self.assertEqual((self.rows("expansion_requests"), self.rows("expansion_grants")), ([], []))
        self.assertTrue(self.ledger.decide(env, proposal, generation=1)["allowed"])
        self.assertTrue(self.ledger.decide(env, proposal, generation=1)["replayed"])
        self.assertEqual(len(self.rows("expansion_grants")), 1)
        self.assertEqual(self.ledger.expansion_state(env["attempt_id"])["headroom_remaining"]["delegations"], 0)

    # AC8 (E6 a): lineage counters inherit grants; per-attempt counters do not; headroom never refills.
    def test_successor_inherits_lineage_grants_and_remaining_headroom_only(self):
        env = self.start(v8({"max_delegations": 1}, {"delegations": 1, "paid_worker_calls": 1}))
        self.ledger.decide(env, self.producer(env, 1), generation=1)
        both = self.ledger.decide(env, self.producer(env, 2), generation=1)
        self.assertEqual(both["expansion"]["limits"], ["delegations", "paid_worker_calls"])
        self.assertTrue(both["allowed"])
        self.ledger.seal_superseded_attempts(env["work_id"], lead_generation=1, successor_generation=2,
                                             action="supersede", expected=[env["attempt_id"]])
        successor = v8({"max_delegations": 1}, {"delegations": 1, "paid_worker_calls": 1}, attempt="successor")
        successor["work_id"] = env["work_id"]
        successor["delivery_lead_claim"] = {**successor["delivery_lead_claim"], "generation": 2}
        successor["predecessors"] = self.ledger.v8_lineage(env["work_id"])[0]
        self.start(successor)
        state = self.ledger.expansion_state("successor")
        self.assertEqual(state["effective_limits"]["paid_worker_calls"], 2)
        self.assertEqual(state["effective_limits"]["delegations"], 1)
        self.assertEqual(state["headroom_remaining"], {"delegations": 0, "paid_worker_calls": 0, "verifier_calls": 0,
                                                       "manager_calls": 0, "manager_rounds": 0})

    # AC11 (T5): earlier protocols keep their legacy denial shape and never record requests.
    def test_protocols_before_v8_keep_terminal_denials(self):
        from test_magentic_execution_contract import action
        v6 = chartered()
        self.start(v6)
        self.ledger.decide(v6, action(v6, 1, v6["roster"][1]), generation=1)
        paid = self.ledger.decide(v6, action(v6, 2, v6["roster"][1], task="Again."), generation=1)
        self.assertEqual(paid, {"allowed": False, "reason": "paid_call_cap", "action_id": paid["action_id"], "grant_id": None})
        for reason, limits, second in (("delegation_cap", {"max_delegations": 1}, 0), ("paid_call_cap", {"max_delegations": 2}, 1)):
            with self.subTest(protocol=7, reason=reason):
                v7 = structured_verifier()
                v7["execution_protocol_version"] = 7
                del v7["limits"]["max_verifier_calls"]
                v7.update(attempt_id=f"v7-{reason}", work_id=f"v7-{reason}")
                v7["limits"].update(limits)
                self.start(v7)
                self.ledger.decide(v7, _action(v7, 1, v7["roster"][1], "First."), generation=1)
                denied = self.ledger.decide(v7, _action(v7, 2, v7["roster"][second], "Again."), generation=1)
                self.assertEqual(denied, {"allowed": False, "reason": reason, "action_id": denied["action_id"], "grant_id": None})
        self.assertEqual(self.rows("expansion_requests"), [])

if __name__ == "__main__":
    unittest.main()
