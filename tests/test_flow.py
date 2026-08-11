import json
import os
import stat
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FLOW_CLI = REPO_ROOT / "cli" / "flow.py"
INSTALL_SCRIPT = REPO_ROOT / "install-flow.sh"
BOOTSTRAP_INSTALL_SCRIPT = REPO_ROOT / "install.sh"


def _clean_env(home: Path | None = None) -> dict[str, str]:
    """Return a subprocess env that won't pull ANSI color into captured stdout.

    Python 3.14's argparse emits ANSI codes when FORCE_COLOR is set; NO_COLOR
    suppresses them. Tests assert on plain text, so we standardize.
    """
    env = os.environ.copy()
    env.pop("FORCE_COLOR", None)
    env["NO_COLOR"] = "1"
    if home is not None:
        env["HOME"] = str(home)
    return env


class FlowCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.repo = Path(self._tempdir.name)
        (self.repo / ".git").mkdir()
        self._fake_home: Path | None = None

    def tearDown(self) -> None:
        self._tempdir.cleanup()

    def run_flow(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(FLOW_CLI), *args],
            cwd=self.repo,
            text=True,
            capture_output=True,
            env=_clean_env(self._fake_home),
        )

    def assert_ok(self, result: subprocess.CompletedProcess[str]) -> None:
        if result.returncode != 0:
            self.fail(
                f"flow command failed with {result.returncode}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )

    def setup_project(self) -> None:
        self.assert_ok(self.run_flow("setup", "project"))

    def use_fake_home(self) -> Path:
        """Create a fake HOME with a flow source symlink. Subsequent run_flow calls use this HOME."""
        fake_home = self.repo / "fake_home"
        fake_home.mkdir()
        (fake_home / ".flow").mkdir()
        (fake_home / ".flow" / "source").symlink_to(REPO_ROOT)
        self._fake_home = fake_home
        return fake_home

    # ------------------------------------------------------------------
    # Two-mode install helpers
    # ------------------------------------------------------------------

    def _new_fake_home(self) -> Path:
        fake_home = self.repo / "fake_home"
        fake_home.mkdir()
        self._fake_home = fake_home
        return fake_home

    def _run_install_sh(self, *args: str) -> subprocess.CompletedProcess[str]:
        if self._fake_home is None:
            self._new_fake_home()
        result = subprocess.run(
            ["bash", str(INSTALL_SCRIPT), *args],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            env=_clean_env(self._fake_home),
        )
        return result

    def _make_fake_python_bin(self, include_compatible: bool) -> Path:
        fake_bin = self.repo / "fake-bin"
        fake_bin.mkdir(exist_ok=True)

        old_python = fake_bin / "python3"
        old_python.write_text(
            "#!/usr/bin/env bash\n"
            "if [[ \"${1:-}\" == \"-c\" ]]; then\n"
            "  echo \"3.9.6\"\n"
            "  exit 1\n"
            "fi\n"
            "echo \"Python 3.9.6\"\n"
            "exit 1\n"
        )
        old_python.chmod(old_python.stat().st_mode | stat.S_IXUSR)

        if include_compatible:
            if sys.version_info < (3, 10):
                self.skipTest("test host Python must be 3.10+ to simulate a compatible interpreter")
            good_name = f"python{sys.version_info.major}.{sys.version_info.minor}"
            good_python = fake_bin / good_name
            if good_python.exists() or good_python.is_symlink():
                good_python.unlink()
            good_python.symlink_to(sys.executable)

        return fake_bin

    def do_install_develop(self) -> Path:
        if self._fake_home is None:
            self._new_fake_home()
        result = self._run_install_sh("--develop")
        if result.returncode != 0:
            self.fail(f"install-flow.sh --develop failed:\n{result.stdout}\n{result.stderr}")
        return self._fake_home  # type: ignore[return-value]

    def do_install_release(self) -> Path:
        if self._fake_home is None:
            self._new_fake_home()
        result = self._run_install_sh("--release")
        if result.returncode != 0:
            self.fail(f"install-flow.sh --release failed:\n{result.stdout}\n{result.stderr}")
        return self._fake_home  # type: ignore[return-value]

    def make_fake_remote_with_tags(self, tags: list[str]) -> Path:
        """Build a bare git repo seeded from REPO_ROOT with the given tags.

        Returns the bare repo path; pass `file://<path>` as the `--remote` arg.
        Every tag points at the same single initial commit — sufficient for
        latest-tag selection and for `flow update` to clone a valid scaffold.
        """
        work = self.repo / "fake-remote-work"
        bare = self.repo / "fake-remote.git"
        shutil.copytree(
            REPO_ROOT,
            work,
            ignore=shutil.ignore_patterns(
                ".git", "*.pyc", "__pycache__", "fake_home", "fake-remote*"
            ),
        )
        env = _clean_env()
        env["GIT_AUTHOR_NAME"] = "test"
        env["GIT_AUTHOR_EMAIL"] = "test@example.com"
        env["GIT_COMMITTER_NAME"] = "test"
        env["GIT_COMMITTER_EMAIL"] = "test@example.com"
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=work, check=True, env=env)
        subprocess.run(["git", "add", "-A"], cwd=work, check=True, env=env)
        subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=work, check=True, env=env)
        for tag in tags:
            subprocess.run(["git", "tag", tag], cwd=work, check=True, env=env)
        subprocess.run(
            ["git", "clone", "--bare", "-q", str(work), str(bare)], check=True, env=env
        )
        return bare

    def test_setup_project_scaffolds_flow_manifest(self) -> None:
        self.setup_project()

        self.assertTrue((self.repo / ".flow" / "flow.toml").exists())
        self.assertTrue((self.repo / ".flow" / "commands" / "flow-plan.md").exists())
        self.assertTrue((self.repo / ".flow" / "agents" / "architect.md").exists())

    def test_sync_claude_generates_runtime_surface(self) -> None:
        self.setup_project()

        self.assert_ok(self.run_flow("sync", "claude"))

        skill_path = self.repo / ".claude" / "skills" / "flow-plan" / "SKILL.md"
        agent_path = self.repo / ".claude" / "agents" / "architect.md"
        tech_writer_path = self.repo / ".claude" / "agents" / "tech-writer.md"
        hook_path = self.repo / ".claude" / "hooks" / "flow-session-start.sh"
        settings_path = self.repo / ".claude" / "settings.json"
        managed_path = self.repo / ".claude" / "flow.managed.toml"

        self.assertTrue(skill_path.exists())
        self.assertTrue(agent_path.exists())
        self.assertTrue(tech_writer_path.exists())
        self.assertTrue(hook_path.exists())
        self.assertTrue(managed_path.exists())
        self.assertIn("disable-model-invocation: true", skill_path.read_text())
        self.assertIn("Flow Agent Routing", skill_path.read_text())
        self.assertIn("effort: medium", agent_path.read_text())
        self.assertIn("model: haiku", tech_writer_path.read_text())
        self.assertIn("effort: low", tech_writer_path.read_text())

        settings = json.loads(settings_path.read_text())
        session_groups = settings["hooks"]["SessionStart"]
        self.assertTrue(
            any(
                group["hooks"][0]["command"] == '"$CLAUDE_PROJECT_DIR"/.claude/hooks/flow-session-start.sh'
                for group in session_groups
            )
        )

    def test_sync_codex_generates_skill_runtime(self) -> None:
        self.setup_project()

        self.assert_ok(self.run_flow("sync", "codex"))

        skill_path = self.repo / ".agents" / "skills" / "flow-plan" / "SKILL.md"
        agent_path = self.repo / ".codex" / "agents" / "architect.toml"
        managed_path = self.repo / ".codex" / "flow.managed.toml"

        self.assertTrue(skill_path.exists())
        self.assertTrue(agent_path.exists())
        self.assertTrue(managed_path.exists())
        content = skill_path.read_text()
        self.assertIn("Generated by flow.", content)
        self.assertIn("Flow Agent Routing", content)
        self.assertTrue(content.startswith("---\nname: flow-plan\ndescription: "))
        agent_content = agent_path.read_text()
        self.assertIn('model = "gpt-5.6-sol"', agent_content)
        self.assertIn('model_reasoning_effort = "medium"', agent_content)
        tech_writer_content = (self.repo / ".codex" / "agents" / "tech-writer.toml").read_text()
        self.assertIn('model = "gpt-5.6-luna"', tech_writer_content)
        self.assertIn('model_reasoning_effort = "low"', tech_writer_content)

    def test_sync_check_detects_codex_drift(self) -> None:
        self.setup_project()
        self.assert_ok(self.run_flow("sync", "codex"))

        skill_path = self.repo / ".agents" / "skills" / "flow-plan" / "SKILL.md"
        skill_path.write_text(skill_path.read_text() + "\nmanual drift\n")

        result = self.run_flow("sync", "codex", "--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("codex sync check: drift detected", result.stdout)

    def test_doctor_reports_both_runtime_states(self) -> None:
        self.setup_project()
        self.assert_ok(self.run_flow("sync", "claude"))
        self.assert_ok(self.run_flow("sync", "codex"))

        result = self.run_flow("doctor")
        self.assert_ok(result)
        self.assertIn("claude drift:     clean", result.stdout)
        self.assertIn("codex drift:      clean", result.stdout)
        self.assertIn("agent policy:     ok (13/13 configured)", result.stdout)
        self.assertIn("codex agents:     ok (13/13 configured)", result.stdout)
        self.assertIn("claude smoke:", result.stdout)
        self.assertIn("codex smoke:", result.stdout)
        self.assertIn("-- user-level", result.stdout)
        self.assertIn("-- project:", result.stdout)

    def test_top_level_help_lists_core_commands_and_examples(self) -> None:
        result = self.run_flow("--help")
        self.assert_ok(result)
        self.assertIn("Portable AI workflow framework CLI.", result.stdout)
        self.assertIn("sync                generate runtime adapters from repo/.flow", result.stdout)
        self.assertIn("flow sync codex --check", result.stdout)

    def test_sync_help_describes_targets_and_examples(self) -> None:
        result = self.run_flow("sync", "--help")
        self.assert_ok(result)
        self.assertIn("Generate runtime-facing adapters", result.stdout)
        self.assertIn("--user", result.stdout)
        self.assertIn("claude  Generate .claude skills, agents, hooks, settings, and a managed manifest.", result.stdout)
        self.assertIn("codex   Generate .agents skills, .codex agents, and a .codex managed manifest.", result.stdout)
        self.assertIn("flow sync claude --user", result.stdout)

    def test_sync_claude_user_writes_to_user_home(self) -> None:
        fake_home = self.use_fake_home()
        result = self.run_flow("sync", "claude", "--user")
        self.assert_ok(result)

        skill_path = fake_home / ".claude" / "skills" / "flow-plan" / "SKILL.md"
        agent_path = fake_home / ".claude" / "agents" / "architect.md"
        hook_path = fake_home / ".claude" / "hooks" / "flow-session-start.sh"
        settings_path = fake_home / ".claude" / "settings.json"
        managed_path = fake_home / ".claude" / "flow.managed.toml"

        self.assertTrue(skill_path.exists())
        self.assertTrue(agent_path.exists())
        self.assertTrue(hook_path.exists())
        self.assertTrue(managed_path.exists())

        # User-mode hook command uses $HOME, not $CLAUDE_PROJECT_DIR
        settings = json.loads(settings_path.read_text())
        session_groups = settings["hooks"]["SessionStart"]
        self.assertTrue(
            any(
                group["hooks"][0]["command"] == '"$HOME"/.claude/hooks/flow-session-start.sh'
                for group in session_groups
            ),
            f"expected $HOME-based hook command in: {settings}",
        )

        # User-mode managed manifest references the scaffold path, not .flow/
        managed_text = managed_path.read_text()
        self.assertIn("~/.flow/source/scaffolds/default/commands/flow-plan.md", managed_text)

    def test_sync_codex_user_writes_to_user_home(self) -> None:
        fake_home = self.use_fake_home()
        result = self.run_flow("sync", "codex", "--user")
        self.assert_ok(result)

        skill_path = fake_home / ".agents" / "skills" / "flow-plan" / "SKILL.md"
        agent_path = fake_home / ".codex" / "agents" / "architect.toml"
        managed_path = fake_home / ".codex" / "flow.managed.toml"

        self.assertTrue(skill_path.exists())
        self.assertTrue(agent_path.exists())
        self.assertTrue(managed_path.exists())

    def test_setup_user_runs_both_target_syncs(self) -> None:
        fake_home = self.use_fake_home()
        result = self.run_flow("setup", "user")
        self.assert_ok(result)
        self.assertTrue((fake_home / ".claude" / "flow.managed.toml").exists())
        self.assertTrue((fake_home / ".codex" / "flow.managed.toml").exists())

    def test_sync_claude_user_check_detects_drift(self) -> None:
        fake_home = self.use_fake_home()
        self.assert_ok(self.run_flow("sync", "claude", "--user"))

        skill_path = fake_home / ".claude" / "skills" / "flow-plan" / "SKILL.md"
        skill_path.write_text(skill_path.read_text() + "\nmanual drift\n")

        result = self.run_flow("sync", "claude", "--user", "--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("drift detected", result.stdout)

    # ----------------------------------------------------------------------
    # User overlay (P2) — ~/.flow/user/ merge during user-mode sync
    # ----------------------------------------------------------------------

    def _write_user_overlay_command(
        self,
        fake_home: Path,
        name: str,
        body: str,
        description: str = "user-overlay command description",
        summary: str = "user overlay summary",
    ) -> None:
        """Drop a user-overlay command under ~/.flow/user/ and register it in flow.toml."""
        overlay_dir = fake_home / ".flow" / "user"
        commands_dir = overlay_dir / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)
        cmd_file = commands_dir / f"{name}.md"
        cmd_file.write_text(body)

        manifest = overlay_dir / "flow.toml"
        # Append the [[claude.commands]] block — minimal TOML the parser
        # in cli/flow.py accepts (single-line string values).
        block = (
            "\n"
            "[[claude.commands]]\n"
            f'name = "{name}"\n'
            f'source = "commands/{name}.md"\n'
            f'description = "{description}"\n'
            f'summary = "{summary}"\n'
        )
        if manifest.exists():
            manifest.write_text(manifest.read_text() + block)
        else:
            manifest.write_text(block)

    def _write_user_overlay_hook(
        self,
        fake_home: Path,
        name: str,
        event: str,
        script: str,
        runtime: str = "codex",
        matcher: str | None = None,
        timeout: int | None = None,
    ) -> None:
        """Drop a user-overlay hook script + [[<runtime>.hooks]] registration."""
        overlay_dir = fake_home / ".flow" / "user"
        hooks_dir = overlay_dir / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        (hooks_dir / script).write_text("#!/bin/bash\nexit 0\n")

        manifest = overlay_dir / "flow.toml"
        block = (
            "\n"
            f"[[{runtime}.hooks]]\n"
            f'name = "{name}"\n'
            f'event = "{event}"\n'
            'type = "command"\n'
            f'script = "{script}"\n'
        )
        if matcher is not None:
            block += f'matcher = "{matcher}"\n'
        if timeout is not None:
            block += f"timeout = {timeout}\n"
        if manifest.exists():
            manifest.write_text(manifest.read_text() + block)
        else:
            manifest.write_text(block)

    def _write_user_overlay_agent(
        self,
        fake_home: Path,
        name: str,
        body: str,
    ) -> None:
        overlay_dir = fake_home / ".flow" / "user"
        agents_dir = overlay_dir / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        (agents_dir / f"{name}.md").write_text(body)

        manifest = overlay_dir / "flow.toml"
        block = (
            "\n"
            "[[agents]]\n"
            f'name = "{name}"\n'
            f'source = "agents/{name}.md"\n'
            'model_tier = "working"\n'
        )
        if manifest.exists():
            manifest.write_text(manifest.read_text() + block)
        else:
            manifest.write_text(block)

    def test_user_overlay_overrides_framework_command(self) -> None:
        """User overlay can replace a framework command's source — the generated
        SKILL.md should embed the user's body, not the framework's."""
        fake_home = self.use_fake_home()
        self._write_user_overlay_command(
            fake_home,
            name="flow-plan",
            body="# flow-plan (USER OVERRIDE)\n\nMy custom plan workflow body.\n",
            description="user override of flow-plan",
            summary="user-overridden plan",
        )

        self.assert_ok(self.run_flow("sync", "claude", "--user"))

        skill = fake_home / ".claude" / "skills" / "flow-plan" / "SKILL.md"
        self.assertTrue(skill.exists())
        content = skill.read_text()
        self.assertIn("USER OVERRIDE", content)
        self.assertIn("My custom plan workflow body", content)
        # Managed manifest should record the user-origin source path.
        managed = (fake_home / ".claude" / "flow.managed.toml").read_text()
        self.assertIn("~/.flow/user/commands/flow-plan.md", managed)

    def test_user_overlay_adds_new_command(self) -> None:
        """User overlay can register a command not in the framework."""
        fake_home = self.use_fake_home()
        self._write_user_overlay_command(
            fake_home,
            name="flow-jira-status",
            body="# flow-jira-status\n\nA user-defined command for checking Jira status.\n",
            description="user-defined Jira status check",
            summary="check Jira tickets",
        )

        self.assert_ok(self.run_flow("sync", "claude", "--user"))

        skill = fake_home / ".claude" / "skills" / "flow-jira-status" / "SKILL.md"
        self.assertTrue(skill.exists(), "user-added command must generate a SKILL.md")
        self.assertIn("user-defined Jira status", skill.read_text())

    def test_skill_edit_hint_matches_origin_and_mode(self) -> None:
        """The generated marker must direct edits to a file that actually
        exists, which depends on BOTH origin and sync mode: a user-overlay
        command's source lives under `~/.flow/user/`; a framework command
        synced in --user mode lives under the scaffold at
        `~/.flow/source/scaffolds/default/` (there is no `.flow/` anywhere
        near `~/.claude/skills/`); only project mode gets the classic
        `.flow/<source>` hint. Review caught the first fix handling only
        the user-origin case and a test pinning the wrong framework-in-
        user-mode string — this asserts all three cells of the matrix.
        """
        fake_home = self.use_fake_home()
        self._write_user_overlay_command(
            fake_home,
            name="flow-jira-status",
            body="# flow-jira-status\n\nbody\n",
            description="user-defined Jira status check",
            summary="check Jira tickets",
        )

        self.assert_ok(self.run_flow("sync", "claude", "--user"))

        user_skill = (fake_home / ".claude" / "skills" / "flow-jira-status" / "SKILL.md").read_text()
        self.assertIn("Edit `~/.flow/user/commands/flow-jira-status.md`", user_skill)
        self.assertIn("flow sync claude --user", user_skill)
        self.assertNotIn("Edit `.flow/", user_skill)

        framework_user = (fake_home / ".claude" / "skills" / "flow-plan" / "SKILL.md").read_text()
        self.assertIn(
            "Edit `~/.flow/source/scaffolds/default/commands/flow-plan.md`",
            framework_user,
            "a framework skill installed at user level cannot be edited via a nonexistent .flow/",
        )
        self.assertIn("flow sync claude --user", framework_user)

        self.setup_project()
        self.assert_ok(self.run_flow("sync", "claude"))
        framework_project = (self.repo / ".claude" / "skills" / "flow-plan" / "SKILL.md").read_text()
        self.assertIn("Edit `.flow/commands/flow-plan.md`", framework_project)
        self.assertNotIn("--user", framework_project.split("-->")[0].split("<!--")[-1])

    # ------------------------------------------------------------------
    # [[codex.hooks]] — full-parity hook management for the Codex runtime
    # ------------------------------------------------------------------

    def test_codex_hooks_generate_script_and_hooks_json_without_touching_config_toml(self) -> None:
        """A [[codex.hooks]] entry deploys its script to ~/.codex/hooks/ and
        merges a handler into ~/.codex/hooks.json — and never touches
        config.toml, which is user-owned (model, plugins, the desktop
        app's own `notify` key). Also proves re-sync idempotency: the
        handler must not duplicate.
        """
        fake_home = self.use_fake_home()
        codex_dir = fake_home / ".codex"
        codex_dir.mkdir(parents=True)
        config_before = 'model = "gpt-5.6-sol"\nnotify = ["someapp", "turn-ended"]\n'
        (codex_dir / "config.toml").write_text(config_before)
        self._write_user_overlay_hook(
            fake_home, name="my-stop-hook", event="Stop", script="flow-my-stop.sh", timeout=15
        )

        self.assert_ok(self.run_flow("sync", "codex", "--user"))

        script = codex_dir / "hooks" / "flow-my-stop.sh"
        self.assertTrue(script.is_file())
        self.assertTrue(script.stat().st_mode & stat.S_IXUSR, "hook script must be executable")

        doc = json.loads((codex_dir / "hooks.json").read_text())
        # The framework registers its own codex Stop hook (flow-token-verdict),
        # so filter to the overlay's handler rather than asserting a count.
        mine = [
            (g, h)
            for g in doc["hooks"]["Stop"]
            for h in g["hooks"]
            if "flow-my-stop.sh" in h.get("command", "")
        ]
        self.assertEqual(len(mine), 1)
        group, handler = mine[0]
        self.assertEqual(handler["type"], "command")
        self.assertIn('"$HOME"/.codex/hooks/flow-my-stop.sh', handler["command"])
        self.assertEqual(handler["timeout"], 15)
        self.assertNotIn("matcher", group, "omitted matcher must be omitted, not emitted empty")

        self.assertEqual((codex_dir / "config.toml").read_text(), config_before)

        # Idempotent: second sync must not duplicate any handler.
        self.assert_ok(self.run_flow("sync", "codex", "--user"))
        doc2 = json.loads((codex_dir / "hooks.json").read_text())
        self.assertEqual(doc2, doc, "a second sync must be a byte-identical no-op")

    def test_codex_hooks_preserve_unmanaged_handlers_on_the_same_event(self) -> None:
        fake_home = self.use_fake_home()
        codex_dir = fake_home / ".codex"
        codex_dir.mkdir(parents=True)
        (codex_dir / "hooks.json").write_text(
            json.dumps(
                {
                    "description": "hand-authored",
                    "hooks": {
                        "Stop": [
                            {"hooks": [{"type": "command", "command": "my-own-thing.sh"}]}
                        ]
                    },
                }
            )
        )
        self._write_user_overlay_hook(fake_home, name="my-stop-hook", event="Stop", script="flow-my-stop.sh")

        self.assert_ok(self.run_flow("sync", "codex", "--user"))

        doc = json.loads((codex_dir / "hooks.json").read_text())
        self.assertEqual(doc["description"], "hand-authored", "unmanaged top-level keys must survive")
        commands = [h["command"] for g in doc["hooks"]["Stop"] for h in g["hooks"]]
        self.assertIn("my-own-thing.sh", commands)
        self.assertTrue(any("flow-my-stop.sh" in c for c in commands))

    def test_codex_hooks_deregistration_removes_only_flow_handlers(self) -> None:
        fake_home = self.use_fake_home()
        codex_dir = fake_home / ".codex"
        codex_dir.mkdir(parents=True)
        (codex_dir / "hooks.json").write_text(
            json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "my-own-thing.sh"}]}]}})
        )
        self._write_user_overlay_hook(fake_home, name="my-stop-hook", event="Stop", script="flow-my-stop.sh")
        self.assert_ok(self.run_flow("sync", "codex", "--user"))

        # Deregister: rewrite the overlay manifest without the hook block.
        manifest = fake_home / ".flow" / "user" / "flow.toml"
        lines = manifest.read_text().splitlines(keepends=True)
        kept = []
        skip = False
        for line in lines:
            if line.startswith("[[codex.hooks]]"):
                skip = True
                continue
            if skip and line.startswith("[["):
                skip = False
            if not skip:
                kept.append(line)
        manifest.write_text("".join(kept))

        self.assert_ok(self.run_flow("sync", "codex", "--user"))

        doc = json.loads((codex_dir / "hooks.json").read_text())
        commands = [h["command"] for g in doc["hooks"]["Stop"] for h in g["hooks"]]
        self.assertIn("my-own-thing.sh", commands)
        self.assertFalse(any("flow-my-stop.sh" in c for c in commands))
        self.assertFalse((codex_dir / "hooks" / "flow-my-stop.sh").exists(), "deregistered script must be removed")

    def test_codex_hooks_project_mode_uses_git_toplevel_path(self) -> None:
        """Codex has no $CLAUDE_PROJECT_DIR equivalent — project-mode hook
        commands use the git rev-parse idiom from Codex's own docs.
        """
        self.use_fake_home()
        self.setup_project()
        flow_toml = self.repo / ".flow" / "flow.toml"
        flow_toml.write_text(
            flow_toml.read_text()
            + "\n[[codex.hooks]]\n"
            + 'name = "proj-hook"\nevent = "SessionStart"\ntype = "command"\nscript = "flow-proj.sh"\n'
        )
        # Project-mode hook scripts still come from the framework hooks/ dir;
        # point at one that exists there.
        flow_toml.write_text(flow_toml.read_text().replace("flow-proj.sh", "flow-session-start.sh"))

        self.assert_ok(self.run_flow("sync", "codex"))

        doc = json.loads((self.repo / ".codex" / "hooks.json").read_text())
        handler = doc["hooks"]["SessionStart"][0]["hooks"][0]
        self.assertIn('"$(git rev-parse --show-toplevel)"/.codex/hooks/flow-session-start.sh', handler["command"])
        self.assertTrue((self.repo / ".codex" / "hooks" / "flow-session-start.sh").is_file())

    def test_hook_script_not_named_flow_is_rejected_at_sync_time(self) -> None:
        """The preserve-unmanaged strip identifies flow's handlers by the
        `/.codex/hooks/flow-` marker — a script named outside that
        convention would survive the strip and duplicate its handler on
        every sync. Review demanded this fail loudly rather than corrupt.
        """
        fake_home = self.use_fake_home()
        (fake_home / ".codex").mkdir(parents=True)
        self._write_user_overlay_hook(fake_home, name="bad-hook", event="Stop", script="my-stop.sh")

        result = self.run_flow("sync", "codex", "--user")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be named flow-*", result.stdout + result.stderr)
        self.assertFalse((fake_home / ".codex" / "hooks.json").exists(), "nothing may be written on rejection")

    def test_dropping_hooks_config_never_deletes_the_merge_file(self) -> None:
        """hooks.json (and settings.json) hold user content alongside
        flow's. Removing hook_dir/hooks_file from the manifest makes the
        file 'stale' — it must be unmanaged, never unlinked.
        """
        self.use_fake_home()
        self.setup_project()
        flow_toml = self.repo / ".flow" / "flow.toml"
        hooks_json = self.repo / ".codex" / "hooks.json"
        hooks_json.parent.mkdir(parents=True, exist_ok=True)
        hooks_json.write_text(
            json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "user-owned.sh"}]}]}})
        )

        self.assert_ok(self.run_flow("sync", "codex"))
        self.assertTrue(hooks_json.exists())

        # Drop the hooks surface from the manifest entirely.
        content = flow_toml.read_text()
        content = content.replace('hook_dir = ".codex/hooks"\n', "").replace(
            'hooks_file = ".codex/hooks.json"\n', ""
        )
        # Also drop the [[codex.hooks]] entries so the runtime has no hooks.
        lines, skip = [], False
        for line in content.splitlines(keepends=True):
            if line.startswith("[[codex.hooks]]"):
                skip = True
                continue
            if skip and line.startswith("[["):
                skip = False
            if not skip:
                lines.append(line)
        flow_toml.write_text("".join(lines))

        self.assert_ok(self.run_flow("sync", "codex"))
        self.assertTrue(hooks_json.exists(), "a merge-mode file must survive being dropped from the manifest")
        doc = json.loads(hooks_json.read_text())
        commands = [h["command"] for g in doc["hooks"]["Stop"] for h in g["hooks"]]
        self.assertIn("user-owned.sh", commands, "the user's own handler must survive")

    def test_claude_hooks_merge_from_user_overlay(self) -> None:
        """Full parity includes the overlay: a [[claude.hooks]] entry in
        ~/.flow/user/flow.toml must land in ~/.claude/settings.json with
        its script deployed from ~/.flow/user/hooks/.
        """
        fake_home = self.use_fake_home()
        self._write_user_overlay_hook(
            fake_home, name="my-claude-hook", event="Stop", script="flow-my-claude.sh", runtime="claude"
        )

        self.assert_ok(self.run_flow("sync", "claude", "--user"))

        self.assertTrue((fake_home / ".claude" / "hooks" / "flow-my-claude.sh").is_file())
        settings = json.loads((fake_home / ".claude" / "settings.json").read_text())
        commands = [h["command"] for g in settings["hooks"]["Stop"] for h in g["hooks"]]
        self.assertTrue(any("flow-my-claude.sh" in c for c in commands))

    def test_user_overlay_overrides_framework_agent(self) -> None:
        """User overlay can replace a framework agent's content."""
        fake_home = self.use_fake_home()
        self._write_user_overlay_agent(
            fake_home,
            name="architect",
            body="---\nname: architect\ndescription: USER OVERRIDE\n---\n\n# Architect (user override)\nBody.\n",
        )

        self.assert_ok(self.run_flow("sync", "claude", "--user"))

        agent = fake_home / ".claude" / "agents" / "architect.md"
        self.assertTrue(agent.exists())
        content = agent.read_text()
        self.assertIn("USER OVERRIDE", content)
        managed = (fake_home / ".claude" / "flow.managed.toml").read_text()
        self.assertIn("~/.flow/user/agents/architect.md", managed)

    def test_user_overlay_adds_new_agent(self) -> None:
        fake_home = self.use_fake_home()
        self._write_user_overlay_agent(
            fake_home,
            name="personal-tutor",
            body="---\nname: personal-tutor\ndescription: explains things at my level\n---\n\n# Personal Tutor\nBody.\n",
        )

        self.assert_ok(self.run_flow("sync", "claude", "--user"))

        agent = fake_home / ".claude" / "agents" / "personal-tutor.md"
        self.assertTrue(agent.exists(), "user-added agent must be generated")
        self.assertIn("Personal Tutor", agent.read_text())

    def test_user_overlay_codex_command_addition(self) -> None:
        """Codex side also picks up user-overlay commands when registered there."""
        fake_home = self.use_fake_home()
        overlay_dir = fake_home / ".flow" / "user"
        (overlay_dir / "commands").mkdir(parents=True)
        (overlay_dir / "commands" / "flow-custom-codex.md").write_text("# flow-custom-codex body\n")
        (overlay_dir / "flow.toml").write_text(
            "\n[[codex.commands]]\n"
            'name = "flow-custom-codex"\n'
            'source = "commands/flow-custom-codex.md"\n'
            'description = "custom codex skill"\n'
        )

        self.assert_ok(self.run_flow("sync", "codex", "--user"))

        skill = fake_home / ".agents" / "skills" / "flow-custom-codex" / "SKILL.md"
        self.assertTrue(skill.exists())
        content = skill.read_text()
        self.assertIn("flow-custom-codex body", content)
        self.assertIn("name: flow-custom-codex", content)
        self.assertIn('description: "custom codex skill"', content)

    def test_sync_codex_migrates_legacy_managed_skills(self) -> None:
        """Existing overlays keep working when their manifest still names the old path."""
        self.setup_project()
        manifest = self.repo / ".flow" / "flow.toml"
        manifest_text = manifest.read_text().replace(
            '[codex]\nskill_dir = ".agents/skills"',
            '[codex]\nskill_dir = ".codex/skills"',
        )
        manifest.write_text(manifest_text)
        self.assertIn('skill_dir = ".codex/skills"', manifest.read_text())

        legacy_skill = self.repo / ".codex" / "skills" / "flow-plan" / "SKILL.md"
        legacy_skill.parent.mkdir(parents=True)
        legacy_skill.write_text("<!-- Generated by flow. -->\nlegacy\n")
        managed = self.repo / ".codex" / "flow.managed.toml"
        managed.parent.mkdir(parents=True, exist_ok=True)
        managed.write_text(
            '[managed]\n'
            'generator = "flow"\n'
            'version = 2\n'
            'target = "codex"\n'
            'source_manifest = ".flow/flow.toml"\n'
            'preserve_unmanaged = true\n\n'
            '[[files]]\n'
            'path = ".codex/skills/flow-plan/SKILL.md"\n'
            'kind = "skill"\n'
            'source = ".flow/commands/flow-plan.md"\n'
            'sync_mode = "replace"\n'
            '\n[[files]]\n'
            'path = ".codex/flow.managed.toml"\n'
            'kind = "managed-manifest"\n'
            'source = ".flow/flow.toml"\n'
            'sync_mode = "replace"\n'
        )

        self.assert_ok(self.run_flow("sync", "codex"))

        current_skill = self.repo / ".agents" / "skills" / "flow-plan" / "SKILL.md"
        self.assertTrue(current_skill.exists())
        self.assertFalse(legacy_skill.exists())
        self.assertIn('.agents/skills/flow-plan/SKILL.md', managed.read_text())

    def test_user_overlay_absent_means_unchanged_behavior(self) -> None:
        """Regression guard: without ~/.flow/user/flow.toml, sync output is
        identical to the pre-user-overlay world."""
        fake_home = self.use_fake_home()
        # No overlay manifest written.
        self.assert_ok(self.run_flow("sync", "claude", "--user"))

        # All framework adapters should be present.
        self.assertTrue((fake_home / ".claude" / "skills" / "flow-plan" / "SKILL.md").exists())
        self.assertTrue((fake_home / ".claude" / "agents" / "architect.md").exists())

        # No spurious entries.
        managed = (fake_home / ".claude" / "flow.managed.toml").read_text()
        self.assertNotIn("~/.flow/user/", managed)

    def test_user_overlay_invalid_toml_falls_back_gracefully(self) -> None:
        """A broken ~/.flow/user/flow.toml prints a warning and proceeds with
        framework-only manifest — sync should still succeed."""
        fake_home = self.use_fake_home()
        (fake_home / ".flow" / "user").mkdir(parents=True, exist_ok=True)
        # Intentionally bad TOML: parse_simple_toml rejects `= 1.5` (no float support).
        (fake_home / ".flow" / "user" / "flow.toml").write_text(
            "[[claude.commands]]\nname = invalid syntax here\n"
        )

        result = self.run_flow("sync", "claude", "--user")
        self.assert_ok(result)
        # Framework adapters still generated.
        self.assertTrue((fake_home / ".claude" / "skills" / "flow-plan" / "SKILL.md").exists())

    def test_doctor_reports_user_overlay_when_present(self) -> None:
        fake_home = self.use_fake_home()
        self._write_user_overlay_command(
            fake_home,
            name="flow-personal",
            body="# personal\n",
            description="personal command",
        )

        result = self.run_flow("doctor")
        self.assert_ok(result)
        self.assertIn("user overlay:", result.stdout)
        self.assertIn("flow-personal", result.stdout)

    def test_doctor_reports_no_user_overlay_when_absent(self) -> None:
        fake_home = self.use_fake_home()
        result = self.run_flow("doctor")
        self.assert_ok(result)
        self.assertIn("user overlay:     none", result.stdout)

    def test_doctor_with_user_install_shows_clean_user_state(self) -> None:
        fake_home = self.use_fake_home()
        self.assert_ok(self.run_flow("setup", "user"))

        result = self.run_flow("doctor")
        self.assert_ok(result)
        self.assertIn("-- user-level", result.stdout)
        # Both user-level and project-level should appear; user-level should be clean
        user_section = result.stdout.split("-- user-level")[1].split("-- project:")[0]
        self.assertIn("claude drift:     clean", user_section)
        self.assertIn("codex drift:      clean", user_section)

    # ----------------------------------------------------------------------
    # Two-mode install (develop / release) tests
    # ----------------------------------------------------------------------

    def test_install_flow_sh_develop_creates_symlink(self) -> None:
        fake_home = self.do_install_develop()
        source = fake_home / ".flow" / "source"
        self.assertTrue(source.is_symlink(), f"expected {source} to be a symlink")
        self.assertEqual(source.resolve(), REPO_ROOT)
        config = (fake_home / ".flow" / "config.toml").read_text()
        self.assertIn('mode = "develop"', config)
        self.assertIn('source_target = "', config)

    def test_install_flow_sh_release_creates_real_directory(self) -> None:
        fake_home = self.do_install_release()
        source = fake_home / ".flow" / "source"
        self.assertTrue(source.is_dir())
        self.assertFalse(source.is_symlink(), f"{source} should be a real directory in release mode")
        # Release roster present
        self.assertTrue((source / "cli" / "flow.py").is_file())
        self.assertTrue((source / "scaffolds" / "default" / "flow.toml").is_file())
        self.assertTrue((source / "README.md").is_file())
        self.assertTrue(
            (source / "CHANGELOG.md").is_file(),
            "CHANGELOG.md must ship in release installs so users can read their version history offline",
        )
        # Excluded paths absent
        self.assertFalse((source / ".git").exists(), "release copy must exclude .git/")
        self.assertFalse((source / "tests").exists(), "release copy must exclude tests/")
        self.assertFalse((source / "install-flow.sh").exists(), "release copy must exclude install-flow.sh")

    def test_release_install_includes_arbitrary_new_top_level_file(self) -> None:
        """Forward-compatibility (backlog P8): the release roster uses a
        blacklist, so a new top-level file added to the framework in a future
        version is automatically included in releases produced by today's
        code — no roster-update required in older clients.
        """
        # Build a temp copy of REPO_ROOT with an extra marker file we know is
        # NOT in the current framework. Install from that.
        temp_repo = self.repo / "marker-repo"
        shutil.copytree(
            REPO_ROOT,
            temp_repo,
            ignore=shutil.ignore_patterns(
                ".git", "*.pyc", "__pycache__", "fake_home", "fake-remote*", "marker-repo"
            ),
        )
        (temp_repo / "FUTURE_FILE.md").write_text("Pretend-future top-level file.\n")

        fake_home = self._new_fake_home()
        result = subprocess.run(
            ["bash", str(temp_repo / "install-flow.sh"), "--release"],
            cwd=str(temp_repo),
            text=True,
            capture_output=True,
            env=_clean_env(fake_home),
        )
        self.assertEqual(
            result.returncode,
            0,
            f"install failed: stdout={result.stdout}\nstderr={result.stderr}",
        )
        # The arbitrary new top-level file landed in the release install.
        self.assertTrue(
            (fake_home / ".flow" / "source" / "FUTURE_FILE.md").is_file(),
            "blacklist-based release roster should include arbitrary new top-level files",
        )

    def test_install_flow_sh_release_stamps_mode_and_version(self) -> None:
        fake_home = self.do_install_release()
        config = (fake_home / ".flow" / "config.toml").read_text()
        self.assertIn('mode = "release"', config)
        self.assertIn('version = "', config)
        self.assertIn('remote = "', config)
        self.assertIn('installed_at = "', config)
        self.assertIn('python = "', config)
        self.assertIn('python_version = "', config)

    def test_install_flow_sh_fails_clearly_without_python_3_10_plus(self) -> None:
        fake_home = self._new_fake_home()
        fake_bin = self._make_fake_python_bin(include_compatible=False)
        env = _clean_env(fake_home)
        env["PATH"] = f"{fake_bin}:/usr/bin:/bin"
        env["FLOW_PYTHON_CANDIDATES"] = str(fake_bin / "python3")

        result = subprocess.run(
            ["bash", str(INSTALL_SCRIPT), "--release"],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            env=env,
        )

        self.assertNotEqual(result.returncode, 0)
        combined = result.stdout + result.stderr
        self.assertIn("flow requires Python 3.10+", combined)
        self.assertIn("checked:", combined)
        self.assertIn("brew install python@3.12", combined)
        self.assertFalse((fake_home / ".flow" / "source").exists())

    def test_install_flow_sh_uses_versioned_python_when_python3_is_too_old(self) -> None:
        fake_home = self._new_fake_home()
        fake_bin = self._make_fake_python_bin(include_compatible=True)
        env = _clean_env(fake_home)
        env["PATH"] = f"{fake_bin}:/usr/bin:/bin"
        env["FLOW_PYTHON_CANDIDATES"] = f"{fake_bin / 'python3'}:{fake_bin / f'python{sys.version_info.major}.{sys.version_info.minor}'}"

        result = subprocess.run(
            ["bash", str(INSTALL_SCRIPT), "--release"],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            env=env,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"install-flow.sh --release failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

        chosen_python = fake_bin / f"python{sys.version_info.major}.{sys.version_info.minor}"
        launcher = (fake_home / ".local" / "bin" / "flow").read_text()
        config = (fake_home / ".flow" / "config.toml").read_text()
        self.assertIn(str(chosen_python), launcher)
        self.assertIn(f'python = "{chosen_python}"', config)
        self.assertIn(f'python_version = "{sys.version_info.major}.{sys.version_info.minor}.', config)

    def test_release_install_is_self_contained_after_clone_removed(self) -> None:
        """After release install, the CLI must run even if the source clone is gone.

        We can't actually remove REPO_ROOT during tests, but we can verify the
        installed CLI doesn't read from REPO_ROOT — by running it with a wrong
        cwd and confirming it resolves through ~/.flow/source/.
        """
        fake_home = self.do_install_release()
        result = subprocess.run(
            [sys.executable, str(fake_home / ".flow" / "source" / "cli" / "flow.py"), "doctor"],
            cwd=str(self.repo),
            text=True,
            capture_output=True,
            env=_clean_env(fake_home),
        )
        self.assert_ok(result)
        self.assertIn("mode:             release", result.stdout)

    def test_doctor_release_install_reports_mode_and_version(self) -> None:
        self.do_install_release()
        result = self.run_flow("doctor")
        self.assert_ok(result)
        self.assertIn("-- install --", result.stdout)
        self.assertIn("mode:             release", result.stdout)
        install_section = result.stdout.split("-- install --")[1].split("-- user-level")[0]
        self.assertIn("version:", install_section)
        self.assertIn("remote:", install_section)
        self.assertIn("installed at:", install_section)

    def test_doctor_develop_install_reports_source_target(self) -> None:
        self.do_install_develop()
        result = self.run_flow("doctor")
        self.assert_ok(result)
        self.assertIn("-- install --", result.stdout)
        self.assertIn("mode:             develop", result.stdout)
        install_section = result.stdout.split("-- install --")[1].split("-- user-level")[0]
        self.assertIn("source target:", install_section)

    def test_install_command_release_converts_from_develop(self) -> None:
        fake_home = self.do_install_develop()
        source = fake_home / ".flow" / "source"
        self.assertTrue(source.is_symlink())

        self.assert_ok(self.run_flow("install", "--release"))

        self.assertFalse(source.is_symlink(), "after conversion source should be a real directory")
        self.assertTrue((source / "cli" / "flow.py").is_file())
        config = (fake_home / ".flow" / "config.toml").read_text()
        self.assertIn('mode = "release"', config)
        # Clone preserved
        self.assertTrue((REPO_ROOT / "cli" / "flow.py").is_file())

    def test_install_release_cleans_up_source_old_symlink_leftover(self) -> None:
        """Regression test for the shutil.rmtree-doesn't-delete-symlinks bug.

        When converting develop → release, the swap renames the develop-mode
        symlink (~/.flow/source → clone) to ~/.flow/source.old. The post-swap
        cleanup must actually delete that symlink — `shutil.rmtree` with
        ignore_errors=True silently no-ops on symlinks, leaving a leftover
        that causes the next `flow update` to crash with ENOTDIR.
        """
        fake_home = self.do_install_develop()
        self.assert_ok(self.run_flow("install", "--release"))
        source_old = fake_home / ".flow" / "source.old"
        # If the symlink leaked, source_old.is_symlink() returns True and
        # source_old.exists() follows it to the clone and is also True. Both
        # must be False after the conversion cleanup.
        self.assertFalse(
            source_old.is_symlink(),
            f"{source_old} symlink was leaked; "
            "shutil.rmtree(ignore_errors=True) silently fails to delete symlinks — "
            "must use _remove_path or os.unlink for symlink-typed entries",
        )
        self.assertFalse(
            source_old.exists(),
            f"{source_old} must not exist after the develop→release conversion cleanup",
        )

    def test_install_command_develop_converts_from_release(self) -> None:
        fake_home = self.do_install_release()
        source = fake_home / ".flow" / "source"
        self.assertFalse(source.is_symlink())

        self.assert_ok(self.run_flow("install", "--develop", str(REPO_ROOT)))

        self.assertTrue(source.is_symlink())
        self.assertEqual(source.resolve(), REPO_ROOT)
        config = (fake_home / ".flow" / "config.toml").read_text()
        self.assertIn('mode = "develop"', config)
        self.assertIn(f'source_target = "{REPO_ROOT}"', config)

    def test_install_command_requires_a_mode(self) -> None:
        self.do_install_develop()
        result = self.run_flow("install")
        self.assertNotEqual(result.returncode, 0)

    def test_install_develop_rejects_nonexistent_path(self) -> None:
        self.do_install_release()
        result = self.run_flow("install", "--develop", str(self.repo / "nope"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not exist", result.stdout)

    def test_install_develop_rejects_non_flow_directory(self) -> None:
        self.do_install_release()
        bogus = self.repo / "bogus-clone"
        bogus.mkdir()
        result = self.run_flow("install", "--develop", str(bogus))
        self.assertEqual(result.returncode, 1)
        self.assertIn("not a flow checkout", result.stdout)

    def test_update_in_develop_mode_prints_manual_instructions(self) -> None:
        self.do_install_develop()
        result = self.run_flow("update")
        self.assert_ok(result)
        self.assertIn("develop install", result.stdout)
        self.assertIn("git -C", result.stdout)
        self.assertIn("flow sync claude --user", result.stdout)

    def test_update_check_in_release_mode_reports_available_tag(self) -> None:
        self.do_install_release()
        remote = self.make_fake_remote_with_tags(["v9.9.9"])

        result = self.run_flow("update", "--check", "--remote", f"file://{remote}")
        self.assert_ok(result)
        self.assertIn("latest:", result.stdout)
        self.assertIn("v9.9.9", result.stdout)
        self.assertIn("update available", result.stdout)

    def test_update_check_shows_changelog_section_for_new_version(self) -> None:
        """flow update --check fetches the remote's CHANGELOG.md at the latest
        tag and prints the section for that version, so the user knows what
        they'd be getting.
        """
        fake_home = self.do_install_release()
        # Pin the config to an older version so the fake remote's v0.4.5 looks
        # like an available update. CHANGELOG.md in REPO_ROOT has a v0.4.5
        # entry (this commit added it), so the fake remote will too.
        config_path = fake_home / ".flow" / "config.toml"
        import re as _re
        text = config_path.read_text()
        text = _re.sub(r'version = "[^"]*"', 'version = "v0.4.0"', text)
        config_path.write_text(text)
        remote = self.make_fake_remote_with_tags(["v0.4.5"])

        result = self.run_flow("update", "--check", "--remote", f"file://{remote}")
        self.assert_ok(result)
        self.assertIn("update available: v0.4.0 -> v0.4.5", result.stdout)
        # The CHANGELOG section header for v0.4.5 should appear in the output.
        self.assertIn("## [0.4.5]", result.stdout)
        # And content from that section should appear too — the v0.4.5 entry
        # is the "CHANGELOG.md ships in the release install roster" change.
        self.assertIn("release install roster", result.stdout.lower())

    def test_update_check_already_current_is_noop(self) -> None:
        fake_home = self.do_install_release()
        # Pin the config's version to one that matches the fake remote's only tag.
        config_path = fake_home / ".flow" / "config.toml"
        text = config_path.read_text()
        import re
        text = re.sub(r'version = "[^"]*"', 'version = "v9.9.9"', text)
        config_path.write_text(text)
        remote = self.make_fake_remote_with_tags(["v9.9.9"])

        result = self.run_flow("update", "--check", "--remote", f"file://{remote}")
        self.assert_ok(result)
        self.assertIn("already at the latest tag", result.stdout)

    def test_update_apply_in_release_mode_swaps_and_records_version(self) -> None:
        fake_home = self.do_install_release()
        remote = self.make_fake_remote_with_tags(["v9.9.9"])

        result = self.run_flow("update", "--remote", f"file://{remote}")
        self.assert_ok(result)

        config = (fake_home / ".flow" / "config.toml").read_text()
        self.assertIn('version = "v9.9.9"', config)
        # New install is intact
        self.assertTrue((fake_home / ".flow" / "source" / "cli" / "flow.py").is_file())
        self.assertTrue((fake_home / ".flow" / "source" / "scaffolds" / "default" / "flow.toml").is_file())
        # Stage and rollback dirs cleaned up
        self.assertFalse((fake_home / ".flow" / "source.new").exists())
        self.assertFalse((fake_home / ".flow" / "source.old").exists())

    def test_update_picks_highest_semver_tag(self) -> None:
        self.do_install_release()
        # Order on purpose — tag insertion order != semver order
        remote = self.make_fake_remote_with_tags(["v1.0.0", "v1.10.0", "v1.2.0"])

        result = self.run_flow("update", "--check", "--remote", f"file://{remote}")
        self.assert_ok(result)
        self.assertIn("latest:  v1.10.0", result.stdout)

    # ----------------------------------------------------------------------
    # Standards / vendored upstream content
    # ----------------------------------------------------------------------

    def test_git_commits_standard_exists_and_cites_upstream(self) -> None:
        standard = REPO_ROOT / "scaffolds" / "default" / "standards" / "git-commits.md"
        self.assertTrue(standard.exists(), "flow-authored git-commits standard must exist")
        text = standard.read_text()
        self.assertIn("Conventional Commits", text)
        self.assertIn("conventionalcommits.org", text)
        self.assertIn("vendor/conventional-commits-1.0.0.md", text)
        # Project overrides section is the documented extension point.
        self.assertIn("Project Overrides", text)

    def test_vendor_mirror_exists_and_carries_attribution(self) -> None:
        vendor = REPO_ROOT / "scaffolds" / "default" / "standards" / "vendor" / "conventional-commits-1.0.0.md"
        self.assertTrue(vendor.exists(), "vendor mirror must exist at the canonical path")
        text = vendor.read_text()
        # Attribution header lives in an HTML comment so it doesn't disturb rendering.
        self.assertIn("VENDORED VERBATIM", text)
        self.assertIn("Pinned SHA:", text)
        self.assertIn("Spec version:  v1.0.0", text)
        self.assertIn("License:", text)
        # Upstream spec body markers — would change if the upstream content drifted.
        self.assertIn("# Conventional Commits 1.0.0", text)
        self.assertIn("BREAKING CHANGE", text)

    def test_vendor_license_file_present(self) -> None:
        license_path = REPO_ROOT / "scaffolds" / "default" / "standards" / "vendor" / "conventional-commits-LICENSE.txt"
        self.assertTrue(license_path.exists(), "upstream license must be carried with the vendor mirror")
        self.assertIn("MIT License", license_path.read_text())

    def test_flow_toml_declares_git_commits_dependency(self) -> None:
        manifest_path = REPO_ROOT / "scaffolds" / "default" / "flow.toml"
        text = manifest_path.read_text()
        # Required keys for the dependency declaration.
        self.assertIn("[standards.git-commits]", text)
        for key in (
            'spec = "Conventional Commits"',
            'upstream = "',
            'upstream_repo = "',
            'upstream_version = "v1.0.0"',
            'upstream_license = "MIT"',
            'vendored_path = "standards/vendor/conventional-commits-1.0.0.md"',
            'vendored_sha = "',
            'vendored_at = "',
            'flow_standard = "standards/git-commits.md"',
        ):
            self.assertIn(key, text, f"flow.toml [standards.git-commits] missing key: {key}")
        # The vendored_sha and vendored_at values must be non-empty.
        import re
        for key in ("vendored_sha", "vendored_at", "upstream_version"):
            match = re.search(rf'{key}\s*=\s*"([^"]+)"', text)
            self.assertIsNotNone(match, f"{key} regex did not match")
            self.assertTrue(match.group(1), f"{key} must have a non-empty value")

    def test_flow_toml_parses_with_internal_parser(self) -> None:
        """Validate the new metadata block round-trips through flow's own TOML parser."""
        # Import the parser module directly so we cover the same code path the
        # CLI uses. flowtoml.py imports nothing from its siblings, so unlike the
        # other direct-load tests this needs no sys.path arrangement.
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "flowtoml_under_test", REPO_ROOT / "cli" / "flowtoml.py"
        )
        flowtoml = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        assert spec and spec.loader
        spec.loader.exec_module(flowtoml)  # type: ignore[union-attr]
        data = flowtoml.read_toml(REPO_ROOT / "scaffolds" / "default" / "flow.toml")
        block = data.get("standards", {}).get("git-commits")
        self.assertIsInstance(block, dict)
        self.assertEqual(block.get("upstream_version"), "v1.0.0")
        self.assertEqual(block.get("upstream_license"), "MIT")
        self.assertEqual(
            block.get("vendored_path"),
            "standards/vendor/conventional-commits-1.0.0.md",
        )

    def test_agents_and_commands_cite_git_commits_standard(self) -> None:
        """The four touchpoints must reference the standard so Claude actually sees it."""
        scaffolds = REPO_ROOT / "scaffolds" / "default"
        citing_paths = [
            scaffolds / "agents" / "lead-developer.md",
            scaffolds / "agents" / "quality-reviewer.md",
            scaffolds / "commands" / "flow-implement.md",
            scaffolds / "commands" / "flow-scout.md",
        ]
        for path in citing_paths:
            text = path.read_text()
            self.assertIn(
                "standards/git-commits.md",
                text,
                f"{path.relative_to(REPO_ROOT)} must cite standards/git-commits.md",
            )

    def test_bootstrap_installer_installs_latest_tag_from_remote(self) -> None:
        """End-to-end test of the portable curl-able installer.

        Builds a fake bare remote with two tags (v0.1.0, v0.2.0), points
        `install.sh` at it via FLOW_REPO_URL, and verifies it picks v0.2.0
        (highest semver) and produces a working release install.
        """
        fake_home = self._new_fake_home()
        remote = self.make_fake_remote_with_tags(["v0.1.0", "v0.2.0"])

        env = _clean_env(fake_home)
        env["FLOW_REPO_URL"] = f"file://{remote}"

        result = subprocess.run(
            ["bash", str(BOOTSTRAP_INSTALL_SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
            env=env,
            timeout=60,
        )
        if result.returncode != 0:
            self.fail(
                f"install.sh failed with exit {result.returncode}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )

        # Bootstrap should have picked the higher semver tag.
        self.assertIn("latest release: v0.2.0", result.stdout)

        # Release-mode install must be in place.
        source = fake_home / ".flow" / "source"
        self.assertTrue(source.is_dir())
        self.assertFalse(source.is_symlink(), "bootstrap install must produce a real directory, not a symlink")
        self.assertTrue((source / "cli" / "flow.py").is_file())
        self.assertTrue((source / "scaffolds" / "default" / "flow.toml").is_file())

        config = (fake_home / ".flow" / "config.toml").read_text()
        self.assertIn('mode = "release"', config)
        self.assertIn('version = "v0.2.0"', config)

        # Launcher placed on PATH.
        self.assertTrue((fake_home / ".local" / "bin" / "flow").is_file())

    def test_bootstrap_installer_errors_when_no_semver_tags_exist(self) -> None:
        """install.sh must fail loudly if the remote has no semver tags."""
        fake_home = self._new_fake_home()
        # Build a fake remote with a non-semver tag so the strict regex rejects it.
        remote = self.make_fake_remote_with_tags(["not-a-version"])

        env = _clean_env(fake_home)
        env["FLOW_REPO_URL"] = f"file://{remote}"

        result = subprocess.run(
            ["bash", str(BOOTSTRAP_INSTALL_SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
            env=env,
            timeout=60,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no semver tags", result.stderr + result.stdout)

    def test_regenerate_flow_help_check_is_clean(self) -> None:
        """Drift test for flow-help.md.

        Asserts that `scripts/regenerate-flow-help.py --check` exits clean —
        i.e., the generated tables in flow-help.md match what flow.toml
        currently says. Catches the case where someone adds/edits a command,
        agent, or CLI summary in flow.toml without re-running the generator.
        Fast, no network, no fake home.
        """
        script = REPO_ROOT / "scripts" / "regenerate-flow-help.py"
        self.assertTrue(script.exists(), f"missing {script}")
        result = subprocess.run(
            [sys.executable, str(script), "--check"],
            capture_output=True,
            text=True,
            check=False,
            env=_clean_env(),
        )
        if result.returncode != 0:
            self.fail(
                "flow-help.md is out of sync with flow.toml.\n"
                "run `python3 scripts/regenerate-flow-help.py` to regenerate.\n\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )

    def test_refresh_script_dry_run_resolves_upstream(self) -> None:
        """Smoke-test that the maintainer refresh script is callable and reaches upstream.

        Skipped automatically when offline or git/network is unavailable.
        """
        script = REPO_ROOT / "scripts" / "refresh-conventional-commits.py"
        self.assertTrue(script.exists())
        result = subprocess.run(
            [sys.executable, str(script), "--dry-run"],
            capture_output=True,
            text=True,
            check=False,
            env=_clean_env(),
            timeout=60,
        )
        if result.returncode != 0:
            # Network failures shouldn't break the test suite — skip rather than fail.
            if "could not resolve host" in (result.stderr.lower() + result.stdout.lower()):
                self.skipTest("offline: cannot reach upstream")
            self.fail(
                f"refresh script exited {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        self.assertIn("upstream:", result.stdout)
        self.assertIn("resolved SHA:", result.stdout)
        self.assertIn("dry-run: no files written", result.stdout)

    # ------------------------------------------------------------------
    # usage store
    #
    # Every test here drives the CLI through run_flow against a fake HOME, so
    # the real ~/.flow/usage.db is never touched. The store is the one artifact
    # the design says must never be rebuilt; a suite that could write to it
    # would be able to corrupt exactly that.
    # ------------------------------------------------------------------

    def _store_path(self, home: Path) -> Path:
        return home / ".flow" / "usage.db"

    def _load_store_module(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "usage_store_under_test", REPO_ROOT / "cli" / "usage_store.py"
        )
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        assert spec and spec.loader
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        return module

    def test_setup_machine_creates_store_at_current_version(self) -> None:
        home = self.use_fake_home()
        self.assert_ok(self.run_flow("setup", "machine"))

        store = self._store_path(home)
        self.assertTrue(store.is_file(), f"expected store at {store}")

        usage_store = self._load_store_module()
        status = usage_store.store_status(store)
        self.assertEqual(status["state"], usage_store.STATE_EMPTY)
        self.assertEqual(status["user_version"], usage_store.SCHEMA_VERSION)

    def test_setup_machine_is_idempotent(self) -> None:
        home = self.use_fake_home()
        self.assert_ok(self.run_flow("setup", "machine"))
        second = self.run_flow("setup", "machine")
        self.assert_ok(second)
        self.assertIn("usage store: current", second.stdout)

        usage_store = self._load_store_module()
        import sqlite3

        conn = sqlite3.connect(self._store_path(home))
        try:
            rows = conn.execute("SELECT count(*) FROM schema_migration").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(
            rows,
            len(usage_store.MIGRATIONS),
            "re-running setup machine must not duplicate ledger rows",
        )

    def test_capability_seed_comes_from_data_file_not_code(self) -> None:
        """The seed must be data. Editing the shipped file must change the store."""
        home = self.use_fake_home()
        self.assert_ok(self.run_flow("setup", "machine"))

        import sqlite3

        conn = sqlite3.connect(self._store_path(home))
        try:
            seeded = conn.execute(
                "SELECT supported FROM harness_capability"
                " WHERE harness='claude' AND field='context_window'"
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(seeded, "expected the shipped capability seed to load")
        self.assertEqual(
            seeded[0], 0, "claude cannot report a context window; seed should say so"
        )

    def test_doctor_reports_absent_store_without_creating_it(self) -> None:
        """doctor is read-only. Reporting the absent state must not resolve it."""
        home = self._new_fake_home()
        (home / ".flow").mkdir(parents=True)
        (home / ".flow" / "source").symlink_to(REPO_ROOT)

        result = self.run_flow("doctor")
        self.assertIn("usage store:", result.stdout)
        self.assertIn("not created", result.stdout)
        self.assertFalse(
            self._store_path(home).exists(),
            "doctor must not create the store it reports as absent",
        )

    def test_doctor_reports_empty_store(self) -> None:
        self.use_fake_home()
        self.assert_ok(self.run_flow("setup", "machine"))
        result = self.run_flow("doctor")
        self.assertIn("usage store:", result.stdout)
        self.assertIn("ok, empty", result.stdout)

    def test_doctor_reports_corrupt_store_without_failing_other_sections(self) -> None:
        home = self.use_fake_home()
        store = self._store_path(home)
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text("this is not a sqlite database")

        result = self.run_flow("doctor")
        self.assertIn("usage store:      error", result.stdout)
        # the rest of doctor still reports — one bad subsystem must not hide the others
        self.assertIn("-- install --", result.stdout)

    def test_doctor_reports_stale_store(self) -> None:
        """A store behind the current schema version reports stale, not ok."""
        home = self.use_fake_home()
        self.assert_ok(self.run_flow("setup", "machine"))

        import sqlite3

        conn = sqlite3.connect(self._store_path(home))
        try:
            conn.execute("PRAGMA user_version = 0")
            conn.commit()
        finally:
            conn.close()

        result = self.run_flow("doctor")
        self.assertIn("stale", result.stdout)
        self.assertIn("pending", result.stdout)

    def test_setup_machine_migrates_a_stale_store(self) -> None:
        """setup machine is the repair path — develop installs have no other one."""
        home = self.use_fake_home()
        self.assert_ok(self.run_flow("setup", "machine"))

        import sqlite3

        store = self._store_path(home)
        conn = sqlite3.connect(store)
        try:
            # Every table any migration has ever created, torn down to simulate
            # a store at v0. Forgetting one here (as happened when v2 added
            # agent_activity_raw) makes re-migration fail on "table already
            # exists" rather than testing what this test means to test.
            conn.execute("DROP TABLE agent_activity_raw")
            conn.execute("DROP TABLE turn_norm")
            conn.execute("DROP TABLE turn_raw")
            conn.execute("DROP TABLE session")
            conn.execute("DROP TABLE harvest")
            conn.execute("DROP TABLE harness_capability")
            conn.execute("DROP TABLE schema_migration")
            conn.execute("PRAGMA user_version = 0")
            conn.commit()
        finally:
            conn.close()

        result = self.run_flow("setup", "machine")
        self.assert_ok(result)
        self.assertIn("usage store: migrated to v", result.stdout)

        usage_store = self._load_store_module()
        status = usage_store.store_status(store)
        self.assertEqual(status["state"], usage_store.STATE_EMPTY)

    def _load_cli_module(self, name: str):
        """Import a cli/ module directly, leaving sys.path and sys.modules as found.

        cli/ modules import each other by bare name, which only resolves with
        cli/ on sys.path. flow.py arranges that for itself at import time; a
        direct load does not, so this does it — and then puts everything back.

        Restoring sys.modules matters as much as sys.path. Loading these binds
        generic top-level names (`paths`, `setup`, `sync`, `render`) in the test
        process, where they would shadow any same-named module a later import
        wanted. Two tests already load modules this way and more will.
        """
        import importlib.util

        cli_dir = str(REPO_ROOT / "cli")
        saved_modules = dict(sys.modules)
        sys.path.insert(0, cli_dir)
        try:
            spec = importlib.util.spec_from_file_location(
                f"flow_cli_{name}_under_test", REPO_ROOT / "cli" / f"{name}.py"
            )
            module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            assert spec and spec.loader
            spec.loader.exec_module(module)  # type: ignore[union-attr]
            return module
        finally:
            sys.path.remove(cli_dir)
            for added in set(sys.modules) - set(saved_modules):
                del sys.modules[added]

    def test_release_staging_requires_cli_siblings(self) -> None:
        """A release shipping the launcher without its siblings installs then breaks."""
        lifecycle = self._load_cli_module("lifecycle")

        staging = self.repo / "staging"
        (staging / "cli").mkdir(parents=True)
        # The required sibling set is read out of the staged entrypoint itself,
        # so the entrypoint has to declare something for there to be anything to
        # miss. `os` is here to prove stdlib names are filtered rather than
        # looked for under cli/.
        (staging / "cli" / "flow.py").write_text(
            "import os\n"
            "import usage_store\n"
            "from render import codex_skill_dir\n"
        )
        (staging / "scaffolds" / "default").mkdir(parents=True)
        (staging / "scaffolds" / "default" / "flow.toml").write_text("")
        (staging / "data").mkdir(parents=True)
        (staging / "data" / "harness_capabilities.json").write_text(
            '{"capabilities": []}'
        )

        # Assert on the derived set directly. Checking only the rejection
        # message would pass or fail on which missing sibling happens to be
        # reported first, and would say nothing about whether `os` was filtered.
        self.assertEqual(
            lifecycle._declared_sibling_imports(staging / "cli" / "flow.py"),
            ["usage_store", "render"],
            "stdlib names must be filtered; siblings must be kept in order",
        )

        reason = lifecycle._validate_staging(staging)
        self.assertIsNotNone(reason, "staging without cli siblings must be rejected")
        self.assertIn("usage_store.py", reason)

        (staging / "cli" / "usage_store.py").write_text("# sibling")
        reason = lifecycle._validate_staging(staging)
        self.assertIsNotNone(reason, "the second declared sibling is still missing")
        self.assertIn("render.py", reason)

        (staging / "cli" / "render.py").write_text("# sibling")
        self.assertIsNone(
            lifecycle._validate_staging(staging),
            "staging with all required files should validate",
        )

    def test_release_staging_rejects_unparseable_entrypoint(self) -> None:
        """A corrupt flow.py must be rejected, not silently swapped into place."""
        lifecycle = self._load_cli_module("lifecycle")

        staging = self.repo / "staging_corrupt"
        (staging / "cli").mkdir(parents=True)
        # Truncated mid-statement — the shape a partial download leaves behind.
        (staging / "cli" / "flow.py").write_text("from setup import (\n")
        (staging / "scaffolds" / "default").mkdir(parents=True)
        (staging / "scaffolds" / "default" / "flow.toml").write_text("")
        (staging / "data").mkdir(parents=True)
        (staging / "data" / "harness_capabilities.json").write_text(
            '{"capabilities": []}'
        )

        reason = lifecycle._validate_staging(staging)
        self.assertIsNotNone(reason, "an unparseable entrypoint must be rejected")
        self.assertIn("does not parse", reason)

    def test_release_staging_accepts_a_future_third_party_dependency(self) -> None:
        """An installed release must not reject a later one for taking a dependency.

        This validation runs from the *installed* version against a *newer*
        staged tree. If it assumed every non-stdlib import were a flow module,
        a future release that started importing a real package would be
        rejected by every existing install — and the fix could not be shipped,
        because the rejecting code is the installed code. Same shape as the P8
        whitelist trap.

        `json` would be filtered as stdlib, so the dependency here is faked with
        a package that exists on sys.path but not under the staged cli/.
        """
        lifecycle = self._load_cli_module("lifecycle")

        deps = self.repo / "site-packages"
        (deps / "pretend_dep").mkdir(parents=True)
        (deps / "pretend_dep" / "__init__.py").write_text("")

        staging = self.repo / "staging_future"
        (staging / "cli").mkdir(parents=True)
        (staging / "cli" / "flow.py").write_text(
            "import pretend_dep\nimport usage_store\n"
        )
        (staging / "cli" / "usage_store.py").write_text("# sibling")
        (staging / "scaffolds" / "default").mkdir(parents=True)
        (staging / "scaffolds" / "default" / "flow.toml").write_text("")
        (staging / "data").mkdir(parents=True)
        (staging / "data" / "harness_capabilities.json").write_text(
            '{"capabilities": []}'
        )

        # Not importable anywhere: indistinguishable from a broken tree, and a
        # dependency flow could not import either. Rejecting is correct.
        reason = lifecycle._validate_staging(staging)
        self.assertIsNotNone(reason, "an unresolvable import must be rejected")
        self.assertIn("pretend_dep", reason)

        # Installed: the release is fine, and must be accepted by old code that
        # has never heard of it.
        sys.path.insert(0, str(deps))
        try:
            self.assertIsNone(
                lifecycle._validate_staging(staging),
                "an installed third-party dependency must not read as a "
                "missing cli/ sibling",
            )
        finally:
            sys.path.remove(str(deps))

    def test_release_staging_ignores_the_running_install_when_resolving(self) -> None:
        """The current install must not vouch for a module absent from staging.

        Every flow module is importable from the running cli/ directory while
        this check runs. If that directory counted as "resolvable", a staged
        tree missing cli/paths.py would be waved through by the very install the
        update is about to replace.
        """
        lifecycle = self._load_cli_module("lifecycle")
        running_cli = REPO_ROOT / "cli"

        sys.path.insert(0, str(running_cli))
        try:
            self.assertFalse(
                lifecycle._resolves_in_environment("paths", running_cli.resolve()),
                "the running cli/ directory must be excluded from resolution",
            )
            self.assertTrue(
                lifecycle._resolves_in_environment("paths", Path("/nonexistent")),
                "control: without the exclusion it would resolve",
            )
        finally:
            sys.path.remove(str(running_cli))

    def test_release_staging_requires_every_real_cli_sibling(self) -> None:
        """Regression guard: the check must reject the real tree minus any one module.

        Two properties, and the second is the one that is easy to lose. First,
        the hand-maintained roster this replaced named one file while flow.py
        needed six, so the check has to derive its set rather than carry it.
        Second, it has to follow imports transitively: flow.py imports only
        four modules directly, and a depth-one check would happily accept a
        release with cli/paths.py missing and then die on the first command.

        Every module under cli/ is removed in turn, so a future module cannot
        quietly fall outside the check. That is deliberate even though it means
        a cli/ module reachable only from somewhere other than flow.py — a hook
        entry point, say — would fail this test. Such a module would also be
        omitted from staging validation, so the right response is to make it
        reachable or teach the validator about it, not to weaken this loop.
        """
        lifecycle = self._load_cli_module("lifecycle")

        staging = self.repo / "staging_real"
        shutil.copytree(REPO_ROOT / "cli", staging / "cli")
        (staging / "scaffolds" / "default").mkdir(parents=True)
        (staging / "scaffolds" / "default" / "flow.toml").write_text("")
        (staging / "data").mkdir(parents=True)
        (staging / "data" / "harness_capabilities.json").write_text(
            '{"capabilities": []}'
        )

        self.assertIsNone(
            lifecycle._validate_staging(staging),
            "a complete copy of cli/ must validate",
        )

        victims = sorted(
            p.stem for p in (REPO_ROOT / "cli").glob("*.py") if p.stem != "flow"
        )
        # paths/fsutil/render/flowtoml reach flow.py only through another
        # module, so they are what proves the walk is transitive rather than
        # depth-one. Asserting the exact set means adding a cli/ module fails
        # here until someone confirms it is covered.
        self.assertEqual(
            victims,
            [
                "claude_collector",
                "codex_collector",
                "cost",
                "diagnostics",
                "flowtoml",
                "fsutil",
                "harvest",
                "hookio",
                "jsonl_watermark",
                "lifecycle",
                "normalize",
                "overlay",
                "paths",
                "render",
                "session_lookup",
                "setup",
                "sync",
                "usage_store",
            ],
        )

        for victim in victims:
            path = staging / "cli" / f"{victim}.py"
            body = path.read_text()
            path.unlink()
            reason = lifecycle._validate_staging(staging)
            self.assertIsNotNone(reason, f"removing cli/{victim}.py must be rejected")
            self.assertIn(f"{victim}.py", reason)
            path.write_text(body)

    def test_harvest_codex_end_to_end_via_cli(self) -> None:
        """`flow harvest codex` against a fixture-backed fake HOME, matching this
        class's subprocess convention rather than CodexCollectorTests's direct
        in-memory-store convention — this is the one test proving the CLI
        wiring (argparse, ensure_store, path resolution) works, not the
        collector logic itself.
        """
        home = self.use_fake_home()
        sessions_dir = home / ".codex" / "sessions" / "2026" / "01" / "01"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "rollout-test.jsonl").write_text(
            _jsonl(
                _session_meta("sess-1"),
                _task_started("turn-1"),
                _turn_context("turn-1", "gpt-5.6"),
                _token_count(),
                _task_complete("turn-1"),
            )
        )

        result = self.run_flow("harvest", "codex")
        self.assert_ok(result)
        self.assertIn("1 files", result.stdout)
        self.assertIn("1 turns", result.stdout)

        store = self._store_path(home)
        self.assertTrue(store.is_file())
        usage_store = self._load_store_module()
        status = usage_store.store_status(store)
        self.assertEqual(status["state"], usage_store.STATE_OK)
        self.assertEqual(status["user_version"], usage_store.SCHEMA_VERSION)

        # Idempotent from the CLI too.
        second = self.run_flow("harvest", "codex")
        self.assert_ok(second)
        self.assertIn("0 turns", second.stdout)

    def test_harvest_codex_without_sessions_dir_is_a_clean_no_op(self) -> None:
        home = self.use_fake_home()
        result = self.run_flow("harvest", "codex")
        self.assert_ok(result)
        self.assertIn("no Codex sessions found", result.stdout)

    def test_harvest_claude_end_to_end_via_cli(self) -> None:
        home = self.use_fake_home()
        sessions_dir = home / ".claude" / "projects" / "-tmp-proj"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "sess-1.jsonl").write_text(
            _jsonl(_claude_user("sess-1"), _claude_assistant("sess-1", "req-1"))
        )
        result = self.run_flow("harvest", "claude")
        self.assert_ok(result)
        self.assertIn("1 turns", result.stdout)

        store = self._store_path(home)
        import sqlite3

        conn = sqlite3.connect(store)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM turn_raw").fetchone()[0], 1)
        conn.close()

        second = self.run_flow("harvest", "claude")
        self.assert_ok(second)
        self.assertIn("0 turns", second.stdout)

    def test_harvest_claude_without_sessions_dir_is_a_clean_no_op(self) -> None:
        self.use_fake_home()
        result = self.run_flow("harvest", "claude")
        self.assert_ok(result)
        self.assertIn("no Claude Code sessions found", result.stdout)

    def test_normalize_end_to_end_via_cli(self) -> None:
        home = self.use_fake_home()
        sessions_dir = home / ".codex" / "sessions" / "2026" / "01" / "01"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "rollout-test.jsonl").write_text(
            _jsonl(
                _session_meta("sess-1"),
                _task_started("turn-1"),
                _turn_context("turn-1", "gpt-5.6"),
                _token_count(),
                _task_complete("turn-1"),
            )
        )
        self.assert_ok(self.run_flow("harvest", "codex"))

        result = self.run_flow("normalize")
        self.assert_ok(result)
        self.assertIn("1 rows", result.stdout)

        store = self._store_path(home)
        # store_status doesn't expose turn_norm counts; check the table directly.
        import sqlite3

        conn = sqlite3.connect(store)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM turn_norm").fetchone()[0], 1)
        conn.close()

        # Idempotent from the CLI too.
        second = self.run_flow("normalize")
        self.assert_ok(second)
        self.assertIn("0 rows", second.stdout)

    def test_normalize_ensures_the_store_on_a_fresh_machine(self) -> None:
        """flow normalize must work standalone, like flow harvest codex does."""
        self.use_fake_home()
        result = self.run_flow("normalize")
        self.assert_ok(result)
        self.assertIn("0 rows", result.stdout)

    def test_cost_summary_end_to_end_via_cli(self) -> None:
        """`flow cost summary` against real harvested-and-normalized data, both
        render modes. Uses `--all`, matching every other fixture in this
        class: their timestamps are fixed at 2026-01-01, far outside any
        `--days` default window relative to whenever this test actually runs.
        """
        home = self.use_fake_home()
        codex_dir = home / ".codex" / "sessions" / "2026" / "01" / "01"
        codex_dir.mkdir(parents=True)
        (codex_dir / "rollout-test.jsonl").write_text(
            _jsonl(
                _session_meta("sess-1"),
                _task_started("turn-1"),
                _turn_context("turn-1", "gpt-5.6"),
                _token_count(
                    rate_limits={
                        "primary": {"used_percent": 41.0, "window_minutes": 300, "resets_at": 123},
                        "secondary": {"used_percent": 12.0, "window_minutes": 10080, "resets_at": 456},
                    }
                ),
                _task_complete("turn-1"),
            )
        )
        claude_dir = home / ".claude" / "projects" / "-tmp-proj"
        claude_dir.mkdir(parents=True)
        (claude_dir / "sess-1.jsonl").write_text(
            _jsonl(_claude_user("sess-1"), _claude_assistant("sess-1", "req-1"))
        )
        self.assert_ok(self.run_flow("harvest", "codex"))
        self.assert_ok(self.run_flow("harvest", "claude"))
        self.assert_ok(self.run_flow("normalize"))

        table = self.run_flow("cost", "summary", "--all")
        self.assert_ok(table)
        self.assertIn("HARNESS", table.stdout)
        self.assertIn("codex", table.stdout)
        self.assertIn("claude", table.stdout)
        self.assertIn("codex capacity", table.stdout)
        self.assertIn("300m window 41.0%", table.stdout)
        self.assertIn("10080m window 12.0%", table.stdout)

        as_json = self.run_flow("cost", "summary", "--all", "--json")
        self.assert_ok(as_json)
        payload = json.loads(as_json.stdout)
        self.assertEqual(len(payload["rows"]), 2)
        harnesses = {row["harness"] for row in payload["rows"]}
        self.assertEqual(harnesses, {"codex", "claude"})
        self.assertEqual(payload["capacity"]["capacity_primary_used_pct"], 41.0)
        self.assertEqual(payload["capacity"]["capacity_secondary_used_pct"], 12.0)

    def test_cost_sessions_end_to_end_via_cli(self) -> None:
        home = self.use_fake_home()
        claude_dir = home / ".claude" / "projects" / "-tmp-proj"
        claude_dir.mkdir(parents=True)
        (claude_dir / "sess-1.jsonl").write_text(
            _jsonl(
                _claude_user("sess-1"),
                _claude_custom_title("sess-1", "My Renamed Session"),
                _claude_assistant("sess-1", "req-1"),
            )
        )
        self.assert_ok(self.run_flow("harvest", "claude"))
        self.assert_ok(self.run_flow("normalize"))

        table = self.run_flow("cost", "sessions", "--all")
        self.assert_ok(table)
        self.assertIn("My Renamed Session", table.stdout)

        as_json = self.run_flow("cost", "sessions", "--all", "--json")
        self.assert_ok(as_json)
        payload = json.loads(as_json.stdout)
        # Same {"rows": [...]} envelope as `cost summary --json`.
        self.assertEqual(len(payload["rows"]), 1)
        self.assertEqual(payload["rows"][0]["label"], "My Renamed Session")
        self.assertEqual(payload["rows"][0]["harness"], "claude")

    def test_cost_sessions_limit_end_to_end_via_cli(self) -> None:
        home = self.use_fake_home()
        claude_dir = home / ".claude" / "projects" / "-tmp-proj"
        claude_dir.mkdir(parents=True)
        for i in range(25):
            (claude_dir / f"sess-{i}.jsonl").write_text(
                _jsonl(_claude_user(f"sess-{i}"), _claude_assistant(f"sess-{i}", f"req-{i}"))
            )
        self.assert_ok(self.run_flow("harvest", "claude"))
        self.assert_ok(self.run_flow("normalize"))

        default = self.run_flow("cost", "sessions", "--all", "--json")
        self.assert_ok(default)
        self.assertEqual(len(json.loads(default.stdout)["rows"]), 20)

        limited = self.run_flow("cost", "sessions", "--all", "--limit", "5", "--json")
        self.assert_ok(limited)
        self.assertEqual(len(json.loads(limited.stdout)["rows"]), 5)

        unlimited = self.run_flow("cost", "sessions", "--all", "--limit", "0", "--json")
        self.assert_ok(unlimited)
        self.assertEqual(len(json.loads(unlimited.stdout)["rows"]), 25)

    def test_cost_active_end_to_end_via_cli(self) -> None:
        """`flow cost active` harvests AND normalizes internally — this test
        deliberately never calls `flow harvest`/`flow normalize`, proving
        the pipeline-first behavior end to end. Needs a near-now timestamp
        (unlike every other fixture in this class) because `active` filters
        on real wall-clock recency.
        """
        from datetime import datetime, timezone

        home = self.use_fake_home()
        claude_dir = home / ".claude" / "projects" / "-tmp-proj"
        claude_dir.mkdir(parents=True)
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        fresh = _claude_assistant("sess-live", "req-1", input_tokens=100_000)
        fresh["timestamp"] = now_iso
        (claude_dir / "sess-live.jsonl").write_text(_jsonl(_claude_user("sess-live"), fresh))

        as_json = self.run_flow("cost", "active", "--json")
        self.assert_ok(as_json)
        payload = json.loads(as_json.stdout)
        self.assertEqual(len(payload["rows"]), 1)
        row = payload["rows"][0]
        self.assertEqual(row["session_id"], "sess-live")
        self.assertEqual(row["ctx_pct"], 50.0)  # 100K of the assumed 200K window
        self.assertEqual(row["recommend"], "fine")  # single turn: carry 0

        table = self.run_flow("cost", "active")
        self.assert_ok(table)
        self.assertIn("RECOMMEND", table.stdout)
        self.assertIn("fine", table.stdout)

    def test_cost_active_with_only_stale_sessions_is_a_clean_empty_result(self) -> None:
        home = self.use_fake_home()
        claude_dir = home / ".claude" / "projects" / "-tmp-proj"
        claude_dir.mkdir(parents=True)
        # The shared fixture's fixed 2026-01-01 timestamp is guaranteed stale.
        (claude_dir / "sess-old.jsonl").write_text(
            _jsonl(_claude_user("sess-old"), _claude_assistant("sess-old", "req-1"))
        )
        result = self.run_flow("cost", "active")
        self.assert_ok(result)
        self.assertIn("no active sessions", result.stdout)

    def test_cost_summary_with_no_data_is_a_clean_empty_result(self) -> None:
        self.use_fake_home()
        table = self.run_flow("cost", "summary", "--all")
        self.assert_ok(table)
        self.assertIn("no data", table.stdout)

        as_json = self.run_flow("cost", "summary", "--all", "--json")
        self.assert_ok(as_json)
        payload = json.loads(as_json.stdout)
        self.assertEqual(payload["rows"], [])
        self.assertNotIn("capacity", payload)

    def test_cost_summary_default_window_excludes_data_outside_it(self) -> None:
        """The actual default invocation — no `--all`, no `--days` — is what
        every other CLI-boundary test in this class deliberately avoids
        (their fixtures are fixed at 2026-01-01, so they always pass `--all`
        to include it). This one uses `flow harvest`'s real ingestion
        timestamp instead of a fixed date, so the default 7-day window has
        something real to exclude: a session harvested with an ancient
        `--all`-only-visible timestamp.
        """
        home = self.use_fake_home()
        codex_dir = home / ".codex" / "sessions" / "2020" / "01" / "01"
        codex_dir.mkdir(parents=True)
        (codex_dir / "rollout-test.jsonl").write_text(
            _jsonl(
                _session_meta("sess-1"),
                _task_started("turn-1"),
                _turn_context("turn-1", "gpt-5.6"),
                {**_token_count(), "timestamp": "2020-01-01T00:00:01Z"},
                _task_complete("turn-1"),
            )
        )
        self.assert_ok(self.run_flow("harvest", "codex"))
        self.assert_ok(self.run_flow("normalize"))

        # No --all, no --days: the default 7-day window.
        result = self.run_flow("cost", "summary")
        self.assert_ok(result)
        self.assertIn("no data", result.stdout)

        # The same data is visible with --all, proving it was really there.
        all_time = self.run_flow("cost", "summary", "--all")
        self.assert_ok(all_time)
        self.assertIn("codex", all_time.stdout)


def _jsonl(*records: dict) -> str:
    """One JSON object per line, newline-terminated — a well-formed Codex session file."""
    return "".join(json.dumps(r) + "\n" for r in records)


def _session_meta(session_id: str, cwd: str = "/tmp/proj", source=None) -> dict:
    payload = {"id": session_id, "timestamp": "2026-01-01T00:00:00Z", "cwd": cwd}
    if source is not None:
        payload["source"] = source
    return {"timestamp": "2026-01-01T00:00:00Z", "type": "session_meta", "payload": payload}


def _task_started(turn_id: str) -> dict:
    return {
        "timestamp": "2026-01-01T00:00:01Z",
        "type": "event_msg",
        "payload": {"type": "task_started", "turn_id": turn_id},
    }


def _turn_context(turn_id: str, model: str) -> dict:
    return {
        "timestamp": "2026-01-01T00:00:01Z",
        "type": "turn_context",
        "payload": {"turn_id": turn_id, "model": model},
    }


def _task_complete(turn_id: str) -> dict:
    return {
        "timestamp": "2026-01-01T00:00:02Z",
        "type": "event_msg",
        "payload": {"type": "task_complete", "turn_id": turn_id},
    }


def _token_count(total: int = 100, rate_limits: dict | None = None) -> dict:
    payload = {
        "type": "token_count",
        "info": {"last_token_usage": {"input_tokens": total, "output_tokens": 1, "total_tokens": total + 1}},
    }
    if rate_limits is not None:
        payload["rate_limits"] = rate_limits
    return {
        "timestamp": "2026-01-01T00:00:01Z",
        "type": "event_msg",
        "payload": payload,
    }


def _sub_agent_activity(agent_thread_id: str, agent_path: str, kind: str = "started") -> dict:
    return {
        "timestamp": "2026-01-01T00:00:01Z",
        "type": "event_msg",
        "payload": {
            "type": "sub_agent_activity",
            "kind": kind,
            "agent_thread_id": agent_thread_id,
            "agent_path": agent_path,
        },
    }


def _claude_user(session_id: str, cwd: str = "/tmp/proj") -> dict:
    return {
        "type": "user",
        "sessionId": session_id,
        "cwd": cwd,
        "timestamp": "2026-01-01T00:00:00Z",
        "message": {"content": "hello"},
    }


def _claude_assistant(
    session_id: str,
    request_id: str,
    model: str = "claude-sonnet-5",
    input_tokens: int = 100,
    cache_read: int | None = 0,
    cache_write: int | None = 0,
    output_tokens: int = 10,
    cwd: str = "/tmp/proj",
    is_sidechain: bool = False,
) -> dict:
    usage = {"input_tokens": input_tokens, "output_tokens": output_tokens}
    if cache_read is not None:
        usage["cache_read_input_tokens"] = cache_read
    if cache_write is not None:
        usage["cache_creation_input_tokens"] = cache_write
    return {
        "type": "assistant",
        "sessionId": session_id,
        "cwd": cwd,
        "requestId": request_id,
        "isSidechain": is_sidechain,
        "timestamp": "2026-01-01T00:00:01Z",
        "message": {"model": model, "usage": usage},
    }


def _claude_custom_title(session_id: str, title: str) -> dict:
    # No `timestamp` field — matches real data exactly. All 6,340 real
    # custom-title/ai-title records sampled while building schema v4 carry
    # only {type, aiTitle|customTitle, sessionId}, nothing else. An earlier
    # version of this fixture included a timestamp that no real record has,
    # which would have made last_seen_ts tests pass for the wrong reason.
    return {"type": "custom-title", "sessionId": session_id, "customTitle": title}


def _claude_ai_title(session_id: str, title: str) -> dict:
    return {"type": "ai-title", "sessionId": session_id, "aiTitle": title}


class CodexCollectorTests(unittest.TestCase):
    """Direct tests of cli/codex_collector.py, against an in-memory store.

    No CLI, no fake HOME — codex_collector takes every path explicitly, so
    these run against a plain sqlite3 in-memory connection with the real
    migrations applied. The one CLI-boundary test lives in FlowCliTests below,
    matching that class's existing subprocess-driven convention.
    """

    def setUp(self) -> None:
        import sqlite3

        self._tempdir = tempfile.TemporaryDirectory()
        self.dir = Path(self._tempdir.name)
        REPO_ROOT_CLI = REPO_ROOT / "cli"
        if str(REPO_ROOT_CLI) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT_CLI))
            self._added_cli_path = True
        else:
            self._added_cli_path = False
        import usage_store
        import codex_collector

        self.usage_store = usage_store
        self.codex_collector = codex_collector
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON")
        for _version, _description, sql in usage_store.MIGRATIONS:
            self.conn.executescript(sql)

    def tearDown(self) -> None:
        self.conn.close()
        self._tempdir.cleanup()
        if self._added_cli_path:
            sys.path.remove(str(REPO_ROOT / "cli"))
        for name in ("usage_store", "codex_collector"):
            sys.modules.pop(name, None)

    def write_session(self, name: str, content: str) -> Path:
        path = self.dir / name
        path.write_text(content)
        return path

    def turn_raw_rows(self) -> list[tuple]:
        return list(
            self.conn.execute(
                "SELECT natural_turn_id, turn_seq, is_subagent, model FROM turn_raw ORDER BY turn_seq"
            )
        )

    # ------------------------------------------------------------------
    # attribution
    # ------------------------------------------------------------------

    def test_multiple_token_counts_in_one_turn_are_distinct_rows(self) -> None:
        """The finding that changed the natural-key design: one turn, several calls."""
        path = self.write_session(
            "a.jsonl",
            _jsonl(
                _session_meta("sess-1"),
                _task_started("turn-1"),
                _turn_context("turn-1", "gpt-5.6"),
                _token_count(100),
                _token_count(200),
                _token_count(300),
                _task_complete("turn-1"),
            ),
        )
        result = self.codex_collector.harvest_file(self.conn, path)
        self.assertEqual(result["turns"], 3)
        self.assertIsNone(result["hard_stop"])
        rows = self.turn_raw_rows()
        self.assertEqual(len(rows), 3)
        # Distinct natural keys, all attributed to the one open turn's model.
        self.assertEqual(len({r[0] for r in rows}), 3)
        self.assertTrue(all(r[3] == "gpt-5.6" for r in rows))

    def test_model_is_null_when_turn_context_has_not_arrived_yet(self) -> None:
        """Absence, not a crash, when turn_context hasn't shown up for the open turn."""
        path = self.write_session(
            "a.jsonl",
            _jsonl(
                _session_meta("sess-1"),
                _task_started("turn-1"),
                _token_count(),  # turn_context never arrives in this fixture
            ),
        )
        result = self.codex_collector.harvest_file(self.conn, path)
        self.assertEqual(result["turns"], 1)
        rows = self.turn_raw_rows()
        self.assertIsNone(rows[0][3])

    def test_token_count_before_any_turn_uses_untracked_key(self) -> None:
        """A token_count with no open turn still gets a stable, unique row."""
        path = self.write_session("a.jsonl", _jsonl(_session_meta("sess-1"), _token_count()))
        result = self.codex_collector.harvest_file(self.conn, path)
        self.assertEqual(result["turns"], 1)
        self.assertTrue(self.turn_raw_rows()[0][0].startswith("untracked:"))

    # ------------------------------------------------------------------
    # lineage — the subagent shape, including the bug this run found
    # ------------------------------------------------------------------

    def test_parent_session_id_extracted_from_thread_spawn(self) -> None:
        path = self.write_session(
            "child.jsonl",
            _jsonl(
                _session_meta(
                    "child-1",
                    source={"subagent": {"thread_spawn": {"parent_thread_id": "parent-1", "agent_path": "/root/x"}}},
                ),
                _task_started("turn-1"),
                _token_count(),
            ),
        )
        self.codex_collector.harvest_file(self.conn, path)
        row = self.conn.execute(
            "SELECT parent_session_id FROM session WHERE session_id = 'child-1'"
        ).fetchone()
        self.assertEqual(row[0], "parent-1")
        self.assertEqual(self.turn_raw_rows()[0][2], 1, "is_subagent must be true for every turn in a child session")

    def test_plain_session_has_no_parent_and_is_not_subagent(self) -> None:
        path = self.write_session(
            "plain.jsonl", _jsonl(_session_meta("sess-1", source="vscode"), _task_started("t"), _token_count())
        )
        self.codex_collector.harvest_file(self.conn, path)
        row = self.conn.execute("SELECT parent_session_id FROM session WHERE session_id = 'sess-1'").fetchone()
        self.assertIsNone(row[0])
        self.assertEqual(self.turn_raw_rows()[0][2], 0)

    def test_second_session_meta_for_the_parent_does_not_hijack_attribution(self) -> None:
        """Regression test for the bug this implementation run found against real data.

        A subagent's file carries a second session_meta shortly after its own
        — a verbatim copy of the PARENT's, injected so the child's transcript
        is self-contained. Confirmed against 35 real files. Locking identity
        to the first session_meta only is what this test guards: without that
        guard, every record after the parent's injected copy misattributes to
        the parent's session instead of the child's — which on real data
        silently dropped roughly half of every affected session's rows via
        the natural-key uniqueness constraint, with no error raised anywhere.
        """
        path = self.write_session(
            "child.jsonl",
            _jsonl(
                _session_meta(
                    "child-1",
                    source={"subagent": {"thread_spawn": {"parent_thread_id": "parent-1", "agent_path": "/root/x"}}},
                ),
                _session_meta("parent-1", source="vscode"),  # injected copy of the parent's own record
                _task_started("turn-1"),
                _turn_context("turn-1", "gpt-5.6"),
                _token_count(),
            ),
        )
        result = self.codex_collector.harvest_file(self.conn, path)
        self.assertEqual(result["turns"], 1)

        child_id = self.conn.execute("SELECT id FROM session WHERE session_id = 'child-1'").fetchone()[0]
        row = self.conn.execute("SELECT session_row_id FROM turn_raw").fetchone()
        self.assertEqual(row[0], child_id, "the turn must attribute to the child, not the injected parent record")
        # The injected copy must not spawn its own session row either — this
        # file is the child's; the parent's own row comes from harvesting the
        # parent's own file, which real data confirms always exists separately.
        parent_row = self.conn.execute("SELECT id FROM session WHERE session_id = 'parent-1'").fetchone()
        self.assertIsNone(parent_row)

    def test_second_session_meta_across_a_batch_boundary_does_not_hijack_attribution(self) -> None:
        """Same bug as above, but reproduced the way it actually happened.

        The single-file version of this test caught the bug within one batch,
        but session identity used to be resolved lazily — from whatever
        session_meta the loop hit first in THAT CALL — which only matched the
        file's own identity by coincidence of both lines landing in the same
        batch. Split the harvest so the child's own session_meta commits in
        run A and the parent's injected copy is the first session_meta-typed
        record run B ever sees, and the bug reappeared: every record in run B
        misattributed to the parent. Fixed by resolving identity once, up
        front, via `_lookup_session_for_path` rather than lazily inside the
        loop — this test is what proves that fix holds across the boundary,
        not just within one batch.
        """
        path = self.write_session(
            "child.jsonl",
            _jsonl(
                _session_meta(
                    "child-1",
                    source={"subagent": {"thread_spawn": {"parent_thread_id": "parent-1", "agent_path": "/root/x"}}},
                ),
            ),
        )
        first = self.codex_collector.harvest_file(self.conn, path)
        self.assertIsNone(first["hard_stop"])

        with path.open("a") as fh:
            fh.write(
                _jsonl(
                    _session_meta("parent-1", source="vscode"),
                    _task_started("turn-1"),
                    _turn_context("turn-1", "gpt-5.6"),
                    _token_count(),
                )
            )
        second = self.codex_collector.harvest_file(self.conn, path)
        self.assertEqual(second["turns"], 1)

        child_id = self.conn.execute("SELECT id FROM session WHERE session_id = 'child-1'").fetchone()[0]
        row = self.conn.execute("SELECT session_row_id FROM turn_raw").fetchone()
        self.assertEqual(row[0], child_id, "run B must still attribute to the child established in run A")
        self.assertIsNone(
            self.conn.execute("SELECT id FROM session WHERE session_id = 'parent-1'").fetchone()
        )

    # ------------------------------------------------------------------
    # state-machine ordering and robustness
    # ------------------------------------------------------------------

    def test_turn_context_arriving_before_task_started_still_attributes_model(self) -> None:
        path = self.write_session(
            "a.jsonl",
            _jsonl(
                _session_meta("sess-1"),
                _turn_context("turn-1", "gpt-5.6"),  # arrives first, out of the "usual" order
                _task_started("turn-1"),
                _token_count(),
            ),
        )
        result = self.codex_collector.harvest_file(self.conn, path)
        self.assertEqual(result["turns"], 1)
        self.assertEqual(self.turn_raw_rows()[0][3], "gpt-5.6")

    def test_stale_task_complete_does_not_close_a_newer_open_turn(self) -> None:
        """A task_complete for a turn that isn't open must not close whatever is."""
        path = self.write_session(
            "a.jsonl",
            _jsonl(
                _session_meta("sess-1"),
                _task_started("turn-1"),
                _task_complete("turn-0"),  # some earlier, already-closed turn
                _turn_context("turn-1", "gpt-5.6"),
                _token_count(),
            ),
        )
        result = self.codex_collector.harvest_file(self.conn, path)
        self.assertEqual(result["turns"], 1)
        self.assertEqual(self.turn_raw_rows()[0][3], "gpt-5.6", "turn-1 must still be open when token_count arrives")

    def test_non_dict_json_is_a_hard_stop_not_a_crash(self) -> None:
        """Valid JSON, wrong shape: `123` parses cleanly but has no `.get()`."""
        path = self.write_session("a.jsonl", _jsonl(_session_meta("sess-1")) + "123\n")
        result = self.codex_collector.harvest_file(self.conn, path)
        self.assertIsNotNone(result["hard_stop"])
        self.assertEqual(result["hard_stop"]["line"], 2)

    def test_missing_required_field_is_a_hard_stop_not_a_crash(self) -> None:
        """A record missing `timestamp` would violate turn_raw.ts NOT NULL."""
        bad_token_count = _token_count()
        del bad_token_count["timestamp"]
        path = self.write_session(
            "a.jsonl", _jsonl(_session_meta("sess-1"), _task_started("t"), bad_token_count)
        )
        result = self.codex_collector.harvest_file(self.conn, path)
        self.assertIsNotNone(result["hard_stop"])
        self.assertIn("missing timestamp", result["hard_stop"]["reason"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM turn_raw").fetchone()[0], 0)

    def test_unattributable_records_are_counted_as_skipped_not_silently_dropped(self) -> None:
        """A file whose session can never be resolved must say so, not report a clean 0."""
        path = self.write_session("a.jsonl", _jsonl(_task_started("t"), _token_count()))
        result = self.codex_collector.harvest_file(self.conn, path)
        self.assertEqual(result["turns"], 0)
        self.assertEqual(result["skipped"], 2)

    def test_repeated_activity_insert_is_ignored_not_duplicated(self) -> None:
        """agent_activity_raw needs the same dedup shape as turn_raw for OR IGNORE to mean anything."""
        path = self.write_session(
            "a.jsonl", _jsonl(_session_meta("sess-1"), _sub_agent_activity("t", "/root/x"))
        )
        self.codex_collector.harvest_file(self.conn, path)
        # Re-run the same batch directly against _harvest_lines, bypassing the
        # watermark, to prove the constraint — not just the watermark — is
        # what prevents a duplicate.
        raw_lines, _, _ = self.codex_collector.read_new_lines(path, 0)
        self.codex_collector._harvest_lines(self.conn, path, raw_lines, 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM agent_activity_raw").fetchone()[0], 1)

    # ------------------------------------------------------------------
    # activity log
    # ------------------------------------------------------------------

    def test_sub_agent_activity_recorded_without_token_data(self) -> None:
        path = self.write_session(
            "a.jsonl",
            _jsonl(_session_meta("sess-1"), _sub_agent_activity("cloud-thread-1", "/root/validation_design")),
        )
        result = self.codex_collector.harvest_file(self.conn, path)
        self.assertEqual(result["activity"], 1)
        self.assertEqual(result["turns"], 0)
        row = self.conn.execute(
            "SELECT kind, agent_thread_id, agent_path FROM agent_activity_raw"
        ).fetchone()
        self.assertEqual(row, ("started", "cloud-thread-1", "/root/validation_design"))

    # ------------------------------------------------------------------
    # malformed-line rule
    # ------------------------------------------------------------------

    def test_malformed_line_before_the_last_stops_that_file_only(self) -> None:
        path = self.write_session(
            "bad.jsonl",
            _jsonl(_session_meta("sess-1"), _task_started("t"))
            + "not json\n"
            + _jsonl(_token_count()),
        )
        result = self.codex_collector.harvest_file(self.conn, path)
        self.assertIsNotNone(result["hard_stop"])
        self.assertEqual(result["hard_stop"]["line"], 3)
        self.assertEqual(result["turns"], 0)

    def test_malformed_line_reproduces_on_rerun_without_advancing(self) -> None:
        path = self.write_session(
            "bad.jsonl", _jsonl(_session_meta("sess-1")) + "not json\n" + _jsonl(_token_count())
        )
        first = self.codex_collector.harvest_file(self.conn, path)
        second = self.codex_collector.harvest_file(self.conn, path)
        self.assertEqual(first["hard_stop"], second["hard_stop"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM turn_raw").fetchone()[0], 0)

    def test_truncated_trailing_line_is_not_an_error(self) -> None:
        """A write in progress: no terminating newline on the last line."""
        content = _jsonl(_session_meta("sess-1")) + '{"type": "event_msg", "payload": {"type": "task_started"'
        path = self.write_session("live.jsonl", content)
        result = self.codex_collector.harvest_file(self.conn, path)
        self.assertIsNone(result["hard_stop"])
        row = self.conn.execute(
            "SELECT last_line_no FROM harvest WHERE source_path = ?", (str(path),)
        ).fetchone()
        self.assertEqual(row[0], 1, "must not advance past the incomplete trailing line")

    def test_truncated_line_completes_on_next_run(self) -> None:
        path = self.write_session(
            "live.jsonl",
            _jsonl(_session_meta("sess-1")) + '{"type": "event_msg", "payload": {"type": "task_started"',
        )
        self.codex_collector.harvest_file(self.conn, path)
        with path.open("a") as fh:
            fh.write(', "turn_id": "t"}}\n')
            fh.write(_jsonl(_turn_context("t", "gpt-5.6"), _token_count()))
        result = self.codex_collector.harvest_file(self.conn, path)
        self.assertIsNone(result["hard_stop"])
        self.assertEqual(result["turns"], 1)
        self.assertEqual(self.turn_raw_rows()[0][3], "gpt-5.6")

    # ------------------------------------------------------------------
    # idempotency and incremental append
    # ------------------------------------------------------------------

    def test_rerun_with_no_new_content_writes_nothing(self) -> None:
        path = self.write_session(
            "a.jsonl", _jsonl(_session_meta("sess-1"), _task_started("t"), _token_count())
        )
        self.codex_collector.harvest_file(self.conn, path)
        result = self.codex_collector.harvest_file(self.conn, path)
        self.assertEqual(result, {"turns": 0, "activity": 0, "skipped": 0, "hard_stop": None})
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM turn_raw").fetchone()[0], 1)

    def test_incremental_append_processes_only_new_lines(self) -> None:
        path = self.write_session(
            "a.jsonl", _jsonl(_session_meta("sess-1"), _task_started("t"), _token_count(1))
        )
        first = self.codex_collector.harvest_file(self.conn, path)
        self.assertEqual(first["turns"], 1)
        with path.open("a") as fh:
            fh.write(_jsonl(_token_count(2)))
        second = self.codex_collector.harvest_file(self.conn, path)
        self.assertEqual(second["turns"], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM turn_raw").fetchone()[0], 2)

    def test_watermark_anomaly_on_shrunk_file(self) -> None:
        path = self.write_session("a.jsonl", _jsonl(_session_meta("sess-1"), _task_started("t"), _token_count()))
        self.codex_collector.harvest_file(self.conn, path)
        path.write_text(_jsonl(_session_meta("sess-1")))  # shrank
        with self.assertRaises(self.codex_collector.WatermarkAnomaly):
            self.codex_collector.harvest_file(self.conn, path)

    # ------------------------------------------------------------------
    # harvest_all — cross-file isolation
    # ------------------------------------------------------------------

    def test_one_files_hard_stop_does_not_affect_another(self) -> None:
        sessions = self.dir / "sessions"
        sessions.mkdir()
        (sessions / "good.jsonl").write_text(
            _jsonl(_session_meta("sess-good"), _task_started("t"), _token_count())
        )
        (sessions / "bad.jsonl").write_text(_jsonl(_session_meta("sess-bad")) + "not json\n")
        summary = self.codex_collector.harvest_all(self.conn, sessions)
        self.assertEqual(summary["files"], 2)
        self.assertEqual(summary["turns"], 1)
        self.assertEqual(len(summary["failures"]), 1)
        self.assertIn("bad.jsonl", summary["failures"][0]["path"])

    def test_a_files_watermark_anomaly_does_not_abort_the_run(self) -> None:
        """WatermarkAnomaly is an exception, not a hard-stop return value — a
        different failure shape than a malformed line, and one harvest_all has
        to catch itself rather than rely on harvest_file to turn into a dict.
        """
        sessions = self.dir / "sessions"
        sessions.mkdir()
        good = sessions / "good.jsonl"
        good.write_text(_jsonl(_session_meta("sess-good"), _task_started("t"), _token_count()))
        shrunk = sessions / "shrunk.jsonl"
        shrunk.write_text(_jsonl(_session_meta("sess-shrunk"), _task_started("t"), _token_count()))

        summary = self.codex_collector.harvest_all(self.conn, sessions)
        self.assertEqual(summary["turns"], 2)
        self.assertEqual(summary["failures"], [])

        shrunk.write_text(_jsonl(_session_meta("sess-shrunk")))  # now smaller than its recorded watermark
        second = self.codex_collector.harvest_all(self.conn, sessions)
        self.assertEqual(second["files"], 2)
        self.assertEqual(len(second["failures"]), 1)
        self.assertIn("shrunk.jsonl", second["failures"][0]["path"])
        # The unaffected file must not be reprocessed or double-counted.
        self.assertEqual(second["turns"], 0)


class ClaudeCollectorTests(unittest.TestCase):
    """Direct tests of cli/claude_collector.py, against an in-memory store.

    Mirrors CodexCollectorTests's structure. Dedup here is by requestId, not
    an open-turn state machine — several assistant lines legitimately share
    one requestId (text, thinking, tool_use blocks of one API response), and
    the schema's own UNIQUE(session_row_id, natural_turn_id) constraint is
    the entire dedup mechanism; no extra bookkeeping needed.
    """

    def setUp(self) -> None:
        import sqlite3

        self._tempdir = tempfile.TemporaryDirectory()
        self.dir = Path(self._tempdir.name)
        REPO_ROOT_CLI = REPO_ROOT / "cli"
        if str(REPO_ROOT_CLI) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT_CLI))
            self._added_cli_path = True
        else:
            self._added_cli_path = False
        import usage_store
        import claude_collector

        self.usage_store = usage_store
        self.claude_collector = claude_collector
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON")
        for _version, _description, sql in usage_store.MIGRATIONS:
            self.conn.executescript(sql)

    def tearDown(self) -> None:
        self.conn.close()
        self._tempdir.cleanup()
        if self._added_cli_path:
            sys.path.remove(str(REPO_ROOT / "cli"))
        for name in ("usage_store", "claude_collector"):
            sys.modules.pop(name, None)

    def write_session(self, name: str, content: str) -> Path:
        path = self.dir / name
        path.write_text(content)
        return path

    def turn_raw_rows(self) -> list[tuple]:
        return list(
            self.conn.execute(
                "SELECT natural_turn_id, turn_seq, is_subagent, model FROM turn_raw ORDER BY turn_seq"
            )
        )

    # ------------------------------------------------------------------
    # dedup and attribution
    # ------------------------------------------------------------------

    def test_multiple_lines_sharing_a_request_id_dedupe_to_one_row(self) -> None:
        """The core reason this collector exists: one API response, several JSONL lines."""
        path = self.write_session(
            "a.jsonl",
            _jsonl(
                _claude_user("sess-1"),
                _claude_assistant("sess-1", "req-1"),  # text block
                _claude_assistant("sess-1", "req-1"),  # thinking block, same call
                _claude_assistant("sess-1", "req-1"),  # tool_use block, same call
                _claude_assistant("sess-1", "req-2"),  # a genuinely different call
            ),
        )
        result = self.claude_collector.harvest_file(self.conn, path)
        self.assertEqual(result["turns"], 2)
        self.assertIsNone(result["hard_stop"])
        rows = self.turn_raw_rows()
        self.assertEqual({r[0] for r in rows}, {"req-1", "req-2"})

    def test_is_subagent_derived_from_is_sidechain_per_record(self) -> None:
        """isSidechain does flag subagent turns — confirmed against 19,139 real records
        once the investigation actually looked inside subagents/ subdirectories.
        Per-record, not a session-level lookup: two rows in the same session
        can have different values.
        """
        path = self.write_session(
            "a.jsonl",
            _jsonl(
                _claude_user("sess-1"),
                _claude_assistant("sess-1", "req-1", is_sidechain=False),
                _claude_assistant("sess-1", "req-2", is_sidechain=True),
            ),
        )
        self.claude_collector.harvest_file(self.conn, path)
        rows = {r[0]: r[2] for r in self.turn_raw_rows()}
        self.assertEqual(rows["req-1"], 0)
        self.assertEqual(rows["req-2"], 1)

    def test_subagent_file_shares_the_parents_session_id(self) -> None:
        """A subagent file declares the parent's own sessionId, not a distinct
        one — confirmed against real data: session identity is shared, not
        linked via a parent_session_id back-reference the way Codex's is.

        Asserts the actual attribution, not just that one session row exists:
        both files' turns must land under that one session_row_id, and each
        must carry its own correct is_subagent — proving the shared-session
        design and the per-record is_subagent fix work together, not just
        that neither one crashed.
        """
        main = self.write_session(
            "main.jsonl", _jsonl(_claude_user("sess-shared"), _claude_assistant("sess-shared", "req-main"))
        )
        subagent = self.write_session(
            "agent-x.jsonl",
            _jsonl(_claude_assistant("sess-shared", "req-sub", is_sidechain=True)),
        )
        self.claude_collector.harvest_file(self.conn, main)
        self.claude_collector.harvest_file(self.conn, subagent)

        sessions = self.conn.execute(
            "SELECT id, parent_session_id FROM session WHERE session_id = 'sess-shared'"
        ).fetchall()
        self.assertEqual(len(sessions), 1, "both files must resolve to the same session row")
        session_row_id, parent_session_id = sessions[0]
        self.assertIsNone(parent_session_id)

        rows = self.conn.execute(
            "SELECT natural_turn_id, session_row_id, is_subagent FROM turn_raw ORDER BY natural_turn_id"
        ).fetchall()
        self.assertEqual(
            {r[1] for r in rows}, {session_row_id}, "both turns must attribute to the one shared session row"
        )
        by_id = {r[0]: r[2] for r in rows}
        self.assertEqual(by_id["req-main"], 0)
        self.assertEqual(by_id["req-sub"], 1)

    def test_model_extracted_from_message(self) -> None:
        path = self.write_session(
            "a.jsonl", _jsonl(_claude_user("sess-1"), _claude_assistant("sess-1", "req-1", model="claude-opus-5"))
        )
        self.claude_collector.harvest_file(self.conn, path)
        self.assertEqual(self.turn_raw_rows()[0][3], "claude-opus-5")

    def test_non_assistant_records_are_ordinary_content_not_skipped(self) -> None:
        """user/system/etc. carry no usage data — expected, not a shape violation."""
        path = self.write_session(
            "a.jsonl", _jsonl(_claude_user("sess-1"), {"type": "custom-title", "sessionId": "sess-1"})
        )
        result = self.claude_collector.harvest_file(self.conn, path)
        self.assertEqual(result["turns"], 0)
        self.assertEqual(result["skipped"], 0)

    def test_assistant_record_without_usage_block_is_not_written(self) -> None:
        path = self.write_session(
            "a.jsonl",
            _jsonl(_claude_user("sess-1"), {"type": "assistant", "sessionId": "sess-1", "message": {}}),
        )
        result = self.claude_collector.harvest_file(self.conn, path)
        self.assertEqual(result["turns"], 0)
        self.assertEqual(len(self.turn_raw_rows()), 0)

    def test_first_record_without_session_id_is_skipped(self) -> None:
        path = self.write_session("a.jsonl", _jsonl({"type": "mode", "mode": "normal"}))
        result = self.claude_collector.harvest_file(self.conn, path)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["turns"], 0)

    # ------------------------------------------------------------------
    # title capture
    # ------------------------------------------------------------------

    def session_title(self, session_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT title FROM session WHERE session_id = ?", (session_id,)
        ).fetchone()
        return row[0] if row is not None else None

    def test_custom_title_sets_session_title(self) -> None:
        path = self.write_session(
            "a.jsonl", _jsonl(_claude_user("sess-1"), _claude_custom_title("sess-1", "My Renamed Session"))
        )
        self.claude_collector.harvest_file(self.conn, path)
        self.assertEqual(self.session_title("sess-1"), "My Renamed Session")

    def test_ai_title_fills_a_genuine_gap(self) -> None:
        path = self.write_session(
            "a.jsonl", _jsonl(_claude_user("sess-1"), _claude_ai_title("sess-1", "auto-generated title"))
        )
        self.claude_collector.harvest_file(self.conn, path)
        self.assertEqual(self.session_title("sess-1"), "auto-generated title")

    def test_custom_title_overwrites_an_existing_ai_title(self) -> None:
        """ai-title arrives first, custom-title arrives second: the rename must win."""
        path = self.write_session(
            "a.jsonl",
            _jsonl(
                _claude_user("sess-1"),
                _claude_ai_title("sess-1", "auto-generated title"),
                _claude_custom_title("sess-1", "My Renamed Session"),
            ),
        )
        self.claude_collector.harvest_file(self.conn, path)
        self.assertEqual(self.session_title("sess-1"), "My Renamed Session")

    def test_ai_title_never_overwrites_an_existing_custom_title(self) -> None:
        """custom-title arrives first, ai-title arrives second: the rename must survive."""
        path = self.write_session(
            "a.jsonl",
            _jsonl(
                _claude_user("sess-1"),
                _claude_custom_title("sess-1", "My Renamed Session"),
                _claude_ai_title("sess-1", "auto-generated title"),
            ),
        )
        self.claude_collector.harvest_file(self.conn, path)
        self.assertEqual(self.session_title("sess-1"), "My Renamed Session")

    def test_title_precedence_is_order_independent_across_separate_harvest_calls(self) -> None:
        """The same precedence must hold when custom-title and ai-title land in
        separate incremental runs, not just within one batch — this is the
        property that rules out an in-memory, single-pass implementation.
        """
        path = self.write_session("a.jsonl", _jsonl(_claude_user("sess-1")))
        self.claude_collector.harvest_file(self.conn, path)
        with path.open("a") as fh:
            fh.write(_jsonl(_claude_custom_title("sess-1", "My Renamed Session")))
        self.claude_collector.harvest_file(self.conn, path)
        with path.open("a") as fh:
            fh.write(_jsonl(_claude_ai_title("sess-1", "auto-generated title")))
        self.claude_collector.harvest_file(self.conn, path)
        self.assertEqual(self.session_title("sess-1"), "My Renamed Session")

    def test_title_record_with_no_resolvable_session_is_skipped(self) -> None:
        path = self.write_session("a.jsonl", _jsonl({"type": "custom-title", "customTitle": "orphaned"}))
        result = self.claude_collector.harvest_file(self.conn, path)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["turns"], 0)

    # ------------------------------------------------------------------
    # ai-title genuine last-write-wins (schema v4)
    #
    # Title records carry no timestamp of their own — see _claude_ai_title's
    # docstring note. These tests build raw dicts directly to control the
    # timestamps on the *surrounding* records, since that's the only way
    # last_seen_ts (and therefore an ai-title's effective timestamp) can be
    # driven from a test.
    # ------------------------------------------------------------------

    def session_row(self, session_id: str) -> tuple:
        return self.conn.execute(
            "SELECT title, title_source, title_ai_ts, last_seen_ts FROM session WHERE session_id = ?",
            (session_id,),
        ).fetchone()

    def test_last_seen_ts_advances_from_any_timestamped_record(self) -> None:
        path = self.write_session(
            "a.jsonl",
            _jsonl(
                {"type": "user", "sessionId": "sess-1", "timestamp": "2026-01-01T00:00:00Z"},
                {"type": "system", "sessionId": "sess-1", "timestamp": "2026-01-02T00:00:00Z"},
            ),
        )
        self.claude_collector.harvest_file(self.conn, path)
        self.assertEqual(self.session_row("sess-1")[3], "2026-01-02T00:00:00Z")

    def test_last_seen_ts_never_regresses(self) -> None:
        path = self.write_session(
            "a.jsonl",
            _jsonl(
                {"type": "user", "sessionId": "sess-1", "timestamp": "2026-01-05T00:00:00Z"},
                {"type": "system", "sessionId": "sess-1", "timestamp": "2026-01-01T00:00:00Z"},
            ),
        )
        self.claude_collector.harvest_file(self.conn, path)
        self.assertEqual(self.session_row("sess-1")[3], "2026-01-05T00:00:00Z")

    def test_ai_title_genuine_last_write_wins_across_real_time_separation(self) -> None:
        """The property chunk 6 shipped as "first wins forever" — two
        ai-title records separated by a genuinely later timestamped record
        in between must resolve to the SECOND ai-title, not the first. This
        test must fail against `WHERE title IS NULL` (chunk 6's
        implementation) to prove it is not vacuous.
        """
        path = self.write_session(
            "a.jsonl",
            _jsonl(
                {"type": "user", "sessionId": "sess-1", "timestamp": "2026-01-01T00:00:00Z"},
                {"type": "ai-title", "sessionId": "sess-1", "aiTitle": "old title"},
                {"type": "system", "sessionId": "sess-1", "timestamp": "2026-01-02T00:00:00Z"},
                {"type": "ai-title", "sessionId": "sess-1", "aiTitle": "new title"},
            ),
        )
        self.claude_collector.harvest_file(self.conn, path)
        row = self.session_row("sess-1")
        self.assertEqual(row[0], "new title")
        self.assertEqual(row[2], "2026-01-02T00:00:00Z")

    def test_ai_title_tied_cluster_keeps_the_first(self) -> None:
        """Two ai-title records with nothing timestamped between them share
        one effective timestamp — a documented, accepted limitation, not a
        bug. Confirms the behavior is what the docstring claims, not silent.
        """
        path = self.write_session(
            "a.jsonl",
            _jsonl(
                {"type": "user", "sessionId": "sess-1", "timestamp": "2026-01-01T00:00:00Z"},
                {"type": "ai-title", "sessionId": "sess-1", "aiTitle": "tied-a"},
                {"type": "ai-title", "sessionId": "sess-1", "aiTitle": "tied-b"},
            ),
        )
        self.claude_collector.harvest_file(self.conn, path)
        self.assertEqual(self.session_row("sess-1")[0], "tied-a")

    def test_ai_title_untimed_cluster_with_no_timestamps_anywhere_keeps_the_first(self) -> None:
        """The no-time-information-at-all variant of the tied cluster: not a
        single timestamped record in the whole file. Review found the first
        cut of the acceptance SQL let every untimed ai-title re-qualify
        (last of the cluster won — the opposite of the documented rule);
        the `title_source IS NULL` leg of the first branch is what makes
        acceptance genuinely once-only in this state.
        """
        path = self.write_session(
            "a.jsonl",
            _jsonl(
                {"type": "ai-title", "sessionId": "sess-1", "aiTitle": "untimed-a"},
                {"type": "ai-title", "sessionId": "sess-1", "aiTitle": "untimed-b"},
            ),
        )
        self.claude_collector.harvest_file(self.conn, path)
        self.assertEqual(self.session_row("sess-1")[0], "untimed-a")

    def test_ai_title_last_write_wins_across_a_sessions_multiple_files(self) -> None:
        """The case the persisted high-water mark exists FOR: one session's
        title records split across two files (1 of 163 real sessions, from
        a session-continuation event). File B's ai-title has a later
        effective timestamp than file A's, carried across the file boundary
        by session.last_seen_ts — an in-memory or file-local ordinal would
        resolve this wrongly.
        """
        file_a = self.write_session(
            "a.jsonl",
            _jsonl(
                {"type": "user", "sessionId": "sess-1", "timestamp": "2026-01-01T00:00:00Z"},
                {"type": "ai-title", "sessionId": "sess-1", "aiTitle": "old title"},
            ),
        )
        file_b = self.write_session(
            "b.jsonl",
            _jsonl(
                {"type": "system", "sessionId": "sess-1", "timestamp": "2026-01-02T00:00:00Z"},
                {"type": "ai-title", "sessionId": "sess-1", "aiTitle": "new title"},
            ),
        )
        self.claude_collector.harvest_file(self.conn, file_a)
        self.claude_collector.harvest_file(self.conn, file_b)
        row = self.session_row("sess-1")
        self.assertEqual(row[0], "new title")
        self.assertEqual(row[2], "2026-01-02T00:00:00Z")

    def test_custom_title_locks_out_a_later_ai_title_even_with_a_newer_effective_timestamp(self) -> None:
        """A genuinely later ai-title must still lose to an earlier custom-title
        — the lockout is permanent and keyed on title_source, not on time.
        """
        path = self.write_session(
            "a.jsonl",
            _jsonl(
                {"type": "user", "sessionId": "sess-1", "timestamp": "2026-01-01T00:00:00Z"},
                {"type": "custom-title", "sessionId": "sess-1", "customTitle": "My Renamed Session"},
                {"type": "system", "sessionId": "sess-1", "timestamp": "2026-06-01T00:00:00Z"},
                {"type": "ai-title", "sessionId": "sess-1", "aiTitle": "much later auto title"},
            ),
        )
        self.claude_collector.harvest_file(self.conn, path)
        row = self.session_row("sess-1")
        self.assertEqual(row[0], "My Renamed Session")
        self.assertEqual(row[1], "custom")

    def test_ai_title_with_no_timestamp_information_anywhere_is_still_accepted_once(self) -> None:
        """The very first ai-title in a file with no timestamped record
        before it (title_ai_ts and last_seen_ts both NULL) must still be
        accepted — "unknown never overrides known" only blocks a *second*
        ai-title once a real effective timestamp exists.
        """
        path = self.write_session(
            "a.jsonl", _jsonl({"type": "ai-title", "sessionId": "sess-1", "aiTitle": "first ever"})
        )
        self.claude_collector.harvest_file(self.conn, path)
        self.assertEqual(self.session_row("sess-1")[0], "first ever")

    # ------------------------------------------------------------------
    # cwd backfill
    # ------------------------------------------------------------------

    def test_cwd_fills_from_a_later_record_when_the_first_record_has_none(self) -> None:
        """A file whose first record is a title line (no `cwd` field)
        creates the session with cwd=NULL via `_get_or_create_session` —
        this asserts a later cwd-bearing record fills the gap rather than
        leaving it NULL forever.
        """
        path = self.write_session(
            "a.jsonl",
            _jsonl(
                {"type": "custom-title", "sessionId": "sess-1", "customTitle": "My Renamed Session"},
                _claude_assistant("sess-1", "req-1", cwd="/tmp/real-proj"),
            ),
        )
        self.claude_collector.harvest_file(self.conn, path)
        row = self.conn.execute("SELECT cwd FROM session WHERE session_id = 'sess-1'").fetchone()
        self.assertEqual(row[0], "/tmp/real-proj")

    def test_cwd_never_overwrites_an_already_set_value(self) -> None:
        path = self.write_session(
            "a.jsonl",
            _jsonl(
                _claude_assistant("sess-1", "req-1", cwd="/tmp/original"),
                _claude_assistant("sess-1", "req-2", cwd="/tmp/different"),
            ),
        )
        self.claude_collector.harvest_file(self.conn, path)
        row = self.conn.execute("SELECT cwd FROM session WHERE session_id = 'sess-1'").fetchone()
        self.assertEqual(row[0], "/tmp/original")

    def test_cwd_stays_null_when_no_record_ever_carries_it(self) -> None:
        path = self.write_session(
            "a.jsonl", _jsonl({"type": "custom-title", "sessionId": "sess-1", "customTitle": "no cwd anywhere"})
        )
        self.claude_collector.harvest_file(self.conn, path)
        row = self.conn.execute("SELECT cwd FROM session WHERE session_id = 'sess-1'").fetchone()
        self.assertIsNone(row[0])

    # ------------------------------------------------------------------
    # malformed-line rule — identical to Codex's, same underlying property
    # ------------------------------------------------------------------

    def test_malformed_line_before_the_last_stops_that_file_only(self) -> None:
        path = self.write_session(
            "bad.jsonl",
            _jsonl(_claude_user("sess-1")) + "not json\n" + _jsonl(_claude_assistant("sess-1", "req-1")),
        )
        result = self.claude_collector.harvest_file(self.conn, path)
        self.assertIsNotNone(result["hard_stop"])
        self.assertEqual(result["hard_stop"]["line"], 2)
        self.assertEqual(result["turns"], 0)

    def test_truncated_trailing_line_is_not_an_error(self) -> None:
        content = _jsonl(_claude_user("sess-1")) + '{"type": "assistant", "sessionId": "sess-1"'
        path = self.write_session("live.jsonl", content)
        result = self.claude_collector.harvest_file(self.conn, path)
        self.assertIsNone(result["hard_stop"])
        row = self.conn.execute(
            "SELECT last_line_no FROM harvest WHERE source_path = ?", (str(path),)
        ).fetchone()
        self.assertEqual(row[0], 1)

    def test_missing_timestamp_is_a_hard_stop(self) -> None:
        bad = _claude_assistant("sess-1", "req-1")
        del bad["timestamp"]
        path = self.write_session("a.jsonl", _jsonl(_claude_user("sess-1"), bad))
        result = self.claude_collector.harvest_file(self.conn, path)
        self.assertIsNotNone(result["hard_stop"])
        self.assertIn("missing timestamp", result["hard_stop"]["reason"])

    # ------------------------------------------------------------------
    # idempotency and incremental append
    # ------------------------------------------------------------------

    def test_rerun_with_no_new_content_writes_nothing(self) -> None:
        path = self.write_session("a.jsonl", _jsonl(_claude_user("sess-1"), _claude_assistant("sess-1", "req-1")))
        self.claude_collector.harvest_file(self.conn, path)
        result = self.claude_collector.harvest_file(self.conn, path)
        self.assertEqual(result, {"turns": 0, "skipped": 0, "hard_stop": None})
        self.assertEqual(len(self.turn_raw_rows()), 1)

    def test_incremental_append_processes_only_new_lines(self) -> None:
        path = self.write_session("a.jsonl", _jsonl(_claude_user("sess-1"), _claude_assistant("sess-1", "req-1")))
        self.claude_collector.harvest_file(self.conn, path)
        with path.open("a") as fh:
            fh.write(_jsonl(_claude_assistant("sess-1", "req-2")))
        self.claude_collector.harvest_file(self.conn, path)
        self.assertEqual(len(self.turn_raw_rows()), 2)

    # ------------------------------------------------------------------
    # cross-file isolation via harvest_all
    # ------------------------------------------------------------------

    def test_one_files_hard_stop_does_not_affect_another(self) -> None:
        sessions = self.dir / "sessions"
        sessions.mkdir()
        (sessions / "good.jsonl").write_text(
            _jsonl(_claude_user("sess-good"), _claude_assistant("sess-good", "req-1"))
        )
        (sessions / "bad.jsonl").write_text(_jsonl(_claude_user("sess-bad")) + "not json\n")
        summary = self.claude_collector.harvest_all(self.conn, sessions)
        self.assertEqual(summary["files"], 2)
        self.assertEqual(summary["turns"], 1)
        self.assertEqual(len(summary["failures"]), 1)
        self.assertIn("bad.jsonl", summary["failures"][0]["path"])


class HarvestBackfillTests(unittest.TestCase):
    """Direct tests of `cli/harvest.py`'s `_reset_claude_watermarks`, against
    an in-memory store shared with `claude_collector`.

    Simulates "already harvested before title capture existed" by harvesting
    a file normally with the current, title-aware collector, then manually
    clearing `session.title` back to `NULL` — the state a pre-chunk-6
    collector would have left, since it consumed the same lines and advanced
    the same watermark, just without ever writing a title. This is easier to
    construct correctly than replaying an actually-older collector, and it
    isolates what this test is actually about: that resetting the watermark
    and re-harvesting recovers the title without duplicating `turn_raw` rows.
    """

    def setUp(self) -> None:
        import sqlite3

        self._tempdir = tempfile.TemporaryDirectory()
        self.dir = Path(self._tempdir.name)
        REPO_ROOT_CLI = REPO_ROOT / "cli"
        if str(REPO_ROOT_CLI) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT_CLI))
            self._added_cli_path = True
        else:
            self._added_cli_path = False
        import usage_store
        import claude_collector
        import harvest

        self.usage_store = usage_store
        self.claude_collector = claude_collector
        self.harvest = harvest
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON")
        for _version, _description, sql in usage_store.MIGRATIONS:
            self.conn.executescript(sql)

    def tearDown(self) -> None:
        self.conn.close()
        self._tempdir.cleanup()
        if self._added_cli_path:
            sys.path.remove(str(REPO_ROOT / "cli"))
        for name in ("usage_store", "claude_collector", "harvest"):
            sys.modules.pop(name, None)

    def write_session(self, name: str, content: str) -> Path:
        path = self.dir / name
        path.write_text(content)
        return path

    def test_backfill_populates_title_without_duplicating_turn_raw(self) -> None:
        path = self.write_session(
            "a.jsonl",
            _jsonl(
                _claude_user("sess-1"),
                _claude_custom_title("sess-1", "My Renamed Session"),
                _claude_assistant("sess-1", "req-1"),
            ),
        )
        self.claude_collector.harvest_file(self.conn, path)
        self.assertEqual(
            self.conn.execute("SELECT title FROM session WHERE session_id = 'sess-1'").fetchone()[0],
            "My Renamed Session",
        )
        # Simulate the pre-chunk-6 state: same watermark, same turn_raw row,
        # but no title was ever recorded.
        self.conn.execute("UPDATE session SET title = NULL WHERE session_id = 'sess-1'")
        turn_raw_count_before = self.conn.execute("SELECT COUNT(*) FROM turn_raw").fetchone()[0]

        self.harvest._reset_claude_watermarks(self.conn)
        self.claude_collector.harvest_all(self.conn, self.dir)

        self.assertEqual(
            self.conn.execute("SELECT title FROM session WHERE session_id = 'sess-1'").fetchone()[0],
            "My Renamed Session",
        )
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM turn_raw").fetchone()[0],
            turn_raw_count_before,
            "replaying an already-harvested file must not duplicate turn_raw rows",
        )

    def test_backfill_derives_title_provenance_for_a_pre_schema_v4_session(self) -> None:
        """Simulates a session that already has a title from before schema
        v4 existed: `title` set, but `title_source`/`title_ai_ts`/
        `last_seen_ts` all NULL — exactly what migrating an existing store
        to v4 produces, since ALTER TABLE can't retroactively derive
        provenance for rows that already exist. One `--backfill` replay
        must re-derive `title_source` correctly by re-processing the file's
        lines in their original order.
        """
        path = self.write_session(
            "a.jsonl",
            _jsonl(
                _claude_user("sess-1"),
                _claude_custom_title("sess-1", "My Renamed Session"),
                _claude_assistant("sess-1", "req-1"),
            ),
        )
        self.claude_collector.harvest_file(self.conn, path)
        # Simulate the pre-v4 state: title survived a migration, but nothing
        # about how it got there did.
        self.conn.execute(
            "UPDATE session SET title_source = NULL, title_ai_ts = NULL, last_seen_ts = NULL"
            " WHERE session_id = 'sess-1'"
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT title_source FROM session WHERE session_id = 'sess-1'"
            ).fetchone()[0],
            None,
        )

        self.harvest._reset_claude_watermarks(self.conn)
        self.claude_collector.harvest_all(self.conn, self.dir)

        row = self.conn.execute(
            "SELECT title, title_source FROM session WHERE session_id = 'sess-1'"
        ).fetchone()
        self.assertEqual(row[0], "My Renamed Session")
        self.assertEqual(row[1], "custom")

    def test_repeated_backfill_never_flips_a_title_backwards(self) -> None:
        """Replay idempotency for the last-write-wins logic — the critical
        review finding on this chunk. After a full pass, last_seen_ts holds
        the file-wide maximum, normally GREATER than the accepted title's
        title_ai_ts (any timestamped activity after the last ai-title — the
        common shape). A replay starting from that state handed the file's
        FIRST ai-title an effective timestamp newer than the stored
        title_ai_ts, so it was re-accepted and the title silently flipped
        backwards. `_reset_claude_watermarks` clearing last_seen_ts and
        title_ai_ts alongside the watermark is the fix; this test is the
        reproduction that confirmed the bug (it fails without that clear)
        and now pins the fix across TWO backfill cycles, not one.
        """
        path = self.write_session(
            "a.jsonl",
            _jsonl(
                {"type": "user", "sessionId": "sess-1", "timestamp": "2026-01-01T00:00:00Z"},
                {"type": "ai-title", "sessionId": "sess-1", "aiTitle": "old title"},
                {"type": "system", "sessionId": "sess-1", "timestamp": "2026-01-02T00:00:00Z"},
                {"type": "ai-title", "sessionId": "sess-1", "aiTitle": "new title"},
                # Timestamped activity after the last ai-title, genuinely
                # LATER than the system record — this is what pushes
                # last_seen_ts past title_ai_ts and armed the original bug.
                # (The shared _claude_assistant fixture's fixed timestamp is
                # 2026-01-01T00:00:01Z, EARLIER than the system record above,
                # which would leave last_seen_ts == title_ai_ts and the
                # strict-greater comparison would mask the bug.)
                {
                    "type": "assistant",
                    "sessionId": "sess-1",
                    "requestId": "req-1",
                    "isSidechain": False,
                    "timestamp": "2026-01-03T00:00:00Z",
                    "message": {"model": "m", "usage": {"input_tokens": 1, "output_tokens": 1}},
                },
            ),
        )
        self.claude_collector.harvest_file(self.conn, path)
        self.assertEqual(
            self.conn.execute("SELECT title FROM session WHERE session_id = 'sess-1'").fetchone()[0],
            "new title",
        )

        for cycle in range(2):
            self.harvest._reset_claude_watermarks(self.conn)
            self.claude_collector.harvest_all(self.conn, self.dir)
            self.assertEqual(
                self.conn.execute("SELECT title FROM session WHERE session_id = 'sess-1'").fetchone()[0],
                "new title",
                f"backfill cycle {cycle + 1} must not flip the title backwards",
            )

    def test_backfill_fills_cwd_for_a_session_created_by_a_title_record(self) -> None:
        path = self.write_session(
            "a.jsonl",
            _jsonl(
                _claude_custom_title("sess-1", "My Renamed Session"),
                _claude_assistant("sess-1", "req-1", cwd="/tmp/real-proj"),
            ),
        )
        self.claude_collector.harvest_file(self.conn, path)
        self.conn.execute("UPDATE session SET cwd = NULL WHERE session_id = 'sess-1'")

        self.harvest._reset_claude_watermarks(self.conn)
        self.claude_collector.harvest_all(self.conn, self.dir)

        row = self.conn.execute("SELECT cwd FROM session WHERE session_id = 'sess-1'").fetchone()
        self.assertEqual(row[0], "/tmp/real-proj")

    def test_reset_only_touches_claude_watermarks(self) -> None:
        self.conn.execute(
            "INSERT INTO harvest (harness, source_path, host_id, last_size, last_offset,"
            " last_line_no, last_line_hash, harvested_at, collector_version)"
            " VALUES ('codex', '/tmp/codex.jsonl', '', 100, 100, 5, 'h', '2026-01-01T00:00:00Z', 1)"
        )
        self.conn.execute(
            "INSERT INTO harvest (harness, source_path, host_id, last_size, last_offset,"
            " last_line_no, last_line_hash, harvested_at, collector_version)"
            " VALUES ('claude', '/tmp/claude.jsonl', '', 100, 100, 5, 'h', '2026-01-01T00:00:00Z', 1)"
        )
        self.harvest._reset_claude_watermarks(self.conn)
        codex_row = self.conn.execute(
            "SELECT last_offset, last_line_no FROM harvest WHERE harness = 'codex'"
        ).fetchone()
        claude_row = self.conn.execute(
            "SELECT last_offset, last_line_no FROM harvest WHERE harness = 'claude'"
        ).fetchone()
        self.assertEqual(codex_row, (100, 5), "resetting Claude watermarks must not touch Codex's")
        self.assertEqual(claude_row, (0, 0))


class NormalizeTests(unittest.TestCase):
    """Direct tests of cli/normalize.py, against an in-memory store.

    turn_raw rows are inserted directly rather than produced via the Codex
    collector — normalization operates on whatever is already in turn_raw
    regardless of how it got there, and decoupling from the collector means
    a change to harvest logic can't accidentally mask a normalize regression.
    """

    def setUp(self) -> None:
        import sqlite3

        REPO_ROOT_CLI = REPO_ROOT / "cli"
        if str(REPO_ROOT_CLI) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT_CLI))
            self._added_cli_path = True
        else:
            self._added_cli_path = False
        import usage_store
        import normalize

        self.usage_store = usage_store
        self.normalize = normalize
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON")
        for _version, _description, sql in usage_store.MIGRATIONS:
            self.conn.executescript(sql)
        self._next_line = 1

    def tearDown(self) -> None:
        self.conn.close()
        if self._added_cli_path:
            sys.path.remove(str(REPO_ROOT / "cli"))
        for name in ("usage_store", "normalize"):
            sys.modules.pop(name, None)

    def insert_session(self, session_id: str = "sess-1", harness: str = "codex") -> int:
        cur = self.conn.execute(
            "INSERT INTO session (harness, session_id, source_path) VALUES (?, ?, ?)",
            (harness, session_id, f"/tmp/{session_id}.jsonl"),
        )
        return cur.lastrowid

    def insert_turn_raw(
        self,
        session_row_id: int,
        record: dict,
        model: str | None = "gpt-5.6",
        is_subagent: int = 0,
    ) -> int:
        line_no = self._next_line
        self._next_line += 1
        cur = self.conn.execute(
            "INSERT INTO turn_raw"
            " (session_row_id, natural_turn_id, turn_seq, is_subagent, ts, model,"
            "  payload, source_path, source_line_no, collector_version)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_row_id,
                f"turn:{line_no}",
                line_no,
                is_subagent,
                record.get("timestamp", "2026-01-01T00:00:00Z"),
                model,
                json.dumps(record),
                "/tmp/x.jsonl",
                line_no,
                1,
            ),
        )
        return cur.lastrowid

    def norm_row(self, turn_raw_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM turn_norm WHERE turn_raw_id = ?", (turn_raw_id,)).fetchone()
        if row is None:
            return None
        cols = [d[0] for d in self.conn.execute("SELECT * FROM turn_norm LIMIT 0").description]
        return dict(zip(cols, row))

    # ------------------------------------------------------------------
    # extraction correctness
    # ------------------------------------------------------------------

    def test_full_payload_extracts_every_field(self) -> None:
        sess = self.insert_session()
        tr_id = self.insert_turn_raw(
            sess,
            {
                "timestamp": "2026-01-01T00:00:01Z",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": {
                            "input_tokens": 100,
                            "cached_input_tokens": 40,
                            "cache_write_input_tokens": 5,
                            "output_tokens": 10,
                            "reasoning_output_tokens": 3,
                        },
                        "model_context_window": 200000,
                    },
                    "rate_limits": {
                        "primary": {"used_percent": 5.0, "window_minutes": 300, "resets_at": 123},
                        "secondary": {"used_percent": 10.0, "window_minutes": 10080, "resets_at": 456},
                    },
                },
            },
        )
        result = self.normalize.normalize_all(self.conn)
        self.assertEqual(result["normalized"], 1)
        row = self.norm_row(tr_id)
        self.assertEqual(row["fresh_input_tokens"], 60)
        self.assertEqual(row["cache_read_tokens"], 40)
        self.assertEqual(row["cache_write_tokens"], 5)
        self.assertEqual(row["output_tokens"], 10)
        self.assertEqual(row["reasoning_tokens"], 3)
        self.assertEqual(row["context_window"], 200000)
        self.assertEqual(row["capacity_primary_used_pct"], 5.0)
        self.assertEqual(row["capacity_primary_window_minutes"], 300)
        self.assertEqual(row["capacity_primary_resets_at"], 123)
        self.assertEqual(row["capacity_secondary_used_pct"], 10.0)
        self.assertEqual(row["capacity_secondary_window_minutes"], 10080)
        self.assertEqual(row["capacity_secondary_resets_at"], 456)
        self.assertEqual(row["model"], "gpt-5.6", "ts/model/is_subagent copy through from turn_raw")
        self.assertEqual(row["norm_version"], self.normalize.NORM_VERSION)

    def test_null_info_leaves_token_columns_null_but_still_produces_a_row(self) -> None:
        """0.1% of real rows have info: null — absence, not a skipped row."""
        sess = self.insert_session()
        tr_id = self.insert_turn_raw(
            sess,
            {
                "timestamp": "2026-01-01T00:00:01Z",
                "payload": {
                    "type": "token_count",
                    "info": None,
                    "rate_limits": {"primary": {"used_percent": 1.0, "window_minutes": 300, "resets_at": 1}},
                },
            },
        )
        self.normalize.normalize_all(self.conn)
        row = self.norm_row(tr_id)
        self.assertIsNotNone(row, "a row must exist even when info is null")
        self.assertIsNone(row["fresh_input_tokens"])
        self.assertIsNone(row["cache_read_tokens"])
        self.assertIsNone(row["context_window"])
        self.assertEqual(row["capacity_primary_used_pct"], 1.0, "rate_limits is independent of info")
        self.assertIsNone(row["capacity_secondary_used_pct"])

    def test_absent_secondary_is_null_not_zero(self) -> None:
        sess = self.insert_session()
        tr_id = self.insert_turn_raw(
            sess,
            {
                "timestamp": "2026-01-01T00:00:01Z",
                "payload": {
                    "type": "token_count",
                    "info": {"last_token_usage": {"input_tokens": 10, "cached_input_tokens": 2}},
                    "rate_limits": {"primary": {"used_percent": 1.0, "window_minutes": 300, "resets_at": 1}},
                },
            },
        )
        self.normalize.normalize_all(self.conn)
        row = self.norm_row(tr_id)
        self.assertIsNone(row["capacity_secondary_used_pct"])
        self.assertIsNone(row["capacity_secondary_window_minutes"])
        self.assertIsNone(row["capacity_secondary_resets_at"])

    # ------------------------------------------------------------------
    # Claude extraction — direct mapping, no subtraction
    # ------------------------------------------------------------------

    def test_claude_full_usage_extracts_direct_mapping(self) -> None:
        """Claude's fields are already disjoint: fresh_input_tokens = input_tokens, no subtraction."""
        sess = self.insert_session(session_id="claude-sess-1", harness="claude")
        tr_id = self.insert_turn_raw(
            sess,
            {
                "type": "assistant",
                "timestamp": "2026-01-01T00:00:01Z",
                "requestId": "req-1",
                "message": {
                    "model": "claude-sonnet-5",
                    "usage": {
                        "input_tokens": 100,
                        "cache_read_input_tokens": 40,
                        "cache_creation_input_tokens": 20,
                        "output_tokens": 10,
                    },
                },
            },
        )
        result = self.normalize.normalize_all(self.conn)
        self.assertEqual(result["normalized"], 1)
        row = self.norm_row(tr_id)
        self.assertEqual(row["fresh_input_tokens"], 100, "no subtraction — Claude's input_tokens is already fresh")
        self.assertEqual(row["cache_read_tokens"], 40)
        self.assertEqual(row["cache_write_tokens"], 20)
        self.assertEqual(row["output_tokens"], 10)
        self.assertIsNone(row["reasoning_tokens"], "Claude transcripts do not carry this")
        self.assertIsNone(row["context_window"])
        self.assertIsNone(row["capacity_primary_used_pct"])
        self.assertIsNone(row["capacity_secondary_used_pct"])

    def test_claude_non_assistant_record_returns_none_and_is_skipped(self) -> None:
        sess = self.insert_session(session_id="claude-sess-2", harness="claude")
        tr_id = self.insert_turn_raw(
            sess, {"type": "user", "timestamp": "2026-01-01T00:00:01Z", "message": {"content": "hi"}}
        )
        result = self.normalize.normalize_all(self.conn)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["normalized"], 0)
        self.assertIsNone(self.norm_row(tr_id))

    def test_claude_missing_usage_block_leaves_token_columns_null(self) -> None:
        """An assistant entry with no usage block — nothing to extract, still a valid row."""
        sess = self.insert_session(session_id="claude-sess-3", harness="claude")
        tr_id = self.insert_turn_raw(
            sess, {"type": "assistant", "timestamp": "2026-01-01T00:00:01Z", "message": {"model": "x"}}
        )
        self.normalize.normalize_all(self.conn)
        row = self.norm_row(tr_id)
        self.assertIsNotNone(row)
        self.assertIsNone(row["fresh_input_tokens"])
        self.assertIsNone(row["cache_read_tokens"])

    def test_unknown_harness_is_left_alone_not_raised(self) -> None:
        """A harness with no extractor is skipped, never raised on.

        Both real harnesses (`codex`, `claude`) have extractors as of this
        chunk, and `session.harness` is schema-constrained to just those two
        — there is no way to construct a genuinely unrecognized harness
        through the real schema anymore. `_EXTRACTORS` is emptied for the
        duration of this test to exercise the fallback directly, the way a
        third harness with no extractor yet would hit it in the future.
        """
        import unittest.mock

        sess = self.insert_session(session_id="claude-sess", harness="claude")
        tr_id = self.insert_turn_raw(sess, {"timestamp": "2026-01-01T00:00:01Z", "payload": {}})
        with unittest.mock.patch.dict(self.normalize._EXTRACTORS, clear=True):
            result = self.normalize.normalize_all(self.conn)
        self.assertEqual(result["normalized"], 0)
        self.assertIsNone(self.norm_row(tr_id))

    # ------------------------------------------------------------------
    # idempotency, incrementality, staleness
    # ------------------------------------------------------------------

    def test_rerun_with_no_new_rows_normalizes_nothing(self) -> None:
        sess = self.insert_session()
        self.insert_turn_raw(sess, {"timestamp": "x", "payload": {"type": "token_count", "info": None}})
        self.normalize.normalize_all(self.conn)
        second = self.normalize.normalize_all(self.conn)
        self.assertEqual(second["normalized"], 0)

    def test_new_turn_raw_row_is_the_only_one_normalized(self) -> None:
        sess = self.insert_session()
        self.insert_turn_raw(sess, {"timestamp": "x", "payload": {"type": "token_count", "info": None}})
        self.normalize.normalize_all(self.conn)
        new_id = self.insert_turn_raw(sess, {"timestamp": "y", "payload": {"type": "token_count", "info": None}})
        result = self.normalize.normalize_all(self.conn)
        self.assertEqual(result["normalized"], 1)
        self.assertIsNotNone(self.norm_row(new_id))

    def test_stale_norm_version_is_reprocessed_alone(self) -> None:
        sess = self.insert_session()
        stale_id = self.insert_turn_raw(sess, {"timestamp": "x", "payload": {"type": "token_count", "info": None}})
        fresh_id = self.insert_turn_raw(sess, {"timestamp": "y", "payload": {"type": "token_count", "info": None}})
        self.normalize.normalize_all(self.conn)
        self.conn.execute("UPDATE turn_norm SET norm_version = 0 WHERE turn_raw_id = ?", (stale_id,))
        self.conn.commit()
        result = self.normalize.normalize_all(self.conn)
        self.assertEqual(result["normalized"], 1)
        self.assertEqual(self.norm_row(stale_id)["norm_version"], self.normalize.NORM_VERSION)
        self.assertEqual(self.norm_row(fresh_id)["norm_version"], self.normalize.NORM_VERSION)

    def test_reprocessing_a_stale_row_overwrites_changed_values(self) -> None:
        """Proves ON CONFLICT DO UPDATE actually replaces content, not just presence.

        A row that goes from having token data to not having any (or vice
        versa) must have its turn_norm row reflect the NEW payload exactly —
        a column populated by the first pass but absent from the second must
        come back NULL, not keep its stale value.
        """
        sess = self.insert_session()
        tr_id = self.insert_turn_raw(
            sess,
            {
                "timestamp": "x",
                "payload": {
                    "type": "token_count",
                    "info": {"last_token_usage": {"input_tokens": 100, "cached_input_tokens": 40}},
                },
            },
        )
        self.normalize.normalize_all(self.conn)
        self.assertEqual(self.norm_row(tr_id)["fresh_input_tokens"], 60)

        # Change the underlying payload and force reprocessing.
        self.conn.execute(
            "UPDATE turn_raw SET payload = ? WHERE id = ?",
            (json.dumps({"timestamp": "x", "payload": {"type": "token_count", "info": None}}), tr_id),
        )
        self.conn.execute("UPDATE turn_norm SET norm_version = 0 WHERE turn_raw_id = ?", (tr_id,))
        self.conn.commit()

        self.normalize.normalize_all(self.conn)
        row = self.norm_row(tr_id)
        self.assertIsNone(row["fresh_input_tokens"], "must reflect the new payload, not retain the old value")
        self.assertEqual(row["norm_version"], self.normalize.NORM_VERSION)

    def test_cached_absent_with_input_present_is_treated_as_zero_cached(self) -> None:
        """The gap the shared _token_count() fixture exercises everywhere else untested."""
        sess = self.insert_session()
        tr_id = self.insert_turn_raw(
            sess,
            {
                "timestamp": "x",
                "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 100}}},
            },
        )
        self.normalize.normalize_all(self.conn)
        row = self.norm_row(tr_id)
        self.assertEqual(row["fresh_input_tokens"], 100, "no cached field present must mean nothing was cached")
        self.assertIsNone(row["cache_read_tokens"])

    def test_input_absent_with_cached_present_is_uncomputable(self) -> None:
        """The genuinely-uncomputable direction — must stay None, not become 0 or negative."""
        sess = self.insert_session()
        tr_id = self.insert_turn_raw(
            sess,
            {
                "timestamp": "x",
                "payload": {"type": "token_count", "info": {"last_token_usage": {"cached_input_tokens": 40}}},
            },
        )
        self.normalize.normalize_all(self.conn)
        row = self.norm_row(tr_id)
        self.assertIsNone(row["fresh_input_tokens"])
        self.assertEqual(row["cache_read_tokens"], 40, "the independent measurement is still recorded")

    def test_cached_exceeding_input_does_not_store_a_negative(self) -> None:
        """Guards against a violation of Codex's own subset semantics reaching turn_norm."""
        sess = self.insert_session()
        tr_id = self.insert_turn_raw(
            sess,
            {
                "timestamp": "x",
                "payload": {
                    "type": "token_count",
                    "info": {"last_token_usage": {"input_tokens": 10, "cached_input_tokens": 40}},
                },
            },
        )
        self.normalize.normalize_all(self.conn)
        row = self.norm_row(tr_id)
        self.assertIsNone(row["fresh_input_tokens"], "a negative result must not be stored")

    def test_non_numeric_leaf_is_skipped_not_a_crash(self) -> None:
        """A leaf value with an unanticipated shape must not abort every other row."""
        sess = self.insert_session()
        bad_id = self.insert_turn_raw(
            sess,
            {
                "timestamp": "x",
                "payload": {
                    "type": "token_count",
                    "info": {"last_token_usage": {"input_tokens": {"value": 5}}},
                },
            },
        )
        good_id = self.insert_turn_raw(
            sess,
            {
                "timestamp": "y",
                "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 5}}},
            },
        )
        result = self.normalize.normalize_all(self.conn)
        # A non-scalar leaf degrades to None (via _num), not a raised
        # exception — this row succeeds with fresh_input_tokens absent rather
        # than failing. The real regression this guards is a leaf shape that
        # *isn't* caught by _num reaching sqlite3 directly; this test pins
        # the current, safe behavior so a future change can't quietly widen
        # what gets passed straight through.
        self.assertEqual(result["failures"], [])
        self.assertIsNone(self.norm_row(bad_id)["fresh_input_tokens"])
        self.assertEqual(self.norm_row(good_id)["fresh_input_tokens"], 5)

    def test_non_token_count_record_is_skipped_not_normalized(self) -> None:
        sess = self.insert_session()
        tr_id = self.insert_turn_raw(sess, {"timestamp": "x", "payload": {"type": "some_future_record"}})
        result = self.normalize.normalize_all(self.conn)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["normalized"], 0)
        self.assertIsNone(self.norm_row(tr_id))

    def test_unrecognized_harness_rows_are_not_reselected_every_run(self) -> None:
        """Filtered at the SQL level, not per-row — a row with no extractor
        must never appear in the candidate set at all, so it costs nothing on
        repeated runs regardless of how many such rows accumulate.

        Patches `_EXTRACTORS` down to `codex` only rather than clearing it
        entirely: with nothing left in the dict, `s.harness IN ()` matches
        no row regardless of harness, and an implementation that dropped the
        SQL filter in favor of a per-row `if harness not in _EXTRACTORS:
        skip` check would pass this test identically. Keeping one real
        extractor and giving both harnesses a row is what forces the SQL
        filter itself to discriminate — `skipped == 0` is the assertion that
        tells "never selected" apart from "selected, then skipped."
        """
        import unittest.mock

        codex_sess = self.insert_session(session_id="codex-sess", harness="codex")
        claude_sess = self.insert_session(session_id="claude-sess", harness="claude")
        self.insert_turn_raw(codex_sess, {"timestamp": "x", "payload": {"type": "token_count"}})
        self.insert_turn_raw(claude_sess, {"timestamp": "x", "payload": {"type": "token_count"}})
        with unittest.mock.patch.dict(
            self.normalize._EXTRACTORS, {"codex": self.normalize._normalize_codex_row}, clear=True
        ):
            first = self.normalize.normalize_all(self.conn)
            second = self.normalize.normalize_all(self.conn)
        self.assertEqual(first["normalized"], 1, "only the codex row should ever be selected")
        self.assertEqual(first["skipped"], 0, "the claude row must be filtered at the SQL level, not selected-then-skipped")
        self.assertEqual(second["normalized"], 0)
        self.assertEqual(first["failures"], [])


