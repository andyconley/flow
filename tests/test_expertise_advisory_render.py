"""The coordinator expertise protocol is the same in generated clients."""

from pathlib import Path
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli"))
import render
import sync


class AdvisoryRenderTests(unittest.TestCase):
    def test_dispatching_commands_share_one_protocol_in_both_clients(self):
        manifest = tomllib.loads((ROOT / "scaffolds/default/flow.toml").read_text())
        commands = {row["name"]: row for row in manifest["codex"]["commands"]}
        dispatchers = {
            name for name, row in commands.items()
            if "## Composition" in (ROOT / "scaffolds/default" / row["source"]).read_text()
        }
        self.assertEqual(dispatchers, {
            "flow-define", "flow-solution", "flow-plan", "flow-implement",
            "flow-review", "flow-archive", "flow-init-project",
        })
        for name in dispatchers | {"flow-scout", "flow-resume"}:
            with self.subTest(name=name):
                body = (ROOT / "scaffolds/default" / commands[name]["source"]).read_text()
                claude = render.render_skill_from_command(
                    {"name": name, "description": "test", "source": commands[name]["source"], "_body": body}, {},
                )
                codex = render.render_codex_skill(name, "test", "source", body)
                shared = render.expertise_advisory_guidance(name).rstrip()
                self.assertIn(shared, claude)
                self.assertIn(shared, codex)
                self.assertEqual(claude.count("## Advisory expertise at role dispatch"), 1)
                self.assertEqual(codex.count("## Advisory expertise at role dispatch"), 1)
                for role in render.EXPERTISE_ADVISORY_ROLES:
                    self.assertIn(role, shared)
        self.assertEqual(render.expertise_advisory_guidance("flow-help"), "")

    def test_user_overlay_can_disable_advisory_generation_for_rollback(self):
        with tempfile.TemporaryDirectory() as temporary:
            user = Path(temporary)
            (user / "flow.toml").write_text("[expertise_advisory]\nenabled = false\n")
            with patch.object(sync, "USER_OVERLAY_DIR", user):
                _, manifest = sync.merge_user_overlay(ROOT / "scaffolds/default")
            self.assertFalse(manifest["expertise_advisory"]["enabled"])
            body = (ROOT / "scaffolds/default/commands/flow-plan.md").read_text()
            codex = render.render_codex_skill("flow-plan", "test", "source", body,
                                              advisory_enabled=manifest["expertise_advisory"]["enabled"])
            self.assertNotIn("## Advisory expertise at role dispatch", codex)

    def test_six_queried_roles_remain_composed(self):
        manifest = tomllib.loads((ROOT / "scaffolds/default/flow.toml").read_text())
        roles = {row["name"]: row for row in manifest["agents"]}
        for role in render.EXPERTISE_ADVISORY_ROLES:
            with self.subTest(role=role):
                self.assertEqual(roles[role]["generation_mode"], "composed")


if __name__ == "__main__":
    unittest.main()
