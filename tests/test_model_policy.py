"""Contract tests for session-model configuration and adapter policy."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "cli"))

from model_policy import (  # noqa: E402
    ModelPolicyError,
    merge_session_model_profiles,
    resolve_session_profile,
    runtime_policy_for_agent,
)
from render import routing_hints_for  # noqa: E402


def _entry(**mapping: str) -> dict[str, str]:
    return {
        **mapping,
        "rationale": "Fixture suitability declaration.",
        "source": "https://example.invalid/model-fixture",
        "verified_at": "2026-09-07",
    }


def _manifest() -> dict:
    return {
        "model_tiers": {
            "mechanical": {
                "claude": {"model": "claude-haiku", "effort": "low"},
                "codex": {"model": "gpt-luna", "model_reasoning_effort": "low"},
            },
            "working": {
                "claude": {"model": "claude-sonnet", "effort": "medium"},
                "codex": {"model": "gpt-terra", "model_reasoning_effort": "medium"},
            },
            "judgment": {
                "claude": {"model": "claude-opus", "effort": "high"},
                "codex": {"model": "gpt-sol", "model_reasoning_effort": "high"},
            },
        },
        "session_model_profiles": {
            "mechanical": {
                "description": "Mechanical transformations.",
                "claude": _entry(tier="mechanical"),
                "codex": _entry(tier="mechanical"),
            },
            "working": {
                "description": "Bounded familiar work.",
                "claude": _entry(tier="working"),
                "codex": _entry(tier="working"),
            },
            "judgment": {
                "description": "Ambiguous architectural work.",
                "claude": _entry(tier="judgment"),
                "codex": _entry(tier="judgment"),
            },
            "demanding": {
                "description": "Unusually demanding unresolved work.",
                "claude": _entry(model="claude-demanding", effort="high"),
                "codex": _entry(model="gpt-astra", model_reasoning_effort="ultra"),
            },
        },
    }


class AgentPolicyResolutionTests(unittest.TestCase):
    def test_runtime_and_generic_overrides_win_in_established_order(self) -> None:
        manifest = _manifest()
        agent = {
            "name": "fixture",
            "model_tier": "working",
            "codex": {"model": "gpt-runtime", "model_reasoning_effort": "high"},
            "model": "gpt-generic",
            "model_reasoning_effort": "ultra",
        }

        self.assertEqual(
            runtime_policy_for_agent(manifest, "codex", agent),
            {"model": "gpt-generic", "model_reasoning_effort": "ultra"},
        )
        self.assertEqual(
            runtime_policy_for_agent(manifest, "claude", agent),
            {"model": "gpt-generic", "effort": "medium", "model_reasoning_effort": "ultra"},
        )

    def test_routing_hints_show_the_same_effective_override_as_generated_policy(self) -> None:
        manifest = _manifest()
        agents = [{
            "name": "fixture",
            "model_tier": "working",
            "claude": {"model": "claude-runtime", "effort": "high"},
            "codex": {"model": "gpt-runtime", "model_reasoning_effort": "ultra"},
        }]

        for runtime, expected_model, expected_effort in (
            ("claude", "claude-runtime", "high"),
            ("codex", "gpt-runtime", "ultra"),
        ):
            policy = runtime_policy_for_agent(manifest, runtime, agents[0])
            self.assertEqual(policy["model"], expected_model)
            self.assertEqual(
                policy.get("model_reasoning_effort", policy.get("effort")), expected_effort
            )
            self.assertIn(
                f"| fixture | working | {expected_model} | {expected_effort} |",
                routing_hints_for(runtime, agents, manifest),
            )

    def test_routing_hints_use_each_runtime_native_effort_when_generic_codex_effort_exists(self) -> None:
        manifest = _manifest()
        agents = [{
            "name": "fixture",
            "model_tier": "working",
            "model": "generic-model",
            "model_reasoning_effort": "ultra",
        }]

        claude_policy = runtime_policy_for_agent(manifest, "claude", agents[0])
        codex_policy = runtime_policy_for_agent(manifest, "codex", agents[0])
        self.assertEqual(claude_policy["effort"], "medium")
        self.assertEqual(claude_policy["model_reasoning_effort"], "ultra")
        self.assertEqual(codex_policy["model_reasoning_effort"], "ultra")
        self.assertIn(
            "| fixture | working | generic-model | medium |",
            routing_hints_for("claude", agents, manifest),
        )
        self.assertIn(
            "| fixture | working | generic-model | ultra |",
            routing_hints_for("codex", agents, manifest),
        )


class SessionProfileTests(unittest.TestCase):
    def test_user_runtime_entry_replaces_the_framework_entry_atomically(self) -> None:
        framework = _manifest()
        merged = merge_session_model_profiles(
            framework,
            {"session_model_profiles": {"demanding": {
                "codex": _entry(model="gpt-user-astra", model_reasoning_effort="high"),
            }}},
            framework_source="framework.toml",
            user_source="user.toml",
        )
        manifest = {**framework, "session_model_profiles": merged}

        codex = resolve_session_profile(manifest, "codex", "demanding")
        claude = resolve_session_profile(manifest, "claude", "demanding")
        self.assertEqual(codex["status"], "resolved")
        self.assertEqual(codex["model"], "gpt-user-astra")
        self.assertEqual(codex["effort"], "high")
        self.assertEqual(codex["provenance"]["profile"], "user.toml")
        self.assertEqual(claude["model"], "claude-demanding")
        self.assertEqual(claude["provenance"]["profile"], "framework.toml")

    def test_disabled_mapping_is_ineligible_without_a_fallback_model(self) -> None:
        framework = _manifest()
        merged = merge_session_model_profiles(
            framework,
            {"session_model_profiles": {"demanding": {"codex": {"disabled": True}}}},
            framework_source="framework.toml",
            user_source="user.toml",
        )

        resolved = resolve_session_profile(
            {**framework, "session_model_profiles": merged}, "codex", "demanding"
        )
        self.assertEqual(resolved["status"], "disabled")
        self.assertIsNone(resolved["model"])
        self.assertIsNone(resolved["effort"])
        self.assertEqual(resolved["reason_codes"], ["mapping_disabled"])

    def test_invalid_mapping_has_no_substituted_native_effort(self) -> None:
        manifest = _manifest()
        manifest["session_model_profiles"]["demanding"]["codex"] = _entry(
            model="gpt-invalid", effort="high"
        )

        resolved = resolve_session_profile(manifest, "codex", "demanding")
        self.assertEqual(resolved["status"], "invalid")
        self.assertIsNone(resolved["model"])
        self.assertIsNone(resolved["effort"])
        self.assertEqual(resolved["reason_codes"], ["invalid_mapping"])

    def test_unknown_profile_is_rejected_when_merging_and_invalid_when_resolving(self) -> None:
        with self.assertRaisesRegex(ModelPolicyError, "unknown session model profile"):
            merge_session_model_profiles(
                _manifest(),
                {"session_model_profiles": {"faster": {}}},
                framework_source="framework.toml",
                user_source="user.toml",
            )

        resolved = resolve_session_profile(_manifest(), "codex", "faster")
        self.assertEqual(resolved["status"], "invalid")
        self.assertEqual(resolved["reason_codes"], ["unknown_profile"])


if __name__ == "__main__":
    unittest.main()