class CostTests(unittest.TestCase):
    """Direct tests of cli/cost.py's query functions, against a small
    constructed turn_norm/session dataset — no collector or normalize
    pipeline involved, since these functions only ever read what's already
    in the store.
    """

    def setUp(self) -> None:
        import sqlite3

        REPO_ROOT_CLI = REPO_ROOT / "cli"
        if str(REPO_ROOT_CLI) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT_CLI))
            self._added_cli_path = True
        else:
            self._added_cli_path = False
        import usage_store
        import cost

        self.usage_store = usage_store
        self.cost = cost
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row
        for _version, _description, sql in usage_store.MIGRATIONS:
            self.conn.executescript(sql)
        self._next_id = 1

    def tearDown(self) -> None:
        self.conn.close()
        if self._added_cli_path:
            sys.path.remove(str(REPO_ROOT / "cli"))
        for name in ("usage_store", "cost"):
            sys.modules.pop(name, None)

    def insert_session(
        self, session_id: str, harness: str = "codex", title: str | None = None, cwd: str | None = None
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO session (harness, session_id, title, cwd, source_path) VALUES (?, ?, ?, ?, ?)",
            (harness, session_id, title, cwd, f"/tmp/{session_id}.jsonl"),
        )
        return cur.lastrowid

    def insert_turn(
        self,
        session_row_id: int,
        ts: str,
        model: str | None = "some-model",
        fresh: int = 0,
        cache_read: int = 0,
        cache_write: int = 0,
        output: int = 0,
        capacity_primary_used_pct: float | None = None,
        capacity_primary_window_minutes: int | None = None,
        capacity_primary_resets_at: int | None = None,
        capacity_secondary_used_pct: float | None = None,
    ) -> int:
        turn_raw_id = self._next_id
        self._next_id += 1
        self.conn.execute(
            "INSERT INTO turn_raw"
            " (id, session_row_id, natural_turn_id, turn_seq, is_subagent, ts, model,"
            "  payload, source_path, source_line_no, collector_version)"
            " VALUES (?, ?, ?, ?, 0, ?, ?, '{}', '/tmp/x', ?, 1)",
            (turn_raw_id, session_row_id, f"t{turn_raw_id}", turn_raw_id, ts, model, turn_raw_id),
        )
        self.conn.execute(
            "INSERT INTO turn_norm"
            " (turn_raw_id, ts, model, is_subagent, fresh_input_tokens, cache_read_tokens,"
            "  cache_write_tokens, output_tokens, capacity_primary_used_pct,"
            "  capacity_primary_window_minutes, capacity_primary_resets_at,"
            "  capacity_secondary_used_pct, norm_version)"
            " VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
            (
                turn_raw_id,
                ts,
                model,
                fresh,
                cache_read,
                cache_write,
                output,
                capacity_primary_used_pct,
                capacity_primary_window_minutes,
                capacity_primary_resets_at,
                capacity_secondary_used_pct,
            ),
        )
        return turn_raw_id

    # ------------------------------------------------------------------
    # summary_rows
    # ------------------------------------------------------------------

    def test_summary_rows_groups_by_harness_and_model(self) -> None:
        codex_sess = self.insert_session("c-1", harness="codex")
        claude_sess = self.insert_session("cl-1", harness="claude")
        self.insert_turn(codex_sess, "2026-01-01T00:00:00+00:00", model="gpt-5", fresh=100, cache_read=40, output=10)
        self.insert_turn(codex_sess, "2026-01-02T00:00:00+00:00", model="gpt-5", fresh=50, output=5)
        self.insert_turn(claude_sess, "2026-01-01T00:00:00+00:00", model="claude-5", fresh=200, output=50)

        rows = self.cost.summary_rows(self.conn, None)
        self.assertEqual(len(rows), 2, "one row per distinct (harness, model) pair, not per turn")
        by_key = {(r["harness"], r["model"]): r for r in rows}
        self.assertEqual(by_key[("codex", "gpt-5")]["turns"], 2)
        self.assertEqual(by_key[("codex", "gpt-5")]["fresh_input_tokens"], 150)
        self.assertEqual(by_key[("claude", "claude-5")]["turns"], 1)

    def test_summary_rows_respects_since_cutoff(self) -> None:
        sess = self.insert_session("c-1")
        self.insert_turn(sess, "2026-01-01T00:00:00+00:00", model="gpt-5", fresh=100)
        self.insert_turn(sess, "2026-06-01T00:00:00+00:00", model="gpt-5", fresh=200)

        rows = self.cost.summary_rows(self.conn, "2026-03-01T00:00:00+00:00")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["fresh_input_tokens"], 200)

    def test_summary_rows_all_ignores_cutoff(self) -> None:
        sess = self.insert_session("c-1")
        self.insert_turn(sess, "2020-01-01T00:00:00+00:00", model="gpt-5", fresh=1)

        rows = self.cost.summary_rows(self.conn, None)
        self.assertEqual(len(rows), 1)

    def test_cutoff_excludes_older_rows_against_real_z_suffixed_timestamps(self) -> None:
        """Every other test in this class passes a literal `+00:00` cutoff
        string. This one calls the real `_cutoff()` — a `+00:00`-suffixed
        string — and filters real `Z`-suffixed timestamps with it, the exact
        combination every actual CLI invocation produces and the one no
        other test exercises.
        """
        sess = self.insert_session("c-1")
        self.insert_turn(sess, "2020-01-01T00:00:00.000Z", model="gpt-5", fresh=1)  # ancient
        self.insert_turn(sess, self.cost._cutoff(0).replace("+00:00", "Z"), model="gpt-5", fresh=2)  # ~now

        rows = self.cost.summary_rows(self.conn, self.cost._cutoff(1))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["fresh_input_tokens"], 2)

    # ------------------------------------------------------------------
    # capacity_gauge
    # ------------------------------------------------------------------

    def test_capacity_gauge_returns_the_most_recent_reading(self) -> None:
        sess = self.insert_session("c-1", harness="codex")
        self.insert_turn(
            sess, "2026-01-01T00:00:00+00:00", capacity_primary_used_pct=10.0, capacity_primary_window_minutes=300
        )
        self.insert_turn(
            sess, "2026-01-02T00:00:00+00:00", capacity_primary_used_pct=25.0, capacity_primary_window_minutes=300
        )

        gauge = self.cost.capacity_gauge(self.conn, None)
        self.assertIsNotNone(gauge)
        self.assertEqual(gauge["capacity_primary_used_pct"], 25.0)

    def test_capacity_gauge_absent_when_no_capacity_data_in_window(self) -> None:
        sess = self.insert_session("c-1", harness="codex")
        self.insert_turn(sess, "2026-01-01T00:00:00+00:00")  # no capacity fields
        self.assertIsNone(self.cost.capacity_gauge(self.conn, None))

    def test_capacity_gauge_ignores_claude_rows(self) -> None:
        """Claude turns never carry real Codex capacity data in practice, but
        this test doesn't rely on that: it gives the Claude row a capacity
        value too, dated *later* than the Codex row, so a gauge query that
        forgot the harness filter would pick up the Claude row instead
        (`ORDER BY tn.ts DESC` favors it) and this test would catch that by
        failing, not by staying silent the way an all-NULL Claude row would.
        """
        codex_sess = self.insert_session("c-1", harness="codex")
        claude_sess = self.insert_session("cl-1", harness="claude")
        self.insert_turn(codex_sess, "2026-01-01T00:00:00+00:00", capacity_primary_used_pct=5.0)
        self.insert_turn(claude_sess, "2026-01-02T00:00:00+00:00", capacity_primary_used_pct=99.0)

        gauge = self.cost.capacity_gauge(self.conn, None)
        self.assertIsNotNone(gauge)
        self.assertEqual(gauge["capacity_primary_used_pct"], 5.0)

    def test_capacity_gauge_respects_since_cutoff(self) -> None:
        sess = self.insert_session("c-1", harness="codex")
        self.insert_turn(sess, "2026-01-01T00:00:00+00:00", capacity_primary_used_pct=5.0)
        self.assertIsNone(self.cost.capacity_gauge(self.conn, "2026-06-01T00:00:00+00:00"))

    # ------------------------------------------------------------------
    # sessions_rows
    # ------------------------------------------------------------------

    def test_sessions_rows_label_fallback_order(self) -> None:
        titled = self.insert_session("s-titled", title="My Title", cwd="/tmp/a")
        cwd_only = self.insert_session("s-cwd", title=None, cwd="/tmp/b")
        neither = self.insert_session("s-bare-1234567890", title=None, cwd=None)
        self.insert_turn(titled, "2026-01-01T00:00:00+00:00")
        self.insert_turn(cwd_only, "2026-01-01T00:00:00+00:00")
        self.insert_turn(neither, "2026-01-01T00:00:00+00:00")

        by_session_id = {r["session_id"]: r["label"] for r in self.cost.sessions_rows(self.conn, None)}
        self.assertEqual(by_session_id["s-titled"], "My Title")
        self.assertEqual(by_session_id["s-cwd"], "/tmp/b")
        self.assertEqual(by_session_id["s-bare-1234567890"], "session:s-bare-1")

    def test_sessions_rows_ordered_most_recently_active_first(self) -> None:
        older = self.insert_session("s-older")
        newer = self.insert_session("s-newer")
        self.insert_turn(older, "2026-01-01T00:00:00+00:00")
        self.insert_turn(newer, "2026-06-01T00:00:00+00:00")

        rows = self.cost.sessions_rows(self.conn, None)
        self.assertEqual([r["session_id"] for r in rows], ["s-newer", "s-older"])

    def test_sessions_rows_defaults_to_20(self) -> None:
        for i in range(25):
            sess = self.insert_session(f"s-{i}")
            self.insert_turn(sess, f"2026-01-{i + 1:02d}T00:00:00+00:00")

        rows = self.cost.sessions_rows(self.conn, None)
        self.assertEqual(len(rows), 20)
        self.assertEqual(rows[0]["session_id"], "s-24", "the cap must keep the most recent, not an arbitrary 20")

    def test_sessions_rows_limit_none_is_unlimited(self) -> None:
        for i in range(25):
            sess = self.insert_session(f"s-{i}")
            self.insert_turn(sess, f"2026-01-{i + 1:02d}T00:00:00+00:00")

        rows = self.cost.sessions_rows(self.conn, None, limit=None)
        self.assertEqual(len(rows), 25)

    def test_sessions_rows_limit_overrides_default(self) -> None:
        for i in range(10):
            sess = self.insert_session(f"s-{i}")
            self.insert_turn(sess, f"2026-01-{i + 1:02d}T00:00:00+00:00")

        rows = self.cost.sessions_rows(self.conn, None, limit=3)
        self.assertEqual(len(rows), 3)

    # ------------------------------------------------------------------
    # renderers
    # ------------------------------------------------------------------

    def test_render_table_on_empty_rows_says_so_rather_than_printing_nothing(self) -> None:
        self.assertEqual(self.cost.render_table([]), "(no data in range)")

    def test_render_json_round_trips(self) -> None:
        rows = [{"harness": "codex", "turns": 3}]
        self.assertEqual(json.loads(self.cost.render_json(rows)), rows)

    def test_render_gauge_line_labels_by_actual_window_size_not_primary_secondary(self) -> None:
        """`usage_store.py`'s _V3 migration documents that `primary`/
        `secondary` don't reliably mean "short window"/"long window" — this
        asserts the rendering leads with the number actually stored, not
        those names, and includes the reading's own timestamp so a stale
        snapshot doesn't read as current.
        """
        gauge = {
            "ts": "2026-01-01T00:00:00+00:00",
            "capacity_primary_used_pct": 41.0,
            "capacity_primary_window_minutes": 300,
            "capacity_secondary_used_pct": 12.0,
            "capacity_secondary_window_minutes": 10080,
        }
        line = self.cost._render_gauge_line(gauge)
        self.assertIn("2026-01-01T00:00:00+00:00", line)
        self.assertIn("300m window 41.0%", line)
        self.assertIn("10080m window 12.0%", line)
        self.assertNotIn("primary", line)
        self.assertNotIn("secondary", line)

    def test_render_gauge_line_omits_secondary_when_absent(self) -> None:
        gauge = {
            "ts": "2026-01-01T00:00:00+00:00",
            "capacity_primary_used_pct": 41.0,
            "capacity_primary_window_minutes": 300,
            "capacity_secondary_used_pct": None,
        }
        line = self.cost._render_gauge_line(gauge)
        self.assertIn("300m window 41.0%", line)
        self.assertEqual(line.count("%"), 1)

    # ------------------------------------------------------------------
    # active_rows — `flow cost active`, superseding token-report --active
    #
    # `now` is injected everywhere for determinism. Timestamps use the Z
    # suffix, matching what the collectors actually store.
    # ------------------------------------------------------------------

    def _active_now(self):
        from datetime import datetime, timezone

        return datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)

    def insert_ctx_turn(self, session_row_id: int, ts: str, ctx: int, is_subagent: int = 0) -> None:
        """One context sample: fresh+cache_read+cache_write = ctx."""
        turn_raw_id = self._next_id
        self._next_id += 1
        self.conn.execute(
            "INSERT INTO turn_raw (id, session_row_id, natural_turn_id, turn_seq, is_subagent,"
            " ts, model, payload, source_path, source_line_no, collector_version)"
            " VALUES (?, ?, ?, ?, ?, ?, 'm', '{}', '/tmp/x', ?, 1)",
            (turn_raw_id, session_row_id, f"t{turn_raw_id}", turn_raw_id, is_subagent, ts, turn_raw_id),
        )
        self.conn.execute(
            "INSERT INTO turn_norm (turn_raw_id, ts, model, is_subagent, fresh_input_tokens,"
            " cache_read_tokens, cache_write_tokens, output_tokens, norm_version)"
            " VALUES (?, ?, 'm', ?, ?, 0, 0, 1, 1)",
            (turn_raw_id, ts, is_subagent, ctx),
        )

    def test_active_rows_within_filter_and_ctx_carry_math(self) -> None:
        sess = self.insert_session("active-1", harness="claude", title="live one")
        self.insert_ctx_turn(sess, "2026-01-10T10:00:00Z", 40_000)  # session start
        self.insert_ctx_turn(sess, "2026-01-10T11:50:00Z", 120_000)  # latest, 10 min ago
        stale = self.insert_session("stale-1", harness="claude")
        self.insert_ctx_turn(stale, "2026-01-10T09:00:00Z", 50_000)  # 3h ago — outside window

        rows = self.cost.active_rows(self.conn, within_minutes=60, now=self._active_now())
        self.assertEqual([r["session_id"] for r in rows], ["active-1"])
        row = rows[0]
        self.assertEqual(row["label"], "live one")
        self.assertEqual(row["ctx_pct"], 60.0)  # 120K of the 200K standard window
        self.assertEqual(row["carry_pct"], 40.0)  # (120K - 40K) of 200K
        self.assertEqual(row["idle_sec"], 600)

    def test_active_rows_excludes_subagent_turns_from_context_math(self) -> None:
        """A sidechain turn's context is a different conversation's size — if
        the newest turn overall is a subagent's, the main thread's own
        newest must still be the one reported.
        """
        sess = self.insert_session("active-1", harness="claude")
        self.insert_ctx_turn(sess, "2026-01-10T11:00:00Z", 40_000)
        self.insert_ctx_turn(sess, "2026-01-10T11:30:00Z", 100_000)
        self.insert_ctx_turn(sess, "2026-01-10T11:55:00Z", 15_000, is_subagent=1)  # newest overall

        rows = self.cost.active_rows(self.conn, within_minutes=60, now=self._active_now())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ctx_pct"], 50.0, "must report the main thread's 100K, not the sidechain's 15K")

    def test_active_rows_window_inference_flips_above_threshold(self) -> None:
        small = self.insert_session("small-ctx", harness="claude")
        self.insert_ctx_turn(small, "2026-01-10T11:50:00Z", 100_000)
        large = self.insert_session("large-ctx", harness="claude")
        self.insert_ctx_turn(large, "2026-01-10T11:50:00Z", 400_000)  # impossible on 200K

        by_id = {
            r["session_id"]: r
            for r in self.cost.active_rows(self.conn, within_minutes=60, now=self._active_now())
        }
        self.assertEqual(by_id["small-ctx"]["ctx_pct"], 50.0)  # assumed 200K window
        self.assertEqual(by_id["large-ctx"]["ctx_pct"], 40.0)  # inferred 1M window
        self.assertFalse(by_id["small-ctx"]["window_exact"])

    def test_active_rows_statusline_window_file_overrides_and_snaps(self) -> None:
        """The statusline's derived window carries integer-percent rounding
        error — a recorded 980000 must snap to the real 1M window. This is
        the one signal that can identify a 1M session still under 190K.
        Points STATUSLINE_DIR at a tmpdir rather than the host's real /tmp,
        where a stray file could flip the expectation.
        """
        import tempfile
        import unittest.mock
        from pathlib import Path as _P

        sess = self.insert_session("statusline-test-sess", harness="claude")
        self.insert_ctx_turn(sess, "2026-01-10T11:50:00Z", 100_000)
        with tempfile.TemporaryDirectory() as tmpdir:
            (_P(tmpdir) / "claude-window-statusline-test-sess").write_text("980000")
            with unittest.mock.patch.object(self.cost, "STATUSLINE_DIR", _P(tmpdir)):
                rows = self.cost.active_rows(self.conn, within_minutes=60, now=self._active_now())
        self.assertEqual(rows[0]["ctx_pct"], 10.0, "100K of the snapped 1M window")
        self.assertTrue(rows[0]["window_exact"])

    def test_active_rows_statusline_file_too_far_from_any_real_window_is_ignored(self) -> None:
        """A corrupt/truncated statusline value snapping confidently to the
        wrong window would be worse than the honest ~ inference — anything
        more than 15% from a real window falls through to inference.
        """
        import tempfile
        import unittest.mock
        from pathlib import Path as _P

        sess = self.insert_session("statusline-junk-sess", harness="claude")
        self.insert_ctx_turn(sess, "2026-01-10T11:50:00Z", 100_000)
        with tempfile.TemporaryDirectory() as tmpdir:
            (_P(tmpdir) / "claude-window-statusline-junk-sess").write_text("600000")  # equidistant junk
            with unittest.mock.patch.object(self.cost, "STATUSLINE_DIR", _P(tmpdir)):
                rows = self.cost.active_rows(self.conn, within_minutes=60, now=self._active_now())
        self.assertFalse(rows[0]["window_exact"])
        self.assertEqual(rows[0]["ctx_pct"], 50.0, "must fall through to the 200K inference")

    def test_active_rows_gap_selects_clear_vs_compact(self) -> None:
        """The idle gap BEFORE the latest turn is what distinguishes 'came
        back to new work' (/clear) from 'same work, heavy context'
        (/compact) — 20 minutes is the carried-over boundary.
        """
        clear_sess = self.insert_session("gap-clear", harness="claude")
        self.insert_ctx_turn(clear_sess, "2026-01-10T11:20:00Z", 10_000)
        self.insert_ctx_turn(clear_sess, "2026-01-10T11:50:00Z", 110_000)  # 30-min gap
        compact_sess = self.insert_session("gap-compact", harness="claude")
        self.insert_ctx_turn(compact_sess, "2026-01-10T11:45:00Z", 10_000)
        self.insert_ctx_turn(compact_sess, "2026-01-10T11:50:00Z", 110_000)  # 5-min gap

        by_id = {
            r["session_id"]: r
            for r in self.cost.active_rows(self.conn, within_minutes=60, now=self._active_now())
        }
        self.assertIn("/clear", by_id["gap-clear"]["recommend"])
        self.assertIn("/compact", by_id["gap-compact"]["recommend"])

    def test_active_rows_recommendation_thresholds(self) -> None:
        # carry 50% of 200K -> "/x now"; 30% -> "at next break"; 10% ->
        # "fine". All with a small gap (compact path).
        for sid, base, latest in (
            ("carry-high", 10_000, 110_000),  # carry 100K = 50%
            ("carry-mid", 10_000, 70_000),  # carry 60K = 30%
            ("carry-low", 10_000, 30_000),  # carry 20K = 10%
        ):
            sess = self.insert_session(sid, harness="claude")
            self.insert_ctx_turn(sess, "2026-01-10T11:45:00Z", base)
            self.insert_ctx_turn(sess, "2026-01-10T11:50:00Z", latest)

        by_id = {
            r["session_id"]: r["recommend"]
            for r in self.cost.active_rows(self.conn, within_minutes=60, now=self._active_now())
        }
        self.assertEqual(by_id["carry-high"], "/compact now")
        self.assertEqual(by_id["carry-mid"], "/compact at next break")
        self.assertEqual(by_id["carry-low"], "fine")

    def test_active_rows_sorted_worst_carry_first(self) -> None:
        small = self.insert_session("carry-small", harness="claude")
        self.insert_ctx_turn(small, "2026-01-10T11:00:00Z", 10_000)
        self.insert_ctx_turn(small, "2026-01-10T11:50:00Z", 30_000)
        big = self.insert_session("carry-big", harness="claude")
        self.insert_ctx_turn(big, "2026-01-10T11:00:00Z", 10_000)
        self.insert_ctx_turn(big, "2026-01-10T11:50:00Z", 150_000)

        rows = self.cost.active_rows(self.conn, within_minutes=60, now=self._active_now())
        self.assertEqual([r["session_id"] for r in rows], ["carry-big", "carry-small"])

    def test_active_rows_ignores_codex_sessions(self) -> None:
        sess = self.insert_session("codex-live", harness="codex")
        self.insert_ctx_turn(sess, "2026-01-10T11:50:00Z", 100_000)
        self.assertEqual(self.cost.active_rows(self.conn, within_minutes=60, now=self._active_now()), [])

    def test_active_rows_subagent_turn_older_than_session_start_does_not_corrupt_carry(self) -> None:
        """The oldest-sample query needs its own is_subagent filter — a
        sidechain turn that happens to be the session's earliest row would
        otherwise become the carry baseline. Review flagged that the
        newest-sample test alone would not catch this.
        """
        sess = self.insert_session("early-sub", harness="claude")
        self.insert_ctx_turn(sess, "2026-01-10T10:00:00Z", 5_000, is_subagent=1)  # earliest overall
        self.insert_ctx_turn(sess, "2026-01-10T10:30:00Z", 40_000)  # true main-thread start
        self.insert_ctx_turn(sess, "2026-01-10T11:50:00Z", 120_000)

        rows = self.cost.active_rows(self.conn, within_minutes=60, now=self._active_now())
        self.assertEqual(rows[0]["carry_pct"], 40.0, "carry base must be the main thread's 40K, not the sidechain's 5K")

    def test_active_rows_session_with_only_zero_context_recent_turns_drops_out(self) -> None:
        """Documented third divergence from token-report: no context sample
        inside the window means no current context to report, even when
        older nonzero samples exist.
        """
        sess = self.insert_session("zero-recent", harness="claude")
        self.insert_ctx_turn(sess, "2026-01-10T09:00:00Z", 80_000)  # nonzero but outside window
        self.insert_ctx_turn(sess, "2026-01-10T11:50:00Z", 0)  # recent but zero-context

        self.assertEqual(self.cost.active_rows(self.conn, within_minutes=60, now=self._active_now()), [])

    def test_render_active_table_marks_inferred_windows(self) -> None:
        rows = [
            {
                "id": "abc12345",
                "label": "some session",
                "ctx_pct": 46.0,
                "carry_pct": 38.0,
                "window_exact": False,
                "idle_sec": 245,
                "recommend": "/compact at next break",
                "session_id": "abc12345-full",
            }
        ]
        out = self.cost._render_active_table(rows)
        self.assertIn("~46%", out)
        self.assertIn("4m", out)
        self.assertIn("window inferred", out)

    def test_render_active_table_empty(self) -> None:
        self.assertEqual(self.cost._render_active_table([]), "(no active sessions in range)")


