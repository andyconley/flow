import hashlib
import json
import os
import re
import stat
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FLOW_CLI = REPO_ROOT / "cli" / "flow.py"


def load_cli_module(name: str):
    """Import a cli/ module directly, leaving sys.path and sys.modules as found.

    cli/ modules import each other by bare name, which only resolves with cli/
    on sys.path. flow.py arranges that for itself at import time; a direct load
    does not, so this does it — and then puts everything back.

    Restoring sys.modules matters as much as sys.path. Loading these binds
    generic top-level names (`paths`, `setup`, `sync`, `render`) in the test
    process, where they would shadow any same-named module a later import
    wanted.
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


class FlowCliHarness(unittest.TestCase):
    """Temp repo, subprocess runner, and fake HOME — the parts every CLI test
    needs and none of the assertions.

    Extracted from `FlowCliTests` because a class that carried both meant any
    test class wanting `run_flow` had to inherit a hundred unrelated tests and
    re-run them. That had already happened twice, and the workaround each time
    was to give up the helpers and reimplement them.
    """

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

    def run_flow_with_input(self, stdin: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(FLOW_CLI), *args],
            cwd=self.repo,
            text=True,
            input=stdin,
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

    def setup_legacy_project(self) -> None:
        """A project overlay as `flow setup project` built them before thinning.

        `setup project` now creates four files. Every test of `flow project
        audit` and `flow project migrate` needs the opposite: a repo carrying
        a full copy of the framework scaffold, because that is the only kind
        of project those two commands have anything to say about. Building it
        here rather than in each test keeps the fixture honest about what it
        is — a legacy overlay, not the current contract — and means the
        thinning does not have to be re-litigated in thirty fixtures.
        """
        self.setup_project()
        flow_dir = self.repo / ".flow"
        scaffold = REPO_ROOT / "scaffolds" / "default"
        for src in scaffold.rglob("*"):
            if not src.is_file():
                continue
            rel = src.relative_to(scaffold)
            if rel == Path("flow.toml"):
                # The scaffold's manifest is the framework's sync
                # configuration. Old `setup project` really did copy it, and
                # the migrate tests depend on a project manifest that declares
                # sources, so it is copied here too — but as the legacy
                # artifact it is, not as something a new project would get.
                # Bytes, not text: `classify_tree` compares raw bytes, so a
                # decode/encode round-trip here could bucket a file as
                # `differs` for an encoding reason rather than a real one.
                (flow_dir / rel).write_bytes(src.read_bytes())
                continue
            dest = flow_dir / rel
            if dest.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())

    def writable_scaffold(self, fake_home: Path) -> Path:
        """Give this fake HOME its own editable copy of the framework scaffold.

        `use_fake_home` points ~/.flow/source straight at the checkout, so a
        test that needs to change the scaffold manifest would be editing the
        repo it is running from. Only `scaffolds/` is copied; everything else
        (hooks/, cli/) stays a link, so hook scripts still resolve.
        """
        source = fake_home / ".flow" / "source"
        if source.is_symlink():
            source.unlink()
        source.mkdir(parents=True, exist_ok=True)
        for entry in REPO_ROOT.iterdir():
            if entry.name.startswith(".") or entry.name == "scaffolds":
                continue
            (source / entry.name).symlink_to(entry)
        shutil.copytree(REPO_ROOT / "scaffolds", source / "scaffolds")
        return source / "scaffolds" / "default"

    def use_fake_home(self) -> Path:
        """Create a fake HOME with a flow source symlink. Subsequent run_flow calls use this HOME."""
        fake_home = self.repo / "fake_home"
        fake_home.mkdir()
        (fake_home / ".flow").mkdir()
        (fake_home / ".flow" / "source").symlink_to(REPO_ROOT)
        self._fake_home = fake_home
        return fake_home


class FlowCliTests(FlowCliHarness):
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

    def test_setup_project_creates_exactly_four_paths(self) -> None:
        """The whole contract of the thinned scaffold, as a set equality.

        Deliberately not four `assertTrue`s: those pass just as happily when a
        fifth file appears, and a fifth file is precisely the regression this
        slice exists to prevent.
        """
        self.setup_project()
        flow_dir = self.repo / ".flow"

        created = {
            p.relative_to(flow_dir).as_posix()
            for p in flow_dir.rglob("*")
            if p.is_file()
        }

        self.assertEqual(
            created,
            {"flow.toml", "PROJECT.md", "memory/STATE.md", "runs/.gitkeep"},
        )

    def test_setup_project_creates_no_framework_md(self) -> None:
        """Stated directly rather than inferred from the set above.

        A project holding its own FRAMEWORK.md is the fork in miniature: it
        goes stale the first time the framework's changes, and nothing reads
        it. Both surveyed real overlays carried one, both already drifted.
        """
        self.setup_project()

        self.assertFalse((self.repo / ".flow" / "FRAMEWORK.md").exists())

    def test_setup_project_manifest_round_trips_through_flowtoml(self) -> None:
        self.setup_project()
        flowtoml = load_cli_module("flowtoml")

        data = flowtoml.read_toml(self.repo / ".flow" / "flow.toml")

        self.assertEqual(data["framework"]["name"], "flow")
        self.assertEqual(data["framework"]["version"], 1)

    def test_setup_project_manifest_is_not_the_framework_manifest(self) -> None:
        """The two documents named `flow.toml` must not open identically.

        Asserting the template's own literal values proves nothing — they were
        copied from the template. What is worth pinning is the difference: a
        project manifest that opened exactly like the framework's would read
        as that file truncated, which is the confusion splitting them was
        meant to end.
        """
        self.setup_project()
        flowtoml = load_cli_module("flowtoml")

        project = flowtoml.read_toml(self.repo / ".flow" / "flow.toml")
        framework = flowtoml.read_toml(REPO_ROOT / "scaffolds" / "default" / "flow.toml")

        self.assertNotEqual(project["framework"], framework["framework"])
        self.assertEqual(project["framework"]["kind"], "project")
        self.assertNotIn("kind", framework["framework"])
        # The framework's sync configuration has no business in a project.
        for table in ("claude", "codex", "agents", "standards"):
            self.assertNotIn(table, project)

    def test_setup_project_manifest_ships_replaces_commented_out(self) -> None:
        """The example must be inert, not merely present.

        `assertIn("[[replaces]]", text)` would pass with a live block, and a
        live block means every new project starts by declaring a replacement
        for a standard it does not have.
        """
        self.setup_project()
        manifest = self.repo / ".flow" / "flow.toml"
        flowtoml = load_cli_module("flowtoml")

        text = manifest.read_text()

        self.assertRegex(text, r"(?m)^\s*#.*\[\[replaces\]\]")
        self.assertNotIn("replaces", flowtoml.read_toml(manifest))

    def test_run_transition_refuses_invalid_gate_without_writing(self) -> None:
        self.setup_project()
        self.assert_ok(self.run_flow("run", "transition", "demo", "start-definition"))
        run_path = self.repo / ".flow" / "runs" / "demo" / "run.json"
        events_path = self.repo / ".flow" / "runs" / "demo" / "events.jsonl"
        before_run = run_path.read_text()
        before_events = events_path.read_text()

        result = self.run_flow("run", "transition", "demo", "start-plan")

        self.assertEqual(result.returncode, 1)
        self.assertIn("transition refused", result.stdout)
        self.assertIn("requires definition_approved", result.stdout)
        self.assertEqual(run_path.read_text(), before_run)
        self.assertEqual(events_path.read_text(), before_events)

    def test_run_core_path_transitions_to_archive(self) -> None:
        self.setup_project()
        commands = (
            ("start-definition", ()),
            (
                "approve-definition",
                (
                    "--artifact",
                    "requirements=.flow/runs/demo/requirements.md",
                    "--artifact",
                    "acceptance_criteria=.flow/runs/demo/acceptance.md",
                ),
            ),
            ("start-solution", ()),
            (
                "approve-solution",
                (
                    "--artifact",
                    "solution=.flow/runs/demo/solution.md",
                    "--disposition",
                    "risk=owned",
                ),
            ),
            ("start-plan", ()),
            (
                "approve-plan",
                (
                    "--artifact",
                    "plan=.flow/runs/demo/plan.md",
                    "--artifact",
                    "handoff=.flow/runs/demo/handoff.md",
                    "--artifact",
                    "validation_plan=.flow/runs/demo/validation.md",
                ),
            ),
            ("start-implementation", ()),
            (
                "mark-handback-ready",
                (
                    "--artifact",
                    "implementation_evidence=.flow/runs/demo/validation-results.md",
                    "--artifact",
                    "handback=.flow/runs/demo/HANDOFF.md",
                ),
            ),
            ("start-review", ()),
            (
                "accept-review",
                ("--artifact", "review=.flow/runs/demo/review.md"),
            ),
            (
                "archive",
                (
                    "--disposition",
                    "capability_gaps=n/a",
                    "--disposition",
                    "memory=n/a",
                ),
            ),
        )
        for event, extra in commands:
            with self.subTest(event=event):
                self.assert_ok(self.run_flow("run", "transition", "demo", event, *extra))

        status = self.run_flow("run", "status", "demo", "--json")
        self.assert_ok(status)
        payload = json.loads(status.stdout)
        self.assertEqual(payload["state"], "archived")
        self.assertEqual(payload["dispositions"]["capability_gaps"], "n/a")
        history = self.run_flow("run", "history", "demo", "--json")
        self.assert_ok(history)
        self.assertEqual(len(json.loads(history.stdout)["events"]), len(commands))
        self.assert_ok(self.run_flow("run", "verify", "demo"))

    def test_run_legacy_status_is_read_only_and_inferred(self) -> None:
        self.setup_project()
        legacy_dir = self.repo / ".flow" / "runs" / "old-work"
        legacy_dir.mkdir()
        (legacy_dir / "PLAN.md").write_text("legacy plan\n")

        status = self.run_flow("run", "status", "old-work", "--json")

        self.assert_ok(status)
        payload = json.loads(status.stdout)
        self.assertEqual(payload["state"], "legacy/inferred")
        self.assertFalse((legacy_dir / "run.json").exists())
        verify = self.run_flow("run", "verify", "old-work")
        self.assert_ok(verify)
        self.assertIn("legacy/inferred", verify.stdout)

    def test_run_scout_archive_creates_minimal_envelope(self) -> None:
        self.setup_project()

        result = self.run_flow(
            "run",
            "transition",
            "scout-fix",
            "archive-scout",
            "--artifact",
            "scout_summary=.flow/runs/scout-fix/scout-summary.md",
            "--disposition",
            "capability_gaps=n/a",
            "--disposition",
            "memory=n/a",
        )

        self.assert_ok(result)
        status = self.run_flow("run", "status", "scout-fix", "--json")
        self.assert_ok(status)
        payload = json.loads(status.stdout)
        self.assertEqual(payload["state"], "archived")
        self.assertEqual(payload["lane"], "scout")

    def test_run_pause_and_resume_returns_to_prior_state(self) -> None:
        self.setup_project()
        self.assert_ok(self.run_flow("run", "transition", "demo", "start-definition"))
        self.assert_ok(self.run_flow("run", "transition", "demo", "pause", "--note", "waiting"))

        paused = json.loads(self.run_flow("run", "status", "demo", "--json").stdout)
        self.assertEqual(paused["state"], "paused")
        self.assertEqual(paused["return_state"], "defining")
        self.assertEqual(paused["return_lane"], "define")
        self.assertEqual(paused["next_action"], "waiting")

        self.assert_ok(self.run_flow("run", "transition", "demo", "resume"))
        resumed = json.loads(self.run_flow("run", "status", "demo", "--json").stdout)
        self.assertEqual(resumed["state"], "defining")
        self.assertEqual(resumed["lane"], "define")
        self.assertNotIn("return_state", resumed)
        self.assertNotIn("return_lane", resumed)
        self.assertNotIn("next_action", resumed)

    def test_lifecycle_commands_reference_c_lite_run_protocol(self) -> None:
        command_dir = REPO_ROOT / "scaffolds" / "default" / "commands"
        expected = {
            "flow-define.md": "flow run transition <work-id> start-definition",
            "flow-solution.md": "flow run transition <work-id> start-solution",
            "flow-plan.md": "flow run transition <work-id> start-plan",
            "flow-implement.md": "flow run transition <work-id> start-implementation",
            "flow-review.md": "flow run transition <work-id> start-review",
            "flow-archive.md": "flow run transition <work-id> archive",
            "flow-scout.md": "flow run transition <work-id> archive-scout",
            "flow-status.md": "flow run list",
            "flow-resume.md": "flow run verify",
        }
        for name, needle in expected.items():
            with self.subTest(command=name):
                self.assertIn(needle, (command_dir / name).read_text())

    def test_shared_commands_use_runtime_memory_provider_language(self) -> None:
        command_dir = REPO_ROOT / "scaffolds" / "default" / "commands"
        for name in ("flow-boot.md", "flow-status.md", "flow-resume.md", "flow-archive.md"):
            with self.subTest(command=name):
                text = (command_dir / name).read_text()
                self.assertIn("runtime memory provider", text)
                self.assertNotIn("Claude Code auto-memory at `~/.claude/projects/<project-id>/memory/` —", text)

    def test_project_scaffold_uses_runtime_memory_provider_language(self) -> None:
        scaffold_dir = REPO_ROOT / "scaffolds" / "default"
        for path in (scaffold_dir / "PROJECT.md", scaffold_dir / "memory" / "STATE.md"):
            with self.subTest(path=path.relative_to(scaffold_dir).as_posix()):
                text = path.read_text()
                self.assertIn("runtime memory provider", text)
                self.assertIn("Codex currently has no Flow-managed durable", text)
                self.assertNotIn("those go to Claude Code's auto-memory", text)
                self.assertNotIn("write to auto-memory", text)

    # -- `flow refresh project`, retired -------------------------------
    #
    # Seven tests here previously asserted that refresh repaired an overlay:
    # restored a deleted manifest, backfilled registered sources, reported
    # changed files, and updated them interactively. None could be adjusted to
    # pass, because each claimed the command does work it must no longer do.
    # They are replaced rather than relaxed — the behaviour under test is
    # different behaviour, so the names change with it.

    def _retired(self, *extra: str):
        return self.run_flow("refresh", "project", *extra)

    def test_refresh_project_is_retired(self) -> None:
        flow_dir = self.repo / ".flow"
        flow_dir.mkdir()
        (flow_dir / "flow.toml").write_text('[framework]\nname = "flow"\nversion = 1\n')

        result = self._retired()

        self.assertEqual(result.returncode, 1)
        self.assertIn("was retired", result.stdout)

    def test_the_retirement_names_where_each_job_went(self) -> None:
        """A refusal that does not say what to run instead just moves the
        problem to whoever hit it."""
        (self.repo / ".flow").mkdir()

        out = self._retired().stdout

        self.assertIn("flow setup project", out)
        self.assertIn("flow project migrate", out)

    def test_the_retirement_admits_the_one_capability_with_no_successor(self) -> None:
        """Updating an existing core file from the framework template has no
        replacement. Saying so beats letting it be discovered."""
        (self.repo / ".flow").mkdir()

        out = self._retired().stdout

        self.assertIn("no replacement", out)

    def test_refresh_project_touches_nothing(self) -> None:
        """Exit 1 alone would pass if the old repair ran before the early
        return, which is exactly the shape this replaced."""
        flow_dir = self.repo / ".flow"
        flow_dir.mkdir()
        (flow_dir / "flow.toml").write_text('[framework]\nname = "flow"\nversion = 1\n')
        before = {
            p.relative_to(self.repo): p.read_bytes()
            for p in self.repo.rglob("*")
            if p.is_file() and ".git" not in p.parts
        }

        self.assertEqual(self._retired().returncode, 1)

        after = {
            p.relative_to(self.repo): p.read_bytes()
            for p in self.repo.rglob("*")
            if p.is_file() and ".git" not in p.parts
        }
        self.assertEqual(before, after)

    def test_refresh_project_is_retired_without_a_flow_dir_too(self) -> None:
        """The older missing-overlay guard used to run first. It no longer
        does, deliberately: someone typing a retired command needs to hear
        that it is retired, not a setup error about a directory the command
        would not have touched.
        """
        result = self._retired()

        self.assertEqual(result.returncode, 1)
        self.assertIn("was retired", result.stdout)
        self.assertNotIn("repo is missing .flow", result.stdout)

    def test_refresh_project_interactive_is_retired_too(self) -> None:
        (self.repo / ".flow").mkdir()

        result = self._retired("--interactive")

        self.assertEqual(result.returncode, 1)
        self.assertIn("was retired", result.stdout)

    def test_refresh_project_all_is_retired(self) -> None:
        (self.repo / ".flow").mkdir()

        result = self._retired("--all")

        self.assertEqual(result.returncode, 1)
        self.assertIn("was retired", result.stdout)

    def test_refresh_project_all_creates_nothing(self) -> None:
        """The point of the retirement is the absence of the copies, not the
        return code."""
        flow_dir = self.repo / ".flow"
        flow_dir.mkdir()
        (flow_dir / "flow.toml").write_text('[framework]\nname = "flow"\nversion = 1\n')

        before = {p.relative_to(flow_dir): p.read_bytes() for p in flow_dir.rglob("*") if p.is_file()}
        self.assertEqual(self._retired("--all").returncode, 1)
        after = {p.relative_to(flow_dir): p.read_bytes() for p in flow_dir.rglob("*") if p.is_file()}

        self.assertEqual(before, after)

    def test_sync_claude_generates_the_full_runtime_surface(self) -> None:
        fake_home = self.use_fake_home()

        self.assert_ok(self.run_flow("sync", "claude", "--user"))

        skill_path = fake_home / ".claude" / "skills" / "flow-plan" / "SKILL.md"
        define_skill_path = fake_home / ".claude" / "skills" / "flow-define" / "SKILL.md"
        agent_path = fake_home / ".claude" / "agents" / "architect.md"
        tech_writer_path = fake_home / ".claude" / "agents" / "tech-writer.md"
        hook_path = fake_home / ".claude" / "hooks" / "flow-session-start.sh"
        settings_path = fake_home / ".claude" / "settings.json"
        managed_path = fake_home / ".claude" / "flow.managed.toml"

        self.assertTrue(skill_path.exists())
        self.assertTrue(define_skill_path.exists())
        self.assertTrue(agent_path.exists())
        self.assertTrue(tech_writer_path.exists())
        self.assertTrue(hook_path.exists())
        self.assertTrue(managed_path.exists())
        self.assertIn("disable-model-invocation: true", skill_path.read_text())
        self.assertIn("research and evidence", define_skill_path.read_text())
        self.assertIn("Flow Agent Routing", skill_path.read_text())
        self.assertIn("effort: medium", agent_path.read_text())
        self.assertIn("model: haiku", tech_writer_path.read_text())
        self.assertIn("effort: low", tech_writer_path.read_text())

        settings = json.loads(settings_path.read_text())
        session_groups = settings["hooks"]["SessionStart"]
        self.assertTrue(
            any(
                group["hooks"][0]["command"] == '"$HOME"/.claude/hooks/flow-session-start.sh'
                for group in session_groups
            )
        )

    def test_sync_codex_generates_skill_runtime(self) -> None:
        fake_home = self.use_fake_home()

        self.assert_ok(self.run_flow("sync", "codex", "--user"))

        skill_path = fake_home / ".agents" / "skills" / "flow-plan" / "SKILL.md"
        define_skill_path = fake_home / ".agents" / "skills" / "flow-define" / "SKILL.md"
        agent_path = fake_home / ".codex" / "agents" / "architect.toml"
        managed_path = fake_home / ".codex" / "flow.managed.toml"

        self.assertTrue(skill_path.exists())
        self.assertTrue(define_skill_path.exists())
        self.assertTrue(agent_path.exists())
        self.assertTrue(managed_path.exists())
        content = skill_path.read_text()
        define_content = define_skill_path.read_text()
        self.assertIn("Generated by flow.", content)
        self.assertIn("research and evidence", define_content)
        self.assertIn("Flow Agent Routing", content)
        self.assertTrue(content.startswith("---\nname: flow-plan\ndescription: "))
        agent_content = agent_path.read_text()
        self.assertIn('model = "gpt-5.6-sol"', agent_content)
        self.assertIn('model_reasoning_effort = "medium"', agent_content)
        tech_writer_content = (fake_home / ".codex" / "agents" / "tech-writer.toml").read_text()
        self.assertIn('model = "gpt-5.6-luna"', tech_writer_content)
        self.assertIn('model_reasoning_effort = "low"', tech_writer_content)

    def test_runtime_smoke_checks_generated_surfaces(self) -> None:
        fake_home = self.use_fake_home()
        self.assert_ok(self.run_flow("sync", "claude", "--user"))
        self.assert_ok(self.run_flow("sync", "codex", "--user"))

        result = self.run_flow("runtime", "smoke", "--target", "all", "--json")

        self.assert_ok(result)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["failed"], 0)
        self.assertEqual(payload["manual_required"], 4)
        targets = {item["target"]: item for item in payload["targets"]}
        claude_static = targets["claude"]["static"]
        codex_static = targets["codex"]["static"]
        self.assertTrue(any(row["name"] == "command flow-plan C-lite protocol" for row in claude_static))
        self.assertTrue(any(row["name"] == "agent support-lead" for row in codex_static))
        self.assertIn("manual_required", {row["status"] for row in targets["codex"]["manual"]})

        text = self.run_flow("runtime", "smoke", "--target", "codex").stdout
        self.assertIn("manual_required: role agent invocation", text)
        self.assertIn("summary: failed=0 manual_required=2", text)

    def test_runtime_smoke_fails_on_missing_agent_policy(self) -> None:
        fake_home = self.use_fake_home()
        self.assert_ok(self.run_flow("sync", "codex", "--user"))
        agent_path = fake_home / ".codex" / "agents" / "support-lead.toml"
        agent_path.write_text(agent_path.read_text().replace('model_reasoning_effort = "low"\n', ""))

        result = self.run_flow("runtime", "smoke", "--target", "codex", "--json")

        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        failures = [
            row
            for target in payload["targets"]
            for row in target["static"]
            if row["status"] == "failed"
        ]
        self.assertTrue(any(row["name"] == "agent support-lead" for row in failures))

    def test_sync_check_detects_codex_drift(self) -> None:
        fake_home = self.use_fake_home()
        self.assert_ok(self.run_flow("sync", "codex", "--user"))

        skill_path = fake_home / ".agents" / "skills" / "flow-plan" / "SKILL.md"
        skill_path.write_text(skill_path.read_text() + "\nmanual drift\n")

        result = self.run_flow("sync", "codex", "--user", "--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("codex sync check: drift detected", result.stdout)

    def test_sync_without_user_is_refused(self) -> None:
        """Project-level sync was retired. Exiting 1 rather than 0 matters: a
        pointer printed alongside success is indistinguishable from having
        synced, and any caller checking the exit code would carry on believing
        its adapters were current."""
        self.use_fake_home()
        self.setup_project()
        for target in ("claude", "codex"):
            result = self.run_flow("sync", target)
            self.assertEqual(result.returncode, 1)
            self.assertIn("project-level sync was retired", result.stdout)
            self.assertIn(f"flow sync {target} --user", result.stdout)
        self.assertFalse((self.repo / ".claude").exists(), "nothing may be generated")

    def test_doctor_reports_both_runtime_states(self) -> None:
        """Doctor still reports two sections, but only the user-level one
        carries runtime state now. Project-level sync was retired, so the
        project section no longer has claude/codex sync, drift, skills,
        agents, or agent-policy lines — it reports the repo overlay only.
        Asserting the old project drift lines here would pin behavior that
        no longer exists; asserting `overlay:` pins what replaced it.
        """
        fake_home = self.use_fake_home()
        self.setup_project()
        self.assert_ok(self.run_flow("sync", "claude", "--user"))
        self.assert_ok(self.run_flow("sync", "codex", "--user"))
        self.assertTrue((fake_home / ".claude" / "flow.managed.toml").exists())

        result = self.run_flow("doctor")
        self.assert_ok(result)
        self.assertIn("claude drift:     clean", result.stdout)
        self.assertIn("codex drift:      clean", result.stdout)
        self.assertIn("agent policy:     ok (13/13 configured)", result.stdout)
        self.assertIn("codex agents:     ok (13/13 configured)", result.stdout)
        self.assertIn("claude smoke:     static ok; 2 manual check(s) required", result.stdout)
        self.assertIn("codex smoke:      static ok; 2 manual check(s) required", result.stdout)
        self.assertIn("flow runtime smoke --target claude", result.stdout)
        self.assertIn("-- user-level", result.stdout)
        self.assertIn("-- project:", result.stdout)

        project_section = result.stdout.split("-- project:", 1)[1]
        self.assertIn("overlay:", project_section)

    def test_top_level_help_lists_core_commands_and_examples(self) -> None:
        result = self.run_flow("--help")
        self.assert_ok(result)
        self.assertIn("Portable AI workflow framework CLI.", result.stdout)
        self.assertIn(
            "sync                generate runtime adapters from the framework scaffold", result.stdout
        )
        self.assertIn("flow sync codex --user --check", result.stdout)
        self.assertIn("flow runtime smoke --target all", result.stdout)
        self.assertIn("flow project audit", result.stdout)
        # The top-level examples advertised `flow sync claude` and
        # `flow sync codex --check` after those forms had started exiting 1.
        # Help that recommends a command which fails is worse than no help.
        self.assertNotIn("flow sync claude\n", result.stdout)

    def test_sync_help_describes_targets_and_examples(self) -> None:
        result = self.run_flow("sync", "--help")
        self.assert_ok(result)
        self.assertIn("Generate runtime-facing adapters", result.stdout)
        self.assertIn("--user", result.stdout)
        self.assertIn("claude  Generate .claude skills, agents, hooks, settings, and a managed manifest.", result.stdout)
        self.assertIn("codex   Generate .agents skills, .codex agents, hooks, hooks.json, and a managed manifest.", result.stdout)
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

    def test_skill_edit_hint_matches_origin(self) -> None:
        """The generated marker must direct edits to a file that actually
        exists, and which file that is depends on the command's origin. A
        user-overlay command's source lives under `~/.flow/user/`; a
        framework command's lives in the scaffold at
        `~/.flow/source/scaffolds/default/`. Neither is `.flow/`, which is
        what the hint used to say and which does not exist anywhere near
        `~/.claude/skills/`. Both cases are asserted below. There used to be
        a third — a framework command synced in project mode, which did get
        the classic `.flow/<source>` hint — and it went away with
        project-level sync.
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
        fake_home = self.use_fake_home()
        flow_toml = self.writable_scaffold(fake_home) / "flow.toml"
        hooks_json = fake_home / ".codex" / "hooks.json"
        hooks_json.parent.mkdir(parents=True, exist_ok=True)
        hooks_json.write_text(
            json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "user-owned.sh"}]}]}})
        )

        self.assert_ok(self.run_flow("sync", "codex", "--user"))
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

        self.assert_ok(self.run_flow("sync", "codex", "--user"))
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
        fake_home = self.use_fake_home()
        manifest = self.writable_scaffold(fake_home) / "flow.toml"
        manifest_text = manifest.read_text().replace(
            '[codex]\nskill_dir = ".agents/skills"',
            '[codex]\nskill_dir = ".codex/skills"',
        )
        manifest.write_text(manifest_text)
        self.assertIn('skill_dir = ".codex/skills"', manifest.read_text())

        legacy_skill = fake_home / ".codex" / "skills" / "flow-plan" / "SKILL.md"
        legacy_skill.parent.mkdir(parents=True)
        legacy_skill.write_text("<!-- Generated by flow. -->\nlegacy\n")
        managed = fake_home / ".codex" / "flow.managed.toml"
        managed.parent.mkdir(parents=True, exist_ok=True)
        managed.write_text(
            '[managed]\n'
            'generator = "flow"\n'
            'version = 2\n'
            'target = "codex"\n'
            'source_manifest = "~/.flow/source/scaffolds/default/flow.toml"\n'
            'preserve_unmanaged = true\n\n'
            '[[files]]\n'
            'path = ".codex/skills/flow-plan/SKILL.md"\n'
            'kind = "skill"\n'
            'source = "~/.flow/source/scaffolds/default/commands/flow-plan.md"\n'
            'sync_mode = "replace"\n'
            '\n[[files]]\n'
            'path = ".codex/flow.managed.toml"\n'
            'kind = "managed-manifest"\n'
            'source = "~/.flow/source/scaffolds/default/flow.toml"\n'
            'sync_mode = "replace"\n'
        )

        self.assert_ok(self.run_flow("sync", "codex", "--user"))

        current_skill = fake_home / ".agents" / "skills" / "flow-plan" / "SKILL.md"
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

    def test_doctor_reports_codex_only_user_overlay_command(self) -> None:
        fake_home = self.use_fake_home()
        overlay_dir = fake_home / ".flow" / "user"
        (overlay_dir / "commands").mkdir(parents=True)
        (overlay_dir / "commands" / "flow-codex-personal.md").write_text("# codex personal\n")
        (overlay_dir / "flow.toml").write_text(
            "\n"
            "[[codex.commands]]\n"
            'name = "flow-codex-personal"\n'
            'source = "commands/flow-codex-personal.md"\n'
            'description = "codex personal command"\n'
            'summary = "codex personal summary"\n'
        )

        result = self.run_flow("doctor")
        self.assert_ok(result)
        self.assertIn("user overlay:", result.stdout)
        self.assertIn("flow-codex-personal", result.stdout)

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

    def test_definition_research_standard_names_role_focuses(self) -> None:
        """flow-define research stays role-owned rather than becoming generic browsing."""
        standard = REPO_ROOT / "scaffolds" / "default" / "standards" / "research-evidence.md"
        text = standard.read_text()
        for role in (
            "product-manager",
            "business-analyst",
            "solution-architect",
            "sre",
            "support-lead",
            "test-engineer",
            "security-reviewer",
            "data-engineer",
            "ux-specialist",
        ):
            self.assertIn(f"`{role}`", text)
        self.assertIn("Requirement impact", text)
        self.assertIn("templates/research-note.md", text)

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
            conn.execute("DROP TABLE plugin_usage_observation")
            conn.execute("DROP TABLE plugin_usage_scan")
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
        """Delegate to the module-level loader.

        Kept as a method because call sites throughout this class use it that
        way; the body moved out so classes that do not subclass this one can
        load cli/ modules without inheriting its whole suite.
        """
        return load_cli_module(name)

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
                "baseline",
                "claude_collector",
                "claude_config",
                "codex_collector",
                "cost",
                "diagnostics",
                "flowtoml",
                "fsutil",
                "gaps",
                "harvest",
                "hookio",
                "jsonl_watermark",
                "lifecycle",
                "migrate",
                "normalize",
                "overlay",
                "paths",
                "plugin_usage",
                "project",
                "render",
                "runstate",
                "runtime_smoke",
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

    def _seed_claude_transcript(self, outputs: tuple[int, ...] = (4, 4, 487)) -> Path:
        home = self.use_fake_home()
        sessions_dir = home / ".claude" / "projects" / "-tmp-proj"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "sess-1.jsonl").write_text(
            _jsonl(
                _claude_user("sess-1"),
                *[_claude_assistant("sess-1", "req-1", output_tokens=o) for o in outputs],
                _claude_compact("sess-1", "manual"),
            )
        )
        return home

    def test_rescan_dry_run_reports_scope_and_writes_nothing(self) -> None:
        home = self._seed_claude_transcript()
        self.assert_ok(self.run_flow("harvest", "claude"))

        import sqlite3

        store = self._store_path(home)
        conn = sqlite3.connect(store)
        before = conn.execute("SELECT source_path, last_offset FROM harvest").fetchall()
        conn.close()

        conn = sqlite3.connect(store)
        schema_before = conn.execute("PRAGMA user_version").fetchone()[0]
        conn.execute("PRAGMA user_version = 4")  # simulate a store one migration behind
        conn.commit()
        conn.close()

        result = self.run_flow("harvest", "claude", "--rescan", "--dry-run")
        self.assert_ok(result)
        self.assertIn("would rewind 1 files", result.stdout)
        self.assertIn("nothing written", result.stdout)

        conn = sqlite3.connect(store)
        self.assertEqual(
            conn.execute("SELECT source_path, last_offset FROM harvest").fetchall(),
            before,
            "a dry run must not move any watermark",
        )
        # A schema migration is a write. `ensure_store` runs before every
        # other command here on purpose; a rehearsal must return before it.
        self.assertEqual(
            conn.execute("PRAGMA user_version").fetchone()[0],
            4,
            "a dry run must not apply pending migrations",
        )
        conn.close()
        self.assertGreater(schema_before, 4, "guard: the store was ahead of v4 to begin with")

    def test_dry_run_on_an_absent_store_says_so(self) -> None:
        self.use_fake_home()
        result = self.run_flow("harvest", "claude", "--rescan", "--dry-run")
        self.assert_ok(result)
        self.assertIn("no usage store", result.stdout)

    def test_narrowing_flags_without_rescan_are_refused(self) -> None:
        """Silently ignoring them would run a plain incremental harvest while
        the caller believed they had scoped something — and for `--dry-run`
        that means a rehearsal that writes."""
        self.use_fake_home()
        for flag in (["--dry-run"], ["--since", "2026-08-01"], ["--session", "abc"]):
            with self.subTest(flag=flag[0]):
                result = self.run_flow("harvest", "claude", *flag)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("require --rescan", result.stderr)

    def test_backfill_is_a_working_hidden_alias_for_rescan(self) -> None:
        self._seed_claude_transcript()
        self.assert_ok(self.run_flow("harvest", "claude"))
        result = self.run_flow("harvest", "claude", "--backfill")
        self.assert_ok(result)
        self.assertNotIn("--backfill", self.run_flow("harvest", "claude", "--help").stdout)

    def test_cost_trend_end_to_end_via_cli(self) -> None:
        self._seed_claude_transcript()
        self.assert_ok(self.run_flow("harvest", "claude"))
        self.assert_ok(self.run_flow("normalize"))

        table = self.run_flow("cost", "trend", "--all")
        self.assert_ok(table)
        self.assertIn("BUCKET", table.stdout)
        self.assertIn("WT/1K OUT", table.stdout)
        self.assertIn("CMPCT MAN", table.stdout)

        weekly = self.run_flow("cost", "trend", "--all", "--bucket", "week", "--json")
        self.assert_ok(weekly)
        # Keyed by the week's Monday rather than `%Y-W%W`, which splits a week
        # across the calendar-year boundary. Asserted as "is a Monday" rather
        # than against a literal, because the bucket is a local-time date and
        # the literal would only hold in the timezone it was written in.
        from datetime import datetime as _dt

        for row in json.loads(weekly.stdout)["rows"]:
            self.assertEqual(
                _dt.strptime(row["bucket"], "%Y-%m-%d").weekday(),
                0,
                f"week bucket {row['bucket']} should be a Monday",
            )

        as_json = self.run_flow("cost", "trend", "--all", "--json")
        self.assert_ok(as_json)
        payload = json.loads(as_json.stdout)
        self.assertIn("rows", payload)
        # Coverage rides alongside rows: it is a property of the store, not of
        # any bucket, and a caller checking whether its window was covered
        # should not have to infer that from which rows happen to be present.
        self.assertIn("coverage", payload)
        self.assertIn("claude", payload["coverage"])

        filtered = self.run_flow("cost", "trend", "--all", "--harness", "codex")
        self.assert_ok(filtered)
        self.assertNotIn("claude", filtered.stdout)

    def test_rescan_reports_compaction_events(self) -> None:
        home = self._seed_claude_transcript()
        result = self.run_flow("harvest", "claude")
        self.assert_ok(result)
        self.assertIn("1 compaction events", result.stdout)

        import sqlite3

        conn = sqlite3.connect(self._store_path(home))
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM agent_activity_raw").fetchone()[0], 1
        )
        # The streamed group is one turn, stored at its final output count.
        self.assertEqual(
            conn.execute(
                "SELECT json_extract(payload, '$.message.usage.output_tokens') FROM turn_raw"
            ).fetchall(),
            [(487,)],
        )
        conn.close()

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
                        "primary": {"used_percent": 41.0, "window_minutes": 300, "resets_at": _FUTURE_RESET},
                        "secondary": {"used_percent": 12.0, "window_minutes": 10080, "resets_at": _FUTURE_RESET + 1},
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

    def test_cost_active_recovers_initial_schema_without_ledger(self) -> None:
        """A replayed v1 migration must not fail on `schema_migration` already existing."""
        home = self.use_fake_home()
        store = self._store_path(home)
        store.parent.mkdir(parents=True, exist_ok=True)

        import sqlite3

        usage_store = self._load_store_module()
        conn = sqlite3.connect(store)
        try:
            conn.executescript(usage_store._V1)
            conn.commit()
        finally:
            conn.close()

        result = self.run_flow("cost", "active")
        self.assert_ok(result)
        self.assertIn("no active sessions", result.stdout)

        status = usage_store.store_status(store)
        self.assertEqual(status["state"], usage_store.STATE_EMPTY)
        self.assertEqual(status["user_version"], usage_store.SCHEMA_VERSION)

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


# A capacity reading's `resets_at`, far enough ahead that no test run reaches
# it. The original fixtures used 123 and 456 — epoch seconds in 1970, i.e. a
# reading that expired 56 years before the test ran. That went unnoticed while
# nothing checked expiry; once `capacity_gauge` started suppressing expired
# fields, every one of those fixtures correctly rendered nothing. Expiry now
# has its own tests, which pass the boundary explicitly rather than relying on
# what a literal happens to mean relative to now.
_FUTURE_RESET = 4_102_444_800  # 2100-01-01T00:00:00Z


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


