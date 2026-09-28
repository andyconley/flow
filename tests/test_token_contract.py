"""The sealed lineage token budget (ADR 0020, AC8, AC13, I6, A1).

The v4 Shaper Contract and Delivery Charter seal three token fields and a
tranche headroom; the v8 envelope projects them through one shared
function; a pre-release v8 attempt stays readable and abandonable but can
never be started.
"""

from __future__ import annotations

import copy
import json
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import delivery_contracts  # noqa: E402
import delivery_gateway  # noqa: E402
from delivery_contracts import (DEFAULT_TOKEN_BUDGET, DeliveryContractError, build_delivery_charter,  # noqa: E402
                                build_shaper_contract, project_envelope_limits, validate_delivery_charter,
                                validate_shaper_intent)
from execution_contracts import (ContractError, expansion_fits, handback_supported, validate_envelope,  # noqa: E402
                                 validate_receipt)
from execution_ledger import ExecutionLedger  # noqa: E402
from runner_limits import MAX_LINEAGE_TOKENS, MAX_TOKEN_TRANCHES  # noqa: E402
from tests.legacy_v8_rows import insert_legacy_attempt, legacy_envelope  # noqa: E402
from tests.shaper_intent_fixture import shaper_intent  # noqa: E402
from tests.test_chartered_execution_contract import structured_verifier  # noqa: E402
from tests.test_delivery_termination import AbandonFixture  # noqa: E402

SOURCES = {"requirements": {"path": ".flow/runs/demo/requirements.md", "sha256": "a" * 64},
           "acceptance_criteria": {"path": ".flow/runs/demo/acceptance.md", "sha256": "b" * 64}}


def intent_with(tokens=None, headroom=None):
    intent = shaper_intent(expansion_headroom=headroom)
    intent["budget_safety_envelope"]["enforceable"].update(tokens or {})
    return intent


class TokenContractTests(unittest.TestCase):
    def test_the_default_budget_is_the_calibrated_one(self):
        self.assertEqual(DEFAULT_TOKEN_BUDGET, {"max_lineage_tokens": 200_000, "token_tranche": 100_000,
                                                "unobserved_send_tokens": 100_000})
        self.assertEqual((MAX_TOKEN_TRANCHES, MAX_LINEAGE_TOKENS), (10, 2_000_000))
        validate_shaper_intent(intent_with(DEFAULT_TOKEN_BUDGET))

    def test_each_invalid_budget_is_refused(self):
        base = dict(DEFAULT_TOKEN_BUDGET)
        cases = {
            "missing field": (lambda e: e.pop("token_tranche"), None, "invalid"),
            "zero": (lambda e: e.update(max_lineage_tokens=0), None, "positive integer"),
            "boolean": (lambda e: e.update(token_tranche=True), None, "positive integer"),
            "tranche below the unobserved charge": (lambda e: e.update(token_tranche=50_000), None,
                                                    "at least unobserved_send_tokens"),
            "unobserved above the budget": (lambda e: e.update(max_lineage_tokens=50_000, token_tranche=100_000), None,
                                            "exceeds max_lineage_tokens"),
            "headroom above the tranche ceiling": (lambda e: None, {"tokens": MAX_TOKEN_TRANCHES + 1}, "runner ceiling"),
            "budget plus headroom above the absolute ceiling": (lambda e: e.update(max_lineage_tokens=1_900_000),
                                                                {"tokens": 2}, "runner ceiling"),
        }
        for label, (mutate, headroom, message) in cases.items():
            with self.subTest(label):
                intent = intent_with(base, headroom)
                mutate(intent["budget_safety_envelope"]["enforceable"])
                with self.assertRaisesRegex(DeliveryContractError, message):
                    validate_shaper_intent(intent)

    def test_the_charter_and_envelope_project_the_budget_exactly(self):
        charter = build_delivery_charter(build_shaper_contract("demo", SOURCES, intent_with(DEFAULT_TOKEN_BUDGET,
                                                                                            {"tokens": 2})))
        validate_delivery_charter(charter)
        self.assertEqual(charter["charter_version"], 4)
        self.assertEqual({key: charter["limits"][key] for key in DEFAULT_TOKEN_BUDGET}, DEFAULT_TOKEN_BUDGET)
        self.assertEqual(charter["limits"]["expansion_headroom"]["tokens"], 2)
        limits, headroom = project_envelope_limits(charter["limits"])
        self.assertEqual({key: limits[key] for key in DEFAULT_TOKEN_BUDGET}, DEFAULT_TOKEN_BUDGET)
        self.assertEqual(headroom, {"tokens": 2})
        self.assertIs(delivery_gateway.project_envelope_limits, delivery_contracts.project_envelope_limits,
                      "prepare and verify-receipt share one projection")
        forged = copy.deepcopy(charter)
        forged["limits"]["token_tranche"] = 1
        forged["digest"] = delivery_contracts.digest({k: v for k, v in forged.items() if k != "digest"})
        with self.assertRaisesRegex(DeliveryContractError, "at least unobserved_send_tokens"):
            validate_delivery_charter(forged)

    def test_envelopes_accept_exactly_two_v8_key_sets(self):
        env = structured_verifier()
        validate_envelope(env)
        self.assertTrue(handback_supported(env))
        legacy = legacy_envelope(env)
        validate_envelope(legacy)  # pre-release attempts stay readable
        self.assertFalse(handback_supported(legacy))
        partial = copy.deepcopy(env)
        partial["limits"].pop("token_tranche")
        with self.assertRaises(ContractError):
            validate_envelope(partial)
        with_headroom = copy.deepcopy(legacy)
        with_headroom["expansion_headroom"] = {"tokens": 1}
        with self.assertRaisesRegex(ContractError, "token headroom requires a sealed token budget"):
            validate_envelope(with_headroom)

    def test_the_tranche_ceiling_includes_the_absolute_budget(self):
        env = structured_verifier()
        env["limits"].update(max_lineage_tokens=1_990_000, token_tranche=5_000, unobserved_send_tokens=1_000)
        self.assertTrue(expansion_fits(env, "tokens", 2))
        self.assertFalse(expansion_fits(env, "tokens", 3), "1,990,000 + 3 x 5,000 passes the 2M ceiling")
        self.assertFalse(expansion_fits(legacy_envelope(env), "tokens", 1))


