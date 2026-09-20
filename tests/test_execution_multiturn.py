"""Deterministic Gate-1 tests for Flow-owned multi-turn execution authority."""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "cli"))
sys.path.insert(0, str(REPO / "tests"))

from execution_contracts import (  # noqa: E402
    ContractError,
    envelope_digest,
    expected_action_id,
    expected_replan_id,
    validate_receipt,
)
from execution_ledger import ExecutionLedger  # noqa: E402
from test_execution import ExecutionFixture, stub_result  # noqa: E402


def action_for(envelope: dict, sequence: int) -> dict:
    return {
        "schema_version": 1,
        "action_id": expected_action_id(envelope, sequence),
        "attempt_id": envelope["attempt_id"],
        "envelope_digest": envelope_digest(envelope),
        "role": envelope["role"], "instance_id": envelope["instance_id"],
        "provider": envelope["provider"], "model": envelope["model"],
        "task_digest": envelope["task_digest"], "sequence": sequence, "kind": "delegate",
    }


def replan_for(envelope: dict, sequence: int, proposal: dict | None = None) -> dict:
    return {
        "schema_version": 1,
        "replan_id": expected_replan_id(envelope, sequence),
        "attempt_id": envelope["attempt_id"], "envelope_digest": envelope_digest(envelope),
        "role": envelope["role"], "instance_id": envelope["instance_id"],
        "provider": envelope["provider"], "model": envelope["model"],
        "task_digest": envelope["task_digest"], "sequence": sequence, "kind": "replan",
        "proposal": proposal or {"reason": f"bounded adjustment {sequence}"},
    }


def maf_checkpoint(checkpoint_id: str, request_id: str, *, workflow: str = "flow-maf-v2-initial") -> str:
    return json.dumps({
        "workflow_name": workflow, "checkpoint_id": checkpoint_id,
        "pending_request_info_events": {request_id: {"__type__": "opaque"}},
    })


