"""Replacement contracts; optional SDK integration is in openhands_runtime_eval.py."""
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))
import openhands_config as config
import openhands_flow as flow
import runstate


class OpenHandsWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.directory = self.root / ".flow/runs/example"
        self.args = Namespace(project_root=self.root, work_id="example", stage=None, disposition=[])

    def tearDown(self):
        self.temp.cleanup()

    def outputs(self, stage):
        for filename in config.OUTPUTS[stage].values():
            (self.directory / filename).write_text(f"Evidence for {stage}\n")

    def test_full_lifecycle_has_artifacts_without_legacy_orchestration(self):
        self.assertEqual(flow.initialize(self.args)["protocol_revision"], 3)
        for stage in ("define", "solution", "plan", "implement", "review"):
            self.args.stage = stage
            if stage != "define":
                start, state, _ = config.STAGES[stage]
                if runstate.status("example", self.root)["state"] != state:
                    flow._transition(self.root, "example", start)
            self.outputs(stage)
            self.args.disposition = ["risk=accepted"] if stage == "solution" else []
            flow.approve(self.args)
        self.args.disposition = ["memory=recorded", "capability_gaps=none"]
        self.assertEqual(flow.archive(self.args)["state"], "archived")
        ok, errors, payload = runstate.verify("example", self.root)
        self.assertTrue(ok, errors)
        self.assertFalse((self.directory / "execution/ledger.sqlite").exists())
        self.assertNotIn("orchestration_manifest", payload["artifacts"])
        self.assertIn("archive", payload["artifacts"])

    def test_missing_outputs_do_not_advance(self):
        flow.initialize(self.args)
        before = (self.directory / "run.json").read_bytes()
        with self.assertRaises(config.RuntimeConfigurationError):
            flow.approve(self.args)
        self.assertEqual((self.directory / "run.json").read_bytes(), before)

    def test_artifact_cannot_escape_run(self):
        flow.initialize(self.args)
        outside = self.root / "outside.md"
        outside.write_text("wrong scope")
        (self.directory / "requirements.md").symlink_to(outside)
        (self.directory / "acceptance-criteria.md").write_text("criteria")
        with self.assertRaises(config.RuntimeConfigurationError):
            flow.approve(self.args)
        self.assertEqual(runstate.status("example", self.root)["state"], "defining")

    def test_native_handoff_preserves_subscription_and_does_not_launch(self):
        flow.initialize(self.args)
        task = self.root / "task.md"
        task.write_text("Review code")
        runtime = self.root / ".flow/runtime.toml"
        runtime.write_text('default_profile="native"\n[profiles.native]\nkind="codex"\n')
        self.args.task_file = task
        self.args.role = self.args.profile = None
        result = flow.native_handoff(self.args)
        self.assertEqual(result["provider"], "codex")
        self.assertIn("permission settings", Path(result["artifact"]).read_text())
        self.assertNotIn("sessions", runstate.status("example", self.root))

    def test_native_access_decision_precedes_execution_and_state_mutation(self):
        flow.initialize(self.args)
        task = self.root / "task.md"
        task.write_text("Do not launch without scoped access approval")
        (self.root / ".flow/runtime.toml").write_text('default_profile="native"\n[profiles.native]\nkind="codex"\n')
        self.args.task_file = task
        self.args.role = self.args.profile = None
        self.args.stage = "define"
        before = (self.directory / "run.json").read_bytes()
        with self.assertRaisesRegex(config.RuntimeConfigurationError, "Native access decision required"):
            flow.execute(self.args)
        self.assertEqual(before, (self.directory / "run.json").read_bytes())
        import openhands_runtime
        selection = config.select(self.root, "define")
        with self.assertRaisesRegex(config.RuntimeConfigurationError, "Native access decision required"):
            openhands_runtime.build_native_agent(selection, self.root)

    def test_sdk_error_status_is_cli_failure(self):
        handler = flow._handler(lambda _: {"work_id": "example", "stage": "define",
                                          "session": {"status": "error", "conversation_id": "test"}})
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(handler(Namespace(json=True)), 1)

    def test_legacy_runs_are_not_migrated_or_resumed(self):
        runstate.apply_transition("example", "start-definition", root=self.root)
        before = (self.directory / "run.json").read_bytes()
        with self.assertRaises(config.RuntimeConfigurationError):
            flow._run(self.root, "example")
        self.assertEqual(before, (self.directory / "run.json").read_bytes())

    def test_overlay_and_different_specialist_profiles(self):
        user = self.root / "user"
        user.mkdir()
        (user / "runtime.toml").write_text('default_profile="cpu"\n[profiles.cpu]\nkind="local"\nmodel="openai/coder"\nbase_url="http://localhost:8000/v1"\n')
        (self.root / ".flow").mkdir()
        (self.root / ".flow/runtime.toml").write_text('[profiles.gpu]\nkind="local"\nmodel="ollama_chat/coder"\nbase_url="http://self-hosted:11434"\n[roles.quality-reviewer]\nprofile="gpu"\n')
        self.assertEqual(config.select(self.root, "implement", user_overlay=user).profile, "cpu")
        self.assertEqual(config.select(self.root, "review", user_overlay=user).profile, "gpu")

    def test_local_profiles_cannot_fall_back_to_vendor_api_or_native_key(self):
        for change in ({"base_url": "https://api.openai.com/v1"}, {"api_key_env": "ANTHROPIC_API_KEY"}, {"api_key": "not-allowed"}, {"base_url": ""}):
            provider = {"kind": "local", "model": "openai/coder", "base_url": "http://localhost:8000/v1", **change}
            with self.subTest(change=change), self.assertRaises(config.RuntimeConfigurationError):
                config.select(self.root, "define", config={"default_profile": "test", "profiles": {"test": provider}})


if __name__ == "__main__":
    unittest.main()
