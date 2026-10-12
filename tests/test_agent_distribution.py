"""Offline install/update contracts in isolated homes; never call a model."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli"))
from render import parse_frontmatter, render_codex_agent
from openhands_runtime import probe


class AgentDistributionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        (self.home / ".flow").mkdir()
        (self.home / ".flow/source").symlink_to(ROOT)
        self.env = {**os.environ, "HOME": str(self.home), "PYTHONDONTWRITEBYTECODE": "1",
                    "NO_COLOR": "1", "LITELLM_LOCAL_MODEL_COST_MAP": "True", "OPENHANDS_SUPPRESS_BANNER": "1"}

    def sync(self, target, check=False, okay=True):
        result = subprocess.run([sys.executable, str(ROOT / "cli/flow.py"), "sync", target,
                                 "--user", *(["--check"] if check else [])], env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0 if okay else 1, result.stdout + result.stderr)
        return result

    def test_all_formats_symlinks_discovery_and_idempotent_updates(self):
        for target, directory, suffix in (("claude", ".claude/agents", "md"),
                                           ("codex", ".codex/agents", "toml"),
                                           ("openhands", ".agents/agents", "md")):
            self.sync(target)
            agents = sorted((self.home / directory).glob(f"*.{suffix}"))
            self.assertEqual(len(agents), 13)
            for agent in agents:
                self.assertTrue(agent.is_symlink())
                self.assertTrue(agent.resolve().is_relative_to(self.home / ".flow/generated/agents"))
                if target == "codex":
                    role = tomllib.loads(agent.read_text())
                    self.assertEqual(role["name"], agent.stem)
                    self.assertTrue(role["description"])
                    self.assertTrue(role["developer_instructions"])
                    self.assertNotIn("tools", role)
                else:
                    metadata, prompt = parse_frontmatter(agent.read_text())
                    self.assertEqual(metadata["name"], agent.stem)
                    self.assertTrue(prompt)
            report = json.loads((self.home / f".flow/generated/agents/{target}/translation-report.json").read_text())
            self.assertEqual(len(report), 13)
            if target != "claude":
                self.assertIn("tools", report[0]["unsupported_source_fields"])
            self.sync(target, check=True)
            self.assertIn("no changes needed", self.sync(target).stdout)

    def test_bootstrap_release_install_and_repeat_are_offline_and_isolated(self):
        for _ in range(2):
            result = subprocess.run(["bash", str(ROOT / "install-flow.sh"), "--release"],
                env={**self.env, "FLOW_PYTHON": sys.executable}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.home / ".flow/source").is_symlink())
        for directory, suffix in ((".claude/agents", "md"), (".codex/agents", "toml"), (".agents/agents", "md")):
            agents = list((self.home / directory).glob(f"*.{suffix}"))
            self.assertEqual(len(agents), 13)
            self.assertTrue(all(agent.is_symlink() for agent in agents))

    def test_managed_copy_fallback_is_idempotent(self):
        import sync
        from unittest.mock import patch
        from contextlib import redirect_stdout
        import io
        with patch.object(sync, "USER_OVERLAY_DIR", self.home / ".flow/user"):
            _, manifest = sync.merge_user_overlay(ROOT / "scaffolds/default")
            desired, entries, mergeable = sync.desired_outputs_for_target("openhands", self.home,
                ROOT / "scaffolds/default", manifest, sync.manifest_ref_for())
        links = {self.home / e["path"]: self.home / e["link"] for e in entries if "link" in e}
        with patch.object(Path, "symlink_to", side_effect=OSError("unsupported")), redirect_stdout(io.StringIO()):
            self.assertEqual(sync.sync_outputs(self.home, "openhands", desired, set(), mergeable,
                check=False, agent_links=links), 0)
        self.assertTrue(all(path.is_file() and not path.is_symlink() for path in links))
        self.sync("openhands", check=True)
        self.assertIn("no changes needed", self.sync("openhands").stdout)

    def test_edited_generated_skill_is_preserved(self):
        self.sync("codex")
        path = self.home / ".agents/skills/flow-boot/SKILL.md"
        path.write_text(path.read_text() + "\nMy edit\n")
        self.sync("codex", okay=False)
        self.assertIn("My edit", path.read_text())

    def test_legacy_differing_agent_is_preserved_until_reviewed(self):
        self.sync("codex")
        path = self.home / ".codex/agents/architect.toml"
        manifest_path = self.home / ".codex/flow.managed.toml"
        # Reproduce a v2 manifest without per-file content hashes.
        manifest_path.write_text("\n".join(line for line in manifest_path.read_text().splitlines()
                                                if not line.startswith(("sha256 =", "link ="))))
        original = path.read_text()
        path.unlink()
        path.write_text(original + "\n# legacy custom edit\n")
        self.sync("codex", okay=False)
        self.assertIn("legacy custom edit", path.read_text())

    def test_missing_owned_backing_is_repaired(self):
        self.sync("openhands")
        path = self.home / ".agents/agents/architect.md"
        path.resolve().unlink()
        self.sync("openhands", check=True, okay=False)
        self.sync("openhands")
        self.assertTrue(path.is_file())
        self.sync("openhands", check=True)

    def test_custom_content_and_skill_survive(self):
        agent = self.home / ".codex/agents/mine.toml"
        agent.parent.mkdir(parents=True)
        agent.write_text('name="mine"\ndescription="custom"\ndeveloper_instructions="custom"\n')
        skill = self.home / ".agents/skills/custom/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("custom skill")
        self.sync("codex")
        self.sync("codex")
        self.assertIn('name="mine"', agent.read_text())
        self.assertEqual(skill.read_text(), "custom skill")

    def test_collision_and_edited_owned_definition_are_preserved(self):
        path = self.home / ".codex/agents/architect.toml"
        path.parent.mkdir(parents=True)
        path.write_text("custom agent")
        self.sync("codex", okay=False)
        self.assertEqual(path.read_text(), "custom agent")
        path.unlink()
        self.sync("codex")
        path.write_text(path.read_text() + "\n# user edit\n")
        self.sync("codex", okay=False)
        self.assertIn("user edit", path.read_text())

    def test_replaced_and_dangling_links_do_not_write_through(self):
        self.sync("claude")
        path = self.home / ".claude/agents/architect.md"
        outside = self.home / "outside.md"
        outside.write_text(path.read_text())
        path.unlink()
        path.symlink_to(outside)
        self.sync("claude", okay=False)
        self.assertEqual(path.resolve(), outside)
        path.unlink()
        path.symlink_to(self.home / "absent")
        self.sync("claude", okay=False)
        self.assertFalse((self.home / "absent").exists())

    def test_overlay_source_update_and_stale_edit_preservation(self):
        overlay = self.home / ".flow/user"
        overlay.mkdir()
        (overlay / "flow.toml").write_text('[[agents]]\nname="mine"\nsource="mine.md"\n')
        source = overlay / "mine.md"
        source.write_text('---\nname: mine\ndescription: Custom specialist\n---\nFirst instructions\n')
        self.sync("openhands")
        target = self.home / ".agents/agents/mine.md"
        source.write_text(source.read_text().replace("First", "Second"))
        self.sync("openhands")
        self.assertIn("Second instructions", target.read_text())
        target.write_text(target.read_text() + "\nUser edit\n")
        (overlay / "flow.toml").write_text("")
        self.sync("openhands", okay=False)
        self.assertIn("User edit", target.read_text())

    def test_codex_instructions_escape_backslashes_quotes_and_newlines(self):
        body = '---\nname: sample\ndescription: sample\n---\nC:\\new\\test and """quotes"""\n'
        result = tomllib.loads(render_codex_agent("sample", "sample.md", body, {}))
        self.assertEqual(result["developer_instructions"], body.split("---\n", 2)[-1])

    @unittest.skipUnless(probe()["ready"], "pinned SDK unavailable")
    def test_sdk_discovers_generated_roles_and_constructs_every_local_factory(self):
        self.sync("openhands")
        code = '''
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1] + "/cli")
from openhands.sdk.subagent import load_project_agents, get_agent_factory
from openhands_config import select
from openhands_runtime import build_agent
root = Path(os.environ["HOME"])
assert len(load_project_agents(root)) == 13
for definition in load_project_agents(root):
    assert definition.description and definition.system_prompt
(root / ".flow/runtime.toml").write_text('default_profile="local"\\n[profiles.local]\\nkind="local"\\nmodel="openai/offline-test"\\nbase_url="http://localhost:8000/v1"\\n')
agent = build_agent(select(root, "implement"), root)
roster = agent.agent_context.system_message_suffix.split("Configured specialist roster:\\n")[1].splitlines()
assert len(roster) == 12, roster
for line in roster:
    role, key = line.split(": use task subagent_type=")
    child = get_agent_factory(key).factory_func(agent.llm)
    assert child.llm.model == agent.llm.model
    assert child.agent_context.system_message_suffix
    assert child.tools
    assert not any(tool.name == "task" for tool in child.tools)
print("13 SDK definitions discovered; 12 stock delegate factories constructed")
'''
        result = subprocess.run([sys.executable, "-c", code, str(ROOT)], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