def _claude_compact(
    session_id: str,
    trigger: str = "auto",
    pre: int = 180000,
    post: int = 25000,
    cwd: str = "/tmp/proj",
) -> dict:
    """A `compact_boundary` record, shaped from real data.

    All 29 on the machine this was written against carry `timestamp`,
    `sessionId`, and `cwd` at the top level — so these attach to a session by
    the ordinary path, with no special handling. `type` is `system` and the
    discriminator is `subtype`; other system records exist and carry no
    compaction data, which is why the collector keys on the latter.

    `compactMetadata` carries more in real data (`preCompactDiscoveredTools`,
    `preservedSegment`, `preservedMessages`) — omitted here because nothing
    reads it, and the raw payload is what preserves it either way.
    """
    return {
        "type": "system",
        "subtype": "compact_boundary",
        "content": "Conversation compacted",
        "level": "info",
        "isSidechain": False,
        "sessionId": session_id,
        "cwd": cwd,
        "timestamp": "2026-01-01T00:00:02Z",
        "compactMetadata": {
            "trigger": trigger,
            "preTokens": pre,
            "postTokens": post,
            "cumulativeDroppedTokens": pre - post,
            "durationMs": 12345,
        },
    }


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
        self.assertEqual(result, {"turns": 0, "activity": 0, "skipped": 0, "hard_stop": None})
        self.assertEqual(len(self.turn_raw_rows()), 1)

    def test_incremental_append_processes_only_new_lines(self) -> None:
        path = self.write_session("a.jsonl", _jsonl(_claude_user("sess-1"), _claude_assistant("sess-1", "req-1")))
        self.claude_collector.harvest_file(self.conn, path)
        with path.open("a") as fh:
            fh.write(_jsonl(_claude_assistant("sess-1", "req-2")))
        self.claude_collector.harvest_file(self.conn, path)
        self.assertEqual(len(self.turn_raw_rows()), 2)

    # ------------------------------------------------------------------
    # streamed output: several assistant lines share one requestId, and only
    # the last carries the final output_tokens
    # ------------------------------------------------------------------

    def _streamed_group(self, session_id: str = "sess-1", request_id: str = "req-1") -> list[dict]:
        """A real streamed response's shape: identical inputs, growing output.

        Modelled on `req_011Cbux7QgYTa5qSx5m2Y2f9` in this machine's corpus,
        whose six lines carry output_tokens [4, 4, 4, 4, 4, 487]. The repo had
        no fixture with more than one line per requestId, which is precisely
        why the partial-output defect survived to be found against the console
        rather than in the suite.
        """
        return [
            _claude_assistant(
                session_id, request_id, input_tokens=860, cache_read=21424,
                cache_write=14692, output_tokens=out,
            )
            for out in (4, 4, 487)
        ]

    def test_streamed_group_stores_final_output_and_counts_inputs_once(self) -> None:
        path = self.write_session(
            "a.jsonl", _jsonl(_claude_user("sess-1"), *self._streamed_group())
        )
        self.claude_collector.harvest_file(self.conn, path)

        rows = self.turn_raw_rows()
        self.assertEqual(len(rows), 1, "one requestId is one API call is one row")
        usage = json.loads(
            self.conn.execute("SELECT payload FROM turn_raw").fetchone()[0]
        )["message"]["usage"]
        self.assertEqual(usage["output_tokens"], 487, "output must be the group's maximum")
        # The whole reason `sum` is the wrong fix: inputs repeat verbatim on
        # every line, so summing the group would triple-count them.
        self.assertEqual(usage["input_tokens"], 860)
        self.assertEqual(usage["cache_read_input_tokens"], 21424)
        self.assertEqual(usage["cache_creation_input_tokens"], 14692)

    def test_streamed_group_split_across_two_harvests_still_converges(self) -> None:
        """The case a `last`-wins rule would get wrong.

        An incremental harvest can land anywhere, including mid-group. Here
        the batch boundary falls after the two partial lines, so the first
        pass stores 4 and the second must correct it to 487 — a plain
        `INSERT OR IGNORE` leaves it at 4 forever.
        """
        group = self._streamed_group()
        path = self.write_session("a.jsonl", _jsonl(_claude_user("sess-1"), *group[:2]))
        self.claude_collector.harvest_file(self.conn, path)
        self.assertEqual(self._stored_output("req-1"), 4, "precondition: partial count stored")

        with path.open("a") as fh:
            fh.write(_jsonl(group[2]))
        self.claude_collector.harvest_file(self.conn, path)

        self.assertEqual(self._stored_output("req-1"), 487)
        self.assertEqual(len(self.turn_raw_rows()), 1, "correcting must not add a row")

    def test_replaying_a_file_is_byte_identical(self) -> None:
        """Idempotence — the property `--rescan` rests on.

        Asserted on the full row rather than on output alone: a rescan
        rewinds every recorded file, so anything that drifted per replay
        would compound across runs.
        """
        path = self.write_session(
            "a.jsonl", _jsonl(_claude_user("sess-1"), *self._streamed_group())
        )
        self.claude_collector.harvest_file(self.conn, path)
        before = self.conn.execute(
            "SELECT natural_turn_id, turn_seq, ts, model, payload, source_line_no"
            " FROM turn_raw ORDER BY id"
        ).fetchall()

        for _ in range(2):
            self.conn.execute("UPDATE harvest SET last_offset = 0, last_line_no = 0")
            self.claude_collector.harvest_file(self.conn, path)

        after = self.conn.execute(
            "SELECT natural_turn_id, turn_seq, ts, model, payload, source_line_no"
            " FROM turn_raw ORDER BY id"
        ).fetchall()
        self.assertEqual(before, after)

    def test_a_lower_output_count_never_overwrites_a_higher_one(self) -> None:
        """Max-wins, not last-wins, stated directly.

        The corpus cannot tell these apart — the two rules differ by 2 tokens
        across every turn on this machine — so the property that makes replay
        safe has to be pinned by construction rather than by measurement.
        """
        path = self.write_session(
            "a.jsonl",
            _jsonl(
                _claude_user("sess-1"),
                _claude_assistant("sess-1", "req-1", output_tokens=487),
                _claude_assistant("sess-1", "req-1", output_tokens=4),
            ),
        )
        self.claude_collector.harvest_file(self.conn, path)
        self.assertEqual(self._stored_output("req-1"), 487)

    def test_a_row_with_no_usage_loses_to_a_row_with_a_real_count(self) -> None:
        """What COALESCE(..., -1) is for.

        NULL loses every SQL comparison, so without the coalesce a stored row
        whose payload has no output_tokens could never be corrected — the
        guard would compare against NULL and refuse every update.
        """
        no_usage = _claude_assistant("sess-1", "req-1")
        del no_usage["message"]["usage"]["output_tokens"]
        path = self.write_session(
            "a.jsonl",
            _jsonl(
                _claude_user("sess-1"),
                no_usage,
                _claude_assistant("sess-1", "req-1", output_tokens=42),
            ),
        )
        self.claude_collector.harvest_file(self.conn, path)
        self.assertEqual(self._stored_output("req-1"), 42)

    def test_ts_and_turn_seq_keep_the_first_lines_values(self) -> None:
        """A corrected turn must not migrate in time.

        `ts` is what every time-bucketed read surface groups on. If the
        correction carried the last line's timestamp, a response that started
        at 23:59 and finished after midnight would move to the next day on
        re-harvest — the same turn landing in different buckets depending on
        when it was harvested.
        """
        first = _claude_assistant("sess-1", "req-1", output_tokens=4)
        first["timestamp"] = "2026-01-01T23:59:00Z"
        last = _claude_assistant("sess-1", "req-1", output_tokens=487)
        last["timestamp"] = "2026-01-02T00:00:30Z"
        path = self.write_session("a.jsonl", _jsonl(_claude_user("sess-1"), first, last))
        self.claude_collector.harvest_file(self.conn, path)

        row = self.conn.execute("SELECT ts, turn_seq, source_line_no FROM turn_raw").fetchone()
        self.assertEqual(row[0], "2026-01-01T23:59:00Z", "ts keeps the first line's value")
        self.assertEqual(row[1], 2, "turn_seq keeps the first line's value")
        self.assertEqual(row[2], 3, "source_line_no advances to the corrected line")
        self.assertEqual(self._stored_output("req-1"), 487)

    def _stored_output(self, request_id: str) -> int | None:
        row = self.conn.execute(
            "SELECT json_extract(payload, '$.message.usage.output_tokens')"
            " FROM turn_raw WHERE natural_turn_id = ?",
            (request_id,),
        ).fetchone()
        return row[0] if row else None

    # ------------------------------------------------------------------
    # compact_boundary — Claude's own context-management telemetry
    # ------------------------------------------------------------------

    def test_compact_boundary_records_land_in_agent_activity_raw(self) -> None:
        path = self.write_session(
            "a.jsonl",
            _jsonl(
                _claude_user("sess-1"),
                _claude_compact("sess-1", "manual", pre=150000, post=30000),
                _claude_assistant("sess-1", "req-1"),
                _claude_compact("sess-1", "auto", pre=190000, post=25000),
            ),
        )
        result = self.claude_collector.harvest_file(self.conn, path)

        self.assertEqual(result["activity"], 2)
        self.assertEqual(result["turns"], 1, "a compaction is not a turn")
        rows = self.conn.execute(
            "SELECT kind, ts, payload FROM agent_activity_raw ORDER BY source_line_no"
        ).fetchall()
        self.assertEqual([r[0] for r in rows], ["compact_boundary", "compact_boundary"])
        # trigger is the field that matters: manual is deliberate hygiene,
        # auto is hitting the ceiling. Summing them into one count would
        # destroy the distinction, so the verbatim payload is what's stored.
        triggers = [json.loads(r[2])["compactMetadata"]["trigger"] for r in rows]
        self.assertEqual(triggers, ["manual", "auto"])
        pre_tokens = [json.loads(r[2])["compactMetadata"]["preTokens"] for r in rows]
        self.assertEqual(pre_tokens, [150000, 190000])

    def test_compact_boundary_does_not_reach_turn_raw(self) -> None:
        """A compaction burns tokens and reports none, so it must not appear
        in the table every token sum reads."""
        path = self.write_session(
            "a.jsonl", _jsonl(_claude_user("sess-1"), _claude_compact("sess-1", "auto"))
        )
        self.claude_collector.harvest_file(self.conn, path)
        self.assertEqual(len(self.turn_raw_rows()), 0)

    def test_other_system_records_are_still_ignored(self) -> None:
        """The branch keys on `subtype`, not on `type == "system"`."""
        path = self.write_session(
            "a.jsonl",
            _jsonl(
                _claude_user("sess-1"),
                {"type": "system", "sessionId": "sess-1", "timestamp": "2026-01-01T00:00:02Z"},
            ),
        )
        result = self.claude_collector.harvest_file(self.conn, path)
        self.assertEqual(result["activity"], 0)
        self.assertEqual(result["skipped"], 0, "an ordinary system record is not a shape violation")

    def test_replaying_compact_records_does_not_duplicate_them(self) -> None:
        path = self.write_session(
            "a.jsonl",
            _jsonl(
                _claude_user("sess-1"),
                _claude_compact("sess-1", "manual"),
                _claude_compact("sess-1", "auto"),
            ),
        )
        self.claude_collector.harvest_file(self.conn, path)
        self.conn.execute("UPDATE harvest SET last_offset = 0, last_line_no = 0")
        result = self.claude_collector.harvest_file(self.conn, path)

        self.assertEqual(result["activity"], 0, "a replayed compaction is a no-op")
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM agent_activity_raw").fetchone()[0], 2
        )

    def test_compact_boundary_without_a_timestamp_hard_stops(self) -> None:
        """`agent_activity_raw.ts` is NOT NULL, and this insert is
        `INSERT OR IGNORE` — which applies its conflict resolution to every
        constraint on the statement, not just the uniqueness one it was
        written for. A NULL timestamp would no-op there, indistinguishable
        from a legitimate duplicate, and nothing would report the drop. So it
        is checked before the insert, matching the assistant path.
        """
        bad = _claude_compact("sess-1", "manual")
        del bad["timestamp"]
        path = self.write_session("a.jsonl", _jsonl(_claude_user("sess-1"), bad))
        result = self.claude_collector.harvest_file(self.conn, path)

        self.assertIsNotNone(result["hard_stop"])
        self.assertIn("timestamp", result["hard_stop"]["reason"])

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

    # ------------------------------------------------------------------
    # --rescan scoping: --since, --session, --dry-run
    # ------------------------------------------------------------------

    def _recorded(self, path: str, mtime: float) -> None:
        self.conn.execute(
            "INSERT INTO harvest (harness, source_path, host_id, last_size, last_offset,"
            " last_line_no, last_line_hash, file_mtime, harvested_at, collector_version)"
            " VALUES ('claude', ?, '', 100, 100, 5, 'h', ?, '2026-01-01T00:00:00Z', 2)",
            (path, mtime),
        )

    @staticmethod
    def _mtime(date: str) -> float:
        from datetime import datetime as _dt

        return _dt.fromisoformat(date).timestamp()

    def _offsets(self) -> dict:
        return {
            row[0]: row[1]
            for row in self.conn.execute(
                "SELECT source_path, last_offset FROM harvest WHERE harness = 'claude'"
            )
        }

    def test_since_rewinds_only_files_modified_on_or_after_the_date(self) -> None:
        """`--since` filters on the transcript's mtime, not on when we last
        harvested it. "Rescan recently active sessions" is a property of the
        file; filtering on `harvested_at` would select by our own bookkeeping
        and sweep in long-dead sessions that happened to be picked up late.
        """
        self._recorded("/tmp/old.jsonl", self._mtime("2026-07-01"))
        self._recorded("/tmp/new.jsonl", self._mtime("2026-08-10"))
        self._recorded("/tmp/boundary.jsonl", self._mtime("2026-08-01"))

        self.harvest._reset_claude_watermarks(self.conn, since="2026-08-01")

        offsets = self._offsets()
        self.assertEqual(offsets["/tmp/old.jsonl"], 100, "outside the window, untouched")
        self.assertEqual(offsets["/tmp/new.jsonl"], 0)
        self.assertEqual(offsets["/tmp/boundary.jsonl"], 0, "on the date is inside the window")

    def test_session_matches_subagent_files_alongside_the_main_transcript(self) -> None:
        """A session uuid must reach the whole session.

        Claude's subagent files live under `subagents/<parent-uuid>/` and
        declare the parent's own sessionId, so the uuid appears in every one
        of that session's paths. Matching `source_path` by substring reaches
        them together — which is required, because subagent turns have the
        same partial-output defect and an exact join on `session.source_path`
        would reach only whichever file was harvested first.
        """
        uuid = "51de70eb-0429-4b1f-a8e1-611a54bd7894"
        self._recorded(f"/tmp/projects/{uuid}.jsonl", self._mtime("2026-08-10"))
        self._recorded(f"/tmp/projects/subagents/{uuid}/agent-abc.jsonl", self._mtime("2026-08-10"))
        self._recorded("/tmp/projects/other-session.jsonl", self._mtime("2026-08-10"))

        self.harvest._reset_claude_watermarks(self.conn, session=uuid)

        offsets = self._offsets()
        self.assertEqual(offsets[f"/tmp/projects/{uuid}.jsonl"], 0)
        self.assertEqual(offsets[f"/tmp/projects/subagents/{uuid}/agent-abc.jsonl"], 0)
        self.assertEqual(offsets["/tmp/projects/other-session.jsonl"], 100)

    def test_filters_compose(self) -> None:
        uuid = "aaaa1111"
        self._recorded(f"/tmp/{uuid}-old.jsonl", self._mtime("2026-07-01"))
        self._recorded(f"/tmp/{uuid}-new.jsonl", self._mtime("2026-08-10"))
        self._recorded("/tmp/other-new.jsonl", self._mtime("2026-08-10"))

        self.harvest._reset_claude_watermarks(self.conn, since="2026-08-01", session=uuid)

        offsets = self._offsets()
        self.assertEqual(offsets[f"/tmp/{uuid}-new.jsonl"], 0, "both filters match")
        self.assertEqual(offsets[f"/tmp/{uuid}-old.jsonl"], 100, "wrong date")
        self.assertEqual(offsets["/tmp/other-new.jsonl"], 100, "wrong session")

    def test_a_filtered_rescan_clears_title_state_only_for_sessions_it_replays(self) -> None:
        """The bug that narrowing the reset would otherwise reintroduce.

        Clearing `title_ai_ts` for a session whose files are NOT being
        rewound leaves it with derived state gone and no replay coming to
        re-derive it — so the next ordinary incremental harvest hands an
        ai-title an effective timestamp with nothing to compare against and
        can flip that title backwards. That is exactly what the unfiltered
        reset was written to prevent.
        """
        in_scope = self.write_session(
            "in-scope.jsonl",
            _jsonl(
                {"type": "user", "sessionId": "sess-in", "timestamp": "2026-01-01T00:00:00Z"},
                _claude_ai_title("sess-in", "in title"),
            ),
        )
        out_of_scope = self.write_session(
            "out-of-scope.jsonl",
            _jsonl(
                {"type": "user", "sessionId": "sess-out", "timestamp": "2026-01-01T00:00:00Z"},
                _claude_ai_title("sess-out", "out title"),
            ),
        )
        self.claude_collector.harvest_file(self.conn, in_scope)
        self.claude_collector.harvest_file(self.conn, out_of_scope)

        self.harvest._reset_claude_watermarks(self.conn, session="in-scope")

        state = {
            row[0]: (row[1], row[2])
            for row in self.conn.execute("SELECT session_id, last_seen_ts, title_ai_ts FROM session")
        }
        self.assertEqual(state["sess-in"], (None, None), "replayed session is reset to a first pass")
        self.assertNotEqual(
            state["sess-out"],
            (None, None),
            "a session not being replayed must keep the derived state it still needs",
        )

    def test_dry_run_scope_counts_files_and_stored_turns(self) -> None:
        path = self.write_session(
            "a.jsonl", _jsonl(_claude_user("sess-1"), _claude_assistant("sess-1", "req-1"))
        )
        self.claude_collector.harvest_file(self.conn, path)
        self.conn.execute(
            "UPDATE harvest SET file_mtime = ? WHERE harness = 'claude'",
            (self._mtime("2026-08-10"),),
        )

        self.assertEqual(
            self.harvest._claude_rescan_scope(self.conn), {"files": 1, "turns": 1}
        )
        self.assertEqual(
            self.harvest._claude_rescan_scope(self.conn, since="2026-08-01"),
            {"files": 1, "turns": 1},
        )
        self.assertEqual(
            self.harvest._claude_rescan_scope(self.conn, since="2026-09-01"),
            {"files": 0, "turns": 0},
            "a filter matching nothing must report nothing, not everything",
        )

    def test_dry_run_scope_writes_nothing(self) -> None:
        """A dry run that writes is worse than no dry run — it looks like a
        rehearsal and behaves like a commit."""
        path = self.write_session(
            "a.jsonl", _jsonl(_claude_user("sess-1"), _claude_assistant("sess-1", "req-1"))
        )
        self.claude_collector.harvest_file(self.conn, path)
        before = self.conn.execute(
            "SELECT source_path, last_offset, last_line_no FROM harvest"
        ).fetchall()

        self.harvest._claude_rescan_scope(self.conn)

        self.assertEqual(
            self.conn.execute("SELECT source_path, last_offset, last_line_no FROM harvest").fetchall(),
            before,
        )

    def test_a_rescan_marks_the_normalized_layer_stale(self) -> None:
        """The corrections must reach a read surface, not just the raw layer.

        `normalize_all` selects rows whose `norm_version` is older than the
        current one, and nothing marked a `turn_norm` row stale when its
        `turn_raw` payload changed underneath it — until the upsert existed, a
        payload never could. So the NORM_VERSION bump only picks up corrected
        payloads if it runs AFTER the rescan, and the likely order is the
        opposite: `flow cost active` normalizes, and hooks run it constantly.

        Caught on the real corpus, where raw held 31.90M output tokens against
        28.13M normalized — the whole 12% recovery stranded one layer down,
        with both tables individually self-consistent and nothing reporting it.
        """
        import normalize

        path = self.write_session(
            "a.jsonl",
            _jsonl(
                _claude_user("sess-1"),
                *[_claude_assistant("sess-1", "req-1", output_tokens=o) for o in (4, 4, 487)],
            ),
        )
        self.claude_collector.harvest_file(self.conn, path)
        # Rewind raw to the partial count AND normalize it, so the stale row
        # is stamped with the current version — the order that hides the bug.
        partial = json.dumps(_claude_assistant("sess-1", "req-1", output_tokens=4))
        self.conn.execute("UPDATE turn_raw SET payload = ? WHERE natural_turn_id = 'req-1'", (partial,))
        normalize.normalize_all(self.conn)
        self.assertEqual(
            self.conn.execute("SELECT output_tokens FROM turn_norm").fetchone()[0],
            4,
            "precondition: the normalized layer holds the partial count",
        )

        self.harvest._reset_claude_watermarks(self.conn)
        self.claude_collector.harvest_all(self.conn, self.dir)
        result = normalize.normalize_all(self.conn)

        self.assertEqual(result["normalized"], 1, "the corrected row must be reprocessed")
        self.assertEqual(
            self.conn.execute("SELECT output_tokens FROM turn_norm").fetchone()[0],
            487,
            "a rescan whose corrections never reach turn_norm changes no visible number",
        )

    def test_an_incremental_correction_reaches_the_normalized_layer(self) -> None:
        """The same loss, with no rescan involved at all.

        `flow cost active` harvests and then normalizes. Run it while a
        response is still streaming and the partial group is stored at output
        4 AND stamped with the current norm_version. The next harvest corrects
        `turn_raw` to 487 — and without the collector invalidating the
        normalized row, `turn_norm` keeps 4 permanently.

        This is the raw-layer test's missing counterpart: the raw layer was
        already proven to converge, and every read surface queries the other
        one.
        """
        import normalize

        group = [
            _claude_assistant("sess-1", "req-1", output_tokens=o) for o in (4, 4, 487)
        ]
        path = self.write_session("a.jsonl", _jsonl(_claude_user("sess-1"), *group[:2]))
        self.claude_collector.harvest_file(self.conn, path)
        normalize.normalize_all(self.conn)
        self.assertEqual(
            self.conn.execute("SELECT output_tokens FROM turn_norm").fetchone()[0], 4
        )

        with path.open("a") as fh:
            fh.write(_jsonl(group[2]))
        self.claude_collector.harvest_file(self.conn, path)
        normalize.normalize_all(self.conn)

        self.assertEqual(
            self.conn.execute("SELECT output_tokens FROM turn_norm").fetchone()[0],
            487,
            "a correction that never reaches turn_norm changes no visible number",
        )

    def test_rescanning_one_file_of_a_multi_file_session_replays_the_whole_session(self) -> None:
        """Why the filter is widened to whole sessions before anything writes.

        A session's derived title state is per session; the watermark is per
        file. Reset them over different sets and a partial replay re-accepts
        the replayed file's title against a cleared `title_ai_ts`, while the
        file carrying the newer title is never replayed to win it back — so
        the title is wrong permanently, not just until the next harvest.
        """
        # One session across two files. `b-main` carries the older ai-title;
        # `a-cont` carries the newer one, which is the accepted title.
        b_main = self.write_session(
            "b-main.jsonl",
            _jsonl(
                {"type": "user", "sessionId": "sess-1", "timestamp": "2026-07-01T00:00:00Z"},
                _claude_ai_title("sess-1", "old title"),
                _claude_assistant("sess-1", "req-b"),
            ),
        )
        a_cont = self.write_session(
            "a-cont.jsonl",
            _jsonl(
                {"type": "user", "sessionId": "sess-1", "timestamp": "2026-08-10T00:00:00Z"},
                _claude_ai_title("sess-1", "new title"),
                _claude_assistant("sess-1", "req-a"),
            ),
        )
        self.claude_collector.harvest_file(self.conn, b_main)
        self.claude_collector.harvest_file(self.conn, a_cont)
        self.assertEqual(
            self.conn.execute("SELECT title FROM session WHERE session_id = 'sess-1'").fetchone()[0],
            "new title",
        )

        # Filter names only one of the session's two files.
        paths, session_ids = self.harvest._claude_rescan_closure(self.conn, session="b-main")
        self.assertEqual(
            len(paths), 2, "the closure must expand to every file of the touched session"
        )
        self.assertEqual(len(session_ids), 1)

        self.harvest._reset_claude_watermarks(self.conn, session="b-main")
        self.claude_collector.harvest_all(self.conn, self.dir)

        self.assertEqual(
            self.conn.execute("SELECT title FROM session WHERE session_id = 'sess-1'").fetchone()[0],
            "new title",
            "a partial replay must not strand the session on the older title",
        )

    def test_the_dry_run_reports_the_widened_scope(self) -> None:
        """A rehearsal whose numbers understate the real blast radius is
        worse than no rehearsal."""
        for name, ts in (("b-main.jsonl", "2026-07-01"), ("a-cont.jsonl", "2026-08-10")):
            self.claude_collector.harvest_file(
                self.conn,
                self.write_session(
                    name,
                    _jsonl(
                        {"type": "user", "sessionId": "sess-1", "timestamp": f"{ts}T00:00:00Z"},
                        _claude_assistant("sess-1", f"req-{name[0]}"),
                    ),
                ),
            )

        scope = self.harvest._claude_rescan_scope(self.conn, session="b-main")
        self.assertEqual(scope, {"files": 2, "turns": 2})

    def test_a_filtered_rescan_leaves_other_sessions_normalized_rows_alone(self) -> None:
        """Invalidating the normalized layer follows the same scope as the
        watermark reset — a session not being replayed must not be left with
        a stale row and no pass coming to recompute it."""
        import normalize

        in_scope = self.write_session(
            "in-scope.jsonl",
            _jsonl(_claude_user("sess-in"), _claude_assistant("sess-in", "req-in")),
        )
        out_of_scope = self.write_session(
            "out-of-scope.jsonl",
            _jsonl(_claude_user("sess-out"), _claude_assistant("sess-out", "req-out")),
        )
        self.claude_collector.harvest_file(self.conn, in_scope)
        self.claude_collector.harvest_file(self.conn, out_of_scope)
        normalize.normalize_all(self.conn)

        self.harvest._reset_claude_watermarks(self.conn, session="in-scope")

        versions = {
            row[0]: row[1]
            for row in self.conn.execute(
                "SELECT tr.natural_turn_id, tn.norm_version FROM turn_norm tn"
                " JOIN turn_raw tr ON tr.id = tn.turn_raw_id"
            )
        }
        self.assertEqual(versions["req-in"], -1, "replayed rows are marked stale")
        self.assertEqual(
            versions["req-out"],
            normalize.NORM_VERSION,
            "a row outside the rescan's scope stays current",
        )

    def test_a_rescan_corrects_a_partial_output_count_end_to_end(self) -> None:
        """The whole point of the mechanism, through the real entry points.

        Simulates a file harvested by the pre-v3 collector — the stored row
        holds the first line's partial `output_tokens` — and asserts one
        rescan reaches 487 without duplicating the row.
        """
        path = self.write_session(
            "a.jsonl",
            _jsonl(
                _claude_user("sess-1"),
                *[
                    _claude_assistant("sess-1", "req-1", output_tokens=out)
                    for out in (4, 4, 487)
                ],
            ),
        )
        self.claude_collector.harvest_file(self.conn, path)
        # Rewind the stored payload to what INSERT OR IGNORE would have left.
        partial = json.dumps(_claude_assistant("sess-1", "req-1", output_tokens=4))
        self.conn.execute("UPDATE turn_raw SET payload = ? WHERE natural_turn_id = 'req-1'", (partial,))

        self.harvest._reset_claude_watermarks(self.conn)
        self.claude_collector.harvest_all(self.conn, self.dir)

        rows = self.conn.execute(
            "SELECT json_extract(payload, '$.message.usage.output_tokens') FROM turn_raw"
        ).fetchall()
        self.assertEqual(rows, [(487,)])


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
                        "primary": {"used_percent": 5.0, "window_minutes": 300, "resets_at": _FUTURE_RESET},
                        "secondary": {"used_percent": 10.0, "window_minutes": 10080, "resets_at": _FUTURE_RESET + 1},
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
        self.assertEqual(row["capacity_primary_resets_at"], _FUTURE_RESET)
        self.assertEqual(row["capacity_secondary_used_pct"], 10.0)
        self.assertEqual(row["capacity_secondary_window_minutes"], 10080)
        self.assertEqual(row["capacity_secondary_resets_at"], _FUTURE_RESET + 1)
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
                    "rate_limits": {"primary": {"used_percent": 1.0, "window_minutes": 300, "resets_at": _FUTURE_RESET}},
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
                    "rate_limits": {"primary": {"used_percent": 1.0, "window_minutes": 300, "resets_at": _FUTURE_RESET}},
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

    # ------------------------------------------------------------------
    # cache-TTL split — the halves bill 60% apart
    # ------------------------------------------------------------------

    def test_claude_cache_ttl_split_sums_to_the_total(self) -> None:
        """The migration's invariant, on real-shaped input.

        `ephemeral_1h + ephemeral_5m == cache_creation_input_tokens` held
        exactly across 20,587 real turns. `cache_write_tokens` stays the
        total rather than being replaced by the halves — it is what Codex
        reports and what existing callers read.
        """
        sess = self.insert_session(session_id="claude-ttl-1", harness="claude")
        tr_id = self.insert_turn_raw(
            sess,
            {
                "type": "assistant",
                "timestamp": "2026-01-01T00:00:01Z",
                "requestId": "req-ttl-1",
                "message": {
                    "model": "claude-sonnet-5",
                    "usage": {
                        "input_tokens": 860,
                        "cache_read_input_tokens": 21424,
                        "cache_creation_input_tokens": 14692,
                        "cache_creation": {
                            "ephemeral_1h_input_tokens": 4692,
                            "ephemeral_5m_input_tokens": 10000,
                        },
                        "output_tokens": 487,
                    },
                },
            },
        )
        self.normalize.normalize_all(self.conn)
        row = self.norm_row(tr_id)
        self.assertEqual(row["cache_write_1h_tokens"], 4692)
        self.assertEqual(row["cache_write_5m_tokens"], 10000)
        self.assertEqual(row["cache_write_tokens"], 14692, "the total is kept, not replaced")
        self.assertEqual(
            row["cache_write_1h_tokens"] + row["cache_write_5m_tokens"],
            row["cache_write_tokens"],
        )

    def test_codex_reports_no_ttl_split_so_both_columns_are_null(self) -> None:
        """NULL, not 0 — `harness_capability` says Codex cannot report this,
        and turn_norm keeps "cannot report" distinct from "reported zero"
        everywhere else."""
        sess = self.insert_session()
        tr_id = self.insert_turn_raw(
            sess,
            {
                "timestamp": "2026-01-01T00:00:01Z",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": {
                            "input_tokens": 10,
                            "cached_input_tokens": 2,
                            "cache_write_input_tokens": 5,
                        }
                    },
                },
            },
        )
        self.normalize.normalize_all(self.conn)
        row = self.norm_row(tr_id)
        self.assertEqual(row["cache_write_tokens"], 5)
        self.assertIsNone(row["cache_write_1h_tokens"])
        self.assertIsNone(row["cache_write_5m_tokens"])

    def test_claude_without_cache_creation_leaves_the_split_null(self) -> None:
        """Older transcripts predate the field. Absent is not zero."""
        sess = self.insert_session(session_id="claude-ttl-2", harness="claude")
        tr_id = self.insert_turn_raw(
            sess,
            {
                "type": "assistant",
                "timestamp": "2026-01-01T00:00:01Z",
                "requestId": "req-ttl-2",
                "message": {
                    "model": "claude-sonnet-5",
                    "usage": {"input_tokens": 100, "cache_creation_input_tokens": 20, "output_tokens": 10},
                },
            },
        )
        self.normalize.normalize_all(self.conn)
        row = self.norm_row(tr_id)
        self.assertEqual(row["cache_write_tokens"], 20)
        self.assertIsNone(row["cache_write_1h_tokens"])
        self.assertIsNone(row["cache_write_5m_tokens"])

    def test_a_norm_version_bump_recomputes_an_existing_row(self) -> None:
        """The whole backfill mechanism for the split — no re-harvest.

        The fields were in the raw payload from the first harvest, just
        unread. Simulates a row normalized under version 1 and asserts the
        current pass picks it up and fills the new columns.
        """
        sess = self.insert_session(session_id="claude-ttl-3", harness="claude")
        tr_id = self.insert_turn_raw(
            sess,
            {
                "type": "assistant",
                "timestamp": "2026-01-01T00:00:01Z",
                "requestId": "req-ttl-3",
                "message": {
                    "model": "claude-sonnet-5",
                    "usage": {
                        "input_tokens": 100,
                        "cache_creation_input_tokens": 30,
                        "cache_creation": {
                            "ephemeral_1h_input_tokens": 10,
                            "ephemeral_5m_input_tokens": 20,
                        },
                        "output_tokens": 10,
                    },
                },
            },
        )
        self.normalize.normalize_all(self.conn)
        # Rewind this row to the pre-split convention: normalized, but by
        # code that never read cache_creation.
        self.conn.execute(
            "UPDATE turn_norm SET norm_version = 1,"
            " cache_write_1h_tokens = NULL, cache_write_5m_tokens = NULL"
            " WHERE turn_raw_id = ?",
            (tr_id,),
        )
        result = self.normalize.normalize_all(self.conn)

        self.assertEqual(result["normalized"], 1, "a stale row is reprocessed")
        row = self.norm_row(tr_id)
        self.assertEqual(row["cache_write_1h_tokens"], 10)
        self.assertEqual(row["cache_write_5m_tokens"], 20)

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


def _pin_tz(test: unittest.TestCase, name: str = "UTC") -> None:
    """Pin the process timezone for one test, restoring it afterwards.

    `flow cost trend` buckets by LOCAL calendar day — a trend meant to show
    whether a working habit is changing has to follow the days the work
    happened in, and UTC buckets split an evening across two rows for anyone
    west of Greenwich. That makes bucket output timezone-dependent, so tests
    that assert on bucket labels have to say which zone they mean rather than
    inheriting the machine's and passing only where they were written.

    SQLite's `localtime` modifier reads the same `TZ` this sets, so pinning it
    here covers both the Python and the SQL side.
    """
    import time

    original = os.environ.get("TZ")
    os.environ["TZ"] = name
    time.tzset()

    def restore() -> None:
        if original is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original
        time.tzset()

    test.addCleanup(restore)


