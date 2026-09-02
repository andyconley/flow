"""Contract tests for Flow's semantic agent-capability resolver.

These tests intentionally stop at deterministic manifest resolution.  They do
not make a network call or claim that a host honors a rendered web setting.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "cli"))
import agent_capabilities  # noqa: E402
sys.path.pop(0)


class AgentCapabilityResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.framework = {
            "agent_capabilities": {
                "web_research": {
                    "default": True,
                    "authorization": "explicit-task-or-brief",
                }
            }
        }
        self.agents = [
            {"name": "architect"},
            {"name": "security-reviewer"},
            {"name": "support-lead"},
        ]

    def resolve(self, framework: dict | None = None, overlay: dict | None = None, agents=None):
        return agent_capabilities.resolve_agent_capabilities(
            framework if framework is not None else self.framework,
            overlay if overlay is not None else {},
            self.agents if agents is None else agents,
            framework_source="framework flow.toml",
            overlay_source="user flow.toml",
        )

    def assert_invalid(self, framework: dict | None = None, overlay: dict | None = None, agents=None) -> str:
        with self.assertRaises(agent_capabilities.CapabilityPolicyError) as raised:
            self.resolve(framework, overlay, agents)
        return str(raised.exception)

    def test_default_grants_web_research_to_every_final_inventory_agent(self) -> None:
        decisions = self.resolve()

        self.assertEqual(set(decisions), {agent["name"] for agent in self.agents})
        self.assertTrue(all(decision["web_research"].enabled for decision in decisions.values()))

    def test_framework_opt_out_requires_rationale_and_overrides_default(self) -> None:
        framework = {
            **self.framework,
            "agent_capability_overrides": [{
                "agent": "security-reviewer",
                "capability": "web_research",
                "enabled": False,
                "rationale": "This role is intentionally local-only.",
            }],
        }

        decisions = self.resolve(framework)

        self.assertFalse(decisions["security-reviewer"]["web_research"].enabled)
        self.assertTrue(decisions["architect"]["web_research"].enabled)

    def test_missing_or_blank_opt_out_rationale_is_rejected(self) -> None:
        for rationale in (None, "", " \t "):
            with self.subTest(rationale=rationale):
                override = {
                    "agent": "security-reviewer",
                    "capability": "web_research",
                    "enabled": False,
                }
                if rationale is not None:
                    override["rationale"] = rationale
                framework = {**self.framework, "agent_capability_overrides": [override]}

                message = self.assert_invalid(framework)

                self.assertIn("security-reviewer", message)
                self.assertIn("rationale", message.lower())

    def test_overlay_omission_preserves_framework_denial_after_agent_replacement(self) -> None:
        framework = {
            **self.framework,
            "agent_capability_overrides": [{
                "agent": "security-reviewer",
                "capability": "web_research",
                "enabled": False,
                "rationale": "Framework local-only policy.",
            }],
        }
        final_agents = [
            {"name": "architect"},
            {"name": "security-reviewer", "source": "agents/custom-security.md"},
            {"name": "support-lead"},
        ]

        decisions = self.resolve(framework, {}, final_agents)

        self.assertFalse(decisions["security-reviewer"]["web_research"].enabled)

    def test_overlay_false_replaces_enabled_default_with_documented_denial(self) -> None:
        overlay = {"agent_capability_overrides": [{
            "agent": "support-lead",
            "capability": "web_research",
            "enabled": False,
            "rationale": "Local corpus validation only.",
        }]}

        decisions = self.resolve(overlay=overlay)

        self.assertFalse(decisions["support-lead"]["web_research"].enabled)

    def test_overlay_reenable_requires_lower_layer_denial_and_rationale(self) -> None:
        framework = {
            **self.framework,
            "agent_capability_overrides": [{
                "agent": "security-reviewer",
                "capability": "web_research",
                "enabled": False,
                "rationale": "Framework local-only policy.",
            }],
        }
        overlay = {"agent_capability_overrides": [{
            "agent": "security-reviewer",
            "capability": "web_research",
            "enabled": True,
            "rationale": "This installation assigns explicit external-policy research.",
        }]}

        decisions = self.resolve(framework, overlay)

        self.assertTrue(decisions["security-reviewer"]["web_research"].enabled)

    def test_redundant_overlay_enable_is_rejected(self) -> None:
        overlay = {"agent_capability_overrides": [{
            "agent": "architect",
            "capability": "web_research",
            "enabled": True,
            "rationale": "Redundant and should not hide the default.",
        }]}

        message = self.assert_invalid(overlay=overlay)

        self.assertIn("architect", message)
        self.assertIn("lower-layer denial", message.lower())

    def test_overlay_cannot_redefine_framework_capability_catalog(self) -> None:
        overlay = {
            "agent_capabilities": {
                "web_research": {
                    "default": False,
                    "authorization": "explicit-task-or-brief",
                }
            }
        }

        message = self.assert_invalid(overlay=overlay)

        self.assertIn("overlay", message.lower())
        self.assertIn("catalog", message.lower())

    def test_invalid_schema_duplicate_or_unknown_identity_is_rejected(self) -> None:
        cases = {
            "non_boolean_default": ({"agent_capabilities": {"web_research": {"default": "true", "authorization": "explicit-task-or-brief"}}}, {}),
            "unknown_authorization": ({"agent_capabilities": {"web_research": {"default": True, "authorization": "anything-goes"}}}, {}),
            "unknown_capability": (self.framework, {"agent_capability_overrides": [{"agent": "architect", "capability": "network", "enabled": False, "rationale": "Not supported."}]}),
            "unknown_agent": (self.framework, {"agent_capability_overrides": [{"agent": "missing-agent", "capability": "web_research", "enabled": False, "rationale": "Not in final inventory."}]}),
            "duplicate_key": ({**self.framework, "agent_capability_overrides": [
                {"agent": "architect", "capability": "web_research", "enabled": False, "rationale": "One."},
                {"agent": "architect", "capability": "web_research", "enabled": False, "rationale": "Two."},
            ]}, {}),
        }
        for label, (framework, overlay) in cases.items():
            with self.subTest(label=label):
                self.assert_invalid(framework, overlay)


if __name__ == "__main__":
    unittest.main()
