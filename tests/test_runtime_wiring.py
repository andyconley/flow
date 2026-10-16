"""Configuration and install wiring; no models, native adapters or credentials."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))
import openhands_config as config


class RuntimeWiringTests(unittest.TestCase):
    def test_native_setup_preserves_user_configuration_and_grants_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config.provision_native_profiles(root)
            path = root / "runtime.toml"
            original = path.read_bytes()
            loaded = config.load_config(root, root)
            self.assertEqual(set(loaded["profiles"]), {"claude", "codex", "openhands-coordinator"})
            self.assertNotIn("default_profile", loaded)
            self.assertTrue(all("permission_requests" not in p for p in loaded["profiles"].values()))
            config.provision_native_profiles(root)
            self.assertEqual(path.read_bytes(), original)
            path.write_text("# custom\ndefault_profile='mine'\n")
            config.provision_native_profiles(root)
            self.assertEqual(path.read_text(), "# custom\ndefault_profile='mine'\n")

    def test_native_role_model_defaults_and_explicit_override(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config.provision_native_profiles(root)
            selected = config.select(root, "plan", profile="claude", user_overlay=root)
            self.assertEqual(selected.role, "lead-developer")
            self.assertEqual(selected.provider["model"], "sonnet")
            cfg = config.load_config(root, root)
            cfg["profiles"]["claude"]["model"] = "custom-model"
            selected = config.select(root, "plan", profile="claude", config=cfg, user_overlay=root)
            self.assertEqual(selected.provider["model"], "custom-model")
            with self.assertRaisesRegex(config.RuntimeConfigurationError, "No runtime profile selected"):
                config.select(root, "plan", user_overlay=root)

    def test_readonly_wiring_distinguishes_native_handoff_and_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(len(config.wiring_report(root, root)["routes"]), 39)
            config.provision_native_profiles(root)
            before = (root / "runtime.toml").read_bytes()
            report = config.wiring_report(root, root)
            self.assertEqual(len(report["routes"]), 39)
            report["routes"] = [r for r in report["routes"] if r.get("kind") in {"claude", "codex"}]
            self.assertTrue(all(r["interactive_handoff_configured"] for r in report["routes"]))
            self.assertTrue(all(r["execution_configured"] and r["human_terminal_required"] for r in report["routes"]))
            self.assertTrue(all(r["permission_requests"] == "interactive" for r in report["routes"]))
            self.assertEqual((root / "runtime.toml").read_bytes(), before)

    def test_local_reasoning_is_forwarded_to_sdk(self):
        from openhands_runtime import local_llm
        selected = config.Selection("lead-developer", "local", {
            "model": "openai/example", "base_url": "http://localhost:8000/v1",
            "reasoning_effort": "medium"}, Path(__file__), {}, {})
        with patch("openhands.sdk.LLM") as llm:
            local_llm(selected)
            self.assertEqual(llm.call_args.kwargs["reasoning_effort"], "medium")

    def test_native_context_keeps_composed_expertise(self):
        from openhands_runtime import role_context
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config.provision_native_profiles(root)
            selected = config.select(root, "implement", profile="claude", user_overlay=root)
            _, prompt = role_context(selected)
            self.assertIn("## Expertise", prompt)
            self.assertIn("Plan a reversible delivery path", prompt)

    def test_update_uses_installed_cli_for_profiles_after_all_adapters(self):
        import lifecycle
        from types import SimpleNamespace
        with patch.object(lifecycle.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
            self.assertEqual(lifecycle._sync_installed_adapters(), 0)
        calls = [call.args[0][2:] for call in run.call_args_list]
        self.assertEqual(calls, [["sync", target, "--user"] for target in ("claude", "codex", "openhands")] + [["setup", "runtime"]])