class CostTests(unittest.TestCase):
    """Direct tests of cli/cost.py's query functions, against a small
    constructed turn_norm/session dataset — no collector or normalize
    pipeline involved, since these functions only ever read what's already
    in the store.
    """

    def setUp(self) -> None:
        import sqlite3

        # Bucket labels are local-time, so they are only deterministic against
        # a stated zone. UTC keeps the Z-suffixed fixtures reading as their
        # own date; `test_buckets_follow_the_local_day` pins a real offset
        # instead, to prove the localtime conversion is actually applied.
        _pin_tz(self)

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

    def insert_ctx_turn(
        self,
        session_row_id: int,
        ts: str,
        ctx: int,
        is_subagent: int = 0,
        model: str = "claude-sonnet-5",
    ) -> None:
        """One context sample: fresh+cache_read+cache_write = ctx.

        `model` defaults to a real id rather than the placeholder `'m'` this
        helper used to write. Once window resolution started consulting
        `data/model_context_windows.json`, a placeholder resolved to "unknown
        model" and correctly suppressed every percentage — which is the right
        behaviour and the wrong fixture: these tests are about the ctx/carry
        arithmetic, so they need a model whose window is knowable. The
        unknown-model path has its own test rather than being the accidental
        default for all of them.
        """
        turn_raw_id = self._next_id
        self._next_id += 1
        self.conn.execute(
            "INSERT INTO turn_raw (id, session_row_id, natural_turn_id, turn_seq, is_subagent,"
            " ts, model, payload, source_path, source_line_no, collector_version)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, '{}', '/tmp/x', ?, 1)",
            (turn_raw_id, session_row_id, f"t{turn_raw_id}", turn_raw_id, is_subagent, ts, model, turn_raw_id),
        )
        self.conn.execute(
            "INSERT INTO turn_norm (turn_raw_id, ts, model, is_subagent, fresh_input_tokens,"
            " cache_read_tokens, cache_write_tokens, output_tokens, norm_version)"
            " VALUES (?, ?, ?, ?, ?, 0, 0, 1, 1)",
            (turn_raw_id, ts, model, is_subagent, ctx),
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

    def _active_row(self, **overrides) -> dict:
        """One `active_rows`-shaped row. Keyed access in the renderer is
        deliberate — a row missing a field is shape drift, not a default."""
        row = {
            "id": "abc12345",
            "label": "some session",
            "ctx_pct": 46.0,
            "carry_pct": 38.0,
            "window_exact": False,
            "window_source": "model",
            "sub_pct": None,
            "idle_sec": 245,
            "recommend": "/compact at next break",
            "session_id": "abc12345-full",
        }
        row.update(overrides)
        return row

    def test_render_active_table_marks_inferred_windows(self) -> None:
        out = self.cost._render_active_table([self._active_row()])
        self.assertIn("~46%", out)
        self.assertIn("4m", out)
        self.assertIn("window inferred", out)

    def test_render_active_table_suppresses_an_unknown_window(self) -> None:
        """`?`, not a blank: a blank cell reads as zero at a glance, and this
        is the opposite claim — not computable, not small."""
        out = self.cost._render_active_table(
            [
                self._active_row(
                    ctx_pct=None, carry_pct=None, window_source="unknown", recommend=None
                )
            ]
        )
        self.assertIn("?", out)
        self.assertIn("window unknown", out)
        self.assertIn("model_context_windows.json", out)
        self.assertNotIn("~", out, "an unknown window is not an inferred one")

    def test_render_active_table_shows_subagent_share(self) -> None:
        out = self.cost._render_active_table([self._active_row(sub_pct=12.9)])
        self.assertIn("13%", out)
        self.assertIn("subagent share", out)

    def test_render_active_table_empty(self) -> None:
        self.assertEqual(self.cost._render_active_table([]), "(no active sessions in range)")

    # ------------------------------------------------------------------
    # window resolution: statusline > this session's auto compaction > model
    # ------------------------------------------------------------------

    def _auto_compaction(self, session_row_id: int, pre_tokens: int, trigger: str = "auto") -> None:
        self.conn.execute(
            "INSERT INTO agent_activity_raw (session_row_id, ts, kind, payload,"
            " source_path, source_line_no, collector_version)"
            " VALUES (?, '2026-01-10T11:00:00Z', 'compact_boundary', ?, '/tmp/x', ?, 3)",
            (
                session_row_id,
                json.dumps({"compactMetadata": {"trigger": trigger, "preTokens": pre_tokens}}),
                self._next_id,
            ),
        )
        self._next_id += 1

    def test_auto_compaction_resolves_that_sessions_window(self) -> None:
        """An auto compaction fires at the ceiling, so its `preTokens` is a
        direct observation of how much the session actually held — better
        than any lookup, and measured rather than inferred.

        The real corpus reads 1,000,069–1,004,282 on 8 of 11 auto events;
        the value below is from that cluster.
        """
        sess = self.insert_session("compacted-1", harness="claude")
        self.insert_ctx_turn(sess, "2026-01-10T11:50:00Z", 120_000)
        self._auto_compaction(sess, 1_001_651)

        rows = self.cost.active_rows(self.conn, within_minutes=60, now=self._active_now())
        row = rows[0]
        self.assertEqual(row["window_source"], "compaction")
        self.assertTrue(row["window_exact"], "an observation from the transcript is not an inference")
        # 120K of 1M, not of the 200K the model table would have assumed.
        self.assertEqual(row["ctx_pct"], 12.0)

    def test_an_auto_compaction_does_not_leak_to_another_session_on_the_same_model(self) -> None:
        """The confirmed scope rule, in the direction that would do damage.

        Every model that has auto-compacted also runs in 200K sessions
        constantly. A model-scoped rule would silently relabel all of them as
        1M and divide every percentage by five.
        """
        compacted = self.insert_session("compacted-1", harness="claude")
        self.insert_ctx_turn(compacted, "2026-01-10T11:50:00Z", 120_000)
        self._auto_compaction(compacted, 1_001_651)
        plain = self.insert_session("plain-1", harness="claude")
        self.insert_ctx_turn(plain, "2026-01-10T11:50:00Z", 120_000)

        rows = {r["session_id"]: r for r in self.cost.active_rows(self.conn, 60, self._active_now())}
        self.assertEqual(rows["compacted-1"]["window_source"], "compaction")
        self.assertEqual(rows["plain-1"]["window_source"], "model")
        self.assertEqual(rows["plain-1"]["ctx_pct"], 60.0, "same model, same ctx, unaffected window")

    def test_a_manual_compaction_says_nothing_about_the_window(self) -> None:
        """A deliberate `/compact` records where the user chose to cut, which
        is unrelated to the ceiling."""
        sess = self.insert_session("manual-1", harness="claude")
        self.insert_ctx_turn(sess, "2026-01-10T11:50:00Z", 120_000)
        self._auto_compaction(sess, 1_001_651, trigger="manual")

        row = self.cost.active_rows(self.conn, 60, self._active_now())[0]
        self.assertEqual(row["window_source"], "model")

    def test_an_unknown_model_suppresses_the_percentage(self) -> None:
        """An honest blank beats a confident wrong number in a tool whose
        purpose is measurement — and it is the signal that the table needs an
        entry."""
        sess = self.insert_session("mystery-1", harness="claude")
        self.insert_ctx_turn(sess, "2026-01-10T11:50:00Z", 120_000, model="claude-not-a-real-model")

        row = self.cost.active_rows(self.conn, 60, self._active_now())[0]
        self.assertEqual(row["window_source"], "unknown")
        self.assertIsNone(row["ctx_pct"])
        self.assertIsNone(row["carry_pct"])
        self.assertIsNone(row["recommend"], "no window means no judgment, not a passing grade")

    def test_a_model_suffix_resolves_via_the_longest_prefix(self) -> None:
        sess = self.insert_session("suffixed-1", harness="claude")
        self.insert_ctx_turn(sess, "2026-01-10T11:50:00Z", 100_000, model="claude-haiku-4-5-20251001")

        row = self.cost.active_rows(self.conn, 60, self._active_now())[0]
        self.assertEqual(row["window_source"], "model")
        self.assertEqual(row["ctx_pct"], 50.0, "100K of the 200K haiku window")

    def test_a_context_larger_than_the_observed_window_discards_the_observation(self) -> None:
        """A point-in-time observation can be outgrown, and believing it is
        worse than the inference it displaced.

        Switch to the 1M variant with `/model` after a 200K auto compaction and
        context keeps climbing. Without the guard the view reports 200% and
        marks it *measured*; the model source would have self-corrected via
        `long_threshold` and shown 40%.
        """
        sess = self.insert_session("outgrown-1", harness="claude")
        self.insert_ctx_turn(sess, "2026-01-10T11:50:00Z", 400_000)
        self._auto_compaction(sess, 200_069)

        row = self.cost.active_rows(self.conn, 60, self._active_now())[0]
        self.assertEqual(row["window_source"], "model", "the stale observation is discarded")
        self.assertEqual(row["ctx_pct"], 40.0, "1M via long_threshold, not 200% of a dead window")

    def test_a_window_size_only_named_in_the_model_table_can_still_be_snapped_to(self) -> None:
        """`_render_active_table` tells the reader that adding a model to the
        table resolves its window. That is only true if the table's sizes are
        also the ones an observation can snap to — a hardcoded (200K, 1M) pair
        would reject every real reading for a 272K model."""
        self.assertIn(272_000, self.cost._known_windows())
        self.assertEqual(self.cost._snap_to_known_window(270_000), 272_000)

    def test_an_out_of_range_compaction_reading_falls_through(self) -> None:
        """A reading too far from any known window is not snapped — a
        confident wrong window would be worse than the honest inference."""
        sess = self.insert_session("weird-1", harness="claude")
        self.insert_ctx_turn(sess, "2026-01-10T11:50:00Z", 120_000)
        self._auto_compaction(sess, 500_000)

        row = self.cost.active_rows(self.conn, 60, self._active_now())[0]
        self.assertEqual(row["window_source"], "model")

    # ------------------------------------------------------------------
    # capacity gauge expiry
    # ------------------------------------------------------------------

    def _capacity_turn(
        self,
        primary_reset: int | None,
        secondary_reset: int | None = None,
        ts: str = "2026-01-10T11:00:00Z",
    ) -> None:
        existing = self.conn.execute(
            "SELECT id FROM session WHERE harness = 'codex' AND session_id = 'codex-cap'"
        ).fetchone()
        sess = existing[0] if existing else self.insert_session("codex-cap", harness="codex")
        turn_raw_id = self._next_id
        self._next_id += 1
        self.conn.execute(
            "INSERT INTO turn_raw (id, session_row_id, natural_turn_id, turn_seq, is_subagent,"
            " ts, model, payload, source_path, source_line_no, collector_version)"
            " VALUES (?, ?, ?, ?, 0, ?, 'gpt-5.6-sol', '{}', '/tmp/x', ?, 1)",
            (turn_raw_id, sess, f"t{turn_raw_id}", turn_raw_id, ts, turn_raw_id),
        )
        self.conn.execute(
            "INSERT INTO turn_norm (turn_raw_id, ts, model, is_subagent, norm_version,"
            " capacity_primary_used_pct, capacity_primary_window_minutes, capacity_primary_resets_at,"
            " capacity_secondary_used_pct, capacity_secondary_window_minutes, capacity_secondary_resets_at)"
            " VALUES (?, ?, 'gpt-5.6-sol', 0, 2, 96.0, 10080, ?, ?, 300, ?)",
            (
                turn_raw_id,
                ts,
                primary_reset,
                None if secondary_reset is None else 42.0,
                secondary_reset,
            ),
        )

    @staticmethod
    def _at(epoch: int):
        from datetime import datetime as _dt
        from datetime import timezone as _tz

        return _dt.fromtimestamp(epoch, _tz.utc)

    def test_gauge_is_absent_once_its_window_has_reset(self) -> None:
        """The defect this fixes: `flow cost summary --days 7` reported a
        96.0% reading taken six days earlier that expired 97 minutes after
        the run. The capacity window is 10,080 minutes — exactly the default
        summary window — so a reading in range can describe a period with
        almost no overlap with the present. An expired gauge is absent, not
        dimmed.
        """
        self._capacity_turn(primary_reset=1_000_000)
        self.assertIsNotNone(
            self.cost.capacity_gauge(self.conn, None, now=self._at(999_999)),
            "one second before the reset it is still true",
        )
        self.assertIsNone(
            self.cost.capacity_gauge(self.conn, None, now=self._at(1_000_000)),
            "at the reset it describes nothing",
        )

    def test_a_live_secondary_outlives_an_expired_primary(self) -> None:
        """Suppressed per field, against each field's own `resets_at`.
        Primary and secondary are independent windows — neither name reliably
        means "the short one" — so a live reading must not disappear because
        an unrelated window rolled.
        """
        self._capacity_turn(primary_reset=1_000_000, secondary_reset=2_000_000)
        gauge = self.cost.capacity_gauge(self.conn, None, now=self._at(1_500_000))
        self.assertIsNotNone(gauge)
        self.assertIsNone(gauge["capacity_primary_used_pct"], "expired field is dropped")
        self.assertEqual(gauge["capacity_secondary_used_pct"], 42.0)
        line = self.cost._render_gauge_line(gauge)
        self.assertNotIn("96.0%", line)
        self.assertIn("42.0%", line)

    def test_the_gauge_line_shows_when_the_reading_resets(self) -> None:
        """`as of` says how old a reading is; only `resets at` says whether it
        still describes anything. It was stored all along and never shown."""
        self._capacity_turn(primary_reset=_FUTURE_RESET)
        gauge = self.cost.capacity_gauge(self.conn, None, now=self._at(1_000_000))
        line = self.cost._render_gauge_line(gauge)
        self.assertIn("as of 2026-01-10T11:00:00Z", line)
        self.assertIn("resets at 2100-01-01T00:00:00+00:00", line)

    def test_a_reading_sampled_late_in_its_own_window_is_labelled(self) -> None:
        """The observed shape of the defect: a sample taken six days into a
        seven-day window, unexpired and therefore shown, describing usage that
        has had almost the whole window to move since.

        Note this is *not* what the plan specified — it said to label a
        reading that predates the summary window, which cannot happen: the
        `since` filter is applied in the query, so such a reading is never
        selected. This measures the hazard that actually occurs.
        """
        from datetime import timedelta as _td

        self._capacity_turn(primary_reset=_FUTURE_RESET)  # 10080-minute window
        taken = self._at(0).replace(year=2026, month=1, day=10, hour=11)

        fresh = self.cost.capacity_gauge(self.conn, None, now=taken + _td(minutes=100))
        self.assertFalse(fresh["stale"], "a fresh sample is not labelled")

        old = self.cost.capacity_gauge(self.conn, None, now=taken + _td(minutes=6000))
        self.assertTrue(old["stale"])
        self.assertIn("more than halfway through its own window", self.cost._render_gauge_line(old))

    def test_a_live_secondary_in_an_older_row_is_not_lost(self) -> None:
        """Each field resolves from its own most-recent non-NULL row.

        Codex populates `secondary` in 7.7% of rows on the real corpus, so a
        single-row query almost always lands on one with a NULL secondary —
        making "a live secondary should not disappear" false in the common
        case rather than the edge one.
        """
        self._capacity_turn(primary_reset=_FUTURE_RESET, secondary_reset=_FUTURE_RESET, ts="2026-01-10T10:00:00Z")
        # A newer reading that carries no secondary at all.
        self._capacity_turn(primary_reset=_FUTURE_RESET, secondary_reset=None, ts="2026-01-10T12:00:00Z")

        gauge = self.cost.capacity_gauge(self.conn, None, now=self._at(1_000_000))
        self.assertEqual(gauge["capacity_primary_ts"], "2026-01-10T12:00:00Z", "newest primary")
        self.assertEqual(gauge["capacity_secondary_used_pct"], 42.0, "older but live secondary survives")
        self.assertEqual(gauge["capacity_secondary_ts"], "2026-01-10T10:00:00Z")

    def test_staleness_is_judged_per_field_against_its_own_window(self) -> None:
        """A 300-minute reading four hours old is 80% through its window and
        must be labelled, even beside a fresh 10,080-minute one. Judging both
        against the longest window would let it pass."""
        from datetime import timedelta as _td

        self._capacity_turn(
            primary_reset=_FUTURE_RESET, secondary_reset=_FUTURE_RESET, ts="2026-01-10T10:00:00Z"
        )
        taken = self._at(0).replace(year=2026, month=1, day=10, hour=10)
        gauge = self.cost.capacity_gauge(self.conn, None, now=taken + _td(hours=4))
        self.assertTrue(gauge["stale"], "the 300m field is 80% through its own window")

    def test_a_reading_with_no_reset_time_survives(self) -> None:
        """It cannot be shown to have expired, so it is not dropped."""
        self._capacity_turn(primary_reset=None)
        gauge = self.cost.capacity_gauge(self.conn, None, now=self._at(_FUTURE_RESET))
        self.assertIsNotNone(gauge)
        self.assertIn("resets at unknown", self.cost._render_gauge_line(gauge))

    # ------------------------------------------------------------------
    # flow cost trend
    # ------------------------------------------------------------------

    def _trend_turn(
        self,
        session_row_id: int,
        ts: str,
        fresh: int = 0,
        read: int = 0,
        write_1h: int = 0,
        write_5m: int = 0,
        output: int = 0,
        is_subagent: int = 0,
        model: str = "claude-sonnet-5",
    ) -> None:
        turn_raw_id = self._next_id
        self._next_id += 1
        self.conn.execute(
            "INSERT INTO turn_raw (id, session_row_id, natural_turn_id, turn_seq, is_subagent,"
            " ts, model, payload, source_path, source_line_no, collector_version)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, '{}', '/tmp/x', ?, 3)",
            (turn_raw_id, session_row_id, f"t{turn_raw_id}", turn_raw_id, is_subagent, ts, model, turn_raw_id),
        )
        self.conn.execute(
            "INSERT INTO turn_norm (turn_raw_id, ts, model, is_subagent, fresh_input_tokens,"
            " cache_read_tokens, cache_write_tokens, cache_write_1h_tokens, cache_write_5m_tokens,"
            " output_tokens, norm_version)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 2)",
            (
                turn_raw_id, ts, model, is_subagent, fresh, read,
                write_1h + write_5m, write_1h, write_5m, output,
            ),
        )

    def test_weighted_tokens_match_a_hand_computed_figure(self) -> None:
        """The headline number, checked against arithmetic done by hand from
        the weights file — an error here is invisible in every other way."""
        sess = self.insert_session("trend-1", harness="claude")
        self._trend_turn(
            sess, "2026-01-10T10:00:00Z",
            fresh=1_000, read=100_000, write_1h=10_000, write_5m=20_000, output=500,
        )
        rows = self.cost.trend_rows(self.conn, None)
        # 1,000*1.0 + 100,000*0.1 + 10,000*2.0 + 20,000*1.25 = 56,000
        # per 1,000 output over 500 output = 112,000
        self.assertEqual(rows[0]["wt_per_1k_out"], 112_000.0)

    def test_the_weights_file_is_the_source_of_truth(self) -> None:
        """A pricing change must be a data edit, which is the file's entire
        justification for existing."""
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        source = Path(tempdir.name)
        (source / "data").mkdir(parents=True)
        (source / "data" / "token_weights.json").write_text(
            json.dumps({"weights": {"cache_read": 1.0}})
        )
        sess = self.insert_session("trend-1", harness="claude")
        self._trend_turn(sess, "2026-01-10T10:00:00Z", read=100_000, output=1_000)

        baseline = self.cost.trend_rows(self.conn, None)[0]["wt_per_1k_out"]
        original_source_dir = self.cost.SOURCE_DIR
        try:
            self.cost.SOURCE_DIR = source
            edited = self.cost.trend_rows(self.conn, None)[0]["wt_per_1k_out"]
        finally:
            self.cost.SOURCE_DIR = original_source_dir

        self.assertEqual(baseline, 10_000.0, "shipped rate: 100,000 read at 0.1")
        self.assertEqual(edited, 100_000.0, "edited rate: 100,000 read at 1.0")

    def test_codex_rows_have_no_weighted_columns(self) -> None:
        """NULL, not 0 — a zero would read as "nothing weighted" rather than
        "this arithmetic does not apply here"."""
        sess = self.insert_session("codex-1", harness="codex")
        self._trend_turn(sess, "2026-01-10T10:00:00Z", fresh=1_000, output=100, model="gpt-5.6-sol")
        row = self.cost.trend_rows(self.conn, None)[0]
        self.assertEqual(row["harness"], "codex")
        self.assertEqual(row["turns"], 1, "every non-weighted column still populates")
        self.assertIsNone(row["wt_per_1k_out"])
        self.assertIsNone(row["sub_pct"])
        self.assertIsNone(row["compact_manual"])

    def test_day_and_week_buckets_agree_on_totals(self) -> None:
        """Bucketing must partition the data, not resample it."""
        sess = self.insert_session("trend-1", harness="claude")
        for day in ("12", "13", "14"):
            self._trend_turn(sess, f"2026-01-{day}T10:00:00Z", fresh=1_000, output=100)

        by_day = self.cost.trend_rows(self.conn, None, bucket="day")
        by_week = self.cost.trend_rows(self.conn, None, bucket="week")
        self.assertEqual(len(by_day), 3)
        self.assertEqual(len(by_week), 1, "all three days fall in one week")
        self.assertEqual(sum(r["turns"] for r in by_day), sum(r["turns"] for r in by_week))

    def test_an_unknown_bucket_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.cost.trend_rows(self.conn, None, bucket="fortnight")

    def test_buckets_follow_the_local_day(self) -> None:
        """An evening's work belongs to the evening, not to tomorrow.

        On the corpus this was built against, 7% of a week's turns fell on the
        wrong side of a UTC boundary — a single evening session split across
        two rows, in the view whose whole job is day-over-day comparison.
        """
        _pin_tz(self, "America/New_York")  # UTC-4 in July
        sess = self.insert_session("trend-1", harness="claude")
        # 01:30 UTC on the 11th is 21:30 on the 10th, local.
        self._trend_turn(sess, "2026-07-11T01:30:00Z", fresh=1_000, output=100)

        rows = self.cost.trend_rows(self.conn, None)
        self.assertEqual(rows[0]["bucket"], "2026-07-10")

    def test_a_week_spanning_new_year_stays_one_bucket(self) -> None:
        """`%Y-W%W` would split it: `%W` numbers weeks within a calendar year,
        so Mon 2026-12-28 → Sun 2027-01-03 becomes a 4-day `2026-W52` and a
        3-day `2027-W00`, and every volume column then compares two partial
        weeks against full ones. Keyed by the week's Monday instead.
        """
        sess = self.insert_session("trend-1", harness="claude")
        for ts in ("2026-12-28T12:00:00Z", "2026-12-31T12:00:00Z", "2027-01-02T12:00:00Z"):
            self._trend_turn(sess, ts, fresh=1_000, output=100)

        rows = self.cost.trend_rows(self.conn, None, bucket="week")
        self.assertEqual(len(rows), 1, "one calendar week is one bucket")
        self.assertEqual(rows[0]["bucket"], "2026-12-28", "keyed by the week's Monday")
        self.assertEqual(rows[0]["turns"], 3)

    def test_a_non_finite_weight_falls_back_instead_of_crashing(self) -> None:
        """`json.loads` accepts the bare literals NaN and Infinity. Both pass
        an isinstance check and then render as `nan`/`inf` in the SQL, which
        SQLite parses as identifiers — "no such column: nan" — killing the
        command that this function's docstring promises will not crash.
        """
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        source = Path(tempdir.name)
        (source / "data").mkdir()
        (source / "data" / "token_weights.json").write_text(
            '{"weights": {"cache_read": NaN, "cache_write_1h": Infinity,'
            ' "uncached_input": -5, "cache_write_5m": true}}'
        )
        sess = self.insert_session("trend-1", harness="claude")
        self._trend_turn(sess, "2026-01-10T10:00:00Z", read=100_000, output=1_000)

        original = self.cost.SOURCE_DIR
        try:
            self.cost.SOURCE_DIR = source
            weights = self.cost.token_weights()
            rows = self.cost.trend_rows(self.conn, None)
        finally:
            self.cost.SOURCE_DIR = original

        self.assertEqual(weights, self.cost._DEFAULT_WEIGHTS, "every unusable value falls back")
        self.assertEqual(rows[0]["wt_per_1k_out"], 10_000.0)

    def test_main_agent_only_columns_exclude_subagent_turns(self) -> None:
        sess = self.insert_session("trend-1", harness="claude")
        self._trend_turn(sess, "2026-01-10T10:00:00Z", fresh=100_000, output=100)
        self._trend_turn(sess, "2026-01-10T11:00:00Z", fresh=300_000, output=100, is_subagent=1)

        row = self.cost.trend_rows(self.conn, None)[0]
        self.assertEqual(row["turns"], 1, "turns counts main-agent turns only")
        self.assertEqual(row["ctx_per_turn"], 100_000, "a sidechain's context is another conversation's size")
        # sub% spans both, which is the entire point of showing it beside them.
        self.assertEqual(row["sub_pct"], 75.0)

    def test_compaction_events_are_split_by_trigger_never_summed(self) -> None:
        """manual is deliberate hygiene, auto is hitting the ceiling. One
        combined count would say nothing about either."""
        sess = self.insert_session("trend-1", harness="claude")
        self._trend_turn(sess, "2026-01-10T10:00:00Z", fresh=1_000, output=100)
        for trigger, pre in (("manual", 300_000), ("manual", 500_000), ("auto", 900_000)):
            self.conn.execute(
                "INSERT INTO agent_activity_raw (session_row_id, ts, kind, payload,"
                " source_path, source_line_no, collector_version)"
                " VALUES (?, '2026-01-10T12:00:00Z', 'compact_boundary', ?, '/tmp/x', ?, 3)",
                (sess, json.dumps({"compactMetadata": {"trigger": trigger, "preTokens": pre}}), self._next_id),
            )
            self._next_id += 1

        row = self.cost.trend_rows(self.conn, None)[0]
        self.assertEqual(row["compact_manual"], 2)
        self.assertEqual(row["compact_auto"], 1)
        self.assertEqual(row["median_pre_manual"], 400_000, "median of the manual cuts only")

    def test_a_compaction_in_a_bucket_with_no_turns_still_appears(self) -> None:
        """A session that compacts just after midnight and then ends
        contributes an event to that day and no turns to it. Building buckets
        from `turn_norm` alone would drop the event silently — the exact
        failure this view exists to make visible.
        """
        sess = self.insert_session("trend-1", harness="claude")
        self._trend_turn(sess, "2026-01-10T23:59:00Z", fresh=1_000, output=100)
        self.conn.execute(
            "INSERT INTO agent_activity_raw (session_row_id, ts, kind, payload,"
            " source_path, source_line_no, collector_version)"
            " VALUES (?, '2026-01-11T00:01:00Z', 'compact_boundary', ?, '/tmp/x', ?, 3)",
            (sess, json.dumps({"compactMetadata": {"trigger": "auto", "preTokens": 900_000}}), self._next_id),
        )
        self._next_id += 1

        rows = {r["bucket"]: r for r in self.cost.trend_rows(self.conn, None)}
        self.assertIn("2026-01-11", rows, "the event's own bucket must exist")
        self.assertEqual(rows["2026-01-11"]["compact_auto"], 1)
        self.assertEqual(rows["2026-01-11"]["turns"], 0)
        self.assertIsNone(rows["2026-01-11"]["ctx_per_turn"], "no turns to average is not zero context")

    def test_coverage_floor_labels_a_window_reaching_before_the_data(self) -> None:
        """Absent buckets and empty buckets are different facts. Truncating
        silently would make the earliest visible bucket look like the start of
        the record, which turns a coverage gap into a false trend."""
        sess = self.insert_session("trend-1", harness="claude")
        self._trend_turn(sess, "2026-05-21T10:00:00Z", fresh=1_000, output=100)

        floor = self.cost.coverage_floor(self.conn)
        self.assertEqual(floor["claude"], "2026-05-21T10:00:00Z")
        notes = self.cost._coverage_notes(floor, "2026-05-17T00:00:00Z", None)
        self.assertEqual(len(notes), 1)
        self.assertIn("coverage begins 2026-05-21", notes[0])
        self.assertIn("absent from the store, not empty", notes[0])
        self.assertEqual(
            self.cost._coverage_notes(floor, "2026-05-22T00:00:00Z", None),
            [],
            "a window inside coverage needs no label",
        )


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

    # --- `--porcelain=v2` parsing -------------------------------------------
    #
    # v2 was adopted to retire the `config --get remote.origin.url` subprocess
    # from the per-prompt hook: its `--branch` header names the upstream
    # directly. But its entry lines are nothing like v1's fixed-width `XY `
    # prefix, and the count these produce is the number the whole advisory is
    # built on — so every line type gets a case.

    def test_every_v2_entry_type_yields_exactly_one_path(self) -> None:
        """Ordinary, rename, unmerged, and untracked entries, with spaces in
        the paths. A fixed-offset slice of the kind v1 allowed would return
        field soup for three of these four."""
        branch, upstream, unpushed, dirty = self.overlay._parse_status_v2(
            "# branch.oid abc123\n"
            "# branch.head main\n"
            "1 .M N... 100644 100644 100644 aaa bbb mod file.md\n"
            "2 R. N... 100644 100644 100644 aaa bbb R100 new name.md\told name.md\n"
            "u UU N... 100644 100644 100644 100644 aaa bbb ccc conflicted file.md\n"
            "? un tracked.md\n"
        )
        self.assertEqual(branch, "main")
        self.assertIsNone(upstream)
        self.assertIsNone(unpushed)
        self.assertEqual(
            dirty,
            ["mod file.md", "new name.md", "conflicted file.md", "un tracked.md"],
            "one path per entry, spaces intact, rename reported at its new path",
        )

    def test_v2_header_reads_upstream_and_ahead_count(self) -> None:
        branch, upstream, unpushed, dirty = self.overlay._parse_status_v2(
            "# branch.oid abc123\n"
            "# branch.head main\n"
            "# branch.upstream origin/main\n"
            "# branch.ab +2 -1\n"
        )
        self.assertEqual((branch, upstream, unpushed), ("main", "origin/main", 2))
        self.assertEqual(dirty, [])

    def test_v2_upstream_present_and_level_is_zero_not_none(self) -> None:
        """None means "nowhere to push" everywhere downstream. An upstream
        that exists and is level must not read as its absence."""
        _, upstream, unpushed, _ = self.overlay._parse_status_v2(
            "# branch.head main\n# branch.upstream origin/main\n# branch.ab +0 -0\n"
        )
        self.assertEqual(upstream, "origin/main")
        self.assertEqual(unpushed, 0)

    def test_v2_detached_head_is_not_a_branch_named_head(self) -> None:
        branch, _, _, _ = self.overlay._parse_status_v2("# branch.oid abc\n# branch.head (detached)\n")
        self.assertIsNone(branch)

    def test_unborn_branch_is_readable_and_still_counts_its_files(self) -> None:
        """A freshly initialized overlay: git prints `(initial)` for the oid
        and `rev-parse HEAD` fails outright, so this state has to come from
        the status header or not at all."""
        d = self.dir / "user"
        d.mkdir()
        (d / "flow.toml").write_text("# overlay\n")
        self._git(d, "init", "-b", "main")
        status = self.overlay.overlay_vcs_status(d)
        self.assertTrue(status["tracked"])
        self.assertFalse(status["error"])
        self.assertEqual(status["branch"], "main")
        self.assertIsNone(status["upstream"])
        self.assertEqual(status["dirty"], ["flow.toml"])

    def test_real_repo_reports_a_spaced_path_verbatim(self) -> None:
        """The parser above is fed literal strings; this proves the shape it
        expects is the shape git actually emits. Asserting the path and not
        just the count: a mangled path is still one entry, so a count
        assertion alone survives a fixed-offset slice."""
        d = self._repo_with_content()
        (d / "two words.md").write_text("x\n")
        status = self.overlay.overlay_vcs_status(d)
        self.assertEqual(status["dirty"], ["two words.md"])

    def test_real_git_rename_reports_the_new_path(self) -> None:
        """`2` entries have nine fields before the path and then a second,
        tab-separated path. The literal-string test above encodes that belief;
        this one checks it against git, because a field count that is off by
        one either mangles the path or drops the entry, and both are silent."""
        d = self._repo_with_content()
        (d / "before.md").write_text("x\n")
        self._git(d, "add", ".")
        self._git(d, "commit", "-m", "add")
        self._git(d, "mv", "before.md", "after two.md")
        status = self.overlay.overlay_vcs_status(d)
        self.assertEqual(status["dirty"], ["after two.md"])

    def test_real_git_merge_conflict_reports_one_path(self) -> None:
        """`u` entries have ten fields before the path — the longest of the
        four shapes, and the one nothing else in the suite exercises."""
        d = self._repo_with_content()
        (d / "c.md").write_text("base\n")
        self._git(d, "add", ".")
        self._git(d, "commit", "-m", "base")
        self._git(d, "checkout", "-b", "other")
        (d / "c.md").write_text("other\n")
        self._git(d, "commit", "-am", "other")
        self._git(d, "checkout", "main")
        (d / "c.md").write_text("main\n")
        self._git(d, "commit", "-am", "main")
        subprocess.run(["git", "merge", "other"], cwd=d, capture_output=True)

        status = self.overlay.overlay_vcs_status(d)
        self.assertEqual(status["dirty"], ["c.md"], "a conflicted file is one entry, not field soup")

    def test_upstream_set_with_no_ahead_behind_line_reads_as_level(self) -> None:
        """`branch.ab` accompanies `branch.upstream` in practice, but the
        contract downstream is that None means untracked. An upstream with no
        countable divergence must not read as its absence."""
        _, upstream, unpushed, _ = self.overlay._parse_status_v2(
            "# branch.head main\n# branch.upstream origin/main\n"
        )
        self.assertEqual(upstream, "origin/main")
        self.assertEqual(unpushed, 0, "an upstream exists, so this is level, not untracked")

    # --- `quick` -------------------------------------------------------------

    def test_quick_skips_the_remote_lookup_and_full_mode_does_not(self) -> None:
        """The whole point of `quick`: one fewer subprocess per prompt. The
        full status is what `doctor` and `setup` read, and `setup` compares
        `remote` against the URL it was given."""
        remote = self.dir / "remote.git"
        remote.mkdir()
        self._git(remote, "init", "--bare", "-b", "main")
        d = self._repo_with_content()
        self._git(d, "remote", "add", "origin", str(remote))
        self._git(d, "push", "-u", "origin", "main")

        full = self.overlay.overlay_vcs_status(d)
        self.assertEqual(full["remote"], str(remote))

        quick = self.overlay.overlay_vcs_status(d, quick=True)
        self.assertIsNone(quick["remote"], "quick must not ask; None here means unasked")
        self.assertEqual(quick["upstream"], "origin/main", "and the upstream covers what the nudge needs")
        self.assertEqual(quick["unpushed"], 0)

    def test_quick_status_never_reports_no_remote(self) -> None:
        """`format_overlay_vcs` reads `remote`, which a quick status never
        populates. Without the `quick` flag in the dict it would report "no
        remote" for a repo that has one — a false diagnostic, produced
        silently, by a caller that did nothing obviously wrong."""
        remote = self.dir / "remote.git"
        remote.mkdir()
        self._git(remote, "init", "--bare", "-b", "main")
        d = self._repo_with_content()
        self._git(d, "remote", "add", "origin", str(remote))
        self._git(d, "push", "-u", "origin", "main")

        line = self.overlay.format_overlay_vcs(self.overlay.overlay_vcs_status(d, quick=True))
        self.assertNotIn("no remote", line)
        self.assertIn("clean", line)

    def test_remote_without_an_upstream_is_no_upstream_not_no_remote(self) -> None:
        """`git push origin main` without `-u` is what `setup`'s init-in-place
        path leaves behind: the content is on the remote and the branch tracks
        nothing. `doctor` must keep those two apart — the whole reason the full
        status still pays for the remote lookup."""
        remote = self.dir / "remote.git"
        remote.mkdir()
        self._git(remote, "init", "--bare", "-b", "main")
        d = self._repo_with_content()
        self._git(d, "remote", "add", "origin", str(remote))
        self._git(d, "push", "origin", "main")

        status = self.overlay.overlay_vcs_status(d)
        self.assertEqual(status["remote"], str(remote), "a remote is configured")
        self.assertIsNone(status["upstream"], "but nothing tracks the branch")
        line = self.overlay.format_overlay_vcs(status)
        self.assertIn("no upstream", line)
        self.assertNotIn("no remote", line)

    def test_quick_status_costs_one_fewer_git_call(self) -> None:
        """The saving, asserted rather than assumed — a `quick` that still
        spawned `config` would pass every other test in this class."""
        import unittest.mock

        d = self._repo_with_content()
        real = self.overlay._git

        def counted(calls):
            def wrapper(cwd, *args):
                calls.append(args[0])
                return real(cwd, *args)

            return wrapper

        full_calls, quick_calls = [], []
        with unittest.mock.patch.object(self.overlay, "_git", counted(full_calls)):
            self.overlay.overlay_vcs_status(d)
        with unittest.mock.patch.object(self.overlay, "_git", counted(quick_calls)):
            self.overlay.overlay_vcs_status(d, quick=True)

        self.assertIn("config", full_calls)
        self.assertNotIn("config", quick_calls)
        self.assertEqual(len(quick_calls), len(full_calls) - 1)


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

    def _overlay_repo(self, with_remote: bool = True, set_upstream: bool = True) -> Path:
        """A tracked overlay. `with_remote` is on by default because a repo
        with nowhere to push is itself a nudge-worthy state, so a test that
        wants "nothing to report" has to opt into being backed up.

        `set_upstream=False` pushes without `-u`: the content reaches the
        remote and the branch tracks nothing. That is the state `setup`'s
        init-in-place path produces, so anything the advisory says about it
        has to be true of a repo that IS backed up."""
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
            self._git(d, "push", *(["-u"] if set_upstream else []), "origin", "main")
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
        self.assertIn("no upstream branch", out)

    def test_the_standing_line_does_not_claim_the_content_is_only_local(self) -> None:
        """The hook reads `upstream`, which cannot tell "never pushed" from
        "pushed without -u". Since it fires for both, it must not assert the
        stronger of the two: this repo's content IS on the remote."""
        d = self._overlay_repo(set_upstream=False)
        _, out = self._run_hook({"hook_event_name": "UserPromptSubmit"}, d)
        self.assertIn("no upstream branch", out, "an untracked branch is still worth one note")
        self.assertNotIn(
            "exists off this machine",
            out,
            "this content does exist off this machine — the remote has it",
        )

    def test_the_standing_line_does_not_refer_to_changes_that_do_not_exist(self) -> None:
        """Nothing is dirty and nothing is ahead in this state, so the
        commit-and-push clause would point at work that is not there. It also
        must not tell a session to set an upstream, because doing that pushes
        the whole branch — the hazard the conditional wording exists for."""
        d = self._overlay_repo(with_remote=False)
        _, out = self._run_hook({"hook_event_name": "UserPromptSubmit"}, d)
        self.assertNotIn("those changes", out)
        self.assertNotIn("commit and push", out.lower())
        self.assertIn("leave it to the person who owns the repo", out)

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
        self.assertIn("no upstream branch", first)
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
        self.assertIn("no upstream branch", standing)

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


class CliReferenceDocTests(unittest.TestCase):
    """`docs/cli-reference.md` against the CLI it documents.

    That doc fell two releases behind — eight of twelve subcommands, with the
    whole usage-tracking and overlay surfaces missing — because nothing
    checked it. A reference is the one kind of doc where being quietly wrong
    is worse than being absent: a reader who finds no section knows to look
    elsewhere, and a reader who finds a wrong default does not.

    So this asserts the parts a machine can settle — command names, flags,
    defaults, coverage, and the output literals the doc quotes — and leaves
    prose to review. It lives in `tests/` rather than `scripts/` for two
    reasons: it runs without anyone remembering to run it, which is the whole
    point, and `tests/` is excluded from the release roster (see
    `paths.RELEASE_EXCLUDE_TOP_LEVEL`), so a dev-only check does not ship to
    people installing flow.
    """

    DOC = REPO_ROOT / "docs" / "cli-reference.md"

    # Below these, assume the parse broke rather than that the doc shrank.
    # A regex that silently stops matching turns every assertion below into a
    # loop over nothing, which reports success.
    MIN_SECTIONS = 20
    MIN_FLAGS = 15
    MIN_DEFAULTS = 4

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = cls.DOC.read_text()
        cls._help_cache: dict[tuple[str, ...], str] = {}

        # `### `flow cost sessions`` -> (("cost", "sessions"), body). Flags and
        # `<placeholders>` are dropped from the invocation but kept for the
        # flag check, since headings like `flow install --release` name a real
        # flag that ought to be verified too.
        cls.sections = []
        parts_iter = re.split(r"^### `flow ([^`]+)`$", cls.text, flags=re.M)
        for heading, body in zip(parts_iter[1::2], parts_iter[2::2]):
            words = heading.split()
            cmd = tuple(w for w in words if not w.startswith(("-", "<")))
            if not cmd:
                continue
            # The last section's body otherwise runs on into `## Typical
            # Sequences` and `## Failure Modes`, whose flag mentions belong to
            # other commands entirely.
            body = re.split(r"^## ", body, flags=re.M)[0]
            heading_flags = {w for w in words if w.startswith("--")}
            cls.sections.append((cmd, heading, body, heading_flags))

    def _help(self, cmd: tuple[str, ...]) -> str:
        """`--help` for one subcommand, cached across tests in this class.

        Uses `_clean_env` because Python 3.14's argparse emits ANSI colour
        when FORCE_COLOR is set, which would break a substring match on
        `default: 7` in a way that looks like a documentation error.
        """
        if cmd not in self._help_cache:
            result = subprocess.run(
                [sys.executable, str(FLOW_CLI), *cmd, "--help"],
                text=True,
                capture_output=True,
                env=_clean_env(),
            )
            self._help_cache[cmd] = result.stdout if result.returncode == 0 else ""
        return self._help_cache[cmd]

    def test_the_doc_parse_found_something_to_check(self) -> None:
        """Guard on the guards. Every test below iterates over what the parse
        produced, so a broken regex would make all of them vacuously pass."""
        self.assertGreaterEqual(len(self.sections), self.MIN_SECTIONS)

    def test_every_documented_command_resolves(self) -> None:
        for cmd, heading, _, _ in self.sections:
            with self.subTest(command=heading):
                self.assertTrue(
                    self._help(cmd),
                    f"the doc has a section for `flow {heading}`, "
                    f"but `flow {' '.join(cmd)} --help` does not succeed",
                )

    def _rejects_flag(self, cmd: tuple[str, ...], flag: str) -> bool:
        """Does the parser actually reject `flag` for this subcommand?

        `--help` is the cheap oracle for "is this flag real," but it is the
        wrong one for a flag registered with `argparse.SUPPRESS` — a
        deliberately hidden alias is accepted and absent from help at the
        same time, and a help-only check calls that a documentation error.

        So this asks argparse directly, and does it without running anything:
        appending a flag that certainly does not exist guarantees a parse
        error before dispatch, and argparse names *every* unrecognized
        argument in that one message. A flag missing from the list was
        accepted; a flag present in it was not. Nothing is harvested, no
        store is created, and the real HOME is never touched.
        """
        result = subprocess.run(
            [sys.executable, str(FLOW_CLI), *cmd, flag, "--zz-not-a-real-flag"],
            text=True,
            capture_output=True,
            env=_clean_env(),
        )
        unrecognized = re.search(r"unrecognized arguments: (.*)", result.stderr + result.stdout)
        if unrecognized is None:
            # The probe flag should always produce this error. If it didn't,
            # the assumption behind this check no longer holds — say so rather
            # than silently reporting "accepted."
            self.fail(
                f"probing `flow {' '.join(cmd)} {flag}` did not produce an "
                f"argparse error; this check's mechanism has broken"
            )
        return flag in unrecognized.group(1).split()

    def test_every_documented_flag_is_accepted(self) -> None:
        checked = 0
        for cmd, heading, body, heading_flags in self.sections:
            help_text = self._help(cmd)
            if not help_text:
                continue  # already reported by the resolution test
            flags = set(re.findall(r"`(--[a-z-]+)", body)) | heading_flags
            for flag in sorted(flags):
                checked += 1
                with self.subTest(command=heading, flag=flag):
                    if flag in help_text:
                        continue
                    # Absent from help — either a hidden alias the doc is
                    # right to mention, or a flag that does not exist.
                    self.assertFalse(
                        self._rejects_flag(cmd, flag),
                        f"the doc names {flag} under `flow {heading}`, "
                        f"but that subcommand does not accept it",
                    )
        self.assertGreaterEqual(checked, self.MIN_FLAGS, "flag extraction found almost nothing")

    def test_every_documented_default_matches_the_cli(self) -> None:
        """Defaults are read out of the DOC and checked against `--help`.

        An earlier version of this check compared `--help` against literals
        hardcoded in the test, which meant editing the doc could not fail it —
        an assertion that looked like coverage and was not.
        """
        checked = 0
        for cmd, heading, body, _ in self.sections:
            help_text = self._help(cmd)
            if not help_text:
                continue
            # `- `--limit N` — cap the sessions shown (default: 20; `0` = ...)`
            for flag, value in re.findall(r"`(--[a-z-]+)[^`]*`[^\n]*?\(default: ([^;)]+)", body):
                checked += 1
                with self.subTest(command=heading, flag=flag):
                    self.assertIn(
                        f"default: {value}",
                        help_text,
                        f"the doc says `flow {heading}` {flag} defaults to {value!r}, "
                        f"and the CLI disagrees",
                    )
        self.assertGreaterEqual(checked, self.MIN_DEFAULTS, "default extraction found almost nothing")

    def test_every_subcommand_appears_in_the_reference(self) -> None:
        """The failure this class exists for: a shipped subcommand nobody
        documented."""
        root_help = subprocess.run(
            [sys.executable, str(FLOW_CLI), "--help"],
            text=True, capture_output=True, env=_clean_env(),
        ).stdout
        # Hyphens included: `plugin-usage` was the first subcommand to carry
        # one, and a pattern that silently failed to match turned this guard
        # into an assertion about its own regex rather than about the CLI.
        match = re.search(r"\{([a-z,-]+)\}", root_help)
        self.assertIsNotNone(match, "could not read the subcommand list out of `flow --help`")
        subcommands = match.group(1).split(",")
        self.assertGreater(len(subcommands), 5, "suspiciously few subcommands parsed")
        documented = {cmd[0] for cmd, _, _, _ in self.sections}
        for name in subcommands:
            with self.subTest(subcommand=name):
                self.assertIn(
                    name,
                    documented,
                    f"`flow {name}` exists but has no `### `flow {name} ...`` section",
                )

    def test_quoted_empty_store_output_is_what_the_cli_prints(self) -> None:
        """The doc quotes two literals as searchable symptoms in Failure
        Modes. A reader greps for them, so they have to be exact."""
        with tempfile.TemporaryDirectory() as scratch:
            home = Path(scratch)
            env = _clean_env(home)
            for cmd, literal in (
                (["cost", "summary"], "(no data in range)"),
                (["cost", "active"], "(no active sessions in range)"),
            ):
                with self.subTest(command=" ".join(cmd)):
                    self.assertIn(literal, self.text, "the doc no longer quotes this literal")
                    result = subprocess.run(
                        [sys.executable, str(FLOW_CLI), *cmd],
                        text=True, capture_output=True, env=env,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn(literal, result.stdout)


class BaselineTests(unittest.TestCase):
    """Direct tests of cli/baseline.py against a constructed store.

    Seeded straight into `turn_raw`/`turn_norm` rather than replayed through
    the collector: every test here turns on an exact `turn_seq`,
    `source_line_no`, or `cache_read_tokens`, and a transcript fixture cannot
    pin those without also encoding collector behaviour that is not what is
    under test.
    """

    # The measured floor series from the real corpus, minus its one genuine
    # move. Every remaining step is sampling wander: +4.8%, -2.5%, +9.3%,
    # +0.5%, -3.4%, 0.0%. Used verbatim rather than as invented "noisy
    # numbers" so the negative test is traceable to observed data.
    REAL_NOISE_SERIES = [20131, 21094, 20568, 22489, 22595, 21830, 21830]

    # Mondays, so each timestamp lands in its own week bucket under the
    # Monday-keyed expression `cost.trend` already uses.
    WEEKS = [
        "2026-01-05", "2026-01-12", "2026-01-19", "2026-01-26",
        "2026-02-02", "2026-02-09", "2026-02-16", "2026-02-23",
    ]

    def setUp(self) -> None:
        import sqlite3

        _pin_tz(self)
        repo_cli = REPO_ROOT / "cli"
        if str(repo_cli) not in sys.path:
            sys.path.insert(0, str(repo_cli))
            self._added_cli_path = True
        else:
            self._added_cli_path = False
        import usage_store
        import baseline

        self.baseline = baseline
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row
        for _version, _description, sql in usage_store.MIGRATIONS:
            self.conn.executescript(sql)
        # Seeded explicitly: MIGRATIONS create harness_capability but leave it
        # empty, and rule 3 is gated on it.
        self.conn.executemany(
            "INSERT INTO harness_capability (harness, field, supported) VALUES (?, ?, ?)",
            [("claude", "compact_boundary", 1), ("codex", "compact_boundary", 0)],
        )
        self._next_id = 1

    def tearDown(self) -> None:
        self.conn.close()
        if self._added_cli_path:
            sys.path.remove(str(REPO_ROOT / "cli"))
        for name in ("usage_store", "baseline", "cost"):
            sys.modules.pop(name, None)

    def seed(
        self,
        cache_read: int,
        week: str = "2026-01-05",
        harness: str = "claude",
        cwd: str | None = "/w",
        turn_seq: int | None = None,
        source_line_no: int = 5,
        is_subagent: int = 0,
        session_row_id: int | None = None,
    ) -> int:
        """One turn, with every field the population rules read exposed."""
        turn_raw_id = self._next_id
        self._next_id += 1
        if session_row_id is None:
            cur = self.conn.execute(
                "INSERT INTO session (harness, session_id, cwd, source_path)"
                " VALUES (?, ?, ?, ?)",
                (harness, f"s{turn_raw_id}", cwd, f"/tmp/s{turn_raw_id}.jsonl"),
            )
            session_row_id = cur.lastrowid
        ts = f"{week}T12:00:00Z"
        self.conn.execute(
            "INSERT INTO turn_raw"
            " (id, session_row_id, natural_turn_id, turn_seq, is_subagent, ts, model,"
            "  payload, source_path, source_line_no, collector_version)"
            " VALUES (?, ?, ?, ?, ?, ?, 'm', '{}', '/tmp/x', ?, 1)",
            (
                turn_raw_id, session_row_id, f"t{turn_raw_id}",
                turn_seq if turn_seq is not None else source_line_no,
                is_subagent, ts, source_line_no,
            ),
        )
        self.conn.execute(
            "INSERT INTO turn_norm"
            " (turn_raw_id, ts, model, is_subagent, fresh_input_tokens,"
            "  cache_read_tokens, cache_write_tokens, output_tokens, norm_version)"
            " VALUES (?, ?, 'm', ?, 0, ?, 0, 0, 1)",
            (turn_raw_id, ts, is_subagent, cache_read),
        )
        return session_row_id

    def seed_week(self, week: str, value: int, count: int = 5, **kw) -> None:
        for _ in range(count):
            self.seed(value, week=week, **kw)

    def compact_boundary(self, session_row_id: int, ts: str) -> None:
        self.conn.execute(
            "INSERT INTO agent_activity_raw"
            " (session_row_id, ts, kind, payload, source_path, source_line_no,"
            "  collector_version)"
            " VALUES (?, ?, 'compact_boundary', '{}', '/tmp/x', 1, 1)",
            (session_row_id, ts),
        )

    def observations(self, harness: str = "claude") -> list:
        return self.baseline.qualifying_observations(self.conn, harness)

    # ------------------------------------------------------------------
    # estimator
    # ------------------------------------------------------------------

    def test_floor_is_low_quantile_not_median(self) -> None:
        """The floor is the leanest prefix observed, not the typical one.

        Prefix readings are repeated plateaus, so a mid-range quantile tracks
        the mix between configurations rather than the floor itself. This
        fixture is deliberately bimodal, the shape that made p25 misreport a
        35% spike on real data.
        """
        for value in (20000, 20000, 30000, 30000, 30000):
            self.seed(value)
        rows = self.baseline.weekly_floor(self.observations())
        self.assertEqual(rows[0]["floor"], 20000)
        self.assertEqual(rows[0]["n"], 5)

    def test_percentile_is_nearest_rank_and_returns_a_real_observation(self) -> None:
        self.assertEqual(self.baseline._percentile([10, 20, 30, 40], 0.10), 10)
        self.assertEqual(self.baseline._percentile([7], 0.10), 7)
        self.assertIsNone(self.baseline._percentile([], 0.10))

    # ------------------------------------------------------------------
    # population rules
    # ------------------------------------------------------------------

    def test_rule1_takes_first_non_subagent_turn(self) -> None:
        """A subagent turn earlier in the file must not become the first turn."""
        sid = self.seed(9999, turn_seq=3, source_line_no=3, is_subagent=1)
        self.seed(21000, turn_seq=9, source_line_no=9, session_row_id=sid)
        self.seed(55555, turn_seq=40, source_line_no=40, session_row_id=sid)
        rows = self.observations()
        self.assertEqual([r["cache_read_tokens"] for r in rows], [21000])

    def test_rule2_excludes_collector_attached_mid_file(self) -> None:
        """A high first line number means the earliest row held is mid-conversation."""
        self.seed(21000, source_line_no=4000)
        self.assertEqual(self.observations(), [])

    def test_rule3_excludes_compaction_at_or_before_the_turn(self) -> None:
        sid = self.seed(21000, week="2026-01-05")
        self.compact_boundary(sid, "2026-01-05T11:00:00Z")
        self.assertEqual(self.observations(), [])

    def test_rule3_admits_compaction_after_the_turn(self) -> None:
        """The rule is "at or before", not "anywhere in the session"."""
        sid = self.seed(21000, week="2026-01-05")
        self.compact_boundary(sid, "2026-01-05T13:00:00Z")
        self.assertEqual(len(self.observations()), 1)

    def test_rule3_not_applied_when_harness_cannot_report_compaction(self) -> None:
        """Codex records no boundary; the row must not be silently filtered."""
        sid = self.seed(21000, harness="codex")
        self.compact_boundary(sid, "2026-01-05T11:00:00Z")
        self.assertEqual(len(self.observations("codex")), 1)

    def test_rule4_excludes_cache_miss_rather_than_reporting_zero(self) -> None:
        """cache_read=0 is a miss carrying no reading, not an empty prefix."""
        self.seed(0)
        rows = self.baseline.weekly_floor(self.observations())
        self.assertEqual(rows, [])

    # ------------------------------------------------------------------
    # changepoints
    # ------------------------------------------------------------------

    def test_changepoint_ignores_real_world_noise(self) -> None:
        """THE load-bearing test.

        These are measured values from the real corpus with its one genuine
        move removed. If a future change loosens either threshold, one of
        these steps starts firing and this fails. Asserting on the constants
        as well means loosening them without noticing breaks the suite twice.
        """
        for week, value in zip(self.WEEKS, self.REAL_NOISE_SERIES):
            self.seed_week(week, value)
        weekly = self.baseline.weekly_floor(self.observations())
        self.assertEqual(
            self.baseline.detect_changepoints(weekly),
            [],
            "measured week-to-week wander must not register as a change",
        )
        limits = self.baseline.thresholds()
        self.assertGreaterEqual(limits["min_pct"], 0.10, "largest observed wander is 9.3%")
        self.assertGreaterEqual(limits["min_abs"], 2000, "largest observed wander is 1,921 tokens")

    def test_changepoint_detects_a_real_move(self) -> None:
        self.seed_week(self.WEEKS[0], 21000)
        self.seed_week(self.WEEKS[1], 13200)
        weekly = self.baseline.weekly_floor(self.observations())
        history = self.baseline.detect_changepoints(weekly)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["delta"], -7800)
        self.assertEqual(history[0]["previous"], 21000)
        self.assertEqual(history[0]["floor"], 13200)

    def test_changepoint_requires_both_thresholds(self) -> None:
        """A big percentage on a tiny floor is not a finding."""
        self.seed_week(self.WEEKS[0], 3000)
        self.seed_week(self.WEEKS[1], 5000)  # +66% but only +2,000 tokens
        weekly = self.baseline.weekly_floor(self.observations())
        self.assertEqual(self.baseline.detect_changepoints(weekly), [])

    def test_thin_bucket_does_not_manufacture_a_change(self) -> None:
        """A blanked week is skipped, not treated as a drop to zero."""
        self.seed_week(self.WEEKS[0], 21000)
        self.seed_week(self.WEEKS[1], 21000, count=2)  # below min_n
        self.seed_week(self.WEEKS[2], 21000)
        weekly = self.baseline.weekly_floor(self.observations())
        self.assertIsNone(weekly[1]["floor"])
        self.assertEqual(self.baseline.detect_changepoints(weekly), [])

    # ------------------------------------------------------------------
    # reporting contract
    # ------------------------------------------------------------------

    def test_insufficient_sample_blanks_rather_than_reporting_a_number(self) -> None:
        self.seed_week(self.WEEKS[0], 21000, count=2)
        rows = self.baseline.weekly_floor(self.observations())
        self.assertEqual(rows[0]["n"], 2)
        self.assertIsNone(rows[0]["floor"], "a thin week must not report a quantile")

    def test_empty_population_reports_no_floor_rather_than_a_number(self) -> None:
        payload = self.baseline.baseline_rows(self.conn, "claude")
        self.assertEqual(payload["n"], 0)
        self.assertIsNone(payload["current_floor"])
        self.assertEqual(payload["history"], [])

    def test_by_cwd_never_compares_one_project_to_another(self) -> None:
        """Regression: two directories in one week are not a time series.

        Before the fix, weekly_floor's (bucket, cwd) rows went straight into
        detect_changepoints, which read consecutive rows as consecutive
        weeks. Two projects in the same week whose floors differ enough then
        rendered as a dated change in which nothing had changed.
        """
        self.seed_week(self.WEEKS[0], 18000, cwd="/a")
        self.seed_week(self.WEEKS[0], 26000, cwd="/b")
        payload = self.baseline.baseline_rows(self.conn, "claude", by_cwd=True)
        self.assertEqual(len(payload["series"]), 2)
        for entry in payload["series"]:
            self.assertEqual(
                entry["history"], [], f"{entry['cwd']} has one week and cannot have a change"
            )

    def test_by_cwd_headline_names_the_directory(self) -> None:
        """A directory-specific floor must not render under an unlabelled heading."""
        self.seed_week(self.WEEKS[0], 18000, cwd="/a")
        self.seed_week(self.WEEKS[0], 26000, cwd="/b")
        payload = self.baseline.baseline_rows(self.conn, "claude", by_cwd=True)
        self.assertIsNone(payload["current_floor"], "no single floor exists when split")
        rendered = self.baseline.render_baseline_table(payload)
        self.assertIn("/a", rendered)
        self.assertIn("/b", rendered)

    def test_changepoint_records_both_endpoints_and_flags_gaps(self) -> None:
        """A change between non-adjacent weeks must not be dated to the later one."""
        self.seed_week(self.WEEKS[0], 21000)
        self.seed_week(self.WEEKS[3], 13200)  # three weeks later, nothing between
        weekly = self.baseline.weekly_floor(self.observations())
        change = self.baseline.detect_changepoints(weekly)[0]
        self.assertEqual(change["previous_bucket"], self.WEEKS[0])
        self.assertEqual(change["date"], self.WEEKS[3])
        self.assertFalse(change["adjacent"])

    def test_consecutive_weeks_are_marked_adjacent(self) -> None:
        self.seed_week(self.WEEKS[0], 21000)
        self.seed_week(self.WEEKS[1], 13200)
        change = self.baseline.detect_changepoints(
            self.baseline.weekly_floor(self.observations())
        )[0]
        self.assertTrue(change["adjacent"])

    def test_since_filters_without_disturbing_the_compaction_clause(self) -> None:
        """Both optional clauses bind parameters; order must survive using both.

        The failure this catches is silent: swap the two appends and the
        compaction filter compares kind against a timestamp while the window
        compares a timestamp against 'compact_boundary'. Both stop matching,
        nothing errors, and every other test still passes.
        """
        old = self.seed(21000, week="2026-01-05")
        self.compact_boundary(old, "2026-01-05T11:00:00Z")
        self.seed(21000, week="2026-02-09")
        rows = self.baseline.qualifying_observations(
            self.conn, "claude", since="2026-02-01T00:00:00Z"
        )
        self.assertEqual(len(rows), 1, "window keeps only the later session")
        self.assertEqual(rows[0]["bucket"], "2026-02-09")
        unwindowed = self.baseline.qualifying_observations(self.conn, "claude")
        self.assertEqual(
            len(unwindowed), 1, "and the compacted session is still excluded without a window"
        )

    def test_percentile_moves_off_the_minimum_once_the_sample_allows(self) -> None:
        """p10 only differs from min above ten observations; pin that it does.

        Every other fixture here has p10 == min, so a `rank = 1` mutant would
        otherwise pass the whole suite.
        """
        values = [100] + [200] * 10  # n=11, ceil(0.10*11) = 2
        self.assertEqual(self.baseline._percentile(values, 0.10), 200)
        self.assertEqual(self.baseline._percentile(values[:10], 0.10), 100)

    def test_thresholds_reject_zero_and_boolean_values(self) -> None:
        """min_pct=0 would make every bucket a changepoint; bool is an int."""
        original = self.baseline._data_file
        try:
            self.baseline._data_file = lambda name: {"min_pct": 0, "min_abs": True, "min_n": -1}
            resolved = self.baseline.thresholds()
        finally:
            self.baseline._data_file = original
        self.assertEqual(resolved, self.baseline.DEFAULT_THRESHOLDS)

    def test_thresholds_fall_back_only_for_the_bad_key(self) -> None:
        original = self.baseline._data_file
        try:
            self.baseline._data_file = lambda name: {"min_pct": 0.4, "min_abs": "nope"}
            resolved = self.baseline.thresholds()
        finally:
            self.baseline._data_file = original
        self.assertEqual(resolved["min_pct"], 0.4, "the good key is honoured")
        self.assertEqual(
            resolved["min_abs"],
            self.baseline.DEFAULT_THRESHOLDS["min_abs"],
            "the bad key falls back on its own",
        )

    def test_capability_without_coverage_does_not_claim_a_filter_ran(self) -> None:
        """A store predating boundary capture has the capability and no rows."""
        self.seed_week(self.WEEKS[0], 21000)
        payload = self.baseline.baseline_rows(self.conn, "claude")
        self.assertTrue(payload["compaction_filtered"])
        self.assertEqual(payload["compaction_boundaries"], 0)
        self.assertIn("no boundary", self.baseline.render_baseline_table(payload))

    def test_pooled_render_discloses_that_project_mix_moves_the_floor(self) -> None:
        self.seed_week(self.WEEKS[0], 21000)
        payload = self.baseline.baseline_rows(self.conn, "claude")
        self.assertIn("pooled across projects", self.baseline.render_baseline_table(payload))

    def test_codex_payload_declares_compaction_filtering_unsupported(self) -> None:
        self.seed_week(self.WEEKS[0], 11000, harness="codex")
        payload = self.baseline.baseline_rows(self.conn, "codex")
        self.assertFalse(payload["compaction_filtered"])
        rendered = self.baseline.render_baseline_table(payload)
        self.assertIn("compaction filtering: unsupported", rendered)

    def test_claude_payload_declares_compaction_filtering_applied(self) -> None:
        self.seed_week(self.WEEKS[0], 21000)
        # A boundary somewhere in the store, so the render reports a filter
        # that actually had rows to match rather than the zero-coverage case.
        excluded = self.seed(21000, week=self.WEEKS[1])
        self.compact_boundary(excluded, f"{self.WEEKS[1]}T11:00:00Z")
        payload = self.baseline.baseline_rows(self.conn, "claude")
        self.assertTrue(payload["compaction_filtered"])
        self.assertEqual(payload["compaction_boundaries"], 1)
        self.assertIn("compaction filtering: applied", self.baseline.render_baseline_table(payload))

    def test_render_states_the_detection_limit(self) -> None:
        """What the surface cannot see is part of its answer."""
        self.seed_week(self.WEEKS[0], 21000)
        payload = self.baseline.baseline_rows(self.conn, "claude")
        self.assertIn("smaller drift is not visible", self.baseline.render_baseline_table(payload))
        self.assertIn("measured on this machine only", self.baseline.render_baseline_table(payload))

    def test_render_never_marks_measured_values_as_inferred(self) -> None:
        """`~` means "the harness did not report this". Nothing here qualifies."""
        self.seed_week(self.WEEKS[0], 21000)
        payload = self.baseline.baseline_rows(self.conn, "claude")
        self.assertNotIn("~", self.baseline.render_baseline_table(payload))

    def test_by_cwd_does_not_pool_across_projects(self) -> None:
        self.seed_week(self.WEEKS[0], 18000, cwd="/a")
        self.seed_week(self.WEEKS[0], 26000, cwd="/b")
        rows = self.baseline.weekly_floor(self.observations(), by_cwd=True)
        self.assertEqual(
            sorted((r["cwd"], r["floor"]) for r in rows), [("/a", 18000), ("/b", 26000)]
        )

    def test_pooled_is_the_default(self) -> None:
        self.seed_week(self.WEEKS[0], 18000, cwd="/a")
        self.seed_week(self.WEEKS[0], 26000, cwd="/b")
        rows = self.baseline.weekly_floor(self.observations())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["n"], 10)

    def test_repeated_reads_are_identical_and_write_nothing(self) -> None:
        self.seed_week(self.WEEKS[0], 21000)
        self.seed_week(self.WEEKS[1], 13200)
        before = self.conn.execute("SELECT COUNT(*) FROM turn_norm").fetchone()[0]
        first = self.baseline.baseline_rows(self.conn, "claude")
        second = self.baseline.baseline_rows(self.conn, "claude")
        self.assertEqual(first, second)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM turn_norm").fetchone()[0], before)

    def test_shipped_thresholds_stay_above_measured_wander(self) -> None:
        """Guards the data file, which no other test here reaches.

        `thresholds()` resolves through SOURCE_DIR, which points at the
        install rather than the checkout, so in every test environment it
        falls back to DEFAULT_THRESHOLDS and the shipped JSON is never read.
        Without this, loosening the file would leave the suite green.

        Both bounds are checked against the largest wander measured on the
        real corpus: 9.3%, 1,921 tokens. A value at or below either would
        make ordinary sampling noise register as a configuration change.
        """
        import json

        shipped = json.loads((REPO_ROOT / "data" / "baseline_thresholds.json").read_text())
        self.assertGreater(shipped["min_pct"], 0.093, "would fire on measured wander")
        self.assertGreater(shipped["min_abs"], 1921, "would fire on measured wander")
        self.assertGreaterEqual(shipped["min_n"], 5, "a quantile over fewer is noise")
        self.assertEqual(
            {k: v for k, v in shipped.items() if not k.startswith("_")}.keys(),
            self.baseline.DEFAULT_THRESHOLDS.keys(),
            "file and in-code fallback must cover the same keys",
        )

    def test_thresholds_fall_back_per_key(self) -> None:
        """A data file that lost a key still yields a usable surface."""
        import cost

        original = cost.SOURCE_DIR
        try:
            cost.SOURCE_DIR = REPO_ROOT / "tests" / "does-not-exist"
            self.assertEqual(self.baseline.thresholds(), self.baseline.DEFAULT_THRESHOLDS)
        finally:
            cost.SOURCE_DIR = original