class PreReleaseAttemptTests(AbandonFixture):
    """I6 and A1: a pre-release v8 attempt cannot start, but it can still be abandoned."""

    def test_create_attempt_refuses_an_envelope_without_a_token_budget(self):
        env = legacy_envelope(structured_verifier())
        ledger = ExecutionLedger(self.root / "legacy.sqlite")
        with self.assertRaisesRegex(ContractError, "sealed lineage token budget"):
            ledger.create_attempt(env)

    def test_prepare_refuses_a_charter_that_seals_no_token_budget(self):
        original = delivery_gateway._sealed_delivery_authority

        def pre_release(*args, **kwargs):
            authority = copy.deepcopy(original(*args, **kwargs))
            authority["charter"]["charter_version"] = 3
            return authority

        with patch("delivery_gateway._sealed_delivery_authority", side_effect=pre_release):
            with self.assertRaisesRegex(ContractError, "seals a token budget"):
                self.prepare()

    def legacy(self, attempt_id, predecessor=None):
        envelope, _, attempt_dir, _ = self.prepare()
        (self.run / "execution" / attempt_id).mkdir(parents=True, exist_ok=True)
        (self.run / "execution" / attempt_id / "baseline.json").write_text((attempt_dir / "baseline.json").read_text())
        # the prepared (handback) attempt is not part of this scenario
        with sqlite3.connect(self.run / "execution" / "ledger.sqlite") as db:
            db.execute("DELETE FROM events WHERE attempt_id=?", (envelope["attempt_id"],))
            db.execute("DELETE FROM attempts WHERE attempt_id=?", (envelope["attempt_id"],))
        return insert_legacy_attempt(self.run / "execution" / "ledger.sqlite", self.run / "execution" / attempt_id,
                                     envelope, attempt_id, predecessor)

    def test_a_pre_release_attempt_refuses_to_advance(self):
        from tests.test_structured_verifier_ledger import _action
        envelope = self.legacy("a" * 32)
        ledger = ExecutionLedger(self.run / "execution" / "ledger.sqlite")
        with self.assertRaisesRegex(ContractError, "predates the sealed token budget"):
            ledger.decide(envelope, _action(envelope, 1, envelope["roster"][1], "Produce."), generation=1)

    def test_a_pre_release_attempt_is_abandoned_with_its_legacy_blocks(self):
        envelope = self.legacy("a" * 32)
        self.assertFalse(handback_supported(envelope))
        result = self.abandon("a" * 32)
        snapshot, receipt = self.assert_abandoned("a" * 32, cause=result["cause"])
        self.assertNotIn("token_usage", receipt)
        self.assertNotIn("lineage_usage", receipt)

    def test_a_pre_release_successor_of_a_pre_release_attempt_is_abandoned(self):
        first = self.legacy("a" * 32)
        self.abandon("a" * 32)
        sealed = self.ledger(read_only=True).snapshot("a" * 32)
        link = {"attempt_id": "a" * 32, "terminal_status": "abandoned", "receipt_sha256": sealed["sealed_receipt_sha256"],
                "lead_generation": first["delivery_lead_claim"]["generation"]}
        self.legacy("c" * 32, link)
        result = self.abandon("c" * 32)
        snapshot, receipt = self.assert_abandoned("c" * 32, cause=result["cause"])
        self.assertEqual(receipt["lineage_usage"], {"predecessor_paid_calls": 0, "predecessor_verifier_sends": 0},
                         "a pre-release lineage keeps its two-key shape")


class LineageChargeTests(AbandonFixture):
    """AC13 (ledger half): a successor's lineage charge counts an abandoned predecessor's unknown send."""

    def test_the_unknown_send_is_charged_its_sealed_amount(self):
        attempt_id = self.unknown_editor_send()
        self.abandon(attempt_id)
        result, _, _, captured = self._run_v8([self.PASS])
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        unobserved = captured["envelope"]["limits"]["unobserved_send_tokens"]
        self.assertEqual(receipt["lineage_usage"]["predecessor_charged"], unobserved)
        validate_receipt(captured["envelope"], receipt)
        with sqlite3.connect(self.run / "execution" / "ledger.sqlite") as db:
            charged = ExecutionLedger._lineage_charged(db, captured["envelope"])
        self.assertEqual(charged["predecessor_charged"], unobserved)
        self.assertEqual(charged["total"], charged["predecessor_charged"] + charged["own"])

    def test_successor_charter_starts_a_fresh_sealed_budget(self):
        attempt_id = self.unknown_editor_send()
        self.abandon(attempt_id)
        _, _, _, captured = self._run_v8([self.PASS])
        successor = copy.deepcopy(captured["envelope"])
        successor["delivery_charter_digest"] = "f" * 64
        with sqlite3.connect(self.run / "execution" / "ledger.sqlite") as db:
            charged = ExecutionLedger._lineage_charged(db, successor)
            attempts = ExecutionLedger._authority_lineage_attempts(db, successor)
        self.assertEqual(charged["predecessor_charged"], 0)
        self.assertEqual(attempts, [successor["attempt_id"]])


if __name__ == "__main__":
    unittest.main()
