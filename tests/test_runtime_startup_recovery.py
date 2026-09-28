"""The startup-recovery command never replays a provider-visible failure."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
import io
import contextlib
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))
from delivery_gateway import ContractError, recover_runtime_startup
from execution_ledger import ExecutionLedger
import flow


class RuntimeStartupRecoveryTests(unittest.TestCase):
    def _snapshot(self, **changes):
        receipt = Path(self.tmp.name) / ".flow" / "runs" / "sample" / "execution" / "old" / "receipt.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        envelope = {"attempt_id": "old"}
        receipt.write_text(json.dumps({"attempt_id": "old", "envelope_digest": "b" * 64,
                                       "status": "failed", "reason": "MAF delivery child failed: missing agent_framework",
                                       "failure_class": "maf_runtime_startup"}) + "\n")
        value = {"work_id": "sample", "execution_protocol_version": 8, "status": "failed",
                 "reason": "MAF delivery child failed: missing agent_framework", "actions": [], "manager_calls": [],
                 "failure_class": "maf_runtime_startup",
                 "receipt_path": str(receipt), "sealed_receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
                 "envelope": envelope}
        value.update(changes)
        return value

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        path = Path(self.tmp.name) / ".flow" / "runs" / "sample" / "execution"
        path.mkdir(parents=True)
        (path / "ledger.sqlite").write_text("fixture")

    def test_only_a_sealed_zero_send_runtime_failure_can_start_successor(self):
        with patch("delivery_gateway.ExecutionLedger") as ledger, patch("delivery_gateway.envelope_digest", return_value="b" * 64), \
             patch("delivery_gateway.execute_chartered_delivery", return_value={"attempt_id": "next", "status": "completed"}) as execute:
            ledger.return_value.snapshot.return_value = self._snapshot()
            ledger.return_value.reconcile_runtime_startup_successor.return_value = None
            result = recover_runtime_startup("sample", "old", Path(self.tmp.name), "commit", root=Path(self.tmp.name))
        self.assertEqual(result["attempt_id"], "next")
        execute.assert_called_once()

    def test_any_send_refuses_without_creating_successor(self):
        with patch("delivery_gateway.ExecutionLedger") as ledger, patch("delivery_gateway.envelope_digest", return_value="b" * 64), \
             patch("delivery_gateway.execute_chartered_delivery") as execute:
            ledger.return_value.snapshot.return_value = self._snapshot(actions=[{"status": "unknown"}])
            ledger.return_value.reconcile_runtime_startup_successor.return_value = None
            with self.assertRaisesRegex(ContractError, "observed or uncertain"):
                recover_runtime_startup("sample", "old", Path(self.tmp.name), "commit", root=Path(self.tmp.name))
        execute.assert_not_called()

    def test_substring_runtime_reason_is_not_recovery_eligible(self):
        with patch("delivery_gateway.ExecutionLedger") as ledger, patch("delivery_gateway.execute_chartered_delivery") as execute:
            ledger.return_value.snapshot.return_value = self._snapshot(
                failure_class=None, reason="ordinary runtime validation failed")
            ledger.return_value.reconcile_runtime_startup_successor.return_value = None
            with self.assertRaisesRegex(ContractError, "not a MAF runtime-startup"):
                recover_runtime_startup("sample", "old", Path(self.tmp.name), "commit", root=Path(self.tmp.name))
        execute.assert_not_called()

    def test_reconcile_finds_predecessor_at_later_lineage_position_and_is_idempotent(self):
        path = Path(self.tmp.name) / "lineage.sqlite"
        ledger = ExecutionLedger(path)
        # Initialize a stranded claim, then emulate a crash after an envelope
        # with this predecessor in its second lineage position was persisted.
        with sqlite3.connect(path) as db:
            db.execute("INSERT INTO attempts(attempt_id,work_id,envelope_json,status,reason,execution_protocol_version) VALUES(?,?,?,?,?,?)",
                       ("old", "sample", json.dumps({"attempt_id": "old"}), "failed", "", 8))
        ledger.claim_runtime_startup_successor("old")
        with sqlite3.connect(path) as db:
            db.execute("INSERT INTO attempts(attempt_id,work_id,envelope_json,status,reason,execution_protocol_version) VALUES(?,?,?,?,?,?)",
                       ("next", "sample", json.dumps({"attempt_id": "next", "predecessors": [{"attempt_id": "earlier"}, {"attempt_id": "old"}]}), "started", "", 8))
        self.assertEqual(ledger.reconcile_runtime_startup_successor("old"), "next")
        self.assertEqual(ledger.reconcile_runtime_startup_successor("old"), "next")
        with self.assertRaisesRegex(ContractError, "already has a successor"):
            ledger.claim_runtime_startup_successor("old")

    def test_reconciled_successor_command_exits_zero(self):
        argv = ["flow", "run", "recover-runtime-startup", "sample", "old", "--worktree", self.tmp.name,
                "--source-commit", "deadbeef"]
        with patch.object(sys, "argv", argv), patch.object(flow, "recover_runtime_startup",
                return_value={"attempt_id": "next", "status": "reconciled", "predecessor_attempt_id": "old"}), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(flow.main(), 0)


if __name__ == "__main__":
    unittest.main()
