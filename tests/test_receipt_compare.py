"""The full-row seal comparison and the receipt token block (ADR 0020, AC14, AC20)."""

from __future__ import annotations

import copy
import fcntl
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "cli"))
sys.path.insert(0, str(REPO_ROOT / "tests"))
import execution_ledger  # noqa: E402
import receipt_compare  # noqa: E402
from execution_contracts import ContractError, validate_receipt  # noqa: E402
from execution_ledger import ExecutionLedger  # noqa: E402
from receipt_compare import ROW_BLOCKS, compare_receipt_rows, describe, expected_blocks  # noqa: E402
from tests.test_expansion_ledger import v8  # noqa: E402
from tests.test_structured_verifier_ledger import _action  # noqa: E402
import tests.test_delivery_trace as trace_tests  # noqa: E402  (module import: its tests are not re-collected)


class CompareTests(unittest.TestCase):
    def expected(self):
        return {"actions": [{"action_id": "a1", "status": "completed", "result": {"usage": {"input_tokens": 1}}}],
                "manager_calls": [], "replans": [], "checkpoints": [], "verifier_inputs": [],
                "verifier_evaluations": [], "verifier_usage": {"maximum": 2}, "lineage_usage": None,
                "expansion": None, "manager_progress": None, "token_usage": {"charged_total": 1}}

    def test_equal_receipts_have_no_mismatch(self):
        receipt = {key: value for key, value in self.expected().items() if value is not None}
        self.assertEqual(compare_receipt_rows(receipt, self.expected(), blocks=ROW_BLOCKS), [])

    def test_a_content_change_with_the_same_status_is_named_with_both_values(self):
        receipt = copy.deepcopy(self.expected())
        receipt["actions"][0]["result"]["usage"]["input_tokens"] = 2
        [mismatch] = compare_receipt_rows(receipt, self.expected(), blocks=ROW_BLOCKS)
        self.assertEqual((mismatch["block"], mismatch["row_id"], mismatch["path"], mismatch["expected"], mismatch["found"]),
                         ("actions", "a1", "actions[0].result.usage.input_tokens", 1, 2))
        self.assertEqual(describe(mismatch), "actions a1 actions[0].result.usage.input_tokens: expected 1, found 2")

    def test_added_removed_keys_rows_and_blocks_are_mismatches(self):
        cases = {
            "added key": lambda r: r["actions"][0].update(extra=True),
            "removed key": lambda r: r["actions"][0].pop("result"),
            "added row": lambda r: r["actions"].append({"action_id": "a2", "status": "allowed"}),
            "removed row": lambda r: r["actions"].clear(),
            "missing block": lambda r: r.pop("verifier_usage"),
        }
        for label, mutate in cases.items():
            with self.subTest(label):
                receipt = copy.deepcopy(self.expected())
                mutate(receipt)
                self.assertTrue(compare_receipt_rows(receipt, self.expected(), blocks=ROW_BLOCKS))
        derived = copy.deepcopy(self.expected())
        derived["expansion"] = {"unexpected": True}
        self.assertTrue(compare_receipt_rows(derived, self.expected(), blocks=("expansion",)))
        derived.pop("token_usage")
        self.assertTrue(compare_receipt_rows(derived, self.expected(), blocks=("token_usage",)))

    def test_long_values_are_reported_by_digest(self):
        expected = self.expected()
        expected["actions"][0]["result"] = {"output": "x" * 500}
        receipt = copy.deepcopy(expected)
        receipt["actions"][0]["result"]["output"] = "y" * 500
        [mismatch] = compare_receipt_rows(receipt, expected, blocks=ROW_BLOCKS)
        self.assertIn("expected_sha256", mismatch)
        self.assertIn("expected sha256", describe(mismatch))

    def test_one_function_serves_both_seals(self):
        self.assertIs(execution_ledger.compare_receipt_rows, receipt_compare.compare_receipt_rows)


