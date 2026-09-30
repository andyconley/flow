"""Black-box v9 receipt, trace, and inspection oracles."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli"))

import flow  # noqa: E402
from delivery_gateway import execute_v9_selected_action  # noqa: E402
from delivery_selection import make_action  # noqa: E402
from execution_ledger import ExecutionLedger  # noqa: E402
from selection_authority import seal_selection_authority  # noqa: E402
from tests.test_delivery_selection import _envelope  # noqa: E402


class V9CliReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.work_id, self.attempt_id = "v9proof", "a" * 32
        self.envelope = _envelope()
        self.envelope["work_id"] = self.work_id
        self.envelope["attempt_id"] = self.attempt_id
        inputs = self.envelope["selection_inputs"]
        self.envelope["selection_authority"] = seal_selection_authority(
            work_id=self.work_id, attempt_id=self.attempt_id,
            charter_digest=self.envelope["charter_digest"], manifest_digest=self.envelope["manifest_digest"],
            generation=1, sealed_at="2026-09-29T12:00:00Z",
            logical_assignments=self.envelope["logical_assignments"], policy=inputs["policy"],
            catalog=inputs["catalog"], availability=inputs["availability"], independence_constraints=[],
        )
        self.execution = self.root / ".flow" / "runs" / self.work_id / "execution"
        self.attempt_dir = self.execution / self.attempt_id
        self.attempt_dir.mkdir(parents=True)
        (self.execution.parent / "run.json").write_text(json.dumps({"state": "implementing", "phase": "implementation"}))
        (self.attempt_dir / "envelope.json").write_text(json.dumps(self.envelope, sort_keys=True))
        self.ledger = ExecutionLedger(self.execution / "ledger.sqlite")
        self.ledger.create_attempt(self.envelope)
        action = make_action(self.envelope, "producer", "Make the bounded edit.", sequence=1, manager_turn=1)
        execute_v9_selected_action(
            self.envelope, action, lambda binding, _: {"candidate": binding["candidate_id"], "ok": True},
            readiness_recheck=lambda binding: {**binding, "state": "ready"}, ledger=self.ledger, generation=1,
        )
        self.ledger.seal_v9_attempt(self.attempt_id, "completed", "proof complete",
                                    self.attempt_dir / "receipt.json", generation=1)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _cli(self, *argv: str) -> tuple[int, dict]:
        stream = io.StringIO()
        with patch.object(sys, "argv", ["flow", "run", *argv]), contextlib.redirect_stdout(stream):
            code = flow.main()
        return code, json.loads(stream.getvalue())

    def test_sealed_v9_receipt_verifies_and_trace_and_inspect_expose_same_selection(self) -> None:
        code, verified = self._cli("verify-receipt", self.work_id, "--project-root", str(self.root), "--json")
        self.assertEqual((code, verified["exit_code"], verified["checks"][0]["status"]), (0, 0, "pass"))

        code, trace = self._cli("trace", self.work_id, "--attempt", self.attempt_id,
                                "--project-root", str(self.root), "--json")
        self.assertEqual(code, 0)
        self.assertEqual(trace["attempts"][-1]["selection_trace"][0]["state"], "consumed")

        code, inspected = self._cli("inspect-delivery", self.work_id, "--attempt-id", self.attempt_id,
                                    "--project-root", str(self.root), "--json")
        self.assertEqual(code, 0)
        self.assertEqual(inspected["attempt"]["execution_protocol_version"], 9)
        self.assertEqual(inspected["attempt"]["selection_trace"][0]["state"], "consumed")

        code, execution = self._cli("inspect-execution", self.work_id, self.attempt_id,
                                    "--project-root", str(self.root), "--json")
        self.assertEqual(code, 0)
        self.assertEqual(execution["snapshot"]["execution_protocol_version"], 9)
        self.assertNotIn("receipt:ledger-mismatch", execution["missing_evidence"])

    def test_resealed_or_edited_receipt_fails_before_cli_reports_valid(self) -> None:
        receipt = self.attempt_dir / "receipt.json"
        receipt.write_bytes(receipt.read_bytes() + b" ")
        code, verified = self._cli("verify-receipt", self.work_id, "--project-root", str(self.root), "--json")
        self.assertEqual((code, verified["exit_code"]), (1, 1))
        self.assertIn("digest differs", verified["checks"][0]["detail"])


if __name__ == "__main__":
    unittest.main()