class ClaudeConfigTests(unittest.TestCase):
    """Direct tests of cli/claude_config.py against files on disk.

    Written against real files in a temp directory rather than mocks: every
    reader here exists to survive another program rewriting a file underneath
    it, and a mock cannot fail the way an OSError or a half-written JSON
    document does.
    """

    # Shaped like the real map, small enough to read. The doubled
    # `security-guidance` keys are the observed case where one plugin is
    # surfaced under two namespaces; `quiet` is the seeded-at-install zero that
    # only `pluginUsage` ever produces.
    PLUGIN_USAGE = {
        "security-guidance@claude-plugins-official": {
            "usageCount": 16373,
            "lastUsedAt": "2026-08-17T12:00:00Z",
            "lastUsedNumStartups": 700,
        },
        "security-guidance@inline": {
            "usageCount": 4800,
            "lastUsedAt": "2026-08-17T12:00:00Z",
            "lastUsedNumStartups": 700,
        },
        "quiet@claude-plugins-official": {
            "usageCount": 0,
            "lastUsedAt": "2026-06-04T00:00:00Z",
            "lastUsedNumStartups": 1,
        },
    }

    # No zero entries, by construction: the harness writes a skill row on first
    # use, so an unused skill is absent rather than present at zero.
    SKILL_USAGE = {
        "flow-plan": {"usageCount": 75, "lastUsedAt": "2026-08-17T12:00:00Z"},
        "superpowers:brainstorming": {"usageCount": 27, "lastUsedAt": "2026-08-01T00:00:00Z"},
    }

    def setUp(self) -> None:
        import tempfile

        repo_cli = REPO_ROOT / "cli"
        if str(repo_cli) not in sys.path:
            sys.path.insert(0, str(repo_cli))
            self._added_cli_path = True
        else:
            self._added_cli_path = False
        import claude_config

        self.cc = claude_config
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)
        if self._added_cli_path:
            sys.path.remove(str(REPO_ROOT / "cli"))
        sys.modules.pop("claude_config", None)

    def write_config(self, payload: dict) -> Path:
        path = self.tmp / ".claude.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    # -- read_usage ------------------------------------------------------

    def test_reads_both_maps_with_their_kinds(self) -> None:
        path = self.write_config(
            {"pluginUsage": self.PLUGIN_USAGE, "skillUsage": self.SKILL_USAGE}
        )
        records, stat = self.cc.read_usage(path)
        self.assertEqual(sum(1 for r in records if r["kind"] == "plugin"), 3)
        self.assertEqual(sum(1 for r in records if r["kind"] == "skill"), 2)
        self.assertEqual(stat.st_size, path.stat().st_size)

    def test_namespace_variants_stay_separate_records(self) -> None:
        """One plugin under two keys is two readings, never one summed total."""
        path = self.write_config({"pluginUsage": self.PLUGIN_USAGE})
        records, _ = self.cc.read_usage(path)
        counts = {r["name"]: r["usage_count"] for r in records}
        self.assertEqual(counts["security-guidance@claude-plugins-official"], 16373)
        self.assertEqual(counts["security-guidance@inline"], 4800)
        self.assertNotIn("security-guidance", counts)

    def test_seeded_zero_is_kept(self) -> None:
        """A plugin at zero is a real reading and must survive to the store."""
        path = self.write_config({"pluginUsage": self.PLUGIN_USAGE})
        records, _ = self.cc.read_usage(path)
        zero = [r for r in records if r["name"] == "quiet@claude-plugins-official"]
        self.assertEqual(zero[0]["usage_count"], 0)

    def test_absent_file_reads_none(self) -> None:
        self.assertIsNone(self.cc.read_usage(self.tmp / "nothing.json"))

    def test_torn_json_reads_none(self) -> None:
        """A file caught mid-rewrite is an ordinary event, not a fault."""
        path = self.tmp / ".claude.json"
        path.write_text('{"pluginUsage": {"a": {"usageCo', encoding="utf-8")
        self.assertIsNone(self.cc.read_usage(path))

    def test_non_dict_document_reads_none(self) -> None:
        path = self.tmp / ".claude.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        self.assertIsNone(self.cc.read_usage(path))

    def test_missing_maps_read_empty_not_none(self) -> None:
        """A readable config with no counters is zero records, not no reading."""
        records, _ = self.cc.read_usage(self.write_config({"editorMode": "normal"}))
        self.assertEqual(records, [])

    def test_non_integer_counter_is_skipped_not_coerced(self) -> None:
        path = self.write_config(
            {"pluginUsage": {"bad@m": {"usageCount": "12"}, "good@m": {"usageCount": 3}}}
        )
        records, _ = self.cc.read_usage(path)
        self.assertEqual([r["name"] for r in records], ["good@m"])

    def test_boolean_counter_is_rejected(self) -> None:
        """bool is an int subclass; a True counter must not read as 1."""
        path = self.write_config({"pluginUsage": {"b@m": {"usageCount": True}}})
        records, _ = self.cc.read_usage(path)
        self.assertEqual(records, [])

    def test_epoch_millisecond_last_used_becomes_iso(self) -> None:
        """The harness writes lastUsedAt as epoch ms, not ISO text.

        A first version of this reader assumed a string, rejected every integer,
        and turned a populated field into None for all 127 real entries without
        failing a single test. Mutation testing found the gap; this closes it.
        """
        path = self.write_config(
            {"pluginUsage": {"a@m": {"usageCount": 1, "lastUsedAt": 1775249400612}}}
        )
        records, _ = self.cc.read_usage(path)
        self.assertEqual(records[0]["last_used_at"], "2026-04-03T20:50:00Z")

    def test_iso_string_last_used_is_passed_through(self) -> None:
        path = self.write_config(
            {"pluginUsage": {"a@m": {"usageCount": 1, "lastUsedAt": "2026-08-17T12:00:00Z"}}}
        )
        records, _ = self.cc.read_usage(path)
        self.assertEqual(records[0]["last_used_at"], "2026-08-17T12:00:00Z")

    def test_uninterpretable_last_used_reads_absent(self) -> None:
        """A timestamp flow cannot interpret is not one it should guess at."""
        path = self.write_config(
            {"pluginUsage": {"a@m": {"usageCount": 1, "lastUsedAt": {"nested": 1}}}}
        )
        records, _ = self.cc.read_usage(path)
        self.assertIsNone(records[0]["last_used_at"])

    def test_absent_last_used_is_none_not_empty_string(self) -> None:
        path = self.write_config({"pluginUsage": {"a@m": {"usageCount": 5}}})
        records, _ = self.cc.read_usage(path)
        self.assertIsNone(records[0]["last_used_at"])
        self.assertIsNone(records[0]["startups"])

    # -- read_enabled_plugins --------------------------------------------

    def test_reads_enabled_plugins(self) -> None:
        path = self.tmp / "settings.json"
        path.write_text(json.dumps({"enabledPlugins": {"a@m": True, "b@m": False}}))
        self.assertEqual(self.cc.read_enabled_plugins(path), {"a@m": True, "b@m": False})

    def test_absent_settings_is_unknown_not_empty(self) -> None:
        """{} means enablement is unknown; callers must not read it as 'none on'."""
        self.assertEqual(self.cc.read_enabled_plugins(self.tmp / "nope.json"), {})

    def test_malformed_settings_does_not_raise(self) -> None:
        path = self.tmp / "settings.json"
        path.write_text("{not json", encoding="utf-8")
        self.assertEqual(self.cc.read_enabled_plugins(path), {})

    # -- installed_skills ------------------------------------------------

    def make_skill(self, root: Path, *parts: str) -> None:
        target = root.joinpath(*parts)
        target.mkdir(parents=True, exist_ok=True)
        (target / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")

    def test_enumerates_user_and_plugin_skills_as_usage_keys(self) -> None:
        home = self.tmp / "home"
        self.make_skill(home, ".claude", "skills", "confluence-adf")
        self.make_skill(
            home, ".claude", "plugins", "cache", "official", "superpowers", "6.3.0",
            "skills", "brainstorming",
        )
        self.assertEqual(
            self.cc.installed_skills(home),
            {"confluence-adf", "superpowers:brainstorming"},
        )

    def test_project_root_widens_the_population(self) -> None:
        """Project-local skills are in scope, which is why scope gets recorded."""
        home = self.tmp / "home"
        project = self.tmp / "proj"
        self.make_skill(home, ".claude", "skills", "user-skill")
        self.make_skill(project, ".claude", "skills", "project-skill")
        self.assertEqual(self.cc.installed_skills(home), {"user-skill"})
        self.assertEqual(
            self.cc.installed_skills(home, project), {"user-skill", "project-skill"}
        )

    def test_absent_roots_enumerate_empty(self) -> None:
        self.assertEqual(self.cc.installed_skills(self.tmp / "gone"), set())

    # -- hook_registering_plugins ----------------------------------------

    def write_hooks(self, home: Path, plugin: str, version: str, hooks: dict) -> None:
        target = home / ".claude" / "plugins" / "cache" / "official" / plugin / version / "hooks"
        target.mkdir(parents=True, exist_ok=True)
        (target / "hooks.json").write_text(json.dumps({"hooks": hooks}), encoding="utf-8")

    def test_counts_hook_entries_across_events(self) -> None:
        """The count is entries, not events: two PostToolUse matchers are two."""
        home = self.tmp / "home"
        self.write_hooks(
            home, "security-guidance", "1.0.0",
            {"SessionStart": [{}], "UserPromptSubmit": [{}], "PostToolUse": [{}, {}], "Stop": [{}]},
        )
        self.write_hooks(home, "ralph-loop", "1.0.0", {"Stop": [{}]})
        counts = self.cc.hook_registering_plugins(home)
        self.assertEqual(counts["security-guidance"], 5)
        self.assertEqual(counts["ralph-loop"], 1)

    def test_plugin_without_hooks_is_absent_from_the_map(self) -> None:
        home = self.tmp / "home"
        self.write_hooks(home, "hooked", "1.0.0", {"Stop": [{}]})
        self.assertNotIn("quiet", self.cc.hook_registering_plugins(home))

    def test_highest_count_wins_across_cached_versions(self) -> None:
        """Under-reporting hook registration is the direction that misleads."""
        home = self.tmp / "home"
        self.write_hooks(home, "p", "1.0.0", {"Stop": [{}]})
        self.write_hooks(home, "p", "2.0.0", {"Stop": [{}], "SessionStart": [{}, {}]})
        self.assertEqual(self.cc.hook_registering_plugins(home)["p"], 3)

    def test_malformed_hooks_json_is_skipped(self) -> None:
        home = self.tmp / "home"
        target = home / ".claude" / "plugins" / "cache" / "official" / "p" / "1.0.0" / "hooks"
        target.mkdir(parents=True)
        (target / "hooks.json").write_text("{broken", encoding="utf-8")
        self.assertEqual(self.cc.hook_registering_plugins(home), {})

    # -- base_plugin_name ------------------------------------------------

    def test_base_name_strips_marketplace_suffix(self) -> None:
        self.assertEqual(self.cc.base_plugin_name("ralph-loop@inline"), "ralph-loop")

    def test_base_name_leaves_unsuffixed_keys_alone(self) -> None:
        self.assertEqual(self.cc.base_plugin_name("humanize"), "humanize")

    def test_base_name_splits_on_the_last_at(self) -> None:
        """A key with more than one @ keeps everything before the suffix."""
        self.assertEqual(self.cc.base_plugin_name("scope@weird@inline"), "scope@weird")


class PluginUsageTests(unittest.TestCase):
    """Direct tests of cli/plugin_usage.py against a constructed store and home.

    A whole fake `home` is built on disk rather than mocked, because most of what
    this module gets wrong is a disagreement between two files written by two
    processes — the counters in `.claude.json` against `enabledPlugins` in
    `settings.json`, and the counter keys against the installed-skill walk. A
    mock of either side cannot disagree with the other in the way real files do.
    """

    def setUp(self) -> None:
        import sqlite3
        import tempfile

        repo_cli = REPO_ROOT / "cli"
        if str(repo_cli) not in sys.path:
            sys.path.insert(0, str(repo_cli))
            self._added_cli_path = True
        else:
            self._added_cli_path = False
        import usage_store
        import plugin_usage

        self.pu = plugin_usage
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "home"
        (self.home / ".claude").mkdir(parents=True)

        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON")
        for _v, _d, sql in usage_store.MIGRATIONS:
            self.conn.executescript(sql)
        self.conn.executemany(
            "INSERT INTO harness_capability (harness, field, supported) VALUES (?, ?, ?)",
            [("claude", "plugin_usage_counters", 1), ("codex", "plugin_usage_counters", 0)],
        )

    def tearDown(self) -> None:
        import shutil

        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)
        if self._added_cli_path:
            sys.path.remove(str(REPO_ROOT / "cli"))
        for name in ("plugin_usage", "claude_config", "usage_store"):
            sys.modules.pop(name, None)

    # -- fixtures --------------------------------------------------------

    def write_counters(
        self,
        plugins: dict,
        skills: dict | None = None,
        mtime: float = 1000.0,
        install: bool = True,
    ):
        """Write a `.claude.json` and pin its mtime, which is the ordering key.

        `install=True` also creates a cache directory for each plugin base name,
        because a counter key with no install directory is a *different* case —
        the read model cannot tell whether it fired hooks, so it goes to its own
        bucket. Tests about invocation lanes want installed plugins; the tests
        about departed plugins pass `install=False` and say so.
        """
        import os

        path = self.home / ".claude.json"
        payload = {"pluginUsage": plugins}
        if skills is not None:
            payload["skillUsage"] = skills
        path.write_text(json.dumps(payload), encoding="utf-8")
        os.utime(path, (mtime, mtime))
        if install:
            for key in plugins:
                self.install_plugin(key.rpartition("@")[0] or key)
        return path

    def install_plugin(self, base_name: str) -> None:
        d = self.home / ".claude" / "plugins" / "cache" / "mkt" / base_name / "1.0.0"
        d.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def entry(count: int, last_used: int | None = None) -> dict:
        e: dict = {"usageCount": count}
        if last_used is not None:
            e["lastUsedAt"] = last_used
        return e

    def write_settings(self, enabled: dict) -> None:
        (self.home / ".claude" / "settings.json").write_text(
            json.dumps({"enabledPlugins": enabled}), encoding="utf-8"
        )

    def install_skill(self, name: str) -> None:
        d = self.home / ".claude" / "skills" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")

    def install_hooked_plugin(self, name: str, entries: int) -> None:
        d = (
            self.home / ".claude" / "plugins" / "cache" / "mkt" / name / "1.0.0" / "hooks"
        )
        d.mkdir(parents=True, exist_ok=True)
        (d / "hooks.json").write_text(
            json.dumps({"hooks": {"Stop": [{} for _ in range(entries)]}}), encoding="utf-8"
        )

    def observe(self, path, **kw):
        return self.pu.observe_usage(path, self.conn, **kw)

    def payload(self):
        return self.pu.usage_payload(self.conn, home=self.home)

    def rows(self) -> list[tuple]:
        return self.conn.execute(
            "SELECT kind, name, usage_count, source_mtime FROM plugin_usage_observation"
            " ORDER BY name, source_mtime"
        ).fetchall()

    # -- write path ------------------------------------------------------

    def test_first_observation_stores_every_counter(self) -> None:
        path = self.write_counters({"a@m": self.entry(3)}, {"s": self.entry(1)})
        result = self.observe(path)
        self.assertEqual(result["inserted"], 2)
        self.assertTrue(result["changed"])
        self.assertEqual(len(self.rows()), 2)

    def test_unchanged_file_is_not_reparsed(self) -> None:
        """The mtime guard is the whole cost control: no move, no parse, no rows."""
        path = self.write_counters({"a@m": self.entry(3)})
        self.observe(path)
        again = self.observe(path)
        self.assertTrue(again["skipped_unchanged"])
        self.assertEqual(again["inserted"], 0)
        self.assertEqual(len(self.rows()), 1)

    def test_unchanged_file_is_never_parsed_at_all(self) -> None:
        """The guard has to stop the read, not just the insert.

        A first version compared the watermark *after* calling read_usage, so
        every session still loaded and decoded the whole document and only the
        write was skipped — the entire cost the guard exists to avoid, with
        every row-count assertion still passing. Asserting on rows cannot catch
        that; only asserting the parse never happened can.
        """
        import claude_config

        path = self.write_counters({"a@m": self.entry(3)})
        self.observe(path)

        calls = []
        original = claude_config.read_usage

        def counted(p):
            calls.append(p)
            return original(p)

        claude_config.read_usage = counted
        try:
            result = self.observe(path)
        finally:
            claude_config.read_usage = original

        self.assertTrue(result["skipped_unchanged"])
        self.assertEqual(calls, [], "the config was parsed despite not having moved")

    def test_advancing_mtime_records_the_new_state(self) -> None:
        path = self.write_counters({"a@m": self.entry(3)}, mtime=1000.0)
        self.observe(path)
        self.write_counters({"a@m": self.entry(9)}, mtime=2000.0)
        self.observe(path)
        self.assertEqual([r[2] for r in self.rows()], [3, 9])

    def test_missing_file_reports_error_and_writes_nothing(self) -> None:
        result = self.observe(self.home / "absent.json")
        self.assertEqual(result["error"], "unreadable")
        self.assertEqual(self.rows(), [])

    def test_torn_json_reports_error_and_writes_nothing(self) -> None:
        path = self.home / ".claude.json"
        path.write_text('{"pluginUsage": {"a', encoding="utf-8")
        self.assertEqual(self.observe(path)["error"], "unreadable")
        self.assertEqual(self.rows(), [])

    def test_scan_state_override_suppresses_a_reobservation(self) -> None:
        """The seam a dual-write test needs: simulate another writer's watermark."""
        path = self.write_counters({"a@m": self.entry(3)}, mtime=1000.0)
        result = self.observe(path, scan_state=5000.0)
        self.assertTrue(result["skipped_unchanged"])
        self.assertEqual(self.rows(), [])

    # -- dual write ------------------------------------------------------

    def test_two_writers_on_one_revision_collapse_to_one_row(self) -> None:
        """The property the UNIQUE key exists for: same state twice is one fact."""
        path = self.write_counters({"a@m": self.entry(3)}, mtime=1000.0)
        self.observe(path)
        # A second writer that never saw the watermark still cannot duplicate.
        second = self.observe(path, scan_state=0.0)
        self.assertEqual(second["inserted"], 0)
        self.assertEqual(len(self.rows()), 1)

    def test_final_state_is_independent_of_writer_order(self) -> None:
        import sqlite3

        import usage_store

        def run(order: list[float]) -> list[tuple]:
            conn = sqlite3.connect(":memory:")
            for _v, _d, sql in usage_store.MIGRATIONS:
                conn.executescript(sql)
            for mtime in order:
                self.write_counters({"a@m": self.entry(int(mtime))}, mtime=mtime)
                self.pu.observe_usage(
                    self.home / ".claude.json", conn, scan_state=0.0
                )
            out = conn.execute(
                "SELECT name, usage_count, source_mtime FROM plugin_usage_observation"
                " ORDER BY source_mtime"
            ).fetchall()
            conn.close()
            return out

        self.assertEqual(run([1000.0, 2000.0, 3000.0]), run([3000.0, 1000.0, 2000.0]))

    def test_out_of_order_observation_still_orders_by_source_mtime(self) -> None:
        """observed_at is not the ordering key; the harness's own clock is."""
        path = self.home / ".claude.json"
        self.write_counters({"a@m": self.entry(10)}, mtime=3000.0)
        self.observe(path, scan_state=0.0)
        self.write_counters({"a@m": self.entry(4)}, mtime=1000.0)
        self.observe(path, scan_state=0.0)
        entry = [p for p in self.payload()["plugins_used"] if p["name"] == "a@m"][0]
        self.assertEqual(entry["usage_count"], 10)
        self.assertEqual(entry["delta"], 6)

    # -- resets ----------------------------------------------------------

    def test_a_reset_plugin_stays_out_of_the_prune_list(self) -> None:
        """A reset satisfies `usage_count == 0` but is not a never-used plugin.

        Its history stopped being comparable at the reset, so listing it beside
        genuinely unused plugins puts something the user may run daily into the
        list they prune from. An earlier version did exactly that, and an
        earlier version of this test asserted it.
        """
        path = self.home / ".claude.json"
        self.write_counters({"a@m": self.entry(40)}, mtime=1000.0)
        self.observe(path, scan_state=0.0)
        self.write_counters({"a@m": self.entry(0)}, mtime=2000.0)
        self.observe(path, scan_state=0.0)
        payload = self.payload()
        self.assertNotIn("a@m", payload["plugins_never_invoked"])
        self.assertEqual([r["name"] for r in payload["resets"]], ["a@m"])

    def test_reset_delta_is_none_not_zero(self) -> None:
        """Zero would report 'no change'; the truth is 'no longer comparable'."""
        path = self.home / ".claude.json"
        self.write_counters({"a@m": self.entry(40)}, mtime=1000.0)
        self.observe(path, scan_state=0.0)
        self.write_counters({"a@m": self.entry(2)}, mtime=2000.0)
        self.observe(path, scan_state=0.0)
        entry = [p for p in self.payload()["plugins_used"] if p["name"] == "a@m"][0]
        self.assertIsNone(entry["delta"])
        self.assertTrue(entry["is_reset"])

    def test_an_unmoved_counter_writes_no_second_row(self) -> None:
        """Rows track changes, not observations.

        Without this guard every observation copies all ~127 entries, so the
        table grows with how often the harness rewrites its config rather than
        with how often anything was used. The consequence is that a delta of
        zero cannot occur by construction — "did not move" is expressed by the
        absence of a new row, and by `last_used_at`, not by a zero.
        """
        path = self.home / ".claude.json"
        self.write_counters({"a@m": self.entry(7)}, mtime=1000.0)
        self.observe(path, scan_state=0.0)
        self.write_counters({"a@m": self.entry(7), "b@m": self.entry(1)}, mtime=2000.0)
        result = self.observe(path, scan_state=0.0)

        self.assertEqual(result["inserted"], 1, "only the moved counter should be stored")
        names = [r[1] for r in self.rows()]
        self.assertEqual(names.count("a@m"), 1)
        by_name = {p["name"]: p for p in self.payload()["plugins_used"]}
        self.assertIsNone(by_name["a@m"]["delta"])  # one row: nothing to compare against
        self.assertIsNone(by_name["b@m"]["delta"])  # first sighting, no predecessor

    def test_a_moved_counter_reports_the_size_of_its_change(self) -> None:
        path = self.home / ".claude.json"
        self.write_counters({"a@m": self.entry(7)}, mtime=1000.0)
        self.observe(path, scan_state=0.0)
        self.write_counters({"a@m": self.entry(19)}, mtime=2000.0)
        self.observe(path, scan_state=0.0)
        by_name = {p["name"]: p for p in self.payload()["plugins_used"]}
        self.assertEqual(by_name["a@m"]["delta"], 12)

    # -- capability and store states -------------------------------------

    def test_codex_reports_unsupported_rather_than_empty(self) -> None:
        self.write_counters({"a@m": self.entry(1)})
        self.observe(self.home / ".claude.json")
        payload = self.pu.usage_payload(self.conn, harness="codex", home=self.home)
        self.assertEqual(payload["state"], self.pu.STATE_UNSUPPORTED)

    def test_unseeded_capability_reports_stale_not_unsupported(self) -> None:
        """An absent capability row is 'not migrated', never 'cannot report'.

        Found by running against a real v5 store: every existing user upgrading
        would have been told "no usage counters exist to sample", which is false
        about Claude. Absent and unsupported are different answers.
        """
        self.conn.execute("DELETE FROM harness_capability")
        self.write_counters({"a@m": self.entry(1)})
        self.observe(self.home / ".claude.json")
        self.assertEqual(self.payload()["state"], self.pu.STATE_STALE)

    def test_explicit_zero_capability_still_reports_unsupported(self) -> None:
        self.conn.execute(
            "UPDATE harness_capability SET supported = 0 WHERE harness = 'claude'"
        )
        self.assertEqual(self.payload()["state"], self.pu.STATE_UNSUPPORTED)

    def test_unmigrated_store_reports_stale_and_does_not_raise(self) -> None:
        """flow doctor never migrates, so a v5 store must degrade, not traceback."""
        import sqlite3

        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE harness_capability (harness TEXT, field TEXT, supported INTEGER)"
        )
        conn.execute(
            "INSERT INTO harness_capability VALUES ('claude', 'plugin_usage_counters', 1)"
        )
        payload = self.pu.usage_payload(conn, home=self.home)
        conn.close()
        self.assertEqual(payload["state"], self.pu.STATE_STALE)

    def test_no_observations_reports_empty(self) -> None:
        self.assertEqual(self.payload()["state"], self.pu.STATE_EMPTY)

    def test_thin_history_is_not_reported_as_mature(self) -> None:
        """A plugin at zero after one snapshot is a short window, not disuse."""
        self.write_counters({"a@m": self.entry(0)})
        self.observe(self.home / ".claude.json")
        self.assertEqual(self.payload()["state"], self.pu.STATE_THIN)

    def test_snapshots_alone_do_not_make_a_history_mature(self) -> None:
        """Five snapshots can land in an hour — the hook fires every session."""
        path = self.home / ".claude.json"
        for i in range(self.pu.MIN_SNAPSHOTS + 2):
            self.write_counters({"a@m": self.entry(i)}, mtime=1000.0 + i)
            self.observe(path, scan_state=0.0)
        self.assertEqual(self.payload()["state"], self.pu.STATE_THIN)

    def test_enough_snapshots_over_enough_days_flips_to_ok(self) -> None:
        path = self.home / ".claude.json"
        day = 86400.0
        for i in range(self.pu.MIN_SNAPSHOTS):
            self.write_counters({"a@m": self.entry(i)}, mtime=1000.0 + i * 2 * day)
            self.observe(path, scan_state=0.0)
        self.assertEqual(self.payload()["state"], self.pu.STATE_OK)

    # -- classification --------------------------------------------------

    def test_hook_registering_plugin_leaves_the_invocation_lane(self) -> None:
        """The defect this feature exists to prevent, asserted directly."""
        self.install_hooked_plugin("noisy", entries=3)
        self.write_counters({"noisy@m": self.entry(9000), "quiet@m": self.entry(4)})
        self.observe(self.home / ".claude.json")
        payload = self.payload()
        self.assertEqual([p["base_name"] for p in payload["plugins_hook_driven"]], ["noisy"])
        self.assertEqual([p["name"] for p in payload["plugins_used"]], ["quiet@m"])

    def test_a_plugin_with_no_install_never_enters_the_invocation_lane(self) -> None:
        """The originating error, in its worst form.

        Hook detection reads the plugin's install directory, so a plugin whose
        counter outlived its install answers "no hooks" for the same reason it
        answers nothing else: it is gone. Routing that absence into the
        deliberate-invocation lane would render an uninstalled hook plugin's
        3,552 firings as calls, uncaveated, at the moment someone re-checks a
        prune.
        """
        self.write_counters({"departed@m": self.entry(3552)}, install=False)
        self.observe(self.home / ".claude.json")
        payload = self.payload()
        self.assertEqual([p["name"] for p in payload["plugins_used"]], [])
        self.assertEqual([p["name"] for p in payload["plugins_hook_driven"]], [])
        self.assertEqual([p["name"] for p in payload["plugins_departed"]], ["departed@m"])

    def test_unknown_hook_status_is_none_not_zero(self) -> None:
        """Cannot-tell and declares-no-hooks are different answers."""
        self.write_counters({"gone@m": self.entry(5)}, install=False)
        self.write_counters(
            {"gone@m": self.entry(5), "here@m": self.entry(5)}, mtime=2000.0, install=False
        )
        self.install_plugin("here")
        self.observe(self.home / ".claude.json")
        by_name = {
            p["name"]: p
            for p in self.payload()["plugins_departed"] + self.payload()["plugins_used"]
        }
        self.assertIsNone(by_name["gone@m"]["hook_entries"])
        self.assertEqual(by_name["here@m"]["hook_entries"], 0)

    def test_departed_plugins_are_rendered_with_their_caveat(self) -> None:
        self.write_counters({"departed@m": self.entry(3552)}, install=False)
        self.observe(self.home / ".claude.json")
        out = self.pu.render_usage_section(self.payload())
        self.assertIn("no install", out)
        self.assertIn("cannot tell whether these fired hooks", out)

    def test_the_plugin_block_declares_its_own_truncation(self) -> None:
        """Silent truncation in the block a prune reads invites the reader to
        infer the population from what is on screen."""
        self.write_counters({f"p{i}@m": self.entry(i + 1) for i in range(12)})
        self.observe(self.home / ".claude.json")
        out = self.pu.render_usage_section(self.payload())
        self.assertIn("and 7 more with invocations", out)

    def test_namespace_variants_are_never_summed(self) -> None:
        self.write_counters({"p@mkt": self.entry(100), "p@inline": self.entry(20)})
        self.observe(self.home / ".claude.json")
        counts = sorted(p["usage_count"] for p in self.payload()["plugins_used"])
        self.assertEqual(counts, [20, 100])
        self.assertNotIn(120, counts)

    def test_enabled_state_resolves_across_namespace_variants(self) -> None:
        """One plugin has one enablement, even when the counters name it twice."""
        self.write_settings({"p@mkt": False})
        self.write_counters({"p@mkt": self.entry(5), "p@inline": self.entry(2)})
        self.observe(self.home / ".claude.json")
        states = {p["namespace"]: p["enabled"] for p in self.payload()["plugins_used"]}
        self.assertEqual(states["mkt"], False)
        self.assertEqual(states["inline"], False)

    def test_absent_skill_is_never_invoked_not_zero(self) -> None:
        self.install_skill("used-skill")
        self.install_skill("unused-skill")
        self.write_counters({}, {"used-skill": self.entry(3)})
        self.observe(self.home / ".claude.json")
        payload = self.payload()
        self.assertEqual(payload["skills_never_invoked"], ["unused-skill"])
        self.assertEqual([s["name"] for s in payload["skills_used"]], ["used-skill"])

    def test_unresolvable_counter_keys_are_surfaced_not_dropped(self) -> None:
        """55% of real keys no longer resolve; silently dropping them looks clean."""
        self.install_skill("current")
        self.write_counters({}, {"current": self.entry(2), "renamed-away": self.entry(60)})
        self.observe(self.home / ".claude.json")
        self.assertEqual(self.payload()["skills_unresolved"], ["renamed-away"])

    # -- rendering -------------------------------------------------------

    def test_every_state_renders_without_raising(self) -> None:
        for state in (
            self.pu.STATE_UNSUPPORTED,
            self.pu.STATE_STALE,
            self.pu.STATE_EMPTY,
        ):
            out = self.pu.render_usage_section({"state": state, "harness": "codex"})
            self.assertLessEqual(len(out.splitlines()), 2, state)

    def test_hook_firings_are_never_called_uses(self) -> None:
        self.install_hooked_plugin("noisy", entries=5)
        self.write_counters({"noisy@m": self.entry(16373)})
        self.observe(self.home / ".claude.json")
        out = self.pu.render_usage_section(self.payload())
        self.assertIn("firings", out)
        self.assertIn("not a usage signal", out)
        hook_line = [ln for ln in out.splitlines() if "16,373" in ln][0]
        self.assertNotIn("invocation", hook_line)

    def test_render_never_exceeds_the_terminal_budget(self) -> None:
        self.install_skill("a-skill")
        self.write_counters(
            {f"p{i}@m": self.entry(i) for i in range(40)},
            {f"s{i}": self.entry(i + 1) for i in range(40)},
        )
        self.observe(self.home / ".claude.json")
        out = self.pu.render_usage_section(self.payload())
        self.assertLessEqual(max(len(ln) for ln in out.splitlines()), 100)

    def test_control_characters_never_reach_the_terminal(self) -> None:
        """A cloned repo can ship a project-local skill whose name moves the cursor.

        doctor output is read to make a decision, so a name carrying ESC or CR
        could overwrite the lines above it. Stripped at render only — the stored
        name stays verbatim.
        """
        hostile = "evil\x1b[2Kname\r"
        self.write_counters({}, {hostile: self.entry(4)})
        self.observe(self.home / ".claude.json")
        out = self.pu.render_usage_section(self.payload())
        self.assertNotIn("\x1b", out)
        self.assertNotIn("\r", out)
        self.assertIn("evil[2Kname", out)
        # ...and the store still holds exactly what the harness wrote.
        stored = self.conn.execute(
            "SELECT name FROM plugin_usage_observation WHERE kind = 'skill'"
        ).fetchone()[0]
        self.assertEqual(stored, hostile)

    def test_inventory_scope_renders_home_relative(self) -> None:
        """doctor output gets pasted into issues; an absolute path carries the
        username and whatever the project is named."""
        self.write_counters({"a@m": self.entry(1)})
        self.observe(self.home / ".claude.json")
        scope = Path.home() / "work" / "client-x"
        payload = self.pu.usage_payload(self.conn, home=self.home, project_root=scope)
        out = self.pu.render_usage_section(payload)
        self.assertIn("~/work/client-x", out)
        self.assertNotIn(str(Path.home() / "work"), out)

    def test_inferred_skill_count_is_marked(self) -> None:
        self.install_skill("never-run")
        self.write_counters({}, {"other": self.entry(1)})
        self.observe(self.home / ".claude.json")
        out = self.pu.render_usage_section(self.payload())
        self.assertIn("~1 installed skills never invoked", out)


