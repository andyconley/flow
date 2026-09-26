import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "cli"))
from delivery_contracts import (  # noqa: E402
    DeliveryContractError,
    build_delivery_charter,
    build_shaper_contract,
    digest,
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
        self.assertEqual(first["version"], 3)
        self.assertEqual(first["max_verifier_calls"], 2)
        self.assertEqual(charter["charter_version"], 3)
        self.assertEqual(charter["limits"]["max_verifier_calls"], 2)
        # Omitted headroom seals as explicit zeros (AC1).
        zeros = {"delegations": 0, "paid_worker_calls": 0, "verifier_calls": 0, "manager_calls": 0, "manager_rounds": 0}
        self.assertEqual(first["expansion_headroom"], zeros)
        self.assertEqual(charter["limits"]["expansion_headroom"], zeros)

    def test_v2_verifier_allowance_is_sealed_and_bounded(self):
        intent = shaper_intent()
        intent["max_verifier_calls"] = 1
        charter = build_delivery_charter(build_shaper_contract("demo", self.sources(), intent))
        self.assertEqual(charter["limits"]["max_verifier_calls"], 1)
        charter["limits"]["max_verifier_calls"] = 3
        with self.assertRaisesRegex(DeliveryContractError, "max_verifier_calls"):
            validate_delivery_charter(charter)

    def test_expansion_headroom_is_sealed_and_bounded_by_runner_ceilings(self):
        intent = shaper_intent(max_delegations=3, limits={"max_concurrent": 2, "max_paid_worker_calls": 2,
                                                          "max_manager_calls": 8, "max_manager_rounds": 4},
                               expansion_headroom={"delegations": 3, "paid_worker_calls": 1, "manager_calls": 4, "manager_rounds": 2})
        intent["max_verifier_calls"] = 1
        intent["expansion_headroom"]["verifier_calls"] = 1
        shaper = build_shaper_contract("demo", self.sources(), intent)
        charter = build_delivery_charter(shaper)
        self.assertTrue(shaper["delegation_matrix"]["delegated_expansion"])
        self.assertEqual(charter["limits"]["expansion_headroom"], {
            "delegations": 3, "paid_worker_calls": 1, "verifier_calls": 1, "manager_calls": 4, "manager_rounds": 2})

    def test_expansion_headroom_refusals(self):
        low = {"max_concurrent": 2, "max_paid_worker_calls": 2, "max_manager_calls": 8, "max_manager_rounds": 4}
        cases = {
            "negative": ({"delegations": -1}, "non-negative"),
            "boolean": ({"delegations": True}, "non-negative"),
            "replans": ({"replans": 1}, "non-expandable"),
            "concurrency": ({"concurrency": 1}, "non-expandable"),
            "verifier above two": ({"verifier_calls": 1}, "runner ceiling"),
            "manager calls above twelve": ({"manager_calls": 5}, "runner ceiling"),
            "manager rounds above six": ({"manager_rounds": 3}, "runner ceiling"),
            "actions above six": ({"delegations": 4}, "runner ceiling"),
            "paid outgrows delegations": ({"paid_worker_calls": 2}, "delegation headroom"),
        }
        for label, (headroom, message) in cases.items():
            with self.subTest(label), self.assertRaisesRegex(DeliveryContractError, message):
                intent = shaper_intent(max_delegations=3, limits=dict(low), expansion_headroom=headroom)
                if label == "paid outgrows delegations":
                    intent["budget_safety_envelope"]["enforceable"]["max_paid_worker_calls"] = 3
                build_shaper_contract("demo", self.sources(), intent)

    def test_delegated_expansion_must_match_sealed_headroom(self):
        intent = shaper_intent(max_delegations=3, limits={"max_concurrent": 2, "max_paid_worker_calls": 2},
                               expansion_headroom={"delegations": 1})
        intent["delegation_matrix"]["delegated_expansion"] = False
        with self.assertRaisesRegex(DeliveryContractError, "delegated_expansion"):
            build_shaper_contract("demo", self.sources(), intent)
        intent = shaper_intent()
        intent["delegation_matrix"]["delegated_expansion"] = True
        with self.assertRaisesRegex(DeliveryContractError, "delegated_expansion"):
            build_shaper_contract("demo", self.sources(), intent)

    def test_sealed_headroom_mutation_is_refused(self):
        intent = shaper_intent(max_delegations=3, limits={"max_concurrent": 2, "max_paid_worker_calls": 2},
                               expansion_headroom={"delegations": 1})
        charter = build_delivery_charter(build_shaper_contract("demo", self.sources(), intent))
        charter["limits"]["expansion_headroom"]["delegations"] = 4
        charter["digest"] = digest({key: value for key, value in charter.items() if key != "digest"})
        with self.assertRaisesRegex(DeliveryContractError, "runner ceiling"):
            validate_delivery_charter(charter)

    def test_v2_contract_and_charter_remain_readable_without_headroom(self):
        shaper = build_shaper_contract("demo", self.sources(), shaper_intent())
        charter = build_delivery_charter(shaper)
        shaper["version"] = 2
        del shaper["expansion_headroom"]
        shaper["digest"] = digest({key: value for key, value in shaper.items() if key != "digest"})
        validate_shaper_contract(shaper)
        charter["charter_version"] = 2
        charter["shaper_contract"] = {**charter["shaper_contract"], "version": 2}
        del charter["limits"]["expansion_headroom"]
        charter["digest"] = digest({key: value for key, value in charter.items() if key != "digest"})
        validate_delivery_charter(charter)
        shaper["delegation_matrix"] = {**shaper["delegation_matrix"], "delegated_expansion": True}
        shaper["digest"] = digest({key: value for key, value in shaper.items() if key != "digest"})
        with self.assertRaisesRegex(DeliveryContractError, "pre-expansion"):
            validate_shaper_contract(shaper)

    def test_v1_contract_and_charter_remain_readable(self):
        shaper = build_shaper_contract("demo", self.sources(), shaper_intent())
        shaper["version"] = 1
        del shaper["max_verifier_calls"]
        del shaper["expansion_headroom"]
        shaper["digest"] = digest({key: value for key, value in shaper.items() if key != "digest"})
        validate_shaper_contract(shaper)
        charter = build_delivery_charter(build_shaper_contract("demo", self.sources(), shaper_intent()))
        charter["charter_version"] = 1
        charter["shaper_contract"] = {**charter["shaper_contract"], "version": 1}
        del charter["limits"]["max_verifier_calls"]
        del charter["limits"]["expansion_headroom"]
        charter["digest"] = digest({key: value for key, value in charter.items() if key != "digest"})
        validate_delivery_charter(charter)

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
