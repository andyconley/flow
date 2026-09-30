from __future__ import annotations

import itertools
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli"))

from provider_selection import (  # noqa: E402
    SelectionPolicyError,
    canonical_bytes,
    merge_selection_policy,
    select_candidate,
)
from flowtoml import parse_simple_toml  # noqa: E402


def candidate(candidate_id: str, provider: str, family: str, **overrides) -> dict:
    value = {
        "candidate_id": candidate_id,
        "provider": provider,
        "model": f"{candidate_id}-model",
        "provider_family": family,
        "tier": "judgment",
        "locality": "local" if provider == "ollama" else "hosted",
        "operations": ["manage", "read", "edit", "verify", "collect"],
        "capabilities": ["structured_output", "structured_edit"],
        "cost_class": 0 if provider == "ollama" else 1,
        "enabled": True,
        "max_input_bytes": 100_000,
        "max_output_bytes": 20_000,
        "max_context_tokens": 32_000,
    }
    value.update(overrides)
    return value


CATALOG = [
    candidate("local", "ollama", "local"),
    candidate("claude", "claude", "anthropic"),
    candidate("codex", "codex", "openai"),
]
READY = [{"candidate_id": item["candidate_id"], "state": "ready"} for item in CATALOG]
REQUIREMENTS = {
    "operation": "edit",
    "minimum_tier": "working",
    "required_capabilities": ["structured_edit"],
    "locality": "any",
    "input_bytes": 1_000,
    "output_bytes": 500,
    "context_tokens": 4_000,
}


class ProviderSelectionTests(unittest.TestCase):
    def test_fallback_toml_parser_accepts_bounded_scalar_arrays(self) -> None:
        parsed = parse_simple_toml('[provider_selection]\nprovider_order = ["ollama", "claude", "codex"]\n')
        self.assertEqual(parsed["provider_selection"]["provider_order"],
                         ["ollama", "claude", "codex"])

    def test_identical_inputs_are_byte_stable_and_input_order_independent(self) -> None:
        policy = merge_selection_policy({"provider_order": ["ollama", "claude", "codex"]})
        decisions = []
        for catalog in itertools.permutations(CATALOG):
            availability = list(reversed(READY))
            decisions.append(canonical_bytes(select_candidate(REQUIREMENTS, policy, catalog, availability)))
        self.assertEqual(len(set(decisions)), 1)
        self.assertEqual(select_candidate(REQUIREMENTS, policy, CATALOG, READY)["selected_candidate_id"], "local")

    def test_hosted_order_applies_after_ineligible_local_candidate(self) -> None:
        policy = merge_selection_policy({"provider_order": ["ollama", "claude", "codex"]})
        availability = [
            {"candidate_id": "local", "state": "unavailable"},
            {"candidate_id": "claude", "state": "ready"},
            {"candidate_id": "codex", "state": "ready"},
        ]
        decision = select_candidate(REQUIREMENTS, policy, CATALOG, availability)
        self.assertEqual(decision["selected_candidate_id"], "claude")
        self.assertEqual(decision["exclusions"], [
            {"candidate_id": "local", "reason_codes": ["availability_unavailable"]}
        ])

    def test_project_can_reorder_hosted_candidates_but_not_displace_local(self) -> None:
        policy = merge_selection_policy(
            {"provider_order": ["ollama", "claude", "codex"]}, None,
            {"provider_order": ["ollama", "codex", "claude"]},
        )
        decision = select_candidate(REQUIREMENTS, policy, CATALOG, READY,
                                    prior_no_send_failures=["local"])
        self.assertEqual(decision["selected_candidate_id"], "codex")
        with self.assertRaisesRegex(SelectionPolicyError, "keep ollama first"):
            merge_selection_policy({}, None, {"provider_order": ["codex", "ollama", "claude"]})

    def test_lower_layers_only_narrow_allowlists_disables_and_caps(self) -> None:
        policy = merge_selection_policy(
            {"allowed_candidates": ["local", "claude", "codex"], "max_input_bytes": 10_000},
            {"allowed_candidates": ["local", "claude"], "disabled_candidates": ["claude"],
             "max_input_bytes": 8_000},
            {"allowed_candidates": ["local", "claude", "codex"], "max_input_bytes": 12_000},
        )
        self.assertEqual(policy["allowed_candidates"], ["claude", "local"])
        self.assertEqual(policy["disabled_candidates"], ["claude"])
        self.assertEqual(policy["max_input_bytes"], 8_000)
        self.assertEqual(policy["provenance"]["max_input_bytes"],
                         ["framework", "administrator", "project"])

    def test_family_filter_is_explanatory_and_fails_closed(self) -> None:
        policy = merge_selection_policy({})
        decision = select_candidate(REQUIREMENTS, policy, CATALOG, READY,
                                    excluded_families=["local", "anthropic", "openai"])
        self.assertIsNone(decision["selected_binding"])
        self.assertEqual(
            {reason for item in decision["exclusions"] for reason in item["reason_codes"]},
            {"provider_family_conflict"},
        )

    def test_waiver_requires_explicit_run_approval(self) -> None:
        with self.assertRaisesRegex(SelectionPolicyError, "run-local only"):
            merge_selection_policy({"independence_waiver": {"approved": True, "approval_digest": "x"}})
        policy = merge_selection_policy({}, None, None, {
            "independence_waiver": {"approved": True, "approval_digest": "abc"}
        })
        self.assertEqual(policy["provenance"]["independence_waiver"], "run")


if __name__ == "__main__":
    unittest.main()