class RepoRootFlowHomeTests(unittest.TestCase):
    """`~/.flow` is flow's own home, not a project overlay.

    Before the guard, any directory under $HOME that was not itself a repo
    walked up, matched flow home's `.flow`, and reported $HOME as its project
    root. `flow doctor` then printed a project section whose manifest was
    missing and whose sync checks had been skipped — indistinguishable, in the
    output, from a genuinely broken project.
    """

    def _repo_root_from(self, home: Path, cwd: Path) -> Path:
        """Call the real `repo_root` with HOME and the working directory faked.

        Both are read at call time rather than import time, so patching the
        environment around the call is enough; no reload is needed.
        """
        fsutil = load_cli_module("fsutil")
        saved_cwd = Path.cwd()
        saved_home = os.environ.get("HOME")
        os.environ["HOME"] = str(home)
        os.chdir(cwd)
        try:
            return fsutil.repo_root()
        finally:
            os.chdir(saved_cwd)
            if saved_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = saved_home

    def _isolated_home(self) -> Path:
        """A HOME with no `.git` anywhere above it.

        `self.repo` carries a `.git` from setUp, which would satisfy the walk
        before it ever reached the case under test.
        """
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        home = Path(tmp.name).resolve() / "home"
        (home / ".flow").mkdir(parents=True)
        return home

    def test_flow_home_is_not_mistaken_for_a_project_overlay(self) -> None:
        home = self._isolated_home()
        work = home / "notes"
        work.mkdir()

        self.assertEqual(
            self._repo_root_from(home, work),
            work,
            "a plain directory under $HOME has no project root; falling back to "
            "the working directory is the honest answer, and claiming $HOME is not",
        )

    def test_a_real_project_overlay_under_home_is_still_found(self) -> None:
        """The guard must exclude one specific path, not `.flow` in general."""
        home = self._isolated_home()
        project = home / "code" / "thing"
        (project / ".flow").mkdir(parents=True)
        nested = project / "src"
        nested.mkdir()

        self.assertEqual(self._repo_root_from(home, nested), project)

    def test_a_git_root_under_home_is_still_found(self) -> None:
        home = self._isolated_home()
        project = home / "code" / "repo"
        (project / ".git").mkdir(parents=True)
        nested = project / "src"
        nested.mkdir()

        self.assertEqual(self._repo_root_from(home, nested), project)

    def test_a_project_overlay_at_home_itself_is_shadowed(self) -> None:
        """Known and accepted: $HOME cannot also be a flow project, because the
        two would need the same `.flow` directory for different purposes. The
        walk continues past it rather than claiming it."""
        home = self._isolated_home()
        (home / ".flow" / "flow.toml").write_text("# would be a project manifest\n")
        work = home / "x"
        work.mkdir()

        self.assertEqual(self._repo_root_from(home, work), work)

    def test_guard_holds_when_home_is_reached_through_a_symlink(self) -> None:
        """Covers the `.resolve()` in `_flow_home`.

        macOS hands out temporary directories under `/var`, a symlink to
        `/private/var`, so HOME and a resolved working directory routinely spell
        the same place differently. Comparing unresolved makes the guard match
        nothing while still looking present in the source.
        """
        home = self._isolated_home()
        link = home.parent / "home-by-another-name"
        link.symlink_to(home)
        work = home / "notes"
        work.mkdir()

        self.assertEqual(
            self._repo_root_from(link, work),
            work,
            "flow home reached through a symlink is still flow home",
        )

    def test_fsutil_flow_home_matches_paths_flow_home(self) -> None:
        """Pin the two derivations together.

        `fsutil` computes `~/.flow` itself rather than importing `FLOW_HOME`, to
        stay a stdlib-only leaf. That duplication is only safe while the two
        agree, so assert it instead of trusting it.
        """
        fsutil = load_cli_module("fsutil")
        paths = load_cli_module("paths")
        self.assertEqual(fsutil._flow_home().resolve(), paths.FLOW_HOME.resolve())

    def test_doctor_from_home_reports_not_a_project(self) -> None:
        """The reported symptom, end to end."""
        home = self._isolated_home()
        (home / ".flow" / "source").symlink_to(REPO_ROOT)

        result = subprocess.run(
            [sys.executable, str(FLOW_CLI), "doctor"],
            cwd=home,
            text=True,
            capture_output=True,
            env=_clean_env(home),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("not a flow project", result.stdout)
        self.assertNotIn(
            "repo .flow:",
            result.stdout,
            "the project section is what made 'not a project' look like a broken one",
        )
        self.assertNotIn("manifest:         missing", result.stdout)


class CapabilityGapLedgerTests(unittest.TestCase):
    """`flow gaps`: the ledger, its grouping, and promotion into the backlog.

    Subclasses TestCase rather than FlowCliTests on purpose. Inheriting that
    class would re-run its whole suite to add these few, which has happened
    before; the module-level loader is what these actually need from it.
    (`FlowCliHarness` now exists for tests that do want the subprocess runner
    without the suite.)
    """

    AT_A = "2026-08-01T00:00:00+00:00"
    AT_B = "2026-08-19T00:00:00+00:00"
    AT_PROMOTE = "2026-08-19T12:00:00+00:00"

    BACKLOG = (
        "# Backlog\n\n## Purpose\n\nOpen work only.\n\n"
        "## Active Priorities\n\n### 1. Existing Thing\n\nStatus: not started\n\n"
        "## Deferred / Watch\n\n### Something Deferred\n\nStatus: deferred\n"
    )

    def setUp(self):
        self.gaps = load_cli_module("gaps")
        self.tmp = Path(tempfile.mkdtemp(prefix="flow-gaps-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.ledger = self.tmp / "capability-gaps.jsonl"

    def _checkout(self, name="repo", backlog=None):
        """A throwaway git work tree carrying a backlog.

        promote() resolves its target from ~/.flow/source by default, which is
        the real clone. Every test passes an explicit source_dir so the real
        docs/backlog.md is never a candidate.
        """
        repo = self.tmp / name
        (repo / "docs").mkdir(parents=True)
        (repo / "docs" / "backlog.md").write_text(
            self.BACKLOG if backlog is None else backlog
        )
        # The sentinel resolve_checkout looks for. Being a git work tree is not
        # enough to be *the flow* work tree.
        (repo / "cli").mkdir()
        (repo / "cli" / "flow.py").write_text("")
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        return repo

    def _observe(self, key, run, project="proj", summary="a gap", at=None):
        return self.gaps.add_gap(
            self.ledger,
            key=key,
            summary=summary,
            project=project,
            run=run,
            at=at or self.AT_A,
        )

    # -- ledger ---------------------------------------------------------

    def test_absent_ledger_reads_empty_rather_than_raising(self):
        events, skipped = self.gaps.read_events(self.tmp / "nope.jsonl")
        self.assertEqual(events, [])
        self.assertEqual(skipped, 0)

    def test_empty_ledger_reads_empty(self):
        self.ledger.write_text("")
        events, skipped = self.gaps.read_events(self.ledger)
        self.assertEqual(events, [])
        self.assertEqual(skipped, 0)

    def test_malformed_lines_are_skipped_and_counted_not_swallowed(self):
        self._observe("a", "run-1")
        with self.ledger.open("a") as handle:
            handle.write("{not json\n")
            handle.write('{"no_event_field": true}\n')
        events, skipped = self.gaps.read_events(self.ledger)
        self.assertEqual(len(events), 1, "the good record must survive its neighbours")
        self.assertEqual(skipped, 2, "damage must be reported, not silently dropped")

    def test_first_observation_is_recorded(self):
        result = self._observe("evidence-inventory", "run-1")
        self.assertEqual(result["status"], "added")
        self.assertEqual(result["count"], 1)
        self.assertTrue(self.ledger.exists())

    def test_same_key_from_a_different_run_is_a_repeat(self):
        self._observe("evidence-inventory", "run-1", project="sheets")
        result = self._observe("evidence-inventory", "run-2", project="flow", at=self.AT_B)
        self.assertEqual(result["status"], "added")
        self.assertEqual(result["count"], 2, "a repeat across runs is the whole signal")

    def test_same_key_in_the_same_run_does_not_inflate_the_count(self):
        self._observe("evidence-inventory", "run-1")
        again = self._observe("evidence-inventory", "run-1")
        self.assertEqual(again["status"], "duplicate")
        entries = self.gaps.group_gaps(self.gaps.read_events(self.ledger)[0])
        self.assertEqual(entries[0]["count"], 1, "re-running an archive is not a recurrence")

    def test_grouping_orders_by_count_descending(self):
        self._observe("seen-twice", "run-1")
        self._observe("seen-twice", "run-2", at=self.AT_B)
        self._observe("seen-once", "run-1")
        entries = self.gaps.group_gaps(self.gaps.read_events(self.ledger)[0])
        self.assertEqual([e["key"] for e in entries], ["seen-twice", "seen-once"])

    def test_timestamp_is_supplied_not_read_from_the_clock(self):
        self._observe("a", "run-1", at=self.AT_A)
        record = json.loads(self.ledger.read_text().splitlines()[0])
        self.assertEqual(
            record["at"],
            self.AT_A,
            "pure functions must take `at`, or no test can assert exact bytes",
        )

    # -- promotion ------------------------------------------------------

    def test_promote_writes_into_deferred_watch(self):
        self._observe("evidence-inventory", "run-1")
        repo = self._checkout()
        result = self.gaps.promote(
            self.ledger, key="evidence-inventory", at=self.AT_PROMOTE, source_dir=repo
        )
        self.assertEqual(result["status"], "promoted")
        text = (repo / "docs" / "backlog.md").read_text()
        deferred = text.split("## Deferred / Watch", 1)[1]
        self.assertIn("Evidence Inventory", deferred)

    def test_promote_leaves_active_priorities_untouched(self):
        self._observe("evidence-inventory", "run-1")
        repo = self._checkout()
        self.gaps.promote(
            self.ledger, key="evidence-inventory", at=self.AT_PROMOTE, source_dir=repo
        )
        text = (repo / "docs" / "backlog.md").read_text()
        active = text.split("## Active Priorities", 1)[1].split("## Deferred", 1)[0]
        self.assertIn("### 1. Existing Thing", active)
        self.assertNotIn(
            "Evidence Inventory",
            active,
            "ranking is the maintainer's call; promotion must not claim a position",
        )

    def test_promoted_entry_carries_no_project_or_run(self):
        """The ledger is private; the backlog is not necessarily.

        `docs/backlog.md` lives in the flow repository, which is public, while
        the ledger sits in a private overlay. The count is the useful half of a
        gap and the provenance is the identifying half, so only the count
        crosses over.
        """
        self._observe("a", "run-alpha", project="path-nexus", summary="No template existed.")
        self._observe("a", "run-beta", project="acme-migration", at=self.AT_B)
        repo = self._checkout()
        self.gaps.promote(self.ledger, key="a", at=self.AT_PROMOTE, source_dir=repo)
        text = (repo / "docs" / "backlog.md").read_text()
        self.assertIn("observed 2 times", text, "the count is what makes a repeat actionable")
        for leaked in ("path-nexus", "acme-migration", "run-alpha", "run-beta"):
            self.assertNotIn(leaked, text, f"{leaked} must not reach the backlog")

    def test_a_summary_cannot_forge_a_heading(self):
        """A summary that looks like Markdown structure must not become it.

        A summary containing the anchor heading would make every later
        promotion fail as ambiguous — a self-inflicted denial of the feature.
        """
        self._observe(
            "a",
            "run-1",
            summary="Broke because\n## Deferred / Watch\nwas emitted verbatim.",
        )
        repo = self._checkout()
        self.gaps.promote(self.ledger, key="a", at=self.AT_PROMOTE, source_dir=repo)
        text = (repo / "docs" / "backlog.md").read_text()
        # The invariant is line-level, because that is what the parser matches
        # on: the anchor must occur as its own line exactly once. Flattening the
        # summary to a single line is what guarantees it — the words may still
        # appear, but never as a heading.
        anchor_lines = [l for l in text.splitlines() if l.strip() == "## Deferred / Watch"]
        self.assertEqual(
            len(anchor_lines),
            1,
            "a forged anchor line would break every subsequent promotion",
        )
        self._observe("b", "run-2", at=self.AT_B)
        second = self.gaps.promote(
            self.ledger, key="b", at="2026-08-20T00:00:00+00:00", source_dir=repo
        )
        self.assertEqual(second["status"], "promoted", "the document must stay parseable")

    def test_git_is_run_with_the_ambient_overrides_stripped(self):
        """GIT_DIR would redirect the write target to an unrelated repository.

        Reached inside a git hook or under `git rebase -x`, an unscrubbed call
        resolves --show-toplevel to whatever GIT_DIR names, and promote would
        write its backlog there.
        """
        repo = self._checkout()
        elsewhere = self._checkout(name="elsewhere")

        # GIT_WORK_TREE is the one that actually moves `--show-toplevel`;
        # GIT_DIR alone leaves cwd as the work tree, so setting only that
        # produced a test which passed against an unscrubbed call and proved
        # nothing. Both are set here, and both are on the stripped list.
        overrides = {
            "GIT_DIR": str(elsewhere / ".git"),
            "GIT_WORK_TREE": str(elsewhere),
        }
        saved = {k: os.environ.get(k) for k in overrides}
        os.environ.update(overrides)
        try:
            resolved = self.gaps.resolve_checkout(repo)
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.assertEqual(
            resolved,
            repo.resolve(),
            "cwd must win; ambient git env must not choose the repository",
        )
        self.assertNotEqual(
            resolved,
            elsewhere.resolve(),
            "promote would have written its backlog into an unrelated checkout",
        )

    def test_promotion_is_a_second_event_not_a_mutated_record(self):
        self._observe("a", "run-1")
        repo = self._checkout()
        self.gaps.promote(self.ledger, key="a", at=self.AT_PROMOTE, source_dir=repo)
        events = [json.loads(l) for l in self.ledger.read_text().splitlines()]
        self.assertEqual(
            [e["event"] for e in events],
            ["observed", "promoted"],
            "an append log must never be rewritten in place",
        )

    def test_promoting_twice_does_not_write_the_backlog_again(self):
        self._observe("a", "run-1")
        repo = self._checkout()
        self.gaps.promote(self.ledger, key="a", at=self.AT_PROMOTE, source_dir=repo)
        after_first = (repo / "docs" / "backlog.md").read_bytes()
        result = self.gaps.promote(
            self.ledger, key="a", at="2026-08-20T00:00:00+00:00", source_dir=repo
        )
        self.assertEqual(result["status"], "already-promoted")
        self.assertEqual((repo / "docs" / "backlog.md").read_bytes(), after_first)

    def test_unknown_key_is_refused(self):
        self._observe("a", "run-1")
        repo = self._checkout()
        result = self.gaps.promote(
            self.ledger, key="never-seen", at=self.AT_PROMOTE, source_dir=repo
        )
        self.assertEqual(result["status"], "unknown-key")

    # -- the checkout guard ---------------------------------------------

    def test_non_checkout_falls_back_and_leaves_the_ledger_intact(self):
        self._observe("rollout", "run-1")
        plain = self.tmp / "notarepo"
        plain.mkdir()
        result = self.gaps.promote(
            self.ledger, key="rollout", at=self.AT_PROMOTE, source_dir=plain
        )
        self.assertEqual(result["status"], "no-checkout")
        self.assertTrue(result["block"], "a refusal must still hand back the entry")
        self.assertFalse(
            self.gaps.is_promoted(self.gaps.read_events(self.ledger)[0], "rollout"),
            "declining must leave the gap promotable later",
        )

    def test_a_plain_directory_is_not_mistaken_for_a_checkout(self):
        """The guard must ask git, not test for a directory.

        Widening it to "the path exists" would call every release install a
        develop one and write a backlog that is not there.
        """
        plain = self.tmp / "exists-but-not-a-repo"
        plain.mkdir()
        self.assertIsNone(self.gaps.resolve_checkout(plain))

    def test_a_real_checkout_resolves_to_its_toplevel(self):
        repo = self._checkout()
        self.assertEqual(self.gaps.resolve_checkout(repo), repo.resolve())

    def test_missing_source_dir_is_not_a_checkout(self):
        self.assertIsNone(self.gaps.resolve_checkout(self.tmp / "absent"))

    # -- refusing to guess ----------------------------------------------

    def test_backlog_without_the_anchor_is_refused_and_left_alone(self):
        self._observe("a", "run-1")
        original = "# Backlog\n\nNo anchor here.\n"
        repo = self._checkout(name="repo2", backlog=original)
        result = self.gaps.promote(
            self.ledger, key="a", at=self.AT_PROMOTE, source_dir=repo
        )
        self.assertEqual(result["status"], "unparsable-backlog")
        self.assertEqual(
            (repo / "docs" / "backlog.md").read_text(),
            original,
            "byte-identical: asserting only the status would pass on a corrupted file",
        )

    def test_duplicated_anchor_is_ambiguous_and_refused(self):
        self._observe("a", "run-1")
        original = self.BACKLOG + "\n## Deferred / Watch\n\nsecond one\n"
        repo = self._checkout(name="repo3", backlog=original)
        result = self.gaps.promote(
            self.ledger, key="a", at=self.AT_PROMOTE, source_dir=repo
        )
        self.assertEqual(result["status"], "unparsable-backlog")
        self.assertEqual((repo / "docs" / "backlog.md").read_text(), original)

    def test_missing_backlog_file_is_refused_and_hands_back_the_entry(self):
        self._observe("a", "run-1")
        repo = self.tmp / "repo4"
        (repo / "cli").mkdir(parents=True)
        (repo / "cli" / "flow.py").write_text("")
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        result = self.gaps.promote(
            self.ledger, key="a", at=self.AT_PROMOTE, source_dir=repo
        )
        self.assertEqual(result["status"], "no-backlog")
        self.assertTrue(result["block"])

    # -- section placement ----------------------------------------------

    def test_entry_lands_inside_deferred_not_after_a_following_section(self):
        self._observe("a", "run-1")
        backlog = self.BACKLOG + "\n## Notes\n\ntrailing section\n"
        repo = self._checkout(name="repo5", backlog=backlog)
        self.gaps.promote(self.ledger, key="a", at=self.AT_PROMOTE, source_dir=repo)
        text = (repo / "docs" / "backlog.md").read_text()
        deferred = text.split("## Deferred / Watch", 1)[1].split("## Notes", 1)[0]
        self.assertIn("### A", deferred)
        self.assertTrue(text.rstrip().endswith("trailing section"))

    # -- the tool never publishes ---------------------------------------

    def test_promoting_issues_no_mutating_git_command(self):
        """Publishing is the engineer's decision, made separately from promoting.

        Observes the calls rather than grepping the source. A text search was
        the first attempt and it was wrong twice over: it matched the module's
        own reassurance string "not committed and not pushed", and it would
        still have passed against a subcommand assembled from a variable.
        """
        self._observe("a", "run-1")
        repo = self._checkout()
        seen = []
        real_run = self.gaps.subprocess.run

        def spy(cmd, *a, **kw):
            seen.append(list(cmd))
            return real_run(cmd, *a, **kw)

        self.gaps.subprocess.run = spy
        try:
            result = self.gaps.promote(
                self.ledger, key="a", at=self.AT_PROMOTE, source_dir=repo
            )
        finally:
            self.gaps.subprocess.run = real_run

        self.assertEqual(result["status"], "promoted")
        self.assertTrue(seen, "promote must actually consult git")
        for cmd in seen:
            self.assertEqual(cmd[0], "git")
            self.assertNotIn(
                cmd[1],
                ("push", "commit", "add", "checkout", "reset"),
                f"promote issued a mutating git command: {cmd}",
            )

    def test_a_git_work_tree_that_is_not_flow_is_rejected(self):
        """Being a repository is not enough to be the flow repository.

        A ~/.flow/source sitting inside an unrelated checkout — a dotfiles repo
        containing $HOME is the plausible case — would otherwise resolve there,
        and a docs/backlog.md in it would be edited.
        """
        stranger = self.tmp / "stranger"
        (stranger / "docs").mkdir(parents=True)
        (stranger / "docs" / "backlog.md").write_text(self.BACKLOG)
        subprocess.run(["git", "init", "-q"], cwd=stranger, check=True)

        self.assertIsNone(self.gaps.resolve_checkout(stranger))

        self._observe("a", "run-1")
        result = self.gaps.promote(
            self.ledger, key="a", at=self.AT_PROMOTE, source_dir=stranger
        )
        self.assertEqual(result["status"], "no-checkout")
        self.assertEqual(
            (stranger / "docs" / "backlog.md").read_text(),
            self.BACKLOG,
            "byte-identical: an unrelated repo's backlog must be untouched",
        )

    # -- the CLI layer, through argparse ---------------------------------

    def _flow(self, *args):
        return subprocess.run(
            [sys.executable, str(FLOW_CLI), *args],
            capture_output=True,
            text=True,
        )

    def test_add_and_list_work_through_the_real_entrypoint(self):
        """Exercises dispatch, not just the pure functions.

        Without this the three dispatch lines in flow.py could be deleted and
        the suite would stay green while `flow gaps add` silently returned 1.
        """
        ledger = str(self.ledger)
        first = self._flow(
            "gaps", "add", "--key", "a-gap", "--summary", "no template existed",
            "--project", "proj", "--run", "run-1", "--at", self.AT_A,
            "--ledger", ledger,
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("recorded", first.stdout)

        repeat = self._flow(
            "gaps", "add", "--key", "a-gap", "--summary", "again",
            "--project", "other", "--run", "run-2", "--at", self.AT_B,
            "--ledger", ledger,
        )
        self.assertEqual(repeat.returncode, 0, repeat.stderr)
        self.assertIn("2 times", repeat.stdout, "a repeat must announce itself")

        listed = self._flow("gaps", "list", "--json", "--ledger", ledger)
        self.assertEqual(listed.returncode, 0, listed.stderr)
        payload = json.loads(listed.stdout)
        self.assertEqual(payload["entries"][0]["key"], "a-gap")
        self.assertEqual(payload["entries"][0]["count"], 2)

    def test_a_key_with_stray_whitespace_does_not_start_a_second_lineage(self):
        ledger = str(self.ledger)
        self._flow(
            "gaps", "add", "--key", "a-gap", "--summary", "s",
            "--project", "p", "--run", "run-1", "--at", self.AT_A,
            "--ledger", ledger,
        )
        self._flow(
            "gaps", "add", "--key", "  a-gap  ", "--summary", "s",
            "--project", "p", "--run", "run-2", "--at", self.AT_B,
            "--ledger", ledger,
        )
        entries = self.gaps.group_gaps(self.gaps.read_events(self.ledger)[0])
        self.assertEqual(
            len(entries),
            1,
            "a padded key renders identically everywhere; it must not fork the count",
        )
        self.assertEqual(entries[0]["count"], 2)

    def test_cli_registers_the_three_verbs(self):
        result = subprocess.run(
            [sys.executable, str(FLOW_CLI), "gaps", "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for verb in ("add", "list", "promote"):
            self.assertIn(verb, result.stdout)


class ProjectManifestDeclarationTests(unittest.TestCase):
    """`declared_sources` — the manifest half of the project audit.

    This function moved out of `cli/setup.py`, where it was
    `_registered_manifest_paths` and returned a bare `set[Path]`. Its behavior
    for `flow refresh project` must be unchanged; what is new is the declaring
    site travelling with each record, and escaping paths coming back as a
    different type instead of being silently dropped.
    """

    def setUp(self) -> None:
        self.project = load_cli_module("project")

    def test_reads_every_declaration_site_that_carries_a_project_source(self) -> None:
        found, rejected = self.project.declared_sources(
            {
                "claude": {"commands": [{"name": "a", "source": "commands/a.md"}]},
                "codex": {"commands": [{"name": "b", "source": "commands/b.md"}]},
                "agents": [{"name": "c", "source": "agents/c.md"}],
                "standards": {
                    "d": {"flow_standard": "standards/d.md"},
                    "e": {"vendored_path": "standards/vendor/e.md"},
                },
            }
        )
        self.assertEqual(rejected, [])
        self.assertEqual(
            [d.rel for d in found],
            [
                "commands/a.md",
                "commands/b.md",
                "agents/c.md",
                "standards/d.md",
                "standards/vendor/e.md",
            ],
        )

    def test_each_declaration_carries_the_site_that_named_it(self) -> None:
        """A later manifest rewrite has to know which entry to drop, and a
        rewrite keyed on array position breaks when someone reorders the file."""
        found, _ = self.project.declared_sources(
            {
                "claude": {
                    "commands": [
                        {"name": "flow-boot", "source": "commands/flow-boot.md"}
                    ]
                },
                "agents": [{"name": "architect", "source": "agents/architect.md"}],
                "standards": {
                    "git-commits": {"flow_standard": "standards/git-commits.md"}
                },
            }
        )
        self.assertEqual(
            [d.declared_by for d in found],
            [
                "claude.commands.flow-boot.source",
                "agents.architect.source",
                "standards.git-commits.flow_standard",
            ],
        )

    def test_an_unnamed_entry_falls_back_to_its_index(self) -> None:
        found, _ = self.project.declared_sources(
            {"agents": [{"source": "agents/one.md"}, {"source": "agents/two.md"}]}
        )
        self.assertEqual(
            [d.declared_by for d in found],
            ["agents.[0].source", "agents.[1].source"],
        )

    def test_escaping_declarations_have_no_joinable_field(self) -> None:
        """The safety property, asserted structurally rather than by string.

        An absolute path or one containing `..` comes back as
        `RejectedDeclaration`, which deliberately has no `rel`. If a future
        refactor folds these back into `Declaration`, a downstream `root / rel`
        would resolve outside the overlay — so the assertion is that the
        attribute does not exist, not that its value looks safe.
        """
        found, rejected = self.project.declared_sources(
            {
                "agents": [
                    {"name": "ok", "source": "agents/ok.md"},
                    {"name": "abs", "source": "/etc/passwd"},
                    {"name": "up", "source": "../../../etc/passwd"},
                ]
            }
        )
        self.assertEqual([d.rel for d in found], ["agents/ok.md"])
        self.assertEqual(
            [(r.declared_value, r.declared_by) for r in rejected],
            [
                ("/etc/passwd", "agents.abs.source"),
                ("../../../etc/passwd", "agents.up.source"),
            ],
        )
        for record in rejected:
            self.assertFalse(
                hasattr(record, "rel"),
                "a rejected declaration must not carry a joinable path",
            )

    def test_hooks_are_not_a_declaration_site(self) -> None:
        """`[[hooks]]` carries `script`, which sync resolves against the
        framework source or the user overlay with no project branch — so a hook
        cannot be an orphaned project source. Including it would invent a
        finding class that cannot occur."""
        found, rejected = self.project.declared_sources(
            {"hooks": [{"name": "h", "script": "hooks/h.sh"}]}
        )
        self.assertEqual(found, [])
        self.assertEqual(rejected, [])

    def test_one_record_per_site_even_when_two_sites_name_one_path(self) -> None:
        """The scaffold really does declare `commands/flow-boot.md` under both
        `[[claude.commands]]` and `[[codex.commands]]`.

        Collapsing to the first site would hand a later manifest rewrite one
        entry to drop and leave the other dangling — the exact failure the
        declaring site was added to carry. Ordered, too: unordered iteration
        would make a rendered report non-deterministic.
        """
        manifest = {
            "claude": {"commands": [{"name": "a", "source": "commands/a.md"}]},
            "codex": {"commands": [{"name": "a", "source": "commands/a.md"}]},
            "agents": [{"name": "z", "source": "agents/z.md"}],
        }
        first, _ = self.project.declared_sources(manifest)
        second, _ = self.project.declared_sources(manifest)
        self.assertEqual(
            [(d.rel, d.declared_by) for d in first],
            [
                ("commands/a.md", "claude.commands.a.source"),
                ("commands/a.md", "codex.commands.a.source"),
                ("agents/z.md", "agents.z.source"),
            ],
        )
        self.assertEqual(first, second)

    def test_refresh_project_still_sees_each_path_once(self) -> None:
        """The one existing caller takes a set of `rel`, so per-site records
        must not change what it refreshes."""
        found, _ = self.project.declared_sources(
            {
                "claude": {"commands": [{"name": "a", "source": "commands/a.md"}]},
                "codex": {"commands": [{"name": "a", "source": "commands/a.md"}]},
            }
        )
        self.assertEqual({d.rel for d in found}, {"commands/a.md"})

    def test_malformed_manifest_shapes_are_skipped_not_fatal(self) -> None:
        found, rejected = self.project.declared_sources(
            {
                "claude": "not-a-table",
                "agents": [{"name": "n", "source": None}, {"name": "e", "source": ""}],
                "standards": {"s": "not-a-table"},
            }
        )
        self.assertEqual(found, [])
        self.assertEqual(rejected, [])

    def test_project_module_imports_no_heavy_siblings(self) -> None:
        """The dependency direction, asserted rather than left in a docstring.

        `cli/setup.py` imports `sync_target`. It no longer imports this module
        — retiring `flow refresh project` removed the only edge — so the cycle
        half of the original rationale is gone, and the weight half is not:
        one convenience import back into `setup` would still drag the whole
        adapter-generation graph into a read-only command. Walked statically
        and transitively, because a runtime check would only see what the
        current code path happens to touch.
        """
        import ast

        cli_dir = REPO_ROOT / "cli"
        siblings = {p.stem for p in cli_dir.glob("*.py")}
        allowed = {"paths", "fsutil", "flowtoml"}

        def sibling_imports(stem: str) -> set[str]:
            tree = ast.parse((cli_dir / f"{stem}.py").read_text())
            names: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names.update(a.name.split(".")[0] for a in node.names)
                elif (
                    isinstance(node, ast.ImportFrom)
                    and node.level == 0
                    and node.module
                ):
                    names.add(node.module.split(".")[0])
            return names & siblings

        reached: set[str] = set()
        queue = list(sibling_imports("project"))
        while queue:
            stem = queue.pop()
            if stem in reached:
                continue
            reached.add(stem)
            queue.extend(sibling_imports(stem))

        self.assertLessEqual(
            reached,
            allowed,
            f"cli/project.py reaches {sorted(reached - allowed)}; it may only "
            f"reach {sorted(allowed)}",
        )
        # Control: the walk does find edges when they exist, so an empty
        # `reached` from a broken parser cannot pass this silently.
        self.assertIn("paths", sibling_imports("diagnostics"))


class DoctorReplacesReportTests(FlowCliHarness):
    """`flow doctor`'s project-wiring block, end to end."""

    def _project(self, manifest_body: str) -> Path:
        home = self.use_fake_home()
        self.setup_project()
        flow_dir = self.repo / ".flow"
        (flow_dir / "flow.toml").write_text(
            '[framework]\nname = "flow"\nversion = 1\nkind = "project"\n' + manifest_body
        )
        return home

    def _overlay_standard(self, home: Path, name: str) -> None:
        target = home / ".flow" / "user" / "standards" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("replacement\n")

    def _project_section(self, stdout: str) -> str:
        """Only the project block.

        doctor prints `overlay:` in the project section and `user overlay:`
        in the section above it, so an unscoped `assertIn` can match the wrong
        half of the same output.
        """
        start = stdout.find("-- project:")
        self.assertNotEqual(start, -1, f"no project section in:\n{stdout}")
        end = stdout.find("-- usage:", start)
        return stdout[start:end if end != -1 else len(stdout)]

    def test_a_resolving_wiring_reports_ok(self) -> None:
        home = self._project(
            '\n[[replaces]]\ndefault = "standards/testing.md"\nwith = "standards/mine.md"\n'
        )
        self._overlay_standard(home, "mine.md")

        section = self._project_section(self.run_flow("doctor").stdout)

        self.assertIn("replaces:         1 wired", section)
        self.assertIn("ok       standards/testing.md -> standards/mine.md", section)

    def test_a_replacement_this_user_lacks_is_reported_as_their_gap(self) -> None:
        """Risk R1: never as a defect in the project.

        A committed manifest names a path under `~/.flow/user/` that the
        author has and a teammate may not. Telling the teammate their repo is
        broken would be wrong and unactionable.
        """
        self._project(
            '\n[[replaces]]\ndefault = "standards/testing.md"\nwith = "standards/mine.md"\n'
        )

        section = self._project_section(self.run_flow("doctor").stdout)

        self.assertIn("absent   standards/testing.md -> standards/mine.md", section)
        # The positive property, rather than a blocklist of blame words: the
        # line points at the reader's own overlay as the place the file is
        # missing from, and never at the repo.
        self.assertIn("not in your", section)
        absent_line = next(line for line in section.splitlines() if "not in your" in line)
        self.assertIn(str(self._fake_home / ".flow" / "user"), absent_line)
        self.assertNotIn(str(self.repo / ".flow"), absent_line)

    def test_a_default_naming_no_framework_file_reports_unknown(self) -> None:
        home = self._project(
            '\n[[replaces]]\ndefault = "standards/standrds.md"\nwith = "standards/mine.md"\n'
        )
        self._overlay_standard(home, "mine.md")

        section = self._project_section(self.run_flow("doctor").stdout)

        self.assertIn("unknown  standards/standrds.md", section)
        self.assertIn("nothing resolves that name", section)

    def test_a_wiring_that_escapes_the_overlay_is_reported_invalid(self) -> None:
        self._project(
            '\n[[replaces]]\ndefault = "standards/testing.md"\nwith = "../../../etc/passwd"\n'
        )

        section = self._project_section(self.run_flow("doctor").stdout)

        self.assertIn("invalid  replaces[0]", section)
        self.assertNotIn("/etc/passwd", section)

    def test_mixed_states_are_each_reported_once(self) -> None:
        home = self._project(
            '\n[[replaces]]\ndefault = "standards/testing.md"\nwith = "standards/mine.md"\n'
            '\n[[replaces]]\ndefault = "standards/security.md"\nwith = "standards/gone.md"\n'
            '\n[[replaces]]\ndefault = "standards/nope.md"\nwith = "standards/mine.md"\n'
        )
        self._overlay_standard(home, "mine.md")

        section = self._project_section(self.run_flow("doctor").stdout)

        self.assertIn("replaces:         3 wired", section)
        self.assertEqual(section.count("\n  ok "), 1)
        self.assertEqual(section.count("\n  absent "), 1)
        self.assertEqual(section.count("\n  unknown "), 1)

    def test_a_project_with_no_wiring_prints_no_replaces_line(self) -> None:
        """An optional feature should not announce its absence every run."""
        self._project("")

        section = self._project_section(self.run_flow("doctor").stdout)

        self.assertNotIn("replaces:", section)

    def test_doctor_still_exits_zero_with_every_wiring_broken(self) -> None:
        self._project(
            '\n[[replaces]]\ndefault = "standards/nope.md"\nwith = "../escape.md"\n'
        )

        self.assert_ok(self.run_flow("doctor"))

    def test_a_malformed_manifest_says_so_rather_than_going_quiet(self) -> None:
        """Silence here is indistinguishable from a project with no wirings.

        `manifest:` above is only an existence check, so a corrupt file
        already reports `ok` there. If this block also said nothing, a broken
        manifest would look exactly like a healthy one.
        """
        self.use_fake_home()
        self.setup_project()
        (self.repo / ".flow" / "flow.toml").write_text("[framework\nname = ")

        result = self.run_flow("doctor")

        self.assert_ok(result)
        section = self._project_section(result.stdout)
        self.assertIn("replaces:         cannot be read", section)

    def test_manifest_values_cannot_forge_lines_in_the_report(self) -> None:
        """A committed manifest is data from another repo reaching stdout.

        A newline in a value carries no `..` and is not absolute, so it passes
        every path guard and would otherwise fabricate rows in a report
        someone is about to read by eye.
        """
        self._project(
            '\n[[replaces]]\ndefault = "standards/testing.md"\n'
            'with = "standards/x\\nreplaces:         99 wired"\n'
        )

        section = self._project_section(self.run_flow("doctor").stdout)

        # The injected text survives as escaped characters on one line; what
        # it must never do is become a line of its own.
        header_lines = [ln for ln in section.splitlines() if ln.startswith("replaces:")]
        self.assertEqual(header_lines, ["replaces:         1 wired"])
        self.assertIn("\\n", section)

    def test_invalid_entries_are_not_counted_as_wired(self) -> None:
        self._project(
            '\n[[replaces]]\ndefault = "standards/testing.md"\nwith = "/etc/passwd"\n'
        )

        section = self._project_section(self.run_flow("doctor").stdout)

        self.assertIn("0 wired, 1 invalid", section)

    def test_a_legacy_project_md_heading_is_flagged(self) -> None:
        self._project("")
        (self.repo / ".flow" / "PROJECT.md").write_text(
            "# Project\n\n## Active project standards\n\n- `project/brand.md`\n"
        )

        section = self._project_section(self.run_flow("doctor").stdout)

        self.assertIn("PROJECT.md:", section)
        self.assertIn("Active project standards", section)

    def test_a_current_project_md_is_not_flagged(self) -> None:
        self._project("")

        section = self._project_section(self.run_flow("doctor").stdout)

        self.assertNotIn("PROJECT.md:", section)


class DoctorDriftReportTests(FlowCliHarness):
    """`flow doctor`'s two overlay counts.

    The counts are asserted against hand-written integer literals rather than
    against a re-import of `report.counts()`, because re-deriving the number
    the same way the implementation does passes whenever the arithmetic
    matches itself instead of matching the classifier.
    """

    def _project_section(self, stdout: str) -> str:
        start = stdout.find("-- project:")
        self.assertNotEqual(start, -1, f"no project section in:\n{stdout}")
        end = stdout.find("-- usage:", start)
        return stdout[start:end if end != -1 else len(stdout)]

    def _section(self) -> str:
        return self._project_section(self.run_flow("doctor").stdout)

    def test_a_drifted_only_overlay_is_not_reported_clean(self) -> None:
        """The live case: hypr carried 18 drifted files and read `clean`."""
        self.use_fake_home()
        self.setup_legacy_project()
        # Migrate away everything removable, leaving drift as the only finding.
        self.run_flow("project", "migrate", "--apply", "--yes")
        target = self.repo / ".flow" / "standards" / "testing.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("a standard, but not the framework's\n")

        section = self._section()

        self.assertIn("overlay:          clean", section)
        self.assertIn("drifted:          1 file(s) differ from the framework", section)

    def test_the_drifted_count_is_not_summed_into_the_overlay_count(self) -> None:
        """Summing would make the number unclearable by `flow project
        migrate`, which is the command the overlay line names.

        Asserted on an overlay whose only finding is drift, so the two
        readings differ maximally: `clean` if the counts stay separate, a
        nonzero framework-copy count if they are summed. On a mixed overlay
        both readings print a large number and the test would not bite.
        """
        self.use_fake_home()
        self.setup_legacy_project()
        self.run_flow("project", "migrate", "--apply", "--yes")
        target = self.repo / ".flow" / "standards" / "testing.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("a standard, but not the framework's\n")

        section = self._section()

        overlay = [l for l in section.splitlines() if l.startswith("overlay:")][0]
        drifted = [l for l in section.splitlines() if l.startswith("drifted:")][0]
        self.assertIn("clean", overlay)
        self.assertNotIn("framework copy", overlay)
        self.assertIn("1 file(s) differ from the framework", drifted)

    def test_an_overlay_with_no_drift_prints_no_drifted_line(self) -> None:
        self.use_fake_home()
        self.setup_legacy_project()

        self.assertNotIn("drifted:", self._section())

    def test_a_project_only_file_is_in_neither_count(self) -> None:
        """It is the project's own content, not framework carryover. Folding
        it in would make doctor cry wolf about files it should never mention."""
        self.use_fake_home()
        self.setup_legacy_project()
        self.run_flow("project", "migrate", "--apply", "--yes")
        house = self.repo / ".flow" / "standards" / "house.md"
        house.parent.mkdir(parents=True, exist_ok=True)
        house.write_text("ours\n")

        section = self._section()

        self.assertIn("overlay:          clean", section)
        self.assertNotIn("drifted:", section)

    def test_the_drifted_line_says_the_two_causes_cannot_be_separated(self) -> None:
        """The caveat travels with the count, because the count is what gets
        pasted into a ticket."""
        self.use_fake_home()
        self.setup_legacy_project()
        target = self.repo / ".flow" / "standards" / "testing.md"
        target.write_text(target.read_text() + "\nlocal edit\n")

        section = self._section()

        self.assertIn("customized or stale", section)
        self.assertIn("flow project audit", section)


class ProjectReplacesParseTests(unittest.TestCase):
    """`declared_replaces` — pure parsing of the `[[replaces]]` table."""

    def setUp(self) -> None:
        self.project = load_cli_module("project")

    def test_reads_a_complete_wiring(self) -> None:
        found, rejected = self.project.declared_replaces(
            {
                "replaces": [
                    {
                        "default": "standards/testing.md",
                        "with": "standards/hypr-testing.md",
                        "why": "pytest only, no BDD layer",
                    }
                ]
            }
        )

        self.assertEqual(rejected, [])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].default, "standards/testing.md")
        self.assertEqual(found[0].with_, "standards/hypr-testing.md")
        self.assertEqual(found[0].why, "pytest only, no BDD layer")
        self.assertEqual(found[0].declared_by, "replaces[0]")

    def test_a_missing_table_is_not_an_error(self) -> None:
        self.assertEqual(self.project.declared_replaces({}), ([], []))

    def test_templates_are_wirable_not_only_standards(self) -> None:
        found, rejected = self.project.declared_replaces(
            {"replaces": [{"default": "templates/adr-template.md", "with": "templates/acme-adr.md"}]}
        )

        self.assertEqual(rejected, [])
        self.assertEqual(found[0].default, "templates/adr-template.md")

    def test_order_is_the_manifests_not_sorted(self) -> None:
        found, _ = self.project.declared_replaces(
            {
                "replaces": [
                    {"default": "standards/zebra.md", "with": "standards/z.md"},
                    {"default": "standards/alpha.md", "with": "standards/a.md"},
                ]
            }
        )

        self.assertEqual([w.default for w in found], ["standards/zebra.md", "standards/alpha.md"])

    def test_a_with_that_escapes_the_user_overlay_is_rejected(self) -> None:
        """The one rejection that matters operationally.

        An escaping `with` would otherwise reach a join against
        `USER_OVERLAY_DIR` and resolve somewhere nobody asked for.
        """
        found, rejected = self.project.declared_replaces(
            {"replaces": [{"default": "standards/testing.md", "with": "../../../etc/passwd"}]}
        )

        self.assertEqual(found, [])
        self.assertEqual(len(rejected), 1)
        self.assertIn("escapes the overlay", rejected[0].reason)

    def test_an_absolute_with_is_rejected(self) -> None:
        found, rejected = self.project.declared_replaces(
            {"replaces": [{"default": "standards/testing.md", "with": "/etc/passwd"}]}
        )

        self.assertEqual(found, [])
        self.assertIn("absolute path", rejected[0].reason)

    def test_a_home_relative_with_is_rejected(self) -> None:
        found, rejected = self.project.declared_replaces(
            {"replaces": [{"default": "standards/testing.md", "with": "~/secrets.md"}]}
        )

        self.assertEqual(found, [])
        self.assertIn("home-relative", rejected[0].reason)

    def test_a_missing_field_is_rejected_and_named(self) -> None:
        found, rejected = self.project.declared_replaces(
            {"replaces": [{"default": "standards/testing.md"}]}
        )

        self.assertEqual(found, [])
        self.assertEqual(rejected[0].reason, "missing with")

    def test_a_non_string_field_is_rejected(self) -> None:
        found, rejected = self.project.declared_replaces(
            {"replaces": [{"default": 3, "with": "standards/x.md"}]}
        )

        self.assertEqual(found, [])
        self.assertIn("not a non-empty string", rejected[0].reason)

    def test_a_bad_why_is_dropped_rather_than_disabling_the_wiring(self) -> None:
        """`why` is a comment that happens to have a TOML key."""
        found, rejected = self.project.declared_replaces(
            {"replaces": [{"default": "standards/testing.md", "with": "standards/x.md", "why": 7}]}
        )

        self.assertEqual(rejected, [])
        self.assertEqual(len(found), 1)
        self.assertIsNone(found[0].why)

    def test_one_bad_entry_does_not_discard_the_others(self) -> None:
        found, rejected = self.project.declared_replaces(
            {
                "replaces": [
                    {"default": "standards/a.md", "with": "standards/a2.md"},
                    {"default": "standards/b.md", "with": "/absolute.md"},
                    {"default": "standards/c.md", "with": "standards/c2.md"},
                ]
            }
        )

        self.assertEqual([w.default for w in found], ["standards/a.md", "standards/c.md"])
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].declared_by, "replaces[1]")

    def test_a_default_outside_standards_and_templates_is_rejected(self) -> None:
        """Commands and agents are merged at sync time, not resolved at runtime.

        A wiring naming one would resolve on disk and report healthy while
        nothing honours it — a confident `ok` that ends the reader's
        investigation in the wrong place.
        """
        found, rejected = self.project.declared_replaces(
            {"replaces": [{"default": "commands/flow-plan.md", "with": "standards/mine.md"}]}
        )

        self.assertEqual(found, [])
        self.assertIn("only standards/ and templates/", rejected[0].reason)

    def test_a_bare_filename_is_rejected(self) -> None:
        found, rejected = self.project.declared_replaces(
            {"replaces": [{"default": "testing.md", "with": "standards/mine.md"}]}
        )

        self.assertEqual(found, [])
        self.assertIn("only standards/ and templates/", rejected[0].reason)

    def test_two_wirings_for_the_same_default_are_both_rejected(self) -> None:
        """No tiebreak exists, so neither may silently win.

        First-wins would make resolution depend on manifest order, which
        nothing documents and no role could predict.
        """
        found, rejected = self.project.declared_replaces(
            {
                "replaces": [
                    {"default": "standards/testing.md", "with": "standards/a.md"},
                    {"default": "standards/testing.md", "with": "standards/b.md"},
                    {"default": "standards/other.md", "with": "standards/c.md"},
                ]
            }
        )

        self.assertEqual([w.default for w in found], ["standards/other.md"])
        self.assertEqual(len(rejected), 2)
        self.assertTrue(all("duplicate default" in r.reason for r in rejected))

    def test_the_shipped_commented_example_parses_if_uncommented(self) -> None:
        """Guards the template against drifting away from the parser.

        `setup project` ships the `[[replaces]]` block commented out, which
        means nothing exercises its field names. If the parser ever expected
        different keys, every user following that example would write a
        manifest the tool silently ignores.
        """
        setup = load_cli_module("setup")
        flowtoml = load_cli_module("flowtoml")
        template = setup._PROJECT_MANIFEST_TEMPLATE

        lines = template.splitlines()
        start = next(
            (i for i, line in enumerate(lines) if line.strip() == "# [[replaces]]"),
            None,
        )
        self.assertIsNotNone(start, "template no longer ships a commented [[replaces]] example")
        uncommented = "\n".join(line.lstrip("#").strip() for line in lines[start:] if line.strip())
        parsed = flowtoml.loads(uncommented)
        found, rejected = self.project.declared_replaces(parsed)

        self.assertEqual(rejected, [], f"template example does not parse: {uncommented}")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].default, "standards/testing.md")


