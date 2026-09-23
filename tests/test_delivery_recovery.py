"""Table tests for the pure v8 recovery eligibility and evidence rules."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

from delivery_recovery import (RecoveryRefused, build_recovery_block, rebuild_chartered_evidence_plan,  # noqa: E402
                               recovery_eligibility, restore_position)

ENVELOPE = {"attempt_id": "attempt", "job_contract": {"producer_instance_ids": ["editor"],
                                                      "verifier_instance_ids": ["verifier"]},
            "limits": {"max_replans": 2}}


def _action(sequence, status, *, instance="editor", reason="allowed"):
    return {"action_id": f"a{sequence}", "status": status, "reason": reason,
            "request": {"sequence": sequence, "instance_id": instance}}


def _link(sequence):
    return {"pending_kind": "worker", "pending_id": f"a{sequence}", "checkpoint_id": f"c{sequence}", "ledger_seq": 3}


def _snapshot(*, protocol=8, status="started", actions=(), manager_calls=(), links=(), events=(), inputs=()):
    return {"attempt_id": "attempt", "execution_protocol_version": protocol, "status": status,
            "actions": list(actions), "manager_calls": list(manager_calls), "magentic_checkpoints": list(links),
            "events": list(events), "verifier_inputs": list(inputs), "replans": []}


def _dispatched(sequence):
    return {"seq": 9, "action_id": f"a{sequence}", "event": "worker_dispatched", "detail": ""}


class RecoveryEligibilityTests(unittest.TestCase):
    def test_eligibility_table(self):
        completed_manager = {"call_id": "m1", "status": "completed"}
        cases = {
            "v6 is inspection only": (_snapshot(protocol=6), False, "v6_inspection_only", None),
            "v7 is not recoverable": (_snapshot(protocol=7), False, "v7_not_recoverable", None),
            "terminal attempt": (_snapshot(status="completed"), False, "attempt_terminal", None),
            "U0 nothing recorded": (_snapshot(), False, "no_restorable_checkpoint", None),
            "U1 completed manager calls only": (_snapshot(manager_calls=[completed_manager]), False,
                                                "no_restorable_checkpoint", None),
            "U2 unconsumed manager grant only": (_snapshot(manager_calls=[{"call_id": "m1", "status": "allowed"}]),
                                                 False, "no_restorable_checkpoint", None),
            "U3 manager call sent without response": (_snapshot(manager_calls=[{"call_id": "m1", "status": "started"}]),
                                                      False, "reconciliation_required", None),
            "U4 first action allowed but unbound": (_snapshot(actions=[_action(1, "allowed")]), False,
                                                    "no_restorable_checkpoint", None),
            "U5 later action allowed but unbound": (_snapshot(actions=[_action(1, "completed"), _action(2, "allowed")],
                                                              links=[_link(1)]), False, "no_restorable_checkpoint", None),
            "unknown action": (_snapshot(actions=[_action(1, "unknown")], links=[_link(1)]), False,
                               "reconciliation_required", None),
            "failed action at the checkpoint": (_snapshot(actions=[_action(1, "failed")], links=[_link(1)]), False,
                                                "checkpoint_position_unrecoverable", None),
            "allowed but dispatch recorded": (_snapshot(actions=[_action(1, "allowed")], links=[_link(1)],
                                                        events=[_dispatched(1)]), False,
                                              "checkpoint_position_unrecoverable", None),
            "completed latest action": (_snapshot(actions=[_action(1, "completed")], links=[_link(1)]), True, None, "answer"),
            "unconsumed bound grant": (_snapshot(actions=[_action(1, "allowed")], links=[_link(1)]), True, None, "pending"),
            "grant released by an earlier recovery": (_snapshot(actions=[_action(1, "not_dispatched", reason="recovery_unconsumed_grant")],
                                                                links=[_link(1)]), True, None, "pending"),
            "runtime outcome recorded": (_snapshot(actions=[_action(1, "completed")], links=[_link(1)],
                                                   events=[{"seq": 5, "action_id": None, "event": "runtime_outcome_recorded",
                                                            "detail": '{"failure":"","generation":1,"transport":false}'}]),
                                         True, None, "seal"),
        }
        for label, (snapshot, recoverable, reason, mode) in cases.items():
            with self.subTest(label=label):
                result = recovery_eligibility(ENVELOPE, snapshot, lead_active=True)
                self.assertEqual((result["recoverable"], result["reason"], result["mode"]), (recoverable, reason, mode))
                if reason in {"reconciliation_required", "no_restorable_checkpoint", "checkpoint_position_unrecoverable"}:
                    self.assertTrue(result["blockers"])
                    self.assertTrue(all(item["evidence_needed"] for item in result["blockers"]))

    def test_inactive_lead_refuses_before_any_position_check(self):
        result = recovery_eligibility(ENVELOPE, _snapshot(actions=[_action(1, "completed")], links=[_link(1)]),
                                      lead_active=False)
        self.assertEqual((result["recoverable"], result["reason"]), (False, "lead_generation_inactive"))
        self.assertEqual(result["blockers"][0]["evidence_needed"], "none; attempt fenced")

    def test_answer_mode_names_the_bound_checkpoint(self):
        result = recovery_eligibility(ENVELOPE, _snapshot(actions=[_action(1, "completed"), _action(2, "completed", instance="verifier")],
                                                          links=[_link(1), _link(2)]), lead_active=True)
        self.assertEqual((result["action_id"], result["checkpoint"]["checkpoint_id"]), ("a2", "c2"))


class EvidencePlanTests(unittest.TestCase):
    def test_reuses_the_single_bound_test_digest(self):
        inputs = [{"diff_digest": "d" * 64, "test_digest": "t" * 64}, {"diff_digest": "d" * 64, "test_digest": "t" * 64}]
        plan = rebuild_chartered_evidence_plan(ENVELOPE, _snapshot(actions=[_action(1, "completed")], inputs=inputs))
        self.assertEqual(plan, {"producer_completed": True, "diff_digest": "d" * 64, "test_digest": "t" * 64})

    def test_captures_once_when_no_input_is_bound(self):
        plan = rebuild_chartered_evidence_plan(ENVELOPE, _snapshot(actions=[_action(1, "completed")]))
        self.assertEqual(plan, {"producer_completed": True, "diff_digest": None, "test_digest": None})
        self.assertFalse(rebuild_chartered_evidence_plan(ENVELOPE, _snapshot(actions=[_action(1, "allowed")]))["producer_completed"])

    def test_conflicting_bindings_refuse(self):
        inputs = [{"diff_digest": "d" * 64, "test_digest": "t" * 64}, {"diff_digest": "d" * 64, "test_digest": "u" * 64}]
        with self.assertRaises(RecoveryRefused) as raised:
            rebuild_chartered_evidence_plan(ENVELOPE, _snapshot(actions=[_action(1, "completed")], inputs=inputs))
        self.assertEqual(raised.exception.reason, "evidence_binding_conflict")
        self.assertTrue(str(raised.exception).startswith("evidence_binding_conflict"))


class RecoveryBlockTests(unittest.TestCase):
    def test_block_projects_ledger_records_and_relied_resolutions(self):
        snapshot = _snapshot(actions=[_action(1, "completed", reason="operator_resolved_completed")])
        snapshot["interruptions"] = [{"interruption_id": "i", "cause": "transport", "detail": "x",
                                      "owner_generation": 1, "ledger_seq": 3, "recorded_at": "t"}]
        snapshot["recoveries"] = [{"recovery_id": "r", "expected_generation": 1, "generation": 2, "lead_generation": 1,
                                   "actor": "op", "mode": "answer", "checkpoint": None, "interruption_ids": ["i"],
                                   "released_action_ids": [], "quarantined": [], "claimed_at": "t"}]
        snapshot["resolutions"] = [{"resolution_id": "res", "action_id": "a1"}]
        block = build_recovery_block(snapshot, replaced_draft_sha256=None)
        self.assertEqual(block["interruptions"], [{"interruption_id": "i", "cause": "transport",
                                                   "owner_generation": 1, "recorded_at": "t"}])
        self.assertEqual(set(block["recoveries"][0]), {"recovery_id", "expected_generation", "generation", "lead_generation",
                                                       "actor", "mode", "released_action_ids", "claimed_at"})
        self.assertEqual(block["resolutions"], ["res"])

    def test_restore_position_counts_only_commitments_before_the_checkpoint(self):
        snapshot = _snapshot(manager_calls=[{"call_id": "m1", "status": "completed"}, {"call_id": "m2", "status": "completed"}],
                             events=[{"seq": 2, "action_id": "m1", "event": "manager_response_observed", "detail": ""},
                                     {"seq": 7, "action_id": "m2", "event": "manager_response_observed", "detail": ""}])
        self.assertEqual(restore_position(ENVELOPE, snapshot, 3), {"manager_calls_committed": 1, "replans_committed": 0})


if __name__ == "__main__":
    unittest.main()
