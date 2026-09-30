from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli"))

from delivery_selection import compute_binding, make_action  # noqa: E402
from provider_selection import digest  # noqa: E402
from selection_receipt import (  # noqa: E402
    V9ReceiptError,
    project_selection_trace,
    seal_selection_receipt,
    verify_selection_receipt,
)
from tests.test_delivery_selection import _envelope  # noqa: E402


def _receipt() -> dict:
    envelope = _envelope()
    first = make_action(envelope, "producer", "Implement.", sequence=1, manager_turn=1)
    successor_decision = compute_binding(
        envelope, "producer", prior_no_send_failures=["local"]
    )
    successor = make_action(
        envelope, "producer", "Implement.", sequence=1, manager_turn=1,
        decision=successor_decision,
    )
    selections = [
        {
            "selection_id": first["selection_id"],
            "logical_action_id": first["logical_action_id"],
            "decision_digest": first["selection_decision"]["decision_digest"],
            "candidate_id": "local",
            "state": "superseded",
            "reason": "connection_refused_before_send",
            "predecessor_selection_id": None,
            "provider_action_id": None,
            "prior_no_send_failures": [],
        },
        {
            "selection_id": successor["selection_id"],
            "logical_action_id": successor["logical_action_id"],
            "decision_digest": successor["selection_decision"]["decision_digest"],
            "candidate_id": "claude",
            "state": "consumed",
            "reason": "",
            "predecessor_selection_id": first["selection_id"],
            "provider_action_id": successor["action_id"],
            "prior_no_send_failures": ["local"],
        },
    ]
    return seal_selection_receipt(envelope, [first, successor], selections)


def _reseal(receipt: dict) -> None:
    receipt["receipt_digest"] = digest({key: item for key, item in receipt.items()
                                         if key != "receipt_digest"})


class SelectionReceiptTests(unittest.TestCase):
    def test_offline_recomputation_and_structured_fallback_trace(self) -> None:
        receipt = _receipt()
        result = verify_selection_receipt(receipt)
        self.assertEqual(result["status"], "valid_pass")
        trace = project_selection_trace(receipt)
        first = next(row for row in trace if row["state"] == "superseded")
        self.assertEqual(len(first["successors"]), 1)
        self.assertEqual(next(row for row in trace if row["state"] == "consumed")["candidate_id"], "claude")

    def test_pre_send_refusal_without_provider_action_is_validated_from_successor(self) -> None:
        receipt = _receipt()
        receipt["actions"] = receipt["actions"][1:]
        _reseal(receipt)
        self.assertEqual(verify_selection_receipt(receipt)["status"], "valid_pass")

    def test_individual_decision_field_tampering_has_specific_failure(self) -> None:
        originals = _receipt()
        mutations = {
            "requirements_digest": "0" * 64,
            "policy_digest": "1" * 64,
            "catalog_digest": "2" * 64,
            "availability_digest": "3" * 64,
            "exclusions": [{"candidate_id": "local", "reason_codes": ["availability_stale"]}],
            "ordered_candidates": [],
            "selected_candidate_id": "codex",
            "selected_binding": None,
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                receipt = copy.deepcopy(originals)
                receipt["actions"][0]["selection_decision"][field] = value
                _reseal(receipt)
                with self.assertRaises(V9ReceiptError) as raised:
                    verify_selection_receipt(receipt)
                self.assertEqual(raised.exception.code, f"v9_{field}_mismatch")

    def test_fallback_lineage_tampering_is_rejected(self) -> None:
        receipt = _receipt()
        receipt["selections"][1]["prior_no_send_failures"] = []
        _reseal(receipt)
        with self.assertRaises(V9ReceiptError) as raised:
            verify_selection_receipt(receipt)
        self.assertIn(raised.exception.code, {
            "v9_prior_no_send_failures_mismatch", "v9_fallback_lineage_invalid"
        })

    def test_orphan_selection_row_is_rejected_even_when_resealed(self) -> None:
        receipt = _receipt()
        orphan = copy.deepcopy(receipt["selections"][0])
        orphan["selection_id"] = "f" * 64
        orphan["logical_action_id"] = "e" * 64
        receipt["selections"].append(orphan)
        _reseal(receipt)
        with self.assertRaises(V9ReceiptError) as raised:
            verify_selection_receipt(receipt)
        self.assertEqual(raised.exception.code, "v9_orphan_selection_row")

    def test_duplicate_action_cannot_reuse_one_selection_row(self) -> None:
        receipt = _receipt()
        receipt["actions"].append(copy.deepcopy(receipt["actions"][0]))
        _reseal(receipt)
        with self.assertRaises(V9ReceiptError) as raised:
            verify_selection_receipt(receipt)
        self.assertEqual(raised.exception.code, "v9_duplicate_selection_action")

    def test_nonconsumed_selection_requires_no_send_closure(self) -> None:
        receipt = _receipt()
        receipt["selections"][0]["reason"] = ""
        _reseal(receipt)
        with self.assertRaises(V9ReceiptError) as raised:
            verify_selection_receipt(receipt)
        self.assertEqual(raised.exception.code, "v9_unconsumed_selection_closure_invalid")

    def test_duplicate_prior_no_send_failure_is_rejected(self) -> None:
        receipt = _receipt()
        receipt["selections"][1]["prior_no_send_failures"] = ["local", "local"]
        _reseal(receipt)
        with self.assertRaises(V9ReceiptError) as raised:
            verify_selection_receipt(receipt)
        self.assertEqual(raised.exception.code, "v9_prior_no_send_failures_invalid")


if __name__ == "__main__":
    unittest.main()