class ProjectReplacesResolveTests(unittest.TestCase):
    """`resolve_replaces` — the three states doctor reports."""

    def setUp(self) -> None:
        self.project = load_cli_module("project")
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.scaffold = root / "scaffold"
        self.overlay = root / "overlay"
        (self.scaffold / "standards").mkdir(parents=True)
        (self.overlay / "standards").mkdir(parents=True)
        (self.scaffold / "standards" / "testing.md").write_text("framework testing\n")

    def _wire(self, default: str, with_: str):
        return self.project.ReplaceWiring(default, with_, None, "replaces[0]")

    def _status(self, default: str, with_: str) -> str:
        return self.project.resolve_replaces(
            [self._wire(default, with_)], self.scaffold, self.overlay
        )[0].status

    def test_ok_when_the_replacement_is_in_the_user_overlay(self) -> None:
        (self.overlay / "standards" / "mine.md").write_text("mine\n")

        self.assertEqual(
            self._status("standards/testing.md", "standards/mine.md"),
            self.project.REPLACE_OK,
        )

    def test_absent_when_the_replacement_is_not_on_this_machine(self) -> None:
        self.assertEqual(
            self._status("standards/testing.md", "standards/mine.md"),
            self.project.REPLACE_ABSENT,
        )

    def test_unknown_when_the_default_names_no_framework_file(self) -> None:
        (self.overlay / "standards" / "mine.md").write_text("mine\n")

        self.assertEqual(
            self._status("standards/standrds-typo.md", "standards/mine.md"),
            self.project.REPLACE_UNKNOWN,
        )

    def test_a_typo_in_default_outranks_a_missing_replacement(self) -> None:
        """Wrong in both ways at once reports the fixable one.

        `absent` sends the reader to their own overlay; `unknown` sends them
        to the manifest line that can never match. The second is the defect.
        """
        self.assertEqual(
            self._status("standards/nope.md", "standards/also-nope.md"),
            self.project.REPLACE_UNKNOWN,
        )

    def test_a_default_the_user_overlay_introduces_is_not_unknown(self) -> None:
        """Rule 2 lets the user overlay add standards the framework never shipped.

        Checking only the scaffold would call every wiring for one of those a
        typo, and send the reader to fix a manifest that is correct.
        """
        (self.overlay / "standards" / "house-only.md").write_text("house\n")
        (self.overlay / "standards" / "mine.md").write_text("mine\n")

        self.assertEqual(
            self._status("standards/house-only.md", "standards/mine.md"),
            self.project.REPLACE_OK,
        )

    def test_a_directory_is_not_a_resolution(self) -> None:
        (self.overlay / "standards" / "mine.md").mkdir()

        self.assertEqual(
            self._status("standards/testing.md", "standards/mine.md"),
            self.project.REPLACE_ABSENT,
        )

    def test_every_wiring_gets_exactly_one_verdict_in_order(self) -> None:
        (self.overlay / "standards" / "here.md").write_text("here\n")
        wirings = [
            self._wire("standards/testing.md", "standards/here.md"),
            self._wire("standards/testing.md", "standards/gone.md"),
            self._wire("standards/typo.md", "standards/here.md"),
        ]

        resolved = self.project.resolve_replaces(wirings, self.scaffold, self.overlay)

        self.assertEqual(
            [r.status for r in resolved],
            [self.project.REPLACE_OK, self.project.REPLACE_ABSENT, self.project.REPLACE_UNKNOWN],
        )


class ResolutionOrderDocumentationTests(unittest.TestCase):
    """The resolution order in `FRAMEWORK.md` is the whole implementation.

    Honouring a `[[replaces]]` wiring is a prompt convention: no code makes a
    role obey it, so this prose is the feature. It is also the only part of
    the slice nothing else can fail on, which is exactly why it needs pinning.
    """

    def setUp(self) -> None:
        text = (REPO_ROOT / "scaffolds" / "default" / "FRAMEWORK.md").read_text()
        start = text.find("## Overlay resolution for standards and templates")
        self.assertNotEqual(start, -1, "resolution section was renamed or removed")
        end = text.find("\n## ", start + 1)
        self.section = text[start:end if end != -1 else len(text)]

    def test_the_order_has_exactly_three_levels(self) -> None:
        numbered = re.findall(r"(?m)^(\d)\. \*\*", self.section)

        self.assertEqual(numbered, ["1", "2", "3"])

    def test_the_retired_project_standards_path_appears_nowhere(self) -> None:
        for retired in ("<repo>/.flow/standards/", "<repo>/.flow/templates/"):
            self.assertNotIn(retired, self.section)

    def test_project_wiring_is_first_and_names_the_manifest(self) -> None:
        self.assertIn("1. **Project wiring**", self.section)
        self.assertIn("[[replaces]]", self.section)
        self.assertIn(".flow/flow.toml", self.section)

    def test_the_absent_case_has_a_stated_fallback(self) -> None:
        """The modal path on any machine but the author's.

        Without this the agent is told to read the replacement and never told
        what to do when it is not there.
        """
        self.assertIn("fall back to rule 2", self.section)

    def test_stacking_names_which_level_wins(self) -> None:
        self.assertIn("nearest", self.section)

    def test_the_wirable_kinds_are_stated(self) -> None:
        self.assertIn("Only `standards/` and `templates/` names are wirable", self.section)


class LegacyProjectHeadingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.project = load_cli_module("project")

    def test_detects_the_retired_heading(self) -> None:
        self.assertTrue(
            self.project.has_legacy_active_standards_heading(
                "# Project\n\n## Active project standards\n\n- project/brand.md\n"
            )
        )

    def test_does_not_fire_on_a_current_project_md(self) -> None:
        self.assertFalse(
            self.project.has_legacy_active_standards_heading(
                (REPO_ROOT / "scaffolds" / "default" / "PROJECT.md").read_text()
            )
        )