class VerdictTests(unittest.TestCase):
    """Direct tests of cost.py's verdict + warn engines, against an
    in-memory store and real transcript fixtures on disk (the engine's
    whole point is the harvest-then-judge pipeline, so these go through
    the real collectors rather than hand-inserting turn_norm rows).
    """

    def setUp(self) -> None:
        import sqlite3

        self._tempdir = tempfile.TemporaryDirectory()
        self.dir = Path(self._tempdir.name)
        REPO_ROOT_CLI = REPO_ROOT / "cli"
        if str(REPO_ROOT_CLI) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT_CLI))
            self._added_cli_path = True
        else:
            self._added_cli_path = False
        import usage_store
        import cost

        self.usage_store = usage_store
        self.cost = cost
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row
        for _version, _description, sql in usage_store.MIGRATIONS:
            self.conn.executescript(sql)

    def tearDown(self) -> None:
        self.conn.close()
        self._tempdir.cleanup()
        if self._added_cli_path:
            sys.path.remove(str(REPO_ROOT / "cli"))
        for name in ("usage_store", "cost"):
            sys.modules.pop(name, None)

    def _claude_transcript(self, name: str, turns: int, start_ctx: int, end_ctx: int, last_gap_min: int = 1) -> Path:
        """A Claude transcript whose context grows linearly from start_ctx to
        end_ctx across `turns` assistant turns, with `last_gap_min` minutes of
        idle before the final turn (the /clear-vs-/compact signal).
        """
        records = [_claude_user("sess-v")]
        for i in range(turns):
            ctx = start_ctx + (end_ctx - start_ctx) * i // max(1, turns - 1)
            rec = _claude_assistant("sess-v", f"req-{i}", input_tokens=ctx)
            minute = i  # one turn per minute...
            if i == turns - 1:
                minute = (turns - 2) + last_gap_min  # ...except the last
            rec["timestamp"] = f"2026-01-01T{10 + minute // 60:02d}:{minute % 60:02d}:00Z"
            records.append(rec)
        path = self.dir / name
        path.write_text(_jsonl(*records))
        return path

    def test_verdict_below_carry_floor_is_silent(self) -> None:
        path = self._claude_transcript("a.jsonl", turns=20, start_ctx=10_000, end_ctx=20_000)
        self.assertIsNone(self.cost.verdict_for_transcript(self.conn, path))

    def test_verdict_young_session_is_silent_despite_heavy_carry(self) -> None:
        path = self._claude_transcript("a.jsonl", turns=5, start_ctx=10_000, end_ctx=150_000)
        self.assertIsNone(self.cost.verdict_for_transcript(self.conn, path))

    def test_verdict_compact_when_working_continuously(self) -> None:
        path = self._claude_transcript("a.jsonl", turns=20, start_ctx=10_000, end_ctx=150_000, last_gap_min=2)
        v = self.cost.verdict_for_transcript(self.conn, path)
        self.assertIsNotNone(v)
        self.assertEqual(v["action"], "compact")
        self.assertEqual(v["carry"], 140_000)
        self.assertEqual(v["ctx"], 150_000)
        self.assertEqual(v["why"], "")

    def test_verdict_clear_after_a_topic_gap(self) -> None:
        path = self._claude_transcript("a.jsonl", turns=20, start_ctx=10_000, end_ctx=150_000, last_gap_min=45)
        v = self.cost.verdict_for_transcript(self.conn, path)
        self.assertIsNotNone(v)
        self.assertEqual(v["action"], "clear")
        self.assertIn("idle 45m", v["why"])

    def test_verdict_works_for_codex_transcripts(self) -> None:
        codex_dir = self.dir / ".codex" / "sessions" / "2026" / "01" / "01"
        codex_dir.mkdir(parents=True)
        records = [_session_meta("sess-cx")]
        for i in range(20):
            records.append(_task_started(f"turn-{i}"))
            records.append(_turn_context(f"turn-{i}", "gpt-5.6"))
            tc = _token_count(total=10_000 + i * 8_000)
            tc["timestamp"] = f"2026-01-01T10:{i:02d}:00Z"
            records.append(tc)
            records.append(_task_complete(f"turn-{i}"))
        path = codex_dir / "rollout-verdict.jsonl"
        path.write_text(_jsonl(*records))

        v = self.cost.verdict_for_transcript(self.conn, path)
        self.assertIsNotNone(v)
        self.assertEqual(v["harness"], "codex")
        self.assertEqual(v["action"], "compact")
        self.assertEqual(v["carry"], 8_000 * 19)

    def test_verdict_session_id_takes_precedence_over_path_lookup(self) -> None:
        """Hook mode passes the runtime's own session_id — a resumed session
        whose transcript is a second file (source_path points at the first)
        must still resolve.
        """
        path = self._claude_transcript("a.jsonl", turns=20, start_ctx=10_000, end_ctx=150_000)
        # Simulate the source_path pointing elsewhere.
        self.cost.verdict_for_transcript(self.conn, path)  # harvest + create session
        self.conn.execute("UPDATE session SET source_path = '/somewhere/else.jsonl'")
        renamed = self.dir / "b.jsonl"
        path.rename(renamed)
        v = self.cost.verdict_for_transcript(self.conn, renamed, session_id="sess-v")
        self.assertIsNotNone(v)

    # ------------------------------------------------------------------
    # warn engine
    # ------------------------------------------------------------------

    def _warn(self, sid: str, tpath: str = "/Users/x/.claude/projects/p/t.jsonl") -> str:
        import contextlib
        import io
        import unittest.mock

        stdin = io.StringIO(json.dumps({"session_id": sid, "transcript_path": tpath}))
        out = io.StringIO()
        with unittest.mock.patch.object(self.cost.sys, "stdin", stdin):
            with contextlib.redirect_stdout(out):
                rc = self.cost.cost_warn_command()
        self.assertEqual(rc, 0)
        return out.getvalue()

    def test_warn_fires_once_and_throttles_until_carry_grows(self) -> None:
        import unittest.mock

        with unittest.mock.patch.object(self.cost, "VERDICT_DIR", self.dir):
            (self.dir / "claude-verdict-sid1").write_text("/compact?\t120000\t150000\t\n")
            first = self._warn("sid1")
            self.assertIn("flow advisory", first)
            self.assertIn("120K", first)

            second = self._warn("sid1")
            self.assertEqual(second, "", "same carry must not re-warn")

            (self.dir / "claude-verdict-sid1").write_text("/compact?\t180000\t210000\t\n")
            third = self._warn("sid1")
            self.assertIn("180K", third, "carry grew past the re-warn step")

    def test_warn_is_silent_below_the_floor_and_without_a_verdict(self) -> None:
        import unittest.mock

        with unittest.mock.patch.object(self.cost, "VERDICT_DIR", self.dir):
            self.assertEqual(self._warn("sid-none"), "")
            (self.dir / "claude-verdict-sid2").write_text("/compact?\t60000\t90000\t\n")
            self.assertEqual(self._warn("sid2"), "")


