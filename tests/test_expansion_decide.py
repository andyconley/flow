"""flow run decide-expansion: fenced, generation-checked engineer decisions (ADR 0017)."""

from __future__ import annotations

import json
import sqlite3
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

import delivery_gateway  # noqa: E402
from delivery_control import change_lead_claim  # noqa: E402
from delivery_recovery import RecoveryRefused  # noqa: E402
from tests.test_expansion_gateway import ExpansionGatewayFixture  # noqa: E402


class DecideExpansionTests(ExpansionGatewayFixture):
    def setUp(self):
        super().setUp()
        supervisor, worker = self.worker_plan([])
        self.paused = self.execute(supervisor, worker=worker)
        self.assertEqual(self.paused["status"], "expansion_paused")
        self.attempt, self.request = self.paused["attempt_id"], self.paused["request_id"]

    def decide(self, *, approve=True, generation=1, request=None, actor="andy", explanation="one more review"):
        with patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])):
            return delivery_gateway.decide_expansion("sample", self.attempt, request or self.request, approve=approve,
                                                     expected_generation=generation, actor=actor,
                                                     explanation=explanation, root=self.root)

    def ledger_view(self):
        ledger = self.ledger()
        return ledger.expansion_state(self.attempt), ledger.snapshot(self.attempt)["events"]

    def assertRefusedUnchanged(self, reason, **kwargs):
        before = self.ledger_view()
        with self.assertRaises(RecoveryRefused) as raised:
            self.decide(**kwargs)
        self.assertEqual(raised.exception.reason, reason)
        self.assertEqual(self.ledger_view(), before, "a refused decision changes nothing")

    # AC5
    def test_approve_records_an_engineer_grant_that_does_not_draw_headroom(self):
        before = self.ledger().expansion_state(self.attempt)
        result = self.decide()
        self.assertEqual((result["status"], result["request_id"]), ("granted", self.request))
        self.assertIn("recover-delivery-lead", result["next_action"])
        after = self.ledger().expansion_state(self.attempt)
        [request] = after["requests"]
        self.assertEqual(request["status"], "granted")
        self.assertEqual({key: request["grant"][key] for key in ("authority", "decision", "actor", "status", "consumed_by")},
                         {"authority": "engineer", "decision": "approve", "actor": "andy", "status": "available",
                          "consumed_by": None})
        self.assertEqual(after["headroom_remaining"], before["headroom_remaining"])
        self.assertEqual(after["effective_limits"], before["effective_limits"], "a grant counts only once consumed")

    def test_deny_records_the_decision(self):
        self.assertEqual(self.decide(approve=False)["status"], "denied")
        [request] = self.ledger().expansion_state(self.attempt)["requests"]
        self.assertEqual((request["status"], request["grant"]["decision"], request["grant"]["status"]),
                         ("denied", "deny", "denied"))

    # AC5 refusals, each with nothing changed (M3, M4).
    def test_stale_generation_is_refused(self):
        self.assertRefusedUnchanged("owner_generation_stale", generation=2)

    def test_unknown_and_already_decided_requests_are_refused(self):
        self.assertRefusedUnchanged("expansion_unknown_request", request="exp-" + "0" * 24)
        self.decide(approve=False)
        self.assertRefusedUnchanged("expansion_already_decided")
        self.assertRefusedUnchanged("expansion_already_decided", approve=False)

    def test_an_attempt_that_is_not_truly_paused_is_refused(self):
        with self.ledger().recovery_lock(self.attempt, holder="live"):
            self.assertRefusedUnchanged("attempt_not_paused")
        with sqlite3.connect(self.ledger().path) as db:
            db.execute("UPDATE actions SET status='unknown' WHERE attempt_id=? AND sequence=1", (self.attempt,))
        self.assertRefusedUnchanged("attempt_not_paused")

    def test_an_inactive_lead_claim_is_refused(self):
        changed, _, errors = change_lead_claim("sample", "attention", root=self.root)
        self.assertTrue(changed, errors)
        self.assertRefusedUnchanged("lead_generation_inactive")

    def test_a_grant_past_a_runner_ceiling_is_refused(self):
        # Another unconsumed engineer grant already holds the counter's last unit.
        with sqlite3.connect(self.ledger().path) as db:
            db.execute("INSERT INTO expansion_requests VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                       ("exp-other", self.attempt, self.attempt, 1, "delegate", "other-row", '["delegations"]', 1,
                        "0" * 64, "earlier", "granted", "2026-09-25T00:00:00+00:00"))
            for grant_id in ("expg-a", "expg-b", "expg-c", "expg-d"):
                db.execute("INSERT INTO expansion_grants VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (grant_id, "exp-other" if grant_id == "expg-a" else f"exp-{grant_id}", self.attempt, self.attempt,
                            "engineer", "approve", '["delegations"]', 1, "andy", "earlier", 1,
                            "2026-09-25T00:00:00+00:00", "available", None))
        self.assertRefusedUnchanged("expansion_ceiling_exceeded")

    # AC10: two concurrent decisions; exactly one wins.
    def test_two_concurrent_decisions_leave_exactly_one_winner(self):
        barrier = threading.Barrier(2)

        def race(approve):
            barrier.wait()
            try:
                return self.decide(approve=approve)["status"]
            except RecoveryRefused as exc:
                return exc.reason

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = sorted(pool.map(race, (True, False)))
        self.assertIn(outcomes, (["expansion_already_decided", "granted"], ["denied", "expansion_already_decided"]))
        [request] = self.ledger().expansion_state(self.attempt)["requests"]
        self.assertIn(request["status"], {"granted", "denied"})

    # AC8/AC10: supersede or release closes open expansions; a racing decide sees exactly one outcome.
    def test_supersede_after_approval_lapses_the_unused_grant(self):
        self.decide()
        changed, _, errors = change_lead_claim("sample", "supersede", root=self.root, owner="successor")
        self.assertTrue(changed, errors)
        [request] = self.ledger().expansion_state(self.attempt)["requests"]
        self.assertEqual((request["status"], request["grant"]["status"]), ("granted", "lapsed"))

    def test_supersede_before_a_decision_cancels_the_request_and_refuses_the_decide(self):
        changed, _, errors = change_lead_claim("sample", "supersede", root=self.root, owner="successor")
        self.assertTrue(changed, errors)
        [request] = self.ledger().expansion_state(self.attempt)["requests"]
        self.assertEqual(request["status"], "cancelled")
        with self.assertRaises(RecoveryRefused) as raised:
            self.decide()
        self.assertIn(raised.exception.reason, {"attempt_terminal", "lead_generation_inactive"})

    def test_release_cancels_a_pending_request(self):
        changed, _, errors = change_lead_claim("sample", "release", root=self.root)
        self.assertTrue(changed, errors)
        [request] = self.ledger().expansion_state(self.attempt)["requests"]
        self.assertEqual(request["status"], "cancelled")
        self.assertEqual(self.ledger().snapshot(self.attempt)["status"], "started", "release does not seal the attempt")

    def test_decide_racing_supersede_has_exactly_one_outcome(self):
        barrier = threading.Barrier(2)

        def decide():
            barrier.wait()
            try:
                return self.decide()["status"]
            except RecoveryRefused as exc:
                return exc.reason

        def supersede():
            barrier.wait()
            changed, _, errors = change_lead_claim("sample", "supersede", root=self.root, owner="successor")
            return "superseded" if changed else errors[0]

        with ThreadPoolExecutor(max_workers=2) as pool:
            decided, superseded = pool.submit(decide), pool.submit(supersede)
            decided, superseded = decided.result(), superseded.result()
        [request] = self.ledger().expansion_state(self.attempt)["requests"]
        status = self.ledger().snapshot(self.attempt)["status"]
        if superseded == "superseded":
            self.assertEqual(status, "superseded")
            self.assertTrue(request["status"] == "cancelled" or request["grant"]["status"] == "lapsed", request)
        else:
            self.assertEqual((decided, request["status"], status), ("granted", "granted", "started"))


if __name__ == "__main__":
    import unittest

    unittest.main()
