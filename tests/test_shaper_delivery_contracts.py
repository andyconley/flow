import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "cli"))
from delivery_contracts import (  # noqa: E402
    DeliveryContractError,
    build_delivery_charter,
    build_shaper_contract,
    validate_delivery_charter,
    validate_shaper_contract,
)
from tests.shaper_intent_fixture import shaper_intent  # noqa: E402


class ShaperDeliveryContractTests(unittest.TestCase):
    def sources(self):
        return {
            "requirements": {"path": ".flow/runs/demo/requirements.md", "sha256": "a" * 64},
            "acceptance_criteria": {"path": ".flow/runs/demo/acceptance.md", "sha256": "b" * 64},
        }

    def test_equivalent_inputs_produce_stable_sealed_contracts(self):
        first = build_shaper_contract("demo", self.sources(), shaper_intent())
        second = build_shaper_contract("demo", dict(reversed(list(self.sources().items()))), shaper_intent())
        self.assertEqual(first, second)
        validate_shaper_contract(first)
        charter = build_delivery_charter(first)
        validate_delivery_charter(charter)
        self.assertEqual(charter, build_delivery_charter(first))
        self.assertEqual(charter["compatibility_version"], 7)

    def test_per_run_intent_changes_the_sealed_semantics(self):
        first_intent = shaper_intent()
        second_intent = shaper_intent()
        second_intent["problem"] = "A different approved problem."
        first = build_shaper_contract("demo", self.sources(), first_intent)
        second = build_shaper_contract("demo", self.sources(), second_intent)
        self.assertNotEqual(first["digest"], second["digest"])
        self.assertEqual(second["problem"]["value"], "A different approved problem.")

    def test_mutation_is_detected_by_digest(self):
        contract = build_shaper_contract("demo", self.sources(), shaper_intent())
        contract["scope"].append("unapproved expansion")
        with self.assertRaisesRegex(DeliveryContractError, "digest mismatch"):
            validate_shaper_contract(contract)

    def test_requires_approved_sources(self):
        sources = self.sources()
        del sources["acceptance_criteria"]
        with self.assertRaisesRegex(DeliveryContractError, "acceptance_criteria"):
            build_shaper_contract("demo", sources, shaper_intent())

    def test_missing_required_shaper_field_is_refused(self):
        contract = build_shaper_contract("demo", self.sources(), shaper_intent())
        del contract["budget_safety_envelope"]
        with self.assertRaisesRegex(DeliveryContractError, "budget_safety_envelope"):
            validate_shaper_contract(contract)

    def test_delivery_charter_rejects_authority_expansion(self):
        charter = build_delivery_charter(build_shaper_contract("demo", self.sources(), shaper_intent()))
        charter["approval_matrix"]["provider_dispatch"] = "Magentic"
        with self.assertRaisesRegex(DeliveryContractError, "Flow grant"):
            validate_delivery_charter(charter)

    def test_delivery_charter_preserves_approved_capabilities_and_limits(self):
        intent = shaper_intent()
        intent["delegation_matrix"]["max_delegations"] = 2
        enforceable = intent["budget_safety_envelope"]["enforceable"]
        enforceable.update(max_concurrent=1, max_replans=0, max_paid_worker_calls=2)
        charter = build_delivery_charter(build_shaper_contract("demo", self.sources(), intent))
        self.assertEqual(charter["limits"]["delegations"], 2)
        self.assertEqual(charter["limits"]["concurrency"], 1)
        self.assertEqual(charter["limits"]["replans"], 0)
        self.assertEqual(charter["limits"]["max_paid_worker_calls"], 2)
        self.assertEqual(charter["eligible_specialists"]["lead-developer"]["approved_capabilities"], ["scoped-edit"])
        self.assertEqual(charter["eligible_specialists"]["lead-developer"]["runtime_capabilities"], ["edit", "read"])
        self.assertEqual(charter["prohibited_capabilities"], intent["prohibited_capabilities"])

    def test_unsupported_specialist_capability_is_refused(self):
        intent = shaper_intent()
        intent["allowed_specialists"][0]["capabilities"] = ["arbitrary-shell"]
        with self.assertRaisesRegex(DeliveryContractError, "unsupported"):
            build_shaper_contract("demo", self.sources(), intent)

    def test_source_from_a_different_run_is_refused(self):
        sources = self.sources()
        sources["requirements"]["path"] = ".flow/runs/other/requirements.md"
        with self.assertRaisesRegex(DeliveryContractError, "outside the current run"):
            build_shaper_contract("demo", sources, shaper_intent())