class VerdictHookModeTests(unittest.TestCase):
    """cost_verdict_command in --hook mode — the code path that runs
    unattended on every Stop of every session. Direct calls with patched
    HOME/VERDICT_DIR/stdin; no subprocess, so failures are debuggable.
    """

    def setUp(self) -> None:
        REPO_ROOT_CLI = REPO_ROOT / "cli"
        if str(REPO_ROOT_CLI) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT_CLI))
            self._added_cli_path = True
        else:
            self._added_cli_path = False
        import cost

        self.cost = cost
        self._tempdir = tempfile.TemporaryDirectory()
        self.dir = Path(self._tempdir.name)
        self.home = self.dir / "home"
        (self.home / ".flow").mkdir(parents=True)
        self.verdicts = self.dir / "verdicts"
        self.verdicts.mkdir()

    def tearDown(self) -> None:
        self._tempdir.cleanup()
        if self._added_cli_path:
            sys.path.remove(str(REPO_ROOT / "cli"))
        sys.modules.pop("cost", None)

    def _run_hook(self, payload) -> int:
        import contextlib
        import io
        import unittest.mock

        stdin = io.StringIO(payload if isinstance(payload, str) else json.dumps(payload))
        with unittest.mock.patch.object(self.cost, "HOME", self.home):
            with unittest.mock.patch.object(self.cost, "VERDICT_DIR", self.verdicts):
                with unittest.mock.patch.object(self.cost.sys, "stdin", stdin):
                    with contextlib.redirect_stdout(io.StringIO()) as out:
                        rc = self.cost.cost_verdict_command(hook=True)
        self.assertEqual(out.getvalue(), "", "hook mode must never print")
        return rc

    def _heavy_transcript(self, name: str = "t.jsonl", end_ctx: int = 150_000) -> Path:
        records = [_claude_user("sess-h")]
        for i in range(20):
            ctx = 10_000 + (end_ctx - 10_000) * i // 19
            rec = _claude_assistant("sess-h", f"req-{i}", input_tokens=ctx)
            rec["timestamp"] = f"2026-01-01T10:{i:02d}:00Z"
            records.append(rec)
        path = self.dir / name
        path.write_text(_jsonl(*records))
        return path

    def test_hook_writes_the_verdict_file(self) -> None:
        path = self._heavy_transcript()
        rc = self._run_hook({"session_id": "sess-h", "transcript_path": str(path)})
        self.assertEqual(rc, 0)
        content = (self.verdicts / "claude-verdict-sess-h").read_text()
        self.assertTrue(content.startswith("/compact?\t140000\t150000"))

    def test_hook_removes_verdict_and_warn_marker_when_below_floor(self) -> None:
        """A /compact drops carry below the floor: BOTH the verdict file and
        the warn hook's high-water marker must go, or re-warning stays
        suppressed until carry exceeds the PRE-compact high + step.
        """
        (self.verdicts / "claude-verdict-sess-l").write_text("/compact?\t140000\t150000\t\n")
        (self.verdicts / "claude-warned-sess-l").write_text("140000")
        records = [_claude_user("sess-l")]
        for i in range(20):
            rec = _claude_assistant("sess-l", f"req-{i}", input_tokens=10_000 + i * 100)
            rec["timestamp"] = f"2026-01-01T10:{i:02d}:00Z"
            records.append(rec)
        path = self.dir / "light.jsonl"
        path.write_text(_jsonl(*records))

        rc = self._run_hook({"session_id": "sess-l", "transcript_path": str(path)})
        self.assertEqual(rc, 0)
        self.assertFalse((self.verdicts / "claude-verdict-sess-l").exists())
        self.assertFalse((self.verdicts / "claude-warned-sess-l").exists())

    def test_hook_malformed_stdin_exits_zero_and_writes_nothing(self) -> None:
        rc = self._run_hook("not json at all")
        self.assertEqual(rc, 0)
        self.assertEqual(list(self.verdicts.iterdir()), [])

    def test_hook_hostile_session_id_exits_zero_and_writes_nothing(self) -> None:
        path = self._heavy_transcript()
        rc = self._run_hook({"session_id": "../../etc/evil", "transcript_path": str(path)})
        self.assertEqual(rc, 0)
        self.assertEqual(list(self.verdicts.iterdir()), [])

    def test_hook_internal_error_exits_zero_and_leaves_existing_file(self) -> None:
        import unittest.mock

        (self.verdicts / "claude-verdict-sess-h").write_text("/compact?\t99\t100\t\n")
        path = self._heavy_transcript()
        with unittest.mock.patch.object(
            self.cost, "verdict_for_transcript", side_effect=RuntimeError("store wedged")
        ):
            rc = self._run_hook({"session_id": "sess-h", "transcript_path": str(path)})
        self.assertEqual(rc, 0, "a broken verdict must never block a Stop")
        self.assertEqual(
            (self.verdicts / "claude-verdict-sess-h").read_text(),
            "/compact?\t99\t100\t\n",
            "stale beats flapping: an internal error must not remove the file",
        )

    def test_hook_missing_transcript_exits_zero(self) -> None:
        rc = self._run_hook({"session_id": "sess-h", "transcript_path": str(self.dir / "nope.jsonl")})
        self.assertEqual(rc, 0)