class ProjectAuditClassifierTests(unittest.TestCase):
    """`classify_tree` and friends, against two synthetic trees.

    No subprocess and no fabricated HOME, which is possible only because both
    roots are parameters. That also defuses the trap this suite invites: with
    `use_fake_home()` the fake `~/.flow/source` is a symlink to `REPO_ROOT`, so
    a test that seeds a project file by *copying* it from the real scaffold and
    then asserts `identical` is comparing a file to itself. It passes against a
    classifier hardcoded to return `identical`.

    So: nothing here copies, and where two sides must be byte-equal they are
    written from two separate literals rather than one shared variable. Where a
    variable *is* shared, one side is mutated — which is what proves the
    comparison reads both trees rather than one.
    """

    CAPABILITY_DIRS = ("agents", "commands", "project", "standards", "templates")

    def setUp(self) -> None:
        self.project = load_cli_module("project")
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.flow_dir = root / "someproject" / ".flow"
        self.scaffold_dir = root / "framework" / "scaffolds" / "default"
        for name in self.CAPABILITY_DIRS:
            (self.flow_dir / name).mkdir(parents=True)
            (self.scaffold_dir / name).mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def put(self, root: Path, rel: str, text: str) -> Path:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def in_project(self, rel: str, text: str) -> Path:
        return self.put(self.flow_dir, rel, text)

    def in_framework(self, rel: str, text: str) -> Path:
        return self.put(self.scaffold_dir, rel, text)

    def audit(self):
        return self.project.audit_project(self.flow_dir, self.scaffold_dir)

    def buckets(self) -> dict:
        return {f.rel: f.bucket for f in self.audit().findings}

    # -- byte comparison ------------------------------------------------

    def test_identical_when_bytes_match(self) -> None:
        # Two literals, not one variable used twice: a shared variable is
        # byte-equal by construction and proves nothing about the comparator.
        self.in_project("standards/testing.md", "# Testing\n\nProve it.\n")
        self.in_framework("standards/testing.md", "# Testing\n\nProve it.\n")
        self.assertEqual(self.buckets()["standards/testing.md"], "identical")

    def test_differs_on_a_single_byte(self) -> None:
        """A trailing newline is the realistic drift. Being falsely lenient here
        is the direction that gets a real customization deleted later."""
        body = "# Testing\n\nProve it."
        self.in_project("standards/testing.md", body)
        self.in_framework("standards/testing.md", body + "\n")
        self.assertEqual(self.buckets()["standards/testing.md"], "differs")

    def test_identical_requires_exact_bytes_not_normalized_text(self) -> None:
        body = "line one\nline two\n"
        self.in_project("standards/eol.md", body.replace("\n", "\r\n"))
        self.in_framework("standards/eol.md", body)
        self.assertEqual(
            self.buckets()["standards/eol.md"],
            "differs",
            "CRLF vs LF must not be normalized away — identical is the bucket a "
            "later migration deletes",
        )

    # -- buckets --------------------------------------------------------

    def test_project_only_when_the_framework_has_no_counterpart(self) -> None:
        self.in_project("standards/house-style.md", "local only\n")
        self.assertEqual(self.buckets()["standards/house-style.md"], "project-only")

    def test_orphaned_when_the_manifest_declares_an_absent_file(self) -> None:
        self.in_project(
            "flow.toml", '[[agents]]\nname = "ghost"\nsource = "agents/ghost.md"\n'
        )
        finding = next(
            f for f in self.audit().findings if f.rel == "agents/ghost.md"
        )
        self.assertEqual(finding.bucket, "orphaned")
        self.assertEqual(finding.declared_by, ("agents.ghost.source",))

    def test_a_declared_file_that_exists_is_never_orphaned(self) -> None:
        """Existence wins over declaration.

        A classifier that checked "declared?" before "present?" would report a
        customized file as orphaned, and a later manifest rewrite would drop an
        entry that resolves perfectly well.
        """
        self.in_project(
            "flow.toml", '[[agents]]\nname = "sre"\nsource = "agents/sre.md"\n'
        )
        self.in_project("agents/sre.md", "customized\n")
        self.in_framework("agents/sre.md", "framework\n")
        found = [f for f in self.audit().findings if f.rel == "agents/sre.md"]
        self.assertEqual([f.bucket for f in found], ["differs"])

    def test_conflict_when_the_project_has_a_directory_where_the_framework_has_a_file(
        self,
    ) -> None:
        """Without this branch the byte comparison raises IsADirectoryError and
        one odd path kills the whole audit."""
        self.in_framework("FRAMEWORK.md", "the framework file\n")
        (self.flow_dir / "FRAMEWORK.md").mkdir()
        self.assertEqual(self.buckets()["FRAMEWORK.md"], "conflict")

    def test_project_stub_is_identical_while_unfilled_and_differs_once_filled(
        self,
    ) -> None:
        """`project/` holds framework-supplied stubs, so the plausible shortcut
        "project/ is user content, therefore always project-only" is wrong in
        both directions."""
        self.in_framework("project/architecture.md", "<describe the architecture>\n")
        self.in_project("project/architecture.md", "<describe the architecture>\n")
        self.assertEqual(self.buckets()["project/architecture.md"], "identical")

        self.in_project("project/architecture.md", "It is a modular monolith.\n")
        self.assertEqual(self.buckets()["project/architecture.md"], "differs")

    def test_bucket_membership_is_not_invariant_under_a_label_swap(self) -> None:
        """Two members per bucket, and named. A one-per-bucket fixture passes
        unchanged if two labels are swapped."""
        for rel in ("standards/a.md", "standards/b.md"):
            self.in_project(rel, "project side\n")
            self.in_framework(rel, "framework side\n")
        for rel in ("standards/c.md", "standards/d.md"):
            self.in_project(rel, "local only\n")

        buckets = self.buckets()
        counts = self.audit().counts()
        self.assertEqual(counts["differs"], 2)
        self.assertEqual(counts["project-only"], 2)
        self.assertEqual(buckets["standards/a.md"], "differs")
        self.assertEqual(buckets["standards/b.md"], "differs")
        self.assertEqual(buckets["standards/c.md"], "project-only")
        self.assertEqual(buckets["standards/d.md"], "project-only")

    # -- scope ----------------------------------------------------------

    def test_only_capability_paths_are_walked(self) -> None:
        """The safety property. A naive walk of `.flow/` passes every other test
        in this class while silently over-scanning — and what this scanner
        visits is what a later migration is allowed to delete."""
        self.in_project("memory/STATE.md", "in flight: something\n")
        self.in_project("runs/2026-01-01/run.md", "a run artifact\n")
        self.in_project("PROJECT.md", "the project's own context\n")
        self.in_project("flow.toml", "# a manifest unlike the framework's\n")
        self.in_framework("PROJECT.md", "the framework's stub\n")
        self.in_framework("flow.toml", "# the framework manifest\n")
        self.in_project("standards/real.md", "scanned\n")

        rels = {f.rel for f in self.audit().findings}
        self.assertIn("standards/real.md", rels)
        for excluded in ("memory/STATE.md", "runs/2026-01-01/run.md", "PROJECT.md", "flow.toml"):
            self.assertNotIn(excluded, rels, f"{excluded} must never be classified")

    def test_flow_toml_is_manifest_input_and_not_a_candidate(self) -> None:
        """It differs from the framework's copy in every real project, so a
        scanner that classified it would report a permanent false positive."""
        self.in_project(
            "flow.toml", '[[agents]]\nname = "ghost"\nsource = "agents/ghost.md"\n'
        )
        self.in_framework("flow.toml", "# entirely different\n")
        report = self.audit()
        self.assertNotIn("flow.toml", {f.rel for f in report.findings})
        self.assertIn("agents/ghost.md", {f.rel for f in report.findings})

    def test_noise_files_are_not_counted(self) -> None:
        """A stray .DS_Store is harmless but pollutes the count being diffed
        against a hand audit."""
        self.in_project("standards/.DS_Store", "\x00\x01")
        self.in_project("standards/real.md", "counted\n")
        self.assertEqual(self.audit().classified(), 1)

    def test_a_project_with_no_capability_directories_reports_nothing(self) -> None:
        for name in self.CAPABILITY_DIRS:
            shutil.rmtree(self.flow_dir / name)
        report = self.audit()
        self.assertEqual(report.findings, [])
        self.assertEqual(report.classified(), 0)
        self.assertTrue(report.has_baseline, "the framework side is still intact")

    def test_no_framework_baseline_refuses_to_report_buckets(self) -> None:
        """Otherwise a pruned or half-installed framework makes every project
        file project-only while the report looks clean."""
        for name in self.CAPABILITY_DIRS:
            shutil.rmtree(self.scaffold_dir / name)
        self.in_project("standards/real.md", "would be misreported\n")
        report = self.audit()
        self.assertFalse(report.has_baseline)
        rendered = self.project.render_audit(report)
        self.assertIn("no framework baseline", rendered)
        self.assertNotIn("project-only (", rendered)


    def test_a_path_declared_at_two_sites_reports_both(self) -> None:
        """The scaffold declares `commands/flow-boot.md` under both
        `[[claude.commands]]` and `[[codex.commands]]`. One finding, two sites:
        a rewrite told about only one leaves the other pointing at a file it
        just deleted."""
        self.in_project(
            "flow.toml",
            '[[claude.commands]]\nname = "boot"\nsource = "commands/boot.md"\n'
            '[[codex.commands]]\nname = "boot"\nsource = "commands/boot.md"\n',
        )
        found = [f for f in self.audit().findings if f.rel == "commands/boot.md"]
        self.assertEqual(len(found), 1, "one path, one finding")
        self.assertEqual(
            found[0].declared_by,
            ("claude.commands.boot.source", "codex.commands.boot.source"),
        )

    def test_a_symlink_is_never_classified(self) -> None:
        """The safety contract in one test.

        Every finding's `rel` must be safe to join against the overlay root,
        because the consumer of these findings deletes what they name. A
        symlinked capability directory produces innocuous-looking keys that
        resolve outside the overlay entirely — `rglob` declines to descend into
        a nested symlinked directory, but it does follow the capability path
        itself.
        """
        outside = Path(self._tmp.name) / "outside"
        outside.mkdir()
        (outside / "secret.md").write_text("not in the overlay\n")

        (self.flow_dir / "standards" / "link.md").symlink_to(outside / "secret.md")
        (self.flow_dir / "agents").rmdir()
        (self.flow_dir / "agents").symlink_to(outside)

        report = self.audit()
        for finding in report.findings:
            resolved = (self.flow_dir / finding.rel).resolve()
            self.assertTrue(
                resolved.is_relative_to(self.flow_dir.resolve()),
                f"{finding.rel} resolves outside the overlay, to {resolved}",
            )
        self.assertNotIn("agents/secret.md", {f.rel for f in report.findings})
        self.assertEqual(report.symlinks, ["agents", "standards/link.md"])

    def test_a_broken_symlink_at_a_capability_path_is_reported_not_dropped(
        self,
    ) -> None:
        """`exists()` is False for a dangling link, so an ordering that checked
        it first would skip the path with no trace while `classified N` still
        looked healthy."""
        (self.flow_dir / "templates").rmdir()
        (self.flow_dir / "templates").symlink_to(
            Path(self._tmp.name) / "nothing-here"
        )
        self.assertIn("templates", self.audit().symlinks)

    def test_an_unreadable_file_gets_a_bucket_rather_than_a_traceback(self) -> None:
        """mode 000 is the ordinary cause. Crashing would break the one promise
        the command makes — that it is safe to run anywhere — and silently
        skipping is worse, because a path with no bucket is indistinguishable
        from a path that is not there."""
        target = self.in_project("standards/locked.md", "secret\n")
        self.in_framework("standards/locked.md", "framework\n")
        target.chmod(0o000)
        try:
            self.assertEqual(self.buckets()["standards/locked.md"], "unreadable")
        finally:
            target.chmod(0o644)

    def test_a_home_relative_declaration_is_rejected(self) -> None:
        """`~/x` is neither absolute nor contains `..`, so it passes both
        guards and lands as an ordinary relative key — right up until one
        consumer calls expanduser."""
        _, rejected = self.project.declared_sources(
            {"agents": [{"name": "h", "source": "~/.ssh/id_rsa"}]}
        )
        self.assertEqual([r.declared_value for r in rejected], ["~/.ssh/id_rsa"])

    def test_control_characters_cannot_fabricate_report_rows(self) -> None:
        """A manifest source containing a newline carries no `..` and is not
        absolute, so it reaches the renderer as an ordinary value."""
        self.in_project(
            "flow.toml",
            '[[agents]]\nname = "x"\nsource = "agents/a\\nfake-bucket (99).md"\n',
        )
        rendered = self.project.render_audit(self.audit())
        self.assertNotIn("\nfake-bucket (99)", rendered)
        self.assertIn("\\n", rendered)

    def test_no_baseline_withholds_findings_from_the_payload_too(self) -> None:
        """The renderer refusing to print buckets while `--json` still shipped
        them would make the doc's claim false for every machine consumer."""
        for name in self.CAPABILITY_DIRS:
            shutil.rmtree(self.scaffold_dir / name)
        self.in_project("standards/real.md", "would be misreported\n")
        payload = self.project.audit_payload(self.audit())
        self.assertFalse(payload["has_baseline"])
        self.assertEqual(payload["findings"], [])
        self.assertEqual(payload["classified"], 0)

    def test_payload_records_whether_the_installed_framework_was_used(self) -> None:
        """`--scaffold` pointed at the project's own overlay makes every file
        `identical`, which is the bucket a migration deletes. The answer travels
        with the report rather than being reconstructed downstream."""
        self.assertFalse(self.project.audit_payload(self.audit())["default_scaffold"])

    # -- render / payload -----------------------------------------------

    def test_render_carries_the_differs_caveat_with_the_count(self) -> None:
        """The one literal-string assertion that earns its keep: this count gets
        pasted into a ticket, and a later migration keys off this label."""
        self.in_project("standards/x.md", "one\n")
        self.in_framework("standards/x.md", "two\n")
        rendered = self.project.render_audit(self.audit())
        self.assertIn("differs (1)", rendered)
        self.assertIn("cannot be told apart locally", rendered)

    def test_render_names_what_it_did_not_scan(self) -> None:
        """Without it, a 71-file .flow reporting 48 scanned reads as a broken
        scanner rather than a deliberate scope."""
        rendered = self.project.render_audit(self.audit())
        for excluded in ("PROJECT.md", "flow.toml", "memory/", "runs/"):
            self.assertIn(excluded, rendered)

    def test_payload_keeps_roots_out_of_the_findings(self) -> None:
        """An absolute path inside a finding is how a later `--apply` acts
        outside the root it was pointed at."""
        self.in_project("standards/x.md", "one\n")
        payload = self.project.audit_payload(self.audit())
        self.assertEqual(payload["flow_dir"], str(self.flow_dir))
        for finding in payload["findings"]:
            self.assertEqual(set(finding), {"rel", "bucket", "declared_by"})
            self.assertFalse(finding["rel"].startswith("/"))
            self.assertNotIn(str(self.flow_dir), finding["rel"])