class MultiTurnLedgerTests(ExecutionFixture):
    def v2_attempt(self):
        base, _, ledger = self.prepare()
        envelope = {**base, "attempt_id": "v2" + base["attempt_id"][2:], "execution_protocol_version": 2}
        ledger.create_attempt(envelope)
        return envelope, ledger

    def test_v2_action_slots_are_ordered_stable_and_replay_after_reopen(self) -> None:
        envelope, ledger = self.v2_attempt()
        first = action_for(envelope, 1)
        first_decision = ledger.decide(envelope, first, generation=1)
        self.assertTrue(first_decision["allowed"])
        self.assertTrue(ledger.consume_grant(first["action_id"], first_decision["grant_id"], generation=1))
        ledger.observe_send(first["action_id"], 1)
        first_result = stub_result(envelope, "first")
        ledger.observe_response(first["action_id"], first_result, 1)
        ledger.complete(first["action_id"], first_result, generation=1)
        reopened = ExecutionLedger(ledger.path)
        replay = reopened.decide(envelope, first, generation=1)
        self.assertFalse(replay["allowed"])
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["result"], first_result)
        with self.assertRaisesRegex(ContractError, "out of order"):
            reopened.decide(envelope, action_for(envelope, 3), generation=1)
        second = action_for(envelope, 2)
        second_decision = reopened.decide(envelope, second, generation=1)
        self.assertTrue(second_decision["allowed"])
        self.assertTrue(reopened.consume_grant(second["action_id"], second_decision["grant_id"], generation=1))
        reopened.observe_send(second["action_id"], 1)
        second_result = stub_result(envelope, "second")
        reopened.observe_response(second["action_id"], second_result, 1)
        reopened.complete(second["action_id"], second_result, generation=1)
        self.assertTrue(reopened.decide(envelope, action_for(envelope, 3), generation=1)["allowed"])
        snapshot = reopened.snapshot(envelope["attempt_id"])
        self.assertEqual([row["request"]["sequence"] for row in snapshot["actions"]], [1, 2, 3])
        self.assertEqual(snapshot["execution_protocol_version"], 2)

    def test_v2_action_changed_payload_and_fresh_id_are_rejected(self) -> None:
        envelope, ledger = self.v2_attempt()
        action = action_for(envelope, 1)
        ledger.decide(envelope, action, generation=1)
        changed = {**action, "proposal": {"different": True}}
        with self.assertRaisesRegex(ContractError, "changed payload"):
            ledger.decide(envelope, changed, generation=1)
        fresh = {**action, "action_id": "fresh-id"}
        with self.assertRaisesRegex(ContractError, "action ID mismatch"):
            ledger.decide(envelope, fresh, generation=1)
        self.assertEqual(len(ledger.snapshot(envelope["attempt_id"])["actions"]), 1)

    def test_replan_slots_persist_two_allows_and_a_cap_denial_without_work(self) -> None:
        envelope, ledger = self.v2_attempt()
        for sequence in (1, 2):
            decision = ledger.decide_replan(envelope, replan_for(envelope, sequence), generation=1)
            self.assertTrue(decision["allowed"])
            ledger = ExecutionLedger(ledger.path)
        third = replan_for(envelope, 3)
        denied = ledger.decide_replan(envelope, third, generation=1)
        self.assertEqual(denied, {"allowed": False, "reason": "replan_cap", "replan_id": third["replan_id"]})
        replay = ExecutionLedger(ledger.path).decide_replan(envelope, third, generation=1)
        self.assertFalse(replay["allowed"])
        self.assertTrue(replay["replayed"])
        snapshot = ledger.snapshot(envelope["attempt_id"])
        self.assertEqual([(r["sequence"], r["status"], r["reason"]) for r in snapshot["replans"]], [(1, "allowed", "allowed"), (2, "allowed", "allowed"), (3, "denied", "replan_cap")])
        self.assertEqual(snapshot["actions"], [])
        self.assertEqual([event for event in snapshot["events"] if event["event"] == "adapter_send_started"], [])

    def test_replan_identity_laundering_and_skipped_slots_are_rejected(self) -> None:
        envelope, ledger = self.v2_attempt()
        with self.assertRaisesRegex(ContractError, "out of order"):
            ledger.decide_replan(envelope, replan_for(envelope, 2), generation=1)
        first = replan_for(envelope, 1)
        ledger.decide_replan(envelope, first, generation=1)
        changed = copy.deepcopy(first)
        changed["proposal"] = {"reason": "changed"}
        with self.assertRaisesRegex(ContractError, "changed payload"):
            ledger.decide_replan(envelope, changed, generation=1)
        fresh = {**first, "replan_id": "fresh-id"}
        with self.assertRaisesRegex(ContractError, "replan ID mismatch"):
            ledger.decide_replan(envelope, fresh, generation=1)

    def test_unknown_action_blocks_actions_and_replans_before_any_new_row(self) -> None:
        envelope, ledger = self.v2_attempt()
        first = action_for(envelope, 1)
        decision = ledger.decide(envelope, first, generation=1)
        self.assertTrue(ledger.consume_grant(first["action_id"], decision["grant_id"], generation=1))
        self.assertEqual(ledger.decide(envelope, action_for(envelope, 2), generation=1)["reason"], "reconciliation_required")
        self.assertEqual(ledger.decide_replan(envelope, replan_for(envelope, 1), generation=1)["reason"], "reconciliation_required")
        ledger.mark_unknown(first["action_id"], "interrupted", generation=1)
        second = ledger.decide(envelope, action_for(envelope, 2), generation=1)
        replan = ledger.decide_replan(envelope, replan_for(envelope, 1), generation=1)
        self.assertEqual(second["reason"], "reconciliation_required")
        self.assertEqual(replan["reason"], "reconciliation_required")
        snapshot = ledger.snapshot(envelope["attempt_id"])
        self.assertEqual(len(snapshot["actions"]), 1)
        self.assertEqual(snapshot["replans"], [])

    def test_legacy_rows_remain_readable_and_cannot_continue_as_v2(self) -> None:
        base, _, _ = self.prepare()
        path = self.run_dir / "execution" / "legacy.sqlite"
        legacy = sqlite3.connect(path)
        legacy.executescript("""
            CREATE TABLE attempts (attempt_id TEXT PRIMARY KEY, work_id TEXT NOT NULL, envelope_json TEXT NOT NULL, status TEXT NOT NULL, reason TEXT NOT NULL, receipt_path TEXT);
            CREATE TABLE actions (action_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL, request_json TEXT NOT NULL, status TEXT NOT NULL, reason TEXT NOT NULL, grant_id TEXT UNIQUE, result_json TEXT);
            CREATE TABLE events (seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, attempt_id TEXT NOT NULL, action_id TEXT, event TEXT NOT NULL, detail TEXT NOT NULL);
        """)
        action = action_for(base, 1)
        legacy.execute("INSERT INTO attempts VALUES(?,?,?,?,?,?)", (base["attempt_id"], base["work_id"], json.dumps(base, sort_keys=True, separators=(",", ":")), "started", "", None))
        legacy.execute("INSERT INTO actions VALUES(?,?,?,?,?,?,?)", (action["action_id"], base["attempt_id"], json.dumps(action, sort_keys=True, separators=(",", ":")), "completed", "allowed", None, None))
        legacy.commit()
        legacy.close()
        migrated = ExecutionLedger(path)
        snapshot = migrated.snapshot(base["attempt_id"])
        self.assertEqual(snapshot["execution_protocol_version"], 1)
        self.assertEqual(snapshot["actions"][0]["status"], "completed")
        v2_claim = {**base, "execution_protocol_version": 2}
        with self.assertRaisesRegex(ContractError, "stale or not recovery-capable"):
            migrated.decide(v2_claim, action_for(v2_claim, 1), generation=1)

    def test_v2_checkpoint_position_is_bound_to_completed_action_and_readback_validates_bytes(self) -> None:
        envelope, ledger = self.v2_attempt()
        action = action_for(envelope, 1)
        decision = ledger.decide(envelope, action, generation=1)
        self.assertTrue(ledger.consume_grant(action["action_id"], decision["grant_id"], generation=1))
        ledger.observe_send(action["action_id"], 1)
        result = stub_result(envelope, "checkpointed")
        ledger.observe_response(action["action_id"], result, 1)
        ledger.complete(action["action_id"], result, generation=1)
        checkpoint_id = "position-1"
        checkpoint = Path(envelope["checkpoint_dir"]) / f"{checkpoint_id}.json"
        checkpoint.write_text(maf_checkpoint(checkpoint_id, "flow-replan-1"))
        high_water = ledger.snapshot(envelope["attempt_id"])["events"][-1]["seq"]
        link = ledger.bind_checkpoint_position(envelope["attempt_id"], "delegate", 1, checkpoint_id, envelope_digest(envelope), high_water, 1, "maf-test", str(checkpoint), generation=1)
        self.assertFalse(link["replayed"])
        replay = ledger.bind_checkpoint_position(envelope["attempt_id"], "delegate", 1, checkpoint_id, envelope_digest(envelope), high_water, 1, "maf-test", str(checkpoint), generation=1)
        self.assertTrue(replay["replayed"])
        loaded = ExecutionLedger(ledger.path).read_checkpoint_position(envelope["attempt_id"], "delegate", 1)
        self.assertIn(b"flow-replan-1", loaded["bytes"])
        checkpoint.write_bytes(b"changed\n")
        with self.assertRaisesRegex(ContractError, "digest or size changed"):
            ledger.read_checkpoint_position(envelope["attempt_id"], "delegate", 1)

    def test_pending_delegate_checkpoint_requires_matching_maf_json_before_send(self) -> None:
        envelope, ledger = self.v2_attempt()
        action = action_for(envelope, 1)
        decision = ledger.decide(envelope, action, generation=1)
        self.assertTrue(decision["allowed"])
        checkpoint_id = "pending-action-1"
        checkpoint = Path(envelope["checkpoint_dir"]) / f"{checkpoint_id}.json"
        checkpoint.write_text(maf_checkpoint(checkpoint_id, "flow-action-1"))
        high_water = ledger.snapshot(envelope["attempt_id"])["events"][-1]["seq"]
        link = ledger.bind_checkpoint_position(envelope["attempt_id"], "pending_delegate", 1, checkpoint_id,
                                               envelope_digest(envelope), high_water, 1, "maf-test",
                                               str(checkpoint), generation=1)
        self.assertEqual(link["kind"], "pending_delegate")
        loaded = ledger.read_checkpoint_position(envelope["attempt_id"], "pending_delegate", 1)
        self.assertIn(b"flow-action-1", loaded["bytes"])

        bad_action = action_for(envelope, 2)
        bad_decision = ledger.decide(envelope, bad_action, generation=1)
        self.assertTrue(bad_decision["allowed"])
        bad_id = "pending-action-2"
        bad = Path(envelope["checkpoint_dir"]) / f"{bad_id}.json"
        bad.write_text(maf_checkpoint(bad_id, "flow-action-2", workflow="foreign"))
        high_water = ledger.snapshot(envelope["attempt_id"])["events"][-1]["seq"]
        with self.assertRaisesRegex(ContractError, "workflow does not match"):
            ledger.bind_checkpoint_position(envelope["attempt_id"], "pending_delegate", 2, bad_id,
                                            envelope_digest(envelope), high_water, 1, "maf-test", str(bad), generation=1)

    def test_completed_delegate_checkpoint_rejects_wrong_pending_replan(self) -> None:
        envelope, ledger = self.v2_attempt()
        action = action_for(envelope, 1)
        decision = ledger.decide(envelope, action, generation=1)
        self.assertTrue(ledger.consume_grant(action["action_id"], decision["grant_id"], generation=1))
        ledger.observe_send(action["action_id"], 1)
        result = stub_result(envelope, "first")
        ledger.observe_response(action["action_id"], result, 1)
        ledger.complete(action["action_id"], result, generation=1)
        checkpoint_id = "wrong-next-request"
        checkpoint = Path(envelope["checkpoint_dir"]) / f"{checkpoint_id}.json"
        checkpoint.write_text(maf_checkpoint(checkpoint_id, "flow-action-2"))
        high_water = ledger.snapshot(envelope["attempt_id"])["events"][-1]["seq"]
        with self.assertRaisesRegex(ContractError, "request does not match"):
            ledger.bind_checkpoint_position(envelope["attempt_id"], "delegate", 1, checkpoint_id,
                                            envelope_digest(envelope), high_water, 1, "maf-test", str(checkpoint), generation=1)

    def test_v2_receipt_requires_linked_replans_and_checkpoint_positions(self) -> None:
        envelope, ledger = self.v2_attempt()
        action = action_for(envelope, 1)
        decision = ledger.decide(envelope, action, generation=1)
        self.assertTrue(ledger.consume_grant(action["action_id"], decision["grant_id"], generation=1))
        ledger.observe_send(action["action_id"], 1)
        result = stub_result(envelope, "receipt")
        ledger.observe_response(action["action_id"], result, 1)
        ledger.complete(action["action_id"], result, generation=1)
        checkpoint = Path(envelope["checkpoint_dir"]) / "receipt.json"
        checkpoint.write_text(maf_checkpoint("receipt-checkpoint", "flow-replan-1"))
        high_water = ledger.snapshot(envelope["attempt_id"])["events"][-1]["seq"]
        ledger.bind_checkpoint_position(envelope["attempt_id"], "delegate", 1, "receipt-checkpoint", envelope_digest(envelope), high_water, 1, "maf-test", str(checkpoint), generation=1)
        ledger.decide_replan(envelope, replan_for(envelope, 1), generation=1)
        snapshot = ledger.snapshot(envelope["attempt_id"])
        receipt = {"schema_version": 1, "work_id": envelope["work_id"], "attempt_id": envelope["attempt_id"],
                   "envelope_digest": envelope_digest(envelope), "charter_digest": envelope["charter_digest"],
                   "charter_sources": envelope["charter_sources"], "run_protocol_revision": envelope["run_protocol_revision"],
                   "manifest_digest": envelope["manifest_digest"], "definition_digest": envelope["definition_digest"],
                   "provider": envelope["provider"], "status": "completed", "actions": snapshot["actions"],
                   "execution_protocol_version": 2, "replans": snapshot["replans"], "checkpoints": snapshot["checkpoint_positions"]}
        validate_receipt(envelope, receipt)
        receipt["checkpoints"].append(dict(receipt["checkpoints"][0]))
        with self.assertRaisesRegex(ContractError, "position is duplicated"):
            validate_receipt(envelope, receipt)

    def test_v2_receipt_endpoint_evidence_is_optional_but_typed(self) -> None:
        envelope, _ = self.v2_attempt()
        receipt = {"schema_version": 1, "work_id": envelope["work_id"], "attempt_id": envelope["attempt_id"],
                   "envelope_digest": envelope_digest(envelope), "charter_digest": envelope["charter_digest"],
                   "charter_sources": envelope["charter_sources"], "run_protocol_revision": envelope["run_protocol_revision"],
                   "manifest_digest": envelope["manifest_digest"], "definition_digest": envelope["definition_digest"],
                   "provider": envelope["provider"], "status": "unknown", "actions": [],
                   "execution_protocol_version": 2, "replans": [], "checkpoints": [],
                   "endpoint_evidence": {"status": "unavailable", "actions": [{"action_id": "action-3", "flow_send_observed": True, "endpoint_arrivals": None}]}}
        validate_receipt(envelope, receipt)
        receipt["endpoint_evidence"]["actions"][0]["endpoint_arrivals"] = 0
        with self.assertRaisesRegex(ContractError, "cannot claim arrivals"):
            validate_receipt(envelope, receipt)


if __name__ == "__main__":
    unittest.main()
