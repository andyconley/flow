from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli"))

from delivery_selection import compute_binding  # noqa: E402
from execution_contracts import ContractError, digest, validate_envelope  # noqa: E402
from provider_selection import merge_selection_policy  # noqa: E402
from selection_authority import effective_family_exclusions, seal_selection_authority  # noqa: E402
from tests.test_delivery_selection import _envelope  # noqa: E402


def _reseal(envelope: dict) -> None:
    inputs = envelope["selection_inputs"]
    envelope["selection_input_digests"] = {key: digest(value) for key, value in inputs.items()}
    old = envelope["selection_authority"]
    envelope["selection_authority"] = seal_selection_authority(
        work_id=envelope["work_id"], attempt_id=envelope["attempt_id"],
        charter_digest=envelope["charter_digest"], manifest_digest=envelope["manifest_digest"],
        generation=old["generation"], sealed_at=old["sealed_at"],
        logical_assignments=envelope["logical_assignments"], policy=inputs["policy"],
        catalog=inputs["catalog"], availability=inputs["availability"],
        independence_constraints=old["independence_constraints"],
        prior_authority_digest=old["prior_authority_digest"],
    )


class SelectionAuthorityTests(unittest.TestCase):
    def test_closed_flow_authority_accepts_normalized_inputs(self) -> None:
        envelope = _envelope(excluded_families=["local", "anthropic"])
        validate_envelope(envelope)
        self.assertEqual(compute_binding(envelope, "verifier")["selected_candidate_id"], "codex")

    def test_credential_bearing_availability_is_rejected_even_when_resealed(self) -> None:
        envelope = _envelope()
        envelope["selection_inputs"]["availability"][0]["authorization"] = "secret-canary"
        _reseal(envelope)
        with self.assertRaisesRegex(ContractError, "availability record fields"):
            validate_envelope(envelope)

    def test_unknown_requirement_enum_is_rejected_even_when_resealed(self) -> None:
        envelope = _envelope()
        envelope["logical_assignments"][0]["requirements"]["minimum_tier"] = "whatever"
        _reseal(envelope)
        with self.assertRaisesRegex(ContractError, "minimum_tier is unsupported"):
            validate_envelope(envelope)

    def test_duplicate_or_incomplete_availability_is_rejected(self) -> None:
        envelope = _envelope()
        envelope["selection_inputs"]["availability"].append(
            copy.deepcopy(envelope["selection_inputs"]["availability"][0])
        )
        _reseal(envelope)
        with self.assertRaisesRegex(ContractError, "availability identities must be unique"):
            validate_envelope(envelope)

        envelope = _envelope()
        envelope["selection_inputs"]["availability"].pop()
        _reseal(envelope)
        with self.assertRaisesRegex(ContractError, "exactly one record per candidate"):
            validate_envelope(envelope)

    def test_impossible_or_excessive_freshness_window_is_rejected(self) -> None:
        envelope = _envelope()
        record = envelope["selection_inputs"]["availability"][0]
        record["expires_at"] = record["observed_at"]
        _reseal(envelope)
        with self.assertRaisesRegex(ContractError, "freshness window is invalid"):
            validate_envelope(envelope)

        envelope = _envelope()
        envelope["selection_inputs"]["availability"][0]["expires_at"] = "2026-09-29T12:10:00Z"
        _reseal(envelope)
        with self.assertRaisesRegex(ContractError, "freshness window is invalid"):
            validate_envelope(envelope)

    def test_waiver_removes_only_exact_approved_family(self) -> None:
        envelope = _envelope(excluded_families=["local", "anthropic"], waiver=True)
        waiver = envelope["selection_inputs"]["policy"]["independence_waiver"]
        waiver["waived_provider_families"] = ["local"]
        waiver["approval_digest"] = digest({key: value for key, value in waiver.items()
                                             if key != "approval_digest"})
        base = merge_selection_policy({})
        envelope["selection_inputs"]["policy"] = merge_selection_policy(
            {}, None, None, {"independence_waiver": waiver}
        )
        self.assertEqual(waiver["prior_policy_digest"], base["policy_digest"])
        _reseal(envelope)
        validate_envelope(envelope)
        self.assertEqual(effective_family_exclusions(envelope, "verifier"), ["anthropic"])

    def test_cross_assignment_or_stale_successor_waiver_is_rejected(self) -> None:
        envelope = _envelope(excluded_families=["local"], waiver=True)
        waiver = envelope["selection_inputs"]["policy"]["independence_waiver"]
        waiver["assignment_id"] = "producer"
        waiver["approval_digest"] = digest({key: value for key, value in waiver.items()
                                             if key != "approval_digest"})
        envelope["selection_inputs"]["policy"] = merge_selection_policy(
            {}, None, None, {"independence_waiver": waiver}
        )
        _reseal(envelope)
        with self.assertRaisesRegex(ContractError, "family scope mismatch"):
            validate_envelope(envelope)

        envelope = _envelope(excluded_families=["local"], waiver=True)
        envelope["selection_inputs"]["availability"][0]["evidence_code"] = "adapter_ready"
        _reseal(envelope)
        with self.assertRaisesRegex(ContractError, "successor authority binding mismatch"):
            validate_envelope(envelope)


if __name__ == "__main__":
    unittest.main()