class OverlayVcsTests(unittest.TestCase):
    """cli/overlay.py — read-only VCS status for ~/.flow/user/.

    Uses real git repos in a tmpdir (a local bare repo stands in for the
    remote, so nothing here touches the network).
    """

    def setUp(self) -> None:
        REPO_ROOT_CLI = REPO_ROOT / "cli"
        if str(REPO_ROOT_CLI) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT_CLI))
            self._added_cli_path = True
        else:
            self._added_cli_path = False
        import overlay

        self.overlay = overlay
        self._tempdir = tempfile.TemporaryDirectory()
        self.dir = Path(self._tempdir.name)
        (self.dir / "empty-bin").mkdir()

    def tearDown(self) -> None:
        self._tempdir.cleanup()
        if self._added_cli_path:
            sys.path.remove(str(REPO_ROOT / "cli"))
        sys.modules.pop("overlay", None)

    def _git(self, cwd: Path, *args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
                 "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e"},
        )

    def _repo_with_content(self) -> Path:
        d = self.dir / "user"
        d.mkdir()
        (d / "flow.toml").write_text("# overlay\n")
        self._git(d, "init", "-b", "main")
        self._git(d, "add", ".")
        self._git(d, "commit", "-m", "initial")
        return d

    def test_absent_overlay_is_not_a_problem(self) -> None:
        status = self.overlay.overlay_vcs_status(self.dir / "nope")
        self.assertFalse(status["present"])
        self.assertFalse(status["tracked"])
        self.assertEqual(self.overlay.format_overlay_vcs(status), "n/a (no overlay)")

    def test_untracked_overlay_names_the_fix(self) -> None:
        d = self.dir / "user"
        d.mkdir()
        (d / "flow.toml").write_text("# overlay\n")
        status = self.overlay.overlay_vcs_status(d)
        self.assertTrue(status["present"])
        self.assertFalse(status["tracked"], "authored content with no history is the state this surfaces")
        self.assertIn("--overlay-repo", self.overlay.format_overlay_vcs(status))

    def test_clean_repo_without_a_remote_says_so(self) -> None:
        d = self._repo_with_content()
        status = self.overlay.overlay_vcs_status(d)
        self.assertTrue(status["tracked"])
        self.assertFalse(status["error"])
        self.assertEqual(status["dirty"], [])
        self.assertIsNone(status["unpushed"], "None means no upstream; 0 would mean level with one")
        self.assertEqual(status["branch"], "main")
        self.assertIn("no remote", self.overlay.format_overlay_vcs(status))

    def test_unreadable_repo_reports_an_error_not_a_plausible_status(self) -> None:
        """Review finding: when every git call failed, the old code synthesized
        `no upstream (detached)` for what might be a clean, pushed repo. A
        diagnostic that states a false condition is worse than one that admits
        it cannot read. Simulates an unresolvable git via a PATH with no git.
        """
        import unittest.mock

        d = self._repo_with_content()
        broken = {k: v for k, v in os.environ.items() if k != "PATH"}
        broken["PATH"] = str(self.dir / "empty-bin")
        with unittest.mock.patch.object(self.overlay, "git_env", return_value=broken):
            status = self.overlay.overlay_vcs_status(d)
        self.assertFalse(
            status["tracked"],
            "with no git to ask, membership is unknown — claiming tracked would be the same "
            "kind of fabrication this test exists to prevent",
        )
        self.assertTrue(status["error"])
        self.assertEqual(self.overlay.format_overlay_vcs(status), "unreadable (git error)")

    def test_missing_git_is_not_mistaken_for_an_untracked_overlay(self) -> None:
        """A broken machine and an ordinary untracked directory need opposite
        messages. Both used to leave `_git` with returncode 1; `_GIT_DID_NOT_RUN`
        is what keeps `--overlay-repo` from being offered as the fix for a
        missing git binary."""
        import unittest.mock

        d = self._repo_with_content()
        broken = {k: v for k, v in os.environ.items() if k != "PATH"}
        broken["PATH"] = str(self.dir / "empty-bin")
        with unittest.mock.patch.object(self.overlay, "git_env", return_value=broken):
            line = self.overlay.format_overlay_vcs(self.overlay.overlay_vcs_status(d))
        self.assertNotIn("--overlay-repo", line, "installing a remote would not fix a missing git")

    def test_overlay_in_a_subdirectory_of_a_repo_is_tracked(self) -> None:
        """The bug this chunk exists to fix. `.git` lives only at a work
        tree's root, so a filesystem test calls a committed subdirectory
        untracked — and chunk 3 makes exactly that the normal arrangement."""
        root = self._repo_with_content()
        nested = root / "flow-user-overlay"
        nested.mkdir()
        (nested / "flow.toml").write_text("# overlay\n")
        self._git(root, "add", ".")
        self._git(root, "commit", "-m", "add overlay subtree")

        status = self.overlay.overlay_vcs_status(nested)
        self.assertTrue(status["tracked"], "committed content inside a repo is tracked")
        self.assertFalse(status["is_root"])
        self.assertEqual(Path(status["root"]).resolve(), root.resolve())
        self.assertEqual(status["branch"], "main")

    def test_symlinked_overlay_resolves_to_its_real_repo(self) -> None:
        """`~/.flow/user` becomes a symlink into the dotfiles repo. Following
        it must land on the repo, not report a rootless directory."""
        root = self._repo_with_content()
        nested = root / "flow-user-overlay"
        nested.mkdir()
        (nested / "flow.toml").write_text("# overlay\n")
        self._git(root, "add", ".")
        self._git(root, "commit", "-m", "add overlay subtree")

        link = self.dir / "linked-user"
        link.symlink_to(nested)
        status = self.overlay.overlay_vcs_status(link)
        self.assertTrue(status["tracked"])
        self.assertFalse(status["is_root"], "the link target is a subdirectory, not the root")

    def test_repo_root_overlay_still_reports_itself_as_root(self) -> None:
        """The pre-existing arrangement must not regress: when the overlay is
        the repo, `doctor` should not start appending a redundant path."""
        d = self._repo_with_content()
        status = self.overlay.overlay_vcs_status(d)
        self.assertTrue(status["is_root"])
        self.assertNotIn("—", self.overlay.format_overlay_vcs(status))

    def test_overlay_inside_a_repo_but_gitignored_is_not_called_tracked(self) -> None:
        """Inside a repo is not the same as kept by it. Reporting `clean` here
        would be the exact false-clean this chunk removes: every file stays
        permanently uncommitted while `doctor` says it is backed up."""
        root = self._repo_with_content()
        (root / ".gitignore").write_text("flow-user-overlay/\n")
        self._git(root, "add", ".gitignore")
        self._git(root, "commit", "-m", "ignore the overlay")

        nested = root / "flow-user-overlay"
        nested.mkdir()
        (nested / "flow.toml").write_text("# never committed\n")

        status = self.overlay.overlay_vcs_status(nested)
        self.assertTrue(status["ignored"])
        self.assertFalse(status["tracked"], "ignored content has no more history than untracked content")
        line = self.overlay.format_overlay_vcs(status)
        self.assertIn("ignored", line)
        self.assertNotIn("--overlay-repo", line, "adding a remote would not un-ignore it")

    def test_symlinked_overlay_inside_an_ignored_path_is_not_called_tracked(self) -> None:
        """The production topology, and the one the `.resolve()` fix exists
        for. Verified empirically that git returns 128 ("outside repository")
        for the unresolved symlink path and 0 for the resolved one — so
        without resolving, the guard is inert precisely here and `doctor`
        reports a confident clean status for content that is never committed.

        The pre-existing non-symlink case passes on macOS with or without the
        fix only by accident of `/var` vs `/private/var`; on a platform where
        tmpdirs are not symlinked it would not catch this at all.
        """
        root = self._repo_with_content()
        (root / ".gitignore").write_text("flow-user-overlay/\n")
        self._git(root, "add", ".gitignore")
        self._git(root, "commit", "-m", "ignore the overlay")
        nested = root / "flow-user-overlay"
        nested.mkdir()
        (nested / "flow.toml").write_text("# never committed\n")

        link = self.dir / "linked-ignored-user"
        link.symlink_to(nested)

        status = self.overlay.overlay_vcs_status(link)
        self.assertTrue(status["ignored"], "reached through a symlink, git needs the resolved path")
        self.assertFalse(status["tracked"])
        self.assertIn("ignored", self.overlay.format_overlay_vcs(status))

    def test_display_path_contracts_home(self) -> None:
        self.assertEqual(self.overlay.display_path(Path.home() / "x"), "~/x")
        self.assertEqual(self.overlay.display_path(Path("/etc/hosts")), "/etc/hosts")

    def test_nested_overlay_reports_the_whole_repo_as_dirty(self) -> None:
        """Whole-repo scoping is deliberate: uncommitted work beside the
        overlay is the same hazard as uncommitted work in it."""
        root = self._repo_with_content()
        nested = root / "flow-user-overlay"
        nested.mkdir()
        (nested / "flow.toml").write_text("# overlay\n")
        self._git(root, "add", ".")
        self._git(root, "commit", "-m", "add overlay subtree")
        (root / "bin-script.sh").write_text("#!/bin/sh\n")

        status = self.overlay.overlay_vcs_status(nested)
        self.assertEqual(len(status["dirty"]), 1, "a sibling's dirt counts")

    def test_detached_head_is_not_reported_as_a_branch_named_head(self) -> None:
        d = self._repo_with_content()
        (d / "second.md").write_text("x\n")
        self._git(d, "add", ".")
        self._git(d, "commit", "-m", "second")
        first = subprocess.run(
            ["git", "rev-list", "--max-parents=0", "HEAD"], cwd=d, capture_output=True, text=True
        ).stdout.strip()
        self._git(d, "checkout", first)
        status = self.overlay.overlay_vcs_status(d)
        self.assertIsNone(status["branch"], "`rev-parse --abbrev-ref` would have said 'HEAD' here")
        self.assertIn("detached", self.overlay.format_overlay_vcs(status))

    def test_repo_with_no_commits_yet_reports_its_branch(self) -> None:
        d = self.dir / "unborn"
        d.mkdir()
        self._git(d, "init", "-b", "main")
        (d / "flow.toml").write_text("# staged nothing\n")
        status = self.overlay.overlay_vcs_status(d)
        self.assertEqual(status["branch"], "main", "an unborn branch still has a name")
        self.assertFalse(status["error"])

    def test_gitignore_actually_excludes_credential_shaped_files(self) -> None:
        """Behavioral, not a constant mirror: writes the shipped ignore file and
        asks git what it excludes. Catches pattern-semantics mistakes the old
        substring assertion could not — `*.local.*` alone does not match a file
        named `settings.local`.
        """
        d = self._repo_with_content()
        (d / ".gitignore").write_text(self.overlay.OVERLAY_GITIGNORE)
        for name in (".env", "settings.local", "settings.local.json", "app.pem", "my.token"):
            (d / name).write_text("secret\n")
        (d / "keys").mkdir()
        (d / "keys" / "k.pub").write_text("k\n")

        untracked = subprocess.run(
            ["git", "status", "--porcelain"], cwd=d, capture_output=True, text=True
        ).stdout
        for name in (".env", "settings.local", "settings.local.json", "app.pem", "my.token", "keys/"):
            self.assertNotIn(name, untracked, f"{name} must be ignored")
        self.assertIn(".gitignore", untracked, "the ignore file itself is tracked content")

    def test_dirty_files_are_counted(self) -> None:
        d = self._repo_with_content()
        (d / "commands").mkdir()
        (d / "commands" / "new.md").write_text("# new\n")
        status = self.overlay.overlay_vcs_status(d)
        self.assertEqual(len(status["dirty"]), 1)
        self.assertIn("1 uncommitted", self.overlay.format_overlay_vcs(status))

    def test_unpushed_commits_are_counted_against_a_real_upstream(self) -> None:
        remote = self.dir / "remote.git"
        remote.mkdir()
        self._git(remote, "init", "--bare", "-b", "main")
        d = self._repo_with_content()
        self._git(d, "remote", "add", "origin", str(remote))
        self._git(d, "push", "-u", "origin", "main")

        status = self.overlay.overlay_vcs_status(d)
        self.assertEqual(status["unpushed"], 0, "level with upstream is 0, not None")
        self.assertIn("clean", self.overlay.format_overlay_vcs(status))
        self.assertEqual(status["remote"], str(remote))

        (d / "another.md").write_text("x\n")
        self._git(d, "add", ".")
        self._git(d, "commit", "-m", "second")
        status = self.overlay.overlay_vcs_status(d)
        self.assertEqual(status["unpushed"], 1)
        self.assertIn("1 unpushed", self.overlay.format_overlay_vcs(status))


