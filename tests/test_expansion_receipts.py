"""Receipts list every expansion request and grant, and validation recomputes them (ADR 0017)."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

from execution_contracts import ContractError, validate_receipt  # noqa: E402
from execution_ledger import ExecutionLedger  # noqa: E402
from tests.test_expansion_gateway import ExpansionGatewayFixture  # noqa: E402
from tests.test_expansion_ledger import v8  # noqa: E402
from tests.test_structured_verifier_ledger import _action  # noqa: E402


class ReceiptExpansionValidationTests(ExpansionGatewayFixture):
    headroom = {"delegations": 1}

    def setUp(self):
        super().setUp()
        supervisor, worker = self.worker_plan([])
        result = self.execute(supervisor, worker=worker)
        self.assertEqual(result["status"], "completed", result)
        self.receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.envelope = self.ledger().snapshot(result["attempt_id"])["envelope"]

    def tampered(self, mutate):
        receipt = copy.deepcopy(self.receipt)
        mutate(receipt)
        return receipt

    def assertRejected(self, mutate, message):
        with self.assertRaisesRegex(ContractError, message):
            validate_receipt(self.envelope, self.tampered(mutate))

    def grant(self, receipt):
        return receipt["expansion"]["requests"][0]["grant"]

    def test_receipt_lists_every_request_and_decision(self):
        validate_receipt(self.envelope, self.receipt)
        [request] = self.receipt["expansion"]["requests"]
        self.assertEqual((request["status"], request["amount"], request["grant"]["authority"]),
                         ("granted", 1, "charter_headroom"))
        self.assertEqual(self.receipt["expansion"]["headroom"]["delegations"], 1)
        self.assertEqual(self.receipt["verifier_usage"]["maximum"], 2)

    def test_receipt_rejects_removed_grant(self):
        self.assertRejected(lambda receipt: receipt["expansion"]["requests"].clear(), "lacks a consumed grant")

    def test_receipt_rejects_removed_expansion_block(self):
        self.assertRejected(lambda receipt: receipt.pop("expansion"), "lacks a consumed grant")

    def test_receipt_rejects_auto_beyond_headroom(self):
        def duplicate(receipt):
            extra = copy.deepcopy(receipt["expansion"]["requests"][0])
            extra["request_id"] = "exp-duplicate"
            receipt["expansion"]["requests"].append(extra)
        self.assertRejected(duplicate, "exceeds sealed headroom")

    def test_receipt_rejects_wrong_authority(self):
        self.assertRejected(lambda receipt: self.grant(receipt).update(authority="shaper"), "authority is invalid")
        self.assertRejected(lambda receipt: self.grant(receipt).update(authority="engineer"), "authority is invalid")

    def test_receipt_rejects_amount_above_one(self):
        self.assertRejected(lambda receipt: self.grant(receipt).update(amount=2), "grant is invalid")
        self.assertRejected(lambda receipt: receipt["expansion"]["requests"][0].update(amount=2), "request is invalid")

    def test_receipt_rejects_foreign_lineage(self):
        self.assertRejected(lambda receipt: receipt["expansion"].update(lineage_id="another-attempt"), "evidence is invalid")

    def test_receipt_rejects_foreign_generation(self):
        self.assertRejected(lambda receipt: self.grant(receipt).update(owner_generation=7), "grant is invalid")

    def test_receipt_rejects_altered_headroom(self):
        self.assertRejected(lambda receipt: receipt["expansion"]["headroom"].update(delegations=3), "evidence is invalid")

    def test_receipt_rejects_expansion_granted_without_grant(self):
        def detach(receipt):
            self.grant(receipt).update(authority="engineer", actor="andy", status="lapsed", consumed_by=None)
        self.assertRejected(detach, "lacks a consumed grant")

    def test_receipt_rejects_an_open_request_or_unused_grant(self):
        self.assertRejected(lambda receipt: self.grant(receipt).update(
            authority="engineer", actor="andy", status="available", consumed_by=None), "open expansion")
        def pending(receipt):
            receipt["expansion"]["requests"][0].update(status="pending", grant=None)
        self.assertRejected(pending, "open expansion")

    def test_receipt_accepts_a_spent_unit_whose_send_grant_expired(self):
        def expire(receipt):
            row = next(item for item in receipt["actions"] if item["action_id"] == self.grant(receipt)["consumed_by"])
            row.update(status="denied", reason="grant_expired")
        receipt = self.tampered(expire)
        from execution_contracts import _validate_expansion
        self.assertEqual(_validate_expansion(self.envelope, receipt)["delegations"], 3)


class VerifierExpansionReceiptTests(ExpansionGatewayFixture):
    # The retry is the third action, so it needs a delegation and a verifier unit.
    headroom = {"verifier_calls": 1, "delegations": 1}
    max_verifier_calls = 1

    def test_verifier_grant_raises_the_receipted_verifier_maximum(self):
        supervisor, worker = self.worker_plan([])
        result = self.execute(supervisor, worker=worker)
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(receipt["verifier_usage"]["maximum"], 2)
        self.assertEqual(receipt["expansion"]["requests"][0]["limits"], ["delegations", "verifier_calls"])
        validate_receipt(self.ledger().snapshot(result["attempt_id"])["envelope"], receipt)


class SealedExpansionEvidenceTests(unittest.TestCase):
    """The seal compares the receipt's block with the ledger: nothing added, removed, or altered."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.dir = Path(temporary.name)
        self.ledger = ExecutionLedger(self.dir / "ledger.sqlite")
        self.env = v8(headroom={"delegations": 1}, attempt="sealed")
        self.ledger.create_attempt(self.env)
        self.ledger.decide(self.env, _action(self.env, 1, self.env["roster"][1], "Produce."), generation=1)
        self.ledger.decide(self.env, _action(self.env, 2, self.env["roster"][0], "Verify."), generation=1)
        self.block = self.ledger.expansion_receipt("sealed")

    def seal(self, block):
        path = self.dir / "receipt.json"
        path.write_text(json.dumps({"expansion": block} if block is not None else {}))
        self.ledger.finish_attempt("sealed", "failed", "test", str(path), generation=1)

    def test_added_removed_or_altered_grants_are_refused_at_seal(self):
        added = copy.deepcopy(self.block)
        added["requests"].append({**copy.deepcopy(added["requests"][0]), "request_id": "exp-added"})
        altered = copy.deepcopy(self.block)
        altered["requests"][0]["grant"]["actor"] = "someone"
        for label, block in (("added", added), ("removed", None), ("altered", altered)):
            with self.subTest(label), self.assertRaisesRegex(ContractError, "differs from the ledger"):
                self.seal(block)
        self.seal(self.block)
        self.assertEqual(self.ledger.snapshot("sealed")["status"], "failed")


if __name__ == "__main__":
    unittest.main()
