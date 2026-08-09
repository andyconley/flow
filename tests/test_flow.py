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
        hook_path = self.repo / ".claude" / "hooks" / "flow-session-start.sh"
        settings_path = self.repo / ".claude" / "settings.json"
        managed_path = self.repo / ".claude" / "flow.managed.toml"

        self.assertTrue(skill_path.exists())
        self.assertTrue(agent_path.exists())
        self.assertTrue(hook_path.exists())
        self.assertTrue(managed_path.exists())
        self.assertIn("disable-model-invocation: true", skill_path.read_text())

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
        managed_path = self.repo / ".codex" / "flow.managed.toml"

        self.assertTrue(skill_path.exists())
        self.assertTrue(managed_path.exists())
        self.assertFalse((self.repo / ".codex" / "agents").exists())
        content = skill_path.read_text()
        self.assertIn("Generated by flow.", content)
        self.assertTrue(content.startswith("---\nname: flow-plan\ndescription: "))

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
        self.assertIn("codex   Generate .agents skills and a .codex managed manifest.", result.stdout)
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
        managed_path = fake_home / ".codex" / "flow.managed.toml"

        self.assertTrue(skill_path.exists())
        self.assertTrue(managed_path.exists())
        self.assertFalse((fake_home / ".codex" / "agents").exists())

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
            "[[claude.agents]]\n"
            f'name = "{name}"\n'
            f'source = "agents/{name}.md"\n'
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
        # Import flow.py's parser directly so we cover the same code path the CLI uses.
        import importlib.util
        flow_module_path = REPO_ROOT / "cli" / "flow.py"
        spec = importlib.util.spec_from_file_location("flow_cli", flow_module_path)
        flow_cli = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        assert spec and spec.loader
        spec.loader.exec_module(flow_cli)  # type: ignore[union-attr]
        data = flow_cli.read_toml(REPO_ROOT / "scaffolds" / "default" / "flow.toml")
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

    def test_release_staging_requires_cli_siblings(self) -> None:
        """A release shipping the launcher without its siblings installs then breaks."""
        import importlib.util

        # lifecycle.py imports its siblings by bare name, which only resolves
        # when cli/ is on sys.path. flow.py arranges that for itself at import
        # time; loading a sibling directly does not, so the test arranges it.
        sys.path.insert(0, str(REPO_ROOT / "cli"))
        try:
            spec = importlib.util.spec_from_file_location(
                "flow_cli_staging", REPO_ROOT / "cli" / "lifecycle.py"
            )
            flow_cli = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            assert spec and spec.loader
            spec.loader.exec_module(flow_cli)  # type: ignore[union-attr]
        finally:
            sys.path.remove(str(REPO_ROOT / "cli"))

        staging = self.repo / "staging"
        (staging / "cli").mkdir(parents=True)
        (staging / "cli" / "flow.py").write_text("# entrypoint")
        (staging / "scaffolds" / "default").mkdir(parents=True)
        (staging / "scaffolds" / "default" / "flow.toml").write_text("")
        (staging / "data").mkdir(parents=True)
        (staging / "data" / "harness_capabilities.json").write_text(
            '{"capabilities": []}'
        )

        reason = flow_cli._validate_staging(staging)
        self.assertIsNotNone(reason, "staging without cli siblings must be rejected")
        self.assertIn("usage_store.py", reason)

        (staging / "cli" / "usage_store.py").write_text("# sibling")
        self.assertIsNone(
            flow_cli._validate_staging(staging),
            "staging with all required files should validate",
        )


if __name__ == "__main__":
    unittest.main()