class OverlayNudgeTests(unittest.TestCase):
    """`flow overlay check --hook` — the code path that runs unattended on
    every prompt and every Write/Edit of every session.

    The bar is the same one the verdict hook is held to: silence unless there
    is something to say, and exit 0 no matter what goes wrong. A nudge that
    errors on every prompt would be the loudest possible failure of a feature
    whose premise is staying quiet.
    """

    def setUp(self) -> None:
        REPO_ROOT_CLI = REPO_ROOT / "cli"
        if str(REPO_ROOT_CLI) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT_CLI))
            self._added_cli_path = True
        else:
            self._added_cli_path = False
        import overlay

        self.overlay = overlay
        self._tempdir = tempfile.TemporaryDirectory()
        self.dir = Path(self._tempdir.name)
        self.state = self.dir / "state"

    def tearDown(self) -> None:
        self._tempdir.cleanup()
        if self._added_cli_path:
            sys.path.remove(str(REPO_ROOT / "cli"))
        sys.modules.pop("overlay", None)

    def _git(self, cwd: Path, *args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
                 "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e"},
        )

    def _overlay_repo(self, with_remote: bool = True) -> Path:
        """A tracked overlay. `with_remote` is on by default because a repo
        with nowhere to push is itself a nudge-worthy state, so a test that
        wants "nothing to report" has to opt into being backed up."""
        d = self.dir / "user"
        d.mkdir()
        (d / "flow.toml").write_text("# overlay\n")
        self._git(d, "init", "-b", "main")
        self._git(d, "add", ".")
        self._git(d, "commit", "-m", "initial")
        if with_remote:
            bare = self.dir / "remote.git"
            bare.mkdir()
            self._git(bare, "init", "--bare", "-b", "main")
            self._git(d, "remote", "add", "origin", str(bare))
            self._git(d, "push", "-u", "origin", "main")
        return d

    def _run_hook(self, payload, overlay_dir: Path) -> tuple[int, str]:
        import contextlib
        import io
        import unittest.mock

        stdin = io.StringIO(payload if isinstance(payload, str) else json.dumps(payload))
        with unittest.mock.patch.object(self.overlay, "USER_OVERLAY_DIR", overlay_dir):
            with unittest.mock.patch.object(self.overlay, "NUDGE_STATE_DIR", self.state):
                with unittest.mock.patch.object(self.overlay.hookio.sys, "stdin", stdin):
                    with contextlib.redirect_stdout(io.StringIO()) as out:
                        rc = self.overlay.overlay_check_command()
        return rc, out.getvalue()

    def test_clean_repo_says_nothing(self) -> None:
        d = self._overlay_repo()
        rc, out = self._run_hook({"hook_event_name": "UserPromptSubmit"}, d)
        self.assertEqual(rc, 0)
        self.assertEqual(out, "", "a committed overlay has nothing to nudge about")

    def test_untracked_overlay_is_left_to_doctor(self) -> None:
        """Someone who never opted into an overlay repo must not be nagged on
        every prompt. `doctor` is where that state belongs."""
        d = self.dir / "plain"
        d.mkdir()
        (d / "flow.toml").write_text("# no repo here\n")
        rc, out = self._run_hook({"hook_event_name": "UserPromptSubmit"}, d)
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")

    def test_dirty_repo_nudges_once_then_throttles(self) -> None:
        d = self._overlay_repo()
        (d / "new-command.md").write_text("# authored\n")

        rc, first = self._run_hook({"hook_event_name": "UserPromptSubmit"}, d)
        self.assertEqual(rc, 0)
        self.assertIn("1 uncommitted file", first)
        self.assertIn("FRAMEWORK.md", first, "the line has to name the convention it points at")

        _, second = self._run_hook({"hook_event_name": "UserPromptSubmit"}, d)
        self.assertEqual(second, "", "an unchanged outstanding set stays quiet")

    def test_the_advisory_is_conditional_not_an_instruction(self) -> None:
        """The reported state covers the whole repository, and the session
        reading the line may have had nothing to do with it. A runtime that
        pre-authorizes `git push` would otherwise be told, unconditionally,
        to publish changes it did not make and cannot evaluate."""
        d = self._overlay_repo()
        (d / "someone-elses-work.md").write_text("x\n")
        _, out = self._run_hook({"hook_event_name": "UserPromptSubmit"}, d)
        self.assertIn("If this session made those changes", out)
        self.assertIn("leave them alone", out)

    def test_posttooluse_output_is_the_json_envelope(self) -> None:
        """Only UserPromptSubmit and SessionStart add plain stdout to the
        model's context. A PostToolUse line printed bare reaches the
        transcript and nothing else — the hook would look like it worked
        while being invisible to the agent it is trying to reach."""
        d = self._overlay_repo()
        (d / "edited.md").write_text("x\n")
        _, out = self._run_hook(
            {"hook_event_name": "PostToolUse", "tool_input": {"file_path": str(d / "edited.md")}}, d
        )
        payload = json.loads(out)
        self.assertEqual(payload["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertIn("uncommitted", payload["hookSpecificOutput"]["additionalContext"])

    def test_prompt_output_is_plain_text_not_json(self) -> None:
        d = self._overlay_repo()
        (d / "edited.md").write_text("x\n")
        _, out = self._run_hook({"hook_event_name": "UserPromptSubmit"}, d)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(out)

    def test_a_repo_with_nowhere_to_push_is_worth_saying(self) -> None:
        """Fifty local commits and no remote means zero copies off this
        machine — the literal scenario the overlay got a repo for. `unpushed`
        is None rather than a count in that state, so a truthiness test alone
        would stay silent about it."""
        d = self._overlay_repo(with_remote=False)
        _, out = self._run_hook({"hook_event_name": "UserPromptSubmit"}, d)
        self.assertIn("no remote", out)

    def test_sessions_do_not_silence_each_other(self) -> None:
        """One marker per repo let whichever session fired first suppress
        every other one for the whole window — including, most likely, the
        session that actually made the edits."""
        d = self._overlay_repo()
        (d / "work.md").write_text("x\n")
        _, first = self._run_hook({"hook_event_name": "UserPromptSubmit", "session_id": "sess-a"}, d)
        self.assertIn("uncommitted", first)

        _, second = self._run_hook({"hook_event_name": "UserPromptSubmit", "session_id": "sess-b"}, d)
        self.assertIn("uncommitted", second, "a second session has not been told yet")

        _, repeat = self._run_hook({"hook_event_name": "UserPromptSubmit", "session_id": "sess-a"}, d)
        self.assertEqual(repeat, "", "but the first session is still throttled")

    def test_a_backwards_clock_does_not_silence_the_nudge_forever(self) -> None:
        """A marker timestamped in the future makes elapsed negative, which
        reads as "inside the window" — and the suppressed branch never
        rewrites the marker, so it would stay suppressed for as long as the
        skew lasts."""
        import time as _time
        import unittest.mock

        d = self._overlay_repo()
        (d / "work.md").write_text("x\n")
        status = self.overlay.overlay_vcs_status(d)
        # Patched, unlike the original version of this test: every other case
        # here reaches the state dir through `_run_hook`, which patches it.
        # Calling `should_nudge` directly wrote into the developer's real
        # ~/.flow/state/ — and since `write_marker` swallows OSError, an
        # unwritable dir would mean no marker, which fires, which passes even
        # with the guard reverted.
        with unittest.mock.patch.object(self.overlay, "NUDGE_STATE_DIR", self.state):
            marker = self.overlay._marker_path(status["root"], "UserPromptSubmit")
            self.overlay.hookio.write_marker(
                marker, f"{_time.time() + 86400}\t{self.overlay.nudge_fingerprint(status)}"
            )
            self.assertTrue(marker.exists(), "the future-dated marker must exist for this to test anything")
            self.assertTrue(
                self.overlay.should_nudge(
                    status, "UserPromptSubmit", throttle_sec=1800, refire_on_change=False
                )
            )

    def test_standing_condition_is_not_keyed_per_session(self) -> None:
        """A repo with no remote is a property of the repo, not of anyone's
        work. Keyed per session it would re-fire on every new session and
        every /clear, turning a once-a-day note into permanent noise."""
        d = self._overlay_repo(with_remote=False)
        _, first = self._run_hook({"hook_event_name": "UserPromptSubmit", "session_id": "sess-a"}, d)
        self.assertIn("no remote", first)
        _, other = self._run_hook({"hook_event_name": "UserPromptSubmit", "session_id": "sess-b"}, d)
        self.assertEqual(other, "", "a different session must not restart the 24h window")

    def test_edit_nudge_names_the_edited_path_not_the_whole_repo(self) -> None:
        """The counts are whole-repo. Telling a session with `git push`
        pre-authorized to 'commit and push them' invites `git add -A` over
        files it does not own."""
        d = self._overlay_repo()
        (d / "mine.md").write_text("x\n")
        (d / "someone-elses.md").write_text("y\n")
        _, out = self._run_hook(
            {"hook_event_name": "PostToolUse", "tool_input": {"file_path": str(d / "mine.md")}}, d
        )
        context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("mine.md", context)
        self.assertIn("do not stage the rest", context)

    def test_standing_marker_does_not_swallow_a_real_edit_nudge(self) -> None:
        """`session=None` is both the standing key and the fallback when a
        payload has no session_id — the Codex case. Sharing one key let a 24h
        standing marker suppress genuine edit nudges for the whole edit
        window."""
        d = self._overlay_repo(with_remote=False)
        _, standing = self._run_hook({"hook_event_name": "PostToolUse"}, d)
        self.assertIn("no remote", standing)

        (d / "real-work.md").write_text("x\n")
        _, edit = self._run_hook({"hook_event_name": "PostToolUse"}, d)
        self.assertIn("uncommitted", edit, "the standing marker must not silence real work")

    def test_edit_throttle_short_circuits_before_the_expensive_calls(self) -> None:
        """Codex has no per-tool matcher and its tool calls carry no single
        file_path, so every `exec` reached the full status. Measured at ~194ms
        per call before this; the throttle now decides first."""
        import unittest.mock

        d = self._overlay_repo()
        (d / "work.md").write_text("x\n")
        self._run_hook({"hook_event_name": "PostToolUse"}, d)  # arms the marker

        real = self.overlay.overlay_vcs_status
        calls = []

        def counting(*a, **kw):
            calls.append(1)
            return real(*a, **kw)

        with unittest.mock.patch.object(self.overlay, "overlay_vcs_status", counting):
            _, out = self._run_hook({"hook_event_name": "PostToolUse"}, d)
        self.assertEqual(out, "", "still throttled")
        self.assertEqual(calls, [], "and it did not compute a status to find that out")

    def test_stale_markers_are_pruned(self) -> None:
        """`~/.flow/state/` is permanent, unlike the /tmp the verdict files
        live in, and markers are per-session — so nothing bounds them without
        this."""
        import os as _os
        import time as _time

        d = self._overlay_repo()
        (d / "work.md").write_text("x\n")
        self._run_hook({"hook_event_name": "UserPromptSubmit", "session_id": "recent"}, d)

        ancient = self.state / "overlay-nudge-UserPromptSubmit-deadbeef-old"
        ancient.write_text("0\tstale")
        old = _time.time() - (self.overlay.NUDGE_MARKER_TTL_SEC + 60)
        _os.utime(ancient, (old, old))

        self._run_hook({"hook_event_name": "UserPromptSubmit", "session_id": "another"}, d)
        self.assertFalse(ancient.exists(), "a marker past its TTL should be gone")
        self.assertTrue(
            any(self.state.glob("overlay-nudge-*")), "fresh markers must survive the prune"
        )

    def test_relative_edit_path_falls_back_rather_than_guessing(self) -> None:
        """A relative path would resolve against the hook process's cwd,
        which is not necessarily the runtime's."""
        d = self._overlay_repo()
        (d / "dirty.md").write_text("x\n")
        _, out = self._run_hook(
            {"hook_event_name": "PostToolUse", "tool_input": {"file_path": "relative/path.md"}}, d
        )
        self.assertIn("uncommitted", out, "unknown location degrades to reporting, not to silence")

    def test_new_work_refires_the_prompt_nudge_before_the_window_expires(self) -> None:
        """The throttle must not swallow work that piles up behind it."""
        d = self._overlay_repo()
        (d / "one.md").write_text("x\n")
        _, first = self._run_hook({"hook_event_name": "UserPromptSubmit"}, d)
        self.assertIn("1 uncommitted file", first)

        (d / "two.md").write_text("y\n")
        _, second = self._run_hook({"hook_event_name": "UserPromptSubmit"}, d)
        self.assertIn("2 uncommitted files", second)

    def test_edit_nudge_does_not_refire_per_file(self) -> None:
        """PostToolUse is bounded by edits, so a ten-file burst should produce
        one line, not ten. This is the opposite policy from the prompt nudge,
        on purpose."""
        d = self._overlay_repo()
        (d / "one.md").write_text("x\n")
        payload = {"hook_event_name": "PostToolUse", "tool_input": {"file_path": str(d / "one.md")}}
        _, first = self._run_hook(payload, d)
        self.assertIn("uncommitted", first)

        (d / "two.md").write_text("y\n")
        payload["tool_input"]["file_path"] = str(d / "two.md")
        _, second = self._run_hook(payload, d)
        self.assertEqual(second, "", "the edit nudge is an awareness ping, not a per-file alarm")

    def test_edit_outside_the_repo_is_ignored(self) -> None:
        d = self._overlay_repo()
        (d / "dirty.md").write_text("x\n")
        outside = self.dir / "somewhere-else.py"
        outside.write_text("# unrelated\n")
        rc, out = self._run_hook(
            {"hook_event_name": "PostToolUse", "tool_input": {"file_path": str(outside)}}, d
        )
        self.assertEqual(rc, 0)
        self.assertEqual(out, "", "editing an unrelated file is not an overlay event")

    def test_edit_without_a_path_falls_back_instead_of_going_silent(self) -> None:
        """Codex's PostToolUse payload shape is unverified. An absent
        file_path must degrade to the plain outstanding-work check, not
        disable the hook on that runtime."""
        d = self._overlay_repo()
        (d / "dirty.md").write_text("x\n")
        rc, out = self._run_hook({"hook_event_name": "PostToolUse"}, d)
        self.assertEqual(rc, 0)
        self.assertIn("uncommitted", out)

    def test_unpushed_commits_are_worth_a_nudge_on_their_own(self) -> None:
        """`doctor` reports `N unpushed`, so committing without pushing
        produces exactly the state FRAMEWORK.md tells agents to avoid."""
        d = self._overlay_repo()
        (d / "later.md").write_text("z\n")
        self._git(d, "add", ".")
        self._git(d, "commit", "-m", "committed but not pushed")

        _, out = self._run_hook({"hook_event_name": "UserPromptSubmit"}, d)
        self.assertIn("1 unpushed commit", out)

    def test_unrelated_events_are_ignored(self) -> None:
        d = self._overlay_repo()
        (d / "dirty.md").write_text("x\n")
        rc, out = self._run_hook({"hook_event_name": "SessionStart"}, d)
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")

    def test_malformed_stdin_exits_zero_and_says_nothing(self) -> None:
        d = self._overlay_repo()
        (d / "dirty.md").write_text("x\n")
        rc, out = self._run_hook("not json at all", d)
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")

    def test_internal_error_exits_zero_and_is_logged(self) -> None:
        """Every failure is swallowed, but never silently: the breadcrumb log
        is what keeps silent-by-design from becoming invisible-forever."""
        import contextlib
        import io
        import unittest.mock

        logged = []
        stdin = io.StringIO(json.dumps({"hook_event_name": "UserPromptSubmit"}))
        with unittest.mock.patch.object(
            self.overlay, "overlay_vcs_status", side_effect=RuntimeError("boom")
        ):
            with unittest.mock.patch.object(
                self.overlay.hookio, "log_hook_error", side_effect=lambda *a: logged.append(a)
            ):
                with unittest.mock.patch.object(self.overlay.hookio.sys, "stdin", stdin):
                    with contextlib.redirect_stdout(io.StringIO()) as out:
                        rc = self.overlay.overlay_check_command()
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(len(logged), 1, "a swallowed error still leaves a breadcrumb")

    def test_hook_script_never_execs_and_always_exits_zero(self) -> None:
        """Exit code 2 means BLOCK on both runtimes, and argparse exits 2 on
        any usage error — so an `exec` here would let a flag typo erase a
        prompt or interrupt a tool call."""
        script = REPO_ROOT / "hooks" / "flow-overlay-reminder.sh"

        # A stub `flow` that exits 2, which is what argparse does on any usage
        # error. Pointing PATH at nowhere instead — as the first version of
        # this test did — leaves $FLOW empty, so the `if` body never runs and
        # `exit 0` is reached no matter what the body says. Verified: an `exec`
        # inserted into the script passed that version.
        fake_bin = self.dir / "fakebin"
        fake_bin.mkdir()
        (fake_bin / "flow").write_text("#!/bin/sh\nexit 2\n")
        (fake_bin / "flow").chmod(0o755)

        proc = subprocess.run(
            ["/bin/bash", str(script)],
            input="",
            capture_output=True,
            text=True,
            env={"PATH": f"{fake_bin}:/usr/bin:/bin", "HOME": str(self.dir)},
        )
        self.assertEqual(
            proc.returncode, 0, "argparse's exit 2 must not reach the runtime as a block"
        )

        # And with no resolvable flow at all.
        missing = subprocess.run(
            ["/bin/bash", str(script)],
            input="",
            capture_output=True,
            text=True,
            env={"PATH": "/nonexistent", "HOME": "/nonexistent"},
        )
        self.assertEqual(missing.returncode, 0, "a missing flow must not block the runtime")
        self.assertEqual(missing.stdout, "")

    def test_marker_filename_carries_no_account_name(self) -> None:
        """Marker paths are derived from a hash of the repo root. Nothing this
        framework writes should spell out whose machine it is."""
        marker = self.overlay._marker_path("/Users/someone/dotfiles", "UserPromptSubmit")
        self.assertNotIn("someone", marker.name)
        self.assertNotIn("/", marker.name)


class SetupUserOverlayRepoTests(unittest.TestCase):
    """`flow setup user --overlay-repo` — the three cases, none of which may
    ever discard existing overlay content."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.dir = Path(self._tempdir.name)
        REPO_ROOT_CLI = REPO_ROOT / "cli"
        if str(REPO_ROOT_CLI) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT_CLI))
            self._added_cli_path = True
        else:
            self._added_cli_path = False

    def tearDown(self) -> None:
        self._tempdir.cleanup()
        if self._added_cli_path:
            sys.path.remove(str(REPO_ROOT / "cli"))
        for name in ("setup", "overlay", "paths", "sync"):
            sys.modules.pop(name, None)

    def _git(self, cwd: Path, *args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
                 "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e"},
        )

    def _seeded_remote(self) -> Path:
        """A bare repo with one commit, usable as a clone source."""
        work = self.dir / "seed"
        work.mkdir()
        (work / "flow.toml").write_text("# from remote\n")
        self._git(work, "init", "-b", "main")
        self._git(work, "add", ".")
        self._git(work, "commit", "-m", "seed")
        bare = self.dir / "remote.git"
        bare.mkdir()
        self._git(bare, "init", "--bare", "-b", "main")
        self._git(work, "remote", "add", "origin", str(bare))
        self._git(work, "push", "-u", "origin", "main")
        return bare

    def _attach(self, overlay_dir: Path, url: str):
        """Call _attach_overlay_repo with USER_OVERLAY_DIR pointed at a tmpdir."""
        import contextlib
        import io
        import unittest.mock

        import setup

        with unittest.mock.patch.object(setup, "USER_OVERLAY_DIR", overlay_dir):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                rc = setup._attach_overlay_repo(url)
        return rc, out.getvalue()

    def test_empty_overlay_clones_the_remote(self) -> None:
        remote = self._seeded_remote()
        overlay_dir = self.dir / "user"
        rc, out = self._attach(overlay_dir, str(remote))
        self.assertEqual(rc, 0)
        self.assertIn("cloned", out)
        self.assertEqual((overlay_dir / "flow.toml").read_text(), "# from remote\n")

    def test_existing_content_is_inited_in_place_never_clobbered(self) -> None:
        remote = self._seeded_remote()
        overlay_dir = self.dir / "user"
        overlay_dir.mkdir()
        (overlay_dir / "flow.toml").write_text("# MY LOCAL WORK\n")

        rc, out = self._attach(overlay_dir, str(remote))
        self.assertEqual(rc, 0)
        self.assertIn("initialized", out)
        self.assertEqual(
            (overlay_dir / "flow.toml").read_text(),
            "# MY LOCAL WORK\n",
            "local overlay content must survive attachment",
        )
        self.assertTrue((overlay_dir / ".git").exists())
        self.assertTrue((overlay_dir / ".gitignore").exists())

    def test_already_a_repo_is_left_alone(self) -> None:
        overlay_dir = self.dir / "user"
        overlay_dir.mkdir()
        (overlay_dir / "flow.toml").write_text("# existing\n")
        self._git(overlay_dir, "init", "-b", "main")
        self._git(overlay_dir, "add", ".")
        self._git(overlay_dir, "commit", "-m", "mine")
        self._git(overlay_dir, "remote", "add", "origin", "git@example.com:me/other.git")

        rc, out = self._attach(overlay_dir, "git@example.com:me/DIFFERENT.git")
        self.assertEqual(rc, 0)
        self.assertIn("already a git repo", out)
        self.assertIn("left as-is", out, "a differing remote must be reported, not silently changed")
        remotes = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=overlay_dir, capture_output=True, text=True,
        ).stdout.strip()
        self.assertEqual(remotes, "git@example.com:me/other.git")

    def test_clone_failure_writes_nothing_and_preserves_the_directory(self) -> None:
        overlay_dir = self.dir / "user"
        rc, out = self._attach(overlay_dir, str(self.dir / "does-not-exist.git"))
        self.assertEqual(rc, 1)
        self.assertIn("failed", out)
        self.assertFalse((overlay_dir / ".gitignore").exists(), "a failed clone must write nothing")
        self.assertFalse((overlay_dir / ".git").exists())

    def test_dotfile_only_overlay_still_takes_the_clone_path(self) -> None:
        """Review finding: a lone .DS_Store made a fresh machine look occupied,
        taking init-in-place and producing an unrelated history against a
        seeded remote.
        """
        remote = self._seeded_remote()
        overlay_dir = self.dir / "user"
        overlay_dir.mkdir()
        (overlay_dir / ".DS_Store").write_bytes(b"\x00")

        rc, out = self._attach(overlay_dir, str(remote))
        self.assertEqual(rc, 0)
        self.assertIn("cloned", out, ".DS_Store must not count as overlay content")
        self.assertEqual((overlay_dir / "flow.toml").read_text(), "# from remote\n")

    def test_repo_without_a_remote_gets_one_added(self) -> None:
        """A partial attach (init succeeded, remote add failed) previously left
        the overlay permanently stuck reporting no remote. Re-running now
        completes it.
        """
        overlay_dir = self.dir / "user"
        overlay_dir.mkdir()
        (overlay_dir / "flow.toml").write_text("# mine\n")
        self._git(overlay_dir, "init", "-b", "main")

        rc, out = self._attach(overlay_dir, "git@example.com:me/overlay.git")
        self.assertEqual(rc, 0)
        self.assertIn("added:", out)
        remote = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=overlay_dir, capture_output=True, text=True,
        ).stdout.strip()
        self.assertEqual(remote, "git@example.com:me/overlay.git")

    def test_credentials_in_a_url_are_not_echoed(self) -> None:
        import setup

        self.assertEqual(
            setup._scrub_url("https://me:ghp_secret@github.com/me/r.git"),
            "https://<credentials>@github.com/me/r.git",
        )
        self.assertEqual(setup._scrub_url("git@github.com:me/r.git"), "git@github.com:me/r.git")


if __name__ == "__main__":
    unittest.main()