class ProjectAuditCommandTests(FlowCliHarness):
    """`flow project audit` through the real entrypoint.

    The classifier is unit-tested against synthetic trees elsewhere; these
    exercise the parts only a subprocess reaches — root resolution, the
    flow-home guard, exit codes, and JSON.
    """

    def audit(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return self.run_flow("project", "audit", *extra)

    def test_a_self_pointed_scaffold_says_so(self) -> None:
        """The one reading of this report that actively misleads.

        Compared against its own tree every file is byte-equal to itself, so
        `identical` fills up and the report reads as an invitation to migrate
        — which `flow project migrate` then refuses. Audit still performs the
        comparison, because it deletes nothing; it just has to say what it is
        looking at.
        """
        self.use_fake_home()
        self.setup_legacy_project()
        flow_dir = self.repo / ".flow"

        result = self.audit("--scaffold", str(flow_dir))

        self.assert_ok(result)
        self.assertIn("names this project's own tree", result.stdout)
        self.assertIn("migrate` refuses", result.stdout)

    def test_a_scaffold_inside_the_overlay_hits_the_baseline_guard_first(self) -> None:
        """Not the overlap notice, and that is the right answer.

        A subdirectory of the overlay holds no capability directories, so the
        no-baseline guard returns before the notice is reached. Its message is
        the more specific of the two. Pinned so nobody "fixes" the notice to
        fire here and buries the better diagnosis under it.

        Migrate differs deliberately: its guard runs in `resolve_roots`,
        upstream of the baseline check, because there the wrong answer deletes
        the overlay rather than printing a table.
        """
        self.use_fake_home()
        self.setup_legacy_project()

        result = self.audit("--scaffold", str(self.repo / ".flow" / "standards"))

        self.assertIn("no framework baseline", result.stdout)
        self.assertNotIn("own tree", result.stdout)

    def test_a_normal_audit_prints_no_overlap_notice(self) -> None:
        """It has to stay quiet on every ordinary run or it becomes noise."""
        self.use_fake_home()
        self.setup_legacy_project()

        self.assertNotIn("own tree", self.audit().stdout)

    def test_a_distinct_scaffold_prints_no_overlap_notice(self) -> None:
        """A non-default scaffold is not by itself an overlap. Without this
        the notice can be implemented as `not default_scaffold`, which would
        fire on every legitimate override."""
        self.use_fake_home()
        self.setup_legacy_project()
        other = self.repo / "other-scaffold"
        shutil.copytree(REPO_ROOT / "scaffolds" / "default", other)

        result = self.audit("--scaffold", str(other))

        self.assert_ok(result)
        self.assertNotIn("own tree", result.stdout)

    def snapshot(self) -> dict:
        """Every path under the project, with content hash and mtime.

        The *set* of paths is part of the snapshot, not just hashes of a fixed
        list: re-hashing paths captured beforehand cannot see a file the command
        created or deleted, which is half of what report-only has to mean.
        """
        state = {}
        for path in sorted((self.repo / ".flow").rglob("*")):
            rel = path.relative_to(self.repo).as_posix()
            if path.is_dir():
                state[rel] = ("dir", None)
            else:
                stat = path.stat()
                state[rel] = (
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    stat.st_mtime_ns,
                )
        return state

    def test_exits_zero_on_a_mixed_report(self) -> None:
        self.use_fake_home()
        self.setup_legacy_project()
        (self.repo / ".flow" / "standards" / "testing.md").write_text("edited\n")
        (self.repo / ".flow" / "standards" / "house.md").write_text("ours\n")

        result = self.audit()
        self.assert_ok(result)
        self.assertIn("standards/testing.md", result.stdout)
        self.assertIn("standards/house.md", result.stdout)

    def test_exits_zero_even_when_every_file_differs(self) -> None:
        """A single happy-path exit-0 assertion cannot tell "always 0" from "0
        this time". Contamination is the normal state of an old project, so the
        worst-looking input must still be a successful run."""
        self.use_fake_home()
        self.setup_legacy_project()
        for path in (self.repo / ".flow" / "standards").rglob("*.md"):
            path.write_text("clobbered\n")

        result = self.audit()
        self.assert_ok(result)
        self.assertNotIn("differs (0)", result.stdout)

    def test_makes_no_filesystem_changes(self) -> None:
        """Report-only asserted as behavior, not as the absence of an --apply
        flag in argparse."""
        self.use_fake_home()
        self.setup_legacy_project()
        (self.repo / ".flow" / "standards" / "house.md").write_text("ours\n")

        before = self.snapshot()
        self.assert_ok(self.audit())
        self.assert_ok(self.audit("--json"))
        after = self.snapshot()

        self.assertEqual(
            set(before), set(after), "the audit added or removed a path"
        )
        self.assertEqual(before, after, "the audit changed content or mtimes")

    def test_classifies_something_in_every_capability_directory(self) -> None:
        """Catches a classifier wired only to standards/, which every
        single-directory fixture would let through."""
        self.use_fake_home()
        self.setup_legacy_project()
        flow_dir = self.repo / ".flow"
        for name in ("agents", "commands", "project", "standards", "templates"):
            (flow_dir / name).mkdir(parents=True, exist_ok=True)
            (flow_dir / name / "zz-local.md").write_text(f"local to {name}\n")

        result = self.audit()
        self.assert_ok(result)
        for name in ("agents", "commands", "project", "standards", "templates"):
            self.assertIn(f"{name}/zz-local.md", result.stdout)

    def test_refuses_to_audit_flow_s_own_home(self) -> None:
        """`repo_root` falls back to the working directory, so from $HOME the
        `.flow` it finds is flow's own home. Reporting the entire framework as
        project-only is the failure being prevented."""
        fake_home = self.use_fake_home()
        result = self.audit("--root", str(fake_home / ".flow"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("flow's own home", result.stdout)

    def test_refuses_a_root_that_is_not_a_directory(self) -> None:
        self.use_fake_home()
        self.setup_legacy_project()
        result = self.audit("--root", str(self.repo / ".flow" / "flow.toml"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("not a directory", result.stdout)

    def test_refuses_when_the_repo_has_no_overlay(self) -> None:
        self.use_fake_home()
        result = self.audit()
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing .flow", result.stdout)

    def test_json_carries_the_same_counts_as_the_table(self) -> None:
        self.use_fake_home()
        self.setup_legacy_project()
        (self.repo / ".flow" / "standards" / "house.md").write_text("ours\n")

        rendered = self.audit()
        payload = self.audit("--json")
        self.assert_ok(rendered)
        self.assert_ok(payload)

        data = json.loads(payload.stdout)
        self.assertTrue(data["has_baseline"])
        for bucket, count in data["counts"].items():
            self.assertIn(f"{bucket} ({count})", rendered.stdout)
        self.assertIn(
            {"rel": "standards/house.md", "bucket": "project-only", "declared_by": []},
            data["findings"],
        )

    def test_json_findings_carry_no_absolute_paths(self) -> None:
        self.use_fake_home()
        self.setup_legacy_project()
        data = json.loads(self.audit("--json").stdout)
        self.assertTrue(data["findings"], "fixture produced nothing to check")
        for finding in data["findings"]:
            self.assertFalse(finding["rel"].startswith("/"), finding)

    def test_an_orphaned_declaration_is_reported_with_its_site(self) -> None:
        self.use_fake_home()
        self.setup_legacy_project()
        manifest = self.repo / ".flow" / "flow.toml"
        manifest.write_text(
            manifest.read_text()
            + '\n[[agents]]\nname = "ghost"\nsource = "agents/ghost.md"\n'
        )
        result = self.audit()
        self.assert_ok(result)
        self.assertIn("agents/ghost.md", result.stdout)
        self.assertIn("agents.ghost.source", result.stdout)

    def test_exits_one_and_reports_nothing_without_a_framework_baseline(self) -> None:
        """The no-baseline path through the real CLI, not just the renderer."""
        self.use_fake_home()
        self.setup_legacy_project()
        empty = self.repo / "empty-framework"
        empty.mkdir()

        result = self.audit("--scaffold", str(empty))
        self.assertEqual(result.returncode, 1)
        self.assertIn("no framework baseline", result.stdout)
        self.assertNotIn("identical (", result.stdout)

        payload = self.audit("--scaffold", str(empty), "--json")
        self.assertEqual(payload.returncode, 1)
        self.assertEqual(json.loads(payload.stdout)["findings"], [])

    def test_refuses_a_root_inside_flow_s_own_home(self) -> None:
        """Equality on the flow-home path alone would let `--root
        ~/.flow/user` through, auditing framework content as a project."""
        fake_home = self.use_fake_home()
        inside = fake_home / ".flow" / "user"
        inside.mkdir(parents=True)
        result = self.audit("--root", str(inside))
        self.assertEqual(result.returncode, 1)
        self.assertIn("flow's own home", result.stdout)


class WriteAtomicTests(unittest.TestCase):
    """`fsutil.write_atomic` — the primitive the migration's manifest rewrite
    depends on."""

    def setUp(self) -> None:
        self.fsutil = load_cli_module("fsutil")
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_replaces_existing_content(self) -> None:
        target = self.root / "f.toml"
        target.write_text("before\n")
        self.fsutil.write_atomic(target, "after\n")
        self.assertEqual(target.read_text(), "after\n")

    def test_creates_the_parent_directory(self) -> None:
        """`os.replace` raises on a missing parent, and `.claude/settings.json`
        can have none."""
        target = self.root / "deep" / "nested" / "f.json"
        self.fsutil.write_atomic(target, "{}\n")
        self.assertEqual(target.read_text(), "{}\n")

    def test_preserves_the_existing_file_mode(self) -> None:
        """mkstemp creates 0600, so without this a rewritten settings.json
        silently becomes owner-only."""
        target = self.root / "f.json"
        target.write_text("{}\n")
        target.chmod(0o644)
        self.fsutil.write_atomic(target, '{"a": 1}\n')
        self.assertEqual(target.stat().st_mode & 0o777, 0o644)

    def test_a_new_file_is_not_owner_only(self) -> None:
        target = self.root / "new.txt"
        self.fsutil.write_atomic(target, "x\n")
        self.assertEqual(target.stat().st_mode & 0o777, 0o644)

    def test_an_explicit_mode_wins(self) -> None:
        target = self.root / "script.sh"
        self.fsutil.write_atomic(target, "#!/bin/sh\n", mode=0o755)
        self.assertEqual(target.stat().st_mode & 0o777, 0o755)

    def test_the_temp_file_lives_beside_the_target(self) -> None:
        """`os.replace` is atomic only within a filesystem. A temp file under
        /tmp is a different mount on many systems and the rename raises EXDEV.

        Asserted by observing where the temp file is created, not by reading the
        source — a test that greps for `dir=` would pass against a comment.
        """
        target = self.root / "sub" / "f.toml"
        target.parent.mkdir()
        seen: list[str] = []
        real_mkstemp = tempfile.mkstemp

        def spy(*args, **kwargs):
            seen.append(str(kwargs.get("dir")))
            return real_mkstemp(*args, **kwargs)

        self.fsutil.tempfile.mkstemp = spy
        try:
            self.fsutil.write_atomic(target, "x\n")
        finally:
            self.fsutil.tempfile.mkstemp = real_mkstemp
        self.assertEqual(seen, [str(target.parent)])

    def test_a_failed_write_leaves_the_original_and_no_debris(self) -> None:
        """The caller must not be able to believe a write succeeded. A migration
        that deletes files on the strength of a manifest rewrite that silently
        failed is the worst outcome this whole slice can produce."""
        target = self.root / "f.toml"
        target.write_text("original\n")

        class Boom(Exception):
            pass

        real_replace = os.replace

        def exploding_replace(*args, **kwargs):
            raise Boom("simulated crash between write and rename")

        self.fsutil.os.replace = exploding_replace
        try:
            with self.assertRaises(Boom):
                self.fsutil.write_atomic(target, "never lands\n")
        finally:
            self.fsutil.os.replace = real_replace

        self.assertEqual(target.read_text(), "original\n")
        self.assertEqual(
            sorted(p.name for p in self.root.iterdir()),
            ["f.toml"],
            "a temp file was left behind",
        )


class ManifestSurgeryTests(unittest.TestCase):
    """Editing `flow.toml` as text rather than parsing and re-serializing it.

    There is no TOML writer in this codebase — `cli/flowtoml.py` only reads, and
    its fallback parser drops comments and formatting and raises on value types
    it does not know. A round-trip would rewrite the hand-annotated scaffold
    manifest into something else, so the migration cuts line ranges out of the
    original bytes. These tests exist to prove that stays true.
    """

    def setUp(self) -> None:
        self.migrate = load_cli_module("migrate")
        self.project = load_cli_module("project")
        self.scaffold_manifest = (
            REPO_ROOT / "scaffolds" / "default" / "flow.toml"
        ).read_text()

    def sites_in(self, text: str) -> set:
        found, _ = self.project.declared_sources(
            load_cli_module("flowtoml").parse_simple_toml(text)
        )
        return {d.declared_by for d in found}

    def test_cutting_an_array_entry_removes_that_block_and_nothing_else(self) -> None:
        text = (
            '# a comment that must survive\n'
            '\n'
            '[[agents]]\n'
            'name = "keep"\n'
            'source = "agents/keep.md"\n'
            '\n'
            '[[agents]]\n'
            'name = "drop"\n'
            'source = "agents/drop.md"\n'
            '\n'
            '[[agents]]\n'
            'name = "also-keep"\n'
            'source = "agents/also-keep.md"\n'
        )
        edits, unresolved = self.migrate.plan_manifest_edits(
            text, ["agents.drop.source"]
        )
        self.assertEqual(unresolved, [])
        result = self.migrate.apply_manifest_edits(text, edits)
        self.assertNotIn("drop", result)
        self.assertIn("# a comment that must survive", result)
        self.assertIn('name = "keep"', result)
        self.assertIn('name = "also-keep"', result)

    def test_cutting_a_standards_key_leaves_the_rest_of_the_table(self) -> None:
        """A `[standards.x]` table can carry `spec` and `upstream` that outlive
        the source going away, so only the offending key line is cut."""
        text = (
            "[standards.git-commits]\n"
            'spec = "Conventional Commits"\n'
            'upstream = "https://example.invalid"\n'
            'flow_standard = "standards/git-commits.md"\n'
        )
        edits, unresolved = self.migrate.plan_manifest_edits(
            text, ["standards.git-commits.flow_standard"]
        )
        self.assertEqual(unresolved, [])
        self.assertEqual([e.kind for e in edits], ["key"])
        result = self.migrate.apply_manifest_edits(text, edits)
        self.assertNotIn("flow_standard", result)
        self.assertIn("[standards.git-commits]", result)
        self.assertIn('spec = "Conventional Commits"', result)
        self.assertIn("upstream", result)

    def test_a_key_whose_name_is_a_prefix_of_another_is_not_confused(self) -> None:
        """`flow_standard` and `flow_standard_extra` both start with the same
        text; a `startswith` match without the `=` split would cut the wrong
        line."""
        text = (
            "[standards.x]\n"
            'flow_standard_extra = "keep me"\n'
            'flow_standard = "standards/x.md"\n'
        )
        edits, _ = self.migrate.plan_manifest_edits(
            text, ["standards.x.flow_standard"]
        )
        result = self.migrate.apply_manifest_edits(text, edits)
        self.assertIn("flow_standard_extra", result)
        self.assertNotIn('flow_standard = ', result)

    def test_an_unresolvable_site_is_reported_never_guessed(self) -> None:
        """The alternative is cutting a range chosen by a near-miss, in a file
        the user hand-annotated."""
        text = '[[agents]]\nname = "real"\nsource = "agents/real.md"\n'
        edits, unresolved = self.migrate.plan_manifest_edits(
            text, ["agents.ghost.source"]
        )
        self.assertEqual(edits, [])
        self.assertEqual(unresolved, ["agents.ghost.source"])
        self.assertEqual(self.migrate.apply_manifest_edits(text, edits), text)

    def test_overlapping_edits_are_refused_not_merged(self) -> None:
        edit = self.migrate.ManifestEdit
        with self.assertRaises(ValueError):
            self.migrate.apply_manifest_edits(
                "a\nb\nc\nd\n",
                [edit("one", 0, 3, "entry"), edit("two", 1, 4, "entry")],
            )

    def test_an_unnamed_entry_is_matched_by_position(self) -> None:
        text = (
            '[[agents]]\nsource = "agents/zero.md"\n'
            '\n'
            '[[agents]]\nsource = "agents/one.md"\n'
        )
        edits, unresolved = self.migrate.plan_manifest_edits(text, ["agents.[1].source"])
        self.assertEqual(unresolved, [])
        result = self.migrate.apply_manifest_edits(text, edits)
        self.assertIn("agents/zero.md", result)
        self.assertNotIn("agents/one.md", result)


    def test_an_array_element_line_is_not_mistaken_for_a_table_header(self) -> None:
        """A line like `["c", "d"]` inside a multi-line array is syntactically
        indistinguishable from a table header to a loose regex.

        Mistaking one truncates the enclosing block's range, so cutting that
        block leaves the array's tail behind as orphaned syntax and the
        manifest no longer parses. The validating re-parse would catch it and
        refuse, which is safe but useless — the entry never gets removed and
        the user has no way to fix it.
        """
        text = (
            '[[agents]]\n'
            'name = "keep"\n'
            'source = "agents/keep.md"\n'
            'matrix = [\n'
            '  ["c", "d"]\n'
            ']\n'
            '\n'
            '[[agents]]\n'
            'name = "drop"\n'
            'source = "agents/drop.md"\n'
        )
        edits, unresolved = self.migrate.plan_manifest_edits(
            text, ["agents.keep.source"]
        )
        self.assertEqual(unresolved, [])
        result = self.migrate.apply_manifest_edits(text, edits)

        self.assertNotIn("agents/keep.md", result)
        self.assertNotIn("matrix", result, "the array's opening line survived the cut")
        self.assertNotIn('["c", "d"]', result, "the array's body was orphaned")
        self.assertIn('name = "drop"', result)
        # The proof that matters: what is left is still TOML.
        parsed = load_cli_module("flowtoml").loads(result)
        self.assertEqual([a["name"] for a in parsed["agents"]], ["drop"])

    # -- against the real manifest ---------------------------------------

    def test_the_real_scaffold_manifest_survives_a_cut_byte_for_byte(self) -> None:
        """The anti-round-trip proof, and the reason this module does text
        surgery at all.

        Every line except the cut range must be byte-identical. A parse-and-
        re-serialize implementation passes none of this: it would reflow the
        whole file while still producing something that parses.
        """
        text = self.scaffold_manifest
        edits, unresolved = self.migrate.plan_manifest_edits(
            text, ["claude.commands.flow-boot.source"]
        )
        self.assertEqual(unresolved, [])
        result = self.migrate.apply_manifest_edits(text, edits)

        before = text.splitlines()
        after = result.splitlines()
        cut = before[edits[0].start : edits[0].end]
        self.assertEqual(
            before[: edits[0].start] + before[edits[0].end :],
            after,
            "lines outside the cut range were modified",
        )
        self.assertIn('name = "flow-boot"', "\n".join(cut))

    def test_the_real_manifest_still_parses_and_loses_exactly_one_site(self) -> None:
        text = self.scaffold_manifest
        before_sites = self.sites_in(text)
        edits, _ = self.migrate.plan_manifest_edits(
            text, ["claude.commands.flow-boot.source"]
        )
        after_sites = self.sites_in(self.migrate.apply_manifest_edits(text, edits))
        self.assertEqual(
            before_sites - after_sites, {"claude.commands.flow-boot.source"}
        )
        self.assertEqual(after_sites - before_sites, set())

    def test_one_source_declared_at_two_sites_cuts_both_entries(self) -> None:
        """`commands/flow-boot.md` is declared under both `[[claude.commands]]`
        and `[[codex.commands]]`. Cutting one and leaving the other is the
        dangling-declaration bug the audit's per-site attribution exists to
        prevent."""
        text = self.scaffold_manifest
        both = [
            "claude.commands.flow-boot.source",
            "codex.commands.flow-boot.source",
        ]
        self.assertLessEqual(set(both), self.sites_in(text), "fixture assumption")
        edits, unresolved = self.migrate.plan_manifest_edits(text, both)
        self.assertEqual(unresolved, [])
        after = self.sites_in(self.migrate.apply_manifest_edits(text, edits))
        self.assertEqual(set(both) & after, set())

    def test_cutting_every_command_declaration_leaves_a_parseable_manifest(self) -> None:
        """The real shape of a migration on a fully forked project."""
        text = self.scaffold_manifest
        sites = sorted(
            s for s in self.sites_in(text) if s.startswith(("claude.", "codex."))
        )
        self.assertGreater(len(sites), 10, "fixture assumption")
        edits, unresolved = self.migrate.plan_manifest_edits(text, sites)
        self.assertEqual(unresolved, [])
        result = self.migrate.apply_manifest_edits(text, edits)
        remaining = self.sites_in(result)
        self.assertEqual(remaining & set(sites), set())
        self.assertTrue(remaining, "agents and standards declarations must survive")


class ProjectMigrateDryRunTests(FlowCliHarness):
    """`flow project migrate` with no `--apply`: planning and reporting only."""

    def migrate(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return self.run_flow("project", "migrate", *extra)

    def snapshot(self) -> dict:
        state = {}
        for path in sorted(self.repo.rglob("*")):
            if ".git" in path.parts:
                continue
            rel = path.relative_to(self.repo).as_posix()
            if path.is_dir():
                state[rel] = ("dir", None)
            else:
                stat = path.stat()
                state[rel] = (
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    stat.st_mtime_ns,
                )
        return state

    def test_dry_run_changes_absolutely_nothing(self) -> None:
        """Proven by a full-tree hash and mtime diff, not by the words "dry
        run" appearing in stdout.

        The bug this defeats is wiring the apply path to run unconditionally and
        merely suppressing its output — against which a stdout assertion passes
        and this does not. The path set is compared too, so a created backup
        directory or a deleted file both show up.
        """
        self.use_fake_home()
        self.setup_legacy_project()
        before = self.snapshot()
        result = self.migrate()
        self.assert_ok(result)
        after = self.snapshot()
        self.assertEqual(set(before), set(after), "a path was created or removed")
        self.assertEqual(before, after, "content or mtime changed")

    def test_dry_run_leaves_the_manifest_byte_identical(self) -> None:
        self.use_fake_home()
        self.setup_legacy_project()
        manifest = self.repo / ".flow" / "flow.toml"
        before = manifest.read_text()
        self.assert_ok(self.migrate())
        self.assertEqual(manifest.read_text(), before)

    def test_reports_the_files_it_would_remove(self) -> None:
        self.use_fake_home()
        self.setup_legacy_project()
        result = self.migrate()
        self.assert_ok(result)
        self.assertIn("would remove", result.stdout)
        self.assertIn("dry run — nothing was changed.", result.stdout)

    def test_names_what_it_leaves_alone(self) -> None:
        """Dry-run output is the whole informed-consent surface, so "my
        customization is not in the removal list" has to be a conclusion someone
        can actually reach."""
        self.use_fake_home()
        self.setup_legacy_project()
        (self.repo / ".flow" / "standards" / "testing.md").write_text("ours\n")
        (self.repo / ".flow" / "standards" / "house.md").write_text("also ours\n")
        result = self.migrate()
        self.assert_ok(result)
        self.assertIn("left alone, and never removed by this command:", result.stdout)
        self.assertIn("standards/testing.md", result.stdout)
        self.assertIn("standards/house.md", result.stdout)

    def test_a_customized_file_is_never_in_the_removal_list(self) -> None:
        """R2, as a planning-level assertion. The real projects contain no
        customized file, so nothing but a synthetic fixture exercises this."""
        self.use_fake_home()
        self.setup_legacy_project()
        target = self.repo / ".flow" / "standards" / "testing.md"
        target.write_text(target.read_text() + "\nOne extra sentence.\n")

        data = json.loads(self.migrate("--json").stdout)
        self.assertNotIn("standards/testing.md", data["delete"])
        self.assertIn("standards/testing.md", data["kept"]["differs"])

    def test_the_same_file_unmodified_is_in_the_removal_list(self) -> None:
        """The other half of the previous test, and what stops it being
        vacuous: identical content must flip the same path into `delete`."""
        self.use_fake_home()
        self.setup_legacy_project()
        data = json.loads(self.migrate("--json").stdout)
        self.assertIn("standards/testing.md", data["delete"])

    def test_a_declaration_at_two_sites_yields_two_edits(self) -> None:
        """`commands/flow-boot.md` is declared under both runtimes. Removing one
        entry and leaving the other is the dangling declaration the audit's
        per-site attribution exists to prevent."""
        self.use_fake_home()
        self.setup_legacy_project()
        (self.repo / ".flow" / "commands" / "flow-boot.md").unlink()
        data = json.loads(self.migrate("--json").stdout)
        sites = {e["site"] for e in data["manifest_edits"]}
        self.assertIn("claude.commands.flow-boot.source", sites)
        self.assertIn("codex.commands.flow-boot.source", sites)

    def test_refuses_without_a_framework_baseline(self) -> None:
        self.use_fake_home()
        self.setup_legacy_project()
        empty = self.repo / "empty-framework"
        empty.mkdir()
        result = self.migrate("--scaffold", str(empty))
        self.assertEqual(result.returncode, 1)
        self.assertIn("no framework baseline", result.stdout)

    def test_refuses_a_root_inside_flow_s_own_home(self) -> None:
        fake_home = self.use_fake_home()
        inside = fake_home / ".flow" / "user"
        inside.mkdir(parents=True)
        result = self.migrate("--root", str(inside))
        self.assertEqual(result.returncode, 1)
        self.assertIn("flow's own home", result.stdout)


class ProjectMigrateApplyTests(FlowCliHarness):
    """`flow project migrate --apply` — the destructive path."""

    STAMP = "20260821T000000Z"

    def migrate(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return self.run_flow("project", "migrate", *extra)

    def apply(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return self.migrate("--apply", "--yes", "--at", self.STAMP, *extra)

    def tree(self) -> dict:
        state = {}
        for path in sorted(self.repo.rglob("*")):
            parts = path.relative_to(self.repo).parts
            if ".git" in parts or "fake_home" in parts:
                continue
            if path.is_file():
                stat = path.stat()
                state[path.relative_to(self.repo).as_posix()] = (
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    stat.st_mtime_ns,
                )
        return state

    def seeded(self):
        """A project carrying a customization and a legacy adapter surface.

        The adapters are fabricated rather than generated, because the command
        that generated them no longer exists — project-level sync was retired
        in the same change that added this. That is not a workaround: it is
        exactly the state migration meets in the field, where the `.claude/`
        tree and its managed manifest were written by an older flow and are
        now just files on disk that nothing maintains.
        """
        home = self.use_fake_home()
        self.setup_legacy_project()

        claude = self.repo / ".claude"
        (claude / "skills" / "flow-boot").mkdir(parents=True)
        (claude / "skills" / "flow-boot" / "SKILL.md").write_text("generated\n")
        (claude / "agents").mkdir(parents=True)
        (claude / "agents" / "architect.md").write_text("generated\n")
        (claude / "hooks").mkdir(parents=True)
        (claude / "hooks" / "flow-session-start.sh").write_text("#!/bin/sh\n")
        (claude / "settings.json").write_text(
            json.dumps(
                {
                    "hooks": {
                        "SessionStart": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": '"$CLAUDE_PROJECT_DIR"/.claude/hooks/flow-session-start.sh',
                                    }
                                ]
                            }
                        ]
                    }
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        managed = [
            "[managed]",
            'generator = "flow"',
            "version = 2",
            'target = "claude"',
            'source_manifest = ".flow/flow.toml"',
            "preserve_unmanaged = true",
            "",
        ]
        for rel, mode in (
            (".claude/skills/flow-boot/SKILL.md", "replace"),
            (".claude/agents/architect.md", "replace"),
            (".claude/hooks/flow-session-start.sh", "replace"),
            (".claude/settings.json", "merge"),
            (".claude/flow.managed.toml", "replace"),
        ):
            managed.extend(
                ["[[files]]", f'path = "{rel}"', f'sync_mode = "{mode}"', ""]
            )
        (claude / "flow.managed.toml").write_text("\n".join(managed))

        custom = self.repo / ".flow" / "standards" / "testing.md"
        custom.write_text(custom.read_text() + "\nOne extra sentence.\n")
        local = self.repo / ".flow" / "standards" / "house.md"
        local.write_text("entirely ours\n")
        return home, custom, local

    # -- refusal ---------------------------------------------------------

    def test_apply_without_yes_refuses_and_changes_nothing(self) -> None:
        self.use_fake_home()
        self.setup_legacy_project()
        before = self.tree()
        result = self.migrate("--apply")
        self.assertEqual(result.returncode, 1)
        self.assertIn("--apply --yes", result.stdout)
        self.assertEqual(self.tree(), before)

    def test_scaffold_pointed_at_own_overlay_refuses(self) -> None:
        """The comparison that inverts the safety rule.

        Every file in the overlay is byte-equal to itself, so pointing
        `--scaffold` at the project's own `.flow` reclassifies the whole
        `differs` bucket — the files migration exists to protect — as
        `identical`, which is the bucket `--apply` deletes. Asserted as a
        whole-tree snapshot rather than by naming files, because the failure
        deletes the overlay and a sampled assertion could miss which part.
        """
        _home, custom, local = self.seeded()
        before = self.tree()
        result = self.apply("--scaffold", str(self.repo / ".flow"))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.tree(), before)
        self.assertTrue(custom.is_file())
        self.assertTrue(local.is_file())

    def test_scaffold_inside_own_overlay_refuses(self) -> None:
        """Equality is the wrong relation: a subdirectory of the overlay is
        still the project's own tree and still self-compares identical."""
        self.seeded()
        before = self.tree()
        result = self.apply("--scaffold", str(self.repo / ".flow" / "standards"))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.tree(), before)
        # Named, not just refused. Without this the test passes on the
        # baseline gate — a subdirectory holds no capability directories — and
        # would keep passing with the containment guard removed.
        self.assertIn("own overlay", result.stdout)

    def test_scaffold_self_pointer_refuses_on_dry_run_too(self) -> None:
        """A planning-time property, not an apply-time one — otherwise the
        dry run and `--json` describe a plan the command would refuse."""
        self.seeded()
        result = self.migrate("--scaffold", str(self.repo / ".flow"))
        self.assertEqual(result.returncode, 1)

    def test_scaffold_self_pointer_message_names_the_collision(self) -> None:
        """So someone who hits this checks their argument instead of filing a
        bug against the classifier."""
        self.seeded()
        result = self.migrate("--scaffold", str(self.repo / ".flow"))
        self.assertIn("--scaffold", result.stdout)
        self.assertIn("own overlay", result.stdout)

    def test_a_distinct_scaffold_is_not_refused(self) -> None:
        """Negative control. Without this the guard can be implemented as
        "refuse any --scaffold", which would break the override entirely."""
        self.seeded()
        # Inside the repo but outside `.flow`, so it is a genuinely distinct
        # tree by the containment test and is cleaned up with the fixture.
        other = self.repo / "other-scaffold"
        shutil.copytree(REPO_ROOT / "scaffolds" / "default", other)
        result = self.migrate("--scaffold", str(other))
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("own overlay", result.stdout)

    # -- the destructive path --------------------------------------------

    def test_removes_identical_copies_and_leaves_everything_else(self) -> None:
        """The over-delete invariant, asserted as a set difference rather than
        by sampling files — so a bug nobody anticipated is not missed by
        checking the wrong ones."""
        _home, custom, local = self.seeded()
        plan = json.loads(self.migrate("--json").stdout)
        deletable = {f".flow/{rel}" for rel in plan["delete"]}
        before = self.tree()

        result = self.apply()
        self.assert_ok(result)
        after = self.tree()

        vanished = set(before) - set(after)
        unexpected = vanished - deletable
        # Generated adapters go too; they are not in the audit's buckets.
        unexpected = {p for p in unexpected if not p.startswith(".claude/")}
        self.assertEqual(unexpected, set(), "removed something outside the plan")

        # Two paths are deliberately rewritten rather than removed: the
        # manifest loses its dead declarations, and the settings file loses
        # flow's handlers. Everything else that survives must be untouched --
        # mtime included, because a rewrite reproducing the same bytes still
        # proves something wrote to a file it should have skipped.
        mutated = {".flow/flow.toml", ".claude/settings.json", ".codex/hooks.json"}
        survivors = set(before).intersection(after).difference(mutated)
        for rel in survivors:
            self.assertEqual(
                before[rel], after[rel], f"{rel} was modified but should not have been"
            )

    def test_a_customization_survives_byte_for_byte(self) -> None:
        """R2. Asserting only that the file still exists would pass against a
        migration that truncated it."""
        _home, custom, _local = self.seeded()
        content = custom.read_text()
        self.assert_ok(self.apply())
        self.assertTrue(custom.exists(), "a differs file was deleted")
        self.assertEqual(custom.read_text(), content)

    def test_a_project_only_file_survives_byte_for_byte(self) -> None:
        _home, _custom, local = self.seeded()
        content = local.read_text()
        self.assert_ok(self.apply())
        self.assertEqual(local.read_text(), content)

    def test_the_manifest_keeps_its_comments_and_loses_only_dead_sites(self) -> None:
        self.use_fake_home()
        self.setup_legacy_project()
        manifest = self.repo / ".flow" / "flow.toml"
        before_text = manifest.read_text()
        before_comments = [l for l in before_text.splitlines() if l.lstrip().startswith("#")]
        self.assertTrue(before_comments, "fixture assumption: the manifest has comments")

        plan = json.loads(self.migrate("--json").stdout)
        removed_sites = {e["site"] for e in plan["manifest_edits"]}
        self.assert_ok(self.apply())

        after_text = manifest.read_text()
        after_comments = [l for l in after_text.splitlines() if l.lstrip().startswith("#")]
        self.assertEqual(before_comments, after_comments, "comments were lost")

        project = load_cli_module("project")
        flowtoml = load_cli_module("flowtoml")
        remaining = {
            d.declared_by
            for d in project.declared_sources(flowtoml.parse_simple_toml(after_text))[0]
        }
        self.assertEqual(removed_sites & remaining, set())

    def test_the_backup_holds_everything_that_was_removed(self) -> None:
        home, _custom, _local = self.seeded()
        plan = json.loads(self.migrate("--json").stdout)
        self.assert_ok(self.apply())

        backup = home / ".flow" / "backups" / f"migrate-{self.repo.name}-{self.STAMP}"
        self.assertTrue(backup.is_dir(), "no backup directory was created")
        self.assertTrue((backup / "MANIFEST.txt").is_file())
        for rel in plan["delete"]:
            self.assertTrue(
                (backup / "files" / ".flow" / rel).is_file(),
                f"{rel} missing from the backup",
            )
        self.assertTrue((backup / "files" / ".flow" / "flow.toml").is_file())

    def test_a_second_run_is_a_no_op(self) -> None:
        """R3: migration must be re-runnable to nothing. A second `--apply`
        with the same stamp would also collide with its own backup directory,
        so the no-op has to be detected before the backup step."""
        self.seeded()
        self.assert_ok(self.apply())
        after_first = self.tree()

        second = self.apply()
        self.assert_ok(second)
        # "nothing removable" rather than "nothing to migrate": this fixture
        # still holds a drifted file, and the headline no longer claims there
        # is nothing here when the body is about to list something.
        self.assertIn("nothing removable", second.stdout)
        self.assertEqual(self.tree(), after_first)

    # -- --drifted, the opt-in destructive path -------------------------

    def test_drifted_is_never_removed_without_the_flag(self) -> None:
        """The default must stay what it has always been."""
        _home, custom, _local = self.seeded()
        before = custom.read_bytes()
        self.assert_ok(self.apply())
        self.assertTrue(custom.is_file())
        self.assertEqual(custom.read_bytes(), before)

    def test_without_the_flag_a_drifted_file_keeps_its_declaration(self) -> None:
        """The file surviving is not enough. Widening the declaration-removal
        set to all drifted files would strip the manifest entry while leaving
        the file, which is the same inconsistency from the other side."""
        self.seeded()
        # A drifted file that is actually declared. The seeded fixture's
        # customization is `standards/testing.md`, which no manifest entry
        # names, so it cannot exercise the declaration path at all.
        declared = self.repo / ".flow" / "agents" / "architect.md"
        declared.write_text(declared.read_text() + "\nlocal edit\n")

        self.assert_ok(self.apply())

        manifest = (self.repo / ".flow" / "flow.toml").read_text()
        self.assertTrue(declared.is_file())
        self.assertIn("agents/architect.md", manifest)

    def test_drifted_removes_the_differs_bucket_and_nothing_else(self) -> None:
        """Three independent filesystem facts, not one assertion about the
        plan's own delete list — a plan that agrees with itself proves
        nothing."""
        _home, custom, local = self.seeded()
        identical = self.repo / ".flow" / "standards" / "architecture.md"
        self.assertTrue(identical.is_file())

        self.assert_ok(self.apply("--drifted"))

        self.assertFalse(custom.exists(), "drifted file should be gone")
        self.assertFalse(identical.exists(), "identical file should still go")
        self.assertTrue(local.is_file(), "project-only file must survive")

    def test_drifted_deletion_is_backed_up_before_removal(self) -> None:
        """Bytes, not a count and not a log line. A count can be right while
        the wrong file was copied, and the backup is the only copy left."""
        home, custom, _local = self.seeded()
        original = custom.read_bytes()
        rel = custom.relative_to(self.repo)

        self.assert_ok(self.apply("--drifted"))

        backups = sorted((home / ".flow" / "backups").iterdir())
        self.assertEqual(len(backups), 1, f"expected one backup, got {backups}")
        saved = backups[0] / "files" / rel
        self.assertTrue(saved.is_file(), f"{rel} missing from the backup")
        self.assertEqual(saved.read_bytes(), original)

    def test_bare_drifted_lists_and_changes_nothing(self) -> None:
        """List-then-confirm: the list has to be receivable without consenting
        to anything."""
        _home, custom, _local = self.seeded()
        before = self.tree()

        result = self.migrate("--drifted")

        self.assert_ok(result)
        self.assertIn("standards/testing.md", result.stdout)
        self.assertEqual(self.tree(), before)
        self.assertTrue(custom.is_file())

    def test_drifted_still_requires_yes(self) -> None:
        """The new destructive path gets the existing consent gate, not a
        weaker one of its own."""
        _home, custom, _local = self.seeded()
        before = self.tree()

        result = self.migrate("--drifted", "--apply")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.tree(), before)
        self.assertTrue(custom.is_file())

    def test_drifted_names_the_loss_before_asking_for_consent(self) -> None:
        self.seeded()
        result = self.migrate("--drifted")
        self.assertIn("DIFFER", result.stdout)
        # The destination, not just the word "backup" — that appears in the
        # warning prose regardless, so asserting it proved nothing.
        self.assertIn("a backup is taken first, under", result.stdout)
        self.assertIn("/backups", result.stdout)

    def test_a_drifted_file_is_listed_once_not_twice(self) -> None:
        """A path appearing under both "would remove" and "never removed by
        this command" makes the output useless as a consent surface."""
        self.seeded()
        for extra in ((), ("--drifted",)):
            with self.subTest(extra=extra):
                out = self.migrate(*extra).stdout
                self.assertEqual(out.count("standards/testing.md"), 1, out)

    def test_a_drifted_file_whose_declaration_cannot_be_found_is_refused(self) -> None:
        """The unrecoverable case.

        For a framework copy an unresolved declaring site is survivable: the
        file is byte-identical to the scaffold's and can be fetched back. A
        drifted file cannot be. Removing it while its declaration stays would
        leave the manifest naming a customization that exists nowhere but the
        backup, so it is refused individually and the run continues.

        The site is made unresolvable by declaring the same name twice, which
        the text locator refuses to disambiguate rather than guess at.
        """
        _home, custom, _local = self.seeded()
        (self.repo / ".flow" / "flow.toml").write_text(
            '[framework]\nname = "flow"\nversion = 1\n'
            '[[agents]]\nname = "dup"\nsource = "standards/testing.md"\n'
            '[[agents]]\nname = "dup"\nsource = "standards/testing.md"\n'
        )

        result = self.apply("--drifted")

        self.assertTrue(custom.is_file(), "refused file must survive")
        self.assertIn("refused", result.stdout)
        self.assertIn("standards/testing.md", result.stdout)

    def test_a_blocked_drifted_file_keeps_its_whole_declaration(self) -> None:
        """The split-site case, found in review.

        A drifted file can have two declaring sites where one resolves and the
        other does not. Blocking the deletion is only half the job: the
        resolvable site was still in the edit set, so the manifest lost an
        entry for a file the command had just refused to remove — the same
        file/manifest inconsistency the block exists to prevent, reached from
        the other side.

        The unresolvable site is produced by a trailing comment on the `name`
        line, which `_NAME_RE` does not match. A hand-annotated manifest is
        exactly the artifact the text-surgery design exists to protect.
        """
        self.use_fake_home()
        self.setup_legacy_project()
        drifted = self.repo / ".flow" / "commands" / "flow-plan.md"
        drifted.write_text(drifted.read_text() + "\nlocal edit\n")
        manifest = self.repo / ".flow" / "flow.toml"
        manifest.write_text(
            '[framework]\nname = "flow"\nversion = 1\n'
            '\n[[claude.commands]]\nname = "flow-plan"\n'
            'source = "commands/flow-plan.md"\n'
            '\n[[codex.commands]]\nname = "flow-plan"  # keep in sync\n'
            'source = "commands/flow-plan.md"\n'
        )
        before = manifest.read_bytes()

        result = self.apply("--drifted")

        self.assertTrue(drifted.is_file(), "blocked file must survive")
        self.assertEqual(
            manifest.read_bytes(),
            before,
            "a refused file must keep every one of its declarations",
        )
        self.assertIn("refused", result.stdout)

    def test_blocking_one_drifted_file_does_not_spare_the_others(self) -> None:
        """The other half of the two-pass fix.

        Re-planning the edits after excluding the blocked file's sites must
        still cut the declarations of the drifted files that are being
        removed. A second pass that dropped every edit would leave the blocked
        file correct and every other removal orphaned in the manifest.
        """
        self.use_fake_home()
        self.setup_legacy_project()
        blocked = self.repo / ".flow" / "commands" / "flow-plan.md"
        removed = self.repo / ".flow" / "commands" / "flow-review.md"
        for path in (blocked, removed):
            path.write_text(path.read_text() + "\nlocal edit\n")
        manifest = self.repo / ".flow" / "flow.toml"
        manifest.write_text(
            '[framework]\nname = "flow"\nversion = 1\n'
            # unresolvable: the trailing comment defeats the name matcher
            '\n[[claude.commands]]\nname = "flow-plan"  # pinned\n'
            'source = "commands/flow-plan.md"\n'
            '\n[[claude.commands]]\nname = "flow-review"\n'
            'source = "commands/flow-review.md"\n'
        )

        self.assert_ok(self.apply("--drifted"))

        self.assertTrue(blocked.is_file(), "blocked file must survive")
        self.assertFalse(removed.exists(), "the resolvable one must still go")
        text = manifest.read_text()
        self.assertIn("commands/flow-plan.md", text, "blocked keeps its entry")
        self.assertNotIn(
            "commands/flow-review.md", text, "removed loses its entry"
        )

    def test_drifted_with_an_empty_bucket_is_still_a_clean_no_op(self) -> None:
        self.use_fake_home()
        self.setup_legacy_project()
        self.assert_ok(self.apply())
        before = self.tree()

        second = self.apply("--drifted")

        self.assert_ok(second)
        self.assertEqual(self.tree(), before)

    def test_the_manifest_and_the_files_it_names_agree_afterwards(self) -> None:
        """The prove-it test, restated as a state fact.

        `flow sync claude --check` is the surface that used to catch this and it
        is being retired, so the property is asserted directly: after migration
        no declaration names a file that is not there.
        """
        self.use_fake_home()
        self.setup_legacy_project()
        # Reproduce path-nexus: delete a source the way a naive migration would,
        # leaving the manifest declaring it.
        (self.repo / ".flow" / "commands" / "flow-boot.md").unlink()
        manifest = self.repo / ".flow" / "flow.toml"
        self.assertIn("commands/flow-boot.md", manifest.read_text())

        self.assert_ok(self.apply())

        project = load_cli_module("project")
        flowtoml = load_cli_module("flowtoml")
        declared, _ = project.declared_sources(
            flowtoml.parse_simple_toml(manifest.read_text())
        )
        missing = [
            d.rel for d in declared if not (self.repo / ".flow" / d.rel).exists()
        ]
        self.assertEqual(missing, [], "the manifest still names files that are gone")

    def test_settings_json_keeps_every_unmanaged_key(self) -> None:
        """R4. Full-subtree equality against a snapshot, not key-by-key
        presence — the failure mode is re-serialization drift, where a sibling
        key is reordered, reformatted, or dropped because its value was empty.
        """
        self.seeded()
        settings = self.repo / ".claude" / "settings.json"
        doc = json.loads(settings.read_text())
        doc["env"] = {"CUSTOM_VAR": "keep me"}
        doc["permissions"] = {"allow": [], "deny": ["Bash(rm:*)"]}
        doc.setdefault("hooks", {}).setdefault("PostToolUse", []).append(
            {"hooks": [{"type": "command", "command": "/usr/local/bin/mine.sh"}]}
        )
        settings.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
        before = json.loads(settings.read_text())

        self.assert_ok(self.apply())

        after = json.loads(settings.read_text())
        self.assertEqual(
            {k: v for k, v in before.items() if k != "hooks"},
            {k: v for k, v in after.items() if k != "hooks"},
            "unmanaged top-level content changed",
        )
        remaining = json.dumps(after.get("hooks", {}))
        self.assertIn("/usr/local/bin/mine.sh", remaining, "user handler was removed")
        self.assertNotIn("/.claude/hooks/flow-", remaining, "flow handlers survived")


class MigrationAbortGuardTests(unittest.TestCase):
    """The three guards that only fire on conditions which never occur naturally.

    Each was added because the consequence of it being absent is severe, and
    each initially survived a mutation run — meaning nothing proved it worked.
    A guard that has never been observed to fire is indistinguishable from one
    that cannot, so every one of them is provoked here directly.

    All three raise before the first deletion. That ordering is the point: a
    migration that stops is recoverable, and these stop it.
    """

    def setUp(self) -> None:
        self.migrate = load_cli_module("migrate")
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.flow_dir = self.root / ".flow"
        self.scaffold = self.root / "scaffold"
        for name in ("standards", "agents", "commands", "project", "templates"):
            (self.flow_dir / name).mkdir(parents=True)
            (self.scaffold / name).mkdir(parents=True)
        (self.flow_dir / "standards" / "same.md").write_text("shared\n")
        (self.scaffold / "standards" / "same.md").write_text("shared\n")
        self.backups = self.root / "backups"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_apply(self):
        plan = self.migrate.plan_migration(self.flow_dir, self.scaffold)
        return self.migrate.apply_migration(
            self.root, self.flow_dir, self.scaffold, plan, self.backups, "STAMP"
        )

    def test_an_incomplete_backup_aborts_before_anything_is_deleted(self) -> None:
        """A migration that cannot prove it backed up does not delete. Project
        sync is retired in the same change, so the backup is the only route
        back — and a partial one is worse than none, because it looks like a
        route."""
        target = self.flow_dir / "standards" / "same.md"
        real = self.migrate.perform_backup

        def under_reporting_backup(root, destination, paths):
            real(root, destination, paths)
            return len(paths) - 1

        self.migrate.perform_backup = under_reporting_backup
        try:
            with self.assertRaises(self.migrate.MigrationAborted) as caught:
                self.run_apply()
        finally:
            self.migrate.perform_backup = real
        self.assertIn("backup incomplete", str(caught.exception))
        self.assertTrue(target.is_file(), "a file was deleted despite the abort")

    def test_a_reused_backup_directory_aborts(self) -> None:
        """Writing a second migration's backup into the first one's directory
        would silently make both unusable."""
        (self.backups / "migrate-.flow-STAMP").mkdir(parents=True)
        (self.backups / f"migrate-{self.root.name}-STAMP").mkdir(parents=True)
        with self.assertRaises(self.migrate.MigrationAborted) as caught:
            self.run_apply()
        self.assertIn("already exists", str(caught.exception))

    def test_a_remover_that_touches_unmanaged_content_aborts_the_write(self) -> None:
        """R4 enforced at write time rather than trusted to a restore."""
        settings = self.root / "settings.json"
        settings.write_text(
            json.dumps({"env": {"KEEP": "1"}, "hooks": {}}, indent=2) + "\n"
        )
        before = settings.read_text()

        def greedy_remover(doc):
            doc.pop("env", None)
            return doc

        with self.assertRaises(self.migrate.MigrationAborted) as caught:
            self.migrate.strip_managed_handlers(settings, greedy_remover)
        self.assertIn("unmanaged content", str(caught.exception))
        self.assertEqual(settings.read_text(), before, "the file was written anyway")

    def test_a_manifest_rewrite_that_did_not_remove_the_site_aborts(self) -> None:
        """The one validating round-trip in the module, and the only thing
        standing between a botched text edit and a deletion performed on the
        strength of it."""
        (self.flow_dir / "flow.toml").write_text(
            '[[agents]]\nname = "ghost"\nsource = "agents/ghost.md"\n'
        )
        manifest_before = (self.flow_dir / "flow.toml").read_text()
        target = self.flow_dir / "standards" / "same.md"
        real = self.migrate.apply_manifest_edits

        def no_op_edit(text, edits):
            return text

        self.migrate.apply_manifest_edits = no_op_edit
        try:
            with self.assertRaises(self.migrate.MigrationAborted) as caught:
                self.run_apply()
        finally:
            self.migrate.apply_manifest_edits = real
        self.assertIn("did not remove", str(caught.exception))
        self.assertEqual((self.flow_dir / "flow.toml").read_text(), manifest_before)
        self.assertTrue(target.is_file(), "a file was deleted despite the abort")


class LegacyOverlaySurvivesThinningTests(FlowCliHarness):
    """Backward compatibility for overlays created before the scaffold thinned.

    Thinning `setup project` is only safe if it leaves existing projects alone,
    and every other test of the thinned contract starts from a thin project —
    which is exactly the shape that cannot catch a regression here.
    """

    def test_the_retired_refresh_leaves_a_legacy_overlay_intact(self) -> None:
        """Same property, different command state.

        This asserted that refresh repaired a legacy overlay without touching
        it. Refresh is retired now, so the exit code moved to 1 — but the
        property that mattered is unchanged and still worth pinning: someone
        who types the retired command against a fat overlay must not lose
        anything to it.
        """
        self.setup_legacy_project()
        flow_dir = self.repo / ".flow"
        before = {
            p.relative_to(flow_dir).as_posix(): p.read_bytes()
            for p in flow_dir.rglob("*")
            if p.is_file()
        }
        self.assertIn("FRAMEWORK.md", before, "fixture assumption: legacy overlay is fat")

        self.assertEqual(self.run_flow("refresh", "project").returncode, 1)

        after = {
            p.relative_to(flow_dir).as_posix(): p.read_bytes()
            for p in flow_dir.rglob("*")
            if p.is_file()
        }
        self.assertEqual(after, before)

    def test_bootstrap_still_passes_on_a_legacy_overlay(self) -> None:
        self.setup_legacy_project()

        self.assert_ok(self.run_flow("bootstrap"))

    def test_a_legacy_overlay_missing_its_manifest_is_not_given_a_thin_one(self) -> None:
        """The one place this slice could lose user data.

        A fat overlay whose manifest has gone missing must not be handed the
        short template. The legacy manifest is what names the project's
        registered sources and, via `[claude] managed_manifest`, what lets
        `flow project migrate` find the generated adapters — replace it with
        eleven lines naming neither and those adapters are orphaned with no
        way back.
        """
        self.setup_legacy_project()
        flow_dir = self.repo / ".flow"
        (flow_dir / "flow.toml").unlink()

        # Asserted through `setup project`, which is `_write_project_manifest`'s
        # only caller now that refresh is retired. The property under test is
        # the refusal, not which command reaches it.
        result = self.run_flow("setup", "project")

        self.assertFalse((flow_dir / "flow.toml").exists())
        self.assertIn("flow project audit", result.stdout)

    def test_a_manifest_shaped_like_a_directory_does_not_crash_setup(self) -> None:
        self.setup_project()
        manifest = self.repo / ".flow" / "flow.toml"
        manifest.unlink()
        manifest.mkdir()

        result = self.run_flow("setup", "project")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(manifest.is_dir())

    def test_a_dangling_manifest_symlink_is_not_written_through(self) -> None:
        """`exists()` follows links and reports False for a broken one.

        Writing the template then lands wherever the link points, which is by
        construction outside the overlay.
        """
        self.setup_project()
        flow_dir = self.repo / ".flow"
        manifest = flow_dir / "flow.toml"
        outside = self.repo / "not-the-overlay.toml"
        manifest.unlink()
        manifest.symlink_to(outside)

        self.assert_ok(self.run_flow("setup", "project"))

        self.assertFalse(outside.exists())


class ManagedPathContainmentTests(unittest.TestCase):
    """A managed-manifest entry can never name a path outside the root.

    `sync_outputs` unlinks whatever it considers stale, and `flow project
    migrate` calls it with an empty desired set specifically in order to delete
    everything the manifest lists. So a manifest entry that escapes the root is
    a deletion outside the root.

    The join is the hazard: `root / "/etc/passwd"` is `/etc/passwd`, because
    pathlib discards the left operand when the right is absolute. That is easy
    to write and impossible to see.
    """

    def setUp(self) -> None:
        self.sync = load_cli_module("sync")
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "repo"
        (self.root / ".claude").mkdir(parents=True)
        self.outside = Path(self._tmp.name) / "victim.txt"
        self.outside.write_text("must survive\n")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def manifest(self, *entries: tuple[str, str]) -> Path:
        path = self.root / ".claude" / "flow.managed.toml"
        body = ["[managed]", 'generator = "flow"', "version = 2", ""]
        for rel, mode in entries:
            body += ["[[files]]", f'path = "{rel}"', f'sync_mode = "{mode}"', ""]
        path.write_text("\n".join(body))
        return path

    def test_an_absolute_entry_is_refused(self) -> None:
        path = self.manifest(
            (str(self.outside), "replace"), (".claude/ok.md", "replace")
        )
        paths = self.sync.read_managed_paths(self.root, path)
        self.assertEqual(paths, {self.root / ".claude" / "ok.md"})
        self.assertNotIn(self.outside, paths)

    def test_a_parent_traversal_entry_is_refused(self) -> None:
        path = self.manifest(("../../escape.md", "replace"), (".claude/ok.md", "replace"))
        paths = self.sync.read_managed_paths(self.root, path)
        self.assertEqual(paths, {self.root / ".claude" / "ok.md"})

    def test_the_merge_protected_reader_is_guarded_too(self) -> None:
        """Merge-protected paths are read by a second function. Guarding only
        the first would leave the settings-file path unchecked, which is the one
        the migration writes to rather than merely deletes."""
        path = self.manifest(
            (str(self.outside), "merge"), (".claude/settings.json", "merge")
        )
        paths = self.sync.read_managed_merge_paths(self.root, path)
        self.assertEqual(paths, {self.root / ".claude" / "settings.json"})

    def test_an_escaping_entry_would_otherwise_have_been_deleted(self) -> None:
        """The control. Proves the guard is load-bearing rather than decorative
        by running the exact call migration makes — `sync_outputs` with an empty
        desired set — and confirming the outside file is still there."""
        (self.root / ".claude" / "ok.md").write_text("managed\n")
        path = self.manifest(
            (str(self.outside), "replace"), (".claude/ok.md", "replace")
        )
        previous = self.sync.read_managed_paths(self.root, path)
        self.sync.sync_outputs(
            self.root, "claude", {}, previous, set(), check=False, merge_protected=set()
        )
        self.assertTrue(self.outside.is_file(), "a file outside the root was deleted")
        self.assertFalse((self.root / ".claude" / "ok.md").exists(), "control: the in-root managed file should go")


class MigrationReviewRegressionTests(FlowCliHarness):
    """Regressions for the defects acceptance review found.

    Each of these shipped in a working, 563-green build. They are here so the
    next change cannot quietly restore any of them.
    """

    STAMP = "20260821T000000Z"

    def migrate(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return self.run_flow("project", "migrate", *extra)

    def test_a_manifest_value_outside_the_fallback_parsers_subset_migrates(self) -> None:
        """The worst defect review found, as a regression test.

        The validating round-trip called `parse_simple_toml` directly instead
        of the tomllib-preferring read. That fallback raises on floats, arrays,
        and inline comments — so a perfectly ordinary manifest crashed the
        apply path *after* the handler strip and the adapter deletion had
        already run, and crashed identically on every retry. The repo was left
        permanently adapter-less with an unedited manifest.
        """
        self.use_fake_home()
        self.setup_legacy_project()
        manifest = self.repo / ".flow" / "flow.toml"
        manifest.write_text(
            manifest.read_text()
            + "\n[tooling]\n"
            + "timeout = 1.5\n"
            + 'matchers = ["Write", "Edit"]\n'
        )
        (self.repo / ".flow" / "commands" / "flow-boot.md").unlink()

        result = self.migrate("--apply", "--yes", "--at", self.STAMP)
        self.assert_ok(result)
        surviving = manifest.read_text()
        self.assertIn("timeout = 1.5", surviving, "the float was lost")
        self.assertIn('matchers = ["Write", "Edit"]', surviving, "the array was lost")
        self.assertNotIn("commands/flow-boot.md", surviving)

    def test_the_float_is_reported_at_plan_time_not_discovered_at_apply(self) -> None:
        """The same manifest through the dry run, which must not crash either —
        the fix moved the validating parse into planning so a failure surfaces
        before anything is destroyed."""
        self.use_fake_home()
        self.setup_legacy_project()
        manifest = self.repo / ".flow" / "flow.toml"
        manifest.write_text(manifest.read_text() + "\n[tooling]\ntimeout = 1.5\n")
        data = json.loads(self.migrate("--json").stdout)
        self.assertEqual(data["unresolved_sites"], [])

    def test_generated_adapters_appear_in_the_dry_run(self) -> None:
        """The dry run is the whole consent surface, and it listed only two of
        the five things `--apply` does. Adapter removal and the handler strip
        were invisible."""
        self.use_fake_home()
        self.setup_legacy_project()
        claude = self.repo / ".claude"
        (claude / "skills" / "flow-boot").mkdir(parents=True)
        (claude / "skills" / "flow-boot" / "SKILL.md").write_text("generated\n")
        (claude / "settings.json").write_text('{"hooks": {}}\n')
        (claude / "flow.managed.toml").write_text(
            "[managed]\n"
            'generator = "flow"\nversion = 2\n\n'
            '[[files]]\npath = ".claude/skills/flow-boot/SKILL.md"\nsync_mode = "replace"\n\n'
            '[[files]]\npath = ".claude/settings.json"\nsync_mode = "merge"\n'
        )

        result = self.migrate()
        self.assert_ok(result)
        self.assertIn("generated adapter file(s)", result.stdout)
        self.assertIn(".claude/skills/flow-boot/SKILL.md", result.stdout)
        self.assertIn("would strip flow's hook handlers", result.stdout)

        data = json.loads(self.migrate("--json").stdout)
        self.assertIn(".claude/skills/flow-boot/SKILL.md", data["adapters"])
        self.assertIn(".claude/settings.json", data["settings_files"])

    def test_an_adapter_tree_alone_is_not_a_no_op(self) -> None:
        """A project whose overlay files all land in `differs` still has a full
        generated adapter tree to remove — and both `flow sync` and `flow
        doctor` send people here to remove it. Reporting "nothing to migrate"
        contradicted the two commands that recommend this one."""
        self.use_fake_home()
        self.setup_legacy_project()
        # Nothing byte-identical and nothing orphaned: every overlay file is
        # edited, so `delete` and `manifest_edits` are both empty. Every file,
        # not just the .md ones — a single byte-identical LICENSE.txt is enough
        # to make this test pass for the wrong reason.
        for path in (self.repo / ".flow").rglob("*"):
            if path.is_file() and path.name != "flow.toml":
                path.write_text("locally rewritten\n")
        claude = self.repo / ".claude"
        claude.mkdir(exist_ok=True)
        (claude / "agents").mkdir(parents=True, exist_ok=True)
        (claude / "agents" / "architect.md").write_text("generated\n")
        (claude / "flow.managed.toml").write_text(
            "[managed]\n"
            'generator = "flow"\nversion = 2\n\n'
            '[[files]]\npath = ".claude/agents/architect.md"\nsync_mode = "replace"\n'
        )

        data = json.loads(self.migrate("--json").stdout)
        self.assertEqual(data["delete"], [])
        self.assertEqual(data["manifest_edits"], [])
        self.assertFalse(data["noop"], "an adapter tree is work to do")

    def test_two_entries_sharing_a_name_are_refused_at_plan_time(self) -> None:
        """`_site` builds one dotted site from both, so a single cut would
        leave the other declaring a file that is gone. Detected while planning,
        because the alternative was an abort after two destructive steps."""
        self.use_fake_home()
        self.setup_legacy_project()
        manifest = self.repo / ".flow" / "flow.toml"
        manifest.write_text(
            manifest.read_text()
            + '\n[[agents]]\nname = "twin"\nsource = "agents/twin-a.md"\n'
            + '\n[[agents]]\nname = "twin"\nsource = "agents/twin-b.md"\n'
        )
        data = json.loads(self.migrate("--json").stdout)
        self.assertIn("agents.twin.source", data["unresolved_sites"])
        self.assertNotIn(
            "agents.twin.source", [e["site"] for e in data["manifest_edits"]]
        )

    def test_unresolved_sites_are_reported_even_when_nothing_else_is_to_do(
        self,
    ) -> None:
        """The no-op branch returned before the unresolved block, so a plan with
        only unresolved sites printed "nothing to migrate" while doctor
        reported declarations to fix."""
        self.use_fake_home()
        self.setup_legacy_project()
        for path in (self.repo / ".flow").rglob("*.md"):
            path.write_text("locally rewritten\n")
        manifest = self.repo / ".flow" / "flow.toml"
        manifest.write_text(
            manifest.read_text()
            + '\n[[agents]]\nname = "twin"\nsource = "agents/twin-a.md"\n'
            + '\n[[agents]]\nname = "twin"\nsource = "agents/twin-b.md"\n'
        )
        result = self.migrate()
        self.assert_ok(result)
        self.assertIn("could not locate", result.stdout)
        self.assertIn("agents.twin.source", result.stdout)

    def test_at_cannot_escape_the_backups_directory(self) -> None:
        self.use_fake_home()
        self.setup_legacy_project()
        result = self.migrate("--apply", "--yes", "--at", "../../escape")
        self.assertEqual(result.returncode, 1)
        self.assertIn("--at must be", result.stdout)

    def test_root_must_look_like_an_overlay(self) -> None:
        """`--root ~/projects` would have walked and backed up something that
        is not an overlay at all."""
        self.use_fake_home()
        elsewhere = self.repo / "not-an-overlay"
        elsewhere.mkdir()
        result = self.migrate("--root", str(elsewhere))
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not look like a .flow overlay", result.stdout)

    def test_a_repo_owning_a_manifest_txt_keeps_it(self) -> None:
        """The backup listing was written to `MANIFEST.txt` at the top of the
        backup, so a repo with its own top-level `MANIFEST.txt` in the managed
        set had it saved and then immediately overwritten — destroyed, not
        saved, and invisible to any count."""
        home = self.use_fake_home()
        self.setup_legacy_project()
        victim = self.repo / "MANIFEST.txt"
        victim.write_text("the project's own manifest\n")
        claude = self.repo / ".claude"
        claude.mkdir(exist_ok=True)
        (claude / "flow.managed.toml").write_text(
            "[managed]\n"
            'generator = "flow"\nversion = 2\n\n'
            '[[files]]\npath = "MANIFEST.txt"\nsync_mode = "replace"\n'
        )

        self.assert_ok(self.migrate("--apply", "--yes", "--at", self.STAMP))
        backup = home / ".flow" / "backups" / f"migrate-{self.repo.name}-{self.STAMP}"
        saved = backup / "files" / "MANIFEST.txt"
        self.assertTrue(saved.is_file(), "the repo's own MANIFEST.txt was not saved")
        self.assertEqual(saved.read_text(), "the project's own manifest\n")
        self.assertTrue((backup / "MANIFEST.txt").is_file(), "the listing is missing")
        self.assertIn("restore a file", (backup / "MANIFEST.txt").read_text())


class WriteAtomicSymlinkTests(unittest.TestCase):
    """`.claude/settings.json` is commonly a symlink into a dotfiles repo."""

    def setUp(self) -> None:
        self.fsutil = load_cli_module("fsutil")
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_writes_through_a_symlink_instead_of_replacing_it(self) -> None:
        """`os.replace` onto the link would break it, leaving the real file
        untouched — which for the migration means flow's handlers survive,
        pointing at scripts the next step deletes."""
        real = self.root / "dotfiles" / "settings.json"
        real.parent.mkdir()
        real.write_text("original\n")
        link = self.root / "settings.json"
        link.symlink_to(real)

        self.fsutil.write_atomic(link, "updated\n")

        self.assertTrue(link.is_symlink(), "the symlink was replaced by a file")
        self.assertEqual(real.read_text(), "updated\n", "the real file was not updated")