class LedgerSealTests(unittest.TestCase):
    """AC20: finish_attempt and seal_terminal_uncertain refuse row content that differs from the ledger."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.dir = Path(temporary.name)
        self.ledger = ExecutionLedger(self.dir / "ledger.sqlite")
        self.env = v8(manager="claude", attempt="sealed")
        self.ledger.create_attempt(self.env)
        self.ledger.decide(self.env, _action(self.env, 1, self.env["roster"][1], "Produce."), generation=1)

    def receipt(self):
        view = self.ledger.seal_view("sealed")
        return copy.deepcopy({key: value for key, value in expected_blocks(view["snapshot"], view["blocks"]).items()
                              if value is not None})

    def finish(self, receipt):
        path = self.dir / "receipt.json"
        path.write_text(json.dumps(receipt))
        self.ledger.finish_attempt("sealed", "failed", "test", str(path), generation=1)

    def test_finish_refuses_a_changed_row_with_the_same_status(self):
        for label, mutate in (("action content", lambda r: r["actions"][0].update(reason="policy_forged")),
                              ("added key", lambda r: r["actions"][0].update(note="x")),
                              ("removed key", lambda r: r["actions"][0].pop("grant_id")),
                              ("verifier usage", lambda r: r["verifier_usage"].update(reserved=9))):
            with self.subTest(label):
                forged = self.receipt()
                mutate(forged)
                with self.assertRaisesRegex(ContractError, "receipt rows differ from the ledger: "):
                    self.finish(forged)
        self.assertEqual(self.ledger.snapshot("sealed")["status"], "started")

    def test_finish_refuses_an_edited_token_block(self):
        forged = self.receipt()
        forged["token_usage"]["observed_charged"] += 1
        with self.assertRaisesRegex(ContractError, "token_usage evidence differs from the ledger"):
            self.finish(forged)
        self.finish(self.receipt())
        self.assertEqual(self.ledger.snapshot("sealed")["status"], "failed")

    def test_the_terminal_seal_refuses_a_changed_row_with_the_same_status(self):
        def render(snapshot, blocks):
            receipt = copy.deepcopy({key: value for key, value in expected_blocks(snapshot, blocks).items()
                                     if value is not None})
            receipt.update(status="abandoned", attempt_id="sealed")
            receipt["actions"][0]["reason"] = "forged"
            return json.dumps(receipt).encode()

        with self.ledger.send_lock(), self.assertRaisesRegex(ContractError, "terminal receipt rows differ from the ledger: "
                                                                             "actions"):
            self.ledger.seal_terminal_uncertain("sealed", "abandoned", expected_generation=1, actor="andy",
                                                explanation="test", cause="reconciliation_required",
                                                receipt_path=self.dir / "terminal.json", build_receipt=render)
        self.assertFalse((self.dir / "terminal.json").exists())


class GatewayTokenBlockTests(trace_tests.TraceFixture):
    """AC14 and AC20 through the gateway: the sealed receipt's token block, and the snapshot taken under send_lock."""

    headroom = {"delegations": 1}

    def test_the_sealed_receipt_carries_a_token_block_its_rows_recompute(self):
        held = []
        real = ExecutionLedger.seal_view

        def check_lock(ledger, attempt_id):
            fd = os.open(ledger.path.parent / "ledger.send.lock", os.O_RDWR)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                held.append(False)
                fcntl.flock(fd, fcntl.LOCK_UN)
            except BlockingIOError:
                held.append(True)
            finally:
                os.close(fd)
            return real(ledger, attempt_id)

        with patch.object(ExecutionLedger, "seal_view", check_lock):
            result = self.completed_run()
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(held[-1:], [True], "the receipt is built from a snapshot taken under send_lock")
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        envelope = self.ledger().snapshot(result["attempt_id"])["envelope"]
        validate_receipt(envelope, receipt)
        block = receipt["token_usage"]
        self.assertEqual(block["unit"], "charged_v1")
        self.assertEqual(block["charged_total"], block["observed_charged"] + block["unobserved_charged"])
        for field in sorted(block):
            with self.subTest(field=field):
                forged = copy.deepcopy(receipt)
                forged["token_usage"][field] = "edited" if isinstance(block[field], str) else block[field] + 1
                with self.assertRaisesRegex(ContractError, "token usage differs from its rows"):
                    validate_receipt(envelope, forged)
        missing = copy.deepcopy(receipt)
        missing.pop("token_usage")
        with self.assertRaisesRegex(ContractError, "token usage differs from its rows"):
            validate_receipt(envelope, missing)


if __name__ == "__main__":
    unittest.main()
