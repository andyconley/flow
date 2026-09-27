"""The startup-recovery command never replays a provider-visible failure."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))
from delivery_gateway import ContractError, recover_runtime_startup


class RuntimeStartupRecoveryTests(unittest.TestCase):
    def _snapshot(self, **changes):
        receipt = Path(self.tmp.name) / "receipt.json"
        receipt.write_text("sealed\n")
        value = {"work_id": "sample", "execution_protocol_version": 8, "status": "failed",
                 "reason": "MAF delivery child failed: missing agent_framework", "actions": [], "manager_calls": [],
                 "receipt_path": str(receipt), "sealed_receipt_sha256": "a" * 64}
        value.update(changes)
        return value

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        path = Path(self.tmp.name) / ".flow" / "runs" / "sample" / "execution"
        path.mkdir(parents=True)
        (path / "ledger.sqlite").write_text("fixture")

    def test_only_a_sealed_zero_send_runtime_failure_can_start_successor(self):
        with patch("delivery_gateway.ExecutionLedger") as ledger, \
             patch("delivery_gateway.execute_chartered_delivery", return_value={"attempt_id": "next", "status": "completed"}) as execute:
            ledger.return_value.snapshot.return_value = self._snapshot()
            result = recover_runtime_startup("sample", "old", Path(self.tmp.name), "commit", root=Path(self.tmp.name))
        self.assertEqual(result["attempt_id"], "next")
        execute.assert_called_once()

    def test_any_send_refuses_without_creating_successor(self):
        with patch("delivery_gateway.ExecutionLedger") as ledger, \
             patch("delivery_gateway.execute_chartered_delivery") as execute:
            ledger.return_value.snapshot.return_value = self._snapshot(actions=[{"status": "unknown"}])
            with self.assertRaisesRegex(ContractError, "observed or uncertain"):
                recover_runtime_startup("sample", "old", Path(self.tmp.name), "commit", root=Path(self.tmp.name))
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
